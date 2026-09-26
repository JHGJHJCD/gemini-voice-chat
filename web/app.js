// app.js — לב האפליקציה: מצב, UI, וחיבור בין GeminiLive לבין האודיו והמדיה.

import { GeminiLive, MODELS, DEFAULT_MODEL, TRANSLATE_INSTRUCTION } from "./live.js";
import { MicCapture, Player } from "./audio.js";
import { VideoCapture, captureTabAudio } from "./media.js";
import { FUNCTION_DECLARATIONS, executeTool } from "./tools.js";
import {
  VOICES,
  PERSONAS,
  THEMES,
  loadSettings,
  saveSettings,
  loadApiKey,
  saveApiKey,
  Memory,
  KnowledgeBase,
  getVoiceByApi,
} from "./storage.js";

// ====================================================================== //
// מצב גלובלי
// ====================================================================== //
const state = {
  settings: loadSettings(),
  apiKey: loadApiKey(),
  running: false,
  translateMode: false,
  muted: false,
  turns: [], // [[speaker, text]] לצורך שמירה בזיכרון
};

const live = new GeminiLive();
const mic = new MicCapture({ echoSuppression: state.settings.echo_suppression });
const player = new Player();
const video = new VideoCapture();

let micChunkTimer = null; // לא בשימוש כרגע — chunks מגיעים מה-worklet ישירות
let tabAudioMic = null; // MicCapture נפרד לאודיו-טאב במצב תרגום

// ====================================================================== //
// עזרים כלליים ל-DOM
// ====================================================================== //
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function applyTheme() {
  document.documentElement.setAttribute("data-theme", state.settings.theme);
  const mode = state.settings.color_mode;
  if (mode === "system") {
    document.documentElement.removeAttribute("data-mode");
  } else {
    document.documentElement.setAttribute("data-mode", mode);
  }
}

// ====================================================================== //
// Toast
// ====================================================================== //
function toast(message, kind = "info", timeoutMs = 5000) {
  const container = $("#toastContainer");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 220);
  }, timeoutMs);
}

// ====================================================================== //
// תמלול — בועות
// ====================================================================== //
let currentUserBubble = null;
let currentBotBubble = null;

function ensureTranscriptEmpty() {
  const t = $("#transcript");
  if (!t.children.length) {
    const empty = document.createElement("div");
    empty.className = "transcript-empty";
    empty.id = "transcriptEmpty";
    empty.textContent = "כשתתחילו לדבר, התמלול יופיע כאן";
    t.appendChild(empty);
  }
}

function clearTranscriptEmpty() {
  $("#transcriptEmpty")?.remove();
}

function scrollTranscript() {
  const t = $("#transcript");
  t.scrollTop = t.scrollHeight;
}

function addSystemBubble(text) {
  clearTranscriptEmpty();
  const el = document.createElement("div");
  el.className = "bubble system";
  el.textContent = text;
  $("#transcript").appendChild(el);
  scrollTranscript();
}

function updateBubble(kind, text, done) {
  clearTranscriptEmpty();
  const t = $("#transcript");
  let bubble = kind === "user" ? currentUserBubble : currentBotBubble;
  if (!bubble) {
    bubble = document.createElement("div");
    bubble.className = `bubble ${kind}`;
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = kind === "user" ? "אתם" : "Gemini";
    bubble.appendChild(who);
    const body = document.createElement("span");
    body.className = "body";
    bubble.appendChild(body);
    t.appendChild(bubble);
    if (kind === "user") currentUserBubble = bubble;
    else currentBotBubble = bubble;
  }
  bubble.querySelector(".body").textContent = text;
  scrollTranscript();
  if (done) {
    state.turns.push([kind === "user" ? "user" : "bot", text]);
    if (kind === "user") currentUserBubble = null;
    else currentBotBubble = null;
  }
}

$("#btnClearChat").addEventListener("click", () => {
  $("#transcript").innerHTML = "";
  currentUserBubble = null;
  currentBotBubble = null;
  ensureTranscriptEmpty();
});

// ====================================================================== //
// הכדור הקולי — canvas, מגיב לעוצמה, צבע/פועם לפי מצב
// ====================================================================== //
const orbCanvas = $("#orbCanvas");
const octx = orbCanvas.getContext("2d");
let orbState = "idle"; // idle | connecting | listening | speaking | translating
let orbLevel = 0;
let orbPhase = 0;

