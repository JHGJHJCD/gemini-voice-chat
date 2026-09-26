@echo off
chcp 65001 >nul
cd /d "%~dp0web"
start "" http://localhost:8765
"C:\Users\יהודה\AppData\Local\Programs\Python\Python313\python.exe" -m http.server 8765
