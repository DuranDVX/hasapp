// Site Board (home), the "+ Record" menu, site setup, e-signature agreement, print centre.

const TILE_ICON = {
  task_sheet: "📋", toolbox_talk: "🗣️", visitors: "🪪", inductions: "👷", medicals: "🩺", certificates: "🎓",
  plant_checks: "🚜", operators: "🪪", esign: "🖊️", appointments: "📜", aes: "✍️", risk: "⚠️", hs_plan: "📘",
  client_spec: "📗", notification: "📨", coid: "🛡️", fall_plan: "🪢", emergency: "🚨", contractors: "🤝",
  audit: "🔍", incidents: "🚑", device_copy: "📴",
};
const STATUS_WORD = { red: "ACTION", amber: "SOON", green: "OK", na: "N/A" };

async function boardData() {
  const key = "board:" + S.siteId;
  if (online()) {
    try { const b = await api("/api/board?site_id=" + S.siteId); await IDB.set(key, b); return { b, live: true }; } catch {}
  }
  const b = await IDB.get(key);
  return { b, live: false };
}

VIEWS.board = async () => {
  const { b, live } = await boardData();
  if (!b) return render(`${head("Site Board")}<div class="note warn">Open the board once with a signal. It then works offline.</div>`);
  const tiles = [...b.tiles];
  // The device copy of the safety file is a tile too: an inspector can arrive with no signal.
  const f = await offlineFile();
  const age = f ? (Date.now() - f.at) / 3600000 : null;
  tiles.push({ group: "Appointments and documents", key: "device_copy", title: "File copy on this device", reg: "7(1)(b)",
    status: !f ? "red" : age > 24 ? "amber" : "green",
    detail: !f ? "No copy yet. Open the File tab with a signal." : `Saved ${age < 1 ? "less than an hour" : Math.round(age) + " h"} ago.`, action: "file" });
  const pend = await pendingItems();
  const counts = { red: 0, amber: 0, green: 0 };
  tiles.forEach((t) => { if (counts[t.status] !== undefined) counts[t.status]++; });
  const overall = counts.red ? "red" : counts.amber ? "amber" : "green";
  const headline = counts.red ? `${counts.red} thing${counts.red > 1 ? "s" : ""} need action now`
    : counts.amber ? "All met · some need attention soon" : "Everything is in order";
  const reds = tiles.filter((t) => t.status === "red");
  const groups = [...new Set(tiles.map((t) => t.group))];
  render(`<div class="summary ${overall}"><h1>${headline}</h1>
      <p>${esc(S.data.site.name)} · ${new Date().toLocaleDateString("en-ZA", { weekday: "long", day: "numeric", month: "long" })}${live ? "" : " · offline, last known status"}</p>
      <div class="counts"><span>🟥 ${counts.red} action</span><span>🟧 ${counts.amber} soon</span><span>🟩 ${counts.green} OK</span></div></div>
    ${!online() ? `<div class="note warn">No signal. You can still fill in and sign everything. It sends when the signal comes back.</div>` : ""}
    ${pend.length ? `<div class="note info">${pend.length} record(s) wait on this device to send. <a href="#records">See them</a></div>` : ""}
    ${reds.length ? `<h2>Fix first</h2>${reds.slice(0, 5).map((t) => `<div class="card tap fix" data-act="nav" data-to="${esc(t.action)}">
      <div class="ico">${TILE_ICON[t.key] || (t.key.startsWith("insp_") ? "🔎" : "•")}</div>
      <div class="grow"><b>${esc(t.title)}</b><div class="small muted">${esc(t.detail)}</div></div><span>›</span></div>`).join("")}` : ""}
    ${groups.map((g) => `<h2>${esc(g)}</h2><div class="tiles">${tiles.filter((t) => t.group === g).map((t) => `
      <button class="tile ${t.status}" data-act="nav" data-to="${esc(t.action)}">
        <div class="t-top"><span>${TILE_ICON[t.key] || (t.key.startsWith("insp_") ? "🔎" : "•")}</span><span>${STATUS_WORD[t.status] || ""}</span></div>
        <div class="t-title">${esc(t.title)}</div><div class="t-detail">${esc(t.detail)}</div>
        <div class="t-reg">Reg ${esc(t.reg)}</div></button>`).join("")}</div>`).join("")}
    ${can.manage() ? `<p class="center"><button class="link" data-act="nav" data-to="setup">⚙️ Not right for this site? Change the site setup</button></p>` : ""}`);
};

// ---------------------------------------------------------------- "+ Record" menu

const RECORD_ACTIONS = [
  ["task", "📋", "Daily task sheet"], ["talk", "🗣️", "Toolbox talk"], ["check", "🚜", "Plant check"],
  ["inspections", "🔎", "Site inspection"], ["visitor", "🪪", "Visitor"], ["incident", "🚨", "Incident"],
  ["appoint", "📜", "Appointment"], ["audit", "🔍", "Audit"],
];
ACT.record = () => {
  const m = document.createElement("div");
  m.className = "modal";
  m.innerHTML = `<div class="sheet"><div class="row between"><h2 style="margin:0">Record something</h2><button class="link" data-x="close">Close</button></div>
    <div class="actions-grid" style="margin-top:12px">${RECORD_ACTIONS.map(([to, ico, label]) =>
      `<button data-x="${to}"><span>${ico}</span>${label}</button>`).join("")}</div></div>`;
  document.body.appendChild(m);
  m.onclick = (e) => {
    const x = e.target.closest("[data-x]")?.dataset.x;
    if (!x && e.target !== m) return;
    m.remove();
    if (x && x !== "close") go(x);
  };
};