function setOrbState(s) {
  orbState = s;
  const captions = {
    idle: "לחצו התחל כדי לדבר",
    connecting: "מתחבר…",
    listening: "מקשיב…",
    speaking: "Gemini מדבר…",
    translating: "מתרגם…",
    reconnecting: "מתחבר מחדש…",
  };
  $("#orbCaption").textContent = captions[s] || "";
}

function accentRGB() {
  const cs = getComputedStyle(document.documentElement);
  return cs.getPropertyValue("--accent-rgb").trim() || "38,198,218";
}

function drawOrb() {
  const w = orbCanvas.width;
  const h = orbCanvas.height;
  octx.clearRect(0, 0, w, h);
  const cx = w / 2;
  const cy = h / 2;

  orbPhase += 0.018;

  // עוצמה חלקה (interpolation) כדי שלא יקפוץ
  let targetLevel = 0;
  if (orbState === "speaking" || orbState === "translating") targetLevel = player.getLevel();
  else if (orbState === "listening") targetLevel = mic.analyser ? mic.getLevel() : 0;
  orbLevel += (targetLevel - orbLevel) * 0.25;

  const baseR = w * 0.26;
  const pulse = Math.sin(orbPhase) * (w * 0.015);
  const levelBoost = Math.min(orbLevel * w * 0.28, w * 0.16);
  const r = baseR + pulse + levelBoost;

  const rgb = accentRGB();
  const isBusy = orbState === "connecting" || orbState === "reconnecting";

  // הילה חיצונית
  const glowR = r * (1.7 + orbLevel * 0.6);
  const glow = octx.createRadialGradient(cx, cy, r * 0.3, cx, cy, glowR);
  glow.addColorStop(0, `rgba(${rgb}, ${isBusy ? 0.28 : 0.4 + orbLevel * 0.3})`);
  glow.addColorStop(1, `rgba(${rgb}, 0)`);
  octx.fillStyle = glow;
  octx.beginPath();
  octx.arc(cx, cy, glowR, 0, Math.PI * 2);
  octx.fill();

  // גוף הכדור
  const bodyGrad = octx.createRadialGradient(cx - r * 0.3, cy - r * 0.3, r * 0.1, cx, cy, r);
  bodyGrad.addColorStop(0, `rgba(${rgb}, 0.95)`);
  bodyGrad.addColorStop(0.6, `rgba(${rgb}, 0.55)`);
  bodyGrad.addColorStop(1, `rgba(${rgb}, 0.12)`);
  octx.fillStyle = bodyGrad;
  octx.beginPath();
  octx.arc(cx, cy, r, 0, Math.PI * 2);
  octx.fill();

  // טבעות מסתובבות עדינות כשעסוק
  if (isBusy) {
    octx.strokeStyle = `rgba(${rgb}, 0.5)`;
    octx.lineWidth = 3;
    octx.beginPath();
    octx.arc(cx, cy, r * 1.25, orbPhase * 2, orbPhase * 2 + Math.PI * 1.2);
    octx.stroke();
  }

  requestAnimationFrame(drawOrb);
}
requestAnimationFrame(drawOrb);

// ====================================================================== //
// פס סטטוס עליון
// ====================================================================== //
function setConnDot(kind) {
  const dot = $("#connDot");
  dot.className = "dot" + (kind ? ` ${kind}` : "");
}

function setStatusText(text) {
  $("#statusText").textContent = text;
}

// ====================================================================== //
// חיבור GeminiLive → UI
// ====================================================================== //
live.on("status", (status) => {
  switch (status) {
    case "connecting":
      setOrbState("connecting");
      setConnDot("busy");
      setStatusText("מתחבר…");
      break;
    case "reconnecting":
      setOrbState("reconnecting");
      setConnDot("busy");
      setStatusText("מתחבר מחדש…");
      break;
    case "listening":
      setOrbState(state.translateMode ? "translating" : "listening");
      setConnDot("live");
      setStatusText(state.translateMode ? "מתרגם בשידור חי" : "מחובר");
      break;
    case "idle":
      setOrbState("idle");
      setConnDot("");
      setStatusText("מוכן");
      break;
  }
});

live.on("modelChanged", (modelId, label) => {
  $("#modelBadge").textContent = label || modelId;
});

live.on("userText", (text, done) => updateBubble("user", text, done));
live.on("botText", (text, done) => updateBubble("bot", text, done));

