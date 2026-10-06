// Set-up screens: workers, certificates, risk library, plant + QR codes, logins, company, profile.
// These need a signal; site records do not.

function needOnline() {
  if (online()) return false;
  render(`<div class="note warn">This screen needs a signal. Site records (task sheets, talks, checks) work offline.</div>`);
  return true;
}
const STATUS_BADGE = { valid: "ok", expiring: "warn", expired: "bad", missing: "bad", none: "" };
const STATUS_TEXT = { valid: "Valid", expiring: "Expires soon", expired: "Expired", missing: "None on file", none: "No expiry" };

// ---------------------------------------------------------------- workers

VIEWS.workers = async () => {
  const ws = S.data.workers;
  render(`${head("People on site", "Workers, contractors and visitors.")}${peopleTabs("workers")}
    ${ws.length ? `<div class="card"><ul class="plain">${ws.map((w) => `<li class="list-item" data-act="nav" data-to="worker/${w.id}">
      ${w.photo_url && online() ? `<img class="avatar" src="${w.photo_url}" alt="">` : `<div class="avatar">${esc(w.name[0])}</div>`}
      <div class="grow"><b>${esc(w.name)}</b><div class="muted small">${esc(w.trade || "")}${w.employer ? " · " + esc(w.employer) : ""}</div>
        <div class="row small" style="gap:10px;margin-top:3px"><span class="row" style="gap:4px"><span class="dot ${w.inducted ? "green" : "red"}"></span>Inducted</span>
        <span class="row" style="gap:4px"><span class="dot ${w.medical === "valid" ? "green" : w.medical === "expiring" ? "amber" : "red"}"></span>Medical</span></div></div>
      <span>›</span></li>`).join("")}</ul></div>`
      : `<div class="note warn">No workers on this site yet.</div>`}
    ${can.write() && online() ? `<button data-act="nav" data-to="worker-pick">Add workers from other sites</button>` : ""}
    ${can.write() ? actionBar(`<button class="primary" data-act="nav" data-to="worker/new">+ Add a worker</button>`) : ""}`);
};

VIEWS["worker-pick"] = async () => {
  if (needOnline()) return;
  const all = await api("/api/workers");
  const here = new Set(S.data.workers.map((w) => w.id));
  const others = all.filter((w) => !here.has(w.id) && w.active);
  render(`<button class="link" data-act="back">‹ Back</button><h1>Add to this site</h1>
    ${others.length ? `<div class="card"><ul class="plain">${others.map((w) => `<li class="row"><label class="row grow" style="color:var(--ink);font-size:16px">
      <input type="checkbox" value="${w.id}" style="width:auto;margin:0"> ${esc(w.name)} <span class="muted small">${esc(w.trade)}</span></label></li>`).join("")}</ul></div>
      <button class="primary" data-act="worker-pick-save">Add to site</button>` : `<p class="muted">All your workers are already on this site.</p>`}`);
};
ACT["worker-pick-save"] = (btn) => busy(btn, "Adding…", async () => {
  const ids = [...document.querySelectorAll("#view input[type=checkbox]:checked")].map((x) => x.value);
  if (!ids.length) return toast("Tick the workers first.", "bad");
  await api(`/api/sites/${S.siteId}/workers`, { json: { worker_ids: ids } });
  await loadSite(true); go("workers");
});

