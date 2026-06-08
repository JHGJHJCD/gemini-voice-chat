# שיחה קולית עם Gemini 🎙️

אפליקציית Windows לשיחה קולית רציפה בעברית עם Gemini — כמו מצב הקול של ChatGPT.
מדברים באופן טבעי, Gemini עונה בקול, אפשר להפריע באמצע. כולל שיתוף מסך ומצלמה.

> Hebrew real-time voice chat app for Windows, powered by the Gemini Live API.
> Talk naturally, get spoken replies, share your screen or camera with the AI.

---

## ✨ תכונות

- 🎙️ **שיחה קולית רציפה** — דיבור טבעי + תשובות קוליות, עם אפשרות להפריע (barge-in)
- 🗣️ **10 קולות** עם שמות בעברית (נשיים וגבריים)
- 👤 **הנחיית מערכת מותאמת** — תבניות מוכנות (מורה, מתרגם, יועץ...) לעריכה
- 🖥️ **שיתוף מסך / חלון** — Gemini רואה את המסך ומגיב
- 📷 **מצלמה** — להראות חפצים, מסמכים, סביבה
- 🎤 **השתקת מיקרופון** זמנית
- 🎨 **6 ערכות צבעים** (Material Design)
- ⌨️ **קיצור מקלדת** — רווח להתחלה/עצירה
- 🔒 **תמיכה בסינון נטפרי** (truststore)

---

## 📦 התקנה

### דרישות
- Windows 10/11
- Python 3.10 ומעלה
- מפתח API חינמי מ-[Google AI Studio](https://aistudio.google.com/app/apikey)

### שלבים
```powershell
# 1. התקנת התלויות
python -m pip install -r requirements.txt

# 2. הגדרת מפתח API
#    צור קובץ api_key.txt והדבק בו את המפתח שלך
#    (ראה api_key.example.txt)

# 3. הרצה
python voice_app.py
```

---

## 🏗️ ארכיטקטורה

| קובץ | תפקיד |
|------|--------|
| `voice_app.py` | הממשק הגרפי (PyQt6 + qt-material) |
| `voice_engine.py` | מנוע השיחה הקולית (Gemini Live, אודיו דו-כיווני) |
| `media.py` | לכידת מסך / חלון / מצלמה |
| `config.py` | קולות, תבניות הנחיה, ערכות צבעים, הגדרות |

המנוע משתמש ב-**Gemini Live API** דרך WebSocket — אודיו ילידי דו-כיווני
(16kHz למעלה, 24kHz למטה), עם זיהוי דיבור אוטומטי (VAD) של Gemini.

---

## 🔧 פתרון בעיות

**שגיאת SSL / אין חיבור** — אם אתה מאחורי סינון (נטפרי וכד'), האפליקציה
משתמשת ב-`truststore` כדי לסמוך על תעודות מערכת ההפעלה. ודא שהתעודה של
הסינון מותקנת ב-Windows.

**אין קול / מיקרופון** — בדוק בהגדרות (⚙) שבחרת את ההתקן הנכון.

---

## 📄 רישיון

לשימוש אישי. מבוסס על Gemini API של Google.