live.on("audio", (int16arr) => {
  player.playChunk(int16arr);
  setOrbState(state.translateMode ? "translating" : "speaking");
});

live.on("interrupted", () => {
  player.flush();
  if (live.isConnected()) setOrbState(state.translateMode ? "translating" : "listening");
});

live.on("toolCall", async (calls) => {
  for (const call of calls) {
    const result = executeTool(call.name, call.args || {});
    live.sendToolResponse(call.id, call.name, result);
    addSystemBubble(`🔧 ${call.name}: ${result}`);
  }
});

live.on("error", (message) => {
  toast(message, "error", 7000);
  stopConversation(true);
});

// ====================================================================== //
// בניית system instruction (הנחיה + זיכרון + בסיס ידע) — כמו voice_app.py
// ====================================================================== //
function buildInstruction() {
  let instruction = state.settings.system_instruction;
  const extras = [];
  if (state.settings.memory_enabled) {
    const mem = Memory.context();
    if (mem) extras.push(mem);
  }
  const kb = KnowledgeBase.context();
  if (kb) extras.push(kb);
  if (extras.length) instruction = instruction + "\n\n" + extras.join("\n\n");
  return instruction;
}

// ====================================================================== //
// התחלה / עצירה של שיחה
// ====================================================================== //
async function startConversation(translate = false) {
  if (!state.apiKey) {
    toast("צריך קודם להזין מפתח API בהגדרות.", "error");
    openSettings();
    return;
  }

  state.translateMode = translate;
  state.turns = [];
  $("#transcript").innerHTML = "";
  currentUserBubble = null;
  currentBotBubble = null;

  try {
    if (translate) {
      const tabStream = await captureTabAudio();
      tabAudioMic = new MicCapture({ echoSuppression: false });
      tabAudioMic.onChunk((chunk) => live.sendAudio(chunk));
      await tabAudioMic.start(tabStream);
    } else {
      await mic.start();
      mic.onChunk((chunk) => {
        if (!state.muted) live.sendAudio(chunk);
      });
    }
    await player.resume();
  } catch (e) {
    if (e?.message === "NO_TAB_AUDIO") {
      toast('לא נבחר אודיו של הטאב — בחלון השיתוף יש לסמן "שתף אודיו של הטאב".', "error", 8000);
    } else if (e?.name === "NotAllowedError") {
      toast("הגישה למיקרופון/למסך נדחתה. אפשר לאשר בהגדרות הדפדפן.", "error");
    } else {
      toast("לא הצלחתי לפתוח את המיקרופון/השיתוף: " + (e?.message || e), "error");
    }
    return;
  }

  state.running = true;
  $("#btnTalk").setAttribute("aria-pressed", "true");
  $("#btnTalk").querySelector(".talk-btn-label").textContent = translate ? "עצירת תרגום" : "עצירת שיחה";

  await live.connect({
    apiKey: state.apiKey,
    mode: translate ? "translate" : "conversation",
    model: state.settings.model || DEFAULT_MODEL,
    voiceApi: state.settings.voice_api,
    systemInstruction: translate ? TRANSLATE_INSTRUCTION : buildInstruction(),
    webSearch: state.settings.web_search,
    computerControl: state.settings.computer_control,
    functionDeclarations: FUNCTION_DECLARATIONS,
    deepThinking: state.settings.deep_thinking,
    affectiveDialog: state.settings.affective_dialog,
    proactiveAudio: state.settings.proactive_audio,
    thinkingLevel: state.settings.thinking_level,
    silenceDurationMs: state.settings.silence_duration_ms,
    startSensitivity: state.settings.start_speech_sensitivity,
    endSensitivity: state.settings.end_speech_sensitivity,
  });
}

function stopConversation(fromError = false) {
  live.disconnect();
  mic.stop();
  if (tabAudioMic) {
    tabAudioMic.stop();
    tabAudioMic = null;
  }
  player.flush();
  video.stop();
  $("#btnScreen").setAttribute("aria-pressed", "false");
  $("#btnCamera").setAttribute("aria-pressed", "false");

  // שמירת השיחה לזיכרון
  if (state.turns.length && state.settings.memory_enabled && !state.translateMode) {
    Memory.addConversation(state.turns, new Date().toLocaleString("he-IL"));
  }

  state.running = false;
  state.translateMode = false;
  $("#btnTalk").setAttribute("aria-pressed", "false");
  $("#btnTalk").querySelector(".talk-btn-label").textContent = "התחל שיחה";
  setOrbState("idle");
  if (!fromError) {
    setConnDot("");
    setStatusText("מוכן");
  }
  ensureTranscriptEmpty();
}

