// Registers: people (workers, contractors, visitors), appointments, documents for
// signing (AES), audits, incidents and investigations.

function peopleTabs(on) {
  const t = [["workers", "Workers"], ["contractors", "Contractors"], ["visitors", "Visitors"]];
  return `<div class="tabs">${t.map(([k, v]) => `<button class="${k === on ? "on" : ""}" data-act="nav" data-to="${k}">${v}</button>`).join("")}</div>`;
}
VIEWS.people = () => VIEWS.workers();

// ---------------------------------------------------------------- visitors (reg 7(6))

VIEWS.visitors = async () => {
  const t = todayStr();
  const pend = (await pendingItems()).filter((p) => p.body.kind === "visitor");
  const list = (S.data.recent || []).filter((r) => r.kind === "visitor");
  render(`${head("People on site", "Workers, contractors and visitors.")}${peopleTabs("visitors")}
    <div class="note info small">Every visitor gets a short induction and PPE before entry (reg 7(6)).</div>
    ${pend.length ? `<div class="card"><b>Waiting to send</b>${pend.map((p) => `<div class="small">• ${esc(p.body.payload.name)}</div>`).join("")}</div>` : ""}
    ${list.length ? `<div class="card"><ul class="plain">${list.map((r) => `<li class="list-item" data-act="nav" data-to="record/${r.id}">
      <div class="grow"><b>${esc(r.summary)}</b><div class="muted small">${esc(r.record_date)}${r.record_date === t ? " · today" : ""}</div></div><span>›</span></li>`).join("")}</ul></div>`
      : `<p class="muted">No visitors in the last 14 days.</p>`}
    ${actionBar(`<button class="primary" data-act="nav" data-to="visitor">+ Sign in a visitor</button>`)}`);
};

VIEWS.visitor = () => {
  if (!can.write()) return render(`<div class="note warn">Your role cannot sign in visitors.</div>`);
  const ppe = S.data.visitor_ppe;
  render(`${head("Sign in a visitor", "Induct the visitor, give PPE, both sign.", "visitors")}
    <div class="card"><label>Visitor's name</label><input id="vi-name" autocomplete="off">
      <label>Company</label><input id="vi-co"><label>Phone</label><input id="vi-phone" type="tel">
      <label>ID number (optional)</label><input id="vi-id">
      <label>Reason for the visit</label><input id="vi-purpose" placeholder="Client walk-through, delivery, inspection…">
      <label>Host (stays with the visitor)</label><input id="vi-host" value="${esc(me().name)}"></div>
    <h2>PPE given</h2><div class="card">${ppe.map((x, i) => `<label class="check"><input type="checkbox" data-ppe="${esc(x)}" ${i < 3 ? "checked" : ""}> ${esc(x)}</label>`).join("")}</div>
    <h2>Read the rules to the visitor</h2><div class="card talk-text" style="font-size:16px">${esc(S.data.visitor_rules)}</div>
    ${S.data.site.emergency ? `<div class="card"><b>Emergency</b><div style="white-space:pre-wrap">${esc(S.data.site.emergency)}</div></div>` : ""}
    ${actionBar(`<button class="primary" data-act="vi-sign">Visitor and host sign</button>`)}`);
};
ACT["vi-sign"] = async (btn) => {
  const name = $("#vi-name").value.trim();
  const ppe = [...document.querySelectorAll("[data-ppe]:checked")].map((x) => x.dataset.ppe);
  if (!name) return toast("Give the visitor's name.", "bad");
  if (!ppe.length) return toast("Tick the PPE the visitor received.", "bad");
  const v = await signatureModal({ name, subtitle: "I received the site rules and PPE and will follow them.", photo: true });
  if (!v) return;
  const h = await signatureModal({ name: me().name, subtitle: "Host: I inducted the visitor and stay with them.", photo: false });
  if (!h) return;
  btn.disabled = true;
  await finishRecord("visitor", { name, company: $("#vi-co").value, phone: $("#vi-phone").value, id_number: $("#vi-id").value,
    purpose: $("#vi-purpose").value, host: $("#vi-host").value, ppe, time_in: localISO() },
    [{ ...v, name, role: "visitor" }, { ...h, user_id: me().id, role: "host" }], { label: "Visitor: " + name });
  go("visitors");
};

