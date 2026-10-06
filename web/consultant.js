// Generic register forms (drill, meeting, observation, PPE issue, permit, RA acceptance)
// and the consultant's documents: import the baseline risk assessment and the client's spec.

// ---------------------------------------------------------------- generic form

const FORM_STATE = {};
VIEWS.form = async (kind) => {
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
