#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config.py
---------
הגדרות האפליקציה: קטלוג קולות, רשימת התקני אודיו, וטעינה/שמירה של בחירות.

מרכז כאן את כל מה שהמשתמש יכול להתאים, כדי שהמנוע והממשק יישארו נקיים.
"""

import json
import os
import sys
from dataclasses import dataclass

import sounddevice as sd


# ---------------------------------------------------------------------- #
# תיקיית הבסיס - חשוב לעבודה תקינה גם כקובץ .exe (PyInstaller)
# ---------------------------------------------------------------------- #
def app_dir() -> str:
    """
    מחזיר את התיקייה שבה נמצאים קבצי המשתמש (api_key.txt, settings.json).
    כ-.exe: התיקייה של הקובץ עצמו. כקוד רגיל: תיקיית הסקריפט.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------- #
# קטלוג קולות - שם תצוגה בעברית → שם הקול ב-API של Gemini
# ---------------------------------------------------------------------- #
@dataclass(frozen=True)
class Voice:
    hebrew_name: str    # שם שמוצג למשתמש
    api_name: str       # שם הקול שנשלח ל-Gemini
    description: str    # תיאור קצר של אופי הקול
    gender: str         # "f" / "m"


# רשימה מובחרת של קולות. כולם נבדקו ועובדים עם עברית.
VOICES: list[Voice] = [
    # קולות נשיים
    Voice("נועה",   "Aoede",   "קלילה ונעימה",   "f"),
    Voice("מאיה",   "Kore",    "ברורה ותקיפה",   "f"),
    Voice("יעל",    "Leda",    "צעירה ורעננה",   "f"),
    Voice("תמר",    "Sulafat", "חמה ונינוחה",    "f"),
    Voice("ליאת",   "Achernar","רכה ועדינה",     "f"),
    # קולות גבריים
    Voice("איתי",   "Puck",    "אנרגטי ושמח",    "m"),
    Voice("דניאל",  "Charon",  "ענייני ורגוע",   "m"),
    Voice("אורי",   "Orus",    "תקיף ובטוח",     "m"),
    Voice("יונתן",  "Algieba", "חלק ונעים",      "m"),
    Voice("נועם",   "Achird",  "ידידותי וחביב",  "m"),
]

DEFAULT_VOICE_API = "Aoede"   # ברירת מחדל - נועה


def get_voice_by_api(api_name: str) -> Voice:
    """מחזיר אובייקט קול לפי שם ה-API, או ברירת המחדל."""
    for v in VOICES:
        if v.api_name == api_name:
            return v
    return VOICES[0]


# ---------------------------------------------------------------------- #
# תבניות הנחיית מערכת - אישיויות מוכנות שאפשר לבחור ולערוך
# ---------------------------------------------------------------------- #
@dataclass(frozen=True)
class Persona:
    name: str           # שם התבנית
    instruction: str    # הנחיית המערכת בפועל


PERSONAS: list[Persona] = [
    Persona(
        "עוזר כללי",
        "אתה עוזר קולי ידידותי שמדבר עברית בצורה טבעית וזורמת. "
        "דבר בקצרה ולעניין, כמו בשיחה אמיתית. "
        "אל תשתמש בסימני פיסוק מיוחדים או אימוג'ים בתשובות.",
    ),
    Persona(
        "מורה פרטי",
        "אתה מורה פרטי סבלני שמדבר עברית. הסבר נושאים בצורה ברורה "
        "ומדורגת, תן דוגמאות, ושאל שאלות כדי לוודא שהבנתי. עודד אותי.",
    ),
    Persona(
        "מתרגם",
        "אתה מתרגם מקצועי. כשאני אומר משפט, תרגם אותו לשפה שאבקש "
        "ואמור את התרגום בקול. אם לא ציינתי שפה, תרגם בין עברית לאנגלית.",
    ),
    Persona(
        "בן שיח לתרגול אנגלית",
        "You are a friendly English conversation partner. Speak in simple, "
        "clear English. Gently correct my mistakes and keep the conversation "
        "going with follow-up questions. Be encouraging.",
    ),
    Persona(
        "יועץ ענייני",
        "אתה יועץ חכם וישיר שמדבר עברית. תן תשובות מעשיות וממוקדות, "
        "ללא מלל מיותר. אם חסר לך מידע, שאל שאלה ממוקדת אחת.",
    ),
]

DEFAULT_INSTRUCTION = PERSONAS[0].instruction