// ---------------------------------------------------------------- contractors (reg 7(1)(c), 7(1)(f), s37(2))

const cStatus = (c) => {
  const items = [["COID letter", c.coid_status === "valid" ? "green" : c.coid_status === "expiring" ? "amber" : "red"],
    ["Appointed in writing", c.appointed_on ? "green" : "red"], ["H&S plan approved", c.hs_plan_ok ? "green" : "amber"]];
  return items;
};
VIEWS.contractors = async () => {
  let list = S.data.contractors || [], aesDocs = [];
  if (online()) { try { list = await api("/api/contractors?site_id=" + S.siteId); aesDocs = await api("/api/aes?site_id=" + S.siteId); } catch {} }
  render(`${head("People on site", "Workers, contractors and visitors.")}${peopleTabs("contractors")}
    <div class="note info small">Each contractor needs a written appointment, a COID letter of good standing and a section 37(2) agreement.</div>
    ${list.length ? list.map((c) => {
      const ag = aesDocs.find((a) => a.contractor_id === c.id);
      const rows = cStatus(c).concat([["37(2) agreement", !ag ? "red" : ag.status === "signed" ? "green" : "amber"]]);
      return `<div class="card tap" data-act="nav" data-to="contractor/${c.id}"><div class="grow"><b>${esc(c.name)}</b>
        <div class="muted small">${esc(c.scope || "")}</div>
        <div class="row wrap small" style="margin-top:6px;gap:10px">${rows.map(([l, st]) => `<span class="row" style="gap:4px"><span class="dot ${st}"></span>${l}</span>`).join("")}</div></div><span>›</span></div>`;
    }).join("") : `<p class="muted">No contractors on this site.</p>`}
    ${can.write() ? actionBar(`<button class="primary" data-act="nav" data-to="contractor/new">+ Add a contractor</button>`) : ""}`);
};
VIEWS.contractor = async (id) => {
  if (needOnline()) return;
  const c = id === "new" ? {} : (await api("/api/contractors?site_id=" + S.siteId)).find((x) => x.id === id) || {};
  const ag = id === "new" ? null : (await api("/api/aes?site_id=" + S.siteId)).find((a) => a.contractor_id === id);
  let coid = null;
  render(`${head(id === "new" ? "Add a contractor" : c.name, "Reg 7(1)(c): appoint in writing, check COID, agree on safety.", "contractors")}
    <div class="card"><label>Company name</label><input id="ct-name" value="${esc(c.name || "")}">
      <label>Registration number</label><input id="ct-reg" value="${esc(c.reg_no || "")}">
      <label>Scope of work</label><textarea id="ct-scope">${esc(c.scope || "")}</textarea>
      <label>Contact person</label><input id="ct-contact" value="${esc(c.contact || "")}">
      <div class="grid2"><div><label>Phone</label><input id="ct-phone" type="tel" value="${esc(c.phone || "")}"></div>
        <div><label>Email</label><input id="ct-email" type="email" value="${esc(c.email || "")}"></div></div>
      <label>Appointed in writing on</label><input id="ct-appt" type="date" value="${esc(c.appointed_on || "")}">
      <label class="check"><input type="checkbox" id="ct-plan" ${c.hs_plan_ok ? "checked" : ""}> Their H&S plan is received and approved</label></div>
    <h2>COID letter of good standing</h2><div class="card">
      ${c.coid_url ? `<a href="${c.coid_url}" target="_blank">📄 Current letter</a> <span class="badge ${c.coid_status === "valid" ? "ok" : c.coid_status === "expiring" ? "warn" : "bad"}">${esc(c.coid_status)}</span>` : `<span class="badge bad">Not uploaded</span>`}
      <label style="margin-top:8px">Valid until</label><input id="ct-coid-exp" type="date" value="${esc(c.coid_expires || "")}">
      <button class="small" data-act="ct-coid">📄 Upload the letter</button> <span id="ct-coid-name" class="muted small"></span></div>
    ${id !== "new" ? `<h2>Section 37(2) agreement</h2><div class="card">${ag ? `<b>${esc(ag.title)}</b> <span class="badge ${ag.status === "signed" ? "ok" : "warn"}">${ag.status === "signed" ? "Signed" : "Waiting for signatures"}</span>
        <p class="small muted">${esc(ag.summary)}</p><button class="small" data-act="nav" data-to="aes">Open documents for signing</button>`
      : `<p class="small muted">The app makes the agreement as a PDF for an advanced e-signature or wet ink.</p>
        ${can.manage() ? `<button class="small dark" data-act="ct-agreement" data-id="${id}">Issue the 37(2) agreement</button>` : ""}`}</div>` : ""}
    ${actionBar(`<button class="primary" data-act="ct-save" data-id="${esc(id)}">Save</button>`)}`);
  ACT["ct-coid"] = async () => { coid = await pickFile(); if (coid) $("#ct-coid-name").textContent = coid.name; };
  ACT["ct-save"] = (btn) => busy(btn, "Saving…", async () => {
    const body = { site_id: S.siteId, name: $("#ct-name").value, reg_no: $("#ct-reg").value, scope: $("#ct-scope").value,
      contact: $("#ct-contact").value, phone: $("#ct-phone").value, email: $("#ct-email").value, appointed_on: $("#ct-appt").value,
      hs_plan_ok: $("#ct-plan").checked, coid_expires: $("#ct-coid-exp").value };
    if (coid) body.coid_file = coid.data;
    const r = id === "new" ? await api("/api/contractors", { json: body, timeout: 120000 })
      : await api("/api/contractors/" + id, { method: "PUT", json: body, timeout: 120000 });
    await loadSite(true); toast("Saved.", "ok"); go("contractor/" + r.id);
  });
};
ACT["ct-agreement"] = (btn) => busy(btn, "Making the agreement…", async () => {
  await api(`/api/contractors/${btn.dataset.id}/agreement`, { json: {} });
  toast("Agreement ready to sign.", "ok"); go("aes");
});

