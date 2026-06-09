#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
voice_app.py
------------
אפליקציית מצב קול - שיחה קולית רציפה עם Gemini בעברית.

תכונות:
  - שיחה קולית טבעית (דיבור + תשובה קולית, אפשר להפריע).
  - הנחיית מערכת מותאמת עם תבניות מוכנות לעריכה.
  - שיתוף מסך / חלון או מצלמה - Gemini רואה ומגיב.
  - תצוגה מקדימה של מה ש-Gemini רואה.
  - השתקת מיקרופון, בחירת קול והתקנים, ערכות צבעים.
  - קיצור מקלדת: רווח להתחלה/עצירה.

עיצוב מודרני מבוסס Material Design (qt-material) במצב כהה.

הרצה:
    $env:GEMINI_API_KEY = "..."
    python voice_app.py
"""

import os
import sys
import math
import time

from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QFont, QPixmap, QShortcut, QKeySequence, QIcon,
    QPainter, QColor, QRadialGradient, QPen, QAction,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QPlainTextEdit, QMessageBox, QDialog,
    QComboBox, QFormLayout, QDialogButtonBox, QFrame, QFileDialog, QLineEdit,
    QCheckBox, QSystemTrayIcon, QMenu,
)

from qt_material import apply_stylesheet

from voice_engine import VoiceEngine
from media import ScreenCapturer, CameraCapturer
import config
import knowledge


# ---------------------------------------------------------------------- #
# פלטת צבעים - הרקעים קבועים (כהים), צבע ההדגשה משתנה לפי הערכה הנבחרת
# ---------------------------------------------------------------------- #
def _darken(hex_color: str, factor: float = 0.72) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{int(r*factor):02x}{int(g*factor):02x}{int(b*factor):02x}"


class Palette:
    BG = "#0f1416"
    CARD = "#1a2327"
    CARD_BORDER = "#2a3940"
    TEXT = "#e8eef0"
    TEXT_MUTED = "#7a8a90"
    SUCCESS = "#66bb6a"
    DANGER = "#ef5350"
    WARNING = "#ffa726"
    # נקבעים לפי הערכה ב-apply_accent():
    ACCENT = "#26c6da"
    ACCENT_DARK = "#0095a8"
    USER = "#4dd0e1"
    BOT = "#80cbc4"

    @classmethod
    def apply_accent(cls, accent: str):
        cls.ACCENT = accent
        cls.ACCENT_DARK = _darken(accent)
        cls.USER = accent
        # צבע קבוע ונבדל ל-Gemini כדי שלא יתנגש בצבע ההדגשה
        cls.BOT = "#9fb4bd"


# ---------------------------------------------------------------------- #
# גשר signals - מעביר callbacks מ-thread המנוע ל-thread של ה-GUI
# ---------------------------------------------------------------------- #
class EngineSignals(QObject):
    status = pyqtSignal(str)
    user_text = pyqtSignal(str)
    bot_text = pyqtSignal(str)
    error = pyqtSignal(str)
    level = pyqtSignal(float)
    hotkey = pyqtSignal()           # קיצור גלובלי נלחץ
    update_found = pyqtSignal(str)  # נמצאה גרסה חדשה (tag)


STATUS_DISPLAY = {
    "connecting":   ("מתחבר…",            Palette.WARNING),
    "reconnecting": ("מתחבר מחדש…",       Palette.WARNING),
    "listening":    ("מאזין — דבר עכשיו", Palette.SUCCESS),
    "speaking":     ("Gemini מדבר…",      Palette.ACCENT),
    "stopped":      ("השיחה הסתיימה",     Palette.TEXT_MUTED),
    "idle":         ("מוכן להתחיל",       Palette.TEXT_MUTED),
}


# ====================================================================== #
# דיאלוג הנחיית מערכת - תבניות מוכנות + עריכה
# ====================================================================== #
class InstructionDialog(QDialog):
    def __init__(self, settings: config.Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("הנחיית מערכת")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(520, 460)
        self.setStyleSheet(f"QDialog {{ background: {Palette.BG}; }}")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        heading = QLabel("הנחיית מערכת")
        heading.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        heading.setStyleSheet(f"color: {Palette.TEXT};")
        layout.addWidget(heading)

        desc = QLabel("בחר תבנית מוכנה, וערוך אותה כרצונך. כך Gemini ידע "
                      "איזה תפקיד למלא ובאיזה סגנון לדבר.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(desc)

        # בורר תבניות
        self.persona_combo = QComboBox()
        self.persona_combo.setStyleSheet(self._combo_style())
        self.persona_combo.addItem("— בחר תבנית —", None)
        for p in config.PERSONAS:
            self.persona_combo.addItem(p.name, p.instruction)
        self.persona_combo.currentIndexChanged.connect(self._on_persona)
        layout.addWidget(self.persona_combo)

        # עורך הטקסט
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(self.settings.system_instruction)
        self.editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {Palette.CARD}; color: {Palette.TEXT};
                border: 1px solid {Palette.CARD_BORDER}; border-radius: 10px;
                padding: 12px; font-size: 13px;
            }}
        """)
        layout.addWidget(self.editor, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        save = buttons.button(QDialogButtonBox.StandardButton.Save)
        save.setText("שמור")
        save.setStyleSheet(
            f"background: {Palette.ACCENT}; color: #00282e; font-weight: bold; "
            f"padding: 8px 22px; border-radius: 8px;"
        )
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setText("ביטול")
        cancel.setStyleSheet(f"color: {Palette.TEXT}; padding: 8px 18px;")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _combo_style(self):
        return f"""
            QComboBox {{
                background: {Palette.CARD}; color: {Palette.TEXT};
                border: 1px solid {Palette.CARD_BORDER}; border-radius: 8px;
                padding: 8px 12px; min-height: 22px;
            }}
            QComboBox:hover {{ border-color: {Palette.ACCENT}; }}
            QComboBox QAbstractItemView {{
                background: {Palette.CARD}; color: {Palette.TEXT};
                selection-background-color: {Palette.ACCENT_DARK};
            }}
        """

    def _on_persona(self, idx: int):
        instruction = self.persona_combo.currentData()
        if instruction:
            self.editor.setPlainText(instruction)

    def _save(self):
        text = self.editor.toPlainText().strip()
        if text:
            self.settings.system_instruction = text
            self.settings.save()
        self.accept()


# ====================================================================== #
# דיאלוג הגדרות - קול, התקנים, ערכת צבעים
# ====================================================================== #
class SettingsDialog(QDialog):
    def __init__(self, settings: config.Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("הגדרות")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(460)
        self.setStyleSheet(f"QDialog {{ background: {Palette.BG}; }}")
        self._build_ui()

    def _combo_style(self):
        return f"""
            QComboBox {{
                background: {Palette.CARD}; color: {Palette.TEXT};
                border: 1px solid {Palette.CARD_BORDER}; border-radius: 8px;
                padding: 8px 12px; min-height: 22px;
            }}
            QComboBox:hover {{ border-color: {Palette.ACCENT}; }}
            QComboBox QAbstractItemView {{
                background: {Palette.CARD}; color: {Palette.TEXT};
                selection-background-color: {Palette.ACCENT_DARK};
            }}
        """

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        heading = QLabel("הגדרות")
        heading.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        heading.setStyleSheet(f"color: {Palette.TEXT};")
        layout.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        label_style = f"color: {Palette.TEXT}; font-size: 13px;"

        def add_row(text, combo):
            combo.setStyleSheet(self._combo_style())
            lbl = QLabel(text)
            lbl.setStyleSheet(label_style)
            form.addRow(lbl, combo)

        # קול
        self.voice_combo = QComboBox()
        for v in config.VOICES:
            icon = "♀" if v.gender == "f" else "♂"
            self.voice_combo.addItem(f"{icon}  {v.hebrew_name} — {v.description}",
                                     v.api_name)
        i = self.voice_combo.findData(self.settings.voice_api)
        if i >= 0:
            self.voice_combo.setCurrentIndex(i)
        add_row("הקול של Gemini:", self.voice_combo)

        # מיקרופון
        self.input_combo = QComboBox()
        for dev in config.list_input_devices():
            self.input_combo.addItem(f"🎤  {dev.name}", dev.index)
        i = self.input_combo.findData(self.settings.input_device)
        if i >= 0:
            self.input_combo.setCurrentIndex(i)
        add_row("מיקרופון:", self.input_combo)

        # רמקול/אוזניות
        self.output_combo = QComboBox()
        for dev in config.list_output_devices():
            self.output_combo.addItem(f"🔊  {dev.name}", dev.index)
        i = self.output_combo.findData(self.settings.output_device)
        if i >= 0:
            self.output_combo.setCurrentIndex(i)
        add_row("רמקול / אוזניות:", self.output_combo)

        # ערכת צבעים
        self.theme_combo = QComboBox()
        for t in config.THEMES:
            self.theme_combo.addItem(f"🎨  {t.hebrew_name}", t.xml)
        i = self.theme_combo.findData(self.settings.theme)
        if i >= 0:
            self.theme_combo.setCurrentIndex(i)
        add_row("ערכת צבעים:", self.theme_combo)

        layout.addLayout(form)

        # --- כלים מתקדמים ---
        tools_title = QLabel("כלים מתקדמים")
        tools_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        tools_title.setStyleSheet(f"color: {Palette.ACCENT}; margin-top: 8px;")
        layout.addWidget(tools_title)

        chk_style = f"""
            QCheckBox {{ color: {Palette.TEXT}; font-size: 13px; spacing: 8px; }}
            QCheckBox::indicator {{ width: 20px; height: 20px; border-radius: 5px;
                                    border: 1px solid {Palette.CARD_BORDER};
                                    background: {Palette.CARD}; }}
            QCheckBox::indicator:checked {{ background: {Palette.ACCENT};
                                            border-color: {Palette.ACCENT}; }}
        """
        self.search_chk = QCheckBox("🔍  חיפוש באינטרנט — תשובות עדכניות מ-Google")
        self.search_chk.setStyleSheet(chk_style)
        self.search_chk.setChecked(self.settings.web_search)
        layout.addWidget(self.search_chk)

        self.think_chk = QCheckBox("🧠  חשיבה מעמיקה — מדויק יותר, אך איטי יותר")
        self.think_chk.setStyleSheet(chk_style)
        self.think_chk.setChecked(self.settings.deep_thinking)
        layout.addWidget(self.think_chk)

        self.echo_chk = QCheckBox("🔇  דיכוי הד — למניעת מצב ש-Gemini שומע את עצמו (לרמקולים)")
        self.echo_chk.setStyleSheet(chk_style)
        self.echo_chk.setChecked(self.settings.echo_suppression)
        layout.addWidget(self.echo_chk)

        echo_note = QLabel("    כבה רק אם אתה משתמש באוזניות (אז אפשר להפריע ל-Gemini תוך כדי דיבור)")
        echo_note.setWordWrap(True)
        echo_note.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        layout.addWidget(echo_note)

        self.memory_chk = QCheckBox("🧩  זיכרון בין שיחות — Gemini יזכור שיחות קודמות")
        self.memory_chk.setStyleSheet(chk_style)
        self.memory_chk.setChecked(self.settings.memory_enabled)
        layout.addWidget(self.memory_chk)

        note = QLabel("הקול, ההתקנים והכלים יחולו בשיחה הבאה. "
                      "שינוי ערכת צבעים יחול בהפעלה הבאה.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        save = buttons.button(QDialogButtonBox.StandardButton.Save)
        save.setText("שמור")
        save.setStyleSheet(
            f"background: {Palette.ACCENT}; color: #00282e; font-weight: bold; "
            f"padding: 8px 22px; border-radius: 8px;"
        )
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setText("ביטול")
        cancel.setStyleSheet(f"color: {Palette.TEXT}; padding: 8px 18px;")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        self.settings.voice_api = self.voice_combo.currentData()
        self.settings.input_device = self.input_combo.currentData()
        self.settings.output_device = self.output_combo.currentData()
        self.settings.theme = self.theme_combo.currentData()
        self.settings.web_search = self.search_chk.isChecked()
        self.settings.deep_thinking = self.think_chk.isChecked()
        self.settings.echo_suppression = self.echo_chk.isChecked()
        self.settings.memory_enabled = self.memory_chk.isChecked()
        self.settings.save()
        self.accept()


# ====================================================================== #
# דיאלוג בסיס ידע - ניהול מסמכים קבועים + ניקוי זיכרון
# ====================================================================== #
class KnowledgeDialog(QDialog):
    def __init__(self, kb: "knowledge.KnowledgeBase",
                 memory: "knowledge.Memory", parent=None):
        super().__init__(parent)
        self.kb = kb
        self.memory = memory
        self.setWindowTitle("בסיס ידע וזיכרון")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(480, 420)
        self.setStyleSheet(f"QDialog {{ background: {Palette.BG}; }}")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        heading = QLabel("📚 בסיס ידע קבוע")
        heading.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        heading.setStyleSheet(f"color: {Palette.TEXT};")
        layout.addWidget(heading)

        desc = QLabel("מסמכים שתוסיף כאן יהיו זמינים ל-Gemini בכל שיחה "
                      "(לא רק פעם אחת). PDF או טקסט.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(desc)

        # רשימת המסמכים
        self.list_widget = QTextEdit()
        self.list_widget.setReadOnly(True)
        self.list_widget.setStyleSheet(f"""
            QTextEdit {{ background: {Palette.CARD}; color: {Palette.TEXT};
                         border: 1px solid {Palette.CARD_BORDER};
                         border-radius: 10px; padding: 10px; }}
        """)
        layout.addWidget(self.list_widget, stretch=1)
        self._refresh_list()

        # כפתורי פעולה
        row = QHBoxLayout()
        add_btn = QPushButton("➕  הוסף מסמך")
        add_btn.setStyleSheet(self._btn_style(Palette.ACCENT, "#00282e"))
        add_btn.clicked.connect(self._add_doc)
        clear_btn = QPushButton("🗑  נקה הכל")
        clear_btn.setStyleSheet(self._btn_style(Palette.CARD, Palette.TEXT))
        clear_btn.clicked.connect(self._clear_kb)
        row.addWidget(add_btn)
        row.addWidget(clear_btn)
        layout.addLayout(row)

        # ניקוי זיכרון שיחות
        mem_btn = QPushButton("🧹  נקה זיכרון שיחות")
        mem_btn.setStyleSheet(self._btn_style(Palette.CARD, Palette.TEXT))
        mem_btn.clicked.connect(self._clear_memory)
        layout.addWidget(mem_btn)

        close_btn = QPushButton("סגור")
        close_btn.setStyleSheet(self._btn_style(Palette.ACCENT, "#00282e"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _btn_style(self, bg, fg):
        return (f"QPushButton {{ background: {bg}; color: {fg}; "
                f"border: 1px solid {Palette.CARD_BORDER}; border-radius: 8px; "
                f"padding: 9px 16px; font-weight: bold; }}")

    def _refresh_list(self):
        names = self.kb.names()
        if not names:
            self.list_widget.setHtml(
                f'<div style="color:{Palette.TEXT_MUTED}; text-align:center; '
                f'padding-top:20px;">אין מסמכים עדיין</div>')
        else:
            items = "".join(
                f'<div style="padding:4px 0;">📄 {n}</div>' for n in names)
            self.list_widget.setHtml(
                f'<div style="color:{Palette.TEXT};">{items}</div>')

    def _add_doc(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "בחר מסמך לבסיס הידע", "",
            "מסמכים (*.pdf *.txt *.md *.csv);;כל הקבצים (*.*)")
        if not path:
            return
        import documents
        try:
            text = documents.extract_text(path)
        except Exception as e:
            QMessageBox.warning(self, "שגיאה", str(e))
            return
        self.kb.add(os.path.basename(path), text)
        self._refresh_list()

    def _clear_kb(self):
        if QMessageBox.question(self, "נקה בסיס ידע", "למחוק את כל המסמכים?") \
                == QMessageBox.StandardButton.Yes:
            for n in list(self.kb.names()):
                self.kb.remove(n)
            self._refresh_list()

    def _clear_memory(self):
        if QMessageBox.question(self, "נקה זיכרון",
                                "למחוק את זיכרון השיחות הקודמות?") \
                == QMessageBox.StandardButton.Yes:
            self.memory.clear()
            QMessageBox.information(self, "נוקה", "זיכרון השיחות נמחק.")


# ====================================================================== #
# כדור קולי מונפש - הלב של העיצוב. מגיב לעוצמת הקול ולמצב.
# ====================================================================== #
class VoiceOrb(QWidget):
    """
    כדור מרכזי שמצויר ב-QPainter ומונפש:
    - טבעות פועמות שמתרחבות החוצה כשמאזין/מדבר
    - הילת זוהר שגדלה עם עוצמת הקול
    - צבע משתנה לפי מצב (סגול=מוכן, כתום=מתחבר, ירוק=מאזין, ציאן=מדבר)
    - לחיצה = התחל/עצור שיחה
    """
    clicked = pyqtSignal()

    STATE_COLORS = {
        "idle":         "#5a6b72",
        "connecting":   "#ffa726",
        "reconnecting": "#ffa726",
        "listening":    "#4cd07d",
        "speaking":     None,   # ישתמש בצבע ההדגשה
    }

    def __init__(self, accent: str, parent=None):
        super().__init__(parent)
        self.accent = accent
        self.state = "idle"
        self._level = 0.0           # יעד עוצמת קול (0..1)
        self._display = 0.0         # ערך מוחלק לתצוגה חלקה
        self._phase = 0.0
        self.setMinimumSize(240, 240)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._timer = QTimer(self)
        self._timer.setInterval(33)   # ~30fps
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_state(self, state: str):
        self.state = state

    def set_level(self, lvl: float):
        # שומרים את המקסימום בין הפריימים כדי לתפוס פסגות
        self._level = max(self._level, min(lvl, 1.0))

    def _color(self) -> QColor:
        c = self.STATE_COLORS.get(self.state)
        return QColor(c if c else self.accent)

    def _tick(self):
        self._phase += 0.05
        # החלקה: מתקרבים ליעד ואז דועכים
        self._display += (self._level - self._display) * 0.3
        self._level *= 0.8
        self.update()

    def mousePressEvent(self, e):
        self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        active = self.state in ("listening", "speaking", "connecting", "reconnecting")
        base_r = min(w, h) * 0.24
        col = self._color()
        lvl = self._display

        # --- טבעות פועמות מתרחבות (כשפעיל) ---
        if active:
            for i in range(3):
                frac = ((self._phase + i * 0.66) % 2.0) / 2.0
                rr = base_r * (1.0 + frac * 1.7)
                a = int(85 * (1.0 - frac) * (0.45 + 0.55 * lvl))
                if a > 0:
                    pen = QPen(QColor(col.red(), col.green(), col.blue(), a))
                    pen.setWidthF(2.0)
                    p.setPen(pen)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawEllipse(QPointF(cx, cy), rr, rr)

        # --- הילת זוהר (גדלה עם עוצמת הקול) ---
        glow_r = base_r * (1.45 + 0.9 * lvl)
        g = QRadialGradient(cx, cy, glow_r)
        g.setColorAt(0, QColor(col.red(), col.green(), col.blue(), int(60 + 130 * lvl)))
        g.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # --- הכדור עצמו (גרדיאנט רדיאלי תלת-ממדי) ---
        orb_r = base_r * (1.0 + 0.13 * lvl)
        og = QRadialGradient(cx - orb_r * 0.32, cy - orb_r * 0.32, orb_r * 1.7)
        og.setColorAt(0.0, col.lighter(155))
        og.setColorAt(0.55, col)
        og.setColorAt(1.0, col.darker(165))
        p.setBrush(og)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), orb_r, orb_r)

        # --- אייקון מיקרופון במרכז ---
        self._draw_mic(p, cx, cy, orb_r * 0.95)

    def _draw_mic(self, p: QPainter, cx: float, cy: float, size: float):
        white = QColor(255, 255, 255, 240)
        # קפסולה
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(white)
        cap_w = size * 0.34
        cap_h = size * 0.60
        rect = QRectF(cx - cap_w / 2, cy - cap_h * 0.75, cap_w, cap_h)
        p.drawRoundedRect(rect, cap_w / 2, cap_w / 2)
        # קשת + רגל
        pen = QPen(white)
        pen.setWidthF(size * 0.065)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        arc_r = size * 0.46
        ar = QRectF(cx - arc_r, cy - arc_r * 0.78, arc_r * 2, arc_r * 1.5)
        p.drawArc(ar, 200 * 16, 140 * 16)
        p.drawLine(QPointF(cx, cy + arc_r * 0.72), QPointF(cx, cy + arc_r * 1.05))
        # בסיס
        bw = size * 0.28
        p.drawLine(QPointF(cx - bw / 2, cy + arc_r * 1.05),
                   QPointF(cx + bw / 2, cy + arc_r * 1.05))


# ====================================================================== #
# החלון הראשי
# ====================================================================== #
class VoiceApp(QMainWindow):
    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key
        self.engine: VoiceEngine | None = None
        self.settings = config.Settings.load()

        # מצב וידאו
        self.capturer = None              # ScreenCapturer / CameraCapturer / None
        self.video_mode: str | None = None  # "screen" / "camera" / None
        self.video_timer = QTimer(self)
        self.video_timer.setInterval(1000)  # פריים לשנייה
        self.video_timer.timeout.connect(self._tick_video)

        # גשר signals
        self.signals = EngineSignals()
        self.signals.status.connect(self._on_status)
        self.signals.user_text.connect(self._on_user_text)
        self.signals.bot_text.connect(self._on_bot_text)
        self.signals.error.connect(self._on_error)
        self.signals.level.connect(self._on_level)
        self.signals.hotkey.connect(self.toggle_conversation)
        self.signals.update_found.connect(self._on_update_found)

        self._turns: list[list[str]] = []

        # מעקב שימוש
        self.usage = config.Usage.load()
        self._session_start = 0.0
        self._tray: QSystemTrayIcon | None = None
        self._force_quit = False

        # זיכרון בין שיחות + בסיס ידע
        self.memory = knowledge.Memory.load()
        self.kb = knowledge.KnowledgeBase.load()

        # אנימציית פעימה לנקודת הסטטוס (תחושת "חי")
        self._pulse_phase = 0.0
        self._pulse_color = Palette.TEXT_MUTED
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(40)
        self._pulse_timer.timeout.connect(self._tick_pulse)

        self.setWindowTitle("שיחה קולית עם Gemini")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(620, 860)
        self.setStyleSheet(f"QMainWindow {{ background: {Palette.BG}; }}")

        # אייקון החלון (סרגל משימות + כותרת)
        icon_path = config.resource_path("app.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui()

        # קיצור מקלדת: רווח להתחלה/עצירה
        shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        shortcut.activated.connect(self.toggle_conversation)

        # שלב 1: מגש מערכת, קיצור גלובלי, בדיקת עדכון
        self._setup_tray()
        self._setup_global_hotkey()
        self._check_updates_async()

    # ------------------------------------------------------------------ #
    # בניית הממשק
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        central = QWidget()
        # רקע גרדיאנט עדין - תחושה פרימיום
        central.setObjectName("central")
        central.setStyleSheet(f"""
            QWidget#central {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #16222a, stop:0.5 {Palette.BG}, stop:1 #0a0e10);
            }}
        """)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(26, 22, 26, 24)
        root.setSpacing(16)

        # ====== שורת כותרת ======
        title_row = QHBoxLayout()
        self.settings_btn = self._icon_button("⚙", "הגדרות — קול, התקנים, צבעים")
        self.settings_btn.clicked.connect(self.open_settings)
        self.persona_btn = self._icon_button("👤", "הנחיית מערכת — אישיות ותפקיד")
        self.persona_btn.clicked.connect(self.open_instruction)
        self.save_btn = self._icon_button("💾", "שמירת תמליל השיחה לקובץ")
        self.save_btn.clicked.connect(self.save_transcript)
        self.kb_btn = self._icon_button("📚", "בסיס ידע וזיכרון")
        self.kb_btn.clicked.connect(self.open_knowledge)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        # לוגו האפליקציה (אם קיים)
        logo_path = config.resource_path("app.png")
        if os.path.exists(logo_path):
            logo = QLabel()
            logo.setPixmap(QPixmap(logo_path).scaled(
                52, 52, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_box.addWidget(logo)
        title = QLabel("שיחה קולית")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Palette.TEXT};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("מבוסס Gemini · עברית")
        subtitle.setFont(QFont("Segoe UI", 10))
        subtitle.setStyleSheet(f"color: {Palette.ACCENT};")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        left_btns = QHBoxLayout()
        left_btns.setSpacing(8)
        left_btns.addWidget(self.settings_btn)
        left_btns.addWidget(self.persona_btn)
        left_btns.addWidget(self.save_btn)
        left_btns.addWidget(self.kb_btn)
        left_wrap = QWidget()
        left_wrap.setLayout(left_btns)
        left_wrap.setStyleSheet("background: transparent;")

        title_row.addWidget(left_wrap)
        title_row.addLayout(title_box, stretch=1)
        spacer = QWidget()
        spacer.setFixedSize(208, 46)   # תואם לרוחב 4 הכפתורים משמאל
        spacer.setStyleSheet("background: transparent;")
        title_row.addWidget(spacer)
        root.addLayout(title_row)

        # ====== כרטיס סטטוס ======
        status_card = QFrame()
        status_card.setStyleSheet(f"""
            QFrame {{ background: {Palette.CARD};
                      border: 1px solid {Palette.CARD_BORDER};
                      border-radius: 14px; }}
        """)
        sl = QHBoxLayout(status_card)
        sl.setContentsMargins(18, 12, 18, 12)
        self.status_dot = QLabel("●")
        self.status_dot.setFont(QFont("Segoe UI", 14))
        self.status_dot.setStyleSheet(f"color: {Palette.TEXT_MUTED};")
        self.status_label = QLabel(STATUS_DISPLAY["idle"][0])
        self.status_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Medium))
        self.status_label.setStyleSheet(f"color: {Palette.TEXT};")
        sl.addWidget(self.status_dot)
        sl.addWidget(self.status_label)
        sl.addStretch()
        root.addWidget(status_card)

        # ====== תצוגה מקדימה של הווידאו (מוסתרת עד הפעלה) ======
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedHeight(180)
        self.preview.setStyleSheet(f"""
            QLabel {{ background: #000; border: 1px solid {Palette.CARD_BORDER};
                      border-radius: 12px; color: {Palette.TEXT_MUTED}; }}
        """)
        self.preview.hide()
        root.addWidget(self.preview)

        # ====== תצוגת תמלול ======
        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setFont(QFont("Segoe UI", 13))
        self.transcript.setStyleSheet(f"""
            QTextEdit {{ background: {Palette.CARD}; color: {Palette.TEXT};
                         border: 1px solid {Palette.CARD_BORDER};
                         border-radius: 14px; padding: 16px; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px; }}
            QScrollBar::handle:vertical {{ background: {Palette.CARD_BORDER};
                         border-radius: 5px; min-height: 30px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self._show_placeholder()
        root.addWidget(self.transcript, stretch=1)

        # ====== בר מדיה (השתקה / מסך / מצלמה + בחירת מקור) ======
        media_bar = QHBoxLayout()
        media_bar.setSpacing(8)
        self.mute_btn = self._toggle_button("🎤  מיקרופון", "השתקת מיקרופון")
        self.mute_btn.clicked.connect(self._toggle_mute)
        self.screen_btn = self._toggle_button("🖥️  מסך", "שיתוף מסך עם Gemini")
        self.screen_btn.clicked.connect(lambda: self._toggle_video("screen"))
        self.cam_btn = self._toggle_button("📷  מצלמה", "שיתוף מצלמה עם Gemini")
        self.cam_btn.clicked.connect(lambda: self._toggle_video("camera"))
        self.record_btn = self._toggle_button("⏺  הקלט", "הקלטת השיחה לקובץ אודיו")
        self.record_btn.clicked.connect(self._toggle_recording)
        self.doc_btn = self._toggle_button("📄  מסמך", "טען מסמך ש-Gemini יקרא")
        self.doc_btn.setCheckable(False)   # פעולה חד-פעמית, לא toggle
        self.doc_btn.clicked.connect(self._load_document)
        media_bar.addWidget(self.mute_btn)
        media_bar.addWidget(self.screen_btn)
        media_bar.addWidget(self.cam_btn)
        media_bar.addWidget(self.record_btn)
        media_bar.addWidget(self.doc_btn)
        root.addLayout(media_bar)

        # בורר מקור וידאו (מוסתר עד שמפעילים מסך/מצלמה)
        self.source_combo = QComboBox()
        self.source_combo.setStyleSheet(f"""
            QComboBox {{ background: {Palette.CARD}; color: {Palette.TEXT};
                         border: 1px solid {Palette.CARD_BORDER};
                         border-radius: 8px; padding: 7px 12px; }}
            QComboBox QAbstractItemView {{ background: {Palette.CARD};
                         color: {Palette.TEXT};
                         selection-background-color: {Palette.ACCENT_DARK}; }}
        """)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.source_combo.hide()
        root.addWidget(self.source_combo)

        # ====== הכדור הקולי (הלב של הממשק) ======
        self.orb = VoiceOrb(Palette.ACCENT)
        self.orb.clicked.connect(self.toggle_conversation)
        orb_row = QHBoxLayout()
        orb_row.addStretch()
        orb_row.addWidget(self.orb)
        orb_row.addStretch()
        root.addLayout(orb_row)

        # תווית מתחת לכדור
        self.orb_label = QLabel("לחץ כדי להתחיל")
        self.orb_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Medium))
        self.orb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.orb_label.setStyleSheet(f"color: {Palette.TEXT};")
        root.addWidget(self.orb_label)

        hk = self.settings.global_hotkey.replace("+", "+").upper()
        hint = QLabel(f"רווח להתחלה/עצירה · {hk} מכל מקום · ניתן להפריע באמצע")
        hint.setFont(QFont("Segoe UI", 9))
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"color: {Palette.TEXT_MUTED};")
        root.addWidget(hint)

        # תווית מעקב שימוש
        self.usage_label = QLabel("")
        self.usage_label.setFont(QFont("Segoe UI", 9))
        self.usage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.usage_label.setStyleSheet(f"color: {Palette.TEXT_MUTED};")
        root.addWidget(self.usage_label)
        self._update_usage_label()

        self._update_media_enabled(False)

    # ------------------------------------------------------------------ #
    # עזרי בנייה
    # ------------------------------------------------------------------ #
    def _icon_button(self, text: str, tip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFont(QFont("Segoe UI", 16))
        btn.setFixedSize(46, 46)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tip)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setStyleSheet(f"""
            QPushButton {{ background: {Palette.CARD}; color: {Palette.TEXT};
                           border: 1px solid {Palette.CARD_BORDER};
                           border-radius: 23px; }}
            QPushButton:hover {{ background: {Palette.CARD_BORDER};
                                 border-color: {Palette.ACCENT}; }}
        """)
        return btn

    def _toggle_button(self, text: str, tip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        btn.setMinimumHeight(42)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tip)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setStyleSheet(f"""
            QPushButton {{ background: {Palette.CARD}; color: {Palette.TEXT};
                           border: 1px solid {Palette.CARD_BORDER};
                           border-radius: 10px; padding: 6px 10px; }}
            QPushButton:hover {{ border-color: {Palette.ACCENT}; }}
            QPushButton:checked {{ background: {Palette.ACCENT_DARK};
                                   border-color: {Palette.ACCENT}; color: #fff; }}
            QPushButton:disabled {{ color: {Palette.TEXT_MUTED}; }}
        """)
        return btn

    def _style_start_button(self):
        """מצב 'מוכן' - הכדור כבוי, תווית הזמנה."""
        self.orb.set_state("idle")
        self.orb_label.setText("לחץ כדי להתחיל")

    def _style_stop_button(self):
        """מצב פעיל - תווית עצירה (צבע הכדור נקבע לפי הסטטוס)."""
        self.orb_label.setText("לחץ כדי לסיים")

    def _on_level(self, level: float):
        """עוצמת קול חיה → אנימציית הכדור."""
        self.orb.set_level(level)

    # ------------------------------------------------------------------ #
    # דיאלוגים
    # ------------------------------------------------------------------ #
    def open_settings(self):
        if SettingsDialog(self.settings, self).exec():
            if self.engine and self.engine.is_running():
                # דיכוי הד חל מיד; שאר ההגדרות בשיחה הבאה
                self.engine.set_echo_suppression(self.settings.echo_suppression)
                v = config.get_voice_by_api(self.settings.voice_api)
                self.status_label.setText(f"הקול ישתנה ל{v.hebrew_name} בשיחה הבאה")

    def open_instruction(self):
        if InstructionDialog(self.settings, self).exec():
            if self.engine and self.engine.is_running():
                self.status_label.setText("ההנחיה החדשה תחול בשיחה הבאה")

    def open_knowledge(self):
        KnowledgeDialog(self.kb, self.memory, self).exec()

    def save_transcript(self):
        """שומר את תמליל השיחה לקובץ טקסט."""
        if not self._turns:
            QMessageBox.information(self, "אין מה לשמור",
                                    "עדיין אין שיחה לשמירה.")
            return

        # שם ברירת מחדל עם תאריך (Qt מספק את הזמן - לא תלוי ב-datetime)
        from PyQt6.QtCore import QDateTime
        stamp = QDateTime.currentDateTime().toString("yyyy-MM-dd_HHmm")
        default = f"שיחה_{stamp}.txt"

        path, _ = QFileDialog.getSaveFileName(
            self, "שמירת תמליל", default, "קובץ טקסט (*.txt)"
        )
        if not path:
            return

        labels = {"user": "אתה", "bot": "Gemini", "error": "שגיאה"}
        lines = [f"שיחה קולית עם Gemini — {stamp}", "=" * 40, ""]
        for speaker, text in self._turns:
            lines.append(f"{labels.get(speaker, speaker)}: {text}")
            lines.append("")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            self.status_label.setText("✓ התמליל נשמר")
        except Exception as e:
            QMessageBox.warning(self, "שגיאה בשמירה", str(e))

    # ------------------------------------------------------------------ #
    # שליטה בשיחה
    # ------------------------------------------------------------------ #
    def toggle_conversation(self):
        if self.engine and self.engine.is_running():
            self._stop_conversation()
        else:
            self._start_conversation()

    def _start_conversation(self):
        self._turns = []
        self.transcript.clear()
        # הרכבת הנחיית המערכת עם זיכרון + בסיס ידע
        instruction = self.settings.system_instruction
        extras = []
        if self.settings.memory_enabled:
            mem = self.memory.context()
            if mem:
                extras.append(mem)
        kb = self.kb.context()
        if kb:
            extras.append(kb)
        if extras:
            instruction = instruction + "\n\n" + "\n\n".join(extras)

        self.engine = VoiceEngine(
            api_key=self.api_key,
            voice_name=self.settings.voice_api,
            input_device=self.settings.input_device,
            output_device=self.settings.output_device,
            system_instruction=instruction,
            web_search=self.settings.web_search,
            deep_thinking=self.settings.deep_thinking,
            on_status=self.signals.status.emit,
            on_user_text=self.signals.user_text.emit,
            on_bot_text=self.signals.bot_text.emit,
            on_error=self.signals.error.emit,
            on_level=self.signals.level.emit,
        )
        self.engine.set_echo_suppression(self.settings.echo_suppression)
        self.engine.start()
        self._session_start = time.monotonic()   # מעקב שימוש
        self._style_stop_button()
        self._update_media_enabled(True)

    def _stop_conversation(self):
        self._stop_video()
        # אם מקליטים - שומרים את ההקלטה לפני הסגירה
        if self.record_btn.isChecked():
            self._save_recording()
            self.record_btn.setChecked(False)
            self.record_btn.setText("⏺  הקלט")
        if self.mute_btn.isChecked():
            self.mute_btn.setChecked(False)
            self.mute_btn.setText("🎤  מיקרופון")
        if self.engine:
            self.engine.stop()
            self.engine = None
        # שמירת השיחה לזיכרון (אם מופעל ויש תוכן)
        if self.settings.memory_enabled:
            real_turns = [t for t in self._turns if t[0] in ("user", "bot")]
            if real_turns:
                from PyQt6.QtCore import QDateTime
                stamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm")
                self.memory.add_conversation(real_turns, stamp)
        # צבירת זמן השיחה למעקב השימוש
        if self._session_start:
            elapsed = time.monotonic() - self._session_start
            if elapsed > 1:
                self.usage.add_session(elapsed)
            self._session_start = 0.0
            self._update_usage_label()
        self._style_start_button()
        self._update_media_enabled(False)
        self._set_status("stopped")

    def _update_usage_label(self):
        """מעדכן את תווית השימוש המצטבר."""
        mins = self.usage.total_minutes
        cost = self.usage.estimated_cost
        self.usage_label.setText(
            f"שימוש מצטבר: {mins:.0f} דק׳ · {self.usage.session_count} שיחות "
            f"· ~${cost:.2f}"
        )

    def _update_media_enabled(self, enabled: bool):
        """מאפשר/חוסם את כפתורי המדיה לפי האם שיחה פעילה."""
        for btn in (self.mute_btn, self.screen_btn, self.cam_btn,
                    self.record_btn, self.doc_btn):
            btn.setEnabled(enabled)

    # ------------------------------------------------------------------ #
    # טעינת מסמך
    # ------------------------------------------------------------------ #
    def _load_document(self):
        """בוחר מסמך, מחלץ טקסט, ושולח ל-Gemini כהקשר לשיחה."""
        if not self.engine or not self.engine.is_running():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "בחר מסמך", "",
            "מסמכים (*.pdf *.txt *.md *.csv);;כל הקבצים (*.*)"
        )
        if not path:
            return
        import documents
        try:
            text = documents.extract_text(path)
        except Exception as e:
            QMessageBox.warning(self, "שגיאה בקריאת המסמך", str(e))
            return

        name = os.path.basename(path)
        prompt = (
            f"המשתמש שיתף איתך מסמך בשם '{name}'. "
            f"קרא אותו והיה מוכן לענות על שאלות לגביו בעברית.\n\n"
            f"--- תוכן המסמך ---\n{text}"
        )
        if self.engine.send_text(prompt):
            self._turns.append(["doc", f"📄 נטען מסמך: {name}"])
            self._render_transcript()
            self.status_label.setText(f"✓ המסמך '{name}' נטען — אפשר לשאול עליו")
        else:
            self.status_label.setText("שליחת המסמך נכשלה")

    # ------------------------------------------------------------------ #
    # הקלטה
    # ------------------------------------------------------------------ #
    def _toggle_recording(self):
        if not self.engine:
            self.record_btn.setChecked(False)
            return
        if self.record_btn.isChecked():
            self.engine.start_recording()
            self.record_btn.setText("⏹  עצור הקלטה")
            self.status_label.setText("● מקליט…")
        else:
            self._save_recording()
            self.record_btn.setText("⏺  הקלט")

    def _save_recording(self):
        """שומר את ההקלטה לקובץ WAV ומציג היכן נשמרה."""
        if not self.engine:
            return
        from PyQt6.QtCore import QDateTime
        stamp = QDateTime.currentDateTime().toString("yyyy-MM-dd_HHmm")
        # תיקיית הקלטות ליד האפליקציה
        rec_dir = os.path.join(config.app_dir(), "הקלטות")
        try:
            os.makedirs(rec_dir, exist_ok=True)
        except Exception:
            rec_dir = config.app_dir()
        path = os.path.join(rec_dir, f"שיחה_{stamp}.wav")
        if self.engine.stop_recording(path):
            self.status_label.setText("✓ ההקלטה נשמרה בתיקיית 'הקלטות'")
        else:
            self.status_label.setText("ההקלטה ריקה — לא נשמרה")

    # ------------------------------------------------------------------ #
    # השתקה
    # ------------------------------------------------------------------ #
    def _toggle_mute(self):
        muted = self.mute_btn.isChecked()
        if self.engine:
            self.engine.set_muted(muted)
        self.mute_btn.setText("🔇  מושתק" if muted else "🎤  מיקרופון")

    # ------------------------------------------------------------------ #
    # וידאו (מסך / מצלמה)
    # ------------------------------------------------------------------ #
    def _toggle_video(self, mode: str):
        btn = self.screen_btn if mode == "screen" else self.cam_btn
        other = self.cam_btn if mode == "screen" else self.screen_btn

        if not btn.isChecked():
            # כובה
            self._stop_video()
            return

        # מצבים הדדיים - מכבים את השני
        if other.isChecked():
            other.setChecked(False)
        self._stop_video(keep_button=mode)

        # אכלוס בורר המקורות
        try:
            if mode == "screen":
                sources = ScreenCapturer.list_sources()
            else:
                sources = CameraCapturer.list_sources()
        except Exception as e:
            self._video_error(f"שגיאה בזיהוי מקורות: {e}", btn)
            return

        if not sources:
            self._video_error("לא נמצא מקור זמין", btn)
            return

        self.video_mode = mode
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for s in sources:
            self.source_combo.addItem(s.name, s)
        self.source_combo.blockSignals(False)
        self.source_combo.show()

        self._start_capturer(sources[0])

    def _on_source_changed(self, idx: int):
        if idx < 0 or not self.video_mode:
            return
        source = self.source_combo.currentData()
        if source:
            self._start_capturer(source)

    def _start_capturer(self, source):
        """פותח לוכד למקור הנבחר ומתחיל את לולאת הפריימים."""
        # סוגרים לוכד קודם
        if self.capturer:
            self.capturer.close()
            self.capturer = None
        try:
            if source.kind == "camera":
                self.capturer = CameraCapturer(source)
            else:
                self.capturer = ScreenCapturer(source)
        except Exception as e:
            self._video_error(f"לא ניתן לפתוח מקור: {e}",
                              self.cam_btn if source.kind == "camera" else self.screen_btn)
            return
        self.preview.show()
        self.preview.setText("טוען תצוגה…")
        self.video_timer.start()

    def _tick_video(self):
        """נקרא כל שנייה: לוכד פריים, מציג תצוגה, ושולח ל-Gemini."""
        if not self.capturer:
            return
        try:
            qimg = self.capturer.grab_qimage()
            jpeg = self.capturer.grab_jpeg()
        except Exception:
            return
        if qimg:
            pix = QPixmap.fromImage(qimg).scaled(
                self.preview.width(), self.preview.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview.setPixmap(pix)
        if jpeg and self.engine:
            self.engine.set_video_frame(jpeg)

    def _stop_video(self, keep_button: str | None = None):
        """עוצר וידאו ומשחרר את הלוכד."""
        self.video_timer.stop()
        if self.capturer:
            self.capturer.close()
            self.capturer = None
        if self.engine:
            self.engine.set_video_frame(None)
        self.video_mode = None
        self.preview.clear()
        self.preview.hide()
        self.source_combo.hide()
        # מכבים את הכפתורים (אלא אם ביקשו להשאיר אחד דלוק תוך כדי מעבר)
        if keep_button != "screen" and self.screen_btn.isChecked():
            self.screen_btn.setChecked(False)
        if keep_button != "camera" and self.cam_btn.isChecked():
            self.cam_btn.setChecked(False)

    def _video_error(self, message: str, btn: QPushButton):
        btn.setChecked(False)
        self.status_label.setText(f"⚠ {message}")

    # ------------------------------------------------------------------ #
    # מטפלי signals
    # ------------------------------------------------------------------ #
    def _on_status(self, status: str):
        self._set_status(status)

    def _set_status(self, status: str):
        text, color = STATUS_DISPLAY.get(status, (status, Palette.TEXT_MUTED))
        if status == "speaking":
            color = Palette.ACCENT
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {Palette.TEXT};")
        self._pulse_color = color
        # עדכון מצב הכדור הקולי
        self.orb.set_state(status)

        # פעימה כשמאזין/מדבר/מתחבר - אחרת נקודה קבועה
        if status in ("listening", "speaking", "connecting", "reconnecting"):
            if not self._pulse_timer.isActive():
                self._pulse_phase = 0.0
                self._pulse_timer.start()
        else:
            self._pulse_timer.stop()
            self.status_dot.setStyleSheet(f"color: {color};")

    def _tick_pulse(self):
        """מאנפש את שקיפות נקודת הסטטוס בגל סינוס - תחושת 'חי'."""
        self._pulse_phase += 0.18
        # אלפא בין 0.35 ל-1.0
        alpha = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(self._pulse_phase))
        h = self._pulse_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        self.status_dot.setStyleSheet(
            f"color: rgba({r}, {g}, {b}, {alpha:.2f});"
        )

    def _on_user_text(self, text: str):
        self._append_chunk("user", text)

    def _on_bot_text(self, text: str):
        self._append_chunk("bot", text)

    def _on_error(self, message: str):
        self._turns.append(["error", message])
        self._render_transcript()
        self._stop_conversation()

    # ------------------------------------------------------------------ #
    # תצוגת תמלול
    # ------------------------------------------------------------------ #
    def _show_placeholder(self):
        self.transcript.setHtml(
            f'<div style="color:{Palette.TEXT_MUTED}; text-align:center; '
            f'padding-top:40px; font-size:14px;">'
            f'התמלול של השיחה יופיע כאן…</div>'
        )

    def _append_chunk(self, speaker: str, text: str):
        if self._turns and self._turns[-1][0] == speaker:
            self._turns[-1][1] += text
        else:
            self._turns.append([speaker, text])
        self._render_transcript()

    def _render_transcript(self):
        meta = {
            "user":  ("אתה",     Palette.USER),
            "bot":   ("Gemini",   Palette.BOT),
            "error": ("⚠ שגיאה", Palette.DANGER),
        }
        html = [f'<div style="color:{Palette.TEXT};">']
        for speaker, text in self._turns:
            if speaker == "doc":
                # הערת מערכת ממורכזת (טעינת מסמך)
                html.append(
                    f'<div style="margin:6px 0; text-align:center; '
                    f'color:{Palette.ACCENT}; font-size:12px;">{text}</div>'
                )
                continue
            label, color = meta.get(speaker, (speaker, Palette.TEXT))
            html.append(
                f'<div style="margin:0 0 14px 0;">'
                f'<span style="color:{color}; font-weight:bold;">{label}:</span> '
                f'<span style="color:{Palette.TEXT};">{text}</span></div>'
            )
        html.append("</div>")
        self.transcript.setHtml("".join(html))
        bar = self.transcript.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    # מגש מערכת
    # ------------------------------------------------------------------ #
    def _setup_tray(self):
        """יוצר אייקון במגש המערכת עם תפריט."""
        icon_path = config.resource_path("app.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else self.windowIcon()
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("שיחה קולית עם Gemini")

        menu = QMenu()
        act_show = QAction("הצג חלון", self)
        act_show.triggered.connect(self._restore_window)
        act_toggle = QAction("התחל / עצור שיחה", self)
        act_toggle.triggered.connect(self.toggle_conversation)
        act_quit = QAction("יציאה", self)
        act_quit.triggered.connect(self._quit_app)
        menu.addAction(act_show)
        menu.addAction(act_toggle)
        menu.addSeparator()
        menu.addAction(act_quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason):
        # לחיצה כפולה על האייקון = הצגת החלון
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_window()

    def _restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self):
        self._force_quit = True
        self.close()

    # ------------------------------------------------------------------ #
    # קיצור מקלדת גלובלי
    # ------------------------------------------------------------------ #
    def _setup_global_hotkey(self):
        """רושם קיצור גלובלי שמתחיל/עוצר שיחה מכל מקום."""
        try:
            import keyboard
        except Exception:
            return
        combo = self.settings.global_hotkey or "ctrl+alt+space"
        try:
            # ה-callback רץ ב-thread נפרד - משדרים signal ל-thread הראשי
            keyboard.add_hotkey(combo, lambda: self.signals.hotkey.emit())
        except Exception:
            pass  # אם הקיצור תפוס/לא חוקי - מתעלמים

    # ------------------------------------------------------------------ #
    # עדכון אוטומטי
    # ------------------------------------------------------------------ #
    def _check_updates_async(self):
        """בודק ברקע אם יש גרסה חדשה ב-GitHub."""
        import threading
        threading.Thread(target=self._check_updates, daemon=True).start()

    def _check_updates(self):
        try:
            import truststore  # כבר מוזרק, אך ליתר ביטחון
            import requests
            url = f"https://api.github.com/repos/{config.GITHUB_REPO}/releases/latest"
            r = requests.get(url, timeout=8)
            if r.status_code != 200:
                return
            tag = r.json().get("tag_name", "").lstrip("v")
            if tag and self._is_newer(tag, config.APP_VERSION):
                self.signals.update_found.emit(tag)
        except Exception:
            pass  # בדיקת עדכון היא נחמדה-אם-אפשר

    @staticmethod
    def _is_newer(remote: str, local: str) -> bool:
        """משווה גרסאות מספריות (1.6 > 1.5)."""
        def parts(v):
            return [int(x) for x in v.split(".") if x.isdigit()]
        try:
            return parts(remote) > parts(local)
        except Exception:
            return False

    def _on_update_found(self, tag: str):
        ans = QMessageBox.question(
            self, "עדכון זמין",
            f"קיימת גרסה חדשה ({tag}).\nלפתוח את דף ההורדה?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            import webbrowser
            webbrowser.open(
                f"https://github.com/{config.GITHUB_REPO}/releases/latest"
            )

    # ------------------------------------------------------------------ #
    def closeEvent(self, event):
        # מזעור למגש במקום סגירה (אם מופעל ולא יציאה מפורשת)
        if (self.settings.minimize_to_tray and self._tray
                and not self._force_quit):
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "ממשיך לרוץ ברקע",
                "האפליקציה במגש המערכת. לחיצה כפולה לפתיחה.",
                QSystemTrayIcon.MessageIcon.Information, 2500,
            )
            return
        self._stop_video()
        if self.engine:
            self.engine.stop()
        try:
            import keyboard
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        event.accept()


def _lighten(hex_color: str, factor: float = 1.18) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{min(int(r*factor),255):02x}{min(int(g*factor),255):02x}{min(int(b*factor),255):02x}"


# ---------------------------------------------------------------------- #
# אשף הגדרת מפתח - מוצג בהפעלה ראשונה כשאין מפתח
# ---------------------------------------------------------------------- #
KEY_FILE = os.path.join(config.app_dir(), "api_key.txt")


class ApiKeyDialog(QDialog):
    """דיאלוג הדבקת מפתח API בהפעלה ראשונה."""

    def __init__(self):
        super().__init__()
        self.api_key = ""
        self.setWindowTitle("הגדרת מפתח API")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(480)
        self.setStyleSheet(f"QDialog {{ background: {Palette.BG}; }}")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 26, 26, 26)
        layout.setSpacing(14)

        heading = QLabel("ברוך הבא! 🎙️")
        heading.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        heading.setStyleSheet(f"color: {Palette.TEXT};")
        layout.addWidget(heading)

        desc = QLabel(
            "כדי להתחיל, צריך מפתח API חינמי של Gemini.\n"
            "1. היכנס לאתר Google AI Studio\n"
            "2. צור מפתח (Create API Key)\n"
            "3. העתק והדבק אותו כאן:"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {Palette.TEXT}; font-size: 13px;")
        layout.addWidget(desc)

        link = QLabel(
            '<a href="https://aistudio.google.com/app/apikey" '
            f'style="color:{Palette.ACCENT};">לחץ כאן לקבלת מפתח →</a>'
        )
        link.setOpenExternalLinks(True)
        link.setStyleSheet("font-size: 13px;")
        layout.addWidget(link)

        self.field = QLineEdit()
        self.field.setPlaceholderText("הדבק כאן את מפתח ה-API שהעתקת")
        self.field.setStyleSheet(f"""
            QLineEdit {{ background: {Palette.CARD}; color: {Palette.TEXT};
                         border: 1px solid {Palette.CARD_BORDER};
                         border-radius: 8px; padding: 10px; font-size: 13px; }}
            QLineEdit:focus {{ border-color: {Palette.ACCENT}; }}
        """)
        self.field.returnPressed.connect(self._accept)
        layout.addWidget(self.field)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"color: {Palette.DANGER}; font-size: 12px;")
        layout.addWidget(self.error_label)

        btn = QPushButton("התחל")
        btn.setMinimumHeight(46)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"background: {Palette.ACCENT}; color: #00282e; font-weight: bold; "
            f"font-size: 15px; border: none; border-radius: 10px;"
        )
        btn.clicked.connect(self._accept)
        layout.addWidget(btn)

    def _accept(self):
        key = self.field.text().strip()
        if len(key) < 20:
            self.error_label.setText("המפתח נראה קצר מדי. בדוק שהעתקת אותו במלואו.")
            return
        # שמירה לקובץ כדי שלא יצטרכו להזין שוב
        try:
            with open(KEY_FILE, "w", encoding="utf-8") as f:
                f.write(key)
        except Exception:
            pass  # גם אם השמירה נכשלה, נמשיך עם המפתח בזיכרון
        self.api_key = key
        self.accept()


def get_api_key() -> str:
    key = os.getenv("GEMINI_API_KEY")
    if key:
        return key
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as f:
            content = f.read().strip()
            # מתעלמים מקובץ הדוגמה / ריק
            if content and "הדבק" not in content:
                return content
    return ""


def main():
    app = QApplication(sys.argv)

    # טעינת ההגדרות כדי לדעת איזו ערכה להחיל
    settings = config.Settings.load()
    theme = config.get_theme_by_xml(settings.theme)
    Palette.apply_accent(theme.accent)
    apply_stylesheet(app, theme=theme.xml, invert_secondary=False)

    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    api_key = get_api_key()
    if not api_key:
        # אשף הגדרת מפתח בהפעלה ראשונה
        dialog = ApiKeyDialog()
        if not dialog.exec():
            sys.exit(0)   # המשתמש סגר בלי להזין מפתח
        api_key = dialog.api_key

    window = VoiceApp(api_key=api_key)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