VIEWS.worker = async (id) => {
  if (id === "new") return workerForm({});
  const w = worker(id);
  if (!w) return render(`<div class="note bad">Worker not found on this site.</div>`);
  render(`<button class="link back" data-act="nav" data-to="workers">‹ Back</button>
    <div class="row" style="margin:8px 0">${w.photo_url && online() ? `<img class="avatar" style="width:72px;height:72px" src="${w.photo_url}">` : `<div class="avatar" style="width:72px;height:72px;font-size:28px">${esc(w.name[0])}</div>`}
      <div><h1 style="margin:0">${esc(w.name)}</h1><div class="muted">${esc(w.trade)}${w.employer ? " · " + esc(w.employer) : " · Own staff"}</div></div></div>
    ${w.inducted ? `<div class="note ok">Inducted on this site.</div>` : `<div class="note warn">Not inducted on this site. ${can.write() ? `<button class="small primary" data-act="nav" data-to="induct/${w.id}">Induct now</button>` : ""}</div>`}
    <div class="card"><table class="simple">
      <tr><td class="muted">ID number</td><td>${esc(w.id_number || "-")}</td></tr>
      <tr><td class="muted">Phone</td><td>${esc(w.phone || "-")}</td></tr>
      <tr><td class="muted">Emergency contact</td><td>${esc(w.emergency_contact || "-")}</td></tr>
      <tr><td class="muted">Language</td><td>${esc(S.data.languages[w.language] || "")}</td></tr></table>
      ${can.write() ? `<button class="small" data-act="worker-edit" data-id="${w.id}" style="margin-top:8px">Edit</button>` : ""}</div>
    <h2>Certificates</h2>
    <div class="card">${w.credentials.length ? `<ul class="plain">${w.credentials.map((c) => `<li class="row"><div class="grow"><b>${esc(c.kind_label)}</b>
      <div class="muted small">${esc(c.title)}${c.expires ? " · expires " + esc(c.expires) : ""}</div>
      ${c.file_url && online() ? `<a class="small" href="${c.file_url}" target="_blank">View</a>` : ""}</div>
      <span class="badge ${STATUS_BADGE[c.status]}">${STATUS_TEXT[c.status]}</span></li>`).join("")}</ul>` : `<p class="muted small">No certificates on file.</p>`}
      ${can.write() ? `<button class="small primary" data-act="nav" data-to="cred/${w.id}">+ Add certificate</button>` : ""}</div>
    ${can.write() ? `<button data-act="worker-off-site" data-id="${w.id}">Remove from this site</button>` : ""}`);
};
ACT["worker-edit"] = (el) => workerForm(worker(el.dataset.id));
ACT["worker-off-site"] = (el) => busy(el, "Removing…", async () => {
  if (!confirm("Remove this worker from this site? Their records stay.")) return;
  await api(`/api/sites/${S.siteId}/workers/${el.dataset.id}`, { method: "DELETE" });
  await loadSite(true); go("workers");
});
function workerForm(w) {
  if (needOnline()) return;
  let photo = "";
  render(`<button class="link" data-act="back">‹ Back</button><h1>${w.id ? "Edit worker" : "Add a worker"}</h1>
    <div class="card"><div class="row"><img id="wf-img" class="avatar ${w.photo_url ? "" : "hidden"}" style="width:64px;height:64px" src="${w.photo_url || ""}">
      <button class="small" data-act="wf-photo">📷 ${w.photo_url ? "New photo" : "Take photo"}</button></div>
    <label>Full name</label><input id="wf-name" value="${esc(w.name || "")}">
    <label>ID or passport number</label><input id="wf-id" value="${esc(w.id_number || "")}">
    <label>Trade</label><input id="wf-trade" value="${esc(w.trade || "")}" placeholder="Bricklayer, general worker, TLB operator">
    <label>Employer (blank = own staff)</label><input id="wf-emp" value="${esc(w.employer || "")}" placeholder="Subcontractor name">
    <label>Phone</label><input id="wf-phone" type="tel" value="${esc(w.phone || "")}">
    <label>Emergency contact</label><input id="wf-em" value="${esc(w.emergency_contact || "")}">
    <label>Language</label><select id="wf-lang">${Object.entries(S.data.languages).map(([k, v]) => `<option value="${k}" ${k === (w.language || "en") ? "selected" : ""}>${v}</option>`).join("")}</select>
    <p class="muted small">The ID number and photo are personal information (POPIA). Only your company's logins can see them.</p>
    <button class="primary" data-act="wf-save" data-id="${w.id || ""}">Save</button></div>`);
  ACT["wf-photo"] = async () => { const p = await pickPhoto({ front: false }); if (p) { photo = p; const i = $("#wf-img"); i.src = p; i.classList.remove("hidden"); } };
  ACT["wf-save"] = (btn) => busy(btn, "Saving…", async () => {
    const body = { name: $("#wf-name").value, id_number: $("#wf-id").value, trade: $("#wf-trade").value, employer: $("#wf-emp").value,
      phone: $("#wf-phone").value, emergency_contact: $("#wf-em").value, language: $("#wf-lang").value };
    if (photo) body.photo = photo;
    let r;
    if (btn.dataset.id) r = await api("/api/workers/" + btn.dataset.id, { method: "PUT", json: body });
    else r = await api("/api/workers", { json: { ...body, site_id: S.siteId } });
    await loadSite(true); toast("Saved.", "ok");
    go(btn.dataset.id ? "worker/" + r.id : "induct/" + r.id);
  });
}
VIEWS.cred = (wid) => {
  if (needOnline()) return;
  const w = worker(wid); let file = null;
  render(`<button class="link" data-act="back">‹ Back</button><h1>Add a certificate</h1><p>${esc(w.name)}</p><div class="card">
    <label>Type</label><select id="cr-kind">${Object.entries(S.data.credential_kinds).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
    <label>Title</label><input id="cr-title" placeholder="Working at heights, first aid level 1…">
    <div class="grid2"><div><label>Issued</label><input id="cr-issued" type="date"></div><div><label>Expires</label><input id="cr-exp" type="date"></div></div>
    <button class="small" data-act="cr-file">📷 Photo or PDF of the certificate</button> <span id="cr-fname" class="muted small"></span>
    <button class="primary" data-act="cr-save" style="margin-top:10px">Save</button></div>`);
  ACT["cr-file"] = async () => { file = await pickFile(); if (file) $("#cr-fname").textContent = file.name; };
  ACT["cr-save"] = (btn) => busy(btn, "Saving…", async () => {
    await api(`/api/workers/${wid}/credentials`, { json: { kind: $("#cr-kind").value, title: $("#cr-title").value,
      issued: $("#cr-issued").value, expires: $("#cr-exp").value, file: file ? file.data : "" }, timeout: 120000 });
    await loadSite(true); go("worker/" + wid);
  });
};

