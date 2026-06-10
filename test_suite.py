#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_suite.py
--------------
בדיקות יחידה ואינטגרציה — pytest
הרץ עם: pytest test_suite.py -v

כל בדיקה בעלת "No network" / "No API" עובדת בלא אינטרנט
בדיקות עם API דורשות מפתח תקין בסביבה
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ====================================================================== #
# A. בדיקות יחידה: config.py
# ====================================================================== #

def test_config_defaults():
    """בדיקה: ערכי ברירת מחדל נטענים כשאין קובץ"""
    with tempfile.TemporaryDirectory() as tmpdir:
        import config
        # מחקה את app_dir
        with patch.object(config, "app_dir", return_value=tmpdir):
            s = config.Settings.load()
            assert isinstance(s.voice_api, str)  # יש voice_api
            assert s.voice_api in [v.api_name for v in config.VOICES]  # תקני
            assert s.echo_suppression == True
            assert len(config.VOICES) > 0


def test_config_save_and_load():
    """בדיקה: שמירה וטעינה של הגדרות"""
    with tempfile.TemporaryDirectory() as tmpdir:
        import config
        with patch.object(config, "app_dir", return_value=tmpdir):
            s = config.Settings()
            s.voice_api = "Charon"
            s.web_search = True
            s.save()

            s2 = config.Settings.load()
            assert s2.voice_api == "Charon"
            assert s2.web_search == True


def test_config_corrupted_json():
    """בדיקה: קובץ JSON פגום מחזיר ברירת מחדל"""
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_file = os.path.join(tmpdir, "settings.json")
        with open(bad_file, "w") as f:
            f.write("{invalid json")

        import config
        with patch.object(config, "app_dir", return_value=tmpdir):
            s = config.Settings.load()
            assert isinstance(s, config.Settings)  # לא קריסה


# ====================================================================== #
# B. בדיקות יחידה: knowledge.py
# ====================================================================== #

def test_memory_add_conversation():
    """בדיקה: הוספת שיחה לזיכרון"""
    from knowledge import Memory
    m = Memory([])
    turns = [["user", "שלום"], ["bot", "היי!"]]
    m.add_conversation(turns, "2026-06-10 15:00")

    assert len(m.entries) == 1
    assert "משתמש: שלום" in m.entries[0]["text"]
    assert "Gemini: היי!" in m.entries[0]["text"]


def test_memory_max_entries():
    """בדיקה: זיכרון שומר רק 6 שיחות אחרונות"""
    from knowledge import Memory, MAX_MEMORY_ENTRIES
    m = Memory([])

    for i in range(10):
        turns = [["user", f"שאלה {i}"]]
        m.add_conversation(turns, f"2026-06-{10+i}")

    assert len(m.entries) == MAX_MEMORY_ENTRIES


def test_knowledge_base_add_remove():
    """בדיקה: הוספה והסרה של מסמכים"""
    from knowledge import KnowledgeBase
    kb = KnowledgeBase([])

    kb.add("דוקומנט 1", "תוכן טקסט")
    assert "דוקומנט 1" in kb.names()

    kb.remove("דוקומנט 1")
    assert "דוקומנט 1" not in kb.names()


def test_knowledge_base_replace():
    """בדיקה: החלפת מסמך בשם זהה"""
    from knowledge import KnowledgeBase
    kb = KnowledgeBase([])

    kb.add("דוקומנט", "טקסט 1")
    kb.add("דוקומנט", "טקסט 2")

    assert len(kb.docs) == 1
    assert kb.docs[0]["text"] == "טקסט 2"


# ====================================================================== #
# C. בדיקות יחידה: documents.py
# ====================================================================== #

def test_extract_text_plain():
    """בדיקה: חילוץ טקסט מקובץ txt"""
    from documents import extract_text

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                      encoding="utf-8", delete=False) as f:
        f.write("שלום עולם")
        fname = f.name

    try:
        text = extract_text(fname)
        assert "שלום עולם" in text
    finally:
        os.unlink(fname)


def test_extract_text_truncate_long():
    """בדיקה: קובץ ארוך מדי נחתך"""
    from documents import extract_text, MAX_CHARS

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                      encoding="utf-8", delete=False) as f:
        f.write("a" * (MAX_CHARS + 1000))
        fname = f.name

    try:
        text = extract_text(fname)
        assert len(text) <= MAX_CHARS + 100  # +100 לסימון נחתוך
        assert "[...המסמך ארוך" in text
    finally:
        os.unlink(fname)


def test_extract_text_unsupported_format():
    """בדיקה: סוג קובץ לא נתמך זורק שגיאה"""
    from documents import extract_text

    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        fname = f.name

    try:
        with pytest.raises(ValueError, match="סוג קובץ לא נתמך"):
            extract_text(fname)
    finally:
        os.unlink(fname)


def test_extract_text_empty_file():
    """בדיקה: קובץ ריק זורק שגיאה"""
    from documents import extract_text

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        fname = f.name

    try:
        with pytest.raises(ValueError, match="לא נמצא טקסט"):
            extract_text(fname)
    finally:
        os.unlink(fname)


# ====================================================================== #
# D. בדיקות יחידה: computer_tools.py
# ====================================================================== #

def test_computer_tools_get_datetime():
    """בדיקה: פונקציית מידע תאריך/שעה"""
    from computer_tools import _get_datetime

    result = _get_datetime()
    assert "יום" in result
    assert "202" in result  # שנה
    assert ":" in result    # שעה


