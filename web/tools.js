// tools.js — function calling: הצהרות + ביצוע. תואם computer_tools.py,
// בהשמטת open_application (אין גישה לפתיחת תוכנות מדפדפן — סטייה מתועדת).

export const FUNCTION_DECLARATIONS = [
  {
    name: "open_website",
    description: "פותח אתר אינטרנט בכרטיסייה חדשה בדפדפן.",
    parameters: {
      type: "object",
      properties: {
        url: { type: "string", description: "כתובת האתר (למשל youtube.com)" },
      },
      required: ["url"],
    },
  },
  {
    name: "get_datetime",
    description: "מחזיר את התאריך והשעה הנוכחיים.",
    parameters: { type: "object", properties: {} },
  },
  {
    name: "take_note",
    description: "שומר פתק/תזכורת לרשימת פתקים מקומית בדפדפן.",
    parameters: {
      type: "object",
      properties: {
        text: { type: "string", description: "תוכן הפתק" },
      },
      required: ["text"],
    },
  },
];

const NOTES_KEY = "gvc.notes";

function openWebsite(url) {
  url = (url || "").trim();
  if (!url) return "לא צוינה כתובת.";
  if (!/^https?:\/\//i.test(url)) url = "https://" + url;
  window.open(url, "_blank", "noopener");
  return `פתחתי את ${url}.`;
}

function getDatetime() {
  const now = new Date();
  const days = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
  const day = days[now.getDay()];
  const dd = String(now.getDate()).padStart(2, "0");
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const yyyy = now.getFullYear();
  const hh = String(now.getHours()).padStart(2, "0");
  const mi = String(now.getMinutes()).padStart(2, "0");
  return `היום יום ${day}, ${dd}/${mm}/${yyyy}, השעה ${hh}:${mi}.`;
}

function takeNote(text) {
  if (!text || !text.trim()) return "הפתק ריק.";
  try {
    const raw = localStorage.getItem(NOTES_KEY);
    const notes = raw ? JSON.parse(raw) : [];
    const stamp = new Date().toLocaleString("he-IL");
    notes.push({ time: stamp, text });
    localStorage.setItem(NOTES_KEY, JSON.stringify(notes));
    return "הפתק נשמר.";
  } catch {
    return "לא הצלחתי לשמור את הפתק.";
  }
}

// מבצע קריאת function call אחת, מחזיר טקסט תוצאה ל-Gemini.
export function executeTool(name, args) {
  try {
    switch (name) {
      case "open_website":
        return openWebsite(args?.url);
      case "get_datetime":
        return getDatetime();
      case "take_note":
        return takeNote(args?.text);
      default:
        return `פונקציה לא מוכרת: ${name}`;
    }
  } catch (e) {
    return `שגיאה בביצוע ${name}: ${e}`;
  }
}
