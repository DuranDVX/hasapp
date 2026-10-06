// Site app core: login, offline cache, outbox sync, router, Today/Records/File/More.
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ls = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
  del(k) { try { localStorage.removeItem(k); } catch {} },
};
const S = { token: ls.get("ss-token"), me: null, siteId: ls.get("ss-site"), data: null, pending: 0, syncing: false };
const ACT = {};          // data-act handlers, registered by each view
const VIEWS = {};        // route name -> render function

let toastTimer;
function toast(msg, kind = "") {
  let el = $(".toast");
  if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.appendChild(el); }
  el.className = "toast " + kind; el.textContent = msg; el.classList.remove("hidden");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.add("hidden"), kind === "bad" ? 7000 : 3500);
}
function friendly(e) {
  if (e.name === "AbortError") return "That took too long. Check your signal and try again.";
  if (e instanceof TypeError) return "No signal. Try again when you have a connection.";
  return e.message || "Something went wrong. Try again.";
}
const online = () => navigator.onLine !== false;

// One page format everywhere: title, one-line purpose, optional back link.
function head(title, purpose = "", back = "") {
  return `<div class="page-head">${back ? `<button class="link back" data-act="${back === "history" ? "back" : "nav"}" data-to="${esc(back)}">‹ Back</button>` : ""}
    <h1>${esc(title)}</h1>${purpose ? `<p>${purpose}</p>` : ""}</div>`;
}
// The main action of a screen sits in the same place on every screen.
function actionBar(html) { return `<div class="action-bar noprint"><div>${html}</div></div>`; }

// Light theme by default: easier to read in sunlight.
(function theme() { document.documentElement.dataset.theme = ls.get("ss-theme") || "light"; })();

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (S.token) headers["X-Token"] = S.token;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), opts.timeout || 60000);
  let res;
  try { res = await fetch(path, { method: opts.method || (opts.body ? "POST" : "GET"), headers, body: opts.body, signal: ctl.signal }); }
  finally { clearTimeout(t); }
  if (!res.ok) {
    let msg = ""; try { msg = (await res.json()).detail || ""; } catch {}
    const e = new Error(typeof msg === "string" ? msg : "Check the form and try again."); e.status = res.status;
    if (res.status === 401 && S.token && !path.startsWith("/api/login")) { logout(true); }
    throw e;
  }
  if (opts.raw) return res;
  return res.json();
}
async function openPdf(path, filename) {
  toast("Building the PDF…");
  try {
    const res = await api(path, { raw: true, timeout: 180000 });
    const blob = await res.blob(), url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.target = "_blank";
    if (filename) a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    toast("PDF ready.", "ok");
  } catch (e) { toast(friendly(e), "bad"); }
}
async function busy(btn, label, fn) {
  const old = btn ? btn.textContent : ""; if (btn) { btn.disabled = true; btn.textContent = label; }
  try { return await fn(); } catch (e) { toast(friendly(e), "bad"); } finally { if (btn) { btn.disabled = false; btn.textContent = old; } }
}

// ---------------------------------------------------------------- data + sync

async function loadMe() {
  if (online()) {
    try { S.me = await api("/api/me"); await IDB.set("me", S.me); return; }
    catch (e) { if (e.status === 401) throw e; }
  }
  S.me = await IDB.get("me");
  if (!S.me) throw new Error("No signal. Log in once with a signal to use the app offline.");
}
async function loadSite(force = false) {
  if (!S.siteId) return;
  const key = "sync:" + S.siteId;
  if (online() && (force || !S.data || S.data.site.id !== S.siteId)) {
    try { S.data = await api("/api/sync?site_id=" + encodeURIComponent(S.siteId)); await IDB.set(key, S.data); renderHeader(); return; }
    catch (e) { if (e.status === 404) { S.siteId = null; ls.del("ss-site"); return; } }
  }
  if (!S.data || S.data.site.id !== S.siteId) S.data = await IDB.get(key);
  renderHeader();
}
const worker = (id) => (S.data?.workers || []).find((w) => w.id === id);
const risk = (id) => (S.data?.risks || []).find((r) => r.id === id);
const can = { write: () => S.me?.can_write, manage: () => S.me?.can_manage, owner: () => S.me?.user.role === "owner" };