// ---------------------------------------------------------------- risk library

VIEWS.risks = () => {
  const rs = S.data.risks, todo = rs.filter((r) => !r.approved).length;
  render(`<h1>Risk assessment library</h1>
    <p class="muted small">The AI only picks activities from this list. A task sheet shows an activity as assessed only after a competent person (SACPCMP-registered) approves it.</p>
    ${todo ? `<div class="note warn">${todo} of ${rs.length} activities are not approved yet. The starter items are drafts.</div>` : `<div class="note ok">All activities approved.</div>`}
    ${can.manage() ? `<button class="primary" data-act="nav" data-to="risk/new">+ New activity</button>` : ""}
    <div class="card" style="margin-top:10px"><ul class="plain">${rs.map((r) => `<li class="list-item" data-act="nav" data-to="risk/${r.id}">
      <div class="grow"><b>${esc(r.activity)}</b><div class="muted small">${r.hazards.length} hazards${r.site_id ? " · this site only" : ""}</div></div>
      <span class="badge ${r.approved ? "ok" : "warn"}">${r.approved ? "Approved" : "Not approved"}</span></li>`).join("")}</ul></div>`);
};
VIEWS.risk = (id) => {
  const r = id === "new" ? { activity: "", hazards: [], ppe: [] } : risk(id);
  if (!r) return render(`<div class="note bad">Not found.</div>`);
  const asText = (hz) => hz.map((h) => `${h.hazard} [${h.risk}]\n${h.controls.map((c) => "- " + c).join("\n")}`).join("\n\n");
  render(`<button class="link" data-act="nav" data-to="risks">‹ Library</button>
    <h1>${id === "new" ? "New activity" : esc(r.activity)}</h1>
    ${r.approved ? `<div class="note ok">Approved by ${esc(r.approved_by)} on ${esc(r.approved_at)}</div>` : id !== "new" ? `<div class="note warn">Not approved.</div>` : ""}
    ${can.manage() ? `<div class="card">
      ${id === "new" ? `<label>Describe the activity, then let the AI draft it (you check and approve)</label>
        <input id="rk-desc" placeholder="Installing a steel staircase with a mobile crane"><button class="dark" data-act="rk-ai">✨ Draft with AI</button><hr style="border:0;border-top:1px solid var(--line);margin:14px 0">` : ""}
      <label>Activity</label><input id="rk-act" value="${esc(r.activity)}">
      <label>Hazards and controls: one hazard per block, risk in [L], [M] or [H], controls start with "-"</label>
      <textarea id="rk-hz" style="min-height:260px;font-family:ui-monospace,monospace;font-size:14px">${esc(asText(r.hazards))}</textarea>
      <label>PPE (comma separated)</label><input id="rk-ppe" value="${esc(r.ppe.join(", "))}">
      ${id === "new" ? `<label class="row" style="color:var(--ink)"><input type="checkbox" id="rk-site" style="width:auto;margin:0"> Only for this site</label>` : ""}
      <button class="primary" data-act="rk-save" data-id="${esc(id)}">Save${id !== "new" ? " (clears the approval)" : ""}</button>
      ${id !== "new" && !r.approved ? `<button class="dark" data-act="rk-approve" data-id="${r.id}" style="margin-top:8px">Approve as competent person</button>` : ""}
      ${id !== "new" ? `<button class="link" data-act="rk-off" data-id="${r.id}">Remove from library</button>` : ""}
    </div>` : `${hazardHtml([r.id])}`}`);
};
function parseHazards(text) {
  return text.split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean).map((b) => {
    const lines = b.split("\n").map((l) => l.trim()).filter(Boolean);
    const m = lines[0].match(/^(.*?)\s*\[([LMH])\]\s*$/i);
    return { hazard: m ? m[1] : lines[0], risk: m ? m[2].toUpperCase() : "M",
      controls: lines.slice(1).map((l) => l.replace(/^[-•*]\s*/, "")).filter(Boolean) };
  });
}
ACT["rk-ai"] = (btn) => busy(btn, "Drafting…", async () => {
  const r = await api("/api/ai/risk-draft", { json: { description: $("#rk-desc").value }, timeout: 90000 });
  $("#rk-act").value = r.activity;
  $("#rk-hz").value = r.hazards.map((h) => `${h.hazard} [${h.risk}]\n${h.controls.map((c) => "- " + c).join("\n")}`).join("\n\n");
  $("#rk-ppe").value = r.ppe.join(", ");
  btn.dataset.ai = "1";
  toast("Draft ready. Check every line before you save.", "ok");
});
ACT["rk-save"] = (btn) => busy(btn, "Saving…", async () => {
  const id = btn.dataset.id;
  const body = { activity: $("#rk-act").value, hazards: parseHazards($("#rk-hz").value), ppe: $("#rk-ppe").value.split(",").map((x) => x.trim()).filter(Boolean) };
  if (id === "new") {
    if ($("#rk-site")?.checked) body.site_id = S.siteId;
    if ($("[data-act=rk-ai]")?.dataset.ai) body.source = "ai_draft";
    await api("/api/risks", { json: body });
  } else await api("/api/risks/" + id, { method: "PUT", json: body });
  await loadSite(true); toast("Saved. It needs approval before it counts as assessed.", "ok"); go("risks");
});
ACT["rk-approve"] = (btn) => busy(btn, "Approving…", async () => {
  if (!confirm("You confirm, as a competent person, that this risk assessment is correct for the work. Your name and SACPCMP number go on every record that uses it.")) return;
  await api(`/api/risks/${btn.dataset.id}/approve`, { method: "POST" });
  await loadSite(true); route();
});
ACT["rk-off"] = (btn) => busy(btn, "Removing…", async () => {
  if (!confirm("Remove this activity from the library? Old records keep their copy.")) return;
  const r = risk(btn.dataset.id);
  await api("/api/risks/" + r.id, { method: "PUT", json: { activity: r.activity, hazards: r.hazards, ppe: r.ppe, active: false } });
  await loadSite(true); go("risks");
});

