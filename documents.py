#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
documents.py
------------
חילוץ טקסט ממסמכים (PDF / טקסט) לשליחה ל-Gemini כהקשר.
"""

import os

# מגבלת תווים - כדי לא לחרוג ממכסת ה-context של Gemini
MAX_CHARS = 60000


def extract_text(path: str) -> str:
    """
    מחלץ טקסט מקובץ. תומך ב-PDF ובקבצי טקסט.
    מחזיר את הטקסט (חתוך אם ארוך מדי), או זורק חריגה עם הסבר.
    """
    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        text = _extract_pdf(path)
    elif ext in (".txt", ".md", ".csv", ".log"):
        text = _extract_plain(path)
    else:
        raise ValueError(f"סוג קובץ לא נתמך: {ext}. תמיכה ב-PDF וטקסט.")

    text = text.strip()
    if not text:
        raise ValueError("לא נמצא טקסט בקובץ (ייתכן מסמך סרוק/תמונה).")

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n[...המסמך ארוך, נחתך כאן...]"
    return text


def _extract_pdf(path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts)


def _extract_plain(path: str) -> str:
    # ניסיון בכמה קידודים נפוצים
    for enc in ("utf-8", "utf-8-sig", "windows-1255", "cp1252"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    # נפילה אחרונה - התעלמות משגיאות
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()
