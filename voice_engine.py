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
import queue
import threading
import traceback
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

SYSTEM_INSTRUCTION = (
    "אתה עוזר קולי ידידותי שמדבר עברית בצורה טבעית וזורמת. "
    "דבר בקצרה ולעניין, כמו בשיחה אמיתית. "
    "אל תשתמש בסימני פיסוק מיוחדים או אימוג'ים בתשובות."
)

# מספר ניסיונות חיבור-מחדש אוטומטיים לפני ויתור
MAX_RECONNECT = 5


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
        on_status: Optional[Callable[[str], None]] = None,
        on_user_text: Optional[Callable[[str], None]] = None,
        on_bot_text: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.api_key = api_key
        self.voice_name = voice_name          # קול Gemini (Aoede, Kore...)
        self.input_device = input_device      # אינדקס מיקרופון (None=ברירת מחדל)
        self.output_device = output_device    # אינדקס רמקול/אוזניות
        # הנחיית מערכת - אם לא סופקה, ברירת המחדל
        self.system_instruction = system_instruction or SYSTEM_INSTRUCTION
        self.on_status = on_status or (lambda s: None)
        self.on_user_text = on_user_text or (lambda t: None)
        self.on_bot_text = on_bot_text or (lambda t: None)
        self.on_error = on_error or (lambda e: None)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._tasks: list[asyncio.Task] = []
        self._reconnect_attempts = 0

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

    def set_video_frame(self, jpeg: bytes | None):
        """
        מעדכן את פריים הווידאו האחרון שיישלח ל-Gemini.
        נקרא מ-thread ה-UI. None = הפסקת שליחת וידאו.
        """
        self._video_frame = jpeg

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
        """מנהל את החיבור ל-Gemini ואת כל המשימות המקבילות."""
        self.on_status("connecting")
        client = genai.Client(api_key=self.api_key)

        config = {
            "response_modalities": ["AUDIO"],
            "system_instruction": self.system_instruction,
            # בחירת הקול של Gemini
            "speech_config": types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice_name
                    )
                )
            ),
            # תמלול אוטומטי - כדי להציג טקסט בממשק
            "input_audio_transcription": {},
            "output_audio_transcription": {},
        }

        try:
            async with client.aio.live.connect(model=MODEL, config=config) as session:
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
            # שגיאות קטלניות - אין טעם לנסות מחדש
            if "SSL" in err or "certificate" in err.lower():
                raise _FatalError("בעיית אבטחה (SSL). בדוק את הגדרות נטפרי.")
            if ("API key" in err or "API_KEY_INVALID" in err
                    or "403" in err or "401" in err):
                raise _FatalError("מפתח API לא תקין.")
            # שאר השגיאות (חיבור נפל) - נזרקות כדי שהעטיפה תתחבר מחדש
            raise

    # ------------------------------------------------------------------ #
    # זרמי אודיו (sounddevice)
    # ------------------------------------------------------------------ #
    def _open_audio_streams(self):
        """פותח את זרמי המיקרופון והרמקול עם callbacks."""

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
                continue

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

                # אודיו - לתור ההשמעה
                if response.data is not None:
                    self.on_status("speaking")
                    self._play_queue.put(response.data)

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