// ---------------------------------------------------------------- plant + QR

VIEWS.plant = () => {
  const ps = S.data.plant;
  render(`<div class="row between"><h1>Plant and QR codes</h1></div>
    ${ps.length ? `<div class="card"><ul class="plain">${ps.map((p) => `<li class="row"><div class="grow"><b>${esc(p.name)}</b> <span class="muted small">${esc(p.ident)}</span>
      <div class="muted small">${esc(p.template_title)}${p.site_id ? "" : " · not on a site"}</div></div>
      ${can.write() ? `<button class="small" data-act="plant-off" data-id="${p.id}">Remove</button>` : ""}</li>`).join("")}</ul></div>
      <button class="dark noprint" data-act="nav" data-to="qr">Print QR stickers</button>` : `<p class="muted">No plant yet.</p>`}
    ${can.write() ? `<h2>Add plant or equipment</h2><div class="card">
      <label>Name</label><input id="pl-name" placeholder="TLB 1, Mixer 2, Bakkie">
      <label>Registration or serial number</label><input id="pl-ident">
      <label>Checklist</label><select id="pl-tpl">${Object.entries(S.data.checklists).filter(([, c]) => c.kind === "plant").map(([k, c]) => `<option value="${k}">${esc(c.title)}</option>`).join("")}</select>
      <button class="primary" data-act="plant-add">Add to this site</button></div>` : ""}`);
};
ACT["plant-add"] = (btn) => busy(btn, "Adding…", async () => {
  if (needOnline()) return;
  await api("/api/plant", { json: { name: $("#pl-name").value, ident: $("#pl-ident").value, template: $("#pl-tpl").value, site_id: S.siteId } });
  await loadSite(true); route();
});
ACT["plant-off"] = (btn) => busy(btn, "Removing…", async () => {
  if (!confirm("Remove this item from the list?")) return;
  await api("/api/plant/" + btn.dataset.id, { method: "PUT", json: { active: false } });
  await loadSite(true); route();
});
VIEWS.qr = async () => {
  if (needOnline()) return;
  const ps = S.data.plant;
  const imgs = await Promise.all(ps.map(async (p) => {
    const res = await api(`/api/plant/${p.id}/qr.svg`, { raw: true });
    return URL.createObjectURL(await res.blob());
  }));
  render(`<div class="noprint"><button class="link" data-act="back">‹ Back</button><p class="muted small">Print this page. Stick each code on its machine where the operator sees it. Scanning it opens the right checklist.</p>
    <button class="dark" onclick="window.print()">Print</button></div>
    <div class="qrgrid" style="margin-top:12px">${ps.map((p, i) => `<div class="card"><img src="${imgs[i]}" alt="QR"><div><b>${esc(p.name)}</b></div>
      <div class="small">${esc(p.ident)}</div><div class="small muted">Scan for the pre-use check</div></div>`).join("")}</div>`);
};

