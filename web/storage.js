// storage.js — הגדרות, זיכרון, בסיס ידע ומפתח API, הכל ב-localStorage.
// מראה 1:1 את config.py (Settings dataclass) ואת knowledge.py (Memory/KnowledgeBase)
// כדי שהמשתמש ירגיש בבית מגרסת ה-PyQt.

// ---------------------------------------------------------------------- //
// קטלוג קולות — voice_api (שם ל-API) + hebrew_name + description + gender
// ---------------------------------------------------------------------- //
export const VOICES = [
  { hebrew_name: "נועה",  api_name: "Aoede",    description: "קלילה ונעימה",  gender: "f" },
  { hebrew_name: "מאיה",  api_name: "Kore",     description: "ברורה ותקיפה",  gender: "f" },
  { hebrew_name: "יעל",   api_name: "Leda",     description: "צעירה ורעננה",  gender: "f" },
  { hebrew_name: "תמר",   api_name: "Sulafat",  description: "חמה ונינוחה",   gender: "f" },
  { hebrew_name: "ליאת",  api_name: "Achernar", description: "רכה ועדינה",    gender: "f" },
  { hebrew_name: "איתי",  api_name: "Puck",     description: "אנרגטי ושמח",   gender: "m" },
  { hebrew_name: "דניאל", api_name: "Charon",   description: "ענייני ורגוע",  gender: "m" },
  { hebrew_name: "אורי",  api_name: "Orus",     description: "תקיף ובטוח",    gender: "m" },
  { hebrew_name: "יונתן", api_name: "Algieba",  description: "חלק ונעים",     gender: "m" },
  { hebrew_name: "נועם",  api_name: "Achird",   description: "ידידותי וחביב", gender: "m" },
];
export const DEFAULT_VOICE_API = "Aoede";

export const PERSONAS = [
  {
    name: "עוזר כללי",
    instruction:
      "אתה עוזר קולי ידידותי שמדבר עברית בצורה טבעית וזורמת. " +
      "דבר בקצרה ולעניין, כמו בשיחה אמיתית. " +
      "אל תשתמש בסימני פיסוק מיוחדים או אימוג'ים בתשובות.",
  },
  {
    name: "מורה פרטי",
    instruction:
      "אתה מורה פרטי סבלני שמדבר עברית. הסבר נושאים בצורה ברורה " +
      "ומדורגת, תן דוגמאות, ושאל שאלות כדי לוודא שהבנתי. עודד אותי.",
  },
  {
    name: "מתרגם",
    instruction:
      "אתה מתרגם מקצועי. כשאני אומר משפט, תרגם אותו לשפה שאבקש " +
      "ואמור את התרגום בקול. אם לא ציינתי שפה, תרגם בין עברית לאנגלית.",
  },
  {
    name: "בן שיח לתרגול אנגלית",
    instruction:
      "You are a friendly English conversation partner. Speak in simple, " +
      "clear English. Gently correct my mistakes and keep the conversation " +
      "going with follow-up questions. Be encouraging.",
  },
  {
    name: "יועץ ענייני",
    instruction:
      "אתה יועץ חכם וישיר שמדבר עברית. תן תשובות מעשיות וממוקדות, " +
      "ללא מלל מיותר. אם חסר לך מידע, שאל שאלה ממוקדת אחת.",
  },
];
export const DEFAULT_INSTRUCTION = PERSONAS[0].instruction;

// ערכות צבע — שם עברי + accent hex (המרה ל-CSS, בלי תלות ב-qt-material)
export const THEMES = [
  { hebrew_name: "ציאן",   key: "cyan",   accent: "#26c6da" },
  { hebrew_name: "סגול",   key: "purple", accent: "#b388ff" },
  { hebrew_name: "טורקיז", key: "teal",   accent: "#1de9b6" },
  { hebrew_name: "ורוד",   key: "pink",   accent: "#ff80ab" },
  { hebrew_name: "כתום",   key: "amber",  accent: "#ffd54f" },
  { hebrew_name: "ירוק",   key: "green",  accent: "#b9f6ca" },
];
export const DEFAULT_THEME = "cyan";

export function getVoiceByApi(apiName) {
  return VOICES.find((v) => v.api_name === apiName) || VOICES[0];
}
export function getThemeByKey(key) {
  return THEMES.find((t) => t.key === key) || THEMES[0];
}

// ---------------------------------------------------------------------- //
// Settings — אותם שדות וברירות מחדל בדיוק כמו config.Settings.
// (שדות שאין להם משמעות בדפדפן — global_hotkey, wake_word, picovoice,
//  input/output device, computer_control-פתיחת-תוכנה — נשמרים כתאימות
//  אך לא באים לידי ביטוי ב-UI; ראו implementation-notes.md.)
// ---------------------------------------------------------------------- //
const SETTINGS_KEY = "gvc.settings";
const APIKEY_KEY = "gvc.apiKey";