VIEWS.inspections = async () => {
  const { b } = await boardData();
  const st = Object.fromEntries((b?.tiles || []).map((t) => [t.key, t]));
  const list = Object.entries(S.data.checklists).filter(([, c]) => c.kind === "inspection");
  render(`${head("Site inspections", "Choose the inspection. The colour shows when it is due.", "board")}
    <div class="card"><ul class="plain">${list.map(([k, c]) => { const t = st["insp_" + k];
      return `<li class="list-item" data-act="nav" data-to="checklist/${k}"><span class="dot ${t ? t.status : "na"}"></span>
        <div class="grow"><b>${esc(c.title)}</b><div class="muted small">${esc(t ? t.detail : c.note || "Not switched on for this site.")}</div></div><span>›</span></li>`; }).join("")}</ul></div>`);
};

// ---------------------------------------------------------------- site setup

VIEWS.setup = () => {
  const site = S.data.site, f = site.features || {};
  render(`${head("Site setup", "Tick what this site has. The board then shows only the duties that apply.", "board")}
    <div class="card">${Object.entries(S.data.site_features).map(([k, v]) =>
      `<label class="check"><input type="checkbox" data-f="${k}" ${f[k] ? "checked" : ""}> ${esc(v)}</label>`).join("")}</div>
    <div class="card"><label class="check"><input type="checkbox" id="su-print" ${site.print_required ? "checked" : ""}> The client wants paper copies</label>
      <p class="muted small">The app still keeps the electronic original. Use the Print centre for the paper copies.</p></div>
    <div class="card"><button class="link" data-act="nav" data-to="site/${site.id}">Edit site name, client and emergency details ›</button></div>
    ${actionBar(`<button class="primary" data-act="setup-save">Save setup</button>`)}`);
};
ACT["setup-save"] = (btn) => busy(btn, "Saving…", async () => {
  if (needOnline()) return;
  const features = {};
  document.querySelectorAll("[data-f]").forEach((x) => { features[x.dataset.f] = x.checked; });
  await api("/api/sites/" + S.siteId, { method: "PUT", json: { features, print_required: $("#su-print").checked } });
  await loadMe(); await loadSite(true); toast("Saved.", "ok"); go("board");
});

// ---------------------------------------------------------------- e-signature agreement

VIEWS.esign = async () => {
  if (needOnline()) return;
  const e = await api("/api/esign");
  render(`${head("E-signature agreement", "Once for the company. It makes the signatures in the app valid by agreement (ECT Act s13).", "more")}
    ${e.accepted ? `<div class="note ok">Accepted by ${esc(e.accepted_by)} on ${esc(e.accepted_at.slice(0, 10))}.</div>` : ""}
    <div class="card" style="white-space:pre-wrap">${esc(e.text)}</div>
    ${!e.accepted && can.owner() ? actionBar(`<button class="primary" data-act="esign-accept">I accept for the company</button>`) :
      !e.accepted ? `<div class="note warn">The owner of the company must accept this.</div>` : ""}`);
};
ACT["esign-accept"] = (btn) => busy(btn, "Saving…", async () => {
  await api("/api/esign/accept", { method: "POST" });
  await loadSite(true); toast("Accepted.", "ok"); go("board");
});

// ---------------------------------------------------------------- print centre

VIEWS.print = async () => {
  if (needOnline()) return;
  const packs = await api("/api/print/packs");
  const insp = Object.entries(S.data.checklists);
  render(`${head("Print centre", "For a client or inspector who wants paper. Each page has a code that proves it matches the electronic original.", "file")}
    ${S.data.site.print_required ? `<div class="note warn">This client wants paper copies. Print the registers each week.</div>` : ""}
    <div class="card"><label>What to print</label><select id="pr-what">${Object.entries(packs).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
      <div id="pr-tpl-wrap" class="hidden"><label>Only this checklist (optional)</label><select id="pr-tpl"><option value="">All checklists</option>
        ${insp.map(([k, c]) => `<option value="${k}">${esc(c.title)}</option>`).join("")}</select></div>
      <div class="grid2"><div><label>From</label><input type="date" id="pr-from" value="${new Date(Date.now() - 6 * 86400000).toISOString().slice(0, 10)}"></div>
        <div><label>To</label><input type="date" id="pr-to" value="${todayStr()}"></div></div></div>
    <div class="note info small">To print one record, open it under Records and tap "Print copy". The whole file is under File.</div>
    ${actionBar(`<button class="primary" data-act="print-go">🖨️ Make the PDF to print</button>`)}`);
  $("#pr-what").onchange = (e) => $("#pr-tpl-wrap").classList.toggle("hidden", e.target.value !== "check_register");
};
ACT["print-go"] = () => {
  const what = $("#pr-what").value, tpl = what === "check_register" ? $("#pr-tpl").value : "";
  openPdf(`/api/sites/${S.siteId}/print.pdf?what=${what}&date_from=${$("#pr-from").value}&date_to=${$("#pr-to").value}${tpl ? "&template=" + tpl : ""}`);
};
