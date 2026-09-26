"""מפעיל מקומי לגרסת הדפדפן — בלי אתר, בלי חלון שחור.

מריץ שרת קטן על המחשב (localhost בלבד, לא נגיש מבחוץ) ופותח את האפליקציה
בחלון Chrome/Edge במצב "אפליקציה" (בלי סרגל כתובת). כשסוגרים את החלון — השרת נסגר.
"""
import functools
import http.server
import os
import socket
import subprocess
import sys
import threading

PORT = 8765
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
URL = f"http://localhost:{PORT}/"
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # בלי הדפסות
        pass


def port_in_use() -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def main():
    server = None
    if not port_in_use():
        handler = functools.partial(QuietHandler, directory=ROOT)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()

    browser = next((b for b in BROWSERS if os.path.exists(b)), None)
    if browser:
        # פרופיל נפרד כדי שהחלון יהיה תהליך משלו ונדע מתי נסגר
        profile = os.path.join(os.path.dirname(ROOT), ".browser_profile")
        proc = subprocess.Popen([browser, f"--app={URL}", f"--user-data-dir={profile}",
                                 "--no-first-run", "--no-default-browser-check",
                                 "--window-size=1100,800"])
        proc.wait()
    else:
        import webbrowser
        webbrowser.open(URL)
        threading.Event().wait()  # אין דרך לדעת מתי נסגר — השרת נשאר עד שמתנתקים

    if server:
        server.shutdown()


if __name__ == "__main__":
    main()
