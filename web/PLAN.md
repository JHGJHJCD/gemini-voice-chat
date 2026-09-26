# תוכנית הגירה — gemini-voice-chat → אפליקציית דפדפן (PWA)

**החלטה מרכזית:** אפליקציית דפדפן *טהורה* (HTML/CSS/JS ללא שרת, ללא build). הדפדפן מדבר ישירות עם
Gemini Live דרך WebSocket. מתארחת ב-GitHub Pages (`web/` → Actions → `https://jhgjhjcd.github.io/gemini-voice-chat/`)
ומותקנת כ-PWA (אייקון בשולחן העבודה, נפתחת כחלון בלי סרגל כתובת). **אין יותר** PyQt, PyInstaller, Inno, aec.py,
עדכון-מהתוכנה, DPAPI — הדפדפן מספק ביטול הד, הרשאות, עדכון אוטומטי.

## מה נשמר / מה משתנה (למשתמש)
| יכולת | ב-PyQt | בדפדפן |
|---|---|---|
| שיחה קולית רציפה בעברית, barge-in | ✔ | ✔ (`getUserMedia` עם `echoCancellation:true, noiseSuppression:true, autoGainControl:true`) |
| בחירת מודל + שרשרת נפילה | ✔ | ✔ אותה רשימה |
| קולות (10), אישיויות (5), הנחיית מערכת חופשית | ✔ | ✔ |
| VAD (רגישות התחלה/סיום, שקט), דיאלוג רגשי, אודיו פרואקטיבי, חשיבה | ✔ | ✔ |
| תמלול דו-צדדי (בועות שיחה) | ✔ | ✔ יפה יותר |
| שיתוף מסך / מצלמה למודל | ✔ | ✔ `getDisplayMedia` / `getUserMedia({video})` → canvas → JPEG כל 1ש' |
| תרגום וידאו סימולטני (אודיו של דפדפן → עברית) | proctap | ✔ `getDisplayMedia({audio:true})` — המשתמש בוחר **טאב** עם "שתף אודיו" |
| זיכרון שיחות + בסיס ידע (PDF/טקסט) | קבצי JSON | `localStorage` + pdf.js (CDN) |
| שליטה במחשב | פתיחת אפליקציות | **ירד.** נשארים: `open_web`, `get_datetime`, `take_note` (function calling) |
| מילת הפעלה (Picovoice) | ✔ | **ירד** (סטייה מתועדת; אפשר להוסיף Porcupine Web בעתיד) |
| חיפוש Google | ✔ | ✔ (ניסיון חוזר בלי כלים אם המודל דוחה) |
| ערכות צבע | qt-material | 4 ערכות CSS (משתני `:root`) + מצב בהיר/כהה |
| מפתח API | DPAPI | `localStorage` (הזנה חד-פעמית במסך פתיחה; אפשר למחוק) |

## מבנה הקבצים (`web/`)
```
index.html          מסך אחד: hero (כדור קולי מונפש) · תמלול · סרגל פעולות · דיאלוג הגדרות · אשף ראשוני
style.css           עיצוב (RTL, dir="rtl", גופן Heebo מ-Google Fonts עם fallback ל-Segoe UI)
app.js              מצב + UI (ES module)
live.js             מחלקת GeminiLive — WebSocket, setup, אודיו, resumption, fallback (ללא תלות ב-UI)
audio.js            MicCapture (AudioWorklet 16k PCM16) · Player (תור 24k, ניקוי ב-interrupted) · Analyser לויזואליזציה
worklets/mic-processor.js  ה-worklet (resample ל-16k, חיתוך ל-PCM16, postMessage)
media.js            ScreenShare / Camera / TabAudio (תרגום)
storage.js          Settings (ברירות מחדל = config.py), Memory, KnowledgeBase — הכל localStorage
tools.js            function declarations + ביצוע (open_web, get_datetime, take_note)
manifest.webmanifest, sw.js (cache-first לקבצים סטטיים, רשת ל-API), icons/ (מ-app.png)
```
GitHub Pages: `.github/workflows/pages.yml` — upload `web/` בכל push ל-main.

## פרוטוקול Live (מקור: voice_engine.py + סקיל gemini-live-api; שמות JSON ב-camelCase)
- URL: `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=<KEY>`
  (ל-2.5 עם דיאלוג רגשי/פרואקטיבי: `v1alpha` במקום `v1beta`).
- הודעה ראשונה `{"setup": {...}}`:
  ```json
  {"model":"models/gemini-3.8-live",
   "generationConfig":{"responseModalities":["AUDIO"],
      "speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":"Aoede"}}},
      "thinkingConfig":{"thinkingLevel":"LOW"}},        // רק ב-extended-thinking; ב-2.5: {"thinkingBudget":N}; ב-3.8 בסיסי לא לשלוח
   "systemInstruction":{"parts":[{"text":"..."}]},
   "inputAudioTranscription":{}, "outputAudioTranscription":{},
   "realtimeInputConfig":{"automaticActivityDetection":{"prefixPaddingMs":20,"silenceDurationMs":500,
        "startOfSpeechSensitivity":"START_SENSITIVITY_LOW|HIGH","endOfSpeechSensitivity":"END_SENSITIVITY_LOW|HIGH"}},  // MEDIUM = לא לשלוח
   "enableAffectiveDialog":true, "proactivity":{"proactiveAudio":true},   // אופציונלי
   "tools":[{"googleSearch":{}},{"functionDeclarations":[...]}],
   "contextWindowCompression":{"slidingWindow":{}},
   "sessionResumption":{"handle":"<saved or omit>"}}
  ```
  מצב תרגום: `{"model":"models/gemini-3.5-live-translate-preview","generationConfig":{"responseModalities":["AUDIO"]},"outputAudioTranscription":{},"translationConfig":{"targetLanguageCode":"he","echoTargetLanguage":true}}` — בלי VAD, בלי system instruction.
