// Generic register forms (drill, meeting, observation, PPE issue, permit, RA acceptance)
// and the consultant's documents: import the baseline risk assessment and the client's spec.

// ---------------------------------------------------------------- generic form

const FORM_STATE = {};
VIEWS.form = async (kind, pre) => {
  const F = S.data.forms[kind];
  if (!F) return render(`<div class="note bad">Unknown form.</div>`);
  if (!can.write()) return render(`<div class="note warn">Your role cannot fill in this form.</div>`);
  const v = (FORM_STATE[kind] = FORM_STATE[kind] || {});
  let permits = [];
  if (F.fields.some((f) => f.type === "open_permit") && online()) {
    try {
      const [p, c] = await Promise.all([api(`/api/records?site_id=${S.siteId}&kind=permit&limit=100`), api(`/api/records?site_id=${S.siteId}&kind=permit_close&limit=200`)]);
      const closed = new Set();
      for (const r of c) { try { const full = await api("/api/records/" + r.id); const f = full.payload.fields.find((x) => x.k === "permit"); if (f?.value?.id) closed.add(f.value.id); } catch {} }
      permits = p.filter((r) => !closed.has(r.id));
    } catch {}
  }
  let incidents = [];
  const incField = F.fields.find((f) => f.type === "open_incident");
  if (incField && online()) {
    try { incidents = (await api("/api/incidents?site_id=" + S.siteId)).filter((r) => !r.closed_id); } catch {}
    if (pre && incidents.some((r) => r.id === pre)) v[incField.k] = pre;
  }
  const needsPick = F.signers.some((g) => g.who === "pick");
  const field = (f) => {
    const val = v[f.k];
    const L = `<label>${esc(f.label)}${f.req ? "" : ' <span class="muted">(optional)</span>'}</label>`;
    switch (f.type) {
      case "textarea": return L + `<textarea data-fk="${f.k}" placeholder="${esc(f.ph || "")}">${esc(val || "")}</textarea>`;
      case "number": return L + `<input data-fk="${f.k}" inputmode="decimal" value="${esc(val ?? "")}">`;
      case "time": return L + `<input data-fk="${f.k}" type="time" value="${esc(val || "")}">`;
      case "yesno": return L + `<div class="answer" style="grid-template-columns:1fr 1fr">${[["yes", true], ["no", false]].map(([l, b]) =>
        `<button class="${b ? "ok" : "defect"} ${val === b ? "on" : ""}" data-act="fm-yn" data-k="${f.k}" data-v="${b}">${l === "yes" ? "Yes" : "No"}</button>`).join("")}</div>`;
      case "select": return L + `<div class="chips">${f.options.map((o) => `<button class="chip ${val === o ? "on" : ""}" data-act="fm-sel" data-k="${f.k}" data-v="${esc(o)}">${esc(o)}</button>`).join("")}</div>`;
      case "multi": return L + `<div class="card" style="padding:4px 12px">${f.options.map((o) => `<label class="check"><input type="checkbox" data-fm-multi="${f.k}" value="${esc(o)}" ${(val || []).includes(o) ? "checked" : ""}> ${esc(o)}</label>`).join("")}</div>`;
      case "worker": return L + `<select data-fk="${f.k}"><option value="">Choose…</option>${S.data.workers.map((w) => `<option value="${w.id}" ${val === w.id ? "selected" : ""}>${esc(w.name)} · ${esc(w.trade || "")}</option>`).join("")}</select>`;
      case "open_permit": return L + (permits.length ? `<select data-fk="${f.k}"><option value="">Choose…</option>${permits.map((r) => `<option value="${r.id}" ${val === r.id ? "selected" : ""}>${esc(r.record_date)} · ${esc(r.summary)}</option>`).join("")}</select>`
        : `<div class="note info small">${online() ? "No open permits." : "Open permits load with a signal."}</div>`);
      case "open_incident": return L + (incidents.length ? `<select data-fk="${f.k}"><option value="">Choose…</option>${incidents.map((r) => `<option value="${r.id}" ${val === r.id ? "selected" : ""}>${esc(r.record_date)} · ${esc(r.title || r.summary)}${r.investigation_id ? "" : " (not investigated yet)"}</option>`).join("")}</select>`
        : `<div class="note info small">${online() ? "No open incidents." : "Open incidents load with a signal."}</div>`);
      case "ra_role": return L + `<select data-fk="${f.k}"><option value="">Choose…</option>${(S.data.ra_roles || []).map((r) => `<option ${val === r ? "selected" : ""}>${esc(r)}</option>`).join("")}</select>
        ${(S.data.ra_roles || []).length ? "" : `<div class="note info small">Load the consultant's risk assessment first (More → Client documents).</div>`}`;
      case "fixed": return L + `<div class="card small">${esc(f.value)}</div>`;
      default: return L + `<input data-fk="${f.k}" value="${esc(val || "")}" placeholder="${esc(f.ph || "")}">`;
    }
  };
  render(`${head(F.title, esc(F.purpose) + ` <span class="muted small">(${esc(F.reg)})</span>`, "board")}
    <div class="card">${F.fields.map(field).join("")}
      ${needsPick ? `<label>${esc(F.signers.find((g) => g.who === "pick").label)}</label><select id="fm-pick"><option value="">Choose…</option>
        ${S.data.workers.map((w) => `<option value="worker:${w.id}">${esc(w.name)}</option>`).join("")}
        ${S.data.users.map((u) => `<option value="user:${u.id}">${esc(u.name)} (login)</option>`).join("")}</select>` : ""}</div>
    ${actionBar(`<button class="primary" data-act="fm-sign" data-kind="${kind}">Sign and save</button>`)}`);
  $("#view").oninput = $("#view").onchange = (e) => {
    const t = e.target;
    if (t.dataset.fk) v[t.dataset.fk] = t.value;
    if (t.dataset.fmMulti) v[t.dataset.fmMulti] = [...document.querySelectorAll(`[data-fm-multi="${t.dataset.fmMulti}"]:checked`)].map((x) => x.value);
  };
};
const redrawForm = (kind) => { const y = scrollY; VIEWS.form(kind).then(() => scrollTo(0, y)); };
ACT["fm-yn"] = (el) => { const k = location.hash.split("/")[1]; FORM_STATE[k][el.dataset.k] = el.dataset.v === "true"; redrawForm(k); };
ACT["fm-sel"] = (el) => { const k = location.hash.split("/")[1]; FORM_STATE[k][el.dataset.k] = el.dataset.v; redrawForm(k); };
ACT["fm-sign"] = async (btn) => {
  const kind = btn.dataset.kind, F = S.data.forms[kind], v = FORM_STATE[kind] || {};
  for (const f of F.fields) {
    const val = v[f.k];
    if (f.req && f.type !== "fixed" && (val === undefined || val === "" || (Array.isArray(val) && !val.length))) return toast(`Fill in: ${f.label}.`, "bad");
  }
  const sigs = [];
  for (const g of F.signers) {
    let who;
    if (g.who === "me") who = { name: me().name, user_id: me().id };
    else if (g.who.startsWith("field:")) { const w = worker(v[g.who.slice(6)]); who = { name: w.name, worker_id: w.id }; }
    else {
      const p = $("#fm-pick")?.value;
      if (!p) return toast(`Choose: ${g.label}.`, "bad");
      if (p.startsWith("user:")) { const u = S.data.users.find((x) => "user:" + x.id === p); who = { name: u.name, user_id: u.id }; }
      else { const w = worker(p.slice(7)); who = { name: w.name, worker_id: w.id }; }
    }
    const sig = await signatureModal({ name: who.name, subtitle: `${g.label}: ${F.title}`, photo: false });
    if (!sig) return;
    sigs.push({ ...sig, ...who, role: g.role });
  }
  btn.disabled = true;
  await finishRecord(kind, { ...v }, sigs, { label: F.title });
  delete FORM_STATE[kind];
  go("board");
};