// Outbox: finished records wait here until the server accepts them.
async function enqueue(body) {
  await IDB.outbox.put({ id: body.client_id, body, created: Date.now(), tries: 0, error: "" });
  await flush();
}
async function flush() {
  if (S.syncing || !S.token) return;
  S.syncing = true;
  try {
    const items = (await IDB.outbox.all()).sort((a, b) => a.created - b.created);
    for (const it of items) {
      if (!online()) break;
      if (it.error && it.tries > 3) continue;
      try {
        await api("/api/records", { json: it.body, timeout: 120000 });
        await IDB.outbox.del(it.id);
      } catch (e) {
        it.tries++;
        if (e instanceof TypeError || e.name === "AbortError" || e.status >= 500 || e.status === 409 || e.status === 429) { await IDB.outbox.put(it); break; }
        it.error = e.message || "Rejected"; await IDB.outbox.put(it);
      }
    }
  } finally {
    S.syncing = false;
    S.pending = (await IDB.outbox.all()).length;
    renderHeader();
  }
}
// Re-draw list screens after a sync; never re-draw a form the user is filling in.
function refreshIfIdle() {
  const name = (location.hash.slice(1) || "board").split("/")[0];
  if (["board", "today", "records", "people", "workers"].includes(name) && !$(".modal")) route();
}
window.addEventListener("online", () => { renderHeader(); flush().then(() => loadSite(true)).then(refreshIfIdle); });
window.addEventListener("offline", renderHeader);
setInterval(() => { if (online()) flush(); }, 30000);

function newId() { return (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)); }

// ---------------------------------------------------------------- shell

function renderHeader() {
  const h = $("header");
  if (!S.me) { h.classList.add("hidden"); $("nav.bottom").classList.add("hidden"); return; }
  h.classList.remove("hidden"); $("nav.bottom").classList.remove("hidden");
  $("#site-name").textContent = S.data?.site?.name ? "📍 " + S.data.site.name : "Choose a site";
  const b = $("#sync");
  if (!online()) { b.className = "sync off"; b.textContent = S.pending ? `Offline · ${S.pending} waiting` : "Offline"; }
  else if (S.pending) { b.className = "sync pending"; b.textContent = `${S.pending} to send`; }
  else { b.className = "sync ok"; b.textContent = "Up to date"; }
}
function render(html) { $("#view").innerHTML = html; window.scrollTo(0, 0); }
function go(hash) { if (location.hash === "#" + hash) route(); else location.hash = hash; }

const NAV_OF = { board: "board", today: "board", records: "records", record: "records", people: "people", workers: "people",
  worker: "people", contractors: "people", contractor: "people", visitors: "people", file: "file", more: "more" };
const FAB_ON = ["board", "today", "records", "people", "workers", "contractors", "visitors"];
async function route() {
  const [name, ...args] = (location.hash.slice(1) || "board").split("/");
  document.querySelectorAll("nav.bottom a").forEach((a) => a.classList.toggle("on", a.dataset.nav === NAV_OF[name]));
  $(".fab")?.classList.toggle("hidden", !S.me || !can.write() || !FAB_ON.includes(name));
  if (!S.token) return VIEWS[name === "signup" ? "signup" : "login"]();
  if (!S.me) return;
  if (!S.siteId || !S.data) { if (!["sites", "site", "more", "profile", "company", "users", "esign"].includes(name)) return VIEWS.sites(); }
  const view = VIEWS[name === "today" ? "board" : name] || VIEWS.board;
  try { await view(...args); } catch (e) { console.error(e); render(`<div class="note bad">${esc(friendly(e))}</div>`); }
}
window.addEventListener("hashchange", route);

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-act]");
  if (!el) return;
  const fn = ACT[el.dataset.act];
  if (fn) { e.preventDefault(); fn(el, e); }
});

// ---------------------------------------------------------------- login / signup