- שרת עונה `{"setupComplete":{}}` → רק אז מתחילים לשלוח אודיו.
- שליחה: `{"realtimeInput":{"audio":{"data":"<b64 PCM16 16k mono>","mimeType":"audio/pcm;rate=16000"}}}` כל ~100ms;
  וידאו `{"realtimeInput":{"video":{"data":"<b64 jpeg>","mimeType":"image/jpeg"}}}`;
  טקסט `{"clientContent":{"turns":[{"role":"user","parts":[{"text":"..."}]}],"turnComplete":true}}`.
- קבלה (הודעות עשויות להגיע כ-Blob — לקרוא `.text()`): `serverContent.modelTurn.parts[].inlineData.data` (PCM16 24k) → נגן;
  `serverContent.interrupted` → לרוקן תור נגינה; `serverContent.inputTranscription.text` / `outputTranscription.text` → בועות (לצבור עד `turnComplete`);
  `sessionResumptionUpdate.{newHandle,resumable}` → לשמור; `goAway` → ניתוק יזום + חיבור מחדש עם handle;
  `toolCall.functionCalls[{id,name,args}]` → להריץ → `{"toolResponse":{"functionResponses":[{"id","name","response":{"result":"..."}}]}}`.
- שגיאות/סגירה (`close.reason`/`code`): "not found"/"not supported"/1008 → מודל הבא בשרשרת; טקסט עם "tool"/"google_search" → אותו מודל בלי כלים;
  API_KEY_INVALID/401/403 → הודעה "המפתח לא תקין" ולפתוח הגדרות; אחר → reconnect עם backoff (1,2,4,8ש', עד 5) ועם ה-handle.

## אודיו (Web Audio)
- `AudioContext({sampleRate:16000})` למיקרופון אם נתמך, אחרת AudioWorklet מבצע resample ליניארי. blokim של 1600 דגימות (100ms).
- נגן: `AudioContext` 24k; לתזמן `AudioBufferSourceNode` ברצף (`nextStartTime`), לשמור רשימת מקורות פעילים כדי לעצור ב-`interrupted`.
  **חובה** לפתוח את ה-AudioContext בלחיצת "התחל" (autoplay policy).
- ויזואליזציה: AnalyserNode על המיקרופון ועל הפלט → כדור/גלים מונפשים (canvas או CSS) שמגיבים לעוצמה; מצבים: מאזין / חושב / מדבר / תרגום.

## עיצוב (זה מה שיהודה יראה — "יותר יפה, יותר מרשים")
- מסך אחד ממורכז, כהה כברירת מחדל, רקע גרדיאנט עמוק עם "אורה" עדינה; כדור קולי גדול במרכז (glow מונפש, פועם לפי עוצמת הקול, צבע לפי מצב).
- למטה: כפתור עגול גדול "התחל / עצור" + כפתורי משנה עגולים (מסך, מצלמה, תרגום וידאו, השתק, הגדרות).
- תמלול כבועות צ'אט (משתמש/בוט) עם גלילה אוטומטית, זמן, וכפתור "נקה".
- פס סטטוס עדין למעלה (מודל פעיל, מצב חיבור, שיתוף פעיל). הודעות שגיאה בעברית פשוטה כ-toast.
- הגדרות: דיאלוג `<dialog>` עם טאבים: כללי (מפתח, מודל, קול עם השמעת דוגמה לא נדרש), אישיות, זיהוי דיבור, יכולות (חיפוש, כלים, רגשי, פרואקטיבי, חשיבה), זיכרון וידע (העלאת PDF/טקסט, מחיקה), מראה (ערכה, בהיר/כהה).
- אשף ראשוני בפעם הראשונה: 3 צעדים (מפתח → קול ואישיות → הרשאת מיקרופון).
- רספונסיבי: עובד גם בטלפון (רוחב 375). `lang="he" dir="rtl"`. ללא ספריות UI. נגישות בסיסית (aria, מקלדת).

## מה *לא* לעשות
- לא להוסיף שרת/backend, לא npm/bundler, לא ספריות מלבד pdf.js (jsdelivr) וגופן Google.
- לא לגעת ב-`api_key.txt`, `settings.json`, ובקוד הפייתון (נשאר עד שהגרסה הדפדפנית מאומתת; לא למחוק).
- לא להריץ שיחה חיה עם מפתח אמיתי.

## אימות (לפני שמדווחים "מוכן")
1. `python -m http.server 8765 -d web` → נפתח ב-Chrome ללא שגיאות קונסולה, RTL תקין, תמונת מסך.
2. עם מפתח דמה `AIza-test` → לחיצה "התחל" מבקשת מיקרופון, פותחת WebSocket, ומציגה שגיאת מפתח ברורה (לא קריסה).
3. Lighthouse/PWA: manifest + sw נטענים; "התקן אפליקציה" זמין.
4. יומן סטיות ב-`web/implementation-notes.md` תחת `## סטיות`.
