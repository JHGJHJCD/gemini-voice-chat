# שיחה קולית עם Gemini (gemini-voice-chat)

אפליקציית Windows (PyQt6) לשיחה קולית רציפה בעברית עם Gemini Live + תרגום וידאו סימולטני.
מופצת כ-one-folder exe + מתקין Inno Setup דרך GitHub Releases (`JHGJHJCD/gemini-voice-chat`).
**מסמכי ההקשר:** `HANDOFF.md` (מצב + פקודות שחרור) · `implementation-notes.md` (יומן סטיות של הגרסה האחרונה) · סקילים גלובליים `gemini-voice-chat` (עבודה ושחרור) ו-`gemini-live-api` (ידע על ה-API).

## סביבה
- **Python 3.13 בלבד:** `C:\Users\יהודה\AppData\Local\Programs\Python\Python313\python.exe` (ה-`python` ב-PATH הוא 3.14 בלי PyQt6).
- SDK: `google-genai` (מותקן 2.10; חדש יותר קיים — לשדרג רק אם צריך ולבדוק `build.spec`).
- נטפרי: `truststore.inject_into_ssl()` בראש `voice_engine.py` — חובה לפני כל ייבוא רשת. `pip`/GitHub נחסמים לפעמים (418) — לנסות שוב.
- מפתח API ב-`api_key.txt` מוצפן DPAPI (`DPAPI:` קידומת) — **לא לגעת, לא להדפיס.** רשימת מודלים דרך REST נכשלת עם המפתח הזה (401) — לא באג.

## קבצים
| קובץ | תפקיד |
|---|---|
| `voice_app.py` | GUI (2200 שורות): הגדרות, אשף ראשוני, עדכון-מהתוכנה, מדיה |
| `voice_engine.py` | מנוע: asyncio ב-thread, sounddevice, Live API, בחירת מודל + שרשרת נפילה, ביטול הד |
| `aec.py` | ביטול הד אקוסטי (numpy בלבד): `ReferenceBuffer` → `EchoCanceller` (PBFDAF) → `EchoGate` |
| `config.py` | `APP_VERSION`, `Settings` (dataclass + save/load ידני — **שדה חדש = 3 מקומות**), קולות, ערכות |
| `knowledge.py`, `documents.py`, `media.py`, `computer_tools.py`, `wakeword.py` | זיכרון, PDF, מסך/מצלמה, שליטה במחשב, מילת הפעלה |
| `build.spec`, `installer.iss`, `make_icon.py` | בנייה (PyInstaller one-folder), מתקין (Hebrew.isl), אייקון |
| `test_suite.py`, `test_aec.py`, `test_models.py`, `test_stability.py` | pytest — להריץ לפני כל בנייה |

## כללים
- **Claude לא מריץ שיחה חיה** (זה המפתח של יהודה). מותר: להריץ את האפליקציה/exe כדי לוודא שנפתחת, לקרוא `log.txt`.
- מודלי Gemini הם preview/משתנים: **כל שינוי מודל = לעדכן `voice_engine.MODELS`** (הסדר = שרשרת נפילה) + `test_models.py`. הגדרות תלויות-מודל רק ב-`_build_conversation_setup`.
- ביטול הד: לא להחזיר "סף עוצמה" גלובלי. כוונון ב-`aec.py` דרך הקבועים למעלה (`NEAR_RATIO`, `RHO_ECHO`, `NEAR_FLOOR`, `PARTITIONS`), ואחריו `pytest test_aec.py`.
- `Settings` — שדה חדש חייב להופיע ב-dataclass, ב-`save()` וב-`load()`.
- קידוד: כל הקבצים UTF-8; `.bat` CRLF; הודעות למשתמש בעברית.
- גרסה: `config.APP_VERSION` + `installer.iss AppVersion` + תג release — שלושתם יחד.
- לא להוסיף Co-Authored-By להודעות commit.

## גרסת דפדפן (PWA) — `web/` (26/9/2026)
הגירה מ-PyQt לאפליקציית web טהורה (ללא שרת/build): `web/PLAN.md` = התוכנית והפרוטוקול; `web/implementation-notes.md` = סטיות.
הרצה מקומית: `הפעל_גרסת_דפדפן.bat` (http.server על 8765). פריסה: ענף `gh-pages` (`git subtree push --prefix web origin gh-pages`).
קוד הפייתון נשאר עד שהגרסה הדפדפנית מאומתת חי. מודל חדש = לעדכן גם `web/live.js` MODELS.
