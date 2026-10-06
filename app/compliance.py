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
          "Contractors", "Audits and incidents"]


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
    tiles.append(_tile("Today", "toolbox_talk", "Toolbox talk", "9(3)",
                       "green" if age is not None and age < 6 else "amber" if age is not None and age < 8 else "red",
                       f"Last talk {age} day(s) ago." if age is not None else "No talk recorded yet.", "talk"))

    visitors_today = [r for r in by_kind.get("visitor", []) if r.record_date == today]
    tiles.append(_tile("Today", "visitors", "Visitor register", "7(6)", "green",
                       f"{len(visitors_today)} visitor(s) inducted today.", "visitor", len(visitors_today)))

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

    for tpl, sched in library.INSPECTION_SCHEDULE.items():
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

    risks = s.scalars(select(db.RiskItem).where(db.RiskItem.company_id == cid, db.RiskItem.active,
                                                (db.RiskItem.site_id.is_(None)) | (db.RiskItem.site_id == sid))).all()
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

    counts = {k: sum(t["status"] == k for t in tiles) for k in ("green", "amber", "red", "na")}
    return {"site_id": sid, "date": today.isoformat(), "tiles": tiles, "groups": GROUPS, "counts": counts,
            "features": feats, "generated_at": db.utcnow().isoformat(timespec="seconds") + "Z"}