$("#btnTalk").addEventListener("click", () => {
  if (state.running) stopConversation();
  else startConversation(false);
});

$("#btnTranslate").addEventListener("click", () => {
  if (state.running && state.translateMode) {
    stopConversation();
    return;
  }
  if (state.running) stopConversation();
  $("#btnTranslate").setAttribute("aria-pressed", "true");
  startConversation(true).finally(() => {
    if (!state.running) $("#btnTranslate").setAttribute("aria-pressed", "false");
  });
});

$("#btnMute").addEventListener("click", () => {
  state.muted = !state.muted;
  mic.setMuted(state.muted);
  $("#btnMute").setAttribute("aria-pressed", String(state.muted));
});

// ------------------------------------------------------------------ //
// שיתוף מסך / מצלמה
// ------------------------------------------------------------------ //
$("#btnScreen").addEventListener("click", async () => {
  if (video.isActive() && video.kind === "screen") {
    video.stop();
    $("#btnScreen").setAttribute("aria-pressed", "false");
    return;
  }
  try {
    video.stop();
    $("#btnCamera").setAttribute("aria-pressed", "false");
    video.onFrame((b64) => live.sendVideoFrame(b64));
    await video.startScreen();
    $("#btnScreen").setAttribute("aria-pressed", "true");
  } catch (e) {
    toast("שיתוף המסך בוטל או נכשל.", "error");
  }
});

$("#btnCamera").addEventListener("click", async () => {
  if (video.isActive() && video.kind === "camera") {
    video.stop();
    $("#btnCamera").setAttribute("aria-pressed", "false");
    return;
  }
  try {
    video.stop();
    $("#btnScreen").setAttribute("aria-pressed", "false");
    video.onFrame((b64) => live.sendVideoFrame(b64));
    await video.startCamera();
    $("#btnCamera").setAttribute("aria-pressed", "true");
  } catch (e) {
    toast("הגישה למצלמה נדחתה או נכשלה.", "error");
  }
});

// ====================================================================== //
// הגדרות — מילוי הטאבים
// ====================================================================== //
function populateSelect(sel, items, valueKey, labelFn) {
  sel.innerHTML = "";
  for (const item of items) {
    const opt = document.createElement("option");
    opt.value = item[valueKey];
    opt.textContent = labelFn(item);
    sel.appendChild(opt);
  }
}

function fillSettingsForm() {
  const s = state.settings;
  $("#apiKeyInput").value = state.apiKey;

  populateSelect($("#modelSelect"), Object.keys(MODELS).map((k) => ({ id: k })), "id", (i) => MODELS[i.id]);
  $("#modelSelect").value = s.model;

  populateSelect($("#voiceSelect"), VOICES, "api_name", (v) => `${v.hebrew_name} — ${v.description}`);
  $("#voiceSelect").value = s.voice_api;
  $("#voiceDesc").textContent = getVoiceByApi(s.voice_api).description;

  populateSelect($("#personaSelect"), PERSONAS, "name", (p) => p.name);
  // בוחרים פרסונה תואמת אם ההנחיה זהה לאחת המוכרות, אחרת משאירים "מותאם אישית"
  const matched = PERSONAS.find((p) => p.instruction === s.system_instruction);
  if (!matched) {
    const opt = document.createElement("option");
    opt.value = "__custom__";
    opt.textContent = "מותאם אישית";
    $("#personaSelect").appendChild(opt);
    $("#personaSelect").value = "__custom__";
  } else {
    $("#personaSelect").value = matched.name;
  }
  $("#instructionText").value = s.system_instruction;

  $("#startSensitivity").value = s.start_speech_sensitivity;
  $("#endSensitivity").value = s.end_speech_sensitivity;
  $("#silenceRange").value = s.silence_duration_ms;
  $("#silenceVal").textContent = s.silence_duration_ms;
  $("#echoSuppression").checked = s.echo_suppression;

  $("#webSearch").checked = s.web_search;
  $("#computerControl").checked = s.computer_control;
  $("#deepThinking").checked = s.deep_thinking;
  $("#thinkingLevel").value = s.thinking_level;
  $("#affectiveDialog").checked = s.affective_dialog;
  $("#proactiveAudio").checked = s.proactive_audio;

  $("#memoryEnabled").checked = s.memory_enabled;
  renderKbList();

  renderThemeSwatches();
  $("#colorModeSelect").value = s.color_mode;
}