// ---------------------------------------------------------------- appointments

VIEWS.appointments = async () => {
  let made = (S.data.recent || []).filter((r) => r.kind === "appointment");
  if (online()) { try { made = await api(`/api/records?site_id=${S.siteId}&kind=appointment&limit=500`); } catch {} }
  const pend = (await pendingItems()).filter((p) => p.body.kind === "appointment");
  const A = S.data.appointments, need = S.data.required_appointments || [];
  const madeTypes = {};
  made.forEach((r) => { const t = Object.keys(A).find((k) => r.summary.startsWith(A[k].title + ":")); if (t) (madeTypes[t] = madeTypes[t] || []).push(r); });
  pend.forEach((p) => { (madeTypes[p.body.payload.type] = madeTypes[p.body.payload.type] || []).push({ summary: "waiting to send" }); });
  render(`${head("Legal appointments", "The Construction Regulations require these people to be appointed in writing.", "board")}
    <h2>Required for this site</h2>
    <div class="card"><ul class="plain">${need.map((k) => { const m = madeTypes[k] || [];
      return `<li class="list-item" data-act="nav" data-to="appoint/${k}"><span class="dot ${m.length ? "green" : "red"}"></span>
        <div class="grow"><b>${esc(A[k].title)}</b> <span class="muted small">reg ${esc(A[k].reg)}</span>
        <div class="muted small">${m.length ? m.map((r) => esc(r.summary.split(": ").slice(1).join(": ") || r.summary)).join(", ") : "Not appointed"}</div></div><span>›</span></li>`; }).join("")}</ul></div>
    <h2>Other appointments</h2>
    <div class="card"><ul class="plain">${Object.keys(A).filter((k) => !need.includes(k)).map((k) => { const m = madeTypes[k] || [];
      return `<li class="list-item" data-act="nav" data-to="appoint/${k}"><span class="dot ${m.length ? "green" : "na"}"></span>
        <div class="grow"><b>${esc(A[k].title)}</b><div class="muted small">${m.length ? m.length + " appointed" : "Optional for this site"}</div></div><span>›</span></li>`; }).join("")}</ul></div>`);
};
VIEWS.appoint = (type) => {
  if (!can.write()) return render(`<div class="note warn">Your role cannot make appointments.</div>`);
  const A = S.data.appointments;
  type = A[type] ? type : Object.keys(A)[0];
  const t = A[type];
  const people = [];
  if (t.who !== "worker") S.data.users.forEach((u) => people.push([`user:${u.id}`, `${u.name} (login)`]));
  if (t.who !== "user") S.data.workers.forEach((w) => people.push([`worker:${w.id}`, `${w.name} · ${w.trade || "worker"}`]));
  render(`${head("Make an appointment", "In writing, signed by both. It goes into the safety file.", "appointments")}
    <div class="card"><label>Appointment</label><select id="ap-type">${Object.entries(A).map(([k, v]) => `<option value="${k}" ${k === type ? "selected" : ""}>${esc(v.title)} (reg ${esc(v.reg)})</option>`).join("")}</select>
      <label>Person</label><select id="ap-who"><option value="">Choose…</option>${people.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join("")}
        ${t.who === "any" ? `<option value="other">Someone else (type the name)</option>` : ""}</select>
      <input id="ap-other" class="hidden" placeholder="Full name">
      <label>${type === "operator" ? "Plant this person may operate" : "Scope (area, work, limits)"}</label>
      <textarea id="ap-scope" placeholder="${type === "operator" ? "TLB, excavator up to 20 t, site bakkie" : "Whole site"}"></textarea>
      <label>From</label><input id="ap-start" type="date" value="${todayStr()}"></div>
    <h2>Duties</h2><div class="card">${esc(t.duties)}</div>
    ${t.aes ? `<div class="note info small">The app also issues this appointment as a PDF for an advanced e-signature (or wet ink). You find it under Documents for signing.</div>` : ""}
    ${actionBar(`<button class="primary" data-act="ap-sign">Both sign</button>`)}`);
  $("#ap-type").onchange = (e) => go("appoint/" + e.target.value);
  $("#ap-who").onchange = (e) => $("#ap-other").classList.toggle("hidden", e.target.value !== "other");
  ACT["ap-sign"] = async (btn) => {
    const who = $("#ap-who").value;
    if (!who) return toast("Choose the person.", "bad");
    let appointee, name;
    if (who === "other") { name = $("#ap-other").value.trim(); if (!name) return toast("Type the name.", "bad"); appointee = { name }; }
    else if (who.startsWith("user:")) { const u = S.data.users.find((x) => "user:" + x.id === who); appointee = { user_id: u.id, name: u.name }; name = u.name; }
    else { const w = worker(who.slice(7)); appointee = { worker_id: w.id, name: w.name }; name = w.name; }
    const a = await signatureModal({ name: me().name, subtitle: `I appoint ${name} as ${t.title}.`, photo: false });
    if (!a) return;
    const b = await signatureModal({ name, subtitle: `I accept the appointment as ${t.title} and its duties.`, photo: false });
    if (!b) return;
    btn.disabled = true;
    const sigB = { ...b, role: "appointee", ...(appointee.user_id ? { user_id: appointee.user_id } : appointee.worker_id ? { worker_id: appointee.worker_id } : { name }) };
    await finishRecord("appointment", { type, appointee, scope: $("#ap-scope").value, start_date: $("#ap-start").value },
      [{ ...a, user_id: me().id, role: "appointer" }, sigB], { label: `${t.title}: ${name}` });
    go("appointments");
  };
};

