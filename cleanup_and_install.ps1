# cleanup_and_install.ps1
# הסרת גרסה ישנה + הורדה של v1.5
# הרץ כמנהל: Right-Click → Run with PowerShell

param(
    [switch]$Auto = $false  # אם $Auto - לא שואל שאלות
)

function Write-Header {
    Write-Host "`n════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  הסרת גרסה ישנה + התקנת v1.5 חדשה" -ForegroundColor Cyan
    Write-Host "════════════════════════════════════════════════════════════════`n" -ForegroundColor Cyan
}

function Test-Admin {
    $admin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) {
        Write-Host "❌ שגיאה: צריך להריץ כמנהל!" -ForegroundColor Red
        Write-Host "פתרון: לחץ ימין → Run with PowerShell (as administrator)" -ForegroundColor Yellow
        pause
        exit 1
    }
    Write-Host "✓ רץ כמנהל - בסדר!`n" -ForegroundColor Green
}

function Remove-OldVersion {
    Write-Host "[שלב 1] 🗑️  מחפש גרסה ישנה..." -ForegroundColor Yellow

    $appPath = "$env:LOCALAPPDATA\Programs\GeminiVoiceChat"

    if (Test-Path $appPath) {
        Write-Host "✓ נמצאה גרסה ישנה ב:" -ForegroundColor Green
        Write-Host "  $appPath`n"

        Write-Host "מוחק..." -ForegroundColor Yellow
        Remove-Item -Path $appPath -Recurse -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1

        if (Test-Path $appPath) {
            Write-Host "❌ לא הצליח למחוק. הסגור את התוכנה!" -ForegroundColor Red
            pause
            exit 1
        } else {
            Write-Host "✓ גרסה ישנה הוסרה בהצלחה!`n" -ForegroundColor Green
        }
    } else {
        Write-Host "✓ אין גרסה ישנה (בסדר!)` n" -ForegroundColor Green
    }
}

function Remove-RegistryEntry {
    Write-Host "[שלב 2] 📋 ניקוי Registry..." -ForegroundColor Yellow

    $regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\GeminiVoiceChat"
    Remove-Item -Path $regPath -Force -ErrorAction SilentlyContinue

    Write-Host "✓ Registry נוקתה`n" -ForegroundColor Green
}

function Download-V15 {
    Write-Host "[שלב 3] 📥 הורדת v1.5..." -ForegroundColor Yellow
    Write-Host "`n🔗 קישור:" -ForegroundColor Cyan
    Write-Host "https://github.com/JHGJHJCD/gemini-voice-chat/releases/download/v1.5/GeminiVoiceChat-Setup.exe`n"

    if ($Auto) {
        Write-Host "✓ מצב אוטומטי - פותח הורדה..." -ForegroundColor Green
        Start-Process "https://github.com/JHGJHJCD/gemini-voice-chat/releases/download/v1.5/GeminiVoiceChat-Setup.exe"
        return
    }

    $answer = Read-Host "רוצה להוריד עכשיו? (y/n)"

    if ($answer -eq "y" -or $answer -eq "Y") {
        Write-Host "✓ פותח דפדפן..." -ForegroundColor Green
        Start-Process "https://github.com/JHGJHJCD/gemini-voice-chat/releases/download/v1.5/GeminiVoiceChat-Setup.exe"
        Start-Sleep -Seconds 2
    } else {
        Write-Host "✓ בחרת לא להוריד כרגע" -ForegroundColor Yellow
    }
}

function Show-Summary {
    Write-Host "`n════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "✅ הסרה הושלמה!" -ForegroundColor Green
    Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan

    Write-Host "`nהצעד הבא:" -ForegroundColor Yellow
    Write-Host "1. אם הורדת - הרץ את GeminiVoiceChat-Setup.exe"
    Write-Host "2. בחר 'More info' ואחר כך 'Run anyway' (תקין!)"
    Write-Host "3. בדוק 'התקן תעודה' בשדה תצוגה"
    Write-Host "4. התקן!"
    Write-Host ""
}

# ביצוע
Write-Header
Test-Admin
Remove-OldVersion
Remove-RegistryEntry
Download-V15
Show-Summary
Read-Host "לחץ Enter לסגירה"
