// audio.js — שכבת Web Audio: לכידת מיקרופון (16kHz PCM16 דרך AudioWorklet)
// והשמעת פלט (24kHz PCM16, מתוזמן ברצף). שני הצדדים חושפים AnalyserNode
// לוויזואליזציה (הכדור הקולי).

// ---------------------------------------------------------------------- //
// עזרים כלליים ל-base64 <-> PCM16
// ---------------------------------------------------------------------- //
export function int16ToBase64(int16arr) {
  const bytes = new Uint8Array(int16arr.buffer, int16arr.byteOffset, int16arr.byteLength);
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

export function base64ToInt16(b64) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Int16Array(bytes.buffer);
}

// ---------------------------------------------------------------------- //
// MicCapture — getUserMedia + AudioWorklet, פולט chunk (Int16Array) כל 100ms
// ---------------------------------------------------------------------- //
export class MicCapture {
  constructor({ echoSuppression = true } = {}) {
    this.echoSuppression = echoSuppression;
    this.ctx = null;
    this.stream = null;
    this.sourceNode = null;
    this.workletNode = null;
    this.analyser = null;
    this._onChunk = null;
    this.muted = false;
  }

  onChunk(fn) {
    this._onChunk = fn;
  }

  // stream חיצוני אופציונלי (למשל טאב-אודיו לתרגום) — אם לא ניתן, נבקש מיקרופון
  async start(externalStream = null) {
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    await this.ctx.audioWorklet.addModule("worklets/mic-processor.js");

    this._ownedStream = !externalStream;
    if (externalStream) {
      this.stream = externalStream;
    } else {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: this.echoSuppression,
          noiseSuppression: this.echoSuppression,
          autoGainControl: this.echoSuppression,
        },
      });
    }

    this.sourceNode = this.ctx.createMediaStreamSource(this.stream);

    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 256;
    this.sourceNode.connect(this.analyser);

    this.workletNode = new AudioWorkletNode(this.ctx, "mic-processor");
    this.workletNode.port.onmessage = (e) => {
      if (e.data?.type === "chunk" && this._onChunk) this._onChunk(e.data.data);
    };
    this.sourceNode.connect(this.workletNode);

    if (this.ctx.state === "suspended") await this.ctx.resume();
  }

  setMuted(value) {
    this.muted = value;
    this.workletNode?.port.postMessage({ type: "mute", value });
  }

  // עוצמה נוכחית (0..1) מה-analyser — לוויזואליזציה
  getLevel() {
    if (!this.analyser) return 0;
    const data = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    return Math.sqrt(sum / data.length);
  }

  stop() {
    try {
      this.workletNode?.disconnect();
      this.sourceNode?.disconnect();
      this.analyser?.disconnect();
      // עוצרים רק טראקים שאנחנו פתחנו (לא stream חיצוני שמנוהל ע"י media.js)
      if (this._ownedStream) this.stream?.getTracks().forEach((t) => t.stop());
      this.ctx?.close();
    } catch {
      /* התעלמות מניקוי */
    }
  }
}

// ---------------------------------------------------------------------- //
// Player — משמיע רצף chunks PCM16 24kHz ברצף חלק (nextStartTime), עם flush
// ---------------------------------------------------------------------- //
export class Player {
  constructor() {
    this.ctx = null;
    this.analyser = null;
    this.nextStartTime = 0;
    this.activeSources = [];
    this._onLevel = null;
  }

  async ensureContext() {
    if (this.ctx) return;
    this.ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 256;
    this.analyser.connect(this.ctx.destination);
    this.nextStartTime = this.ctx.currentTime;
  }

  async resume() {
    await this.ensureContext();
    if (this.ctx.state === "suspended") await this.ctx.resume();
  }

  // int16arr: Int16Array בקצב 24000Hz mono
  playChunk(int16arr) {
    if (!this.ctx) return;
    const float32 = new Float32Array(int16arr.length);
    for (let i = 0; i < int16arr.length; i++) float32[i] = int16arr[i] / 32768;

    const buffer = this.ctx.createBuffer(1, float32.length, 24000);
    buffer.copyToChannel(float32, 0);

    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.analyser);

    const now = this.ctx.currentTime;
    const startAt = Math.max(this.nextStartTime, now);
    source.start(startAt);
    this.nextStartTime = startAt + buffer.duration;

    this.activeSources.push(source);
    source.onended = () => {
      this.activeSources = this.activeSources.filter((s) => s !== source);
    };
  }

  // barge-in / interrupted — מרוקן את תור הנגינה מיידית
  flush() {
    for (const s of this.activeSources) {
      try {
        s.stop();
      } catch {
        /* כבר הסתיים */
      }
    }
    this.activeSources = [];
    if (this.ctx) this.nextStartTime = this.ctx.currentTime;
  }

  getLevel() {
    if (!this.analyser) return 0;
    const data = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    return Math.sqrt(sum / data.length);
  }

  isSpeaking() {
    return this.activeSources.length > 0;
  }
}
