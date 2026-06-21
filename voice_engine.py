#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
voice_engine.py
---------------
המנוע הקולי - שיחת קול רציפה ודו-כיוונית עם Gemini Live.

זה הלב של מצב הקול. הוא מתאם שלושה זרמים בו-זמנית:
  1. מיקרופון  → שליחה רציפה ל-Gemini (16kHz PCM)
  2. Gemini     → קבלת אודיו רציפה (24kHz PCM)
  3. אודיו מ-Gemini → השמעה ברמקול

יכולות:
  - זיהוי דיבור אוטומטי (VAD מובנה של Gemini) - לא צריך ללחוץ "סיימתי".
  - הפרעה (barge-in) - אם המשתמש מדבר בזמן ש-Gemini מדבר, ההשמעה נעצרת.
  - תמלול - גם של המשתמש וגם של Gemini (לתצוגה בממשק).
  - תמיכה בנטפרי דרך truststore.

ארכיטקטורה טכנית:
  המנוע רץ ב-asyncio event loop בתוך thread נפרד (כדי לא לחסום את ה-GUI).
  המיקרופון והרמקול עובדים עם callbacks של sounddevice, ומתקשרים עם
  ה-asyncio loop דרך תורים (queues) בטוחי-thread.

  התקשורת עם ה-GUI נעשית דרך callbacks פשוטים (on_status, on_user_text...).
