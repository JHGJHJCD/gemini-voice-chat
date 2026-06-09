#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
computer_tools.py
-----------------
פונקציות בטוחות ש-Gemini יכול להפעיל בקול (function calling):
פתיחת תוכנות, אתרים, מידע מערכת, ורישום פתקים.

מוגבל בכוונה לפעולות שאינן הרסניות - אין מחיקה, שינוי מערכת או הרצת קוד שרירותי.
"""

import os
import subprocess
import webbrowser
from datetime import datetime

import config


# הצהרות הפונקציות עבור Gemini (סכמה)
FUNCTION_DECLARATIONS = [
    {
        "name": "open_application",
        "description": "פותח תוכנה במחשב לפי שם (למשל מחשבון, פנקס רשימות, "
                       "כרום, וורד, אקסל, צייר).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": "שם התוכנה לפתיחה בעברית או אנגלית"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "open_website",
        "description": "פותח אתר אינטרנט בדפדפן ברירת המחדל.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string",
                        "description": "כתובת האתר (למשל youtube.com)"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "get_datetime",
        "description": "מחזיר את התאריך והשעה הנוכחיים.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "take_note",
        "description": "שומר פתק/תזכורת לקובץ פתקים מקומי.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "תוכן הפתק"},
            },
            "required": ["text"],
        },
    },
]

# מיפוי שמות תוכנות נפוצים (עברית/אנגלית) → פקודת הפעלה
APP_MAP = {
    "מחשבון": "calc", "calculator": "calc", "calc": "calc",
    "פנקס רשימות": "notepad", "notepad": "notepad", "פנקס": "notepad",
    "צייר": "mspaint", "paint": "mspaint",
    "כרום": "chrome", "chrome": "chrome", "גוגל כרום": "chrome",
    "אדג": "msedge", "edge": "msedge",
    "וורד": "winword", "word": "winword",
    "אקסל": "excel", "excel": "excel",
    "סייר": "explorer", "explorer": "explorer", "סייר הקבצים": "explorer",
    "הגדרות": "ms-settings:", "settings": "ms-settings:",
}

NOTES_FILE = os.path.join(config.app_dir(), "פתקים.txt")


def execute(name: str, args: dict) -> str:
    """מבצע פונקציה ומחזיר תוצאה טקסטואלית ל-Gemini."""
    try:
        if name == "open_application":
            return _open_app(args.get("name", ""))
        if name == "open_website":
            return _open_web(args.get("url", ""))
        if name == "get_datetime":
            return _get_datetime()
        if name == "take_note":
            return _take_note(args.get("text", ""))
        return f"פונקציה לא מוכרת: {name}"
    except Exception as e:
        return f"שגיאה בביצוע {name}: {e}"


def _open_app(name: str) -> str:
    key = name.strip().lower()
    cmd = APP_MAP.get(name.strip()) or APP_MAP.get(key)
    try:
        if cmd:
            if cmd.startswith("ms-"):
                os.startfile(cmd)
            else:
                subprocess.Popen(cmd, shell=True)
            return f"פתחתי את {name}."
        # ניסיון כללי - אולי זו פקודה תקפה
        subprocess.Popen(name, shell=True)
        return f"ניסיתי לפתוח את {name}."
    except Exception:
        return f"לא הצלחתי לפתוח את {name}."


def _open_web(url: str) -> str:
    url = url.strip()
    if not url:
        return "לא צוינה כתובת."
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"פתחתי את {url}."


def _get_datetime() -> str:
    now = datetime.now()
    days = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    day = days[now.weekday()]
    return f"היום יום {day}, {now.strftime('%d/%m/%Y')}, השעה {now.strftime('%H:%M')}."


def _take_note(text: str) -> str:
    if not text.strip():
        return "הפתק ריק."
    stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
    try:
        with open(NOTES_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {text}\n")
        return "הפתק נשמר."
    except Exception:
        return "לא הצלחתי לשמור את הפתק."
