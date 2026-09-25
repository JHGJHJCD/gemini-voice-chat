# HANDOFF — שיחה קולית עם Gemini (Gemini Voice Chat)

מסמך העברה לצ'אט חדש. מצב נכון ל-v1.9 (25/9/2026).

## מה זו התוכנה
אפליקציית PyQt6 בעברית: שיחה קולית עם Gemini + **תרגום וידאו סימולטני** (מתרגם אודיו של הדפדפן לעברית בזמן אמת). Windows, one-folder exe + Inno Setup installer, מופצת דרך GitHub Releases.

## סביבה / נתיבים קריטיים
- תיקיית פרויקט: `C:\Users\יהודה\Desktopgemini-voice-chat`
- **בונים עם Python 3.13 בלבד:** `C:\Users\יהודה\AppData\Local\Programs\Python\Python313\python.exe` (3.14 חסר PyQt6)
- תעודת חתימה (self-signed) thumbprint: `D343EC483EC52D1B9C0FFA2D267DF924E624EB63`
- signtool: `C:\Program Files (x86)\Windows Kits\10\App Certification Kit\signtool.exe`
- ISCC: `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`
- gh CLI: `%LOCALAPPDATA%\gh_cli\bin\gh.exe`
- repo: `JHGJHJCD/Desktopgemini-voice-chat`
- NetFree חוסם לפעמים GitHub (HTTP 418) — לנסות שוב.

## ארכיטקטורה (קבצים)
- `voice_engine.py` — מנוע. שני מצבים חולקים `_run_session`: `_build_conversation_setup()` (מודל `gemini-2.5-flash-native-audio-preview-09-2025`) ו-`_build_translate_setup()` (מודל `gemini-3.5-live-translate-preview` + `translation_config` target `he`). לכידת דפדפן דרך `proctap` (`_find_browser_pid` עם pycaw = session פעיל, `_attach_proctap`, `_browser_watchdog`).
- `voice_app.py` — GUI. עדכון-מתוך-התוכנה (`_check_updates`, `_start_update_download`, `_on_update_ready`), חיווי לכידה (`_update_capture_indicator`), לוג (`_setup_logging`), `SetCurrentProcessExplicitAppUserModelID`.
- `config.py` — `APP_VERSION`, `atomic_write_json`, הצפנת מפתח DPAPI (`save_api_key`/`load_api_key`, קידומת `DPAPI:`).
- `knowledge.py` — זיכרון/בסיס ידע (כתיבה אטומית).
- `build.spec` — hiddenimports כולל proctap, psutil, pycaw, comtypes, soundcard.
- `installer.iss` — Inno Setup, שפה **Hebrew.isl**, מסיר גרסה ישנה ב-`InitializeSetup`.
- `make_icon.py` — מייצר `app.ico` (רב-רזולוציה 16..256) + `app.png`.

## תלויות pip שהוספו (מותקנות ב-3.13)
`google-genai==2.8.0` (שודרג! ל-translation_config), `proctap`, `psutil`, `pycaw`, `comtypes`, `soundcard`.

## מצב נוכחי — v1.9 (25/9/2026)
v1.8 לא שוחררה לבד; תוכנה אוחד לתוך v1.9. מה נכנס ב-1.9:
- **מודלים:** `voice_engine.MODELS` — `gemini-3.8-live` (ברירת מחדל, GA), `gemini-3.8-live-extended-thinking`, `gemini-2.5-flash-native-audio-preview-12-2025`. בחירה בהגדרות (`Settings.model`). `_build_conversation_setup(model)` מתאים config לפי מודל: 3.8 בסיסי בלי `thinking_config`; extended עם `thinking_level` (minimal→LOW); 2.5 עם `thinking_budget` ו-v1alpha לדיאלוג רגשי. `_session_main` מנסה את שרשרת `MODEL_FALLBACK_CHAIN` על `_ModelUnavailable`, ומנסה שוב בלי כלים על `_ToolsUnsupported` (חיפוש Google לא מאושר בתיעוד 3.8).
- **שיחה ארוכה:** `context_window_compression` (sliding window) + `session_resumption` (handle נשמר ב-`_receive`, `go_away` → ניתוק יזום והתחברות מחדש עם אותו handle).
- **ביטול הד (`aec.py`):** `ReferenceBuffer` (מה שהושמע ברמקול, 24k→16k ב-numpy) → `EchoCanceller` (PBFDAF, 24×25ms=600ms זנב) → `EchoGate` (מתאם ρ בין מיקרופון להד המשוער + סף שארית לפי ERLE; שנייה ראשונה = חוק העוצמה הישן 0.22). בלוק הרמקול 2400 (100ms) כדי לשמור יישור. בדיקות: `test_aec.py`, `test_models.py`.
- אייקון חדש רב-רזולוציה, AppUserModelID, עדכון-מתוך-התוכנה, התקנה בעברית (מ-1.8).

### להמשך / ידוע
- `settings.json` המקומי: `picovoice_key` מכיל מפתח שנראה כמו Google (`AIza…`) — מילת הפעלה תיכשל אם תופעל. לא שונה.
- אימות חי מול Gemini 3.8 (שיחה אמיתית) — ע"י יהודה בלבד (מפתח שלו). לפתוח את `log.txt` אם משהו לא עובד.
- `implementation-notes.md` — יומן סטיות של 1.9.

### פקודות שחרור (בנייה → חתימה → מתקין → release → commit)
```powershell
$T="D343EC483EC52D1B9C0FFA2D267DF924E624EB63"
$ST="C:\Program Files (x86)\Windows Kits\10\App Certification Kit\signtool.exe"
$GH="$env:LOCALAPPDATA\gh_cli\bin\gh.exe"
$PY="C:\Users\יהודה\AppData\Local\Programs\Python\Python313\python.exe"
cd "C:\Users\יהודה\Desktop\gemini-voice-chat"
& $PY -m pytest test_aec.py test_models.py test_suite.py -q          # 0. בדיקות
& $PY -m PyInstaller build.spec --noconfirm                           # 1. exe (~3 דק')
& $ST sign /sha1 $T /fd SHA256 /t http://timestamp.digicert.com "dist\GeminiVoiceChat\GeminiVoiceChat.exe"
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss        # 2. מתקין (~5 דק'; לסגור את האפליקציה קודם)
& $ST sign /sha1 $T /fd SHA256 /t http://timestamp.digicert.com "installer_output\GeminiVoiceChat-Setup.exe"
& $GH release create vX.Y "installer_output\GeminiVoiceChat-Setup.exe" --repo JHGJHJCD/gemini-voice-chat --title "vX.Y" --notes "..."
git add -A; git commit -m "vX.Y - ..."; git push origin main
```
לפני חתימה: להריץ את ה-exe, לוודא שנפתח, לסגור. NetFree חוסם לפעמים GitHub (418) — לנסות שוב.

## עובדות/מלכודות
- מפתח API ב-`api_key.txt` מוצפן DPAPI (קידומת `DPAPI:`) — לא לגעת.
- מודלי Gemini הם **preview** — יש טיפול חינני (`_FatalError` על not_found) ב-`_run_session`.
- תרגום: לכידת דפדפן בלבד (בלי משוב). מפגר קבוע ~5ש' (טבעי לתרגום סימולטני, לא באג). השתקה: דרך Windows Volume Mixer (Chrome), לא בנגן יוטיוב.
- עדכון-מתוך-התוכנה מגיע למשתמשים רק מ-v1.8 והלאה.
- `log.txt` נוצר ליד ה-exe — להוסיף ל-.gitignore.
