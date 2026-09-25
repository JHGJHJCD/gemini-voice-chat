"""
aec.py - ביטול הד אקוסטי (Acoustic Echo Cancellation) לשיחה ברמקולים.

הבעיה: כש-Gemini מדבר מהרמקול, הקול שלו חוזר למיקרופון, נשלח אליו בחזרה,
והוא "עונה לעצמו". חוק של סף-עוצמה לא מספיק - ברמקולים חזקים ההד עובר את הסף.

הפתרון (כמו בכל תוכנת שיחות וידאו):
1. **אות ייחוס** - שומרים בדיוק את מה שהושמע ברמקול (ReferenceBuffer).
2. **מסנן אדפטיבי** (PBFDAF - Partitioned-Block Frequency-Domain Adaptive
   Filter, אלגוריתם NLMS בתחום התדר) לומד את "דרך ההד" (רמקול→חדר→מיקרופון,
   כולל ההשהיה של כרטיס הקול) ומחסר את ההד המשוער מהמיקרופון (EchoCanceller).
3. **שער החלטה** (EchoGate) - מחליט בכל בלוק: זה רק הד שנשאר (לא לשלוח),
   או שהמשתמש באמת מדבר (לשלוח את האות המנוקה - כך ההתפרצות עובדת).

הכל ב-numpy בלבד (בלי ספריות native) - כדי לא לסבך את הבנייה ל-exe.
עובד גם באוזניות: המסנן לומד ש"אין הד" (ההד המשוער ≈ 0) והאות עובר כמו שהוא.
"""

from __future__ import annotations

import threading

import numpy as np

RATE = 16000              # קצב הדגימה של המיקרופון (ושל האות המנוקה)
SUB_BLOCK = 400           # בלוק עיבוד פנימי: 25ms
PARTITIONS = 24           # 24 × 25ms = 600ms - זנב ההד המקסימלי שהמסנן מכסה
                          # (כולל השהיית כרטיס הקול ~50-250ms)
_EPS = 1e-8

# עוצמת RMS (0..1) שמתחתיה מתייחסים לרמקול כ"שקט"
FAR_FLOOR = 0.002
# רמת RMS מינימלית לאות מנוקה כדי להיחשב "המשתמש מדבר" (מסנן רעש רקע)
NEAR_FLOOR = 0.015
# כמה ביחס להד-השארית-המשוער האות צריך להיות כדי להיחשב דיבור של המשתמש
NEAR_RATIO = 2.5
# ERLE (Echo Return Loss Enhancement, ב-dB): הנחה שמרנית בהתחלה, ותקרה
ERLE_INITIAL_DB = 6.0
ERLE_MAX_DB = 20.0
# כמה בלוקי-התאמה (25ms עם רמקול פעיל) עד שסומכים על המסנן (~1 שנייה)
TRAINED_BLOCKS = 40
# חלון בלוקים (של 25ms) שבו הרמקול נחשב "פעיל" אחרי שהאודיו נפסק
FAR_HANGOVER = 24         # 600ms
# מתאם (0..1) בין המיקרופון להד המשוער שמתחתיו האות "לא נראה כמו הד"
RHO_ECHO = 0.6
# דהיית מקדמים בזמן דיבור-כפול (לכל תת-בלוק)
NEAR_LEAK = 0.995