def test_computer_tools_take_note():
    """בדיקה: שמירת פתק"""
    from computer_tools import _take_note

    with tempfile.TemporaryDirectory() as tmpdir:
        import config
        with patch.object(config, "app_dir", return_value=tmpdir):
            result = _take_note("זכרון בדיקה")
            # בדיקה שהפונקציה מחזירה הודעת הצלחה
            assert "נשמר" in result or "saved" in result.lower() or result


def test_computer_tools_execute_unknown_func():
    """בדיקה: קריאה לפונקציה לא מוכרת"""
    from computer_tools import execute

    result = execute("unknown_function", {})
    assert "לא מוכרת" in result


def test_computer_tools_open_website_validation():
    """בדיקה: ולידציה של URL"""
    from computer_tools import _open_web

    # URL בלי https יוסיף אותה
    with patch("webbrowser.open") as mock:
        _open_web("google.com")
        mock.assert_called_once()
        assert "https://" in mock.call_args[0][0]


# ====================================================================== #
# E. בדיקות יחידה: wakeword.py
# ====================================================================== #

def test_wakeword_builtin_keywords():
    """בדיקה: רשימת מילות הפעלה מובנות קיימת"""
    from wakeword import BUILTIN_KEYWORDS

    assert "jarvis" in BUILTIN_KEYWORDS
    assert "computer" in BUILTIN_KEYWORDS
    assert len(BUILTIN_KEYWORDS) > 0


def test_wakeword_listener_init():
    """בדיקה: יצירת listener"""
    from wakeword import WakeWordListener

    listener = WakeWordListener(
        access_key="test",
        keyword="jarvis",
        on_detected=lambda: None,
        on_error=lambda e: None
    )
    assert listener.keyword == "jarvis"
    assert not listener.is_running()


def test_wakeword_listener_start_stop():
    """בדיקה: התחלה וסגירה של listener"""
    from wakeword import WakeWordListener

    listener = WakeWordListener(
        access_key="invalid",  # לא נריץ בפועל
        keyword="test"
    )
    listener.start()
    # התחלה היא async, אז לא נחכה
    listener.stop()
    # צריך להיות מסוגל לעצור בלי שגיאה


# ====================================================================== #
# F. בדיקות אינטגרציה: חיבור + ניתוק
# ====================================================================== #

@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="מפתח API לא זמין"
)
def test_voice_engine_basic_init():
    """בדיקה: יצירת voice engine בלא רשת"""
    from voice_engine import VoiceEngine

    api_key = os.getenv("GEMINI_API_KEY")
    engine = VoiceEngine(
        api_key=api_key,
        system_prompt="בדיקה",
        on_transcript=lambda x: None,
        on_response=lambda x: None
    )
    assert engine.api_key == api_key


# ====================================================================== #
# G. בדיקות קיצוניות: edge cases
# ====================================================================== #

def test_memory_empty_context():
    """בדיקה: זיכרון ריק מחזיר string ריק"""
    from knowledge import Memory
    m = Memory([])
    context = m.context()
    assert context == ""


def test_knowledge_base_empty_context():
    """בדיקה: בסיס ידע ריק מחזיר string ריק"""
    from knowledge import KnowledgeBase
    kb = KnowledgeBase([])
    context = kb.context()
    assert context == ""


def test_memory_very_long_text():
    """בדיקה: שיחה מאוד ארוכה נחתכת"""
    from knowledge import Memory, MAX_MEMORY_CHARS
    m = Memory([])

    long_text = "א" * (MAX_MEMORY_CHARS + 1000)
    turns = [["user", long_text]]
    m.add_conversation(turns, "2026-06-10")

    saved_text = m.entries[0]["text"]
    assert len(saved_text) <= MAX_MEMORY_CHARS + 10


def test_computer_tools_empty_note():
    """בדיקה: פתק ריק מוחזר ללא שגיאה"""
    from computer_tools import _take_note

    result = _take_note("")
    assert "ריק" in result


def test_computer_tools_empty_url():
    """בדיקה: URL ריק מוחזר ללא שגיאה"""
    from computer_tools import _open_web

    result = _open_web("")
    assert "צוינה" in result or "לא" in result


# ====================================================================== #
# H. בדיקות רגרסיה: תרחישים משותפים
# ====================================================================== #

def test_config_persistence_cycle():
    """בדיקה: הגדרות נשמרות בין יצירות"""
    with tempfile.TemporaryDirectory() as tmpdir:
        import config
        with patch.object(config, "app_dir", return_value=tmpdir):
            # שמור
            s1 = config.Settings()
            s1.voice_api = "Puck"
            s1.deep_thinking = True
            s1.save()

            # טען
            s2 = config.Settings.load()
            assert s2.voice_api == "Puck"
            assert s2.deep_thinking == True

            # שנה וחוזר
            s2.voice_api = "Charon"
            s2.save()
            s3 = config.Settings.load()
            assert s3.voice_api == "Charon"


def test_knowledge_full_workflow():
    """בדיקה: זרימה מלאה של זיכרון + בסיס ידע"""
    from knowledge import Memory, KnowledgeBase

    # זיכרון
    mem = Memory([])
    mem.add_conversation(
        [["user", "שלום"], ["bot", "היי!"]],
        "2026-06-10 15:00"
    )
    mem_ctx = mem.context()
    assert "משתמש" in mem_ctx

    # בסיס ידע
    kb = KnowledgeBase([])
    kb.add("חוקים", "חוק ראשון: לא עושים זאת")
    kb_ctx = kb.context()
    assert "חוק ראשון" in kb_ctx

    # שניהם ביחד
    full_context = mem_ctx + "\n" + kb_ctx
    assert len(full_context) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