VIEWS.login = () => {
  render(`<h1>Log in</h1><p class="muted">Site health and safety, without the paper.</p>
    <div class="card"><label>Email</label><input id="l-email" type="email" autocomplete="username">
    <label>Password</label><input id="l-pw" type="password" autocomplete="current-password">
    <button class="primary" data-act="login">Log in</button></div>
    <p class="center"><a href="#signup">New company? Create an account</a></p>`);
  $("#l-pw").onkeydown = (e) => { if (e.key === "Enter") ACT.login($("[data-act=login]")); };
};
ACT.login = (btn) => busy(btn, "Logging in…", async () => {
  const r = await api("/api/login", { json: { email: $("#l-email").value.trim(), password: $("#l-pw").value } });
  await afterLogin(r.token);
});
VIEWS.signup = () => {
  render(`<h1>Create your company</h1>
    <div class="card"><label>Company name</label><input id="s-co">
    <label>Your name</label><input id="s-name" autocomplete="name">
    <label>Email</label><input id="s-email" type="email" autocomplete="username">
    <label>Password (8 or more characters)</label><input id="s-pw" type="password" autocomplete="new-password">
    <label>Invite code (pilot)</label><input id="s-inv">
    <button class="primary" data-act="signup">Create account</button></div>
    <p class="center"><a href="#login">I already have a login</a></p>`);
};
ACT.signup = (btn) => busy(btn, "Creating…", async () => {
  const r = await api("/api/signup", { json: { company: $("#s-co").value, name: $("#s-name").value, email: $("#s-email").value,
    password: $("#s-pw").value, invite: $("#s-inv").value } });
  await afterLogin(r.token); go("site/new");
});
async function afterLogin(token) {
  S.token = token; ls.set("ss-token", token);
  await loadMe();
  if (S.siteId && !S.me.sites.find((x) => x.id === S.siteId)) { S.siteId = null; ls.del("ss-site"); }
  if (!S.siteId && S.me.sites.filter((x) => x.status === "active").length === 1) { S.siteId = S.me.sites.find((x) => x.status === "active").id; ls.set("ss-site", S.siteId); }
  await loadSite(true);
  renderHeader(); route();
}
async function logout(expired) {
  if (!expired) { try { await api("/api/logout", { method: "POST" }); } catch {} }
  S.token = null; S.me = null; S.data = null; ls.del("ss-token");
  await IDB.del("me");
  renderHeader(); go("login");
  if (expired) toast("Please log in again.", "bad");
}
ACT.logout = async () => {
  const n = (await IDB.outbox.all()).length;
  if (n && !confirm(`${n} record(s) have not been sent yet. They stay on this device. Log out anyway?`)) return;
  logout(false);
};

// ---------------------------------------------------------------- sites

VIEWS.sites = () => {
  const sites = S.me.sites;
  render(`${head("Choose a site", "Pick the site you work on today.")}
    ${sites.length ? `<div class="stack">${sites.map((x) => `<div class="card tap" data-act="pick-site" data-id="${x.id}">
      <div class="ico">🏗️</div><div class="grow"><b>${esc(x.name)}</b><div class="muted small">${esc(x.address || "")}</div></div>
      ${x.status === "closed" ? '<span class="badge">Closed</span>' : ""}</div>`).join("")}</div>`
      : `<div class="note warn">No sites yet.</div>`}
    ${can.manage() ? `<button class="primary" data-act="nav" data-to="site/new">+ Add a site</button>` : ""}`);
};
ACT["pick-site"] = async (el) => {
  S.siteId = el.dataset.id; ls.set("ss-site", S.siteId); S.data = null;
  await loadSite(true);
  if (!S.data) return toast("Open this site once with a signal so it works offline.", "bad");
  go("board"); autoOfflineFile();
};
ACT.nav = (el) => go(el.dataset.to);
VIEWS.site = (id) => {
  const x = id === "new" ? {} : S.me.sites.find((s) => s.id === id) || {};
  render(`${head(id === "new" ? "New site" : "Edit site", "", "sites")}<div class="card">
    <label>Site name</label><input id="st-name" value="${esc(x.name || "")}" placeholder="Erf 1234, Plettenberg Bay">
    <label>Address</label><input id="st-addr" value="${esc(x.address || "")}">
    <label>Client</label><input id="st-client" value="${esc(x.client || "")}">
    <label>Client's H&S agent</label><input id="st-agent" value="${esc(x.client_agent || "")}">
    <label>Emergency info (nearest hospital, numbers)</label><textarea id="st-em">${esc(x.emergency || "")}</textarea>
    <div class="grid2"><div><label>Start date</label><input id="st-start" type="date" value="${esc(x.start_date || "")}"></div>
    <div><label>End date</label><input id="st-end" type="date" value="${esc(x.end_date || "")}"></div></div>
    ${id !== "new" ? `<label>Status</label><select id="st-status"><option value="active">Active</option><option value="closed" ${x.status === "closed" ? "selected" : ""}>Closed</option></select>` : ""}
    <button class="primary" data-act="save-site" data-id="${esc(id)}">Save site</button></div>`);
};
ACT["save-site"] = (btn) => busy(btn, "Saving…", async () => {
  const id = btn.dataset.id;
  const body = { name: $("#st-name").value, address: $("#st-addr").value, client: $("#st-client").value,
    client_agent: $("#st-agent").value, emergency: $("#st-em").value, start_date: $("#st-start").value, end_date: $("#st-end").value };
  if ($("#st-status")) body.status = $("#st-status").value;
  const x = id === "new" ? await api("/api/sites", { json: body }) : await api("/api/sites/" + id, { method: "PUT", json: body });
  await loadMe();
  S.siteId = x.id; ls.set("ss-site", x.id); await loadSite(true);
  toast("Site saved.", "ok"); go(id === "new" ? "setup" : "board");
});

