"""
test_aec.py - בדיקות לביטול ההד (aec.py) עם הד מדומה.
הרץ: pytest test_aec.py -v
"""
import numpy as np
import pytest

import aec


def _speech_like(n, seed, rate=16000):
    """אות "דומה לדיבור": רעש מסונן עם מעטפת משתנה."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n).astype(np.float32)
    # מסנן פס-נמוך גס (ממוצע נע) + מעטפת של הברות
    x = np.convolve(x, np.ones(8) / 8, mode="same")
    t = np.arange(n) / rate
    env = 0.5 + 0.5 * np.abs(np.sin(2 * np.pi * 3.0 * t))
    x = x * env
    return (0.3 * x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def _echo_path(x, delay, gain=0.8, tail=0.3):
    """הד: השהיה + הנחתה + זנב הדהוד קצר."""
    h = np.zeros(delay + 800, dtype=np.float32)
    h[delay] = gain
    h[delay + 200] = gain * tail
    h[delay + 500] = gain * tail * 0.4
    return np.convolve(x, h)[: x.size].astype(np.float32)


def _run_blocks(gate, mic, ref, block=1600):
    decisions = []
    for i in range(0, mic.size - block + 1, block):
        send, e, lvl = gate.decide(mic[i:i + block], ref[i:i + block])
        decisions.append((send, float(np.sqrt(np.mean(e * e)))))
    return decisions


def test_canceller_converges_on_pure_echo():
    """רק הד (המשתמש שותק): המסנן צריך להוריד את ההד ב->10dB תוך ~2 שניות."""
    rate = 16000
    ref = _speech_like(rate * 6, seed=1)
    mic = _echo_path(ref, delay=int(0.12 * rate))       # הד עם השהיה 120ms
    canc = aec.EchoCanceller()
    e, _, _ = canc.process(mic, ref)
    # מודדים ב-3 השניות האחרונות (אחרי התכנסות)
    tail = slice(rate * 3, rate * 6)
    erle = 10 * np.log10(np.mean(mic[tail] ** 2) / (np.mean(e[tail] ** 2) + 1e-12))
    assert erle > 10.0, f"ERLE נמוך מדי: {erle:.1f} dB"
    assert canc.trained
    assert canc.erle_db > 6.0


def test_gate_blocks_echo_and_passes_user_speech():
    """
    1) בזמן ש-Gemini מדבר והמשתמש שותק - לא שולחים כלום (אחרי התכנסות).
    2) כשהמשתמש מדבר מעל ההד - שולחים, והאות שנשלח נקי ברובו מההד.
    """
    rate = 16000
    ref = _speech_like(rate * 8, seed=2)
    echo = _echo_path(ref, delay=int(0.09 * rate), gain=0.9)
    user = _speech_like(rate * 8, seed=3) * 0.8
    # המשתמש מדבר רק בשניות 5-7
    mask = np.zeros_like(user)
    mask[rate * 5: rate * 7] = 1.0
    user = user * mask
    mic = (echo + user).astype(np.float32)

    gate = aec.EchoGate()
    dec = _run_blocks(gate, mic, ref)
    per_sec = rate // 1600   # 10 בלוקים בשנייה

    # שניות 3-5: רק הד, המסנן כבר התכנס - אסור לשלוח
    echo_only = dec[3 * per_sec: 5 * per_sec]
    sent = sum(1 for s, _ in echo_only if s)
    assert sent <= 1, f"נשלחו {sent} בלוקי הד מתוך {len(echo_only)}"

    # שניות 5-7: המשתמש מדבר - חייבים לשלוח את רוב הבלוקים
    talking = dec[5 * per_sec: 7 * per_sec]
    sent = sum(1 for s, _ in talking if s)
    assert sent >= len(talking) * 0.7, f"נשלחו רק {sent} מתוך {len(talking)}"


def test_headphones_no_echo_passes_everything():
    """באוזניות אין הד: כשהמשתמש מדבר בזמן ש-Gemini מדבר - עובר כמו שהוא."""
    rate = 16000
    ref = _speech_like(rate * 4, seed=4)
    user = _speech_like(rate * 4, seed=5) * 0.6
    gate = aec.EchoGate()
    dec = _run_blocks(gate, user, ref)
    # המשתמש מדבר כל הזמן - אחרי שנייה של "אימון" (המסנן לומד שאין הד)
    # כל הבלוקים צריכים להישלח
    after_warmup = dec[15:]
    sent = sum(1 for s, _ in after_warmup if s)
    assert sent >= len(after_warmup) * 0.9, f"{sent}/{len(after_warmup)}"
    # והאות שנשלח לא עוות: ה-RMS שלו קרוב ל-RMS של המשתמש
    rate_blocks = [r for (s, r) in after_warmup if s]
    assert np.mean(rate_blocks) > 0.6 * np.sqrt(np.mean(user[rate * 2:] ** 2))


def test_reference_buffer_resamples_24k_to_16k():
    rb = aec.ReferenceBuffer()
    # טון רציף של 440Hz, נדחף בבלוקים של 100ms (כמו ה-callback של הרמקול)
    t = np.arange(2400 * 5) / 24000.0
    tone = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    for i in range(5):
        rb.push(tone[i * 2400:(i + 1) * 2400].tobytes())
    out = rb.pull(1600 * 5)
    assert out.size == 1600 * 5
    # אחרי ההתייצבות: אמפליטודה נשמרת, ואין "קפיצות" בגבולות הבלוקים -
    # האות צריך להתאים לטון 440Hz נקי ב-16kHz (עד כדי היסט קטן של המסנן)
    t16 = np.arange(1600 * 5) / 16000.0
    seg = out[1600:4800]
    assert 0.4 < np.abs(seg).max() < 0.6
    best = max(np.corrcoef(seg, np.sin(2 * np.pi * 440 * t16[1600:4800] + ph))[0, 1]
               for ph in np.linspace(0, 2 * np.pi, 64, endpoint=False))
    assert best > 0.98, f"התאמה לטון נקי: {best:.3f}"
    # משיכה ללא נתונים מחזירה שקט באורך הנכון
    assert rb.pull(100).size == 100