// ---------------------------------------------------------------- logins

VIEWS.users = async () => {
  if (needOnline()) return;
  const us = await api("/api/users");
  render(`<h1>Logins and roles</h1>
    <div class="card"><ul class="plain">${us.map((u) => `<li class="row"><div class="grow"><b>${esc(u.name)}</b> ${u.active ? "" : '<span class="badge">Off</span>'}
      <div class="muted small">${esc(u.email)} · ${esc(u.role_label)}${u.sacpcmp_no ? " · SACPCMP " + esc(u.sacpcmp_no) : ""}</div></div>
      ${u.id !== S.me.user.id ? `<button class="small" data-act="user-reset" data-id="${u.id}">Reset</button>
        <button class="small" data-act="user-toggle" data-id="${u.id}" data-on="${u.active ? 1 : 0}">${u.active ? "Switch off" : "Switch on"}</button>` : ""}</li>`).join("")}</ul></div>
    <h2>Add a login</h2><div class="card">
      <label>Name</label><input id="u-name"><label>Email</label><input id="u-email" type="email">
      <label>Role</label><select id="u-role">${Object.entries(S.me.roles).filter(([k]) => k !== "owner").map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}<option value="owner">Owner</option></select>
      <label>SACPCMP number (safety officers)</label><input id="u-sac">
      <button class="primary" data-act="user-add">Add login</button><div id="u-out"></div></div>
    <p class="muted small">Foreman: fills in site records. Safety officer: also approves risk assessments and manages the file. Auditor: reads and exports only (for the client's H&S agent).</p>`);
};
ACT["user-add"] = (btn) => busy(btn, "Adding…", async () => {
  const r = await api("/api/users", { json: { name: $("#u-name").value, email: $("#u-email").value, role: $("#u-role").value, sacpcmp_no: $("#u-sac").value } });
  await VIEWS.users();
  $("#u-out").innerHTML = `<div class="note ok">Login made for ${esc(r.email)}. Temporary password: <b>${esc(r.temp_password)}</b><br>Email: ${esc(r.email_status)}. Give the password to the person if the email did not send.</div>`;
});
ACT["user-reset"] = (btn) => busy(btn, "…", async () => {
  if (!confirm("Make a new temporary password for this login?")) return;
  const r = await api("/api/users/" + btn.dataset.id, { method: "PUT", json: { reset_password: true } });
  alert("New temporary password: " + r.temp_password);
});
ACT["user-toggle"] = (btn) => busy(btn, "…", async () => {
  await api("/api/users/" + btn.dataset.id, { method: "PUT", json: { active: btn.dataset.on !== "1" } }); route();
});

