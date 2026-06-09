#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wakeword.py
-----------
האזנה למילת הפעלה ("Jarvis", "Computer"...) באמצעות Porcupine.
כשהמילה מזוהה - מפעיל callback (בד"כ התחלת שיחה).

דורש מפתח גישה חינמי מ-Picovoice (console.picovoice.ai).
מילים מובנות לא דורשות אימון. למילה מותאמת ("היי ג'מיני") צריך
לאמן ב-Picovoice ולספק קובץ .ppn.
"""

import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

# מילות הפעלה מובנות (לא דורשות אימון)
BUILTIN_KEYWORDS = [
    "jarvis", "computer", "alexa", "hey google",
    "picovoice", "bumblebee", "terminator",
]


class WakeWordListener:
    """
    מאזין למילת הפעלה ברקע. רץ ב-thread נפרד.
    on_detected נקרא כשהמילה זוהתה.
    """

    def __init__(self, access_key: str, keyword: str,
                 input_device: int | None = None,
                 on_detected: Optional[Callable[[], None]] = None,
                 on_error: Optional[Callable[[str], None]] = None):
        self.access_key = access_key
        self.keyword = keyword
        self.input_device = input_device
        self.on_detected = on_detected or (lambda: None)
        self.on_error = on_error or (lambda e: None)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._porcupine = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def _run(self):
        import pvporcupine
        try:
            self._porcupine = pvporcupine.create(
                access_key=self.access_key,
                keywords=[self.keyword],
            )
        except Exception as e:
            self.on_error(f"מילת הפעלה: {e}")
            self._running = False
            return

        frame_len = self._porcupine.frame_length     # 512
        rate = self._porcupine.sample_rate            # 16000

        try:
            with sd.RawInputStream(
                samplerate=rate, channels=1, dtype="int16",
                blocksize=frame_len, device=self.input_device,
            ) as stream:
                while self._running:
                    data, _ = stream.read(frame_len)
                    pcm = np.frombuffer(data, dtype=np.int16)
                    if len(pcm) < frame_len:
                        continue
                    if self._porcupine.process(pcm) >= 0:
                        self.on_detected()
        except Exception as e:
            if self._running:
                self.on_error(f"מילת הפעלה: {e}")
        finally:
            try:
                if self._porcupine:
                    self._porcupine.delete()
            except Exception:
                pass
            self._porcupine = None
            self._running = False