# ---------------------------------------------------------------------- #
# ערכות צבעים (Material themes של qt-material)
# ---------------------------------------------------------------------- #
@dataclass(frozen=True)
class Theme:
    hebrew_name: str    # שם בעברית
    xml: str            # שם קובץ הערכה של qt-material
    accent: str         # צבע הדגשה (hex) לרכיבים המותאמים אישית


# כל הערכות כהות - מתאימות לכרטיסים הכהים של הממשק.
# כל ערכה מגדירה צבע הדגשה שונה לכפתורים, סטטוס ושמות בתמלול.
THEMES: list[Theme] = [
    Theme("ציאן",   "dark_cyan.xml",       "#26c6da"),
    Theme("סגול",   "dark_purple.xml",     "#b388ff"),
    Theme("טורקיז", "dark_teal.xml",       "#1de9b6"),
    Theme("ורוד",   "dark_pink.xml",       "#ff80ab"),
    Theme("כתום",   "dark_amber.xml",      "#ffd54f"),
    Theme("ירוק",   "dark_lightgreen.xml", "#b9f6ca"),
]

DEFAULT_THEME = "dark_cyan.xml"


def get_theme_by_xml(xml: str) -> Theme:
    for t in THEMES:
        if t.xml == xml:
            return t
    return THEMES[0]


# ---------------------------------------------------------------------- #
# התקני אודיו - רשימה נקייה לבחירת מיקרופון/רמקול/אוזניות
# ---------------------------------------------------------------------- #
@dataclass(frozen=True)
class AudioDevice:
    index: int | None   # אינדקס ב-sounddevice, או None = ברירת מחדל מערכת
    name: str           # שם ידידותי לתצוגה


# ערך מיוחד שמשמעו "ברירת המחדל של Windows" (עוקב אחרי אוזניות מחוברות)
SYSTEM_DEFAULT = AudioDevice(None, "ברירת מחדל של Windows")


def _clean_devices(want_input: bool) -> list[AudioDevice]:
    """
    מחזיר רשימת התקנים נקייה (בלי כפילויות מבלבלות).
    מסנן ל-host API אחד (MME) שנותן שמות ידידותיים ותואם את
    ברירות המחדל של Windows.
    """
    result: list[AudioDevice] = [SYSTEM_DEFAULT]
    seen_names: set[str] = set()
    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception:
        return result

    for i, d in enumerate(devices):
        # רק MME - השמות הכי נקיים ותואמי-Windows
        if hostapis[d["hostapi"]]["name"] != "MME":
            continue
        channels = d["max_input_channels"] if want_input else d["max_output_channels"]
        if channels <= 0:
            continue
        name = d["name"].strip()
        # מדלגים על ה"Sound Mapper" (זה הנתב, לא התקן ממשי)
        if "Sound Mapper" in name:
            continue
        if name in seen_names:
            continue
        seen_names.add(name)
        result.append(AudioDevice(i, name))
    return result


def list_input_devices() -> list[AudioDevice]:
    """רשימת מיקרופונים זמינים."""
    return _clean_devices(want_input=True)


def list_output_devices() -> list[AudioDevice]:
    """רשימת רמקולים/אוזניות זמינים."""
    return _clean_devices(want_input=False)


# ---------------------------------------------------------------------- #
# שמירה/טעינה של הגדרות המשתמש
# ---------------------------------------------------------------------- #
SETTINGS_FILE = os.path.join(app_dir(), "settings.json")


@dataclass
class Settings:
    voice_api: str = DEFAULT_VOICE_API
    input_device: int | None = None    # None = ברירת מחדל
    output_device: int | None = None
    system_instruction: str = DEFAULT_INSTRUCTION
    theme: str = DEFAULT_THEME

    def save(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "voice_api": self.voice_api,
                    "input_device": self.input_device,
                    "output_device": self.output_device,
                    "system_instruction": self.system_instruction,
                    "theme": self.theme,
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # שמירה היא נחמדה-אם-אפשר, לא קריטית

    @classmethod
    def load(cls) -> "Settings":
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return cls(
                voice_api=data.get("voice_api", DEFAULT_VOICE_API),
                input_device=data.get("input_device"),
                output_device=data.get("output_device"),
                system_instruction=data.get("system_instruction", DEFAULT_INSTRUCTION),
                theme=data.get("theme", DEFAULT_THEME),
            )
        except Exception:
            return cls()  # ברירות מחדל אם אין קובץ / שגיאה