export const DEFAULT_SETTINGS = {
  voice_api: DEFAULT_VOICE_API,
  system_instruction: DEFAULT_INSTRUCTION,
  theme: DEFAULT_THEME,
  color_mode: "dark", // "dark" | "light" | "system"
  web_search: false,
  deep_thinking: false,
  computer_control: false, // כלים: open_web / get_datetime / take_note בלבד
  echo_suppression: true, // echoCancellation ב-getUserMedia
  memory_enabled: true,
  affective_dialog: true,
  proactive_audio: false,
  thinking_level: "minimal",
  silence_duration_ms: 800,
  start_speech_sensitivity: "MEDIUM",
  end_speech_sensitivity: "MEDIUM",
  features_configured: false,
  model: "gemini-3.8-live",
};

export function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    const data = JSON.parse(raw);
    return { ...DEFAULT_SETTINGS, ...data };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function saveSettings(settings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    /* לא קריטי */
  }
}

export function loadApiKey() {
  try {
    return localStorage.getItem(APIKEY_KEY) || "";
  } catch {
    return "";
  }
}

export function saveApiKey(key) {
  try {
    if (key) localStorage.setItem(APIKEY_KEY, key);
    else localStorage.removeItem(APIKEY_KEY);
  } catch {
    /* לא קריטי */
  }
}

// ---------------------------------------------------------------------- //
// זיכרון בין שיחות — כמו knowledge.Memory
// ---------------------------------------------------------------------- //
const MEMORY_KEY = "gvc.memory";
const MAX_MEMORY_ENTRIES = 6;
const MAX_MEMORY_CHARS = 2500;

export const Memory = {
  load() {
    try {
      const raw = localStorage.getItem(MEMORY_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  },
  save(entries) {
    try {
      localStorage.setItem(
        MEMORY_KEY,
        JSON.stringify(entries.slice(-MAX_MEMORY_ENTRIES))
      );
    } catch {
      /* לא קריטי */
    }
  },
  addConversation(turns, timestamp) {
    const labels = { user: "משתמש", bot: "Gemini" };
    const lines = [];
    for (const [speaker, text] of turns) {
      if (labels[speaker]) lines.push(`${labels[speaker]}: ${text}`);
    }
    let text = lines.join("\n").trim();
    if (!text) return;
    if (text.length > MAX_MEMORY_CHARS) text = text.slice(0, MAX_MEMORY_CHARS) + "…";
    const entries = Memory.load();
    entries.push({ time: timestamp, text });
    Memory.save(entries);
  },
  clear() {
    Memory.save([]);
  },
  context() {
    const entries = Memory.load();
    if (!entries.length) return "";
    const parts = ["סיכום שיחות קודמות שלך עם המשתמש (לזיכרון והמשכיות):"];
    for (const e of entries) parts.push(`\n[${e.time || ""}]\n${e.text || ""}`);
    return parts.join("\n");
  },
};

// ---------------------------------------------------------------------- //
// בסיס ידע — כמו knowledge.KnowledgeBase
// ---------------------------------------------------------------------- //
const KB_KEY = "gvc.knowledge";
const MAX_KB_CHARS = 40000;

export const KnowledgeBase = {
  load() {
    try {
      const raw = localStorage.getItem(KB_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  },
  save(docs) {
    try {
      localStorage.setItem(KB_KEY, JSON.stringify(docs));
    } catch {
      /* לא קריטי */
    }
  },
  add(name, text) {
    let docs = KnowledgeBase.load().filter((d) => d.name !== name);
    docs.push({ name, text });
    KnowledgeBase.save(docs);
  },
  remove(name) {
    const docs = KnowledgeBase.load().filter((d) => d.name !== name);
    KnowledgeBase.save(docs);
  },
  context() {
    const docs = KnowledgeBase.load();
    if (!docs.length) return "";
    const parts = ["מסמכי ידע קבועים שאתה מכיר (ענה על שאלות לפיהם):"];
    let total = 0;
    for (const d of docs) {
      let chunk = `\n--- ${d.name || ""} ---\n${d.text || ""}`;
      if (total + chunk.length > MAX_KB_CHARS) chunk = chunk.slice(0, MAX_KB_CHARS - total) + "…";
      parts.push(chunk);
      total += chunk.length;
      if (total >= MAX_KB_CHARS) break;
    }
    return parts.join("\n");
  },
};
