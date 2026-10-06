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
         "induction": "Site induction"}
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
           "ai_translated": bool(p.get("ai_translated")),
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
            result = "fail" if q["critical"] or result == "fail" else "defects"
        item = {"q": q["q"], "critical": q["critical"], "answer": ans,
                "note": _text(a.get("note"), 500)}
        if a.get("photo"):
            item["photo"] = a["photo"]
        items.append(item)
    return {"template": p["template"], "title": tpl["title"], "type": tpl["kind"],
            "plant_id": plant.id if plant else "", "plant_name": plant.name if plant else "",
            "plant_ident": plant.ident if plant else "", "location": _text(p.get("location"), 200),
            "items": items, "result": result, "notes": _text(p.get("notes"), 1000)}


def _incident(s, cid, site_id, p: dict) -> dict:
    kind = p.get("type") if p.get("type") in library.INCIDENT_TYPES else "other"
    people = []
    for x in (p.get("people") or [])[:20]:
        if isinstance(x, dict):
            people.append({"name": _text(x.get("name"), 200), "worker_id": _text(x.get("worker_id"), 16),
                           "injury": _text(x.get("injury"), 500), "treatment": _text(x.get("treatment"), 500)})
    out = {"type": kind, "occurred_at": _text(p.get("occurred_at"), 60), "location": _text(p.get("location"), 200),
           "description": _text(p.get("description"), 4000), "people": people,
           "witnesses": [_text(w, 200) for w in (p.get("witnesses") or [])[:20]],
           "immediate_actions": _text(p.get("immediate_actions"), 2000),
           "possible_causes": [_text(c, 300) for c in (p.get("possible_causes") or [])[:10]],
           "possibly_reportable": bool(p.get("possibly_reportable")),
           "reportable_reason": _text(p.get("reportable_reason"), 500),
           "photos": (p.get("photos") or [])[:10]}
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
    return {"worker_id": w.id, "worker_name": w.name, "induction_text": text,
            "language": p.get("language") if p.get("language") in library.LANGUAGES else "en"}


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
                   "induction": lambda: _induction(s, cid, site.id, p, company)}[kind]()
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
        return f"{library.INCIDENT_TYPES.get(p.get('type'), 'Incident')}: {p.get('description', '')[:80]}"
    if rec.kind == "induction":
        return p.get("worker_name", "")
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
