"""The Site Board: every legal duty for one site as a green, amber or red tile.

Each tile says what the law asks (with the regulation), what the site has,
and which screen fixes it. Status rules:
  red    the duty is not met now (missing, expired, overdue)
  amber  met for now, but action is due soon or something is incomplete
  green  met
  na     does not apply to this site (switched off in site setup)
"""
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import config, db, library

GROUPS = ["Today", "People", "Plant and inspections", "Appointments and documents",
          "Contractors", "Audits and incidents", "Client specification"]


def records_value(rec, key):
    for f in (rec.payload or {}).get("fields", []):
        if f["k"] == key:
            return f["value"]
    return None


def _tile(group, key, title, reg, status, detail, action="", count=None):
    return {"group": group, "key": key, "title": title, "reg": reg, "status": status,
            "detail": detail, "action": action, "count": count}


def _exp(d: date | None, today: date) -> str:
    if not d:
        return "none"
    if d < today:
        return "expired"
    if d <= today + timedelta(days=config.EXPIRY_WARN_DAYS):
        return "expiring"
    return "valid"


def board(s, company: db.Company, site: db.Site, today: date, now_hour: int = 12) -> dict:
    cid, sid = company.id, site.id
    feats = site.features or {}
    on = lambda f: f is None or bool(feats.get(f))
    tiles = []
    cfg = site.settings or {}
    spec = cfg.get("spec") or {}
    freq = spec.get("frequencies") or {}

    recs = s.scalars(select(db.Record).where(db.Record.site_id == sid,
                                             db.Record.record_date >= today - timedelta(days=400))
                     .options(selectinload(db.Record.signatures))).all()
    by_kind: dict[str, list] = {}
    for r in recs:
        by_kind.setdefault(r.kind, []).append(r)
    for v in by_kind.values():
        v.sort(key=lambda r: (r.record_date, r.seq))

    # ------------------------------------------------------------ Today
    ts_today = [r for r in by_kind.get("task_sheet", []) if r.record_date == today]
    if ts_today:
        review = any(r.payload.get("unmatched") or not all(t.get("assessed") for t in r.payload.get("tasks", []))
                     for r in ts_today)
        tiles.append(_tile("Today", "task_sheet", "Daily task sheet", "9(3)", "amber" if review else "green",
                           "Done. Some tasks need the safety officer's review." if review else "Done and signed.", "task"))
    else:
        tiles.append(_tile("Today", "task_sheet", "Daily task sheet", "9(3)", "red" if now_hour >= 9 else "amber",
                           "Not done yet. Brief the workers and get it signed before work.", "task"))

    talks = by_kind.get("toolbox_talk", [])
    last_talk = talks[-1].record_date if talks else None
    age = (today - last_talk).days if last_talk else None
    tdays = freq.get("toolbox_talk_days") or 7
    tiles.append(_tile("Today", "toolbox_talk", "Toolbox talk", "9(3)" + (", spec" if spec else ""),
                       "green" if age is not None and age < tdays - 1 else
                       "amber" if age is not None and age <= tdays else "red",
                       ("Talk done today." if age == 0 else f"Last talk {age} day(s) ago.") if age is not None
                       else "No talk recorded yet.", "talk"))

    visitors_today = [r for r in by_kind.get("visitor", []) if r.record_date == today]
    tiles.append(_tile("Today", "visitors", "Visitor register", "7(6)", "green",
                       f"{len(visitors_today)} visitor(s) inducted today." if visitors_today else
                       "No visitors today. Induct every visitor before entry.", "visitors", len(visitors_today)))

    # ------------------------------------------------------------ People
    workers = s.scalars(select(db.Worker).join(db.SiteWorker, db.SiteWorker.worker_id == db.Worker.id)
                        .where(db.SiteWorker.site_id == sid, db.Worker.active)
                        .options(selectinload(db.Worker.credentials))).all()
    inducted = {r.payload.get("worker_id") for r in by_kind.get("induction", [])}
    not_ind = [w.name for w in workers if w.id not in inducted]
    if not workers:
        tiles.append(_tile("People", "inductions", "Inductions", "7(5), 7(7)", "red",
                           "No workers on this site yet.", "workers"))
    else:
        tiles.append(_tile("People", "inductions", "Inductions", "7(5), 7(7)", "red" if not_ind else "green",
                           (f"{len(not_ind)} not inducted: " + ", ".join(not_ind[:4])) if not_ind
                           else f"All {len(workers)} workers inducted.", "workers", len(not_ind)))

    med_bad, med_soon = [], []
    for w in workers:
        meds = [c for c in w.credentials if c.kind == "medical"]
        st = max((_exp(c.expires, today) for c in meds), key=["expired", "expiring", "none", "valid"].index,
                 default="missing")
        if st in ("missing", "expired"):
            med_bad.append(w.name)
        elif st == "expiring":
            med_soon.append(w.name)
    tiles.append(_tile("People", "medicals", "Medical certificates", "7(8), Annexure 3",
                       "red" if med_bad else "amber" if med_soon else "green" if workers else "na",
                       (f"{len(med_bad)} missing or expired: " + ", ".join(med_bad[:4])) if med_bad
                       else (f"{len(med_soon)} expire within 30 days." if med_soon else "All valid."),
                       "workers", len(med_bad)))

    cert_bad = [f"{w.name}: {c.title}" for w in workers for c in w.credentials
                if c.kind != "medical" and _exp(c.expires, today) == "expired"]
    cert_soon = [f"{w.name}: {c.title}" for w in workers for c in w.credentials
                 if c.kind != "medical" and _exp(c.expires, today) == "expiring"]
    tiles.append(_tile("People", "certificates", "Training and licences", "9(3), 23(1)(d)",
                       "red" if cert_bad else "amber" if cert_soon else "green",
                       (f"{len(cert_bad)} expired: " + "; ".join(cert_bad[:3])) if cert_bad
                       else (f"{len(cert_soon)} expire within 30 days." if cert_soon else "No expired certificates."),
                       "workers", len(cert_bad)))

    # ------------------------------------------------------------ Plant and inspections
    plant = s.scalars(select(db.Plant).where(db.Plant.company_id == cid, db.Plant.active,
                                             db.Plant.site_id == sid)).all()
    checks = by_kind.get("check", [])
    checks_today = {r.payload.get("plant_id"): r.payload.get("result") for r in checks if r.record_date == today}
    if plant or on("mobile_plant") and feats.get("mobile_plant"):
        failed = [p.name for p in plant if checks_today.get(p.id) == "fail"]
        missing = [p.name for p in plant if p.id not in checks_today]
        st = "red" if failed or (missing and now_hour >= 9) else "amber" if missing else "green"
        detail = (f"FAILED, do not use: {', '.join(failed)}. " if failed else "") + \
                 (f"Not checked today: {', '.join(missing[:4])}." if missing else "") or \
                 (f"All {len(plant)} item(s) checked today." if plant else "Add the plant on this site.")
        tiles.append(_tile("Plant and inspections", "plant_checks", "Plant pre-use checks", "23(1)(k)",
                           st if plant else "red", detail, "check", len(failed) + len(missing)))
        # Operators authorised in writing
        appts = by_kind.get("appointment", [])
        authorised = {r.payload.get("appointee", {}).get("worker_id") for r in appts if r.payload.get("type") == "operator"}
        operators = {g.worker_id: g.name for r in checks if r.payload.get("plant_id")
                     and r.record_date >= today - timedelta(days=30) for g in r.signatures
                     if g.role == "operator" and g.worker_id}
        unauth = [n for wid, n in operators.items() if wid not in authorised]
        tiles.append(_tile("Plant and inspections", "operators", "Operators authorised in writing", "23(1)(d)(i)",
                           "red" if unauth or (plant and not authorised) else "green",
                           (f"Not authorised: {', '.join(unauth[:4])}." if unauth else
                            "No operator authorisation on file." if plant and not authorised else
                            f"{len(authorised)} operator(s) authorised."), "appointments", len(unauth)))

    schedule = {k: dict(v) for k, v in library.INSPECTION_SCHEDULE.items()}
    equipment = {"scaffold", "excavation", "temporary_works", "material_hoist"}
    for ri in spec.get("required_inspections") or []:
        k = ri.get("checklist")
        c = library.CHECKLISTS.get(k)
        if not c or c["kind"] != "inspection":
            continue
        cur = schedule.get(k, {"every": "month", "days": 30, "feature": None, "reg": ""})
        days = ri.get("days") or cur["days"]
        cur.update(days=days, every={1: "day", 7: "week", 30: "month"}.get(days, f"{days} days"),
                   reg=f"{cur['reg']}, spec {ri.get('clause', '')}".strip(", "),
                   feature=cur["feature"] if k in equipment else None)
        schedule[k] = cur
    for tpl, sched in schedule.items():
        c = library.CHECKLISTS[tpl]
        if not on(sched["feature"]):
            continue
        done = [r for r in checks if r.payload.get("template") == tpl]
        last = done[-1] if done else None
        days = (today - last.record_date).days if last else None
        if last and last.payload.get("result") == "fail" and days == 0:
            st, detail = "red", "Failed today. Do not use until fixed and inspected again."
        elif days is None:
            st, detail = "red", f"Never inspected. Due every {sched['every']}."
        elif days >= sched["days"]:
            st, detail = "red", f"Overdue: last inspection {days} day(s) ago. Due every {sched['every']}."
        elif sched["days"] > 1 and days >= sched["days"] - 1:
            st, detail = "amber", f"Due tomorrow (last {last.record_date})."
        else:
            st, detail = "green", f"Inspected {'today' if days == 0 else f'{days} day(s) ago'}."
        tiles.append(_tile("Plant and inspections", f"insp_{tpl}", c["title"], sched["reg"], st, detail,
                           f"checklist/{tpl}"))

    # ------------------------------------------------------------ Appointments and documents
    tiles.append(_tile("Appointments and documents", "esign", "E-signature agreement", "ECT Act s13",
                       "green" if company.esign_accepted_at else "red",
                       f"Accepted by {company.esign_accepted_by}." if company.esign_accepted_at
                       else "The owner must accept the e-signature agreement once.", "esign"))

    appts = by_kind.get("appointment", [])
    have = {r.payload.get("type") for r in appts}
    need = [k for k, f in library.REQUIRED_APPOINTMENTS if on(f)]
    for a in spec.get("required_appointments") or []:
        k = a.get("key")
        gate = {"scaffold": "scaffolding", "scaffold_inspector": "scaffolding", "temporary_works_designer": "temporary_works",
                "temporary_works_supervisor": "temporary_works", "fall_protection": "work_at_height"}.get(k)
        if k in library.APPOINTMENTS and k not in need and k not in ("hs_rep", "assistant_manager", "assistant_supervisor") \
                and (gate is None or feats.get(gate)):
            need.append(k)
    if len(workers) > 20 and "hs_rep" not in need:
        need.append("hs_rep")    # OHS Act s17: more than 20 employees
    missing = [library.APPOINTMENTS[k]["title"] for k in need if k not in have]
    aes = s.scalars(select(db.AesDoc).where(db.AesDoc.company_id == cid,
                                            (db.AesDoc.site_id == sid) | (db.AesDoc.site_id.is_(None)))).all()
    aes_wait = [a for a in aes if a.status != "signed"]
    tiles.append(_tile("Appointments and documents", "appointments", "Legal appointments", "8, 9, 10, 13, 16, 23",
                       "red" if missing else "amber" if any(a.kind == "appointment" for a in aes_wait) else "green",
                       (f"Missing: {', '.join(missing[:4])}" + (" and more." if len(missing) > 4 else "."))
                       if missing else "All required appointments made.", "appointments", len(missing)))
    tiles.append(_tile("Appointments and documents", "aes", "Documents awaiting AES", "ECT Act s13(1)",
                       "amber" if aes_wait else "green",
                       f"{len(aes_wait)} document(s) wait for an advanced e-signature or wet ink."
                       if aes_wait else "All signed.", "aes", len(aes_wait)))

    rq = select(db.RiskItem).where(db.RiskItem.company_id == cid, db.RiskItem.active)
    rq = rq.where(db.RiskItem.site_id == sid) if cfg.get("ra_only") else \
        rq.where((db.RiskItem.site_id.is_(None)) | (db.RiskItem.site_id == sid))
    risks = s.scalars(rq).all()
    used = {x["id"] for r in by_kind.get("task_sheet", []) if r.record_date >= today - timedelta(days=30)
            for t in r.payload.get("tasks", []) for x in t.get("risks", [])}
    used_unapproved = [r.activity for r in risks if r.id in used and not r.approved_at]
    unapproved = [r for r in risks if not r.approved_at]
    tiles.append(_tile("Appointments and documents", "risk", "Risk assessment approved", "9(1)",
                       "red" if used_unapproved or not any(r.approved_at for r in risks)
                       else "amber" if unapproved else "green",
                       (f"In use but not approved: {', '.join(used_unapproved[:3])}." if used_unapproved else
                        f"{len(unapproved)} of {len(risks)} activities not approved." if unapproved else
                        "All activities approved by a competent person."), "risks", len(used_unapproved)))

    docs = s.scalars(select(db.Doc).where(db.Doc.company_id == cid,
                                          (db.Doc.site_id.is_(None)) | (db.Doc.site_id == sid))).all()
    have_docs = {d.section for d in docs}
    def doc_tile(key, section, title, reg, feature=None):
        if not on(feature):
            return
        hit = [d for d in docs if d.section == section]
        exp = [d for d in hit if _exp(d.expires, today) == "expired"]
        soon = [d for d in hit if _exp(d.expires, today) == "expiring"]
        st = "red" if not hit or exp else "amber" if soon else "green"
        detail = "Not uploaded." if not hit else f"Expired: {exp[0].title}." if exp else \
            f"Expires {soon[0].expires}." if soon else "On file."
        tiles.append(_tile("Appointments and documents", key, title, reg, st, detail, "file"))
    doc_tile("hs_plan", "hs_plan", "H&S plan (approved)", "7(1)(a)")
    doc_tile("client_spec", "client_spec", "Client H&S specification", "5(1)(b)")
    doc_tile("notification", "notification", "Notification / work permit", "3, 4")
    doc_tile("coid", "company", "COID letter of good standing", "5(1)(j)")
    doc_tile("fall_plan", "fall_protection", "Fall protection plan", "10", "work_at_height")
    doc_tile("emergency", "emergency", "Emergency plan", "GSR 3, ERW 9")
    wanted = {d.get("section") for d in spec.get("required_documents") or []}
    if "policies" in wanted:
        n_pol = len([d for d in spec["required_documents"] if d.get("section") == "policies"])
        have_pol = [d for d in docs if d.section == "policies"]
        tiles.append(_tile("Appointments and documents", "policies", "Company policies (signed)", "spec 2.1-2.3, 4.3",
                           "green" if len(have_pol) >= n_pol else "red" if not have_pol else "amber",
                           f"{len(have_pol)} of {n_pol} on file: " + ", ".join(d["title"].split(" signed")[0]
                                                                         for d in spec["required_documents"] if d.get("section") == "policies"),
                           "file", n_pol - len(have_pol)))
    if "organogram" in wanted:
        doc_tile("organogram", "organogram", "Organogram", "spec 2.4.11")
    if "fire_survey" in wanted:
        doc_tile("fire_survey", "fire_survey", "Fire risk survey", "spec 3.4.3")

    # ------------------------------------------------------------ Contractors
    contractors = s.scalars(select(db.Contractor).where(db.Contractor.site_id == sid, db.Contractor.active)).all()
    if contractors or feats.get("subcontractors"):
        agreements = {a.contractor_id for a in aes if a.kind == "mandatary_agreement" and a.status == "signed"}
        agreements_any = {a.contractor_id for a in aes if a.kind == "mandatary_agreement"}
        bad, warn = [], []
        for c in contractors:
            ce = _exp(c.coid_expires, today)
            if ce in ("expired", "none") or not c.coid_file:
                bad.append(f"{c.name}: COID letter")
            elif ce == "expiring":
                warn.append(f"{c.name}: COID expires {c.coid_expires}")
            if c.id not in agreements_any:
                bad.append(f"{c.name}: 37(2) agreement")
            elif c.id not in agreements:
                warn.append(f"{c.name}: 37(2) agreement not signed")
            if not c.appointed_on:
                bad.append(f"{c.name}: appointment in writing")
            if not c.hs_plan_ok:
                warn.append(f"{c.name}: H&S plan not approved")
        tiles.append(_tile("Contractors", "contractors", "Contractors", "7(1)(c), 7(1)(f), OHS s37(2)",
                           "red" if bad or not contractors else "amber" if warn else "green",
                           ("; ".join(bad[:3]) + ("…" if len(bad) > 3 else "")) if bad else
                           ("; ".join(warn[:3])) if warn else
                           (f"{len(contractors)} contractor(s) in order." if contractors else "Add the contractors on site."),
                           "contractors", len(bad)))

    # ------------------------------------------------------------ Audits and incidents
    audits = by_kind.get("audit", [])
    last_a = audits[-1] if audits else None
    started = site.start_date or site.created_at.date()
    if last_a:
        a_age = (today - last_a.record_date).days
        acked = any(r.payload.get("audit_id") == last_a.id for r in by_kind.get("audit_ack", []))
        st = "red" if a_age > 30 else "amber" if a_age >= 25 or (not acked and a_age > 7) else "green"
        detail = f"Last audit {a_age} day(s) ago, score {last_a.payload.get('score')}%." + \
            ("" if acked else " Report not yet received by the principal contractor (due within 7 days).")
    else:
        due = started + timedelta(days=30)
        st = "red" if today > due else "amber"
        detail = f"No audit yet. First audit due by {due}."
    tiles.append(_tile("Audits and incidents", "audit", "Monthly audit", "5(1)(o)-(p), 7(1)(c)(vii)", st, detail, "audit"))

    incidents = by_kind.get("incident", [])
    inv = {r.payload.get("incident_id"): r for r in by_kind.get("investigation", [])}
    open_inc = [r for r in incidents if r.id not in inv]
    overdue = [r for r in open_inc if (today - r.record_date).days > 7]
    rep = [r for r in open_inc if r.payload.get("possibly_reportable")]
    if not incidents:
        st, detail = "green", "No incidents recorded."
    elif overdue:
        st, detail = "red", f"{len(overdue)} incident(s) not investigated within 7 days."
    elif rep:
        st, detail = "red", f"{len(rep)} possibly reportable incident(s): investigate and report within 7 days."
    elif open_inc:
        st, detail = "amber", f"{len(open_inc)} incident(s) to investigate (within 7 days)."
    else:
        st, detail = "green", f"{len(incidents)} incident(s), all investigated."
    tiles.append(_tile("Audits and incidents", "incidents", "Incidents investigated and reported",
                       "OHS s24, GAR 8-9", st, detail, "incidents", len(open_inc)))

    # ------------------------------------------------------------ consultant's risk assessment
    G = "Client specification"
    ra = cfg.get("ra")
    if ra:
        reds = [f for f in ra.get("flags", []) if f["level"] == "red"]
        ambers = [f for f in ra.get("flags", []) if f["level"] == "amber"]
        h = ra.get("header", {})
        tiles.append(_tile(G, "ra_doc", "Baseline risk assessment", "9(1)",
                           "red" if reds else "amber" if ambers else "green",
                           (f"{len(reds)} problem(s): {reds[0]['text']}" if reds else
                            f"{len(ambers)} point(s) to fix: {ambers[0]['text']}" if ambers else
                            f"RA {h.get('ra_no', '')} by {', '.join(t.get('name', '') for t in h.get('team', []))} in use."),
                           "consultant", len(reds)))
        roles = ra.get("roles") or []
        accepted = {str(records_value(r, "role")).lower() for r in by_kind.get("ra_acceptance", [])}
        missing_roles = [r for r in roles if r.lower() not in accepted]
        tiles.append(_tile(G, "ra_acceptance", "Risk assessment accepted by those responsible", "9(1), spec 2.9.3.5",
                           "red" if missing_roles else "green",
                           ("Not accepted yet: " + "; ".join(missing_roles[:3])) if missing_roles else "All responsible roles accepted.",
                           "form/ra_acceptance", len(missing_roles)))

    # ------------------------------------------------------------ the client's specification
    if spec:
        aes_spec = [a for a in aes if a.kind == "spec_acceptance"]
        tiles.append(_tile(G, "spec_acceptance", "Specification accepted and signed", "5(1)(b), spec p.26",
                           "green" if any(a.status == "signed" for a in aes_spec) else "amber" if aes_spec else "red",
                           "Signed." if any(a.status == "signed" for a in aes_spec) else
                           "Issued, waiting for signatures." if aes_spec else
                           "Issue the acceptance page for signing: " + ", ".join((spec.get("acceptance_signatories") or [])[:4]),
                           "consultant"))
        cov = (cfg.get("coverage") or {}).get("results") or []
        if spec.get("client_hazards"):
            miss = [c["hazard"] for c in cov if c["status"] == "missing"]
            part = [c["hazard"] for c in cov if c["status"] == "partial"]
            tiles.append(_tile(G, "client_hazards", "Client's hazards in the risk assessment", "spec 2.9.18",
                               "amber" if not cov else "red" if miss else "amber" if part else "green",
                               "Not checked yet." if not cov else
                               (f"{len(miss)} not covered: " + "; ".join(miss[:3])) if miss else
                               (f"{len(part)} only partly covered: " + "; ".join(part[:3])) if part else
                               f"All {len(cov)} client hazards covered.", "consultant", len(miss)))
        talks_env = [r for r in talks if r.payload.get("environmental")]
        need_env = freq.get("environmental_talks_min")
        if need_env:
            tiles.append(_tile(G, "env_talks", "Environmental toolbox talks", "spec 2.11.2.5",
                               "green" if len(talks_env) >= need_env else "amber",
                               f"{len(talks_env)} of at least {need_env} done.", "talk", need_env - len(talks_env)))

        def due_tile(key, kind, title, reg, days, first_within=None, action=None):
            if not days:
                return
            done = by_kind.get(kind, [])
            last = done[-1].record_date if done else None
            if last:
                age_ = (today - last).days
                stt = "red" if age_ > days else "amber" if age_ > days - 7 else "green"
                det = f"Last on {last} ({age_} day(s) ago). Due every {days} days."
            else:
                due = started + timedelta(days=first_within or days)
                stt = "red" if today > due else "amber"
                det = f"None yet. First one due by {due}."
            tiles.append(_tile(G, key, title, reg, stt, det, action or f"form/{kind}"))
        due_tile("drill", "drill", "Evacuation drill", "ERW 9, spec 2.12.6", freq.get("evacuation_drill_days"),
                 freq.get("first_drill_within_days"))
        due_tile("meeting", "meeting", "H&S committee meeting", "OHS s19, spec 2.6.2", freq.get("committee_meeting_days"))
        due_tile("observation", "observation", "Planned task observations", "spec 2.9.12", freq.get("observation_days") or 30)

        issued = {(records_value(r, "worker") or {}).get("id") for r in by_kind.get("ppe_issue", [])}
        no_ppe = [w.name for w in workers if w.id not in issued]
        tiles.append(_tile(G, "ppe_issue", "PPE issue records", "GSR 2, spec 2.16.5",
                           "red" if no_ppe else "green",
                           (f"{len(no_ppe)} worker(s) without a PPE issue record: " + ", ".join(no_ppe[:3])) if no_ppe
                           else "Every worker signed for their PPE.", "form/ppe_issue", len(no_ppe)))

        if spec.get("permits"):
            names = " ".join(x.get("activity", "").lower()
                             for r in ts_today for t in r.payload.get("tasks", []) for x in t.get("risks", []))
            names += " " + " ".join(t.get("description", "").lower() for r in ts_today for t in r.payload.get("tasks", []))
            need_p = [p for p, words in library.PERMIT_TRIGGERS.items() if any(w in names for w in words)]
            have_p = {records_value(r, "type") for r in by_kind.get("permit", []) if r.record_date == today}
            closed = {(records_value(r, "permit") or {}).get("id") for r in by_kind.get("permit_close", [])}
            open_old = [r for r in by_kind.get("permit", []) if r.id not in closed and r.record_date < today]
            missing_p = [p for p in need_p if p not in have_p]
            tiles.append(_tile(G, "permits", "Permits to work", "spec 2.10",
                               "red" if missing_p else "amber" if open_old else "green",
                               (f"Today's work needs a permit: {', '.join(missing_p)}.") if missing_p else
                               (f"{len(open_old)} permit(s) from earlier days not closed.") if open_old else
                               ("Permits in place for today's work." if need_p else "No permit work on today's task sheet."),
                               "form/permit", len(missing_p)))

        fac = spec.get("facilities") or {}
        have_fac = cfg.get("facilities") or {}
        if fac.get("toilet_per_workers") or fac.get("shower_per_workers"):
            import math
            n = len(workers)
            need_t = math.ceil(n / fac["toilet_per_workers"]) if fac.get("toilet_per_workers") and n else 0
            need_s = math.ceil(n / fac["shower_per_workers"]) if fac.get("shower_per_workers") and n else 0
            if not have_fac:
                stt, det = "amber", "Enter the number of toilets and showers in site setup."
            else:
                short = []
                if have_fac.get("toilets", 0) < need_t:
                    short.append(f"toilets {have_fac.get('toilets', 0)} of {need_t}")
                if have_fac.get("showers", 0) < need_s:
                    short.append(f"showers {have_fac.get('showers', 0)} of {need_s}")
                stt = "red" if short else "green"
                det = ("Too few: " + ", ".join(short) + f" for {n} workers.") if short else f"Enough for {n} workers."
            tiles.append(_tile(G, "facilities", "Toilets and showers", "CR 30, Facilities Regs, spec 4.2", stt, det, "setup"))

    counts = {k: sum(t["status"] == k for t in tiles) for k in ("green", "amber", "red", "na")}
    return {"site_id": sid, "date": today.isoformat(), "tiles": tiles, "groups": GROUPS, "counts": counts,
            "features": feats, "generated_at": db.utcnow().isoformat(timespec="seconds") + "Z"}