// ---------------------------------------------------------------- documents for signing (AES)

VIEWS.aes = async () => {
  if (needOnline()) return;
  const docs = await api("/api/aes?site_id=" + S.siteId);
  const wait = docs.filter((d) => d.status !== "signed"), done = docs.filter((d) => d.status === "signed");
  const card = (d) => `<div class="card"><div class="row between"><b>${esc(d.title)}</b>
      <span class="badge ${d.status === "signed" ? "ok" : "warn"}">${d.status === "signed" ? (d.method === "aes" ? "AES signed" : "Wet ink") : "To sign"}</span></div>
    <div class="muted small">${esc(d.kind_label)} · signers: ${esc(d.signers.join("; "))}</div>
    ${d.status === "signed" ? `<p class="small">${esc(d.note || d.summary)}</p><a class="small" href="${d.signed_url}" target="_blank">Open the signed document</a>`
      : `<div class="grid2" style="margin-top:8px"><a class="btn" href="${d.original_url}" target="_blank">1. Download to sign</a>
        <button class="dark" data-act="aes-up" data-id="${d.id}" data-m="aes">2. Upload AES-signed PDF</button></div>
        <button class="link" data-act="aes-up" data-id="${d.id}" data-m="wet_ink">Signed by hand? Upload the scan</button>`}</div>`;
  render(`${head("Documents for signing", "Documents where the law needs an advanced electronic signature (AES) or a handwritten one.", "board")}
    <details class="card"><summary><b>How AES signing works</b></summary><ol class="small">
      <li>Download the PDF.</li><li>Each signer signs it with their advanced electronic signature from an accredited provider (for example LAWtrust AeSign, also through SigniFlow).</li>
      <li>Upload the signed PDF here. The app checks the signatures and that nobody changed the document after signing.</li></ol>
      <p class="small muted">No AES yet? Print, sign by hand, scan and upload. It goes into the safety file either way.</p></details>
    ${wait.length ? `<h2>To sign (${wait.length})</h2>${wait.map(card).join("")}` : `<div class="note ok">Nothing waits for a signature.</div>`}
    ${done.length ? `<h2>Signed</h2>${done.map(card).join("")}` : ""}
    ${can.manage() ? actionBar(`<button class="primary" data-act="nav" data-to="aes-new">+ New document for signing</button>`) : ""}`);
};
ACT["aes-up"] = async (el) => {
  const f = await pickFile(el.dataset.m === "aes" ? "application/pdf" : "image/*,application/pdf");
  if (!f) return;
  try {
    const r = await api(`/api/aes/${el.dataset.id}/signed`, { json: { method: el.dataset.m, file: f.data }, timeout: 120000 });
    toast(r.method === "aes" ? "Signatures checked: " + r.summary : "Scan saved.", "ok");
    route();
  } catch (e) { toast(friendly(e), "bad"); }
};
VIEWS["aes-new"] = () => {
  const K = S.data.aes_kinds;
  render(`${head("New document for signing", "", "aes")}
    <div class="card"><label>Type</label><select id="an-kind">${Object.entries(K).filter(([k]) => !["appointment", "mandatary_agreement"].includes(k))
      .map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
      <label>Title</label><input id="an-title">
      <div id="an-exc"><label>Excavation (location)</label><input id="an-loc"><label>Depth (m)</label><input id="an-depth" inputmode="decimal">
        <label>Soil conditions observed</label><textarea id="an-soil"></textarea><label>Decision</label><textarea id="an-dec" placeholder="Shoring not needed: stable material, sloped to angle of repose…"></textarea>
        <label>Conditions / controls</label><textarea id="an-cond"></textarea></div>
      <div id="an-txt" class="hidden"><label>Text of the document</label><textarea id="an-text" style="min-height:160px"></textarea>
        <button class="small" data-act="an-file">Or upload your own PDF</button> <span id="an-fname" class="muted small"></span></div>
      <label>Who must sign (one per line, with capacity)</label><textarea id="an-signers" placeholder="J. Smith, competent person (excavations)\nA. Engineer Pr.Eng"></textarea></div>
    ${actionBar(`<button class="primary" data-act="an-make">Make the PDF to sign</button>`)}`);
  let file = null;
  const sync = () => { const exc = $("#an-kind").value === "excavation_decision"; $("#an-exc").classList.toggle("hidden", !exc); $("#an-txt").classList.toggle("hidden", exc); };
  $("#an-kind").onchange = sync; sync();
  ACT["an-file"] = async () => { file = await pickFile("application/pdf"); if (file) $("#an-fname").textContent = file.name; };
  ACT["an-make"] = (btn) => busy(btn, "Making…", async () => {
    const kind = $("#an-kind").value;
    const body = { kind, site_id: S.siteId, title: $("#an-title").value, signers: $("#an-signers").value.split("\n").map((x) => x.trim()).filter(Boolean) };
    if (kind === "excavation_decision") body.fields = { location: $("#an-loc").value, depth: $("#an-depth").value, soil: $("#an-soil").value, decision: $("#an-dec").value, conditions: $("#an-cond").value };
    else if (file) body.file = file.data; else body.text = $("#an-text").value;
    await api("/api/aes", { json: body, timeout: 120000 });
    toast("Ready to sign.", "ok"); go("aes");
  });
};