"""

import asyncio
import os
import queue
import threading
import time
import traceback
import wave
from typing import Callable, Optional

# מעקף נטפרי - חייב לפני ייבוא google-genai וכל חיבור רשת
import truststore
truststore.inject_into_ssl()

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types


# ---------------------------------------------------------------------- #
# קבועים - פורמט האודיו נקבע ע"י דרישות Gemini Live
# ---------------------------------------------------------------------- #
SEND_RATE = 16000      # קצב דגימה לשליחה (דרישת Gemini)
RECV_RATE = 24000      # קצב דגימה לקבלה (פלט Gemini)
CHANNELS = 1           # מונו
BLOCK = 1600           # גודל בלוק מיקרופון (~100ms ב-16kHz)
FORMAT = "int16"       # 16-bit PCM

# מודל אודיו ילידי - הקול הכי טבעי, תומך עברית
MODEL = "gemini-2.5-flash-native-audio-preview-09-2025"

# מודל תרגום חי ייעודי - תרגום סימולטני זורם בהשהיה נמוכה (תרגום וידאו)
TRANSLATE_MODEL = "gemini-3.5-live-translate-preview"
TRANSLATE_TARGET = "he"   # קוד שפת יעד (BCP-47) - עברית

SYSTEM_INSTRUCTION = (
    "אתה עוזר קולי ידידותי שמדבר עברית בצורה טבעית וזורמת. "
    "דבר בקצרה ולעניין, כמו בשיחה אמיתית. "
    "אל תשתמש בסימני פיסוק מיוחדים או אימוג'ים בתשובות."
)

# הנחיה למצב תרגום וידאו - Gemini שומע את קול המערכת ומתרגם לעברית ברצף
TRANSLATE_INSTRUCTION = (
    "אתה מנוע תרגום בלבד - לא עוזר ולא בן שיח. "
    "תפקידך היחיד: לתרגם לעברית את מה שנאמר בשפה זרה (אנגלית או אחרת) "
    "ולומר בקול רק את התרגום. "
    "אסור לך בשום אופן: לשאול שאלות, להציע עזרה, להסביר מילים, "
    "להוסיף הערות, או לנהל שיחה. אתה אך ורק מתרגם. "
    "אם אתה שומע דיבור בעברית - התעלם ממנו לחלוטין, אל תתרגם ואל תחזור עליו, "
    "זה הקול שלך עצמך. "
    "אם אתה לא בטוח מה נאמר, או שאתה שומע שקט/מוזיקה/רעש בלבד - שתוק לגמרי. "
    "תרגם ברצף תוך כדי הדיבור."
)

# מספר ניסיונות חיבור-מחדש אוטומטיים לפני ויתור
MAX_RECONNECT = 5

# סף עוצמת קול (0..1) לזיהוי התפרצות בזמן דיכוי הד.
# קול חזק מעל הסף בזמן ש-Gemini מדבר = המשתמש רוצה להפריע.
BARGE_IN_LEVEL = 0.22


class _FatalError(Exception):
    """שגיאה שאין טעם לנסות אחריה שוב (מפתח שגוי, SSL)."""
    pass


class VoiceEngine:
    """
    מנוע שיחה קולית עם Gemini Live.

    שימוש:
        engine = VoiceEngine(
            api_key="...",
            on_status=lambda s: print(s),
            on_user_text=lambda t: print("אתה:", t),
            on_bot_text=lambda t: print("Gemini:", t),
        )
        engine.start()   # מתחיל שיחה (לא חוסם)
        ...
        engine.stop()    # מסיים שיחה
    """

    def __init__(
        self,
        api_key: str,
        voice_name: str = "Aoede",
        input_device: int | None = None,
        output_device: int | None = None,
        system_instruction: str | None = None,
        web_search: bool = False,
        deep_thinking: bool = False,
        computer_control: bool = False,
        affective_dialog: bool = True,
        proactive_audio: bool = False,
        thinking_level: str = "minimal",
        silence_duration_ms: int = 800,
        start_speech_sensitivity: str = "MEDIUM",
        end_speech_sensitivity: str = "MEDIUM",
        capture_mode: str = "mic",
        on_status: Optional[Callable[[str], None]] = None,
        on_user_text: Optional[Callable[[str], None]] = None,
        on_bot_text: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_level: Optional[Callable[[float], None]] = None,
    ):
        self.api_key = api_key
        self.voice_name = voice_name          # קול Gemini (Aoede, Kore...)
        self.input_device = input_device      # אינדקס מיקרופון (None=ברירת מחדל)
        self.output_device = output_device    # אינדקס רמקול/אוזניות
        # במצב תרגום וידאו - הנחיית תרגום קבועה (מתעלמים מהנחיה שהועברה)
        if capture_mode == "system":
            self.system_instruction = TRANSLATE_INSTRUCTION
            # תרגום דורש התנהגות דטרמיניסטית - בלי פטפוט רגשי
            affective_dialog = False
            proactive_audio = False
        else:
            self.system_instruction = system_instruction or SYSTEM_INSTRUCTION
        self.web_search = web_search        # כלי חיפוש Google
        self.deep_thinking = deep_thinking  # מצב חשיבה מורחב
        self.computer_control = computer_control  # פתיחת תוכנות/אתרים בקול
        self.affective_dialog = affective_dialog
        self.proactive_audio = proactive_audio
        self.thinking_level = thinking_level
        self.silence_duration_ms = silence_duration_ms
        self.start_speech_sensitivity = start_speech_sensitivity
        self.end_speech_sensitivity = end_speech_sensitivity
        # מצב לכידה: "mic" = מיקרופון רגיל, "system" = קול המערכת (תרגום וידאו)
        self.capture_mode = capture_mode
        self._loopback_thread: Optional[threading.Thread] = None
        self._proctap = None              # לכידת דפדפן (proc-tap)
        self._browser_capture = False     # True כשלוכדים דפדפן בלבד (אין משוב)
        self._browser_rate = 48000
        self._browser_channels = 2
        self._browser_pid = None          # ה-PID שנלכד כרגע (ל-watchdog)
        self._last_browser_audio = 0.0    # מתי הגיע אודיו אחרון מהדפדפן
        self._watchdog_thread: Optional[threading.Thread] = None
        # דיכוי הד - השתקת מיקרופון בזמן ש-Gemini מדבר (לרמקולים)
        self.echo_suppression = True
        self._last_output_time = 0.0        # מתי הושמע אודיו לאחרונה
        self._barge_in_until = 0.0          # עד מתי חלון התפרצות פתוח
        self.on_status = on_status or (lambda s: None)
        self.on_user_text = on_user_text or (lambda t: None)
        self.on_bot_text = on_bot_text or (lambda t: None)
        self.on_error = on_error or (lambda e: None)
        # עוצמת קול (0..1) לאנימציה מגיבה בממשק
        self.on_level = on_level or (lambda lvl: None)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._tasks: list[asyncio.Task] = []
        self._reconnect_attempts = 0
        self._session = None

        # תורים בטוחי-thread בין callbacks של sounddevice ל-asyncio
        self._mic_queue: "queue.Queue[bytes]" = queue.Queue()
        self._play_queue: "queue.Queue[bytes]" = queue.Queue()

        self._in_stream: Optional[sd.RawInputStream] = None
        self._out_stream: Optional[sd.RawOutputStream] = None

        # השתקת מיקרופון - כשמושתק, ממשיכים לרוקן את התור אך לא שולחים
        self.mic_muted = False

        # פריים וידאו אחרון לשליחה (מסך/מצלמה). None = אין וידאו.
        # נכתב מ-thread ה-UI, נקרא מ-thread ה-asyncio - גישה אטומית ב-Python.
        self._video_frame: bytes | None = None

        # הקלטת השיחה - מיקס של המיקרופון ושל Gemini לציר זמן משותף
        self.recording = False
        self._rec_lock = threading.Lock()
        self._rec_samples = np.zeros(0, dtype=np.int32)  # מצבר 24kHz מונו
        self._rec_start = 0.0

    # ================================================================== #
    # API ציבורי
    # ================================================================== #
    def start(self):
        """מתחיל שיחה קולית ב-thread נפרד. לא חוסם."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """עוצר את השיחה ומשחרר משאבים בצורה מסודרת."""
        self._running = False
        # ביטול המשימות בצורה מסודרת - מאפשר ל-async with לסגור
        # את ה-WebSocket כראוי במקום לקטוע את הלולאה באמצע.
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._cancel_tasks)

    def _cancel_tasks(self):
        """מבטל את משימות ה-asyncio (נקרא בתוך ה-loop)."""
        for task in self._tasks:
            if not task.done():
                task.cancel()

    def is_running(self) -> bool:
        return self._running

    def set_muted(self, muted: bool):
        """משתיק/מבטל השתקה של המיקרופון (לא מנתק את השיחה)."""
        self.mic_muted = muted

    def set_echo_suppression(self, enabled: bool):
        """מפעיל/מכבה דיכוי הד (השתקת מיק בזמן דיבור של Gemini)."""
        self.echo_suppression = enabled

    def set_video_frame(self, jpeg: bytes | None):
        """
        מעדכן את פריים הווידאו האחרון שיישלח ל-Gemini.
        נקרא מ-thread ה-UI. None = הפסקת שליחת וידאו.
        """
        self._video_frame = jpeg

    def send_text(self, text: str) -> bool:
        """
        שולח טקסט ל-Gemini באמצע שיחה (למשל תוכן מסמך).
        נקרא מ-thread ה-UI; מתזמן את השליחה ב-event loop של המנוע.
        """
        if not self._running or not self._loop or not self._session:
            return False
        try:
            coro = self._session.send_client_content(
                turns={"role": "user", "parts": [{"text": text}]},
                turn_complete=True,
            )
            asyncio.run_coroutine_threadsafe(coro, self._loop)
            return True
        except Exception:
            return False

    # ================================================================== #
    # הקלטת השיחה
    # ================================================================== #
    def start_recording(self):
        """מתחיל להקליט את השיחה (מיקרופון + Gemini) למיקס אחד."""
        with self._rec_lock:
            self._rec_samples = np.zeros(0, dtype=np.int32)
            self._rec_start = time.monotonic()
            self.recording = True

    def stop_recording(self, path: str) -> bool:
        """
        עוצר הקלטה ושומר לקובץ WAV (24kHz מונו).
        מחזיר True אם נשמר בהצלחה.
        """
        with self._rec_lock:
            self.recording = False
            samples = self._rec_samples
            self._rec_samples = np.zeros(0, dtype=np.int32)

        if len(samples) == 0:
            return False

        # חיתוך לטווח int16 (מניעת עיוות מהמיקס)
        clipped = np.clip(samples, -32768, 32767).astype(np.int16)
        try:
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)        # 16-bit
                wf.setframerate(RECV_RATE)
                wf.writeframes(clipped.tobytes())
            return True
        except Exception:
            return False

    @staticmethod
    def _rms_level(pcm_bytes: bytes) -> float:
        """מחשב עוצמת קול מנורמלת (0..1) מ-PCM int16."""
        arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        if arr.size == 0:
            return 0.0
        rms = np.sqrt(np.mean(arr.astype(np.float32) ** 2))
        # נרמול לוגריתמי גס לטווח 0..1 (32768 = max)
        return float(min(rms / 8000.0, 1.0))

    def _mix_into_recording(self, pcm_bytes: bytes, rate: int):
        """
        מערבב חתיכת אודיו לתוך ההקלטה בציר זמן משותף (לפי שעון).
        מיקרופון (16kHz) עובר דגימה-מחדש ל-24kHz. הכל מתווסף (מיקס).
        """
        if not self.recording:
            return
        arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        if rate != RECV_RATE:
            # דגימה-מחדש לינארית ל-24kHz
            n_dst = int(len(arr) * RECV_RATE / rate)
            if n_dst <= 0:
                return
            arr = np.interp(
                np.linspace(0, len(arr), n_dst, endpoint=False),
                np.arange(len(arr)), arr,
            )
        arr = arr.astype(np.int32)

        with self._rec_lock:
            if not self.recording:
                return
            # מיקום הכתיבה לפי הזמן שחלף מתחילת ההקלטה
            pos = int((time.monotonic() - self._rec_start) * RECV_RATE)
            if pos < 0:
                pos = 0
            end = pos + len(arr)
            if end > len(self._rec_samples):
                # הארכת המצבר בשקט
                self._rec_samples = np.concatenate([
                    self._rec_samples,
                    np.zeros(end - len(self._rec_samples), dtype=np.int32),
                ])
            # מיקס (חיבור) - כך שדיבור בו-זמני לא דורס
            self._rec_samples[pos:end] += arr

    # ================================================================== #
    # לולאת asyncio (רצה ב-thread הנפרד)
    # ================================================================== #
    def _run_loop(self):
        """נקודת הכניסה של ה-thread - מריץ את ה-asyncio loop."""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._main_with_reconnect())
        except Exception as e:
            self.on_error(f"שגיאה במנוע הקולי: {e}")
            traceback.print_exc()
        finally:
            self._cleanup_audio()
            self._running = False
            self.on_status("stopped")

    async def _main_with_reconnect(self):
        """
        מריץ את השיחה ומתחבר מחדש אוטומטית אם החיבור נופל באמצע.
        שגיאות "קטלניות" (מפתח שגוי, SSL) לא מנסות מחדש - אין טעם.
        """
        self._reconnect_attempts = 0
        while self._running:
            try:
                await self._session_main()
                return  # יציאה נקייה (המשתמש עצר)
            except asyncio.CancelledError:
                return
            except _FatalError as e:
                self.on_error(str(e))
                return
            except Exception:
                # שגיאה זמנית (חיבור נפל) - מנסים להתחבר מחדש
                self._cleanup_audio()
                if not self._running:
                    return
                self._reconnect_attempts += 1
                if self._reconnect_attempts > MAX_RECONNECT:
                    self.on_error(
                        "החיבור נכשל שוב ושוב. נסה להתחיל שיחה מחדש."
                    )
                    return
                self.on_status("reconnecting")
                # השהיה הולכת וגדלה בין ניסיונות (backoff)
                await asyncio.sleep(min(2 * self._reconnect_attempts, 8))

    async def _session_main(self):
        """
        מנהל את החיבור ל-Gemini. שני המצבים (תרגום וידאו / שיחה רגילה)
        חולקים את אותו מנגנון סשן (_run_session) - רק בניית ה-config שונה,
        ומופרדת לשתי פונקציות נפרדות וברורות.
        """
        self.on_status("connecting")
        if self.capture_mode == "system":
            client, model, config = self._build_translate_setup()
        else:
            client, model, config = self._build_conversation_setup()
        await self._run_session(client, model, config)

    def _build_translate_setup(self):
        """מצב תרגום וידאו: מודל תרגום חי ייעודי (זורם, השהיה נמוכה)."""
        client = genai.Client(api_key=self.api_key)
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            translation_config=types.TranslationConfig(
                target_language_code=TRANSLATE_TARGET,
                echo_target_language=True,
            ),
        )
        return client, TRANSLATE_MODEL, config

    def _build_conversation_setup(self):
        """מצב שיחה רגיל: קול, VAD, כלים, חשיבה, דיאלוג רגשי."""
        # v1alpha נדרש רק לדיאלוג רגשי / אודיו פרואקטיבי
        client_kwargs = {"api_key": self.api_key}
        if self.affective_dialog or self.proactive_audio:
            client_kwargs["http_options"] = {"api_version": "v1alpha"}
        client = genai.Client(**client_kwargs)

        config = {
            "response_modalities": ["AUDIO"],
            "system_instruction": self.system_instruction,
            "speech_config": types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice_name
                    )
                )
            ),
            "input_audio_transcription": {},
            "output_audio_transcription": {},
        }

        # כוונון זיהוי דיבור (VAD) - רגישות נשלחת רק אם LOW/HIGH
        # (ב-SDK יש רק LOW/HIGH; MEDIUM = ברירת מחדל השרת)
        sensitivity_map = {
            "LOW": types.StartSensitivity.START_SENSITIVITY_LOW,
            "HIGH": types.StartSensitivity.START_SENSITIVITY_HIGH,
        }
        end_sensitivity_map = {
            "LOW": types.EndSensitivity.END_SENSITIVITY_LOW,
            "HIGH": types.EndSensitivity.END_SENSITIVITY_HIGH,
        }
        vad = {
            "prefix_padding_ms": 20,
            "silence_duration_ms": self.silence_duration_ms,
        }
        if self.start_speech_sensitivity in sensitivity_map:
            vad["start_of_speech_sensitivity"] = \
                sensitivity_map[self.start_speech_sensitivity]
        if self.end_speech_sensitivity in end_sensitivity_map:
            vad["end_of_speech_sensitivity"] = \
                end_sensitivity_map[self.end_speech_sensitivity]
        config["realtime_input_config"] = {"automatic_activity_detection": vad}

        if self.affective_dialog:
            config["enable_affective_dialog"] = True
        if self.proactive_audio:
            config["proactivity"] = {"proactive_audio": True}

        # כלים: חיפוש Google + שליטה במחשב
        tools = []
        if self.web_search:
            tools.append({"google_search": {}})
        if self.computer_control:
            import computer_tools
            tools.append({"function_declarations":
                          computer_tools.FUNCTION_DECLARATIONS})
        if tools:
            config["tools"] = tools

        # חשיבה - המודל 2.5 תומך ב-thinking_budget (לא thinking_level)
        if self.deep_thinking:
            budget_map = {"minimal": 512, "low": 1024,
                          "medium": 2048, "high": 4096}
            config["thinking_config"] = types.ThinkingConfig(
                thinking_budget=budget_map.get(self.thinking_level, 2048))

        return client, MODEL, config

    async def _run_session(self, client, model, config):
        """מתחבר ל-Gemini, פותח זרמי אודיו, ומריץ את המשימות המקבילות."""
        try:
            async with client.aio.live.connect(model=model, config=config) as session:
                self._session = session
                self._open_audio_streams()
                self.on_status("listening")
                # חיבור יציב - מאפסים את מונה הניסיונות
                self._reconnect_attempts = 0

                # משימות מקבילות: מיקרופון + וידאו + קבלת אודיו.
                # שומרים אותן כדי שאפשר יהיה לבטל בצורה מסודרת ב-stop().
                self._tasks = [
                    asyncio.create_task(self._send_mic(session)),
                    asyncio.create_task(self._send_video(session)),
                    asyncio.create_task(self._receive(session)),
                ]
                try:
                    await asyncio.gather(*self._tasks)
                except asyncio.CancelledError:
                    pass  # כיבוי יזום - תקין
        except asyncio.CancelledError:
            pass  # כיבוי יזום - יציאה נקייה
        except Exception as e:
            err = str(e)
            low = err.lower()
            # שגיאות קטלניות - אין טעם לנסות מחדש
            if "SSL" in err or "certificate" in low:
                raise _FatalError("בעיית אבטחה (SSL). בדוק את הגדרות נטפרי.")
            if "expired" in low:
                raise _FatalError(
                    "מפתח ה-API פג תוקף. צור מפתח חדש ב-aistudio.google.com/apikey "
                    "והזן אותו בהגדרות.")
            if ("API key" in err or "API_KEY_INVALID" in err
                    or "403" in err or "401" in err):
                raise _FatalError("מפתח API לא תקין.")
            # מודל לא זמין/הוסר ע"י Google (מודלי preview משתנים) - כשל חינני
            if ("not_found" in low or "not found" in low or "404" in err
                    or "does not exist" in low or "is not supported" in low
                    or "was not found" in low):
                mode = "התרגום" if self.capture_mode == "system" else "השיחה"
                raise _FatalError(
                    f"מודל {mode} אינו זמין כרגע - ייתכן ש-Google עדכנה אותו. "
                    "בדוק אם יש גרסה חדשה של האפליקציה (עזרה → בדוק עדכונים).")
            # שאר השגיאות (חיבור נפל) - נזרקות כדי שהעטיפה תתחבר מחדש
            raise

    # ------------------------------------------------------------------ #
    # זרמי אודיו (sounddevice)
    # ------------------------------------------------------------------ #
    def _open_audio_streams(self):
        """פותח את זרמי הקלט (מיקרופון או קול-מערכת) והרמקול."""

        if self.capture_mode == "system":
            # מצב תרגום וידאו - לוכדים את קול המערכת (loopback) במקום מיקרופון
            self._start_loopback_capture()
        else:
            # --- מיקרופון: callback דוחף bytes לתור ---
            def mic_callback(indata, frames, time_info, status):
                if self._running:
                    self._mic_queue.put(bytes(indata))

            self._in_stream = sd.RawInputStream(
                samplerate=SEND_RATE,
                channels=CHANNELS,
                dtype=FORMAT,
                blocksize=BLOCK,
                device=self.input_device,   # None = ברירת מחדל מערכת
                callback=mic_callback,
            )
            self._in_stream.start()

        # --- רמקול: callback מושך bytes מהתור ---
        def speaker_callback(outdata, frames, time_info, status):
            need = len(outdata)
            buf = bytearray()
            # אוסף מספיק bytes מהתור כדי למלא את הבלוק
            while len(buf) < need:
                try:
                    buf.extend(self._play_queue.get_nowait())
                except queue.Empty:
                    break
            if len(buf) > 0:
                # הושמע אודיו ממשי - מסמנים זמן (לדיכוי הד)
                self._last_output_time = time.monotonic()
            if len(buf) < need:
                # אין מספיק אודיו - ממלא בשקט
                buf.extend(b"\x00" * (need - len(buf)))
                outdata[:] = bytes(buf[:need])
            else:
                # יש עודף - מחזיר אותו לראש התור
                outdata[:] = bytes(buf[:need])
                leftover = bytes(buf[need:])
                if leftover:
                    # מחזיר את העודף לתחילת התור
                    self._play_queue.queue.appendleft(leftover)

        self._out_stream = sd.RawOutputStream(
            samplerate=RECV_RATE,
            channels=CHANNELS,
            dtype=FORMAT,
            blocksize=BLOCK,
            device=self.output_device,   # None = ברירת מחדל מערכת
            callback=speaker_callback,
        )
        self._out_stream.start()

    _BROWSERS = ("chrome", "msedge", "firefox", "brave", "opera", "vivaldi")

    @classmethod
    def _find_browser_pid(cls):
        """
        מחזיר את ה-PID של תהליך הדפדפן ש*מנגן אודיו כרגע*.
        עדיפות: session אודיו פעיל ששייך לדפדפן (זה התהליך שבאמת מייצר
        קול - לרוב תהליך-בן). כך proc-tap לוכד בדיוק את מקור הקול.
        """
        # 1) דרך pycaw - התהליך עם session אודיו של דפדפן.
        #    מעדיפים session *פעיל* (State==1) - זה שמנגן כרגע - על פני
        #    לשונית שקטה/שפג תוקפה, אחרת עלולים ללכוד תהליך שלא מייצר קול.
        try:
            from pycaw.pycaw import AudioUtilities
            active_pid = None
            any_pid = None
            for s in AudioUtilities.GetAllSessions():
                if not s.Process:
                    continue
                try:
                    nm = (s.Process.name() or "").lower().replace(".exe", "")
                    pid = s.Process.pid
                    state = s.State
                except Exception:
                    continue
                if "webview" in nm or not any(b in nm for b in cls._BROWSERS):
                    continue
                if any_pid is None:
                    any_pid = pid
                if state == 1 and active_pid is None:   # AudioSessionStateActive
                    active_pid = pid
            if active_pid is not None:
                return active_pid
            if any_pid is not None:
                return any_pid
        except Exception:
            pass
        # 2) fallback - תהליך הדפדפן הראשי לפי psutil
        try:
            import psutil
        except Exception:
            return None
        REAL = tuple(b + ".exe" for b in cls._BROWSERS)
        procs = []
        for p in psutil.process_iter(["pid", "name", "ppid"]):
            nm = (p.info.get("name") or "").lower()
            if nm in REAL:
                procs.append(p.info)
        if not procs:
            return None
        from collections import Counter
        best_name = Counter(p["name"].lower() for p in procs).most_common(1)[0][0]
        family = [p for p in procs if p["name"].lower() == best_name]
        pids = {p["pid"] for p in family}
        roots = [p for p in family if p["ppid"] not in pids] or family
        return roots[0]["pid"]

    def _on_browser_audio(self, pcm: bytes, frames=None):
        """callback מ-proc-tap: ממיר 48k stereo float32 -> 16k mono int16."""
        if not self._running or not pcm:
            return
        try:
            ch = max(1, self._browser_channels)
            arr = np.frombuffer(pcm, dtype=np.float32)
            if arr.size == 0:
                return
            # stereo -> mono (חיתוך שארית כדי ש-reshape לא יקרוס על פריים חלקי)
            if ch >= 2:
                n = (arr.size // ch) * ch
                if not n:
                    return
                arr = arr[:n].reshape(-1, ch).mean(axis=1)
            # דגימה-מחדש 48000 -> 16000 (ממוצע כל 3 דגימות, אנטי-aliasing גס)
            if self._browser_rate == 48000:
                n = (arr.size // 3) * 3
                if n:
                    arr = arr[:n].reshape(-1, 3).mean(axis=1)
            elif self._browser_rate != SEND_RATE:
                ratio = self._browser_rate / SEND_RATE
                idx = (np.arange(int(arr.size / ratio)) * ratio).astype(np.int64)
                arr = arr[idx] if idx.size else arr[:0]
            pcm16 = (np.clip(arr, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        except Exception:
            return   # פריים פגום - מדלגים בלי להפיל את ה-thread של proc-tap
        if pcm16:
            self._last_browser_audio = time.monotonic()
            self._mic_queue.put(pcm16)

    def _attach_proctap(self, pid):
        """יוצר ומפעיל לכידת proc-tap על PID נתון. מחזיר True בהצלחה."""
        import proctap
        cap = proctap.ProcessAudioCapture(pid=pid,
                                          on_data=self._on_browser_audio)
        fmt = cap.get_format()
        self._browser_rate = int(fmt.get("sample_rate", 48000))
        self._browser_channels = int(fmt.get("channels", 2))
        cap.start()
        self._proctap = cap
        self._browser_pid = pid
        self._browser_capture = True
        self._last_browser_audio = time.monotonic()
        return True

    def _browser_watchdog(self):
        """
        מנטר את לכידת הדפדפן ומתאושש אם היא נעצרה בשקט: אם תהליך-האודיו
        מת (Chrome אתחל את שירות האודיו / נסגרה לשונית), או שהאודיו נעצר
        זמן רב ויש תהליך-דפדפן אחר שמנגן - מתחבר מחדש ל-PID הנכון.
        ריצה בזמן שהסרטון מושהה (pid חי, אין אודיו) לא גורמת לחיבור-מחדש.
        """
        try:
            import psutil
        except Exception:
            return
        while self._running and self._browser_capture:
            time.sleep(2.0)
            if not (self._running and self._browser_capture):
                break
            try:
                pid_alive = self._browser_pid and psutil.pid_exists(self._browser_pid)
                stalled = (time.monotonic() - self._last_browser_audio) > 4.0
                need_pid = None
                if not pid_alive:
                    need_pid = self._find_browser_pid()      # התהליך מת
                elif stalled:
                    cur = self._find_browser_pid()
                    if cur and cur != self._browser_pid:     # האודיו עבר לתהליך אחר
                        need_pid = cur
                if need_pid:
                    try:
                        if self._proctap:
                            self._proctap.stop(); self._proctap.close()
                    except Exception:
                        pass
                    self._proctap = None
                    self._attach_proctap(need_pid)
            except Exception:
                pass  # watchdog לא אמור להפיל את המנוע

    def _start_loopback_capture(self):
        """
        לוכד את האודיו של *הדפדפן בלבד* (ברמת תהליך, proc-tap) ודוחף
        ל-_mic_queue. כך Gemini לא שומע את התרגום של עצמו - אין לולאת
        משוב, ואפשר לתרגם בו-זמנית בלי לעצור את הסרטון.
        אם אין דפדפן/נכשל - נופלים חזרה ללכידת קול-המערכת (soundcard).
        """
        if self._loopback_thread and self._loopback_thread.is_alive():
            return
        if self._proctap is not None:
            return

        # ניסיון ראשי: לכידת הדפדפן בלבד (proc-tap)
        try:
            pid = self._find_browser_pid()
            if pid is None:
                raise RuntimeError("no-browser")
            self._attach_proctap(pid)
            # watchdog להתאוששות אוטומטית
            self._watchdog_thread = threading.Thread(
                target=self._browser_watchdog, daemon=True)
            self._watchdog_thread.start()
            return
        except Exception as e:
            self._browser_capture = False
            if str(e) == "no-browser":
                self.on_error(
                    "לא נמצא דפדפן פתוח. פתח את הסרטון בדפדפן "
                    "(Chrome/Edge/Firefox) ונסה שוב. בינתיים אתרגם את כל קול המערכת.")
            else:
                self.on_error(f"לכידת דפדפן נכשלה ({e}); עובר לקול-מערכת.")
            # נפילה ללכידת קול-מערכת רגילה (soundcard)

        def loopback_loop():
            try:
                import soundcard as sc
            except Exception as e:
                self.on_error(f"לכידת קול המערכת נכשלה: {e}")
                return
            while self._running:
                try:
                    spk = sc.default_speaker()
                    mic = sc.get_microphone(spk.name, include_loopback=True)
                    with mic.recorder(samplerate=SEND_RATE, channels=CHANNELS,
                                      blocksize=BLOCK) as rec:
                        while self._running:
                            frames = rec.record(numframes=BLOCK)
                            if frames.ndim > 1:
                                frames = frames[:, 0]
                            pcm = (np.clip(frames, -1.0, 1.0) * 32767).astype(
                                np.int16).tobytes()
                            if self._running:
                                self._mic_queue.put(pcm)
                except Exception:
                    if not self._running:
                        break
                    time.sleep(0.3)

        self._loopback_thread = threading.Thread(
            target=loopback_loop, daemon=True)
        self._loopback_thread.start()

    def _cleanup_audio(self):
        """סוגר את זרמי האודיו."""
        for stream in (self._in_stream, self._out_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self._in_stream = None
        self._out_stream = None
        # סגירת לכידת הדפדפן (proc-tap)
        if self._proctap is not None:
            try:
                self._proctap.stop()
                self._proctap.close()
            except Exception:
                pass
            self._proctap = None
        self._browser_capture = False
        self._browser_pid = None

    def _clear_playback(self):
        """מרוקן את תור ההשמעה - לשימוש בעת הפרעה (barge-in)."""
        try:
            while True:
                self._play_queue.get_nowait()
        except queue.Empty:
            pass

    # ------------------------------------------------------------------ #
    # משימות asyncio
    # ------------------------------------------------------------------ #
    async def _send_mic(self, session):
        """קורא bytes מתור המיקרופון ושולח ל-Gemini ברצף."""
        loop = asyncio.get_event_loop()
        while self._running:
            # קריאה מהתור בלי לחסום את ה-event loop
            try:
                data = await loop.run_in_executor(
                    None, self._mic_queue.get, True, 0.1
                )
            except queue.Empty:
                continue

            # אם מושתק - מרוקנים את התור אך לא שולחים ל-Gemini
            if self.mic_muted:
                self.on_level(0.0)
                continue

            # מצב תרגום וידאו - מודל התרגום הייעודי מתרגם זרם רציף בעצמו,
            # אז פשוט מזרימים את האודיו ברצף.
            if self.capture_mode == "system":
                # בלכידת דפדפן אין משוב (לא לוכדים את הקול שלנו). אבל בנתיב
                # הגיבוי (קול-מערכת) כן - אז חוסמים שליחה בזמן ש-Gemini מדבר,
                # אחרת המודל ישמע את העברית של עצמו ויהדהד אותה בלולאה.
                if not self._browser_capture and \
                        (time.monotonic() - self._last_output_time) < 0.5:
                    self.on_level(0.0)
                    continue
                # השגת-קצב: אם נוצר פיגור (התור נערם), משמיטים אודיו ישן
                # ושולחים רק את העדכני - כך התרגום נשאר חי ולא מפגר יותר ויותר.
                if self._mic_queue.qsize() > 12:   # ~1.2s פיגור
                    dropped = b""
                    try:
                        while self._mic_queue.qsize() > 3:
                            dropped = self._mic_queue.get_nowait()
                    except queue.Empty:
                        pass
                    if dropped:
                        data = dropped
                self.on_level(self._rms_level(data))
                try:
                    await session.send_realtime_input(
                        audio=types.Blob(data=data,
                                         mime_type="audio/pcm;rate=16000"))
                except Exception:
                    if self._running:
                        raise
                    break
                continue

            # דיכוי הד חכם - בזמן ש-Gemini מדבר חוסמים את ההד החלש,
            # אבל מאפשרים לקול חזק לעבור (התפרצות / barge-in).
            # כשמזוהה קול רם, נפתח חלון קצר שבו המיקרופון עובר,
            # כך ש-Gemini "שומע" את ההפרעה ומפסיק לדבר.
            if self.echo_suppression and \
                    (time.monotonic() - self._last_output_time) < 0.2:
                lvl = self._rms_level(data)
                if lvl >= BARGE_IN_LEVEL:
                    # קול רם = ניסיון התפרצות, פותחים חלון
                    self._barge_in_until = time.monotonic() + 1.2
                if time.monotonic() >= self._barge_in_until:
                    # אין התפרצות פעילה - חוסמים את ההד
                    self.on_level(0.0)
                    continue
                # אחרת - נותנים לקול לעבור (המשך ההתפרצות)

            # עוצמת קול המשתמש - לאנימציה
            self.on_level(self._rms_level(data))

            # הקלטה - קול המשתמש (16kHz)
            if self.recording:
                self._mix_into_recording(data, SEND_RATE)

            try:
                await session.send_realtime_input(
                    audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                )
            except Exception:
                if self._running:
                    raise
                break

    async def _send_video(self, session):
        """
        שולח את פריים הווידאו האחרון ל-Gemini בקצב של פריים לשנייה.
        אם אין פריים (וידאו כבוי) - פשוט ממתין.
        """
        while self._running:
            await asyncio.sleep(1.0)   # ~1fps - מספיק ל-Gemini, חוסך רוחב פס
            frame = self._video_frame
            if frame is None:
                continue
            try:
                await session.send_realtime_input(
                    video=types.Blob(data=frame, mime_type="image/jpeg")
                )
            except Exception:
                if self._running:
                    raise
                break

    async def _receive(self, session):
        """מקבל אודיו ותמלול מ-Gemini ומנתב להשמעה / לתצוגה."""
        while self._running:
            turn = session.receive()
            async for response in turn:
                if not self._running:
                    return

                # קריאה לפונקציה (שליטה במחשב)
                if getattr(response, "tool_call", None):
                    await self._handle_tool_call(session, response.tool_call)
                    continue

                # אודיו - לתור ההשמעה
                if response.data is not None:
                    self.on_status("speaking")
                    self._play_queue.put(response.data)
                    # עוצמת קול Gemini - לאנימציה
                    self.on_level(self._rms_level(response.data))
                    # הקלטה - קול Gemini (24kHz)
                    if self.recording:
                        self._mix_into_recording(response.data, RECV_RATE)

                sc = response.server_content
                if sc is None:
                    continue

                # תמלול דברי המשתמש
                if sc.input_transcription and sc.input_transcription.text:
                    self.on_user_text(sc.input_transcription.text)

                # תמלול דברי Gemini
                if sc.output_transcription and sc.output_transcription.text:
                    self.on_bot_text(sc.output_transcription.text)

                # הפרעה - המשתמש דיבר בזמן ש-Gemini דיבר
                if sc.interrupted:
                    self._clear_playback()
                    self.on_status("listening")

                # סוף תור - חזרה להאזנה
                if sc.turn_complete:
                    self.on_status("listening")

    async def _handle_tool_call(self, session, tool_call):
        """מבצע קריאות פונקציה של Gemini (שליטה במחשב) ומחזיר תוצאה."""
        import computer_tools
        responses = []
        for fc in tool_call.function_calls:
            args = dict(fc.args) if fc.args else {}
            self.on_bot_text(f"[מבצע: {fc.name}] ")
            result = computer_tools.execute(fc.name, args)
            responses.append(types.FunctionResponse(
                id=fc.id, name=fc.name, response={"result": result}))
        try:
            await session.send_tool_response(function_responses=responses)
        except Exception:
            pass


# בדיקה עצמאית מהטרמינל
if __name__ == "__main__":
    import os
    import sys
    import time
    sys.stdout.reconfigure(encoding="utf-8")

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("הגדר GEMINI_API_KEY")
        sys.exit(1)

    print("=" * 60)
    print("בדיקת מנוע קולי - דבר למיקרופון! (Ctrl+C ליציאה)")
    print("=" * 60)

    engine = VoiceEngine(
        api_key=key,
        on_status=lambda s: print(f"[סטטוס] {s}"),
        on_user_text=lambda t: print(f"אתה: {t}", end="", flush=True),
        on_bot_text=lambda t: print(f"\rGemini: {t}", end="", flush=True),
        on_error=lambda e: print(f"\n[שגיאה] {e}"),
    )
    engine.start()
    try:
        while engine.is_running():
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nמסיים...")
        engine.stop()
        time.sleep(1)