// ---------------------------------------------------------------- today

const todayStr = () => localDate();
async function pendingItems() { return (await IDB.outbox.all()).filter((i) => i.body.site_id === S.siteId); }

// ---------------------------------------------------------------- records

VIEWS.records = async (kind = "") => {
  const pend = await pendingItems();
  let list = S.data.recent || [];
  if (online()) { try { list = await api(`/api/records?site_id=${S.siteId}&limit=150${kind ? "&kind=" + kind : ""}`); } catch {} }
  else if (kind) list = list.filter((r) => r.kind === kind);
  const kinds = { "": "All", task_sheet: "Task sheets", toolbox_talk: "Talks", check: "Checks", visitor: "Visitors",
    incident: "Incidents", investigation: "Investigations", induction: "Inductions", appointment: "Appointments", audit: "Audits",
    permit: "Permits", ppe_issue: "PPE issue", observation: "Observations", drill: "Drills", meeting: "Meetings" };
  render(`${head("Records", "Every signed record for this site. Tap one to see it, print it or check it.")}
    <div class="chips">${Object.entries(kinds).map(([k, v]) => `<button class="chip ${k === kind ? "on" : ""}" data-act="nav" data-to="records/${k}">${v}</button>`).join("")}</div>
    ${pend.length ? `<h2>Waiting to send</h2><div class="card"><ul class="plain">${pend.map((p) => `<li><div class="row between"><div class="grow"><b>${esc(p.label || p.body.kind)}</b>
      <div class="muted small">${esc(p.body.record_date)}${p.error ? ` · <span class="crit">${esc(p.error)}</span>` : ""}</div></div>
      ${p.error ? `<button class="small" data-act="discard" data-id="${esc(p.id)}">Remove</button>` : '<span class="badge">Waiting</span>'}</div></li>`).join("")}</ul>
      ${online() ? `<button class="small" data-act="flush">Send now</button>` : ""}</div>` : ""}
    ${list.length ? `<div class="card"><ul class="plain">${list.map((r) => `<li class="list-item" data-act="nav" data-to="record/${r.id}">
      <div class="grow"><b>${esc(r.kind_label)}</b> <span class="muted small">${esc(r.record_date)}</span><div class="muted small">${esc(r.summary)}</div></div><span>›</span></li>`).join("")}</ul></div>`
      : `<p class="muted">No records yet.</p>`}
    ${!online() ? `<p class="muted small">Offline: this list shows the last 14 days.</p>` : ""}`);
};
ACT.flush = async () => { await flush(); route(); };
ACT.discard = async (el) => {
  if (!confirm("Remove this record from the device? It was rejected by the server and will not be sent.")) return;
  await IDB.outbox.del(el.dataset.id); S.pending = (await IDB.outbox.all()).length; renderHeader(); route();
};