// ---------------------------------------------------------------- monthly audit (reg 5(1)(o)-(p))

VIEWS.audit = async () => {
  let audits = [], acks = [];
  if (online()) {
    try { audits = await api(`/api/records?site_id=${S.siteId}&kind=audit&limit=50`); acks = await api(`/api/records?site_id=${S.siteId}&kind=audit_ack&limit=50`); } catch {}
  } else audits = (S.data.recent || []).filter((r) => r.kind === "audit");
  const last = audits[0];
  const acked = last && acks.some((a) => a.record_date >= last.record_date);
  render(`${head("Monthly audit", "At least every 30 days. The report goes to the principal contractor within 7 days.", "board")}
    ${last ? `<div class="card"><div class="row between"><b>Last audit ${esc(last.record_date)}</b><span class="badge ${acked ? "ok" : "warn"}">${acked ? "Report received" : "Report not received yet"}</span></div>
      <p class="small muted">${esc(last.summary)}</p>
      <div class="grid2"><button data-act="nav" data-to="record/${last.id}">Open</button>
        ${!acked && can.write() ? `<button class="dark" data-act="audit-ack" data-id="${last.id}">Principal contractor received it</button>` : ""}</div></div>` : `<div class="note warn">No audit yet.</div>`}
    ${audits.slice(1).map((a) => `<div class="card tap" data-act="nav" data-to="record/${a.id}"><div class="grow"><b>${esc(a.record_date)}</b><div class="muted small">${esc(a.summary)}</div></div><span>›</span></div>`).join("")}
    ${actionBar(`<button class="primary" data-act="nav" data-to="audit-new">Start an audit</button>`)}`);
};
ACT["audit-ack"] = async (btn) => {
  const s = await signatureModal({ name: me().name, subtitle: "For the principal contractor: I received the audit report.", photo: false });
  if (!s) return;
  btn.disabled = true;
  await finishRecord("audit_ack", { audit_id: btn.dataset.id }, [{ ...s, user_id: me().id, role: "principal contractor" }], { label: "Audit report received" });
  route();
};
VIEWS["audit-new"] = async () => {
  if (needOnline()) return;
  const pre = await api("/api/audit/prefill?site_id=" + S.siteId);
  const d = { items: pre.items.map((i) => ({ ...i, result: i.result || "" })), findings: [], notes: "" };
  const draw = () => {
    render(`${head("Audit", "The board has filled in what it knows. Check each item on site and change it where needed.", "audit")}
      ${d.items.map((it, i) => `<div class="card"><b>${esc(it.title)}</b> <span class="muted small">reg ${esc(it.reg)}</span>
        <div class="answer">${["ok", "gap", "na"].map((v) => `<button class="${v} ${it.result === v ? "on" : ""}" data-act="au-ans" data-i="${i}" data-v="${v}">${{ ok: "OK", gap: "Gap", na: "N/A" }[v]}</button>`).join("")}</div>
        ${it.result === "gap" ? `<input data-au-note="${i}" value="${esc(it.note)}" placeholder="What is wrong?">` : ""}</div>`).join("")}
      <h2>Findings and actions</h2>
      ${d.findings.map((f, i) => `<div class="card"><input data-fi="${i}" data-k="finding" value="${esc(f.finding)}" placeholder="Finding">
        <input data-fi="${i}" data-k="action" value="${esc(f.action)}" placeholder="Action to take">
        <div class="grid2"><input data-fi="${i}" data-k="owner" value="${esc(f.owner)}" placeholder="Responsible"><input data-fi="${i}" data-k="due" type="date" value="${esc(f.due)}"></div></div>`).join("")}
      <button data-act="au-find">+ Add a finding</button>
      <label style="margin-top:12px">Notes</label><textarea id="au-notes">${esc(d.notes)}</textarea>
      ${actionBar(`<button class="primary" data-act="au-sign">Sign the audit</button>`)}`);
    $("#view").oninput = (e) => {
      if (e.target.dataset.auNote !== undefined) d.items[+e.target.dataset.auNote].note = e.target.value;
      if (e.target.dataset.fi !== undefined) d.findings[+e.target.dataset.fi][e.target.dataset.k] = e.target.value;
      if (e.target.id === "au-notes") d.notes = e.target.value;
    };
  };
  ACT["au-ans"] = (el) => { const y = scrollY; d.items[+el.dataset.i].result = el.dataset.v; draw(); scrollTo(0, y); };
  ACT["au-find"] = () => { const y = scrollY; d.findings.push({ finding: "", action: "", owner: "", due: "" }); draw(); scrollTo(0, y); };
  ACT["au-sign"] = async (btn) => {
    if (d.items.some((i) => !i.result)) return toast("Answer every item.", "bad");
    const s = await signatureModal({ name: me().name, subtitle: "Auditor: this audit is a true record of what I found.", photo: false });
    if (!s) return;
    btn.disabled = true;
    await finishRecord("audit", { items: d.items.map((i) => ({ key: i.key, result: i.result, note: i.note })), findings: d.findings,
      notes: d.notes, board: pre.board, report_due: pre.report_due }, [{ ...s, user_id: me().id, role: "auditor" }], { label: "Audit" });
    go("audit");
  };
  draw();
};

