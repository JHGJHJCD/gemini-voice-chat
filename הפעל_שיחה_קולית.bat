@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo מפעיל שיחה קולית עם Gemini...
python voice_app.py
if errorlevel 1 (
    echo.
    echo אירעה שגיאה. ודא ש-Python מותקן והתלויות הותקנו.
    pause
)
