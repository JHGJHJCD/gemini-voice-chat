// live.js — מחלקת GeminiLive: כל התקשורת מול Gemini Live דרך WebSocket גולמי.
// תואם 1:1 את הפרוטוקול והלוגיקה של voice_engine.py (ראו web/PLAN.md).
// אין תלות ב-UI — משדר אירועים בלבד (event-emitter style).

import { int16ToBase64, base64ToInt16 } from "./audio.js";

// מודלי שיחה (Live API). הראשון = ברירת מחדל. סדר = שרשרת נפילה.
export const MODELS = {
  "gemini-3.8-live": "Gemini 3.8 Live — מהיר וטבעי (מומלץ)",
  "gemini-3.8-live-extended-thinking": "Gemini 3.8 Live — חשיבה מורחבת (מדויק, איטי יותר)",
  "gemini-2.5-flash-native-audio-preview-12-2025": "Gemini 2.5 (הדור הקודם)",
};
export const DEFAULT_MODEL = "gemini-3.8-live";
export const MODEL_FALLBACK_CHAIN = Object.keys(MODELS);

export const TRANSLATE_MODEL = "gemini-3.5-live-translate-preview";
export const TRANSLATE_TARGET = "he";

export const TRANSLATE_INSTRUCTION =
  "אתה מנוע תרגום בלבד - לא עוזר ולא בן שיח. " +
  "תפקידך היחיד: לתרגם לעברית את מה שנאמר בשפה זרה (אנגלית או אחרת) " +
  "ולומר בקול רק את התרגום. " +
  "אסור לך בשום אופן: לשאול שאלות, להציע עזרה, להסביר מילים, " +
  "להוסיף הערות, או לנהל שיחה. אתה אך ורק מתרגם. " +
  "אם אתה שומע דיבור בעברית - התעלם ממנו לחלוטין, אל תתרגם ואל תחזור עליו, " +
  "זה הקול שלך עצמך. " +
  "אם אתה לא בטוח מה נאמר, או שאתה שומע שקט/מוזיקה/רעש בלבד - שתוק לגמרי. " +
  "תרגם ברצף תוך כדי הדיבור.";

const MAX_RECONNECT = 5;

export class GeminiLive {
  constructor() {
    this._listeners = {};
    this.ws = null;
    this.setupDone = false;
    this.manualDisconnect = false;
    this.toolsDisabled = false;
    this.resumeHandle = null;
    this.reconnectAttempts = 0;
    this.activeModel = null;
    this.mode = "conversation"; // "conversation" | "translate"
    this.opts = null;
    this._userTextBuf = "";
    this._botTextBuf = "";
    this._chain = [];
    this._chainIndex = 0;
    this._pendingAudioQueue = []; // אודיו שנצבר לפני setupComplete
  }

  on(event, fn) {
    (this._listeners[event] ||= []).push(fn);
    return this;
  }

  _emit(event, ...args) {
    (this._listeners[event] || []).forEach((fn) => {
      try {
        fn(...args);
      } catch (e) {
        console.error(`[GeminiLive] listener error on ${event}:`, e);
      }
    });
  }

  // opts: { apiKey, mode, model, voiceApi, systemInstruction, webSearch,
  //         computerControl, affectiveDialog, proactiveAudio, thinkingLevel,
  //         silenceDurationMs, startSensitivity, endSensitivity }
  async connect(opts) {
    this.opts = opts;
    this.mode = opts.mode || "conversation";
    this.manualDisconnect = false;
    this.toolsDisabled = false;
    this.reconnectAttempts = 0;

    if (this.mode === "translate") {
      this._chain = [TRANSLATE_MODEL];
    } else {
      const chosen = opts.model || DEFAULT_MODEL;
      this._chain = [chosen, ...MODEL_FALLBACK_CHAIN.filter((m) => m !== chosen)];
    }
    this._chainIndex = 0;
    this._connectCurrent();
  }