function renderThemeSwatches() {
  const wrap = $("#themeSwatches");
  wrap.innerHTML = "";
  for (const theme of THEMES) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "swatch" + (theme.key === state.settings.theme ? " active" : "");
    btn.style.background = theme.accent;
    btn.title = theme.hebrew_name;
    btn.addEventListener("click", () => {
      state.settings.theme = theme.key;
      applyTheme();
      renderThemeSwatches();
    });
    wrap.appendChild(btn);
  }
}

function renderKbList() {
  const list = $("#kbList");
  list.innerHTML = "";
  const docs = KnowledgeBase.load();
  if (!docs.length) {
    const li = document.createElement("li");
    li.textContent = "אין מסמכים בבסיס הידע";
    li.style.color = "var(--text-3)";
    list.appendChild(li);
    return;
  }
  for (const d of docs) {
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.textContent = d.name;
    const btn = document.createElement("button");
    btn.textContent = "מחיקה";
    btn.addEventListener("click", () => {
      KnowledgeBase.remove(d.name);
      renderKbList();
    });
    li.appendChild(span);
    li.appendChild(btn);
    list.appendChild(li);
  }
}

function saveSettingsForm() {
  const s = state.settings;
  s.model = $("#modelSelect").value;
  s.voice_api = $("#voiceSelect").value;
  s.system_instruction = $("#instructionText").value;
  s.start_speech_sensitivity = $("#startSensitivity").value;
  s.end_speech_sensitivity = $("#endSensitivity").value;
  s.silence_duration_ms = parseInt($("#silenceRange").value, 10);
  s.echo_suppression = $("#echoSuppression").checked;
  s.web_search = $("#webSearch").checked;
  s.computer_control = $("#computerControl").checked;
  s.deep_thinking = $("#deepThinking").checked;
  s.thinking_level = $("#thinkingLevel").value;
  s.affective_dialog = $("#affectiveDialog").checked;
  s.proactive_audio = $("#proactiveAudio").checked;
  s.memory_enabled = $("#memoryEnabled").checked;
  s.color_mode = $("#colorModeSelect").value;

  saveSettings(s);
  state.apiKey = $("#apiKeyInput").value.trim();
  saveApiKey(state.apiKey);
  applyTheme();
}

$("#personaSelect").addEventListener("change", (e) => {
  const p = PERSONAS.find((p) => p.name === e.target.value);
  if (p) $("#instructionText").value = p.instruction;
});
$("#voiceSelect").addEventListener("change", (e) => {
  $("#voiceDesc").textContent = getVoiceByApi(e.target.value).description;
});
$("#silenceRange").addEventListener("input", (e) => {
  $("#silenceVal").textContent = e.target.value;
});
$("#btnToggleKey").addEventListener("click", () => {
  const input = $("#apiKeyInput");
  input.type = input.type === "password" ? "text" : "password";
  $("#btnToggleKey").textContent = input.type === "password" ? "הצג" : "הסתר";
});
$("#btnClearMemory").addEventListener("click", () => {
  Memory.clear();
  toast("הזיכרון נוקה.", "info", 3000);
});
$("#colorModeSelect").addEventListener("change", (e) => {
  state.settings.color_mode = e.target.value;
  applyTheme();
});

// טעינת קובץ לבסיס הידע — txt ישירות, pdf דרך pdf.js (נטען לפי דרישה)
let pdfjsLoaded = false;
async function ensurePdfJs() {
  if (pdfjsLoaded) return window.pdfjsLib;
  const mod = await import("https://cdn.jsdelivr.net/npm/pdfjs-dist@4/build/pdf.min.mjs");
  mod.GlobalWorkerOptions.workerSrc = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4/build/pdf.worker.min.mjs";
  window.pdfjsLib = mod;
  pdfjsLoaded = true;
  return mod;
}

