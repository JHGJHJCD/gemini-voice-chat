// mic-processor.js — AudioWorklet שרץ בתהליכון אודיו נפרד מה-UI.
// מקבל אודיו בקצב הדגימה המקורי של המכשיר (בד"כ 48kHz), מבצע דגימה-מחדש
// (resample) ליניארית ל-16kHz mono, וממיר ל-PCM16. שולח בלוקים של 1600
// דגימות (100ms ב-16kHz) חזרה ל-thread הראשי דרך postMessage.

class MicProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = 16000;
    this.inputRate = sampleRate; // global בתוך AudioWorkletGlobalScope
    this.ratio = this.inputRate / this.targetRate;
    this.buffer = []; // דגימות float שממתינות ל-resample
    this.outChunk = new Int16Array(1600);
    this.outPos = 0;
    this.muted = false;

    this.port.onmessage = (e) => {
      if (e.data && e.data.type === "mute") this.muted = e.data.value;
    };
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const channel = input[0];

    if (this.muted) return true;

    // צבירה ל-buffer של float, ואז resample ליניארי ל-16kHz
    for (let i = 0; i < channel.length; i++) {
      this.buffer.push(channel[i]);
    }

    // כמה דגימות פלט (16kHz) אפשר להפיק מה-buffer שיש כרגע
    const available = Math.floor(this.buffer.length / this.ratio);
    for (let i = 0; i < available; i++) {
      const srcIndex = i * this.ratio;
      const idx0 = Math.floor(srcIndex);
      const idx1 = Math.min(idx0 + 1, this.buffer.length - 1);
      const frac = srcIndex - idx0;
      const sample = this.buffer[idx0] * (1 - frac) + this.buffer[idx1] * frac;
      const clamped = Math.max(-1, Math.min(1, sample));
      this.outChunk[this.outPos++] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;

      if (this.outPos >= this.outChunk.length) {
        // שולחים עותק (transferable) כדי לא להעתיק שוב ב-main thread
        const copy = this.outChunk.slice(0);
        this.port.postMessage({ type: "chunk", data: copy }, [copy.buffer]);
        this.outPos = 0;
      }
    }

    // משאירים רק את השארית שלא נוצלה עדיין
    const consumedSrc = Math.floor(available * this.ratio);
    this.buffer = this.buffer.slice(consumedSrc);

    return true;
  }
}

registerProcessor("mic-processor", MicProcessor);