// ---------------------------------------------------------------- consultant documents

let RA_PREVIEW = null, SPEC_PREVIEW = null;
const BAND_CLS = { Low: "green", Medium: "amber", Significant: "red", High: "red" };
const bandChip = (n, b) => n ? `<span class="badge ${BAND_CLS[b] || ""}">${n}${b ? " " + b : " ⚠"}</span>` : "";

VIEWS.consultant = async () => {
  if (needOnline()) return;
  const c = await api("/api/consultant?site_id=" + S.siteId);
  const flagsHtml = (fl) => fl.map((f) => `<div class="note ${f.level === "red" ? "bad" : f.level === "amber" ? "warn" : "info"} small">${esc(f.text)}</div>`).join("");
  const cov = c.coverage?.results || [];
  render(`${head("Client documents", "Load the consultant's risk assessment and the client's specification. The board then checks the site against them.", "more")}
    <h2>Baseline risk assessment</h2>
    <div class="card">${c.ra ? `<b>RA ${esc(c.ra.header.ra_no || "")} · ${esc(c.ra.header.description || "")}</b>
        <div class="muted small">${esc((c.ra.header.team || []).map((t) => t.name + " (" + t.title + ")").join(", "))} · ${esc(c.ra.header.date || "")} · review ${esc(c.ra.header.review_date || "-")}</div>
        <div class="muted small">Loaded ${esc(c.ra.imported_at.slice(0, 10))} by ${esc(c.ra.imported_by)}${c.ra_only ? " · the AI uses only this assessment on this site" : ""}</div>
        <a class="small" href="${c.ra.file_url}" target="_blank">Open the original</a>${flagsHtml(c.ra.flags)}`
      : `<p class="muted small">PDF, Word, Excel or a photo. The app copies every row with its scores, checks it against the risk matrix, and the AI then uses only these activities on task sheets.</p>`}
      ${can.manage() ? `<button class="${c.ra ? "" : "primary"}" data-act="ra-up" style="margin-top:8px">${c.ra ? "Load a new revision" : "Upload the risk assessment"}</button>` : ""}</div>
    <h2>Client H&S specification</h2>
    <div class="card">${c.spec ? `<b>${esc(c.spec.project || "Specification")}</b> <span class="muted small">${esc(c.spec.author || "")} · ${esc(c.spec.date || "")}</span>
        <div class="small" style="margin-top:6px">${Object.entries(c.spec.frequencies || {}).filter(([, d]) => d).map(([k, d]) => `<span class="badge" style="margin:2px">${esc(k.replace(/_days|_min/g, "").replace(/_/g, " "))}: ${d}${k.endsWith("_min") ? "" : " d"}</span>`).join("")}</div>
        <p class="small muted">${(c.spec.required_documents || []).length} documents · ${(c.spec.required_appointments || []).length} appointments · permits: ${esc((c.spec.permits || []).join(", ") || "none")}</p>
        <a class="small" href="${c.spec.file_url}" target="_blank">Open the original</a>
        ${can.manage() ? `<button class="dark" data-act="spec-accept" style="margin-top:8px">Issue the acceptance page for signing</button>` : ""}`
      : `<p class="muted small">The app reads the specification: frequencies, documents, appointments, permits, the client's hazards and the site rules. They become tiles on the Site Board.</p>`}
      ${can.manage() ? `<button class="${c.spec ? "" : "primary"}" data-act="spec-up" style="margin-top:8px">${c.spec ? "Load a new version" : "Upload the specification"}</button>` : ""}</div>
    ${cov.length ? `<h2>Client's hazards in the risk assessment</h2><div class="card"><ul class="plain">${cov.map((x) => `<li class="row"><span class="dot ${x.status === "covered" ? "green" : x.status === "partial" ? "amber" : "red"}"></span>
      <div class="grow"><b>${esc(x.hazard)}</b><div class="muted small">${esc(x.note || x.status)}</div></div></li>`).join("")}</ul>
      ${can.manage() ? `<button class="small" data-act="cov-re">Check again</button>` : ""}</div>` : ""}`);
};
async function uploadThenPreview(btn, path, label) {
  const f = await pickFile("application/pdf,image/*,.docx,.xlsx");
  if (!f) return;
  render(`<div class="spinner"></div><p class="center">Reading the ${label}… about 30 seconds.</p>`);
  try { return await api(path, { json: { site_id: S.siteId, file: f.data, filename: f.name }, timeout: 240000 }); }
  catch (e) { toast(friendly(e), "bad"); go("consultant"); return null; }
}
ACT["ra-up"] = async (btn) => { const r = await uploadThenPreview(btn, "/api/consultant/ra/preview", "risk assessment"); if (r) { RA_PREVIEW = r; go("ra-preview"); } };
ACT["spec-up"] = async (btn) => { const r = await uploadThenPreview(btn, "/api/consultant/spec/preview", "specification"); if (r) { SPEC_PREVIEW = r; go("spec-preview"); } };
ACT["cov-re"] = (btn) => busy(btn, "Checking…", async () => { await api("/api/consultant/coverage", { json: { site_id: S.siteId }, timeout: 120000 }); route(); });
ACT["spec-accept"] = (btn) => busy(btn, "Making…", async () => { await api("/api/consultant/spec/acceptance", { json: { site_id: S.siteId } }); toast("Ready to sign.", "ok"); go("aes"); });

VIEWS["ra-preview"] = () => {
  const r = RA_PREVIEW;
  if (!r) return go("consultant");
  const h = r.header;
  render(`${head("Check the risk assessment", "This is what the app read. Nothing is saved until you confirm.", "consultant")}
    <div class="card"><b>RA ${esc(h.ra_no)} · ${esc(h.description)}</b><div class="muted small">${esc(h.location)} · ${esc(h.date)} · review ${esc(h.review_date || "-")}</div>
      <div class="small">Team: ${esc((h.team || []).map((t) => t.name + " (" + t.title + ")").join(", ") || "-")}</div></div>
    <h2>What the app found</h2>${r.flags.map((f) => `<div class="note ${f.level === "red" ? "bad" : f.level === "amber" ? "warn" : "info"} small">${esc(f.text)}</div>`).join("") || `<div class="note ok">No problems found.</div>`}
    <h2>${r.items.length} activities</h2>
    ${r.items.map((it) => { const z = it.hazards[0]; return `<div class="card"><div class="row between"><b>${esc(it.activity)}</b><span class="muted small">${esc(it.ref.split(" · ")[1] || "")}</span></div>
      <div class="small">${esc(z.hazard)}${z.consequence ? ` → <i>${esc(z.consequence)}</i>` : ""}</div>
      <div class="row small" style="margin:6px 0;gap:6px">${bandChip(z.rating, z.band)} → ${bandChip(z.rrating, z.rband)} <span class="muted">· ${esc(z.responsible)}</span></div>
      <div class="small muted">${z.controls.map(esc).join("; ")}</div>${it.ppe.length ? `<div class="small"><b>PPE:</b> ${esc(it.ppe.join(", "))}</div>` : ""}</div>`; }).join("")}
    <div class="card"><label class="check"><input type="checkbox" id="ra-approve" checked> This is the approved assessment, signed by the competent person named above</label>
      <label class="check"><input type="checkbox" id="ra-only" checked> Use only this assessment on this site (not the starter library)</label></div>
    ${actionBar(`<button class="primary" data-act="ra-confirm">Load into the app</button>`)}`);
};
ACT["ra-confirm"] = (btn) => busy(btn, "Loading…", async () => {
  const r = await api("/api/consultant/ra/confirm", { json: { site_id: S.siteId, approve: $("#ra-approve").checked, ra_only: $("#ra-only").checked }, timeout: 180000 });
  RA_PREVIEW = null; await loadSite(true); toast(`${r.items} activities loaded.`, "ok"); go("consultant");
});

VIEWS["spec-preview"] = () => {
  const s = SPEC_PREVIEW;
  if (!s) return go("consultant");
  const list = (title, arr, fn) => arr?.length ? `<h2>${title} (${arr.length})</h2><div class="card"><ul class="plain">${arr.map((x) => `<li class="small">${fn(x)}</li>`).join("")}</ul></div>` : "";
  render(`${head("Check the specification", "This is what the app read. Nothing is saved until you confirm.", "consultant")}
    <div class="card"><b>${esc(s.project || "")}</b><div class="muted small">${esc(s.author || "")} · ${esc(s.date || "")}</div></div>
    <h2>Frequencies</h2><div class="card"><ul class="plain">${Object.entries(s.frequencies).filter(([, d]) => d).map(([k, d]) => `<li class="row between small"><span>${esc(k.replace(/_days|_min/g, "").replace(/_/g, " "))}</span><b>${k.endsWith("_min") ? "at least " + d : "every " + d + " day(s)"}</b></li>`).join("")}</ul></div>
    ${list("Client's hazards for the risk assessment", s.client_hazards, esc)}
    ${list("Permits", s.permits, esc)}
    ${list("Documents for the file", s.required_documents, (d) => `${esc(d.title)} <span class="muted">(${esc(d.clause)})</span>`)}
    ${list("Appointments", s.required_appointments, (a) => `${esc(a.title)} <span class="muted">(${esc(a.clause)})</span>`)}
    ${list("Inspections", s.required_inspections, (i) => `${esc(i.item)}${i.days ? " · every " + i.days + " d" : ""} <span class="muted">(${esc(i.clause)})</span>`)}
    ${list("Site rules (added to every induction)", s.key_rules, (r) => `${esc(r.rule)} <span class="muted">(${esc(r.clause)})</span>`)}
    ${list("Must sign acceptance", s.acceptance_signatories, esc)}
    ${actionBar(`<button class="primary" data-act="spec-confirm">Use this specification</button>`)}`);
};
ACT["spec-confirm"] = (btn) => busy(btn, "Saving…", async () => {
  await api("/api/consultant/spec/confirm", { json: { site_id: S.siteId }, timeout: 180000 });
  SPEC_PREVIEW = null; await loadSite(true); toast("Specification in use. See the board.", "ok"); go("board");
});

// ---------------------------------------------------------------- H&S plan (CR 7(1)(a))
// The app drafts the principal contractor's site plan from the client's spec, the
// site and the risk assessment. A competent person checks it; the client approves it.

VIEWS.hsplan = async () => {
  if (needOnline()) return;
  const r = await api("/api/hs-plan?site_id=" + S.siteId);
  drawPlan(r);
};
function drawPlan(r) {
  const p = r.plan, aesDoc = p?.aes, missing = r.inputs.filter((i) => !i.ok);
  const status = aesDoc?.status === "signed" ? `<div class="note ok"><b>Approved plan on file.</b> Version ${p.version}, signed ${esc(aesDoc.signed_at)}. It is in the safety file.</div>`
    : aesDoc ? `<div class="note warn"><b>Version ${p.version} is out for signature</b> since ${esc(aesDoc.created_at)}. Upload the signed copy when it comes back.
        <button class="small" data-act="nav" data-to="aes" style="margin-top:6px">Open documents for signing</button></div>` : "";
  render(`${head("H&S plan", "The principal contractor's site plan (CR 7(1)(a)). The app drafts it from the client's spec, the site and the risk assessment. A competent person checks and signs it; the client approves it.", "file")}
    ${status}
    <div class="card"><b>What the plan is built from</b>
      ${r.inputs.map((i) => `<div class="row" style="margin-top:8px;align-items:flex-start"><span class="badge ${i.ok ? "ok" : "warn"}" style="flex:none">${i.ok ? "✓" : "!"}</span>
        <div class="grow small"><b>${esc(i.label)}</b>${i.ok ? "" : `<div class="muted">${esc(i.detail)} <a href="#${i.action}">Fix</a></div>`}</div></div>`).join("")}
      ${missing.length ? `<p class="small muted" style="margin-top:8px">You can draft now. Missing facts show in the plan as <b>[to complete]</b>.</p>` : ""}</div>
    ${!p ? `<div class="card"><p>The app writes all ${r.sections.length} sections: scope, policy, appointments, risk assessment, training, inspections, site hazards, permits, PPE, contractors, incidents, emergencies, welfare, records and review.</p>
        <p class="small muted">It takes about a minute. You can change any text before you issue it.</p></div>
        ${can.manage() ? actionBar(`<button class="primary" data-act="plan-draft">✍️ Draft the plan</button>`) : ""}`
      : planEditor(r)}`);
}
function planEditor(r) {
  const p = r.plan, edit = can.manage() && p.aes?.status !== "signed";
  return `${p.questions?.length ? `<div class="note warn"><b>The plan still needs:</b>${p.questions.map((q) => `<div>• ${esc(q)}</div>`).join("")}</div>` : ""}
    <p class="small muted">Drafted ${esc((p.generated_at || "").replace("T", " "))} by ${esc(p.generated_by || "")}${p.edited_at ? ` · changed ${esc(p.edited_at.replace("T", " "))}` : ""}.
      Lines that start with “## ” are headings; “- ” are bullet points.</p>
    ${r.sections.map((s, i) => `<details class="card" ${i === 0 ? "open" : ""}><summary><b>${i + 1}. ${esc(s.title)}</b>
        ${s.src.includes("ai") && /\[to complete/i.test(p.text[s.key] || "") ? '<span class="badge warn">to complete</span>' : ""}</summary>
      ${s.src.includes("ai") ? `<textarea data-plan="${s.key}" style="min-height:220px" ${edit ? "" : "readonly"}>${esc(p.text[s.key] || "")}</textarea>` : ""}
      ${s.src.includes("data") ? `<div class="note info small">📋 ${esc(r.summary[s.key] || "Filled in from the app.")} The PDF always uses the latest data.</div>` : ""}</details>`).join("")}
    ${edit ? `<div class="card"><b>Issue for signature</b>
      <p class="small muted">The PDF goes to three signers: the principal contractor, the competent person who checked it (SACPCMP-registered), and the client or client's agent.</p>
      <div class="grid2"><div><label>Competent person who checked it</label><input id="pl-rev" value="${esc(r.consultants[0]?.name || "")}"></div>
        <div><label>Registration no.</label><input id="pl-reg" value="${esc(r.consultants[0]?.reg || "")}" placeholder="SACPCMP no."></div></div>
      <div class="grid2"><div><label>Signs for the principal contractor</label><input id="pl-pc" value="${esc(me().name)}"></div>
        <div><label>Signs for the client</label><input id="pl-cl" value="${esc(r.client || "")}"></div></div>
      <button class="dark" data-act="plan-issue">Issue version ${(p.version || 0) + 1} for signature</button></div>
      <button class="link" data-act="plan-draft">Draft it again from scratch</button>` : ""}
    ${actionBar(`<button class="primary" data-act="pdf" data-path="/api/hs-plan/pdf?site_id=${S.siteId}">📄 Preview the plan (PDF)</button>`)}`;
}
let planTimer = null;
document.addEventListener("input", (e) => {
  const k = e.target.dataset?.plan;
  if (!k) return;
  clearTimeout(planTimer);
  planTimer = setTimeout(async () => {
    const text = {};
    document.querySelectorAll("[data-plan]").forEach((t) => { text[t.dataset.plan] = t.value; });
    try { await api("/api/hs-plan", { method: "PUT", json: { site_id: S.siteId, text } }); toast("Saved.", "ok"); }
    catch (err) { toast(friendly(err), "bad"); }
  }, 1200);
});
ACT["plan-draft"] = async (btn) => {
  if (btn.classList.contains("link") && !confirm("Draft the whole plan again? Your changes to the text are replaced.")) return;
  render(`<div class="spinner"></div><p class="center">Writing the H&amp;S plan from the client's spec, the site and the risk assessment…<br><span class="muted small">About a minute. Keep this screen open.</span></p>`);
  try { drawPlan(await api("/api/hs-plan/draft", { json: { site_id: S.siteId }, timeout: 240000 })); toast("Plan drafted. Check every section.", "ok"); }
  catch (e) { toast(friendly(e), "bad"); VIEWS.hsplan(); }
};
ACT["plan-issue"] = (btn) => busy(btn, "Issuing…", async () => {
  if (!$("#pl-rev").value.trim()) return toast("Name the competent person who checked the plan.", "bad");
  await api("/api/hs-plan/issue", { json: { site_id: S.siteId, reviewer: $("#pl-rev").value, reviewer_reg: $("#pl-reg").value,
    pc_signer: $("#pl-pc").value, client_signer: $("#pl-cl").value } });
  toast("Issued. Send the PDF for signature.", "ok"); go("aes");
});