  _connectCurrent() {
    const model = this._chain[this._chainIndex];
    this.activeModel = model;
    const { url, setup } = this._buildSetup(model);

    this._emit("status", "connecting");
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      this._emit("error", "לא הצלחתי לפתוח חיבור לרשת.");
      return;
    }
    this.ws = ws;
    this.setupDone = false;
    ws.binaryType = "blob";

    ws.onopen = () => {
      ws.send(JSON.stringify({ setup }));
    };

    ws.onmessage = async (evt) => {
      let text;
      if (evt.data instanceof Blob) {
        text = await evt.data.text();
      } else {
        text = evt.data;
      }
      let msg;
      try {
        msg = JSON.parse(text);
      } catch {
        return;
      }
      this._handleMessage(msg);
    };

    ws.onerror = () => {
      // onclose תמיד נורה אחרי onerror ב-WebSocket, מטפלים שם
    };

    ws.onclose = (evt) => {
      this._handleClose(evt);
    };
  }

  _buildSetup(model) {
    const isLegacy = model.startsWith("gemini-2.5");
    const isExtended = model.includes("extended-thinking");
    const useV1Alpha =
      isLegacy && (this.opts.affectiveDialog || this.opts.proactiveAudio);
    const apiVersion = useV1Alpha ? "v1alpha" : "v1beta";
    const url =
      `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.` +
      `${apiVersion}.GenerativeService.BidiGenerateContent?key=${encodeURIComponent(this.opts.apiKey)}`;

    if (this.mode === "translate") {
      const setup = {
        model: `models/${model}`,
        generationConfig: { responseModalities: ["AUDIO"] },
        outputAudioTranscription: {},
        translationConfig: {
          targetLanguageCode: TRANSLATE_TARGET,
          echoTargetLanguage: true,
        },
      };
      return { url, setup };
    }

    const generationConfig = {
      responseModalities: ["AUDIO"],
      speechConfig: {
        voiceConfig: { prebuiltVoiceConfig: { voiceName: this.opts.voiceApi } },
      },
    };

    // חשיבה — תלוי מודל (ראה voice_engine._build_conversation_setup)
    if (this.opts.deepThinking && isLegacy) {
      const budgetMap = { minimal: 512, low: 1024, medium: 2048, high: 4096 };
      generationConfig.thinkingConfig = {
        thinkingBudget: budgetMap[this.opts.thinkingLevel] ?? 2048,
      };
    } else if (isExtended) {
      const levelMap = { minimal: "LOW", low: "LOW", medium: "MEDIUM", high: "HIGH" };
      generationConfig.thinkingConfig = {
        thinkingLevel: levelMap[this.opts.thinkingLevel] ?? "MEDIUM",
      };
    }
    // 3.8 בסיסי: חשיבה מובנית, לא שולחים thinkingConfig בכלל.

    const setup = {
      model: `models/${model}`,
      generationConfig,
      systemInstruction: { parts: [{ text: this.opts.systemInstruction || "" }] },
      inputAudioTranscription: {},
      outputAudioTranscription: {},
    };

    // VAD — רגישות MEDIUM = ברירת מחדל השרת, לא שולחים בכלל
    const vad = {
      prefixPaddingMs: 20,
      silenceDurationMs: this.opts.silenceDurationMs ?? 800,
    };
    if (this.opts.startSensitivity === "LOW" || this.opts.startSensitivity === "HIGH") {
      vad.startOfSpeechSensitivity = `START_SENSITIVITY_${this.opts.startSensitivity}`;
    }
    if (this.opts.endSensitivity === "LOW" || this.opts.endSensitivity === "HIGH") {
      vad.endOfSpeechSensitivity = `END_SENSITIVITY_${this.opts.endSensitivity}`;
    }
    setup.realtimeInputConfig = { automaticActivityDetection: vad };

    if (this.opts.affectiveDialog) setup.enableAffectiveDialog = true;
    if (this.opts.proactiveAudio) setup.proactivity = { proactiveAudio: true };

    // כלים — מדולגים לגמרי אם נדחו ע"י המודל (retry-without-tools)
    if (!this.toolsDisabled) {
      const tools = [];
      if (this.opts.webSearch) tools.push({ googleSearch: {} });
      if (this.opts.computerControl && this.opts.functionDeclarations?.length) {
        tools.push({ functionDeclarations: this.opts.functionDeclarations });
      }
      if (tools.length) setup.tools = tools;
    }

    setup.contextWindowCompression = { slidingWindow: {} };
    if (this.resumeHandle) setup.sessionResumption = { handle: this.resumeHandle };
    else setup.sessionResumption = {};

    return { url, setup };
  }

  _handleMessage(msg) {
    if (msg.setupComplete !== undefined) {
      this.setupDone = true;
      this.reconnectAttempts = 0;
      this._emit("modelChanged", this.activeModel, MODELS[this.activeModel] || this.activeModel);
      this._emit("status", "listening");
      // שולחים אודיו שהצטבר בזמן ההמתנה ל-setupComplete
      for (const chunk of this._pendingAudioQueue) this._sendRaw(chunk);
      this._pendingAudioQueue = [];
      return;
    }

    if (msg.serverContent) {
      const sc = msg.serverContent;
      if (sc.interrupted) {
        this._emit("interrupted");
      }
      if (sc.modelTurn?.parts) {
        for (const part of sc.modelTurn.parts) {
          if (part.inlineData?.data) {
            const pcm = base64ToInt16(part.inlineData.data);
            this._emit("audio", pcm);
          }
        }
      }
      if (sc.inputTranscription?.text) {
        this._userTextBuf += sc.inputTranscription.text;
        this._emit("userText", this._userTextBuf, false);
      }
      if (sc.outputTranscription?.text) {
        this._botTextBuf += sc.outputTranscription.text;
        this._emit("botText", this._botTextBuf, false);
      }
      if (sc.turnComplete) {
        if (this._userTextBuf) this._emit("userText", this._userTextBuf, true);
        if (this._botTextBuf) this._emit("botText", this._botTextBuf, true);
        this._userTextBuf = "";
        this._botTextBuf = "";
      }
      return;
    }

    if (msg.sessionResumptionUpdate) {
      const upd = msg.sessionResumptionUpdate;
      if (upd.resumable && upd.newHandle) this.resumeHandle = upd.newHandle;
      return;
    }

    if (msg.goAway) {
      // ניתוק יזום מהשרת — מתחברים מחדש עם ה-handle השמור, בלי לבזבז ניסיון backoff
      this._emit("status", "reconnecting");
      this.manualDisconnect = false;
      try {
        this.ws?.close();
      } catch {
        /* ignore */
      }
      return;
    }

    if (msg.toolCall?.functionCalls) {
      this._emit("toolCall", msg.toolCall.functionCalls);
      return;
    }
  }

  _classifyText(text) {
    const low = (text || "").toLowerCase();
    if (low.includes("ssl") || low.includes("certificate")) return "ssl";
    if (low.includes("expired")) return "expired";
    if (
      low.includes("api key") ||
      low.includes("api_key_invalid") ||
      low.includes("403") ||
      low.includes("401") ||
      low.includes("permission_denied") ||
      low.includes("unauthenticated")
    )
      return "api_key";
    if (
      (low.includes("tool") || low.includes("google_search") || low.includes("function")) &&
      (low.includes("not supported") || low.includes("invalid") || low.includes("unsupported") || low.includes("400"))
    )
      return "tools_unsupported";
    if (
      low.includes("not_found") ||
      low.includes("not found") ||
      low.includes("404") ||
      low.includes("does not exist") ||
      low.includes("is not supported") ||
      low.includes("was not found") ||
      low.includes("not available")
    )
      return "model_unavailable";
    return "transient";
  }

  _handleClose(evt) {
    if (this.manualDisconnect) {
      this._emit("status", "idle");
      return;
    }

    const reasonText = `${evt.code || ""} ${evt.reason || ""}`.trim();
    const kind = this.setupDone ? this._classifyText(reasonText) : this._classifyText(reasonText) || "model_unavailable";

    if (kind === "ssl") {
      this._emit("error", "בעיית אבטחה (SSL) בחיבור לרשת.");
      return;
    }
    if (kind === "expired") {
      this._emit(
        "error",
        "מפתח ה-API פג תוקף. צור מפתח חדש ב-aistudio.google.com/apikey והזן אותו בהגדרות."
      );
      return;
    }
    if (kind === "api_key") {
      this._emit("error", "מפתח API לא תקין.");
      return;
    }

    if (kind === "tools_unsupported" && !this.setupDone) {
      if (this.toolsDisabled) {
        this._emit("error", "המודל דחה את הגדרות השיחה.");
        return;
      }
      this.toolsDisabled = true;
      this._emit("botText", "[הכלים (חיפוש/שליטה במחשב) לא נתמכים במודל הזה - ממשיך בלעדיהם] ", true);
      this._connectCurrent();
      return;
    }

    if (kind === "model_unavailable" && !this.setupDone) {
      if (this._chainIndex + 1 >= this._chain.length) {
        this._emit(
          "error",
          this.mode === "translate"
            ? "מודל התרגום אינו זמין כרגע - ייתכן ש-Google עדכנה אותו."
            : "אף מודל שיחה אינו זמין כרגע - ייתכן ש-Google עדכנה אותם."
        );
        return;
      }
      const prevModel = this._chain[this._chainIndex];
      this._chainIndex += 1;
      const nextModel = this._chain[this._chainIndex];
      this._emit(
        "botText",
        `[המודל ${MODELS[prevModel] || prevModel} לא זמין כרגע - עובר ל-${MODELS[nextModel] || nextModel}] `,
        true
      );
      this._connectCurrent();
      return;
    }

    // שגיאה זמנית — reconnect עם backoff
    this.reconnectAttempts += 1;
    if (this.reconnectAttempts > MAX_RECONNECT) {
      this._emit("error", "החיבור נכשל שוב ושוב. נסה להתחיל שיחה מחדש.");
      return;
    }
    this._emit("status", "reconnecting");
    const delayMs = Math.min(2000 * this.reconnectAttempts, 8000);
    setTimeout(() => {
      if (!this.manualDisconnect) this._connectCurrent();
    }, delayMs);
  }

  _sendRaw(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
    }
  }

  sendAudio(int16Array) {
    const msg = {
      realtimeInput: {
        audio: { data: int16ToBase64(int16Array), mimeType: "audio/pcm;rate=16000" },
      },
    };
    if (!this.setupDone) {
      // צוברים זמנית — לא שולחים לפני setupComplete
      if (this._pendingAudioQueue.length < 20) this._pendingAudioQueue.push(msg);
      return;
    }
    this._sendRaw(msg);
  }

  sendVideoFrame(base64Jpeg) {
    if (!this.setupDone) return;
    this._sendRaw({
      realtimeInput: { video: { data: base64Jpeg, mimeType: "image/jpeg" } },
    });
  }

  sendText(str) {
    if (!this.setupDone) return;
    this._sendRaw({
      clientContent: { turns: [{ role: "user", parts: [{ text: str }] }], turnComplete: true },
    });
  }

  sendToolResponse(id, name, result) {
    this._sendRaw({
      toolResponse: { functionResponses: [{ id, name, response: { result } }] },
    });
  }

  disconnect() {
    this.manualDisconnect = true;
    try {
      this.ws?.close();
    } catch {
      /* ignore */
    }
    this.ws = null;
    this.setupDone = false;
  }

  isConnected() {
    return !!this.ws && this.ws.readyState === WebSocket.OPEN && this.setupDone;
  }
}
