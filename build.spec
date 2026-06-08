# -*- mode: python ; coding: utf-8 -*-
"""
build.spec - מפרט בנייה ל-PyInstaller.
בונה קובץ הפעלה יחיד (.exe) ללא תלות ב-Python מותקן.

בנייה:  python -m PyInstaller build.spec --noconfirm
הפלט:   dist/GeminiVoiceChat.exe
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# קבצי נתונים שצריך לארוז יחד עם הקוד
datas = []
datas += collect_data_files("qt_material")      # ערכות העיצוב (XML, פונטים)
datas += collect_data_files("google")           # נתוני google-genai אם יש
datas += [("app.png", "."), ("app.ico", ".")]   # אייקון ולוגו

# מודולים שעלולים להתפספס בזיהוי האוטומטי
hiddenimports = []
hiddenimports += collect_submodules("google.genai")
hiddenimports += ["sounddevice", "mss", "pygetwindow", "cv2", "PIL"]

a = Analysis(
    ["voice_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas"],  # לא בשימוש - מקטין גודל
    noarchive=False,
)

pyz = PYZ(a.pure)

# מצב one-folder (תיקייה) - מהיר יותר ופחות נחסם ע"י אנטי-וירוס מ-one-file.
# ה-installer יארוז את התיקייה הזו ויתקין אותה ל-Program Files.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,     # הקבצים הבינאריים בתיקייה, לא בתוך ה-exe
    name="GeminiVoiceChat",
    icon="app.ico",            # אייקון מותאם ל-exe
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # בלי UPX - מפחית false-positives של אנטי-וירוס
    console=False,             # אפליקציית GUI - בלי חלון מסוף
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GeminiVoiceChat",
)
