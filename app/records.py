"""Signed site records: normalise, store, chain and verify.

The device sends a finished record with all signatures in one request. The
request is idempotent on client_id, so the offline outbox can retry safely.
The server, not the device, copies safety content (hazards, controls,
checklist questions, induction text) into the record, then adds the record
to the company's hash chain.
"""
import hashlib
import json
import threading
from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from . import db, files, library

KINDS = {"task_sheet": "Daily task sheet", "toolbox_talk": "Toolbox talk",
         "check": "Check / inspection", "incident": "Incident report",
         "induction": "Site induction", "visitor": "Visitor induction",
         "appointment": "Legal appointment", "audit": "Health and safety audit",
         "audit_ack": "Audit report received", "investigation": "Incident investigation"}
KINDS.update({k: f["title"] for k, f in library.FORMS.items()})
GENESIS = "0" * 64
_chain_lock = threading.Lock()


# ---------------------------------------------------------------- files inside payloads

def _store_files(cid: str, value):
    """Replace data: URLs with {"file": name}; check {"file": name} belongs to the company."""
    if isinstance(value, str) and value.startswith("data:"):
        try:
            return {"file": files.put_data_url(cid, value)}
        except ValueError as e:
            raise HTTPException(400, str(e))
    if isinstance(value, dict):
        if set(value) == {"file"}:
            if not files.owned(cid, value["file"]):
                raise HTTPException(400, "A file in this record is missing. Record it again.")
            return value
        return {k: _store_files(cid, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_store_files(cid, v) for v in value]
    return value


def with_urls(value):
    """Add a signed URL next to every stored file reference."""
    if isinstance(value, dict):
        if set(value) == {"file"}:
            return {"file": value["file"], "url": files.sign(value["file"])}
        return {k: with_urls(v) for k, v in value.items()}
    if isinstance(value, list):
        return [with_urls(v) for v in value]
    return value


def _text(v, n=4000) -> str:
    return str(v or "").strip()[:n]


# ---------------------------------------------------------------- per-kind normalising

def _risk_snapshot(s, cid: str, site_id: str, ids) -> list[dict]:
    ids = [i for i in (ids or []) if isinstance(i, str)][:20]
    if not ids:
        return []
    rows = s.scalars(select(db.RiskItem).where(
        db.RiskItem.company_id == cid, db.RiskItem.id.in_(ids),
        (db.RiskItem.site_id.is_(None)) | (db.RiskItem.site_id == site_id))).all()
    by_id = {r.id: r for r in rows}
    return [{"id": r.id, "activity": r.activity, "hazards": r.hazards, "ppe": r.ppe,
             "approved": r.approved_at is not None, "approved_by": r.approved_by}
            for i in ids if (r := by_id.get(i))]


def _names(s, model, cid: str, ids) -> list[dict]:
    ids = [i for i in (ids or []) if isinstance(i, str)][:200]
    if not ids:
        return []
    rows = s.scalars(select(model).where(model.company_id == cid, model.id.in_(ids))).all()
    by_id = {r.id: r for r in rows}
    return [{"id": i, "name": by_id[i].name} for i in ids if i in by_id]


def _task_sheet(s, cid, site_id, p: dict) -> dict:
    tasks = []
    for t in (p.get("tasks") or [])[:30]:
        snap = _risk_snapshot(s, cid, site_id, t.get("risk_item_ids"))
        ppe = sorted({x for r in snap for x in r["ppe"]})
        tasks.append({
            "description": _text(t.get("description"), 500), "location": _text(t.get("location"), 200),
            "risks": snap, "ppe": ppe,
            "assessed": bool(snap) and all(r["approved"] for r in snap),
            "workers": _names(s, db.Worker, cid, t.get("worker_ids")),
            "plant": _names(s, db.Plant, cid, t.get("plant_ids")),
        })
    if not tasks:
        raise HTTPException(400, "Add at least one task.")
    unmatched = [{"description": _text(u.get("description"), 500), "reason": _text(u.get("reason"), 300)}
                 for u in (p.get("unmatched") or [])[:20] if isinstance(u, dict)]
    return {"tasks": tasks, "unmatched": unmatched, "notes": _text(p.get("notes"), 2000),
            "transcript_used": bool(p.get("transcript_used"))}


def _toolbox_talk(s, cid, site_id, p: dict) -> dict:
    lang = p.get("language") if p.get("language") in library.LANGUAGES else "en"
    out = {"topic": _text(p.get("topic"), 200), "title": _text(p.get("title"), 200),
           "language": lang, "text": _text(p.get("text"), 8000), "text_en": _text(p.get("text_en"), 8000),
           "key_points": [_text(x, 300) for x in (p.get("key_points") or [])[:10]],
           "questions": [_text(x, 300) for x in (p.get("questions") or [])[:10]],
           "ai_translated": bool(p.get("ai_translated")), "environmental": bool(p.get("environmental")),
           "task_sheet_id": _text(p.get("task_sheet_id"), 16)}
    if not (out["text"] or out["topic"]):
        raise HTTPException(400, "Add the talk text or at least the topic.")
    if p.get("group_photo"):
        out["group_photo"] = p["group_photo"]
    return out


def _check(s, cid, site_id, p: dict) -> dict:
    tpl = library.CHECKLISTS.get(p.get("template"))
    if not tpl:
        raise HTTPException(400, "Unknown checklist.")
    plant = None
    if p.get("plant_id"):
        plant = s.get(db.Plant, p["plant_id"])
        if not plant or plant.company_id != cid:
            raise HTTPException(400, "Unknown plant item.")
    answers = p.get("answers") or []
    if len(answers) != len(tpl["items"]):
        raise HTTPException(400, "Answer every item on the checklist.")
    items, result = [], "pass"
    for q, a in zip(tpl["items"], answers):
        ans = a.get("answer") if isinstance(a, dict) else None
        if ans not in ("ok", "defect", "na"):
            raise HTTPException(400, "Answer every item on the checklist.")
        if ans == "defect":
            result = "fail" if q.get("critical") or result == "fail" else "defects"
        item = {"q": q["q"], "critical": bool(q.get("critical")), "answer": ans,
                "note": _text(a.get("note"), 500)}
        if a.get("photo"):
            item["photo"] = a["photo"]
        items.append(item)
    return {"template": p["template"], "title": tpl["title"], "type": tpl["kind"],
            "plant_id": plant.id if plant else "", "plant_name": plant.name if plant else "",
            "plant_ident": plant.ident if plant else "", "location": _text(p.get("location"), 200),
            "items": items, "result": result, "notes": _text(p.get("notes"), 1000)}


def _pick(values, allowed) -> list:
    return [v for v in (values or []) if v in allowed]


def _opt_bool(v):
    return None if v in (None, "", "unknown") else bool(v) and v not in ("no", "false")


def _incident(s, cid, site_id, p: dict) -> dict:
    kind = p.get("type") if p.get("type") in library.INCIDENT_TYPES else "other"
    people = []
    for x in (p.get("people") or [])[:20]:
        if not isinstance(x, dict):
            continue
        w = s.get(db.Worker, x.get("worker_id") or "")
        w = w if w and w.company_id == cid else None
        m = x.get("medical") if isinstance(x.get("medical"), dict) else {}
        people.append({
            "name": w.name if w else _text(x.get("name"), 200), "worker_id": w.id if w else "",
            "id_number": (w.id_number if w else "") or _text(x.get("id_number"), 40),
            "occupation": (w.trade if w else "") or _text(x.get("occupation"), 100),
            "injury": _text(x.get("injury"), 500), "treatment": _text(x.get("treatment"), 500),
            "body_parts": _pick(x.get("body_parts"), library.BODY_PARTS),
            "effects": _pick(x.get("effects"), library.EFFECTS), "effect_other": _text(x.get("effect_other"), 200),
            "disablement": x.get("disablement") if x.get("disablement") in library.DISABLEMENT else "",
            "medical": {"clinic": _text(m.get("clinic"), 1000), "pre_existing": _text(m.get("pre_existing"), 300),
                        "physio": _opt_bool(m.get("physio")), "unfit": _opt_bool(m.get("unfit")),
                        "light_duty_date": _text(m.get("light_duty_date"), 20),
                        "resumption_date": _text(m.get("resumption_date"), 20)}})
    photos = [ph for ph in (p.get("photos") or [])[:12]]
    captions = [_text(c, 200) for c in (p.get("photo_captions") or [])[:12]]
    out = {"type": kind, "title": _text(p.get("title"), 200),
           "occurred_at": _text(p.get("occurred_at"), 60), "location": _text(p.get("location"), 200),
           "reported_by": _text(p.get("reported_by"), 200), "reporter_contact": _text(p.get("reporter_contact"), 60),
           "work_type": _text(p.get("work_type"), 300),
           "description": _text(p.get("description"), 6000), "people": people,
           "damage": _pick(p.get("damage"), library.DAMAGE), "damage_note": _text(p.get("damage_note"), 300),
           "witnesses": [_text(w, 200) for w in (p.get("witnesses") or [])[:20] if _text(w)],
           "immediate_actions": _text(p.get("immediate_actions"), 4000),
           "possible_causes": [_text(c, 300) for c in (p.get("possible_causes") or [])[:10]],
           "possibly_reportable": bool(p.get("possibly_reportable")),
           "reportable_reason": _text(p.get("reportable_reason"), 500),
           "photos": photos, "photo_captions": captions + [""] * (len(photos) - len(captions))}
    if not out["description"]:
        raise HTTPException(400, "Describe what happened.")
    return out


def _induction(s, cid, site_id, p: dict, company: db.Company) -> dict:
    w = s.get(db.Worker, p.get("worker_id") or "")
    if not w or w.company_id != cid:
        raise HTTPException(400, "Unknown worker.")
    if not s.get(db.SiteWorker, (site_id, w.id)):
        s.add(db.SiteWorker(site_id=site_id, worker_id=w.id))
    text = company.induction_text or library.DEFAULT_INDUCTION
    site = s.get(db.Site, site_id)
    rules = (((site.settings or {}).get("spec") or {}).get("key_rules") or []) if site else []
    if rules:
        text += "\n\nClient's site rules\n" + "\n".join(f"- {r['rule']} ({r['clause']})" for r in rules[:25])
    if not p.get("consent"):
        raise HTTPException(400, "The worker must agree to e-signatures and the privacy notice.")
    return {"worker_id": w.id, "worker_name": w.name, "induction_text": text,
            "consent": True, "consent_text": library.WORKER_CONSENT,
            "language": p.get("language") if p.get("language") in library.LANGUAGES else "en"}


def _visitor(s, cid, site_id, p: dict) -> dict:
    out = {"name": _text(p.get("name"), 200), "company": _text(p.get("company"), 200),
           "phone": _text(p.get("phone"), 40), "id_number": _text(p.get("id_number"), 40),
           "purpose": _text(p.get("purpose"), 300), "host": _text(p.get("host"), 200),
           "ppe": [x for x in (p.get("ppe") or []) if x in library.VISITOR_PPE],
           "rules_text": library.VISITOR_RULES, "time_in": _text(p.get("time_in"), 40)}
    if not out["name"]:
        raise HTTPException(400, "Give the visitor's name.")
    if not out["ppe"]:
        raise HTTPException(400, "Tick the PPE the visitor received (reg 7(6)).")
    return out


def _appointment(s, cid, site_id, p: dict) -> dict:
    t = library.APPOINTMENTS.get(p.get("type"))
    if not t:
        raise HTTPException(400, "Pick the appointment type.")
    who = p.get("appointee") or {}
    name, wid, uid = _text(who.get("name"), 200), None, None
    if who.get("worker_id"):
        w = s.get(db.Worker, who["worker_id"])
        if not w or w.company_id != cid:
            raise HTTPException(400, "Unknown worker.")
        wid, name = w.id, w.name
    elif who.get("user_id"):
        u = s.get(db.User, who["user_id"])
        if not u or u.company_id != cid:
            raise HTTPException(400, "Unknown user.")
        uid, name = u.id, u.name
    if not name:
        raise HTTPException(400, "Choose the person to appoint.")
    return {"type": p["type"], "title": t["title"], "reg": t["reg"], "duties": t["duties"],
            "aes_required": t["aes"], "appointee": {"name": name, "worker_id": wid, "user_id": uid},
            "scope": _text(p.get("scope"), 1000), "start_date": _text(p.get("start_date"), 10),
            "end_date": _text(p.get("end_date"), 10)}


def _audit(s, cid, site_id, p: dict) -> dict:
    answers = {a.get("key"): a for a in (p.get("items") or []) if isinstance(a, dict)}
    items, ok, gap = [], 0, 0
    for key, title, reg in library.AUDIT_ITEMS:
        a = answers.get(key) or {}
        res = a.get("result") if a.get("result") in ("ok", "gap", "na") else None
        if res is None:
            raise HTTPException(400, f"Answer every audit item ({title}).")
        ok += res == "ok"
        gap += res == "gap"
        items.append({"key": key, "title": title, "reg": reg, "result": res, "note": _text(a.get("note"), 500)})
    findings = [{"finding": _text(f.get("finding"), 500), "action": _text(f.get("action"), 500),
                 "owner": _text(f.get("owner"), 200), "due": _text(f.get("due"), 10)}
                for f in (p.get("findings") or [])[:50] if isinstance(f, dict) and _text(f.get("finding"))]
    score = round(100 * ok / (ok + gap)) if ok + gap else 100
    return {"period": _text(p.get("period"), 60), "items": items, "findings": findings, "score": score,
            "board": p.get("board") if isinstance(p.get("board"), dict) else {},
            "report_due": _text(p.get("report_due"), 10), "notes": _text(p.get("notes"), 2000)}


def _audit_ack(s, cid, site_id, p: dict) -> dict:
    a = s.get(db.Record, p.get("audit_id") or "")
    if not a or a.company_id != cid or a.kind != "audit":
        raise HTTPException(400, "Unknown audit.")
    return {"audit_id": a.id, "audit_date": a.record_date.isoformat(), "score": a.payload.get("score")}


def _investigation(s, cid, site_id, p: dict) -> dict:
    inc = s.get(db.Record, p.get("incident_id") or "")
    if not inc or inc.company_id != cid or inc.kind != "incident":
        raise HTTPException(400, "Unknown incident.")
    def _rep(x):
        x = x if isinstance(x, dict) else {}
        return {"date": _text(x.get("date"), 10), "ref": _text(x.get("ref"), 100)}
    lines = lambda v, n=10: [_text(x, 400) for x in (v or [])[:n] if _text(x)]
    out = {"incident_id": inc.id, "incident_date": inc.record_date.isoformat(),
           "incident_summary": _text(inc.payload.get("description"), 300),
           "investigator": _text(p.get("investigator"), 200), "designation": _text(p.get("designation"), 200),
           "short_description": _text(p.get("short_description"), 1000),
           "suspected_cause": _text(p.get("suspected_cause"), 1000),
           "findings": _text(p.get("findings"), 6000),
           "root_causes": lines(p.get("root_causes")),
           "agencies_general": _pick(p.get("agencies_general"), library.AGENCIES_GENERAL),
           "agencies_hygiene": _pick(p.get("agencies_hygiene"), library.AGENCIES_HYGIENE),
           "normal_work": _opt_bool(p.get("normal_work")),
           "unsafe_acts": _pick(p.get("unsafe_acts"), library.UNSAFE_ACTS),
           "unsafe_conditions": _pick(p.get("unsafe_conditions"), library.UNSAFE_CONDITIONS),
           "personal_factors": _pick(p.get("personal_factors"), library.PERSONAL_FACTORS),
           "job_factors": _pick(p.get("job_factors"), library.JOB_FACTORS),
           "control_personal": _pick(p.get("control_personal"), library.CONTROL_PERSONAL),
           "control_job": _pick(p.get("control_job"), library.CONTROL_JOB),
           "actions": [{"action": _text(a.get("action"), 500), "owner": _text(a.get("owner"), 200),
                        "due": _text(a.get("due"), 10)} for a in (p.get("actions") or [])[:20]
                       if isinstance(a, dict) and _text(a.get("action"))],
           "employer_action": _text(p.get("employer_action"), 2000),
           "close_out": _text(p.get("close_out"), 2000),
           "committee_remarks": _text(p.get("committee_remarks"), 2000),
           "reportable": bool(p.get("reportable")), "not_reportable_reason": _text(p.get("not_reportable_reason"), 500),
           "reported_dol": _rep(p.get("reported_dol")), "reported_cf": _rep(p.get("reported_cf"))}
    if not out["findings"]:
        raise HTTPException(400, "Write the investigation findings.")
    if out["reportable"] and not out["reported_dol"]["date"]:
        raise HTTPException(400, "Give the date it was reported to the Department of Employment and Labour.")
    return out


def _form(s, cid, site_id, kind: str, p: dict) -> dict:
    """Generic form: validate each field against library.FORMS[kind]."""
    spec = library.FORMS[kind]
    out = {"form": kind, "title": spec["title"], "reg": spec["reg"], "fields": []}
    for f in spec["fields"]:
        v, t = p.get(f["k"]), f["type"]
        if t == "fixed":
            val = f["value"]
        elif t == "number":
            try:
                val = float(v) if v not in (None, "") else None
            except (TypeError, ValueError):
                raise HTTPException(400, f"{f['label']}: give a number.")
        elif t == "yesno":
            val = None if v in (None, "") else bool(v) and v not in ("no", "false", False)
        elif t == "multi":
            val = [x for x in (v or []) if x in f["options"]]
        elif t == "select":
            val = v if v in f["options"] else ""
        elif t == "worker":
            w = s.get(db.Worker, v or "")
            if v and (not w or w.company_id != cid):
                raise HTTPException(400, "Unknown worker.")
            val = {"id": w.id, "name": w.name} if w else None
        elif t == "open_incident":
            r = s.get(db.Record, v or "")
            if v and (not r or r.company_id != cid or r.kind != "incident"):
                raise HTTPException(400, "Unknown incident.")
            val = {"id": r.id, "date": r.record_date.isoformat(), "summary": summary(r)} if r else None
        elif t == "open_permit":
            r = s.get(db.Record, v or "")
            if v and (not r or r.company_id != cid or r.kind != "permit"):
                raise HTTPException(400, "Unknown permit.")
            val = {"id": r.id, "date": r.record_date.isoformat(), "summary": summary(r)} if r else None
        else:
            val = _text(v, 6000 if t == "textarea" else 300)
        empty = val in (None, "", [])
        if f.get("req") and empty:
            raise HTTPException(400, f"Fill in: {f['label']}.")
        if f["type"] == "yesno" and f.get("req") and f["k"] in ("understood", "complete", "actions_done", "safe") \
                and val is not True:
            raise HTTPException(400, f"{f['label']}: this must be yes before signing.")
        out["fields"].append({"k": f["k"], "label": f["label"], "type": t, "value": val})
    return out


def form_value(rec, key):
    for f in (rec.payload or {}).get("fields", []):
        if f["k"] == key:
            return f["value"]
    return None


# ---------------------------------------------------------------- hashing

def canonical(rec: db.Record) -> str:
    sigs = [{"order": g.order, "worker_id": g.worker_id, "user_id": g.user_id, "name": g.name,
             "role": g.role, "image": g.image_file, "photo": g.photo_file, "signed_at": g.signed_at,
             "lat": g.lat, "lng": g.lng} for g in sorted(rec.signatures, key=lambda g: g.order)]
    body = {"id": rec.id, "company_id": rec.company_id, "site_id": rec.site_id, "kind": rec.kind,
            "client_id": rec.client_id, "record_date": rec.record_date.isoformat(),
            "payload": rec.payload, "audio": rec.audio_file, "created_by": rec.created_by,
            "created_name": rec.created_name, "device_time": rec.device_time,
            "received_at": rec.received_at.isoformat(), "lat": rec.lat, "lng": rec.lng,
            "seq": rec.seq, "signatures": sigs}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(prev: str, rec: db.Record) -> str:
    return hashlib.sha256((prev + canonical(rec)).encode()).hexdigest()


# ---------------------------------------------------------------- create

def _coord(v):
    try:
        f = float(v)
        return f if -180 <= f <= 180 else None
    except (TypeError, ValueError):
        return None


def create(ctx, body: dict) -> str:
    """Store one finished record. Return its id (the existing id on a retry)."""
    cid = ctx.cid
    client_id = _text(body.get("client_id"), 64)
    kind = body.get("kind")
    if not client_id or kind not in KINDS:
        raise HTTPException(400, "Bad record.")
    with db.session() as s:
        hit = s.scalar(select(db.Record.id).where(db.Record.company_id == cid,
                                                  db.Record.client_id == client_id))
        if hit:
            return hit
    try:
        rdate = date.fromisoformat(body.get("record_date") or "")
    except ValueError:
        raise HTTPException(400, "Bad record date.")

    with _chain_lock, db.session() as s:
        site = s.get(db.Site, body.get("site_id") or "")
        if not site or site.company_id != cid:
            raise HTTPException(404, "Site not found.")
        p = body.get("payload") or {}
        company = s.get(db.Company, cid)
        payload = {"task_sheet": lambda: _task_sheet(s, cid, site.id, p),
                   "toolbox_talk": lambda: _toolbox_talk(s, cid, site.id, p),
                   "check": lambda: _check(s, cid, site.id, p),
                   "incident": lambda: _incident(s, cid, site.id, p),
                   "induction": lambda: _induction(s, cid, site.id, p, company),
                   "visitor": lambda: _visitor(s, cid, site.id, p),
                   "appointment": lambda: _appointment(s, cid, site.id, p),
                   "audit": lambda: _audit(s, cid, site.id, p),
                   "audit_ack": lambda: _audit_ack(s, cid, site.id, p),
                   "investigation": lambda: _investigation(s, cid, site.id, p),
                   **{k: (lambda k=k: _form(s, cid, site.id, k, p)) for k in library.FORMS}}[kind]()
        payload = _store_files(cid, payload)
        audio = ""
        if body.get("audio"):
            audio = _store_files(cid, body["audio"])["file"]
        seq = (s.scalar(select(func.max(db.Record.seq)).where(db.Record.company_id == cid)) or 0) + 1
        prev = s.scalar(select(db.Record.hash).where(db.Record.company_id == cid,
                                                     db.Record.seq == seq - 1)) or GENESIS
        rec = db.Record(id=db.new_id(), company_id=cid, site_id=site.id, kind=kind, client_id=client_id,
                        record_date=rdate, payload=payload, audio_file=audio,
                        transcript=_text(body.get("transcript"), 8000),
                        created_by=ctx.uid, created_name=ctx.user.name,
                        device_time=_text(body.get("device_time"), 40),
                        received_at=db.utcnow().replace(microsecond=0),
                        lat=_coord(body.get("lat")), lng=_coord(body.get("lng")),
                        seq=seq, prev_hash=prev, hash="")
        sigs = body.get("signatures") or []
        if not sigs:
            raise HTTPException(400, "The record needs at least one signature.")
        for i, g in enumerate(sigs[:200]):
            sig = _signature(s, ctx, g, i)
            sig.record_id = rec.id
            rec.signatures.append(sig)
        s.add(rec)
        rec.hash = compute_hash(prev, rec)
        try:
            s.flush()
        except IntegrityError:
            raise HTTPException(409, "Two records arrived at once. The app will try again.")
        return rec.id


def _signature(s, ctx, g: dict, order: int) -> db.Signature:
    cid = ctx.cid
    worker_id = g.get("worker_id") or None
    user_id = None
    name = _text(g.get("name"), 200)
    if worker_id:
        w = s.get(db.Worker, worker_id)
        if not w or w.company_id != cid:
            raise HTTPException(400, "A signature is from an unknown worker.")
        name = w.name
    elif g.get("user_id"):
        u = s.get(db.User, g["user_id"])
        if not u or u.company_id != cid:
            raise HTTPException(400, "A signature is from an unknown user.")
        user_id, name = u.id, u.name
    if not name:
        raise HTTPException(400, "Each signature needs a name.")
    if not g.get("image"):
        raise HTTPException(400, f"{name} has not signed.")
    image = _store_files(cid, g["image"])["file"]
    photo = _store_files(cid, g["photo"])["file"] if g.get("photo") else ""
    return db.Signature(id=db.new_id(), company_id=cid, order=order, worker_id=worker_id, user_id=user_id,
                        name=name, role=_text(g.get("role"), 60) or "worker", image_file=image,
                        photo_file=photo, signed_at=_text(g.get("signed_at"), 40),
                        lat=_coord(g.get("lat")), lng=_coord(g.get("lng")))


# ---------------------------------------------------------------- read

def to_dict(rec: db.Record, full: bool = True) -> dict:
    d = {"id": rec.id, "kind": rec.kind, "kind_label": KINDS[rec.kind], "site_id": rec.site_id,
         "record_date": rec.record_date.isoformat(), "created_name": rec.created_name,
         "received_at": rec.received_at.isoformat() + "Z", "device_time": rec.device_time,
         "summary": summary(rec), "hash": rec.hash, "seq": rec.seq,
         "signature_count": len(rec.signatures)}
    if full:
        d |= {"payload": with_urls(rec.payload), "transcript": rec.transcript,
              "audio_url": files.sign(rec.audio_file), "lat": rec.lat, "lng": rec.lng,
              "prev_hash": rec.prev_hash,
              "signatures": [{"name": g.name, "role": g.role, "signed_at": g.signed_at,
                              "image_url": files.sign(g.image_file), "photo_url": files.sign(g.photo_file),
                              "worker_id": g.worker_id, "lat": g.lat, "lng": g.lng}
                             for g in rec.signatures]}
    return d


def summary(rec: db.Record) -> str:
    p = rec.payload or {}
    if rec.kind == "task_sheet":
        n = len(p.get("tasks", []))
        flag = " · needs review" if p.get("unmatched") or not all(t.get("assessed") for t in p.get("tasks", [])) else ""
        return f"{n} task{'s' * (n != 1)}, {len(rec.signatures)} signed{flag}"
    if rec.kind == "toolbox_talk":
        return f"{p.get('title') or p.get('topic')} · {len(rec.signatures)} signed"
    if rec.kind == "check":
        res = {"pass": "Pass", "defects": "Defects noted", "fail": "FAIL: do not use"}[p.get("result", "pass")]
        return f"{p.get('plant_name') or p.get('title')} · {res}"
    if rec.kind == "incident":
        return f"{library.INCIDENT_TYPES.get(p.get('type'), 'Incident')}: {(p.get('title') or p.get('description', ''))[:80]}"
    if rec.kind == "induction":
        return p.get("worker_name", "")
    if rec.kind == "visitor":
        return f"{p.get('name')} ({p.get('company') or 'visitor'}) · host {p.get('host') or '-'}"
    if rec.kind == "appointment":
        return f"{p.get('title')}: {p.get('appointee', {}).get('name', '')}"
    if rec.kind == "audit":
        return f"Score {p.get('score')}% · {len(p.get('findings', []))} finding(s)"
    if rec.kind == "audit_ack":
        return f"Report of audit {p.get('audit_date')} received"
    if rec.kind == "investigation":
        return f"Incident {p.get('incident_date')}: " + ("reported" if p.get("reportable") else "not reportable")
    if rec.kind in library.FORMS:
        def v(k):
            x = form_value(rec, k)
            return x.get("name") if isinstance(x, dict) else (", ".join(x) if isinstance(x, list) else x)
        return {"drill": lambda: f"{v('scenario') or 'Drill'} · {v('minutes') or '?'} min",
                "meeting": lambda: (v("minutes") or "")[:80],
                "observation": lambda: f"{v('worker')}: {v('task')} · procedure {v('procedure')}",
                "ppe_issue": lambda: f"{v('worker')}: {v('items')}",
                "permit": lambda: f"{v('type')} · {v('location')} · until {v('valid_until')}",
                "permit_close": lambda: f"Closed: {(form_value(rec, 'permit') or {}).get('summary', '')}",
                "ra_acceptance": lambda: f"{v('role')}",
                "incident_close": lambda: f"Closed: {(form_value(rec, 'incident') or {}).get('summary', '')}"}.get(rec.kind, lambda: "")()
    return ""


# ---------------------------------------------------------------- verify

def verify(cid: str) -> dict:
    """Recompute the whole chain. Any edit to a stored record breaks it."""
    broken, prev, n = [], GENESIS, 0
    with db.session() as s:
        for rec in s.scalars(select(db.Record).where(db.Record.company_id == cid).order_by(db.Record.seq)):
            n += 1
            if rec.prev_hash != prev or compute_hash(prev, rec) != rec.hash:
                broken.append({"seq": rec.seq, "id": rec.id})
            for g in rec.signatures:
                for f in (g.image_file, g.photo_file):
                    if f and not (files.path(f)).exists():
                        broken.append({"seq": rec.seq, "id": rec.id, "missing_file": f})
            prev = rec.hash
    return {"records": n, "ok": not broken, "broken": broken, "head": prev,
            "checked_at": db.utcnow().isoformat(timespec="seconds") + "Z"}