$("#kbFile").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
      const pdfjsLib = await ensurePdfJs();
      const buf = await file.arrayBuffer();
      const doc = await pdfjsLib.getDocument({ data: buf }).promise;
      let text = "";
      for (let i = 1; i <= doc.numPages; i++) {
        const page = await doc.getPage(i);
        const content = await page.getTextContent();
        text += content.items.map((it) => it.str).join(" ") + "\n";
      }
      KnowledgeBase.add(file.name, text);
    } else {
      const text = await file.text();
      KnowledgeBase.add(file.name, text);
    }
    renderKbList();
    toast(`"${file.name}" נוסף לבסיס הידע.`, "info", 3000);
  } catch (err) {
    toast("קריאת הקובץ נכשלה: " + (err?.message || err), "error");
  } finally {
    e.target.value = "";
  }
});

// ------------------------------------------------------------------ //
// טאבים
// ------------------------------------------------------------------ //
$$(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".tab").forEach((t) => t.classList.remove("active"));
    $$(".tab-panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    $(`.tab-panel[data-panel="${tab.dataset.tab}"]`).classList.add("active");
  });
});

// ------------------------------------------------------------------ //
// פתיחה/סגירה של דיאלוג הגדרות
// ------------------------------------------------------------------ //
function openSettings() {
  fillSettingsForm();
  $("#settingsDialog").showModal();
}
$("#btnSettings").addEventListener("click", openSettings);
$("#settingsDialog").addEventListener("close", saveSettingsForm);
$("#btnSaveSettings").addEventListener("click", saveSettingsForm);

$("#btnColorMode").addEventListener("click", () => {
  const cur = state.settings.color_mode;
  state.settings.color_mode = cur === "dark" ? "light" : "dark";
  saveSettings(state.settings);
  applyTheme();
});

// ====================================================================== //
// אשף ראשוני
// ====================================================================== //
let wizardStep = 1;
const WIZARD_STEPS = 3;

function showWizardStep(n) {
  wizardStep = n;
  $$(".wizard-page").forEach((p) => p.classList.toggle("active", parseInt(p.dataset.step) === n));
  $$("#wizardSteps .step-dot").forEach((d, i) => d.classList.toggle("active", i === n - 1));
  $("#wizardBack").disabled = n === 1;
  $("#wizardNext").hidden = n === WIZARD_STEPS;
  $("#wizardFinish").hidden = n !== WIZARD_STEPS;
}

function initWizardFields() {
  populateSelect($("#wizardVoice"), VOICES, "api_name", (v) => `${v.hebrew_name} — ${v.description}`);
  $("#wizardVoice").value = state.settings.voice_api;
  populateSelect($("#wizardPersona"), PERSONAS, "name", (p) => p.name);
  $("#wizardPersona").value = PERSONAS[0].name;
}

$("#wizardNext").addEventListener("click", () => {
  if (wizardStep === 1) {
    const key = $("#wizardApiKey").value.trim();
    if (!key) {
      toast("צריך להזין מפתח API כדי להמשיך.", "error");
      return;
    }
    state.apiKey = key;
    saveApiKey(key);
  }
  if (wizardStep < WIZARD_STEPS) showWizardStep(wizardStep + 1);
});
$("#wizardBack").addEventListener("click", () => {
  if (wizardStep > 1) showWizardStep(wizardStep - 1);
});
$("#wizardFinish").addEventListener("click", () => {
  const voice = $("#wizardVoice").value;
  const personaName = $("#wizardPersona").value;
  const persona = PERSONAS.find((p) => p.name === personaName) || PERSONAS[0];
  state.settings.voice_api = voice;
  state.settings.system_instruction = persona.instruction;
  state.settings.features_configured = true;
  saveSettings(state.settings);
  $("#wizardDialog").close();
  toast("מוכנים! לחצו על הכפתור הגדול כדי להתחיל לדבר.", "info", 6000);
});

function maybeShowWizard() {
  if (!state.settings.features_configured || !state.apiKey) {
    initWizardFields();
    showWizardStep(1);
    $("#wizardApiKey").value = state.apiKey || "";
    $("#wizardDialog").showModal();
  }
}

// ====================================================================== //
// אתחול
// ====================================================================== //
applyTheme();
$("#modelBadge").textContent = MODELS[state.settings.model] || MODELS[DEFAULT_MODEL];
ensureTranscriptEmpty();
maybeShowWizard();

// רישום Service Worker (PWA)
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").catch(() => {
      /* לא קריטי אם נכשל (למשל ב-file://) */
    });
  });
}
