#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
media.py
--------
לכידת וידאו לשליחה ל-Gemini Live: מסך, חלון בודד, או מצלמה.

כל לוכד מספק:
  - list_sources()  : רשימת מקורות זמינים לבחירה ב-UI.
  - grab_jpeg()     : פריים נוכחי כ-JPEG bytes (לשליחה ל-Gemini).
  - grab_qimage()   : פריים נוכחי כ-QImage (לתצוגה מקדימה ב-UI).

הערה על threading:
  אובייקטי mss חייבים לפעול ב-thread שבו נוצרו. לכן הלוכדים מיועדים
  לשימוש מ-thread אחד בלבד (ב-UI, דרך QTimer). ה-UI לוכד פריים, מציג
  אותו כתצוגה מקדימה, ומעביר את ה-JPEG למנוע שישלח ל-Gemini.
"""

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image
from PyQt6.QtGui import QImage


# גודל מקסימלי של פריים שנשלח (לחיסכון ברוחב פס; Gemini לא צריך 4K)
MAX_DIM = 1024
JPEG_QUALITY = 70


@dataclass(frozen=True)
class MediaSource:
    """מקור וידאו לבחירה: מסך, חלון, או מצלמה."""
    kind: str        # "screen" / "window" / "camera"
    id: object       # אינדקס מסך / כותרת חלון / אינדקס מצלמה
    name: str        # שם ידידותי לתצוגה


def _pil_to_jpeg(img: Image.Image) -> bytes:
    """ממיר תמונת PIL ל-JPEG bytes, אחרי הקטנה לגודל סביר."""
    img.thumbnail((MAX_DIM, MAX_DIM))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def _pil_to_qimage(img: Image.Image) -> QImage:
    """ממיר תמונת PIL ל-QImage לתצוגה מקדימה."""
    rgb = img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3,
                  QImage.Format.Format_RGB888)
    return qimg.copy()  # copy כי data זמני


# ====================================================================== #
# לכידת מסך / חלון
# ====================================================================== #
class ScreenCapturer:
    """
    לוכד מסך שלם או חלון ספציפי.

    שימוש:
        sources = ScreenCapturer.list_sources()
        cap = ScreenCapturer(sources[0])
        jpeg = cap.grab_jpeg()
    """

    def __init__(self, source: MediaSource):
        import mss
        self.source = source
        self._sct = mss.mss()

    @staticmethod
    def list_sources() -> list[MediaSource]:
        """מחזיר רשימת מסכים + חלונות פתוחים."""
        sources: list[MediaSource] = []

        # מסכים (monitors[0] = הכל ביחד, נדלג עליו; 1+ = מסכים בודדים)
        try:
            import mss
            with mss.mss() as sct:
                monitors = sct.monitors
            if len(monitors) <= 2:
                sources.append(MediaSource("screen", 1, "המסך שלי"))
            else:
                for i in range(1, len(monitors)):
                    sources.append(MediaSource("screen", i, f"מסך {i}"))
        except Exception:
            pass

        # חלונות פתוחים
        try:
            import pygetwindow as gw
            for w in gw.getAllWindows():
                title = (w.title or "").strip()
                # מסננים חלונות ריקים/זעירים
                if not title or w.width < 100 or w.height < 100:
                    continue
                short = title if len(title) <= 45 else title[:42] + "…"
                sources.append(MediaSource("window", title, f"חלון: {short}"))
        except Exception:
            pass

        return sources

    def _grab_pil(self) -> Image.Image:
        """לוכד את המקור ומחזיר תמונת PIL."""
        if self.source.kind == "window":
            region = self._window_region(self.source.id)
        else:
            region = self._sct.monitors[self.source.id]

        shot = self._sct.grab(region)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def _window_region(self, title: str) -> dict:
        """מחזיר את אזור המסך של חלון לפי כותרתו."""
        import pygetwindow as gw
        wins = gw.getWindowsWithTitle(title)
        if not wins:
            # אם החלון נסגר - נופלים חזרה למסך הראשי
            return self._sct.monitors[1]
        w = wins[0]
        # מוודאים ערכים חוקיים (חלון ממוזער מחזיר ערכים שליליים)
        left, top = max(w.left, 0), max(w.top, 0)
        width, height = max(w.width, 1), max(w.height, 1)
        return {"left": left, "top": top, "width": width, "height": height}

    def grab_jpeg(self) -> bytes:
        return _pil_to_jpeg(self._grab_pil())

    def grab_qimage(self) -> QImage:
        return _pil_to_qimage(self._grab_pil())

    def close(self):
        try:
            self._sct.close()
        except Exception:
            pass


# ====================================================================== #
# לכידת מצלמה
# ====================================================================== #
class CameraCapturer:
    """
    לוכד פריימים ממצלמת רשת.

    שימוש:
        sources = CameraCapturer.list_sources()
        cam = CameraCapturer(sources[0])
        jpeg = cam.grab_jpeg()
        cam.close()
    """

    def __init__(self, source: MediaSource):
        import cv2
        self.source = source
        self._cap = cv2.VideoCapture(int(source.id), cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            raise RuntimeError("לא ניתן לפתוח את המצלמה")

    @staticmethod
    def list_sources(max_check: int = 3) -> list[MediaSource]:
        """בודק אילו מצלמות זמינות (index 0..max_check)."""
        import cv2
        sources: list[MediaSource] = []
        for i in range(max_check):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                ok, _ = cap.read()
                if ok:
                    name = "מצלמה" if i == 0 else f"מצלמה {i + 1}"
                    sources.append(MediaSource("camera", i, name))
                cap.release()
        return sources

    def _grab_pil(self) -> Image.Image | None:
        ok, frame = self._cap.read()
        if not ok:
            return None
        # OpenCV נותן BGR - ממירים ל-RGB
        import cv2
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    def grab_jpeg(self) -> bytes | None:
        img = self._grab_pil()
        return _pil_to_jpeg(img) if img else None

    def grab_qimage(self) -> QImage | None:
        img = self._grab_pil()
        return _pil_to_qimage(img) if img else None

    def close(self):
        try:
            self._cap.release()
        except Exception:
            pass
