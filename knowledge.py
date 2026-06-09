#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
knowledge.py
------------
שני מנגנונים שנותנים ל-Gemini "זיכרון":

1. Memory       - זיכרון בין שיחות. שומר תקצירי שיחות קודמות ומזריק
                  אותן לשיחה חדשה, כך ש-Gemini זוכר על מה דיברתם.
2. KnowledgeBase - בסיס ידע קבוע. אוסף מסמכים ש-Gemini תמיד מכיר
                  (לא רק מסמך אחד לשיחה).

הכל נשמר מקומית בקבצי JSON ליד האפליקציה.
"""

import json
import os

import config

MEMORY_FILE = os.path.join(config.app_dir(), "memory.json")
KNOWLEDGE_FILE = os.path.join(config.app_dir(), "knowledge.json")

# מגבלות תווים - כדי לא לחרוג מחלון ההקשר של Gemini
MAX_MEMORY_ENTRIES = 6       # כמה שיחות אחרונות לזכור
MAX_MEMORY_CHARS = 2500      # תווים לכל שיחה בזיכרון
MAX_KB_CHARS = 40000         # סך התווים מבסיס הידע


# ====================================================================== #
# זיכרון בין שיחות
# ====================================================================== #
class Memory:
    def __init__(self, entries: list[dict]):
        self.entries = entries   # [{time, text}]

    @classmethod
    def load(cls) -> "Memory":
        try:
            with open(MEMORY_FILE, encoding="utf-8") as f:
                return cls(json.load(f))
        except Exception:
            return cls([])

    def save(self):
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.entries[-MAX_MEMORY_ENTRIES:], f,
                          ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_conversation(self, turns: list[list[str]], timestamp: str):
        """שומר שיחה (רשימת [דובר, טקסט]) כרשומת זיכרון מקוצרת."""
        labels = {"user": "משתמש", "bot": "Gemini"}
        lines = []
        for speaker, text in turns:
            if speaker in labels:
                lines.append(f"{labels[speaker]}: {text}")
        text = "\n".join(lines).strip()
        if not text:
            return
        if len(text) > MAX_MEMORY_CHARS:
            text = text[:MAX_MEMORY_CHARS] + "…"
        self.entries.append({"time": timestamp, "text": text})
        self.entries = self.entries[-MAX_MEMORY_ENTRIES:]
        self.save()

    def clear(self):
        self.entries = []
        self.save()

    def context(self) -> str:
        """מחזיר טקסט הקשר להזרקה ל-Gemini, או מחרוזת ריקה."""
        if not self.entries:
            return ""
        parts = ["סיכום שיחות קודמות שלך עם המשתמש (לזיכרון והמשכיות):"]
        for e in self.entries:
            parts.append(f"\n[{e.get('time', '')}]\n{e.get('text', '')}")
        return "\n".join(parts)


# ====================================================================== #
# בסיס ידע קבוע
# ====================================================================== #
class KnowledgeBase:
    def __init__(self, docs: list[dict]):
        self.docs = docs   # [{name, text}]

    @classmethod
    def load(cls) -> "KnowledgeBase":
        try:
            with open(KNOWLEDGE_FILE, encoding="utf-8") as f:
                return cls(json.load(f))
        except Exception:
            return cls([])

    def save(self):
        try:
            with open(KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.docs, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add(self, name: str, text: str):
        # מחליפים אם כבר קיים בשם זהה
        self.docs = [d for d in self.docs if d.get("name") != name]
        self.docs.append({"name": name, "text": text})
        self.save()

    def remove(self, name: str):
        self.docs = [d for d in self.docs if d.get("name") != name]
        self.save()

    def names(self) -> list[str]:
        return [d.get("name", "") for d in self.docs]

    def context(self) -> str:
        """מחזיר את תוכן בסיס הידע להזרקה, חתוך למגבלה."""
        if not self.docs:
            return ""
        parts = ["מסמכי ידע קבועים שאתה מכיר (ענה על שאלות לפיהם):"]
        total = 0
        for d in self.docs:
            chunk = f"\n--- {d.get('name', '')} ---\n{d.get('text', '')}"
            if total + len(chunk) > MAX_KB_CHARS:
                chunk = chunk[:MAX_KB_CHARS - total] + "…"
            parts.append(chunk)
            total += len(chunk)
            if total >= MAX_KB_CHARS:
                break
        return "\n".join(parts)
