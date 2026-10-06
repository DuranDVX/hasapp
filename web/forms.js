// Field forms: task sheet, toolbox talk, checks, incidents, inductions.
// Each form keeps a draft on the device, so a reload or a flat battery
// does not lose signatures. "Finish" moves the record to the outbox.

const draftKey = (k) => `draft:${k}:${S.siteId}`;
const saveDraft = (k, d) => IDB.set(draftKey(k), d);
const dropDraft = (k) => IDB.del(draftKey(k));
function steps(n, of) { return `<div class="steps">${Array.from({ length: of }, (_, i) => `<span class="${i < n ? "on" : ""}"></span>`).join("")}</div>`; }
function me() { return S.me.user; }
async function finishRecord(kind, payload, signatures, extra = {}) {
  const fix = await gps();
  const body = { client_id: extra.client_id || newId(), site_id: S.siteId, kind, record_date: todayStr(), device_time: localISO(),
    lat: fix.lat, lng: fix.lng, payload, signatures, transcript: extra.transcript || "", audio: extra.audio || "" };
  await IDB.outbox.put({ id: body.client_id, body, created: Date.now(), tries: 0, error: "", label: extra.label || kind });
  S.pending = (await IDB.outbox.all()).length; renderHeader();
  // With a signal, wait for the send so the next screen shows the new record.
  if (online()) { await flush(); loadSite(true).then(refreshIfIdle); } else flush();
  toast(online() ? "Saved. Sending now." : "Saved on this device. It sends when the signal comes back.", "ok");
}
const BAND_C = { Low: "green", Medium: "amber", Significant: "red", High: "red" };
function scoreHtml(h) {
  return h.rating ? ` <span class="badge ${BAND_C[h.band] || ""}">${h.rating} ${esc(h.band || "")}</span> → <span class="badge ${BAND_C[h.rband] || ""}">${h.rrating} ${esc(h.rband || "")}</span>` : "";
}
function hazardHtml(ids) {
  return ids.map(risk).filter(Boolean).map((r) => `<div class="hazard"><b>${esc(r.activity)}</b>${r.approved ? "" : ' <span class="badge warn">Not approved</span>'}
    ${r.hazards.map((h) => `<div>• ${esc(h.hazard)}${scoreHtml(h)}${h.consequence ? `<div class="small"><i>${esc(h.consequence)}</i></div>` : ""}<div class="muted small">${h.controls.map(esc).join("; ")}</div></div>`).join("")}
    <div class="small"><b>PPE:</b> ${esc(r.ppe.join(", "))}</div></div>`).join("");
}
function riskOptions(exclude = []) {
  const rs = S.data.risks.filter((r) => !exclude.includes(r.id));
  return `<option value="">+ Add an activity…</option>` + rs.map((r) => `<option value="${r.id}">${esc(r.activity)}${r.approved ? "" : " (not approved)"}</option>`).join("");
}
function micBlock(label) {
  return `<p class="center muted">${label}</p>
    <button class="mic" data-act="mic" aria-label="Record">🎙️</button><div class="timer" id="timer">Tap to record</div>`;
}
let micHandler = null;
ACT.mic = async (btn) => {
  if (Recorder.active) {
    btn.classList.remove("rec"); $("#timer").textContent = "Working…";
    const blob = await Recorder.stop();
    if (!blob) { $("#timer").textContent = "Nothing recorded. Try again."; return; }
    micHandler && micHandler(blob);
    return;
  }
  try {
    await Recorder.start((t) => { const el = $("#timer"); if (el) el.textContent = "Recording " + t + " · tap to stop"; });
    btn.classList.add("rec");
  } catch { toast("The app needs the microphone. Allow it in the browser settings.", "bad"); }
};
async function voiceToAI(path, blob, text, onDone, onOffline, extra = { site_id: S.siteId }) {
  if (!online()) return onOffline(blob ? await blobToDataURL(blob) : "");
  render(`<div class="spinner"></div><p class="center">Listening and writing it up…</p>`);
  const fd = new FormData();
  Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
  if (blob) fd.append("audio", blob, "note." + (blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm"));
  if (text) fd.append("text", text);
  try { onDone(await api(path, { body: fd, timeout: 120000 })); }
  catch (e) { toast(friendly(e), "bad"); onOffline(blob ? await blobToDataURL(blob) : ""); }
}

// ================================================================ daily task sheet

VIEWS.task = async () => {
  if (!can.write()) return render(`<div class="note warn">Your role cannot fill in task sheets.</div>`);
  const d = await IDB.get(draftKey("task"));
  if (!d) return taskVoice();
  if (d.step === "sign") return taskSign(d);
  return taskReview(d);
};
function taskVoice() {
  render(`${head("Daily task sheet (DSTI)", "Brief the workers on today's tasks, hazards and PPE; they sign before work.", "board")}${steps(1, 3)}
    ${micBlock("Say what each team does today, where, and with which machines.<br><i>“Sipho and his team: brickwork on the east wall from the scaffold. Johan digs the trench for the sewer with the TLB.”</i>")}
    <details class="card"><summary>Type it instead</summary><textarea id="t-text" placeholder="Type today's work"></textarea>
      <button class="dark" data-act="task-text">Use this text</button></details>
    <button class="link" data-act="task-manual">Build the sheet by hand</button>`);
  micHandler = (blob) => taskFromVoice(blob, "");
}
ACT["task-text"] = () => { const t = $("#t-text").value.trim(); if (!t) return toast("Type the work first.", "bad"); taskFromVoice(null, t); };
ACT["task-manual"] = async () => { const d = newTaskDraft(); d.tasks.push(blankTask()); await saveDraft("task", d); taskReview(d); };
const blankTask = () => ({ description: "", location: "", risk_item_ids: [], worker_ids: [], plant_ids: [] });
const newTaskDraft = () => ({ client_id: newId(), step: "review", transcript: "", audio: "", tasks: [], unmatched: [], notes: "", questions: [], signatures: {}, created: Date.now() });
function taskFromVoice(blob, text) {
  voiceToAI("/api/ai/task-sheet", blob, text, async (r) => {
    const d = newTaskDraft();
    Object.assign(d, { transcript: r.transcript, audio: r.audio || "", tasks: r.draft.tasks, unmatched: r.draft.unmatched || [],
      notes: r.draft.notes || "", questions: r.draft.questions || [] });
    if (!d.tasks.length) d.tasks.push(blankTask());
    await saveDraft("task", d); taskReview(d);
  }, async (audio) => {
    const d = newTaskDraft(); d.audio = audio; d.transcript = text; d.tasks.push(blankTask());
    if (text) d.notes = text;
    await saveDraft("task", d); taskReview(d);
    toast("No AI right now. Pick the activities by hand. The voice note stays with the sheet.", "bad");
  });
}
function taskReview(d) {
  const W = S.data.workers, P = S.data.plant;
  render(`<div class="row between"><h1>Check today's tasks</h1><button class="link" data-act="task-reset">Start again</button></div>${steps(2, 3)}
    ${d.questions.length ? `<div class="note warn"><b>Check:</b>${d.questions.map((q) => `<div>• ${esc(q)}</div>`).join("")}</div>` : ""}
    ${d.tasks.map((t, i) => `<div class="card" data-i="${i}">
      <div class="row between"><b>Task ${i + 1}</b><button class="link" data-act="task-del" data-i="${i}">Remove</button></div>
      <label>What</label><input data-f="description" data-i="${i}" value="${esc(t.description)}" placeholder="Brickwork, east wall">
      <label>Where</label><input data-f="location" data-i="${i}" value="${esc(t.location)}" placeholder="East wall, ground floor">
      <label>Activities (from the risk assessment)</label>
      <div class="chips">${t.risk_item_ids.map((id) => { const r = risk(id); return r ? `<button class="chip on ${r.approved ? "" : "unapproved"}" data-act="task-risk-off" data-i="${i}" data-id="${id}">${esc(r.activity)} ✕</button>` : ""; }).join("")}</div>
      <select data-act-change="task-risk-add" data-i="${i}">${riskOptions(t.risk_item_ids)}</select>
      ${t.risk_item_ids.length ? `<details><summary class="small">Hazards, controls and PPE</summary>${hazardHtml(t.risk_item_ids)}</details>` : `<div class="note warn">Pick at least one activity. If none fits, the safety officer must assess this task first.</div>`}
      <label>Workers</label><div class="chips">${W.map((w) => `<button class="chip ${t.worker_ids.includes(w.id) ? "on" : ""}" data-act="task-worker" data-i="${i}" data-id="${w.id}">${esc(w.name)}</button>`).join("") || '<span class="muted small">No workers on this site yet.</span>'}</div>
      ${P.length ? `<label>Plant</label><div class="chips">${P.map((p) => `<button class="chip ${t.plant_ids.includes(p.id) ? "on" : ""}" data-act="task-plant" data-i="${i}" data-id="${p.id}">${esc(p.name)}</button>`).join("")}</div>` : ""}
    </div>`).join("")}
    <button data-act="task-add">+ Add a task</button>
    ${d.unmatched.length ? `<div class="note warn" style="margin-top:12px"><b>No risk assessment for:</b>${d.unmatched.map((u, i) => `<div class="row between">• ${esc(u.description)} <button class="link" data-act="task-unmatched-del" data-i="${i}">✕</button></div>`).join("")}
      <div class="small">Do not start this work until the safety officer assesses it.</div></div>` : ""}
    <label>Notes (weather, deliveries, visitors)</label><textarea data-f="notes">${esc(d.notes)}</textarea>
    ${d.transcript ? `<details class="small muted"><summary>What you said</summary>${esc(d.transcript)}</details>` : ""}
    <button class="primary" data-act="task-to-sign" style="margin-top:12px">Next: workers sign</button>`);
  $("#view").oninput = async (e) => {
    const f = e.target.dataset.f; if (!f) return;
    if (f === "notes") d.notes = e.target.value; else d.tasks[+e.target.dataset.i][f] = e.target.value;
    await saveDraft("task", d);
  };
  $("#view").onchange = async (e) => {
    if (e.target.dataset.actChange !== "task-risk-add" || !e.target.value) return;
    d.tasks[+e.target.dataset.i].risk_item_ids.push(e.target.value); await saveDraft("task", d); taskReview(d);
  };
}
async function withTask(fn) { const d = await IDB.get(draftKey("task")); if (!d) return; fn(d); await saveDraft("task", d); if (d.step === "sign") taskSign(d); else taskReview(d); }
const toggle = (arr, id) => { const i = arr.indexOf(id); i >= 0 ? arr.splice(i, 1) : arr.push(id); };
ACT["task-risk-off"] = (el) => withTask((d) => toggle(d.tasks[+el.dataset.i].risk_item_ids, el.dataset.id));
ACT["task-worker"] = (el) => withTask((d) => toggle(d.tasks[+el.dataset.i].worker_ids, el.dataset.id));
ACT["task-plant"] = (el) => withTask((d) => toggle(d.tasks[+el.dataset.i].plant_ids, el.dataset.id));
ACT["task-add"] = () => withTask((d) => d.tasks.push(blankTask()));
ACT["task-del"] = (el) => withTask((d) => d.tasks.splice(+el.dataset.i, 1));
ACT["task-unmatched-del"] = (el) => withTask((d) => d.unmatched.splice(+el.dataset.i, 1));
ACT["task-reset"] = async () => { if (confirm("Throw away this task sheet and start again?")) { await dropDraft("task"); taskVoice(); } };
ACT["task-to-sign"] = () => withTask((d) => {
  if (!d.tasks.length || d.tasks.some((t) => !t.description.trim())) { toast("Each task needs a description.", "bad"); return; }
  if (!d.tasks.some((t) => t.worker_ids.length)) { toast("Assign workers to the tasks.", "bad"); return; }
  d.step = "sign";
});
function taskWorkers(d) { return [...new Set(d.tasks.flatMap((t) => t.worker_ids))].map(worker).filter(Boolean); }
function taskSign(d) {
  const ws = taskWorkers(d), sup = d.signatures["user:" + me().id];
  const signed = ws.filter((w) => d.signatures[w.id]).length;
  render(`<div class="row between"><h1>Sign the task sheet</h1><button class="link" data-act="task-back">‹ Tasks</button></div>${steps(3, 3)}
    <p class="muted">Each worker hears their task, hazards and PPE, then signs. ${signed}/${ws.length} signed.</p>
    <div class="card"><ul class="plain">${ws.map((w) => `<li class="row">
      ${w.photo_url && online() ? `<img class="avatar" src="${w.photo_url}">` : `<div class="avatar">${esc(w.name[0])}</div>`}
      <div class="grow"><b>${esc(w.name)}</b><div class="muted small">${esc(w.trade || "")}${w.inducted ? "" : ' · <span class="crit">not inducted</span>'}</div></div>
      ${d.signatures[w.id] ? '<span class="badge ok">Signed ✓</span>' : `<button class="small primary" data-act="task-sign" data-id="${w.id}">Sign</button>
        <button class="small" data-act="task-absent" data-id="${w.id}">Absent</button>`}</li>`).join("")}</ul>
      ${signed < ws.length ? `<button class="dark" data-act="task-sign-all">Sign everyone in turn</button>` : ""}</div>
    <div class="card"><div class="row between"><div><b>${esc(me().name)}</b><div class="muted small">Supervisor: I explained the tasks, hazards and PPE.</div></div>
      ${sup ? '<span class="badge ok">Signed ✓</span>' : `<button class="small primary" data-act="task-sign-sup">Sign</button>`}</div></div>
    <button class="primary" data-act="task-finish" ${sup && signed === ws.length && ws.length ? "" : "disabled"}>Finish and save</button>`);
}
function workerBrief(d, wid) {
  return d.tasks.filter((t) => t.worker_ids.includes(wid)).map((t) => `<div><b>${esc(t.description)}</b> ${esc(t.location)}</div>${hazardHtml(t.risk_item_ids)}`).join("");
}
async function signWorker(d, w) {
  const sig = await signatureModal({ name: w.name, subtitle: "I understand my task, the hazards, the controls and the PPE.", detail: workerBrief(d, w.id) });
  if (!sig) return false;
  d.signatures[w.id] = { ...sig, worker_id: w.id, role: "worker" };
  await saveDraft("task", d); return true;
}
ACT["task-sign"] = async (el) => { const d = await IDB.get(draftKey("task")); if (await signWorker(d, worker(el.dataset.id))) taskSign(d); };
ACT["task-sign-all"] = async () => {
  const d = await IDB.get(draftKey("task"));
  for (const w of taskWorkers(d)) { if (d.signatures[w.id]) continue; if (!(await signWorker(d, w))) break; }
  taskSign(d);
};
ACT["task-absent"] = (el) => withTask((d) => { d.tasks.forEach((t) => { t.worker_ids = t.worker_ids.filter((x) => x !== el.dataset.id); }); });
ACT["task-back"] = () => withTask((d) => { d.step = "review"; });
ACT["task-sign-sup"] = async () => {
  const d = await IDB.get(draftKey("task"));
  const sig = await signatureModal({ name: me().name, subtitle: "Supervisor: I explained the tasks, hazards and PPE to each worker.", photo: false });
  if (!sig) return;
  d.signatures["user:" + me().id] = { ...sig, user_id: me().id, role: "supervisor" };
  await saveDraft("task", d); taskSign(d);
};
ACT["task-finish"] = async (btn) => {
  const d = await IDB.get(draftKey("task"));
  btn.disabled = true;
  const sigs = taskWorkers(d).map((w) => d.signatures[w.id]).concat([d.signatures["user:" + me().id]]);
  await finishRecord("task_sheet", { tasks: d.tasks, unmatched: d.unmatched, notes: d.notes, transcript_used: !!d.transcript }, sigs,
    { client_id: d.client_id, transcript: d.transcript, audio: d.audio, label: "Daily task sheet" });
  await dropDraft("task"); go("board");
};

// ================================================================ toolbox talk

VIEWS.talk = async () => {
  if (!can.write()) return render(`<div class="note warn">Your role cannot record toolbox talks.</div>`);
  let d = await IDB.get(draftKey("talk"));
  if (!d) {
    const task = await IDB.get(draftKey("task"));
    const pend = (await pendingItems()).filter((p) => p.body.kind === "task_sheet" && p.body.record_date === todayStr());
    const ids = new Set();
    (task?.tasks || pend[0]?.body.payload.tasks || []).forEach((t) => t.risk_item_ids.forEach((i) => ids.add(i)));
    if (!ids.size) (S.data.today_risk_ids || []).forEach((i) => ids.add(i));
    d = { client_id: newId(), step: "prepare", topic: "", language: "en", risk_item_ids: [...ids], title: "", text: "", text_en: "",
      key_points: [], questions: [], ai_translated: false, audio_url: "", group_photo: "", signatures: {}, absent: [] };
    await saveDraft("talk", d);
  }
  if (d.step === "prepare") return talkPrepare(d);
  if (d.step === "talk") return talkShow(d);
  return talkSign(d);
};
function talkPrepare(d) {
  render(`<h1>Toolbox talk</h1>${steps(1, 3)}
    <label>Language the workers understand best</label>
    <select id="tk-lang">${Object.entries(S.data.languages).map(([k, v]) => `<option value="${k}" ${k === d.language ? "selected" : ""}>${v}</option>`).join("")}</select>
    <label>Today's activities</label>
    <div class="chips">${d.risk_item_ids.map((id) => { const r = risk(id); return r ? `<button class="chip on" data-act="talk-risk-off" data-id="${id}">${esc(r.activity)} ✕</button>` : ""; }).join("")}</div>
    <select data-act-change="talk-risk-add">${riskOptions(d.risk_item_ids)}</select>
    <label>Or a topic</label><input id="tk-topic" value="${esc(d.topic)}" placeholder="Working at height on the scaffold">
    <label class="check"><input type="checkbox" id="tk-env" ${d.environmental ? "checked" : ""}> This is an environmental talk (waste, spills, dust, noise)</label>
    <button class="primary" data-act="talk-ai">✨ Write the talk for me</button>
    <button data-act="talk-own">I will give my own talk</button>`);
  $("#view").onchange = async (e) => {
    if (e.target.dataset.actChange === "talk-risk-add" && e.target.value) { d.risk_item_ids.push(e.target.value); await saveDraft("talk", d); talkPrepare(d); }
  };
}
async function withTalk(fn) { const d = await IDB.get(draftKey("talk")); fn(d); await saveDraft("talk", d); route(); }
ACT["talk-risk-off"] = (el) => withTalk((d) => toggle(d.risk_item_ids, el.dataset.id));
ACT["talk-ai"] = async (btn) => {
  const d = await IDB.get(draftKey("talk"));
  d.language = $("#tk-lang").value; d.topic = $("#tk-topic").value.trim(); d.environmental = $("#tk-env").checked;
  if (!online()) { toast("The AI needs a signal. Give your own talk instead.", "bad"); return; }
  await busy(btn, "Writing the talk…", async () => {
    const r = await api("/api/ai/toolbox-talk", { json: { site_id: S.siteId, language: d.language, topic: d.topic, risk_item_ids: d.risk_item_ids }, timeout: 120000 });
    Object.assign(d, { title: r.title, text: r.text, text_en: r.text_en, key_points: r.key_points_en, questions: r.questions_en, ai_translated: r.ai_translated, step: "talk" });
    await saveDraft("talk", d); talkShow(d);
  });
};
ACT["talk-own"] = async () => {
  const d = (await IDB.get(draftKey("talk"))) || { client_id: newId(), risk_item_ids: [], signatures: {}, absent: [] };
  d.language = $("#tk-lang").value; d.topic = $("#tk-topic").value.trim(); d.environmental = $("#tk-env").checked;
  Object.assign(d, { title: d.topic || "Toolbox talk", text: "", text_en: "", key_points: [], questions: [], ai_translated: false, step: "talk", own: true });
  await saveDraft("talk", d); talkShow(d);
};
function talkShow(d) {
  const tts = S.data.tts_languages.includes(d.language) && online() && d.text;
  render(`<div class="row between"><h1>${esc(d.title || "Toolbox talk")}</h1><button class="link" data-act="talk-reset">Start again</button></div>${steps(2, 3)}
    ${d.own ? `<label>Topic</label><input id="tk-title" value="${esc(d.title)}"><label>What you told the workers (short notes)</label><textarea id="tk-text">${esc(d.text)}</textarea>`
      : `${d.ai_translated ? `<div class="note warn small">AI translation. If a worker who speaks the language finds an error, tell the safety officer.</div>` : ""}
      ${tts ? `<button class="dark" data-act="talk-play">▶️ Play the talk aloud</button><audio id="tk-audio" controls class="hidden" style="width:100%;margin-top:8px"></audio>` : ""}
      <div class="card talk-text">${esc(d.text)}</div>
      ${d.language !== "en" ? `<details class="card"><summary>English</summary><div class="talk-text">${esc(d.text_en)}</div></details>` : ""}
      ${d.key_points.length ? `<div class="card"><b>Key points</b>${d.key_points.map((k) => `<div>• ${esc(k)}</div>`).join("")}</div>` : ""}
      ${d.questions.length ? `<div class="card"><b>Ask the workers</b>${d.questions.map((k) => `<div>• ${esc(k)}</div>`).join("")}</div>` : ""}`}
    <button class="primary" data-act="talk-to-sign">Next: attendance</button>`);
}
ACT["talk-play"] = async (btn) => {
  const d = await IDB.get(draftKey("talk"));
  await busy(btn, "Making the audio…", async () => {
    if (!d.audio_url) { const r = await api("/api/tts", { json: { text: d.text, language: d.language }, timeout: 90000 }); d.audio_url = r.url; await saveDraft("talk", d); }
    const a = $("#tk-audio"); a.src = d.audio_url; a.classList.remove("hidden"); a.play().catch(() => {});
  });
};
ACT["talk-reset"] = async () => { if (confirm("Throw away this talk and start again?")) { await dropDraft("talk"); route(); } };
ACT["talk-to-sign"] = () => withTalk((d) => {
  if (d.own) { d.title = $("#tk-title").value.trim(); d.text = $("#tk-text").value.trim(); d.topic = d.topic || d.title; if (!d.title) { toast("Give the topic.", "bad"); return; } }
  d.step = "sign";
});
function talkSign(d) {
  const ws = S.data.workers.filter((w) => !d.absent.includes(w.id)), pres = d.signatures["user:" + me().id];
  const signed = ws.filter((w) => d.signatures[w.id]).length;
  render(`<div class="row between"><h1>Attendance</h1><button class="link" data-act="talk-back">‹ Talk</button></div>${steps(3, 3)}
    <p class="muted">${signed}/${ws.length} signed.</p>
    <div class="card"><ul class="plain">${ws.map((w) => `<li class="row"><div class="grow"><b>${esc(w.name)}</b></div>
      ${d.signatures[w.id] ? '<span class="badge ok">Signed ✓</span>' : `<button class="small primary" data-act="talk-sign" data-id="${w.id}">Sign</button><button class="small" data-act="talk-absent" data-id="${w.id}">Absent</button>`}</li>`).join("")}</ul>
      ${signed < ws.length ? `<button class="dark" data-act="talk-sign-all">Sign everyone in turn</button>` : ""}</div>
    <div class="card"><div class="row between"><b>Group photo</b><button class="small" data-act="talk-photo">📷 ${d.group_photo ? "Retake" : "Take"}</button></div>
      ${d.group_photo ? `<img src="${d.group_photo}" style="width:100%;border-radius:10px;margin-top:8px">` : ""}</div>
    <div class="card"><div class="row between"><div><b>${esc(me().name)}</b><div class="muted small">Presenter</div></div>
      ${pres ? '<span class="badge ok">Signed ✓</span>' : `<button class="small primary" data-act="talk-sign-pres">Sign</button>`}</div></div>
    <button class="primary" data-act="talk-finish" ${pres && signed === ws.length && signed ? "" : "disabled"}>Finish and save</button>`);
}
async function signTalk(d, w) {
  const sig = await signatureModal({ name: w.name, subtitle: `I attended the toolbox talk: ${d.title}`, photo: false,
    detail: d.key_points.map((k) => "• " + esc(k)).join("<br>") });
  if (!sig) return false;
  d.signatures[w.id] = { ...sig, worker_id: w.id, role: "attendee" }; await saveDraft("talk", d); return true;
}
ACT["talk-sign"] = async (el) => { const d = await IDB.get(draftKey("talk")); if (await signTalk(d, worker(el.dataset.id))) talkSign(d); };
ACT["talk-sign-all"] = async () => {
  const d = await IDB.get(draftKey("talk"));
  for (const w of S.data.workers) { if (d.signatures[w.id] || d.absent.includes(w.id)) continue; if (!(await signTalk(d, w))) break; }
  talkSign(d);
};
ACT["talk-absent"] = (el) => withTalk((d) => d.absent.push(el.dataset.id));
ACT["talk-back"] = () => withTalk((d) => { d.step = "talk"; });
ACT["talk-photo"] = async () => { const p = await pickPhoto(); if (p) withTalk((d) => { d.group_photo = p; }); };
ACT["talk-sign-pres"] = async () => {
  const d = await IDB.get(draftKey("talk"));
  const sig = await signatureModal({ name: me().name, subtitle: "Presenter", photo: false });
  if (!sig) return;
  d.signatures["user:" + me().id] = { ...sig, user_id: me().id, role: "presenter" }; await saveDraft("talk", d); talkSign(d);
};
ACT["talk-finish"] = async (btn) => {
  const d = await IDB.get(draftKey("talk"));
  btn.disabled = true;
  const sigs = S.data.workers.filter((w) => d.signatures[w.id]).map((w) => d.signatures[w.id]).concat([d.signatures["user:" + me().id]]);
  await finishRecord("toolbox_talk", { topic: d.topic, title: d.title, language: d.language, text: d.text, text_en: d.text_en,
    key_points: d.key_points, questions: d.questions, ai_translated: d.ai_translated, group_photo: d.group_photo,
    environmental: !!d.environmental }, sigs,
    { client_id: d.client_id, label: "Toolbox talk: " + d.title });
  await dropDraft("talk"); go("board");
};

// ================================================================ checks and inspections

VIEWS.check = async (token) => {
  if (token) {
    let p = S.data.plant.find((x) => x.qr_token === token);
    if (!p && online()) { try { p = await api("/api/plant/by-token/" + encodeURIComponent(token)); } catch (e) { return render(`<div class="note bad">${esc(friendly(e))}</div>`); } }
    if (!p) return render(`<div class="note bad">This machine is not on this site's list. Open the site it belongs to, or add it under Plant.</div>`);
    return go(`checklist/${p.template}/${p.id}`);
  }
  const plant = S.data.plant, insp = Object.entries(S.data.checklists).filter(([, c]) => c.kind === "inspection");
  render(`${head("Plant pre-use checks", "Scan the QR sticker on the machine, or choose it here. Inspections are under + Record.", "board")}
    <h2>Plant</h2>${plant.length ? `<div class="card"><ul class="plain">${plant.map((p) => `<li class="list-item" data-act="nav" data-to="checklist/${p.template}/${p.id}">
      <div class="grow"><b>${esc(p.name)}</b> <span class="muted small">${esc(p.ident)}</span><div class="muted small">${esc(p.template_title)}</div></div><span>›</span></li>`).join("")}</ul></div>`
      : `<p class="muted">No plant yet. <a href="#plant">Add plant</a></p>`}
    <h2>Site inspections</h2><div class="card"><ul class="plain">${insp.map(([k, c]) => `<li class="list-item" data-act="nav" data-to="checklist/${k}">
      <div class="grow"><b>${esc(c.title)}</b>${c.note ? `<div class="muted small">${esc(c.note)}</div>` : ""}</div><span>›</span></li>`).join("")}</ul></div>`);
};
VIEWS.checklist = async (tpl, plantId = "") => {
  if (!can.write()) return render(`<div class="note warn">Your role cannot record checks.</div>`);
  const c = S.data.checklists[tpl];
  if (!c) return render(`<div class="note bad">Unknown checklist.</div>`);
  const plant = S.data.plant.find((p) => p.id === plantId);
  const key = `check:${tpl}:${plantId}`;
  const d = (await IDB.get(draftKey(key))) || { client_id: newId(), answers: c.items.map(() => ({ answer: "", note: "", photo: "" })), location: "", notes: "", signer: "", sig: null };
  const fails = c.items.some((q, i) => q.critical && d.answers[i].answer === "defect");
  render(`${head(c.title, c.kind === "plant" ? "Answer every item before use." : "Inspect, answer every item, sign.", c.kind === "plant" ? "check" : "inspections")}${plant ? `<p><b>${esc(plant.name)}</b> <span class="muted">${esc(plant.ident)}</span></p>` : `<label>Location on site</label><input data-cf="location" value="${esc(d.location)}" placeholder="North scaffold, block B">`}
    ${c.note ? `<div class="note warn small">${esc(c.note)}</div>` : ""}
    ${c.items.map((q, i) => { const a = d.answers[i]; return `<div class="card"><div>${esc(q.q)} ${q.critical ? '<span class="crit">*</span>' : ""}</div>
      <div class="answer">${["ok", "defect", "na"].map((v) => `<button class="${v} ${a.answer === v ? "on" : ""}" data-act="ck-ans" data-i="${i}" data-v="${v}">${{ ok: "OK", defect: "Defect", na: "N/A" }[v]}</button>`).join("")}</div>
      ${a.answer === "defect" ? `<input data-cf="note" data-i="${i}" value="${esc(a.note)}" placeholder="What is wrong?">
        <div class="row">${a.photo ? `<img class="thumb" src="${a.photo}">` : ""}<button class="small" data-act="ck-photo" data-i="${i}">📷 Photo</button></div>` : ""}</div>`; }).join("")}
    <p class="muted small"><span class="crit">*</span> Critical: a defect means the item must not be used.</p>
    ${fails ? `<div class="note bad"><b>DO NOT USE.</b> Tell the foreman. Lock it out or tag it until it is repaired.</div>` : ""}
    <label>Notes</label><textarea data-cf="notes">${esc(d.notes)}</textarea>
    <label>Who did the check?</label>
    <select data-cf="signer"><option value="">Choose…</option><option value="user:${me().id}" ${d.signer === "user:" + me().id ? "selected" : ""}>${esc(me().name)} (me)</option>
      ${S.data.workers.map((w) => `<option value="${w.id}" ${d.signer === w.id ? "selected" : ""}>${esc(w.name)}</option>`).join("")}</select>
    ${actionBar(`<button class="primary" data-act="ck-finish" data-tpl="${tpl}" data-plant="${plantId}">Sign and save</button>`)}`);
  const save = () => saveDraft(key, d);
  $("#view").oninput = $("#view").onchange = (e) => {
    const f = e.target.dataset.cf; if (!f) return;
    if (f === "note") d.answers[+e.target.dataset.i].note = e.target.value; else d[f] = e.target.value;
    save();
  };
  ACT["ck-ans"] = async (el) => { d.answers[+el.dataset.i].answer = el.dataset.v; await save(); const y = window.scrollY; await VIEWS.checklist(tpl, plantId); window.scrollTo(0, y); };
  ACT["ck-photo"] = async (el) => { const p = await pickPhoto(); if (!p) return; d.answers[+el.dataset.i].photo = p; await save(); const y = window.scrollY; await VIEWS.checklist(tpl, plantId); window.scrollTo(0, y); };
  ACT["ck-finish"] = async (btn) => {
    if (d.answers.some((a) => !a.answer)) return toast("Answer every item.", "bad");
    if (d.answers.some((a) => a.answer === "defect" && !a.note.trim())) return toast("Describe each defect.", "bad");
    if (!d.signer) return toast("Choose who did the check.", "bad");
    const isMe = d.signer.startsWith("user:"), w = isMe ? null : worker(d.signer);
    const sig = await signatureModal({ name: isMe ? me().name : w.name, subtitle: "I did this check and the answers are true.", photo: false });
    if (!sig) return;
    btn.disabled = true;
    const signature = { ...sig, role: plant ? "operator" : "inspector", ...(isMe ? { user_id: me().id } : { worker_id: w.id }) };
    await finishRecord("check", { template: tpl, plant_id: plantId, location: d.location, notes: d.notes,
      answers: d.answers.map((a) => ({ answer: a.answer, note: a.note, ...(a.photo ? { photo: a.photo } : {}) })) }, [signature],
      { client_id: d.client_id, label: plant ? plant.name : c.title });
    await dropDraft(key);
    go(fails ? "board" : "check");
  };
};

// ================================================================ incident

VIEWS.incident = async () => {
  if (!can.write()) return render(`<div class="note warn">Your role cannot report incidents. Tell the foreman.</div>`);
  const d = await IDB.get(draftKey("incident"));
  if (d) return incidentForm(d);
  render(`${head("Report an incident", "Speak or type what happened. The app writes the flash report and Annexure 1 for you to check.", "incidents")}
    <div class="note bad small">If someone is hurt: first aid and call for help first. Report after.</div>
    ${micBlock("Say: who you are, when and where, what work was being done, what happened, who was hurt and how, what you did straight away, and where the person was taken.")}
    <details class="card"><summary>Type it instead</summary><textarea id="inc-text" style="min-height:140px"></textarea>
      <button class="dark" data-act="inc-text">Use this text</button></details>
    <button class="link" data-act="inc-manual">Fill in the form by hand</button>`);
  micHandler = (blob) => incidentFromAI(blob, "");
};
function incidentFromAI(blob, text) {
  voiceToAI("/api/ai/incident", blob, text, async (r) => {
    const x = r.draft;
    const nd = { ...blankIncident(), ...x, client_id: newId(), transcript: r.transcript, audio: r.audio || "",
      witnesses: (x.witnesses || []).join(", "), photos: [], photo_captions: [] };
    await saveDraft("incident", nd); incidentForm(nd);
  }, async (audio) => { const nd = blankIncident(); nd.audio = audio; nd.description = text; await saveDraft("incident", nd); incidentForm(nd); });
}
ACT["inc-text"] = () => { const t = $("#inc-text").value.trim(); if (!t) return toast("Type what happened first.", "bad"); incidentFromAI(null, t); };
const blankPerson = () => ({ name: "", worker_id: "", injury: "", treatment: "", body_parts: [], effects: [], effect_other: "", disablement: "",
  medical: { clinic: "", pre_existing: "", physio: null, unfit: null, light_duty_date: "", resumption_date: "" } });
const blankIncident = () => ({ client_id: newId(), transcript: "", audio: "", type: "near_miss", title: "", occurred_at: localISO().slice(0, 16).replace("T", " "),
  location: "", reported_by: me().name, reporter_contact: "", work_type: "", description: "", people: [], damage: [], damage_note: "",
  witnesses: "", immediate_actions: "", possible_causes: [], possibly_reportable: false, reportable_reason: "", questions: [], photos: [], photo_captions: [] });
ACT["inc-manual"] = async () => { const d = blankIncident(); await saveDraft("incident", d); incidentForm(d); };
const chipList = (attr, i, all, chosen) => `<div class="chips">${all.map((o) => `<button class="chip ${(chosen || []).includes(o) ? "on" : ""}" data-act="inc-chip" data-attr="${attr}" data-i="${i}" data-v="${esc(o)}">${esc(o)}</button>`).join("")}</div>`;
const ynBtns = (attr, i, v) => `<div class="answer" style="grid-template-columns:1fr 1fr 1fr">${[["Yes", true], ["No", false], ["Unknown", null]].map(([l, b]) =>
  `<button class="${b === true ? "ok" : b === false ? "defect" : "na"} ${v === b ? "on" : ""}" data-act="inc-yn" data-attr="${attr}" data-i="${i}" data-v="${b}">${l}</button>`).join("")}</div>`;
function incidentForm(d) {
  const L = S.data.incident_lists;
  render(`<div class="row between"><h1 style="margin:0">Incident report</h1><button class="link" data-act="inc-reset">Start again</button></div>
    ${d.questions?.length ? `<div class="note warn"><b>Still missing:</b>${d.questions.map((q) => `<div>• ${esc(q)}</div>`).join("")}</div>` : ""}
    <h2>1. Basic information</h2><div class="card">
      <label>Type of incident (short)</label><input data-if="title" value="${esc(d.title)}" placeholder="Trench collapse: worker trapped by falling soil">
      <label>Category</label><select data-if="type">${Object.entries(S.data.incident_types).map(([k, v]) => `<option value="${k}" ${k === d.type ? "selected" : ""}>${v}</option>`).join("")}</select>
      <div class="grid2"><div><label>Date and time</label><input data-if="occurred_at" value="${esc(d.occurred_at)}"></div>
        <div><label>Where</label><input data-if="location" value="${esc(d.location)}"></div></div>
      <div class="grid2"><div><label>Reported by</label><input data-if="reported_by" value="${esc(d.reported_by)}"></div>
        <div><label>Contact number</label><input data-if="reporter_contact" type="tel" value="${esc(d.reporter_contact)}"></div></div>
      <label>Machine, process or type of work</label><input data-if="work_type" value="${esc(d.work_type)}"></div>
    <h2>2. People hurt or involved</h2>
    ${d.people.map((p, i) => `<div class="card"><div class="row between"><b>Person ${i + 1}</b><button class="link" data-act="inc-person-del" data-i="${i}">Remove</button></div>
      <label>Worker</label><select data-ip="worker_id" data-i="${i}"><option value="">Not on the worker list</option>${S.data.workers.map((w) => `<option value="${w.id}" ${w.id === p.worker_id ? "selected" : ""}>${esc(w.name)}</option>`).join("")}</select>
      ${p.worker_id ? "" : `<input data-ip="name" data-i="${i}" value="${esc(p.name)}" placeholder="Full name">`}
      <label>Injury description</label><input data-ip="injury" data-i="${i}" value="${esc(p.injury)}">
      <label>Immediate medical action / treatment</label><input data-ip="treatment" data-i="${i}" value="${esc(p.treatment)}">
      <details><summary class="small"><b>Annexure 1 boxes</b> (part of body, effect, time off)</summary>
        <label>Part of body affected</label>${chipList("body_parts", i, L.body_parts, p.body_parts)}
        <label>Effect on person</label>${chipList("effects", i, L.effects, p.effects)}
        ${(p.effects || []).includes("Other") ? `<input data-ip="effect_other" data-i="${i}" value="${esc(p.effect_other)}" placeholder="Other: specify">` : ""}
        <label>Expected period of disablement</label><select data-ip="disablement" data-i="${i}"><option value="">-</option>${L.disablement.map((o) => `<option ${o === p.disablement ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></details>
      <details><summary class="small"><b>Medical report findings</b></summary>
        <label>Clinic / hospital description</label><input data-im="clinic" data-i="${i}" value="${esc(p.medical?.clinic)}">
        <label>Pre-existing defect or disease</label><input data-im="pre_existing" data-i="${i}" value="${esc(p.medical?.pre_existing)}">
        <label>Referred for physiotherapy</label>${ynBtns("physio", i, p.medical?.physio)}
        <label>Unfit for work</label>${ynBtns("unfit", i, p.medical?.unfit)}
        <div class="grid2"><div><label>Fit for light duty from</label><input type="date" data-im="light_duty_date" data-i="${i}" value="${esc(p.medical?.light_duty_date)}"></div>
          <div><label>Back at work on</label><input type="date" data-im="resumption_date" data-i="${i}" value="${esc(p.medical?.resumption_date)}"></div></div></details></div>`).join("")}
    <button class="small" data-act="inc-person">+ Add a person</button>
    <h2>3. What happened</h2><div class="card"><textarea data-if="description" style="min-height:180px">${esc(d.description)}</textarea>
      <label>Damage</label>${chipList("damage", -1, L.damage, d.damage)}
      <label>Witnesses</label><input data-if="witnesses" value="${esc(d.witnesses)}"></div>
    <h2>4. Immediate actions taken (one per line)</h2><div class="card"><textarea data-if="immediate_actions" style="min-height:120px">${esc(d.immediate_actions)}</textarea></div>
    <h2>Photos</h2><div class="card">${d.photos.map((ph, i) => `<div class="row" style="margin-bottom:6px"><img class="thumb" src="${ph}">
        <input data-cap="${i}" value="${esc(d.photo_captions[i] || "")}" placeholder="Caption, e.g. trench barricaded" style="margin:0"></div>`).join("")}
      <button class="small" data-act="inc-photo">📷 Add photo</button></div>
    <div class="card"><label class="check"><input type="checkbox" data-if="possibly_reportable" ${d.possibly_reportable ? "checked" : ""}> This may be reportable (OHS Act s24)</label>
      ${d.possibly_reportable ? `<div class="note bad small">${esc(d.reportable_reason || "")} The safety officer must decide and report it to the Department of Employment and Labour in time.</div>` : ""}</div>
    ${actionBar(`<button class="primary" data-act="inc-finish">Sign and save</button>`)}`);
  $("#view").oninput = $("#view").onchange = async (e) => {
    const t = e.target, f = t.dataset.if, pf = t.dataset.ip, mf = t.dataset.im;
    if (f) d[f] = t.type === "checkbox" ? t.checked : t.value;
    if (pf) { const p = d.people[+t.dataset.i]; p[pf] = t.value; if (pf === "worker_id") { const w = worker(t.value); if (w) p.name = w.name; } }
    if (mf) d.people[+t.dataset.i].medical[mf] = t.value;
    if (t.dataset.cap !== undefined) d.photo_captions[+t.dataset.cap] = t.value;
    await saveDraft("incident", d);
    if (f === "possibly_reportable" || pf === "worker_id") { const y = scrollY; incidentForm(d); scrollTo(0, y); }
  };
}
async function withInc(fn) { const d = await IDB.get(draftKey("incident")); await fn(d); await saveDraft("incident", d); const y = scrollY; incidentForm(d); scrollTo(0, y); }
ACT["inc-person"] = () => withInc((d) => d.people.push(blankPerson()));
ACT["inc-person-del"] = (el) => withInc((d) => d.people.splice(+el.dataset.i, 1));
ACT["inc-photo"] = () => withInc(async (d) => { const p = await pickPhoto(); if (p) { d.photos.push(p); d.photo_captions.push(""); } });
ACT["inc-chip"] = (el) => withInc((d) => {
  const i = +el.dataset.i, a = el.dataset.attr, target = i < 0 ? d : d.people[i];
  target[a] = target[a] || []; toggle(target[a], el.dataset.v);
});
ACT["inc-yn"] = (el) => withInc((d) => { d.people[+el.dataset.i].medical[el.dataset.attr] = el.dataset.v === "null" ? null : el.dataset.v === "true"; });
ACT["inc-reset"] = async () => { if (confirm("Throw away this report?")) { await dropDraft("incident"); route(); } };
ACT["inc-finish"] = async (btn) => {
  const d = await IDB.get(draftKey("incident"));
  if (!d.description.trim()) return toast("Describe what happened.", "bad");
  const sig = await signatureModal({ name: me().name, subtitle: "I report this incident. The facts are true as far as I know.", photo: false });
  if (!sig) return;
  btn.disabled = true;
  const keys = ["type", "title", "occurred_at", "location", "reported_by", "reporter_contact", "work_type", "description", "people", "damage",
    "damage_note", "immediate_actions", "possible_causes", "possibly_reportable", "reportable_reason", "photos", "photo_captions"];
  const payload = Object.fromEntries(keys.map((k) => [k, d[k]]));
  payload.witnesses = (d.witnesses || "").split(",").map((x) => x.trim()).filter(Boolean);
  await finishRecord("incident", payload, [{ ...sig, user_id: me().id, role: "reporter" }],
    { client_id: d.client_id, transcript: d.transcript, audio: d.audio, label: "Incident report" });
  await dropDraft("incident"); go("incidents");
};

// ================================================================ induction

VIEWS.induct = async (wid) => {
  const w = worker(wid);
  if (!w) return render(`<div class="note bad">Add the worker to this site first.</div>`);
  const site = S.data.site;
  let wsig = null;
  render(`${head("Site induction", `${esc(w.name)} · ${esc(site.name)}. Read the rules to the worker, then both sign.`, "history")}
    <div class="card talk-text" style="font-size:16px">${esc(S.data.induction_text)}</div>
    ${site.emergency ? `<div class="card"><b>Emergency</b><div style="white-space:pre-wrap">${esc(site.emergency)}</div></div>` : ""}
    <h2>Worker's agreement</h2><div class="card"><div class="small" style="white-space:pre-wrap">${esc(S.data.worker_consent)}</div>
      <label class="check"><input type="checkbox" id="ind-consent"> ${esc(w.name)} agrees</label></div>
    <div class="card"><div class="row between"><div><b>${esc(w.name)}</b><div class="muted small">I understand the site rules.</div></div><span id="ind-w"><button class="small primary" data-act="ind-sign-w">Sign</button></span></div></div>
    <div class="card"><div class="row between"><div><b>${esc(me().name)}</b><div class="muted small">Inductor</div></div><span id="ind-me"></span></div></div>
    ${actionBar(`<button class="primary" data-act="ind-finish" disabled>Finish and save</button>`)}`);
  ACT["ind-sign-w"] = async () => {
    if (!$("#ind-consent").checked) return toast("The worker must agree first (e-signatures and privacy).", "bad");
    wsig = await signatureModal({ name: w.name, subtitle: "I understand the site rules.", photoRequired: !w.photo_url });
    if (!wsig) return;
    $("#ind-w").innerHTML = '<span class="badge ok">Signed ✓</span>';
    $("#ind-me").innerHTML = `<button class="small primary" data-act="ind-sign-me">Sign</button>`;
  };
  ACT["ind-sign-me"] = async () => {
    const s = await signatureModal({ name: me().name, subtitle: "Inductor: I explained the site rules.", photo: false });
    if (!s) return;
    $("#ind-me").innerHTML = '<span class="badge ok">Signed ✓</span>';
    const b = $("[data-act=ind-finish]"); b.disabled = false;
    ACT["ind-finish"] = async () => {
      b.disabled = true;
      await finishRecord("induction", { worker_id: w.id, language: w.language, consent: true }, [{ ...wsig, worker_id: w.id, role: "worker" }, { ...s, user_id: me().id, role: "inductor" }],
        { label: "Induction: " + w.name });
      w.inducted = true; go("workers");
    };
  };
};
