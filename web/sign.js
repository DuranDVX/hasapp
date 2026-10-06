// Signature pad, photo capture, voice recorder and GPS. No libraries.

// ---- photos: camera or gallery -> JPEG data URL, max 1280 px ----
function pickPhoto({ front = false } = {}) {
  return new Promise((resolve) => {
    const inp = document.createElement("input");
    inp.type = "file"; inp.accept = "image/*";
    inp.setAttribute("capture", front ? "user" : "environment");
    inp.onchange = async () => {
      const f = inp.files && inp.files[0];
      resolve(f ? await shrinkImage(f, 1280) : null);
    };
    inp.click();
  });
}
function pickFile(accept = "image/*,application/pdf") {
  return new Promise((resolve) => {
    const inp = document.createElement("input");
    inp.type = "file"; inp.accept = accept;
    inp.onchange = async () => {
      const f = inp.files && inp.files[0];
      if (!f) return resolve(null);
      if (f.type.startsWith("image/")) return resolve({ name: f.name, data: await shrinkImage(f, 1800) });
      if (f.size > 15 * 1024 * 1024) { toast("That file is too big (max 15 MB).", "bad"); return resolve(null); }
      resolve({ name: f.name, data: await blobToDataURL(f) });
    };
    inp.click();
  });
}
function blobToDataURL(blob) {
  return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(blob); });
}
async function shrinkImage(file, max) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url; });
    const r = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement("canvas");
    c.width = Math.round(img.naturalWidth * r); c.height = Math.round(img.naturalHeight * r);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", 0.8);
  } catch { toast("That photo could not be read. Try again.", "bad"); return null; }
  finally { URL.revokeObjectURL(url); }
}

// ---- GPS: one fix per few minutes, never blocks a signature ----
let lastFix = null;
function gps() {
  if (lastFix && Date.now() - lastFix.t < 5 * 60 * 1000) return Promise.resolve(lastFix);
  return new Promise((res) => {
    if (!navigator.geolocation) return res(lastFix || {});
    navigator.geolocation.getCurrentPosition(
      (p) => { lastFix = { lat: +p.coords.latitude.toFixed(6), lng: +p.coords.longitude.toFixed(6), t: Date.now() }; res(lastFix); },
      () => res(lastFix || {}), { enableHighAccuracy: true, timeout: 6000, maximumAge: 300000 });
  });
}
function localISO(d = new Date()) {
  const off = -d.getTimezoneOffset(), sign = off >= 0 ? "+" : "-", pad = (n) => String(Math.floor(Math.abs(n))).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}${sign}${pad(off / 60)}:${pad(off % 60)}`;
}
const localDate = () => localISO().slice(0, 10);

// ---- signature modal: resolves {image, photo, signed_at, lat, lng} or null ----
function signatureModal({ name, subtitle = "", detail = "", photo = true, photoRequired = false }) {
  return new Promise((resolve) => {
    const m = document.createElement("div");
    m.className = "modal";
    m.innerHTML = `<div class="sheet">
      <div class="row between"><h2 style="margin:0">${esc(name)}</h2><button class="link" data-x="cancel">Cancel</button></div>
      ${subtitle ? `<p class="muted small" style="margin:2px 0 8px">${esc(subtitle)}</p>` : ""}
      ${detail ? `<div class="note warn" style="max-height:30vh;overflow:auto">${detail}</div>` : ""}
      ${photo ? `<div class="row" style="margin:8px 0"><img class="thumb hidden" alt=""><button class="small" data-x="photo">📷 ${photoRequired ? "Take photo (needed)" : "Take photo"}</button></div>` : ""}
      <div class="padwrap"><canvas></canvas><span class="hint">Sign here with your finger</span></div>
      <div class="grid2" style="margin-top:10px"><button data-x="clear">Clear</button><button class="primary" data-x="ok">Save signature</button></div>
    </div>`;
    document.body.appendChild(m);
    const canvas = m.querySelector("canvas"), ctx = canvas.getContext("2d");
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const size = () => { const r = canvas.getBoundingClientRect(); canvas.width = r.width * dpr; canvas.height = r.height * dpr;
      ctx.scale(dpr, dpr); ctx.lineWidth = 2.6; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = "#0b1a2a"; };
    size();
    let drawing = false, points = 0, last = null, shot = null;
    const pos = (e) => { const r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
    canvas.onpointerdown = (e) => { drawing = true; last = pos(e); canvas.setPointerCapture(e.pointerId); m.querySelector(".hint").style.display = "none"; };
    canvas.onpointermove = (e) => { if (!drawing) return; const p = pos(e); ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke(); last = p; points++; };
    canvas.onpointerup = canvas.onpointercancel = () => { drawing = false; };
    const done = (v) => { m.remove(); resolve(v); };
    m.onclick = async (e) => {
      const x = e.target.closest("[data-x]")?.dataset.x;
      if (x === "cancel") done(null);
      if (x === "clear") { ctx.clearRect(0, 0, canvas.width, canvas.height); points = 0; }
      if (x === "photo") {
        shot = await pickPhoto({ front: true });
        if (shot) { const t = m.querySelector(".thumb"); t.src = shot; t.classList.remove("hidden"); }
      }
      if (x === "ok") {
        if (points < 8) return toast("Sign in the box first.", "bad");
        if (photoRequired && !shot) return toast("Take the photo first.", "bad");
        const fix = await gps();
        done({ image: canvas.toDataURL("image/png"), photo: shot || "", signed_at: localISO(), lat: fix.lat, lng: fix.lng });
      }
    };
  });
}

// ---- voice recorder ----
const Recorder = {
  rec: null, chunks: [], started: 0, timer: null,
  async start(onTick) {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    const type = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";
    this.rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    this.chunks = [];
    this.rec.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.rec.start(1000);
    this.started = Date.now();
    this.timer = setInterval(() => {
      const s = Math.floor((Date.now() - this.started) / 1000);
      onTick && onTick(`${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`);
      if (s >= 300) this.stop();   // 5-minute cap
    }, 250);
  },
  stop() {
    return new Promise((res) => {
      clearInterval(this.timer);
      if (!this.rec || this.rec.state === "inactive") return res(null);
      this.rec.onstop = () => {
        this.rec.stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(this.chunks, { type: this.rec.mimeType || "audio/webm" });
        this.rec = null;
        res(blob.size > 1000 ? blob : null);
      };
      this.rec.stop();
    });
  },
  get active() { return !!(this.rec && this.rec.state === "recording"); },
};