VIEWS.record = async (id) => {
  if (!online()) return render(`<div class="note warn">Open a stored record when you have a signal.</div>`);
  const r = await api("/api/records/" + id);
  const p = r.payload;
  let body = "";
  if (r.kind === "task_sheet") {
    body = p.tasks.map((t, i) => `<div class="card"><b>Task ${i + 1}: ${esc(t.description)}</b> <span class="muted small">${esc(t.location)}</span>
      ${t.assessed ? "" : `<div class="note warn">Not covered by an approved risk assessment.</div>`}
      ${t.risks.map((x) => `<div class="hazard"><b>${esc(x.activity)}</b> ${x.approved ? "" : '<span class="badge warn">Not approved</span>'}
        ${x.hazards.map((h) => `<div>• ${esc(h.hazard)} <span class="muted small">(${esc(h.risk)})</span><div class="muted small">${h.controls.map(esc).join("; ")}</div></div>`).join("")}</div>`).join("")}
      <div class="small"><b>PPE:</b> ${esc(t.ppe.join(", ") || "-")}</div>
      <div class="small"><b>Workers:</b> ${esc(t.workers.map((w) => w.name).join(", ") || "-")}</div></div>`).join("")
      + (p.unmatched.length ? `<div class="note warn"><b>Tasks without a risk assessment</b>${p.unmatched.map((u) => `<div>• ${esc(u.description)}</div>`).join("")}</div>` : "")
      + (p.notes ? `<div class="card"><b>Notes</b><div>${esc(p.notes)}</div></div>` : "");
  } else if (r.kind === "toolbox_talk") {
    body = `<div class="card"><b>${esc(p.title || p.topic)}</b><div class="talk-text">${esc(p.text)}</div>
      ${p.group_photo?.url ? `<img src="${p.group_photo.url}" style="width:100%;border-radius:10px;margin-top:8px">` : ""}</div>`;
  } else if (r.kind === "check") {
    body = `<div class="note ${p.result === "fail" ? "bad" : p.result === "defects" ? "warn" : "ok"}">${esc(p.title)} ${esc(p.plant_name)}: ${p.result === "fail" ? "FAIL — do not use" : p.result === "defects" ? "pass with defects" : "pass"}</div>
      <div class="card"><table class="simple">${p.items.map((it) => `<tr><td>${esc(it.q)}${it.critical ? ' <span class="crit">*</span>' : ""}${it.note ? `<div class="muted small">${esc(it.note)}</div>` : ""}
      ${it.photo?.url ? `<img class="thumb" src="${it.photo.url}">` : ""}</td><td><b class="${it.answer === "defect" ? "crit" : ""}">${{ ok: "OK", defect: "DEFECT", na: "N/A" }[it.answer]}</b></td></tr>`).join("")}</table></div>`;
  } else if (r.kind === "incident") {
    body = `${p.possibly_reportable ? `<div class="note bad">Possibly reportable: ${esc(p.reportable_reason)}</div>` : ""}
      <div class="card"><b>${esc(S.data.incident_types[p.type] || p.type)}</b><p>${esc(p.description)}</p>
      <div class="small"><b>When:</b> ${esc(p.occurred_at)} · <b>Where:</b> ${esc(p.location)}</div>
      ${p.people.map((x) => `<div class="small">• ${esc(x.name)}: ${esc(x.injury)} (${esc(x.treatment)})</div>`).join("")}
      ${p.immediate_actions ? `<div class="small"><b>Actions:</b> ${esc(p.immediate_actions)}</div>` : ""}
      <div class="chips">${(p.photos || []).map((x) => x.url ? `<img class="thumb" src="${x.url}">` : "").join("")}</div></div>`;
  } else if (r.kind === "induction") {
    body = `<div class="card"><b>${esc(p.worker_name)}</b><div class="small" style="white-space:pre-wrap">${esc(p.induction_text)}</div>
      ${p.consent ? `<div class="note ok small">Worker agreed to e-signatures and the privacy notice.</div>` : ""}</div>`;
  } else if (r.kind === "visitor") {
    body = `<div class="card"><table class="simple">${[["Visitor", p.name], ["Company", p.company], ["Purpose", p.purpose], ["Host", p.host],
      ["Time in", (p.time_in || "").replace("T", " ").slice(0, 16)], ["PPE issued", (p.ppe || []).join(", ")]].map(([a, b]) => `<tr><td class="muted">${a}</td><td>${esc(b || "-")}</td></tr>`).join("")}</table></div>`;
  } else if (r.kind === "appointment") {
    body = `<div class="card"><b>${esc(p.title)}</b> <span class="muted small">reg ${esc(p.reg)}</span>
      <p><b>Appointee:</b> ${esc(p.appointee.name)}</p><p class="small">${esc(p.duties)}</p>${p.scope ? `<p class="small"><b>Scope:</b> ${esc(p.scope)}</p>` : ""}
      ${p.aes_required ? `<div class="note info small">Also issued for an advanced e-signature. <a href="#aes">Documents for signing</a></div>` : ""}</div>`;
  } else if (r.kind === "audit") {
    body = `<div class="card"><b>Score ${p.score}%</b><ul class="plain">${p.items.map((it) => `<li class="row"><span class="dot ${it.result === "ok" ? "green" : it.result === "gap" ? "red" : "na"}"></span>
      <div class="grow">${esc(it.title)}${it.note ? `<div class="muted small">${esc(it.note)}</div>` : ""}</div></li>`).join("")}</ul></div>
      ${p.findings.length ? `<div class="card"><b>Findings</b>${p.findings.map((f) => `<div class="small" style="margin-top:6px">• ${esc(f.finding)}: ${esc(f.action)} (${esc(f.owner)}, ${esc(f.due)})</div>`).join("")}</div>` : ""}`;
  } else if (r.kind === "investigation") {
    body = `<div class="card"><b>Incident of ${esc(p.incident_date)}</b><p>${esc(p.findings)}</p>
      ${p.actions.map((a) => `<div class="small">• ${esc(a.action)} (${esc(a.owner)}, ${esc(a.due)})</div>`).join("")}
      <p class="small">${p.reportable ? `Reported to DEL ${esc(p.reported_dol.date)} (ref ${esc(p.reported_dol.ref)})` : "Not reportable: " + esc(p.not_reportable_reason)}</p></div>`;
  } else if (S.data.forms[r.kind]) {
    const fmt = (v) => v == null || v === "" ? "-" : v === true ? "Yes" : v === false ? "No" : Array.isArray(v) ? v.join(", ") : typeof v === "object" ? (v.name || v.summary || "-") : v;
    body = `<div class="card"><table class="simple">${p.fields.map((f) => `<tr><td class="muted">${esc(f.label)}</td><td>${esc(fmt(f.value))}</td></tr>`).join("")}</table>
      <p class="muted small">${esc(p.reg)}</p></div>`;
  } else if (r.kind === "audit_ack") {
    body = `<div class="card">Report of the audit of ${esc(p.audit_date)} received.</div>`;
  }
  render(`${head(r.kind_label, `${esc(r.record_date)} · by ${esc(r.created_name)} · record #${r.seq}`, "history")}${body}
    <h2>Signatures</h2><div class="card"><ul class="plain">${r.signatures.map((g) => `<li class="row">
      ${g.photo_url ? `<img class="avatar" src="${g.photo_url}">` : `<div class="avatar">${esc(g.name[0])}</div>`}
      <div class="grow"><b>${esc(g.name)}</b><div class="muted small">${esc(g.role)} · ${esc(g.signed_at.replace("T", " ").slice(0, 16))}</div></div>
      <img class="sigimg" src="${g.image_url}"></li>`).join("")}</ul></div>
    <p class="muted small">Hash ${esc(r.hash.slice(0, 20))}… · received ${esc(r.received_at.replace("T", " ").slice(0, 16))} UTC${r.lat ? ` · GPS ${r.lat.toFixed(4)}, ${r.lng.toFixed(4)}` : ""}</p>
    ${actionBar(`<div class="grid2"><button class="dark" data-act="pdf" data-path="/api/records/${r.id}/pdf">Open PDF</button>
      <button data-act="pdf" data-path="/api/records/${r.id}/pdf?print=1">🖨️ Print copy</button></div>
      ${r.kind === "incident" ? `<div class="grid2"><button data-act="pdf" data-path="/api/records/${r.id}/annexure1.pdf">Annexure 1</button>
        <button class="primary" data-act="nav" data-to="investigate/${r.id}">Investigate</button></div>` : ""}`)}`);
};
ACT.back = () => history.back();
ACT.pdf = (el) => openPdf(el.dataset.path);

// ---------------------------------------------------------------- safety file

// The site tablet keeps a full copy of the safety file, so an inspector
// can see it when there is no signal (reg 7(1)(b): "keep on site").
async function offlineFile() { try { return await IDB.get("offline-file:" + S.siteId); } catch { return null; } }
async function saveOfflineFile(quiet = false) {
  if (!online()) { if (!quiet) toast("No signal. The last saved copy stays on this device.", "bad"); return; }
  try {
    const res = await api(`/api/sites/${S.siteId}/file.pdf`, { raw: true, timeout: 300000 });
    const blob = await res.blob();
    await IDB.set("offline-file:" + S.siteId, { blob, at: Date.now(), bytes: blob.size });
    if (!quiet) toast("Safety file saved on this device.", "ok");
  } catch (e) { if (!quiet) toast(friendly(e), "bad"); }
}
async function autoOfflineFile() {
  const f = await offlineFile();
  if (online() && (!f || Date.now() - f.at > 12 * 3600 * 1000)) saveOfflineFile(true);
}
ACT["offline-save"] = (btn) => busy(btn, "Saving…", async () => { await saveOfflineFile(); route(); });
ACT["offline-open"] = async () => {
  const f = await offlineFile();
  if (!f) return toast("No copy on this device yet.", "bad");
  const url = URL.createObjectURL(f.blob), a = document.createElement("a");
  a.href = url; a.target = "_blank"; document.body.appendChild(a); a.click(); a.remove();
};

VIEWS.file = async () => {
  const f = await offlineFile();
  const age = f ? Math.round((Date.now() - f.at) / 3600000) : null;
  const offlineCard = `<div class="card"><div class="row between"><b>📴 Copy on this device</b>
      <span class="badge ${!f ? "red" : age > 24 ? "amber" : "green"}">${!f ? "None" : age < 1 ? "Up to date" : age + " h old"}</span></div>
      <p class="muted small">For an inspector when there is no signal. It updates by itself twice a day.</p>
      <div class="grid2"><button data-act="offline-open" ${f ? "" : "disabled"}>Open copy</button><button data-act="offline-save">Update now</button></div></div>`;
  if (!online()) return render(`${head("Safety file", "The site's health and safety file.")}${offlineCard}
    <div class="note warn">No signal. Open the copy on this device. Uploads and exports need a signal.</div>`);
  const docs = await api("/api/docs?site_id=" + S.siteId);
  const secs = S.data.file_sections;
  const t = todayStr(), start = S.data.site.start_date || "";
  render(`${head("Safety file", "Everything the law wants in the file. Upload the documents; the app adds the signed records.")}
    ${offlineCard}
    <div class="card"><b>Export the whole file</b><p class="muted small">One PDF: index, documents and every signed record.</p>
      <div class="grid2"><div><label>From</label><input type="date" id="f-from" value="${esc(start)}"></div><div><label>To</label><input type="date" id="f-to" value="${t}"></div></div>
      <button class="dark" data-act="export-file">Download safety file PDF</button>
      <div class="grid2" style="margin-top:8px"><button data-act="nav" data-to="print">🖨️ Print centre</button><button data-act="verify">Check integrity</button></div>
      <div id="verify-out"></div></div>
    <h2>Sections</h2>
    ${secs.map((s, i) => {
      const mine = docs.filter((d) => d.section === s.key);
      const auto = s.type.includes("auto");
      const status = mine.length ? `<span class="badge ok">${mine.length} doc${mine.length > 1 ? "s" : ""}</span>` : auto ? '<span class="badge">From records</span>' : '<span class="badge bad">Missing</span>';
      return `<div class="card"><div class="row between"><div class="grow"><b>${i + 1}. ${esc(s.title)}</b></div>${status}</div>
        ${mine.map((d) => `<div class="row small" style="margin-top:6px"><a class="grow" href="${d.file_url}" target="_blank">📄 ${esc(d.title)}</a>
          ${d.expires ? `<span class="badge ${d.status === "expired" ? "bad" : d.status === "expiring" ? "warn" : "ok"}">exp ${esc(d.expires)}</span>` : ""}
          ${can.manage() ? `<button class="link" data-act="del-doc" data-id="${d.id}">Delete</button>` : ""}</div>`).join("")}
        ${s.type.includes("upload") && can.manage() ? `<button class="small" style="margin-top:8px" data-act="add-doc" data-section="${s.key}" data-title="${esc(s.title)}">+ Upload</button>` : ""}</div>`;
    }).join("")}`);
};
ACT["export-file"] = () => openPdf(`/api/sites/${S.siteId}/file.pdf?date_from=${$("#f-from").value}&date_to=${$("#f-to").value}`,
  `Safety-file-${S.data.site.name.replace(/\W+/g, "-")}.pdf`);
ACT.verify = async () => {
  const v = await api("/api/verify");
  $("#verify-out").innerHTML = v.ok ? `<div class="note ok">${v.records} records checked. The chain is intact.</div>`
    : `<div class="note bad">${v.broken.length} problem(s) found. Records were changed outside the app. Contact support.</div>`;
};
ACT["add-doc"] = async (el) => {
  const f = await pickFile();
  if (!f) return;
  const title = prompt("Document title", f.name.replace(/\.[^.]+$/, "")) || f.name;
  const expires = prompt("Expiry date (YYYY-MM-DD), or leave blank", "") || "";
  const siteOnly = confirm("Is this document only for this site?\nOK = this site only. Cancel = all sites (company document).");
  try {
    await api("/api/docs", { json: { section: el.dataset.section, title, expires, file: f.data, site_id: siteOnly ? S.siteId : "" }, timeout: 120000 });
    toast("Uploaded.", "ok"); route();
  } catch (e) { toast(friendly(e), "bad"); }
};
ACT["del-doc"] = async (el) => {
  if (!confirm("Delete this document from the safety file?")) return;
  try { await api("/api/docs/" + el.dataset.id, { method: "DELETE" }); route(); } catch (e) { toast(friendly(e), "bad"); }
};

// ---------------------------------------------------------------- more

VIEWS.more = () => {
  const u = S.me.user;
  const item = (to, ico, label, sub = "", show = true) => show ? `<div class="card tap" data-act="nav" data-to="${to}"><div class="ico">${ico}</div>
    <div class="grow"><b>${label}</b>${sub ? `<div class="muted small">${sub}</div>` : ""}</div><span>›</span></div>` : "";
  const dark = (ls.get("ss-theme") || "light") === "dark";
  render(`${head("More", `${esc(u.name)} · ${esc(u.role_label)} · ${esc(S.me.company.name)}`)}
    <h2>This site</h2>
    ${item("consultant", "📑", "Client documents", "Consultant's risk assessment and the client's specification")}
    ${item("setup", "⚙️", "Site setup", "What the site has: excavations, scaffolds, plant…", can.manage())}
    ${item("appointments", "📜", "Legal appointments", "Construction manager, supervisors, operators…")}
    ${item("aes", "✍️", "Documents for signing", "Advanced e-signature or wet ink")}
    ${item("audit", "📋", "Monthly audit")}
    ${item("incidents", "🚑", "Incidents and investigations")}
    ${item("print", "🖨️", "Print centre", "Registers and records on paper")}
    ${item("sites", "🏗️", "Switch site")}
    <h2>Company</h2>
    ${item("risks", "⚠️", "Risk assessment library")}
    ${item("plant", "🚜", "Plant and QR codes")}
    ${item("esign", "🖊️", "E-signature agreement")}
    ${item("users", "👥", "Logins and roles", "", can.owner())}
    ${item("company", "🏢", "Company details and site rules", "", can.manage())}
    ${item("profile", "👤", "My profile and password")}
    <div class="card"><label class="check"><input type="checkbox" data-act-change="theme" ${dark ? "checked" : ""}> Dark screen (for indoors)</label></div>
    <button data-act="logout">Log out</button>
    <p class="muted small center"><a href="/privacy.html" target="_blank">Privacy</a> · <a href="/terms.html" target="_blank">Terms</a> · ${esc(S.me.app_name)} pilot</p>`);
  $("#view").onchange = (e) => {
    if (e.target.dataset.actChange === "theme") { const t = e.target.checked ? "dark" : "light"; ls.set("ss-theme", t); document.documentElement.dataset.theme = t; }
  };
};

// ---------------------------------------------------------------- boot

async function boot() {
  if ("serviceWorker" in navigator) {
    // A new version of the app takes over: reload once so every screen uses it. Drafts are safe in IndexedDB.
    const hadController = !!navigator.serviceWorker.controller;
    let reloaded = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (hadController && !reloaded && !$(".modal")) { reloaded = true; location.reload(); }
    });
    navigator.serviceWorker.register("/sw.js").then((r) => r.update()).catch(() => {});
  }
  renderHeader();
  if (!S.token) return route();
  try {
    await loadMe();
    await loadSite();
    S.pending = (await IDB.outbox.all()).length;
    renderHeader();
    route();
    flush();
    if (S.siteId) autoOfflineFile();
  } catch (e) {
    if (e.status === 401) return logout(true);
    render(`<div class="note bad">${esc(friendly(e))}</div>`);
  }
}
window.addEventListener("DOMContentLoaded", boot);
