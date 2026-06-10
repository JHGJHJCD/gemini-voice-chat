@echo off
REM cleanup_and_install.bat
REM סקריפט להסרת גרסה ישנה והתקנת v1.5 החדשה
REM הרץ כמנהל!

setlocal enabledelayedexpansion
chcp 65001 >nul

echo.
echo ═══════════════════════════════════════════════════════════════
echo  הסרת גרסה ישנה + התקנת v1.5 חדשה
echo ═══════════════════════════════════════════════════════════════
echo.

REM בדוק אם רץ כמנהל
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ שגיאה: צריך להריץ את הסקריפט כמנהל!
    echo.
    echo פתרון:
    echo 1. לחץ ימין על הקובץ
    echo 2. בחר "Run as administrator"
    pause
    exit /b 1
)

echo ✓ רץ כמנהל - בסדר!
echo.

REM שלב 1: הסרת גרסה ישנה
echo [שלב 1] 🗑️ מחפש גרסה ישנה...
set "OLD_APP=%LOCALAPPDATA%\Programs\GeminiVoiceChat"

if exist "%OLD_APP%" (
    echo ✓ נמצאה גרסה ישנה ב:
    echo   %OLD_APP%
    echo.
    echo   מוחק...
    rmdir /s /q "%OLD_APP%" >nul 2>&1

    if exist "%OLD_APP%" (
        echo ❌ לא הצליח למחוק. ייתכן שהתוכנה רצה.
        echo    סגור את התוכנה וחזור שנית.
        pause
        exit /b 1
    ) else (
        echo ✓ גרסה ישנה הוסרה בהצלחה!
    )
) else (
    echo ✓ אין גרסה ישנה (בסדר!)
)

echo.

REM שלב 2: הסרה מRegistry
echo [שלב 2] 📋 ניקוי רשומות מערכת...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\GeminiVoiceChat" /f >nul 2>&1
echo ✓ רשומות נוקו

echo.

REM שלב 3: הורדת v1.5
echo [שלב 3] 📥 הורדת v1.5 החדשה...
echo.
echo 🔗 קישור:
echo https://github.com/JHGJHJCD/gemini-voice-chat/releases/download/v1.5/GeminiVoiceChat-Setup.exe
echo.

set /p DOWNLOAD="רוצה להוריד עכשיו? (y/n): "
if /i "%DOWNLOAD%"=="y" (
    echo ✓ פותח דפדפן...
    start https://github.com/JHGJHJCD/gemini-voice-chat/releases/download/v1.5/GeminiVoiceChat-Setup.exe
    timeout /t 2 >nul
) else (
    echo ✓ בחרת לא להוריד כרגע
)

echo.
echo ═══════════════════════════════════════════════════════════════
echo ✅ הסרה הושלמה!
echo.
echo הצעד הבא:
echo 1. אם הורדת - הרץ את GeminiVoiceChat-Setup.exe
echo 2. בחר "More info" ואז "Run anyway"
echo 3. בדוק "התקן תעודה" בתצוגה
echo 4. התקן!
echo.
echo ═══════════════════════════════════════════════════════════════
pause