def pcm16_to_float(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def float_to_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()


def _lowpass_fir(numtaps: int, cutoff: float) -> np.ndarray:
    """מסנן FIR מעביר-נמוכים (sinc עם חלון Hamming). cutoff יחסי ל-Nyquist."""
    n = np.arange(numtaps) - (numtaps - 1) / 2.0
    h = np.sinc(cutoff * n) * cutoff
    h *= np.hamming(numtaps)
    return (h / h.sum()).astype(np.float32)


class _Resampler:
    """
    המרת קצב דגימה רציונלית (up/down) ב-numpy בלבד, עם המשכיות בין בלוקים
    (שומר את זנב הבלוק הקודם כדי שלא יהיו "קפיצות" בגבולות).
    24000→16000 = up 2, down 3.
    """

    def __init__(self, up: int, down: int, taps_per_phase: int = 12):
        self.up, self.down = up, down
        numtaps = taps_per_phase * max(up, down)
        if numtaps % 2 == 0:
            numtaps += 1
        self.h = _lowpass_fir(numtaps, 1.0 / max(up, down)) * up
        # כמה דגימות-מקור לשמור מהבלוק הקודם (אורך המסנן במקור)
        self.tail_len = int(np.ceil(numtaps / up)) + 1
        self._tail = np.zeros(self.tail_len, dtype=np.float32)
        self._phase = 0    # היסט הדצימציה בין בלוקים (כדי לא לאבד/להכפיל דגימה)

    def process(self, x: np.ndarray) -> np.ndarray:
        joined = np.concatenate([self._tail, x])
        self._tail = joined[-self.tail_len:]
        # upsample (זריעת אפסים) → סינון → decimate
        upsampled = np.zeros(joined.size * self.up, dtype=np.float32)
        upsampled[::self.up] = joined
        filtered = np.convolve(upsampled, self.h, mode="same")
        # חותכים את החלק שמקביל לזנב (כבר הוצא בבלוק הקודם)
        start = self.tail_len * self.up
        seg = filtered[start:]
        out = seg[self._phase::self.down]
        # היסט לבלוק הבא: איפה "נופלת" הדגימה הבאה
        consumed = seg.size - self._phase
        self._phase = (self.down - consumed % self.down) % self.down
        return out.astype(np.float32)

    def reset(self) -> None:
        self._tail[:] = 0.0
        self._phase = 0


class ReferenceBuffer:
    """
    אוסף את מה שבאמת הושמע ברמקול (24kHz) וממיר ל-16kHz - אות הייחוס למסנן.

    ההתאמה בזמן למיקרופון היא לפי *סדר הדגימות* (FIFO): שני הזרמים רצים
    באותו קצב, אז בלוק מיקרופון מס' k מקביל לבלוק ייחוס מס' k עד כדי היסט
    קבוע - וההיסט הקבוע הזה הוא בדיוק מה שהמסנן האדפטיבי לומד.
    """

    def __init__(self, src_rate: int = 24000, dst_rate: int = RATE,
                 max_seconds: float = 3.0):
        self.src_rate = src_rate
        self.dst_rate = dst_rate
        g = int(np.gcd(src_rate, dst_rate))
        self._resampler = (_Resampler(dst_rate // g, src_rate // g)
                           if src_rate != dst_rate else None)
        self._buf = np.zeros(0, dtype=np.float32)
        self._max = int(max_seconds * dst_rate)
        self._lock = threading.Lock()

    def push(self, pcm_src: bytes) -> None:
        """נקרא מ-callback הרמקול עם הבלוק שהושמע זה עתה (כולל שקט)."""
        x = pcm16_to_float(pcm_src)
        if x.size == 0:
            return
        y = self._resampler.process(x) if self._resampler else x
        with self._lock:
            self._buf = np.concatenate([self._buf, y])
            if self._buf.size > self._max:
                # הרמקול "ברח" קדימה (לא אמור לקרות) - זורקים את הישן
                self._buf = self._buf[-self._max:]

    def pull(self, n: int) -> np.ndarray:
        """מחזיר את n הדגימות הבאות (16kHz). אם אין מספיק - משלים בשקט."""
        with self._lock:
            take = self._buf[:n]
            self._buf = self._buf[n:]
        if take.size < n:
            take = np.concatenate([take, np.zeros(n - take.size, np.float32)])
        return take

    def reset(self) -> None:
        with self._lock:
            self._buf = np.zeros(0, dtype=np.float32)
        if self._resampler:
            self._resampler.reset()


class EchoCanceller:
    """מסנן אדפטיבי PBFDAF: לומד את דרך ההד ומחסר אותו מהמיקרופון."""

    def __init__(self, block: int = SUB_BLOCK, partitions: int = PARTITIONS,
                 mu: float = 0.5):
        self.N = block
        self.M = partitions
        self.mu = mu
        bins = block + 1
        self.W = np.zeros((partitions, bins), dtype=np.complex64)
        self.X_hist = np.zeros((partitions, bins), dtype=np.complex64)
        self.P = np.full(bins, _EPS, dtype=np.float32)   # הספק ייחוס לפי תדר
        self._x_prev = np.zeros(block, dtype=np.float32)
        # מעקב ERLE - הספקים מוחלקים, נמדדים רק בבלוקים של "הד בלבד"
        ratio = 10.0 ** (ERLE_INITIAL_DB / 10.0)
        self._d_pow = ratio * 1e-6
        self._e_pow = 1e-6
        self._far_blocks = 0
        self._adapt_blocks = 0
        self.last_far_rms = 0.0
        self.last_rho = 0.0

    # ---- מדדים ---------------------------------------------------------
    @property
    def erle_db(self) -> float:
        val = 10.0 * np.log10((self._d_pow + _EPS) / (self._e_pow + _EPS))
        return float(min(max(val, 0.0), ERLE_MAX_DB))

    @property
    def trained(self) -> bool:
        """המסנן ראה מספיק אודיו מהרמקול כדי שנסמוך על ההד המשוער."""
        return self._adapt_blocks >= TRAINED_BLOCKS

    @property
    def far_active(self) -> bool:
        """הרמקול השמיע משהו ב-600ms האחרונות."""
        return self._far_blocks > 0

    def near_threshold(self, y_rms: float) -> float:
        """סף RMS לאות המנוקה שמעליו זה דיבור של המשתמש ולא שארית הד."""
        expected_residual = y_rms * (10.0 ** (-self.erle_db / 20.0))
        return max(NEAR_FLOOR, NEAR_RATIO * expected_residual)

    # ---- עיבוד ---------------------------------------------------------
    def process_sub(self, d: np.ndarray, x: np.ndarray):
        """
        בלוק אחד של 25ms. מחזיר (אות מנוקה e, הד משוער y, המשתמש מדבר?).
        """
        N = self.N
        x_buf = np.concatenate([self._x_prev, x])
        self._x_prev = x
        X = np.fft.rfft(x_buf).astype(np.complex64)
        self.X_hist = np.roll(self.X_hist, 1, axis=0)
        self.X_hist[0] = X

        Y = (self.W * self.X_hist).sum(axis=0)
        y = np.fft.irfft(Y, n=2 * N)[N:].astype(np.float32)
        e = d - y

        far_rms = float(np.sqrt(np.mean(x * x) + _EPS))
        self.last_far_rms = far_rms
        if far_rms > FAR_FLOOR:
            self._far_blocks = FAR_HANGOVER
        elif self._far_blocks > 0:
            self._far_blocks -= 1

        e_rms = float(np.sqrt(np.mean(e * e) + _EPS))
        y_rms = float(np.sqrt(np.mean(y * y) + _EPS))
        # מתאם בין המיקרופון להד המשוער: הד בלבד → קרוב ל-1;
        # המשתמש מדבר (או אוזניות - אין הד) → נמוך. זה גלאי "דיבור כפול".
        rho = float(np.dot(d, y) / (np.sqrt(np.dot(d, d) * np.dot(y, y)) + _EPS))
        self.last_rho = rho
        # "המשתמש מדבר" = יש אות ממשי אחרי הניקוי, וגם: הוא לא נראה כמו
        # ההד (מתאם נמוך) או שהוא גדול משמעותית משארית ההד הצפויה
        near = self.trained and e_rms > NEAR_FLOOR and (
            rho < RHO_ECHO or e_rms > self.near_threshold(y_rms))

        # מתאימים את המסנן רק כשיש אות ייחוס (אחרת אין ממה ללמוד)
        if far_rms > FAR_FLOOR:
            mu = self.mu
            if near:
                # דיבור כפול: לא "לקלקל" את המסנן עם קול המשתמש, ולתת
                # למקדמים "רועשים" (שנלמדו מדיבור ולא מהד) לדהות בהדרגה
                mu *= 0.05
                self.W *= NEAR_LEAK
            else:
                self._d_pow = 0.9 * self._d_pow + 0.1 * float(np.mean(d * d))
                self._e_pow = 0.9 * self._e_pow + 0.1 * (e_rms * e_rms)
                self._adapt_blocks += 1

            self.P = 0.8 * self.P + 0.2 * (np.abs(self.X_hist) ** 2).sum(axis=0)
            E = np.fft.rfft(np.concatenate([np.zeros(N, np.float32), e]))
            reg = 1e-3 * float(self.P.mean()) + _EPS
            grad = mu * E[None, :] * np.conj(self.X_hist) / (self.P[None, :] + reg)
            self.W = (self.W + grad).astype(np.complex64)
            # אילוץ: רק החצי הראשון של כל חלק בתחום הזמן (overlap-save)
            w = np.fft.irfft(self.W, n=2 * N, axis=1)
            w[:, N:] = 0.0
            self.W = np.fft.rfft(w, axis=1).astype(np.complex64)

        return e, y, near

    def process(self, d: np.ndarray, x: np.ndarray):
        """
        בלוק בגודל כלשהו (כפולה של 25ms).
        מחזיר (e, y, מספר תת-הבלוקים שבהם זוהה דיבור של המשתמש).
        """
        n = d.size
        e_out = np.empty(n, dtype=np.float32)
        y_out = np.empty(n, dtype=np.float32)
        near_count = 0
        for i in range(0, n, self.N):
            e, y, near = self.process_sub(d[i:i + self.N], x[i:i + self.N])
            e_out[i:i + self.N] = e
            y_out[i:i + self.N] = y
            near_count += int(near)
        return e_out, y_out, near_count


class EchoGate:
    """
    שער ההחלטה: מה לשלוח ל-Gemini מכל בלוק מיקרופון.

    decide() מחזיר (לשלוח?, האות לשליחה, עוצמת RMS לאנימציה).
    """

    def __init__(self, barge_in_level: float = 0.22,
                 barge_in_window_blocks: int = 12):
        self.aec = EchoCanceller()
        self.barge_in_level = barge_in_level          # החוק הישן (לפני אימון)
        self._window = barge_in_window_blocks          # 12 × 100ms = 1.2s
        self._open_blocks = 0

    def decide(self, mic: np.ndarray, ref: np.ndarray):
        e, y, near_count = self.aec.process(mic, ref)
        e_rms = float(np.sqrt(np.mean(e * e) + _EPS))

        if not self.aec.far_active:
            # הרמקול שקט - אין הד. שולחים את האות (המנוקה - זהה בפועל).
            self._open_blocks = 0
            return True, e, e_rms

        if self.aec.trained:
            # המסנן עובד: לפחות חצי מתת-הבלוקים זוהו כדיבור של המשתמש
            sub_blocks = max(1, mic.size // self.aec.N)
            near = near_count * 2 >= sub_blocks
        else:
            # השנייה הראשונה - המסנן עוד לומד: חוק העוצמה הישן
            d_rms = float(np.sqrt(np.mean(mic * mic) + _EPS))
            near = d_rms >= self.barge_in_level

        if near:
            self._open_blocks = self._window
        if self._open_blocks > 0:
            self._open_blocks -= 1
            return True, e, e_rms
        return False, e, 0.0