// ---------------------------------------------------------------- incidents and investigations

VIEWS.incidents = async () => {
  if (needOnline()) return;
  const list = await api("/api/incidents?site_id=" + S.siteId);
  render(`${head("Incidents", "Investigate every incident within 7 days (GAR 9). Report serious ones to the Department within 7 days (OHS Act s24).", "board")}
    ${list.length ? list.map((r) => { const left = 7 - r.days_open, done = !!r.investigation_id;
      const st = done ? "green" : left < 0 ? "red" : r.possibly_reportable ? "red" : "amber";
      return `<div class="card"><div class="row between"><b>${esc(r.record_date)}</b><span class="badge ${st}">${done ? "Investigated" : left < 0 ? `${-left} day(s) late` : `${left} day(s) left`}</span></div>
        <p class="small">${esc(r.summary)}</p>${r.possibly_reportable && !done ? `<div class="note bad small">Possibly reportable to the Department of Employment and Labour.</div>` : ""}
        <div class="grid2"><button data-act="nav" data-to="record/${r.id}">Open</button>
          ${done ? `<button data-act="pdf" data-path="/api/records/${r.id}/annexure1.pdf">Annexure 1</button>` : `<button class="primary" data-act="nav" data-to="investigate/${r.id}">Investigate</button>`}</div></div>`;
    }).join("") : `<div class="note ok">No incidents recorded.</div>`}
    ${can.write() ? actionBar(`<button class="danger" data-act="nav" data-to="incident">🚨 Report an incident</button>`) : ""}`);
};
VIEWS.investigate = async (id) => {
  if (needOnline()) return;
  const inc = await api("/api/records/" + id);
  const p = inc.payload;
  const d = { findings: "", causes: "", actions: [{ action: "", owner: "", due: "" }], reportable: !!p.possibly_reportable,
    dol: { date: "", ref: "" }, cf: { date: "", ref: "" }, reason: "" };
  const draw = () => {
    render(`${head("Investigate", `Incident of ${esc(inc.record_date)}: ${esc((p.description || "").slice(0, 120))}`, "incidents")}
      <div class="card"><label>What did the investigation find?</label><textarea id="iv-f">${esc(d.findings)}</textarea>
        <label>Root causes (one per line)</label><textarea id="iv-c">${esc(d.causes)}</textarea></div>
      <h2>Corrective actions</h2>
      ${d.actions.map((a, i) => `<div class="card"><input data-ai="${i}" data-k="action" value="${esc(a.action)}" placeholder="Action">
        <div class="grid2"><input data-ai="${i}" data-k="owner" value="${esc(a.owner)}" placeholder="Responsible"><input data-ai="${i}" data-k="due" type="date" value="${esc(a.due)}"></div></div>`).join("")}
      <button data-act="iv-add">+ Add an action</button>
      <h2>Reporting</h2><div class="card"><label class="check"><input type="checkbox" id="iv-rep" ${d.reportable ? "checked" : ""}> Reportable under section 24 of the OHS Act</label>
        ${d.reportable ? `<label>Reported to the Department of Employment and Labour on</label><div class="grid2"><input id="iv-dd" type="date" value="${esc(d.dol.date)}"><input id="iv-dr" placeholder="Reference" value="${esc(d.dol.ref)}"></div>
          <label>Reported to the Compensation Fund (W.Cl.2) on</label><div class="grid2"><input id="iv-cd" type="date" value="${esc(d.cf.date)}"><input id="iv-cr" placeholder="Reference" value="${esc(d.cf.ref)}"></div>`
          : `<label>Why it is not reportable</label><input id="iv-why" value="${esc(d.reason)}" placeholder="First aid only, no lost time">`}</div>
      ${actionBar(`<button class="primary" data-act="iv-sign">Sign the investigation</button>`)}`);
    $("#view").oninput = $("#view").onchange = (e) => {
      const t = e.target;
      if (t.id === "iv-f") d.findings = t.value; if (t.id === "iv-c") d.causes = t.value; if (t.id === "iv-why") d.reason = t.value;
      if (t.id === "iv-dd") d.dol.date = t.value; if (t.id === "iv-dr") d.dol.ref = t.value; if (t.id === "iv-cd") d.cf.date = t.value; if (t.id === "iv-cr") d.cf.ref = t.value;
      if (t.dataset.ai !== undefined) d.actions[+t.dataset.ai][t.dataset.k] = t.value;
      if (t.id === "iv-rep") { d.reportable = t.checked; const y = scrollY; draw(); scrollTo(0, y); }
    };
  };
  ACT["iv-add"] = () => { const y = scrollY; d.actions.push({ action: "", owner: "", due: "" }); draw(); scrollTo(0, y); };
  ACT["iv-sign"] = async (btn) => {
    if (!d.findings.trim()) return toast("Write what the investigation found.", "bad");
    if (d.reportable && !d.dol.date) return toast("Give the date you reported it to the Department.", "bad");
    const s = await signatureModal({ name: me().name, subtitle: "Investigator: this investigation is true and complete.", photo: false });
    if (!s) return;
    btn.disabled = true;
    await finishRecord("investigation", { incident_id: id, findings: d.findings, root_causes: d.causes.split("\n").map((x) => x.trim()).filter(Boolean),
      actions: d.actions.filter((a) => a.action.trim()), reportable: d.reportable, reported_dol: d.dol, reported_cf: d.cf, not_reportable_reason: d.reason },
      [{ ...s, user_id: me().id, role: "investigator" }], { label: "Investigation" });
    go("incidents");
  };
  draw();
};
