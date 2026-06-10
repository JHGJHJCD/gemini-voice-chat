# 🗑️ הסרה אוטומטית של גרסה ישנה

**שתי דרכים להסיר גרסה ישנה בחכמה:**

---

## **דרך 1: Batch Script (הקלה)** ⭐

### **איך להשתמש:**

1. **מצא את הקובץ:**
   ```
   cleanup_and_install.bat
   ```

2. **לחץ כפול** (double-click) על הקובץ

3. **אשר UAC** (אם מופיע)
   ```
   "Do you want to allow this app to make changes?"
   → Yes
   ```

4. **חכה שהתוכנה הישנה תמחק**

5. **בחר אם להוריד v1.5:**
   ```
   רוצה להוריד עכשיו? (y/n): y
   ```

6. **דפדפן נפתח → לחץ Download**

7. **הרץ את ה-Setup.exe החדש**

---

## **דרך 2: PowerShell Script (חזק יותר)** 

### **איך להשתמש:**

1. **לחץ ימין** על `cleanup_and_install.ps1`

2. **בחר:** `Run with PowerShell`

3. **אשר UAC**
   ```
   "Do you want to allow this app?"
   → Yes
   ```

4. **חכה שהמסך ישחור (זה תקין!)**

5. **בחר:**
   ```
   רוצה להוריד עכשיו? (y/n): y
   ```

6. **הדפדפן פתח → יורד v1.5**

7. **הרץ את GeminiVoiceChat-Setup.exe**

---

## **עם דגל אוטומטי** (ללא שאלות)

אם רוצה **שלא תשאל שאלות:**

```powershell
# PowerShell כמנהל:
.\cleanup_and_install.ps1 -Auto
```

זה **יסיר + יוריד אוטומטית.**

---

## **מה קורה:**

| שלב | פעולה | סטטוס |
|-----|--------|--------|
| 1️⃣ | מחפש גרסה ישנה | `$LOCALAPPDATA\Programs\GeminiVoiceChat` |
| 2️⃣ | מוחק את התיקייה | `rmdir /s /q` או `Remove-Item` |
| 3️⃣ | ניקוי Registry | `HKCU\...\Uninstall\GeminiVoiceChat` |
| 4️⃣ | הורדה ישיר | v1.5 מ-GitHub |

---

## 🆘 **אם יש בעיה**

### **"Access Denied"**
```
✓ סגור את התוכנה תחילה
✓ הרץ את הscript כמנהל (Run as administrator)
```

### **"File in use"**
```
✓ סגור את התוכנה
✓ סגור את Explorer אם הוא פתוח בתיקייה
✓ נסה שנית
```

### **Batch לא עובד**
```
✓ נסה את ה-PowerShell script במקום
✓ או הסר ידנית (ראה DOWNLOAD_AND_UNINSTALL.md)
```

---

## 📋 **עבור קבוצות / IT מנהלים**

**להריץ לכל המשתמשים:**

```batch
REM Run on all computers (domain)
.\cleanup_and_install.bat
```

**או ב-PowerShell:**

```powershell
Get-ADComputer -Filter * | ForEach-Object {
    Invoke-Command -ComputerName $_.Name -ScriptBlock {
        C:\Scripts\cleanup_and_install.ps1 -Auto
    }
}
```

---

## ✅ **וודא הצלחה**

```
הגדרות → אפליקציות → תוכניות מותקנות
חפש: "שיחה קולית"
→ אמור להיות: v1.5 ✓
```

---

**יוצר:** 2026-06-10  
**גרסה:** v1.5 cleanup scripts
