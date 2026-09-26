// media.js — שיתוף מסך/מצלמה (→ JPEG כל שנייה) ולכידת אודיו-טאב לתרגום.

// ---------------------------------------------------------------------- //
// VideoCapture — משמש גם למסך וגם למצלמה. שולח פריים JPEG כל 1000ms.
// ---------------------------------------------------------------------- //
export class VideoCapture {
  constructor() {
    this.stream = null;
    this.video = document.createElement("video");
    this.video.muted = true;
    this.video.playsInline = true;
    this.canvas = document.createElement("canvas");
    this.ctx2d = this.canvas.getContext("2d");
    this.timer = null;
    this.kind = null; // "screen" | "camera"
    this._onFrame = null;
  }

  onFrame(fn) {
    this._onFrame = fn;
  }

  async startScreen() {
    this.stream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: 5 },
      audio: false,
    });
    this.kind = "screen";
    await this._attach();
  }

  async startCamera() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user" },
      audio: false,
    });
    this.kind = "camera";
    await this._attach();
  }

  async _attach() {
    this.video.srcObject = this.stream;
    await this.video.play();
    // עוצרים אוטומטית אם המשתמש מבטל שיתוף מתפריט הדפדפן
    const track = this.stream.getVideoTracks()[0];
    if (track) track.onended = () => this.stop();

    this.timer = setInterval(() => this._captureFrame(), 1000);
  }

  _captureFrame() {
    if (!this.video.videoWidth) return;
    const maxWidth = 1024;
    const scale = Math.min(1, maxWidth / this.video.videoWidth);
    const w = Math.round(this.video.videoWidth * scale);
    const h = Math.round(this.video.videoHeight * scale);
    this.canvas.width = w;
    this.canvas.height = h;
    this.ctx2d.drawImage(this.video, 0, 0, w, h);
    const dataUrl = this.canvas.toDataURL("image/jpeg", 0.6);
    const base64 = dataUrl.split(",")[1];
    if (this._onFrame) this._onFrame(base64);
  }

  isActive() {
    return !!this.stream;
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.kind = null;
  }
}

// ---------------------------------------------------------------------- //
// captureTabAudio — למצב תרגום וידאו: getDisplayMedia({video:true,audio:true})
// ואז שימוש רק בטראק האודיו (מתעלמים מהוידאו). מחזיר MediaStream של אודיו
// בלבד, או זורק שגיאה אם המשתמש לא סימן "שתף אודיו של הטאב".
// ---------------------------------------------------------------------- //
export async function captureTabAudio() {
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: true,
    audio: true,
  });
  const audioTracks = stream.getAudioTracks();
  const videoTracks = stream.getVideoTracks();
  // הוידאו לא נחוץ לתרגום — משתיקים ומשליכים אותו כדי לחסוך משאבים
  videoTracks.forEach((t) => t.stop());

  if (audioTracks.length === 0) {
    stream.getTracks().forEach((t) => t.stop());
    throw new Error("NO_TAB_AUDIO");
  }
  return new MediaStream(audioTracks);
}
