; installer.iss - סקריפט Inno Setup ל-installer מקצועי
; קומפילציה:  ISCC.exe installer.iss
; הפלט:       installer_output\GeminiVoiceChat-Setup.exe

#define AppName "שיחה קולית עם Gemini"
#define AppVersion "1.5"
#define AppPublisher "Yehuda"
#define AppExe "GeminiVoiceChat.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppId={{8F3A2C1B-9D4E-4A7F-B2C8-1E6D5A9F3B70}
; התקנה לתיקיית המשתמש - לא דורש הרשאות מנהל (חוויה חלקה)
DefaultDirName={localappdata}\Programs\GeminiVoiceChat
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=GeminiVoiceChat-Setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; אם יש קובץ אייקון לאשף
DisableWelcomePage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "צור קיצור דרך בשולחן העבודה"; GroupDescription: "קיצורי דרך:"
Name: "installcert"; Description: "התקן תעודת אבטחה (מסיר אזהרת 'מפרסם לא ידוע')"; GroupDescription: "אבטחה:"

[Files]
; כל קבצי האפליקציה מתיקיית ה-one-folder
Source: "dist\GeminiVoiceChat\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; התעודה הציבורית (להתקנה אופציונלית)
Source: "GeminiVoiceChat-Certificate.cer"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; תפריט Start
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\app.ico"
Name: "{group}\הסר את {#AppName}"; Filename: "{uninstallexe}"
; שולחן עבודה (אם נבחר)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\app.ico"; Tasks: desktopicon

[Run]
; התקנת התעודה ל-Trusted Root של המשתמש (אם נבחר) - מסיר אזהרת מפרסם
Filename: "certutil.exe"; Parameters: "-user -addstore -f Root ""{app}\GeminiVoiceChat-Certificate.cer"""; \
  Flags: runhidden; Tasks: installcert; StatusMsg: "מתקין תעודת אבטחה..."
; הפעלת האפליקציה בסיום
Filename: "{app}\{#AppExe}"; Description: "הפעל את {#AppName} עכשיו"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; הסרת התעודה בעת הסרת התוכנה
Filename: "certutil.exe"; Parameters: "-user -delstore Root ""Gemini Voice Chat"""; Flags: runhidden; RunOnceId: "DelCert"
