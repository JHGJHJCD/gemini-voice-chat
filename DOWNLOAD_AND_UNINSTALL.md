# 📥 הורדה והסרה — שיחה קולית עם Gemini v1.5

---

## 📥 להורדה וההתקנה

### קישור ישיר — לחץ כאן להורדה! 

```
https://github.com/JHGJHJCD/gemini-voice-chat/releases/download/v1.5/GeminiVoiceChat-Setup.exe
```

**גודל:** ~75 MB  
**סוג:** Windows installer (exe)  
**חתום:** כן ✓ (תעודה עצמית)

---

### שלבי התקנה

1. **הורד את הקובץ**
   - לחץ על הקישור למעלה
   - או היכנס לעמוד ה-Release: https://github.com/JHGJHJCD/gemini-voice-chat/releases/latest

2. **הרץ ה-installer**
   ```
   GeminiVoiceChat-Setup.exe
   ```

3. **אזהרת Windows (תקינה)**
   ```
   ⚠️ "Windows protected your PC"
   → More info → Run anyway
   ```
   (תקין! התוכנה לא בעלת תעודה מסחרית שכרויה)

4. **בחר אפשרויות**
   ```
   ☑ התקן תעודת אבטחה (מסיר אזהרות)
   ☑ צור קיצור דרך בשולחן העבודה
   ```

5. **התקנה**
   - לחץ Install
   - המתן לסיום
   - בחר "הפעל עכשיו"

6. **הפעלה ראשונה**
   - תתבקש מפתח API (חינמי)
   - היכנס ל: https://aistudio.google.com/app/apikey
   - צור key והדבק
   - לחץ "התחל"

---

## 🗑️ להסרה מהמחשב

### שיטה 1: דרך Settings (הקלה)

```
Windows Settings
  ↓
Apps (אפליקציות)
  ↓
Installed apps (יישומים מותקנים)
  ↓
חפש: "שיחה קולית" או "Gemini"
  ↓
לחץ עליו
  ↓
Uninstall (הסר)
  ↓
אשר הסרה
```

### שיטה 2: דרך Control Panel (קלאסי)

```
Control Panel (לוח בקרה)
  ↓
Programs
  ↓
Programs and Features (תוכניות ותכונות)
  ↓
חפש: "שיחה קולית" או "Gemini"
  ↓
בחר
  ↓
Uninstall
  ↓
אשר
```

### שיטה 3: מ-Start Menu

```
Start Menu (תפריט התחלה)
  ↓
חיפוש: "שיחה קולית"
  ↓
לחץ ימין (right-click)
  ↓
Uninstall
```

### ניקוי מלא (אחרי הסרה)

הסרת קובץ התיקייה (אם בחרת תיקייה קסטום):

```
C:\Users\[שמך]\AppData\Local\Programs\GeminiVoiceChat
```

הסרת נתונים אישיים (אופציונלי):

```
C:\Users\[שמך]\AppData\Local\Programs\GeminiVoiceChat\*
  ├── api_key.txt (מפתח API שלך)
  ├── settings.json (הגדרות קול וצבע)
  ├── memory.json (שיחות שנשמרו)
  ├── knowledge.json (מסמכים שהוספת)
  ├── usage.json (סטטיסטיקות שימוש)
  └── הקלטות/ (קבצי WAV שהקלטת)
```

**הסרת התעודה הידנית** (אם התקנת):

```
PowerShell (כמנהל):
  certutil.exe -user -delstore Root "Gemini Voice Chat"
```

---

## 📋 דרישות מינימליות

- **OS:** Windows 10 או 11
- **RAM:** 2 GB (המלצה: 4 GB+)
- **מיקום דיסק:** 200 MB חופשי
- **אינטרנט:** חיבור קבוע (Gemini Live API)
- **אודיו:** מיקרופון + רמקולים (או אוזניות)

---

## 🔧 פתרון בעיות

### "Windows protected your PC"
```
→ More info
→ Run anyway
```
זה תקין! התוכנה בטוחה, פשוט לא עם תעודה מסחרית.

### "Installer לא מתחיל"
1. בדוק: האם קובץ הורד לחלוטין? (75 MB)
2. בדוק: שם הקובץ לא מכיל תווים מוזרים?
3. ערוך ידנית הורדה מחדש

### "התוכנה לא עונה"
1. בדוק: האם יש מפתח API תקין?
2. בדוק: אינטרנט פעיל?
3. כבה ופתח מחדש

### "מיקרופון לא נראה"
```
Windows Settings
  → Privacy & Security
  → Microphone
  → Allow apps to access microphone: ON
  → scroll down, find "שיחה קולית" → ON
```

---

## 💡 טיפים

- **קיצור מקלדת:** `Ctrl+Alt+Space` — התחל/עצור שיחה (כל מקום)
- **ממגש:** לחץ אייקון → מינימום; לחץ שוב → הצג
- **שדרוג:** בדיקה אוטומטית בהגדרות
- **היסטוריה:** קבצים בתיקיית ההתקנה

---

## 🆘 עזרה נוספת

**דיווח באגים:**  
https://github.com/JHGJHJCD/gemini-voice-chat/issues

**בקשות פיצ'רים:**  
https://github.com/JHGJHJCD/gemini-voice-chat/discussions

**קוד משמע:**  
https://github.com/JHGJHJCD/gemini-voice-chat

---

**נוצר:** 2026-06-10  
**גרסה:** v1.5  
**Status:** ✅ Production Ready