// ---------------------------------------------------------------- company, profile

VIEWS.company = () => {
  if (needOnline()) return;
  const c = S.me.company; let logo = "";
  render(`<h1>Company</h1><div class="card">
    <label>Company name</label><input id="c-name" value="${esc(c.name)}">
    <label>Registration number</label><input id="c-reg" value="${esc(c.reg_no)}">
    <label>COID / Compensation Fund number</label><input id="c-coid" value="${esc(c.coid_no)}">
    <label>Phone</label><input id="c-phone" value="${esc(c.phone)}"><label>Email</label><input id="c-email" value="${esc(c.email)}">
    <label>Address</label><textarea id="c-addr">${esc(c.address)}</textarea>
    <div class="row"><img id="c-logo" class="${c.logo_url ? "" : "hidden"}" src="${c.logo_url}" style="max-height:48px"><button class="small" data-act="c-logo">Logo for PDFs</button></div>
    <label>Site rules for inductions</label><textarea id="c-ind" style="min-height:240px">${esc(c.induction_text)}</textarea>
    <button class="primary" data-act="c-save">Save</button></div>`);
  ACT["c-logo"] = async () => { const p = await pickPhoto(); if (p) { logo = p; $("#c-logo").src = p; $("#c-logo").classList.remove("hidden"); } };
  ACT["c-save"] = (btn) => busy(btn, "Saving…", async () => {
    const body = { name: $("#c-name").value, reg_no: $("#c-reg").value, coid_no: $("#c-coid").value, phone: $("#c-phone").value,
      email: $("#c-email").value, address: $("#c-addr").value, induction_text: $("#c-ind").value };
    if (logo) body.logo = logo;
    await api("/api/company", { method: "PUT", json: body });
    await loadMe(); await loadSite(true); toast("Saved.", "ok");
  });
};
VIEWS.profile = () => {
  const u = S.me.user;
  render(`<h1>My profile</h1><div class="card">
    <label>Name</label><input id="p-name" value="${esc(u.name)}"><label>Phone</label><input id="p-phone" value="${esc(u.phone)}">
    <label>SACPCMP registration number (needed to approve risk assessments)</label><input id="p-sac" value="${esc(u.sacpcmp_no)}">
    <button class="primary" data-act="p-save">Save</button></div>
    <h2>Change password</h2><div class="card"><label>Old password</label><input id="p-old" type="password" autocomplete="current-password">
    <label>New password</label><input id="p-new" type="password" autocomplete="new-password"><button data-act="p-pw">Change password</button></div>`);
};
ACT["p-save"] = (btn) => busy(btn, "Saving…", async () => {
  await api("/api/profile", { method: "PUT", json: { name: $("#p-name").value, phone: $("#p-phone").value, sacpcmp_no: $("#p-sac").value } });
  await loadMe(); toast("Saved.", "ok");
});
ACT["p-pw"] = (btn) => busy(btn, "Changing…", async () => {
  const r = await api("/api/account/password", { method: "PUT", json: { old_password: $("#p-old").value, password: $("#p-new").value } });
  S.token = r.token; ls.set("ss-token", r.token); toast("Password changed. Other devices must log in again.", "ok");
});
