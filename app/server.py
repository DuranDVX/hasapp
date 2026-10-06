"""HTTP API + static PWA. Run: .venv/bin/uvicorn app.server:app --port 8500"""
import io
import logging
import os
import re
import secrets
import tempfile
import time
from contextlib import asynccontextmanager
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import ai, auth, config, db, files, library, mailer, pdf, records, stt, tts
from .auth import Ctx, current

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hasapp")


class _Redact(logging.Filter):
    RX = re.compile(r"([?&](?:sig|token)=)[^&\s\"]+")

    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(self.RX.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args)
        return True


logging.getLogger("uvicorn.access").addFilter(_Redact())

@asynccontextmanager
async def _lifespan(_app):
    db.init()
    if os.getenv("HAS_WARM_STT", "1") == "1":
        stt.warm_up()
    yield


app = FastAPI(title=config.APP_NAME, docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan)
SA = ZoneInfo("Africa/Johannesburg")
SIGNUP_CODE = os.getenv("HAS_SIGNUP_CODE", "")   # set during the pilot: sign-up by invite only


def today() -> date:
    return datetime.now(SA).date()


SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "microphone=(self), camera=(self), geolocation=(self)",
}


@app.middleware("http")
async def _headers(request: Request, call_next):
    resp = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    path = request.url.path
    if not path.startswith("/api/"):
        if path.endswith((".png", ".jpg", ".webp", ".ico", ".svg")):
            resp.headers.setdefault("Cache-Control", "public, max-age=86400")
        else:
            resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


# ---------------------------------------------------------------- helpers

_calls: dict[str, deque] = defaultdict(deque)


def _limit(ctx: Ctx) -> None:
    q, now = _calls[ctx.cid], time.monotonic()
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= config.AI_PER_HOUR:
        raise HTTPException(429, "Too many AI requests this hour. Try again later.")
    q.append(now)


def _ai(fn, *args):
    try:
        return fn(*args)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        log.exception("AI step failed")
        raise HTTPException(502, "The AI had a problem. Try again in a minute, or fill the form by hand.")


def _date(v, field="date") -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise HTTPException(400, f"Bad {field}.")


def _s(v, n=200) -> str:
    return str(v or "").strip()[:n]


def _get(s, model, id_: str, ctx: Ctx, what="Item"):
    row = s.get(model, id_ or "")
    if not row or row.company_id != ctx.cid:
        raise HTTPException(404, f"{what} not found.")
    return row


def _expiry(d: date | None) -> str:
    if not d:
        return "none"
    if d < today():
        return "expired"
    if d <= today() + timedelta(days=config.EXPIRY_WARN_DAYS):
        return "expiring"
    return "valid"


def _audio_text(ctx: Ctx, audio: UploadFile | None, text: str) -> tuple[str, dict | None]:
    """Return (text, stored audio ref). Audio is kept so the record can carry it."""
    if audio is None or not audio.filename:
        if not text.strip():
            raise HTTPException(400, "Record a voice note or type the details.")
        return text.strip()[:6000], None
    data = audio.file.read(files.MAX_BYTES + 1)
    if len(data) > files.MAX_BYTES:
        raise HTTPException(413, "The recording is too long.")
    if len(data) < 1000:
        raise HTTPException(400, "The recording is empty. Hold the phone closer and try again.")
    mime = (audio.content_type or "audio/webm").split(";")[0]
    if mime not in files.TYPES or not mime.startswith("audio/"):
        mime = "audio/webm"
    ref = {"file": files.put(ctx.cid, data, mime)}
    suffix = files.TYPES[mime]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
    try:
        spoken, _ = stt.transcribe(f.name)
    except Exception:
        log.exception("speech recognition failed")
        raise HTTPException(422, "We could not read that recording. Try again, or type it.")
    finally:
        Path(f.name).unlink(missing_ok=True)
    if not spoken:
        raise HTTPException(422, "No speech found in the recording.")
    return (spoken + ("\n" + text.strip() if text.strip() else ""))[:6000], ref


# ---------------------------------------------------------------- serialisers

def user_d(u: db.User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "role": u.role,
            "role_label": auth.ROLES.get(u.role, u.role), "sacpcmp_no": u.sacpcmp_no, "active": u.active}


def company_d(c: db.Company) -> dict:
    return {"id": c.id, "name": c.name, "reg_no": c.reg_no, "address": c.address, "phone": c.phone,
            "email": c.email, "coid_no": c.coid_no, "logo_url": files.sign(c.logo_file),
            "induction_text": c.induction_text or library.DEFAULT_INDUCTION}


def site_d(x: db.Site) -> dict:
    return {"id": x.id, "name": x.name, "address": x.address, "client": x.client,
            "client_agent": x.client_agent, "emergency": x.emergency,
            "start_date": x.start_date.isoformat() if x.start_date else "",
            "end_date": x.end_date.isoformat() if x.end_date else "", "status": x.status}


def cred_d(c: db.Credential) -> dict:
    return {"id": c.id, "kind": c.kind, "kind_label": library.CREDENTIAL_KINDS.get(c.kind, c.kind),
            "title": c.title, "issued": c.issued.isoformat() if c.issued else "",
            "expires": c.expires.isoformat() if c.expires else "", "status": _expiry(c.expires),
            "file_url": files.sign(c.file)}


def worker_d(w: db.Worker, ctx: Ctx, inducted: bool | None = None) -> dict:
    idn = w.id_number if ctx.role != "auditor" else (("•" * max(0, len(w.id_number) - 4)) + w.id_number[-4:])
    medical = [c for c in w.credentials if c.kind == "medical"]
    med_status = max((_expiry(c.expires) for c in medical),
                     key=["none", "expired", "expiring", "valid"].index, default="missing") if medical else "missing"
    d = {"id": w.id, "name": w.name, "id_number": idn, "trade": w.trade, "employer": w.employer,
         "phone": w.phone, "emergency_contact": w.emergency_contact, "language": w.language,
         "photo_url": files.sign(w.photo_file), "active": w.active, "medical": med_status,
         "credentials": [cred_d(c) for c in w.credentials]}
    if inducted is not None:
        d["inducted"] = inducted
    return d


def risk_d(r: db.RiskItem) -> dict:
    return {"id": r.id, "site_id": r.site_id, "activity": r.activity, "hazards": r.hazards, "ppe": r.ppe,
            "source": r.source, "approved": r.approved_at is not None, "approved_by": r.approved_by,
            "approved_at": r.approved_at.date().isoformat() if r.approved_at else "", "active": r.active}


def plant_d(p: db.Plant) -> dict:
    tpl = library.CHECKLISTS.get(p.template, {})
    return {"id": p.id, "site_id": p.site_id, "name": p.name, "template": p.template,
            "template_title": tpl.get("title", ""), "ident": p.ident, "qr_token": p.qr_token,
            "qr_url": f"{config.PUBLIC_URL}/p/{p.qr_token}", "active": p.active}


def doc_d(d: db.Doc) -> dict:
    return {"id": d.id, "site_id": d.site_id, "section": d.section, "title": d.title,
            "expires": d.expires.isoformat() if d.expires else "", "status": _expiry(d.expires),
            "file_url": files.sign(d.file), "uploaded_by": d.uploaded_by,
            "created_at": d.created_at.date().isoformat()}


# ---------------------------------------------------------------- health, auth

@app.get("/api/health")
def health():
    return {"ok": True, "app": config.APP_NAME}


@app.post("/api/signup")
def signup(body: dict = Body(...)):
    if SIGNUP_CODE and _s(body.get("invite")) != SIGNUP_CODE:
        raise HTTPException(403, "Sign-up needs an invite code during the pilot.")
    email = _s(body.get("email")).lower()
    if "@" not in email or not _s(body.get("company")) or not _s(body.get("name")):
        raise HTTPException(400, "Fill in the company name, your name and your email.")
    auth.valid_pw(body.get("password", ""))
    with db.session() as s:
        if s.scalar(select(db.User).where(db.User.email == email)):
            raise HTTPException(409, "That email already has an account. Log in instead.")
        c = db.Company(name=_s(body["company"]), email=email)
        s.add(c)
        s.flush()
        u = db.User(company_id=c.id, email=email, name=_s(body["name"]), role="owner",
                    pw_hash=auth.hash_pw(body["password"]))
        s.add(u)
        for r in library.STARTER_RISKS:
            s.add(db.RiskItem(company_id=c.id, activity=r["activity"], hazards=r["hazards"],
                              ppe=r["ppe"], source="starter"))
        s.flush()
        return {"token": auth.new_session(s, u)}


@app.post("/api/login")
def login(body: dict = Body(...)):
    email = _s(body.get("email")).lower()
    with db.session() as s:
        u = s.scalar(select(db.User).where(db.User.email == email))
        if not u or not u.active or not auth.check_pw(body.get("password", ""), u.pw_hash):
            time.sleep(0.5)
            raise HTTPException(401, "Wrong email or password.")
        return {"token": auth.new_session(s, u)}


@app.post("/api/logout")
def logout(x_token: str = Header(None)):
    if x_token:
        with db.session() as s:
            auth.end_session(s, x_token)
    return {"ok": True}


@app.put("/api/account/password")
def change_password(body: dict = Body(...), ctx: Ctx = Depends(current), x_token: str = Header(None)):
    auth.valid_pw(body.get("password", ""))
    with db.session() as s:
        u = s.get(db.User, ctx.uid)
        if not auth.check_pw(body.get("old_password", ""), u.pw_hash):
            raise HTTPException(400, "The old password is wrong.")
        u.pw_hash = auth.hash_pw(body["password"])
        auth.end_all(s, u.id)
        return {"token": auth.new_session(s, u)}


@app.get("/api/me")
def me(ctx: Ctx = Depends(current)):
    with db.session() as s:
        sites = s.scalars(select(db.Site).where(db.Site.company_id == ctx.cid)
                          .order_by(db.Site.status, db.Site.name)).all()
        return {"user": user_d(ctx.user), "company": company_d(ctx.company),
                "sites": [site_d(x) for x in sites], "roles": auth.ROLES,
                "can_manage": ctx.role in auth.MANAGE, "can_write": ctx.role in auth.WRITE,
                "app_name": config.APP_NAME}


# ---------------------------------------------------------------- company and users

@app.put("/api/company")
def update_company(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need("owner", "safety")
    with db.session() as s:
        c = s.get(db.Company, ctx.cid)
        for k in ("name", "reg_no", "phone", "email", "coid_no"):
            if k in body:
                setattr(c, k, _s(body[k]))
        if "address" in body:
            c.address = _s(body["address"], 500)
        if "induction_text" in body:
            c.induction_text = _s(body["induction_text"], 8000)
        if body.get("logo"):
            try:
                c.logo_file = files.put_data_url(c.id, body["logo"])
            except ValueError as e:
                raise HTTPException(400, str(e))
        if not c.name:
            raise HTTPException(400, "The company needs a name.")
        return company_d(c)


@app.get("/api/users")
def list_users(ctx: Ctx = Depends(current)):
    ctx.need("owner", "safety")
    with db.session() as s:
        return [user_d(u) for u in s.scalars(select(db.User).where(db.User.company_id == ctx.cid)
                                             .order_by(db.User.name))]


@app.post("/api/users")
def add_user(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need("owner")
    email, role = _s(body.get("email")).lower(), body.get("role")
    if "@" not in email or not _s(body.get("name")) or role not in auth.ROLES:
        raise HTTPException(400, "Fill in the name, email and role.")
    temp = secrets.token_urlsafe(6)
    with db.session() as s:
        if s.scalar(select(db.User).where(db.User.email == email)):
            raise HTTPException(409, "That email already has a login.")
        u = db.User(company_id=ctx.cid, email=email, name=_s(body["name"]), role=role,
                    phone=_s(body.get("phone"), 40), sacpcmp_no=_s(body.get("sacpcmp_no"), 60),
                    pw_hash=auth.hash_pw(temp))
        s.add(u)
        s.flush()
        sent = mailer.send(email, f"Your {config.APP_NAME} login",
                           f"{ctx.user.name} added you to {ctx.company.name} on {config.APP_NAME}.\n\n"
                           f"Open {config.PUBLIC_URL}/app.html\nEmail: {email}\nTemporary password: {temp}\n\n"
                           "Change the password after you log in.")
        return user_d(u) | {"temp_password": temp, "email_status": sent}


@app.put("/api/users/{uid}")
def update_user(uid: str, body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need("owner")
    with db.session() as s:
        u = _get(s, db.User, uid, ctx, "User")
        if "role" in body:
            if body["role"] not in auth.ROLES:
                raise HTTPException(400, "Unknown role.")
            if u.id == ctx.uid and body["role"] != "owner":
                raise HTTPException(400, "You cannot remove your own owner role.")
            u.role = body["role"]
        for k in ("name", "phone", "sacpcmp_no"):
            if k in body:
                setattr(u, k, _s(body[k]))
        out = {}
        if "active" in body:
            if u.id == ctx.uid:
                raise HTTPException(400, "You cannot switch off your own login.")
            u.active = bool(body["active"])
            if not u.active:
                auth.end_all(s, u.id)
        if body.get("reset_password"):
            temp = secrets.token_urlsafe(6)
            u.pw_hash = auth.hash_pw(temp)
            auth.end_all(s, u.id)
            out["temp_password"] = temp
        return user_d(u) | out


# ---------------------------------------------------------------- sites

def _site_fields(x: db.Site, body: dict) -> None:
    for k in ("name", "client", "client_agent"):
        if k in body:
            setattr(x, k, _s(body[k]))
    for k in ("address", "emergency"):
        if k in body:
            setattr(x, k, _s(body[k], 1000))
    for k in ("start_date", "end_date"):
        if k in body:
            setattr(x, k, _date(body[k], k))
    if body.get("status") in ("active", "closed"):
        x.status = body["status"]
    if not x.name:
        raise HTTPException(400, "The site needs a name.")


@app.post("/api/sites")
def add_site(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.MANAGE)
    with db.session() as s:
        x = db.Site(company_id=ctx.cid, name="")
        _site_fields(x, body)
        s.add(x)
        s.flush()
        return site_d(x)


@app.put("/api/sites/{sid}")
def update_site(sid: str, body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.MANAGE)
    with db.session() as s:
        x = _get(s, db.Site, sid, ctx, "Site")
        _site_fields(x, body)
        return site_d(x)


# ---------------------------------------------------------------- workers

def _worker_fields(w: db.Worker, body: dict, cid: str) -> None:
    for k, n in (("name", 200), ("id_number", 40), ("trade", 100), ("employer", 200), ("phone", 40),
                 ("emergency_contact", 200)):
        if k in body:
            setattr(w, k, _s(body[k], n))
    if body.get("language") in library.LANGUAGES:
        w.language = body["language"]
    if body.get("photo"):
        try:
            w.photo_file = files.put_data_url(cid, body["photo"])
        except ValueError as e:
            raise HTTPException(400, str(e))
    if not w.name:
        raise HTTPException(400, "The worker needs a name.")


def _inducted(s, site_id: str) -> set:
    rows = s.scalars(select(db.Record).where(db.Record.site_id == site_id, db.Record.kind == "induction"))
    return {r.payload.get("worker_id") for r in rows}


@app.get("/api/workers")
def list_workers(site_id: str = "", ctx: Ctx = Depends(current)):
    with db.session() as s:
        q = select(db.Worker).where(db.Worker.company_id == ctx.cid).options(selectinload(db.Worker.credentials))
        if site_id:
            _get(s, db.Site, site_id, ctx, "Site")
            q = q.join(db.SiteWorker, db.SiteWorker.worker_id == db.Worker.id).where(db.SiteWorker.site_id == site_id)
            ind = _inducted(s, site_id)
            return [worker_d(w, ctx, w.id in ind) for w in s.scalars(q.order_by(db.Worker.name))]
        return [worker_d(w, ctx) for w in s.scalars(q.order_by(db.Worker.name))]


@app.post("/api/workers")
def add_worker(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    with db.session() as s:
        w = db.Worker(company_id=ctx.cid, name="")
        _worker_fields(w, body, ctx.cid)
        s.add(w)
        s.flush()
        if body.get("site_id"):
            _get(s, db.Site, body["site_id"], ctx, "Site")
            s.add(db.SiteWorker(site_id=body["site_id"], worker_id=w.id))
        s.flush()
        s.refresh(w)
        return worker_d(w, ctx, False if body.get("site_id") else None)


@app.put("/api/workers/{wid}")
def update_worker(wid: str, body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    with db.session() as s:
        w = _get(s, db.Worker, wid, ctx, "Worker")
        _worker_fields(w, body, ctx.cid)
        if "active" in body:
            w.active = bool(body["active"])
        return worker_d(w, ctx)


@app.post("/api/sites/{sid}/workers")
def site_add_workers(sid: str, body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    with db.session() as s:
        _get(s, db.Site, sid, ctx, "Site")
        for wid in (body.get("worker_ids") or [])[:500]:
            _get(s, db.Worker, wid, ctx, "Worker")
            if not s.get(db.SiteWorker, (sid, wid)):
                s.add(db.SiteWorker(site_id=sid, worker_id=wid))
    return {"ok": True}


@app.delete("/api/sites/{sid}/workers/{wid}")
def site_remove_worker(sid: str, wid: str, ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    with db.session() as s:
        _get(s, db.Site, sid, ctx, "Site")
        s.query(db.SiteWorker).filter_by(site_id=sid, worker_id=wid).delete()
    return {"ok": True}


@app.post("/api/workers/{wid}/credentials")
def add_credential(wid: str, body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    if body.get("kind") not in library.CREDENTIAL_KINDS:
        raise HTTPException(400, "Pick the certificate type.")
    with db.session() as s:
        w = _get(s, db.Worker, wid, ctx, "Worker")
        c = db.Credential(company_id=ctx.cid, worker_id=w.id, kind=body["kind"],
                          title=_s(body.get("title")) or library.CREDENTIAL_KINDS[body["kind"]],
                          issued=_date(body.get("issued"), "issue date"),
                          expires=_date(body.get("expires"), "expiry date"))
        if body.get("file"):
            try:
                c.file = files.put_data_url(ctx.cid, body["file"])
            except ValueError as e:
                raise HTTPException(400, str(e))
        s.add(c)
        s.flush()
        return cred_d(c)


@app.delete("/api/credentials/{cid_}")
def delete_credential(cid_: str, ctx: Ctx = Depends(current)):
    ctx.need(*auth.MANAGE)
    with db.session() as s:
        s.delete(_get(s, db.Credential, cid_, ctx, "Certificate"))
    return {"ok": True}


# ---------------------------------------------------------------- risk library

def _risk_fields(r: db.RiskItem, body: dict) -> None:
    if "activity" in body:
        r.activity = _s(body["activity"])
    if "hazards" in body:
        hz = []
        for h in (body["hazards"] or [])[:20]:
            if isinstance(h, dict) and _s(h.get("hazard")):
                hz.append({"hazard": _s(h["hazard"], 300),
                           "risk": h.get("risk") if h.get("risk") in ("L", "M", "H") else "M",
                           "controls": [_s(c, 300) for c in (h.get("controls") or [])[:15] if _s(c)]})
        r.hazards = hz
    if "ppe" in body:
        r.ppe = [_s(x, 100) for x in (body["ppe"] or [])[:20] if _s(x)]
    if not r.activity or not r.hazards:
        raise HTTPException(400, "Give the activity and at least one hazard.")


@app.get("/api/risks")
def list_risks(site_id: str = "", ctx: Ctx = Depends(current)):
    with db.session() as s:
        q = select(db.RiskItem).where(db.RiskItem.company_id == ctx.cid, db.RiskItem.active)
        q = q.where((db.RiskItem.site_id.is_(None)) | (db.RiskItem.site_id == site_id)) if site_id \
            else q
        return [risk_d(r) for r in s.scalars(q.order_by(db.RiskItem.activity))]


@app.post("/api/risks")
def add_risk(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.MANAGE)
    with db.session() as s:
        r = db.RiskItem(company_id=ctx.cid, activity="", source=_s(body.get("source")) if body.get("source") == "ai_draft" else "manual")
        if body.get("site_id"):
            r.site_id = _get(s, db.Site, body["site_id"], ctx, "Site").id
        _risk_fields(r, body)
        s.add(r)
        s.flush()
        return risk_d(r)


@app.put("/api/risks/{rid}")
def update_risk(rid: str, body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.MANAGE)
    with db.session() as s:
        r = _get(s, db.RiskItem, rid, ctx, "Risk item")
        _risk_fields(r, body)
        r.approved_at, r.approved_by = None, ""     # an edit needs a new approval
        if "active" in body:
            r.active = bool(body["active"])
        return risk_d(r)


@app.post("/api/risks/{rid}/approve")
def approve_risk(rid: str, ctx: Ctx = Depends(current)):
    ctx.need(*auth.MANAGE)
    if not ctx.user.sacpcmp_no:
        raise HTTPException(400, "Add your SACPCMP registration number to your profile first. "
                                 "Only a competent person may approve a risk assessment.")
    with db.session() as s:
        r = _get(s, db.RiskItem, rid, ctx, "Risk item")
        r.approved_at = db.utcnow()
        r.approved_by = f"{ctx.user.name} (SACPCMP {ctx.user.sacpcmp_no})"
        return risk_d(r)


@app.put("/api/profile")
def update_profile(body: dict = Body(...), ctx: Ctx = Depends(current)):
    with db.session() as s:
        u = s.get(db.User, ctx.uid)
        for k in ("name", "phone", "sacpcmp_no"):
            if k in body:
                setattr(u, k, _s(body[k]))
        if not u.name:
            raise HTTPException(400, "Your name is needed.")
        return user_d(u)


# ---------------------------------------------------------------- plant

@app.get("/api/plant")
def list_plant(site_id: str = "", ctx: Ctx = Depends(current)):
    with db.session() as s:
        q = select(db.Plant).where(db.Plant.company_id == ctx.cid, db.Plant.active)
        if site_id:
            q = q.where(db.Plant.site_id == site_id)
        return [plant_d(p) for p in s.scalars(q.order_by(db.Plant.name))]


@app.post("/api/plant")
def add_plant(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    if body.get("template") not in library.CHECKLISTS:
        raise HTTPException(400, "Pick the checklist type.")
    with db.session() as s:
        p = db.Plant(company_id=ctx.cid, name=_s(body.get("name")), template=body["template"],
                     ident=_s(body.get("ident"), 100))
        if not p.name:
            raise HTTPException(400, "Give the item a name.")
        if body.get("site_id"):
            p.site_id = _get(s, db.Site, body["site_id"], ctx, "Site").id
        s.add(p)
        s.flush()
        return plant_d(p)


@app.put("/api/plant/{pid}")
def update_plant(pid: str, body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    with db.session() as s:
        p = _get(s, db.Plant, pid, ctx, "Plant item")
        for k in ("name", "ident"):
            if k in body:
                setattr(p, k, _s(body[k]))
        if "site_id" in body:
            p.site_id = _get(s, db.Site, body["site_id"], ctx, "Site").id if body["site_id"] else None
        if "active" in body:
            p.active = bool(body["active"])
        return plant_d(p)


@app.get("/api/plant/{pid}/qr.svg")
def plant_qr(pid: str, ctx: Ctx = Depends(current)):
    import segno
    with db.session() as s:
        p = _get(s, db.Plant, pid, ctx, "Plant item")
        buf = io.BytesIO()
        segno.make(f"{config.PUBLIC_URL}/p/{p.qr_token}", error="m").save(buf, kind="svg", scale=6, border=2)
        return Response(buf.getvalue(), media_type="image/svg+xml")


@app.get("/api/plant/by-token/{token}")
def plant_by_token(token: str, ctx: Ctx = Depends(current)):
    with db.session() as s:
        p = s.scalar(select(db.Plant).where(db.Plant.qr_token == token))
        if not p or p.company_id != ctx.cid:
            raise HTTPException(404, "This QR code is not on your company's list.")
        return plant_d(p)


@app.get("/p/{token}")
def qr_landing(token: str):
    return RedirectResponse(f"/app.html#check/{token}")


# ---------------------------------------------------------------- documents

@app.get("/api/docs")
def list_docs(site_id: str = "", ctx: Ctx = Depends(current)):
    with db.session() as s:
        q = select(db.Doc).where(db.Doc.company_id == ctx.cid)
        if site_id:
            q = q.where((db.Doc.site_id.is_(None)) | (db.Doc.site_id == site_id))
        return [doc_d(d) for d in s.scalars(q.order_by(db.Doc.section, db.Doc.created_at))]


@app.post("/api/docs")
def add_doc(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.MANAGE)
    if body.get("section") not in library.UPLOAD_SECTIONS:
        raise HTTPException(400, "Pick the safety file section.")
    if not body.get("file"):
        raise HTTPException(400, "Choose the file.")
    with db.session() as s:
        d = db.Doc(company_id=ctx.cid, section=body["section"], title=_s(body.get("title")) or "Document",
                   expires=_date(body.get("expires"), "expiry date"), uploaded_by=ctx.user.name, file="")
        if body.get("site_id"):
            d.site_id = _get(s, db.Site, body["site_id"], ctx, "Site").id
        try:
            d.file = files.put_data_url(ctx.cid, body["file"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        s.add(d)
        s.flush()
        return doc_d(d)


@app.delete("/api/docs/{did}")
def delete_doc(did: str, ctx: Ctx = Depends(current)):
    ctx.need(*auth.MANAGE)
    with db.session() as s:
        s.delete(_get(s, db.Doc, did, ctx, "Document"))
    return {"ok": True}


# ---------------------------------------------------------------- files

@app.get("/api/f/{cid}/{name}")
def get_file(cid: str, name: str, exp: int = Query(...), sig: str = Query(...)):
    full = f"{cid}/{name}"
    if not files.check(full, exp, sig):
        raise HTTPException(403, "This link has expired. Refresh the page.")
    try:
        p = files.path(full)
    except ValueError:
        raise HTTPException(404, "File not found.")
    if not p.exists():
        raise HTTPException(404, "File not found.")
    return Response(p.read_bytes(), media_type=files.mime(full),
                    headers={"Cache-Control": "private, max-age=21600"})


# ---------------------------------------------------------------- sync (offline cache)

@app.get("/api/sync")
def sync(site_id: str, ctx: Ctx = Depends(current)):
    """Everything a site device needs to work offline for the day."""
    with db.session() as s:
        site = _get(s, db.Site, site_id, ctx, "Site")
        ind = _inducted(s, site.id)
        q = (select(db.Worker).join(db.SiteWorker, db.SiteWorker.worker_id == db.Worker.id)
             .where(db.SiteWorker.site_id == site.id, db.Worker.active)
             .options(selectinload(db.Worker.credentials)).order_by(db.Worker.name))
        workers = [worker_d(w, ctx, w.id in ind) for w in s.scalars(q)]
        risks = s.scalars(select(db.RiskItem).where(
            db.RiskItem.company_id == ctx.cid, db.RiskItem.active,
            (db.RiskItem.site_id.is_(None)) | (db.RiskItem.site_id == site.id)).order_by(db.RiskItem.activity))
        plant = s.scalars(select(db.Plant).where(db.Plant.company_id == ctx.cid, db.Plant.active,
                                                 (db.Plant.site_id == site.id) | (db.Plant.site_id.is_(None)))
                          .order_by(db.Plant.name))
        users = s.scalars(select(db.User).where(db.User.company_id == ctx.cid, db.User.active))
        since = today() - timedelta(days=14)
        recent = s.scalars(select(db.Record).where(db.Record.site_id == site.id, db.Record.record_date >= since)
                           .options(selectinload(db.Record.signatures))
                           .order_by(db.Record.record_date.desc(), db.Record.seq.desc()))
        return {"site": site_d(site), "workers": workers, "risks": [risk_d(r) for r in risks],
                "plant": [plant_d(p) for p in plant], "users": [{"id": u.id, "name": u.name, "role": u.role} for u in users],
                "checklists": library.CHECKLISTS, "languages": library.LANGUAGES,
                "tts_languages": [l for l in library.TTS_VOICES if tts.enabled(l)],
                "incident_types": library.INCIDENT_TYPES, "credential_kinds": library.CREDENTIAL_KINDS,
                "induction_text": ctx.company.induction_text or library.DEFAULT_INDUCTION,
                "recent": [records.to_dict(r, full=False) for r in recent],
                "today": today().isoformat(), "synced_at": db.utcnow().isoformat() + "Z"}


# ---------------------------------------------------------------- dashboard

@app.get("/api/dashboard")
def dashboard(site_id: str, ctx: Ctx = Depends(current)):
    t = today()
    with db.session() as s:
        site = _get(s, db.Site, site_id, ctx, "Site")
        recs = s.scalars(select(db.Record).where(db.Record.site_id == site.id,
                                                 db.Record.record_date >= t - timedelta(days=30))
                         .options(selectinload(db.Record.signatures))).all()
        todays = [r for r in recs if r.record_date == t]
        talks = sorted((r for r in recs if r.kind == "toolbox_talk"), key=lambda r: r.record_date)
        ind = _inducted(s, site.id)
        workers = s.scalars(select(db.Worker).join(db.SiteWorker, db.SiteWorker.worker_id == db.Worker.id)
                            .where(db.SiteWorker.site_id == site.id, db.Worker.active)
                            .options(selectinload(db.Worker.credentials))).all()
        plant = s.scalars(select(db.Plant).where(db.Plant.company_id == ctx.cid, db.Plant.active,
                                                 db.Plant.site_id == site.id)).all()
        checked = {r.payload.get("plant_id"): r.payload.get("result") for r in todays if r.kind == "check"}
        unapproved = s.scalars(select(db.RiskItem).where(
            db.RiskItem.company_id == ctx.cid, db.RiskItem.active, db.RiskItem.approved_at.is_(None),
            (db.RiskItem.site_id.is_(None)) | (db.RiskItem.site_id == site.id))).all()
        docs = s.scalars(select(db.Doc).where(db.Doc.company_id == ctx.cid,
                                              (db.Doc.site_id.is_(None)) | (db.Doc.site_id == site.id))).all()
        expiring = []
        for w in workers:
            for c in w.credentials:
                st = _expiry(c.expires)
                if st in ("expired", "expiring"):
                    expiring.append({"who": w.name, "what": c.title, "expires": c.expires.isoformat(), "status": st})
        for d in docs:
            st = _expiry(d.expires)
            if st in ("expired", "expiring"):
                expiring.append({"who": "Company", "what": d.title, "expires": d.expires.isoformat(), "status": st})
        have = {d.section for d in docs}
        missing = [x["title"] for x in library.FILE_SECTIONS if x["type"] == "upload" and x["key"] not in have]
        return {
            "date": t.isoformat(),
            "task_sheet_today": [records.to_dict(r, False) for r in todays if r.kind == "task_sheet"],
            "last_talk": talks[-1].record_date.isoformat() if talks else "",
            "talk_due": not talks or (t - talks[-1].record_date).days >= 7,
            "plant": [{"id": p.id, "name": p.name, "result": checked.get(p.id, "")} for p in plant],
            "incidents_30d": [records.to_dict(r, False) for r in recs if r.kind == "incident"],
            "reportable": [r.id for r in recs if r.kind == "incident" and r.payload.get("possibly_reportable")],
            "workers": len(workers),
            "not_inducted": [w.name for w in workers if w.id not in ind],
            "no_medical": [w.name for w in workers if not any(c.kind == "medical" and _expiry(c.expires) in ("valid", "expiring", "none") for c in w.credentials)],
            "expiring": sorted(expiring, key=lambda x: x["expires"]),
            "unapproved_risks": len(unapproved),
            "missing_docs": missing,
        }


# ---------------------------------------------------------------- records

@app.post("/api/records")
def create_record(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    rid = records.create(ctx, body)
    with db.session() as s:
        rec = s.get(db.Record, rid)
        return records.to_dict(rec, full=False)


@app.get("/api/records")
def list_records(site_id: str, kind: str = "", date_from: str = "", date_to: str = "",
                 limit: int = 200, ctx: Ctx = Depends(current)):
    with db.session() as s:
        _get(s, db.Site, site_id, ctx, "Site")
        q = select(db.Record).where(db.Record.company_id == ctx.cid, db.Record.site_id == site_id) \
            .options(selectinload(db.Record.signatures))
        if kind:
            q = q.where(db.Record.kind == kind)
        if date_from:
            q = q.where(db.Record.record_date >= _date(date_from))
        if date_to:
            q = q.where(db.Record.record_date <= _date(date_to))
        q = q.order_by(db.Record.record_date.desc(), db.Record.seq.desc()).limit(min(limit, 1000))
        return [records.to_dict(r, False) for r in s.scalars(q)]


@app.get("/api/records/{rid}")
def get_record(rid: str, ctx: Ctx = Depends(current)):
    with db.session() as s:
        rec = _get(s, db.Record, rid, ctx, "Record")
        return records.to_dict(rec)


@app.get("/api/records/{rid}/pdf")
def record_pdf(rid: str, ctx: Ctx = Depends(current)):
    with db.session() as s:
        rec = _get(s, db.Record, rid, ctx, "Record")
        site = s.get(db.Site, rec.site_id)
        data = pdf.record_pdf(rec, ctx.company, site)
        name = f"{rec.kind}-{rec.record_date}-{rec.seq}.pdf"
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{name}"'})


@app.get("/api/verify")
def verify(ctx: Ctx = Depends(current)):
    return records.verify(ctx.cid)


# ---------------------------------------------------------------- safety file

@app.get("/api/sites/{sid}/file.pdf")
def safety_file(sid: str, date_from: str = "", date_to: str = "", ctx: Ctx = Depends(current)):
    with db.session() as s:
        site = _get(s, db.Site, sid, ctx, "Site")
        d0 = _date(date_from) or site.start_date or date(2000, 1, 1)
        d1 = _date(date_to) or today()
        docs = s.scalars(select(db.Doc).where(db.Doc.company_id == ctx.cid,
                                              (db.Doc.site_id.is_(None)) | (db.Doc.site_id == site.id))
                         .order_by(db.Doc.section, db.Doc.created_at)).all()
        workers = s.scalars(select(db.Worker).join(db.SiteWorker, db.SiteWorker.worker_id == db.Worker.id)
                            .where(db.SiteWorker.site_id == site.id)
                            .options(selectinload(db.Worker.credentials)).order_by(db.Worker.name)).all()
        risks = s.scalars(select(db.RiskItem).where(
            db.RiskItem.company_id == ctx.cid, db.RiskItem.active,
            (db.RiskItem.site_id.is_(None)) | (db.RiskItem.site_id == site.id)).order_by(db.RiskItem.activity)).all()
        recs = s.scalars(select(db.Record).where(db.Record.site_id == site.id, db.Record.record_date >= d0,
                                                 db.Record.record_date <= d1)
                         .options(selectinload(db.Record.signatures))).all()
        data = pdf.safety_file(ctx.company, site, date_from=d0, date_to=d1, docs=docs, workers=workers,
                               inducted=_inducted(s, site.id), risks=risks, recs=recs,
                               chain=records.verify(ctx.cid))
    name = re.sub(r"[^\w-]+", "-", site.name)[:40]
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="Safety-file-{name}-{d1}.pdf"'})


# ---------------------------------------------------------------- AI drafts

def _site_context(s, ctx: Ctx, site_id: str):
    site = _get(s, db.Site, site_id, ctx, "Site")
    risks = [risk_d(r) for r in s.scalars(select(db.RiskItem).where(
        db.RiskItem.company_id == ctx.cid, db.RiskItem.active,
        (db.RiskItem.site_id.is_(None)) | (db.RiskItem.site_id == site.id)))]
    workers = [{"id": w.id, "name": w.name, "trade": w.trade, "employer": w.employer} for w in s.scalars(
        select(db.Worker).join(db.SiteWorker, db.SiteWorker.worker_id == db.Worker.id)
        .where(db.SiteWorker.site_id == site.id, db.Worker.active))]
    plant = [{"id": p.id, "name": p.name, "ident": p.ident} for p in s.scalars(
        select(db.Plant).where(db.Plant.company_id == ctx.cid, db.Plant.active,
                               (db.Plant.site_id == site.id) | (db.Plant.site_id.is_(None))))]
    return site, risks, workers, plant


@app.post("/api/ai/task-sheet")
def ai_task_sheet(site_id: str = Form(...), audio: UploadFile | None = File(None), text: str = Form(""),
                  ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    _limit(ctx)
    with db.session() as s:
        _, risks, workers, plant = _site_context(s, ctx, site_id)
    spoken, ref = _audio_text(ctx, audio, text)
    draft = _ai(ai.task_sheet, spoken, risks, workers, plant)
    # Server-side safety rule: drop any id that is not in this site's lists.
    rid, wid, pid = {r["id"] for r in risks}, {w["id"] for w in workers}, {p["id"] for p in plant}
    for t in draft.get("tasks", []):
        t["risk_item_ids"] = [i for i in t.get("risk_item_ids", []) if i in rid]
        t["worker_ids"] = [i for i in t.get("worker_ids", []) if i in wid]
        t["plant_ids"] = [i for i in t.get("plant_ids", []) if i in pid]
        if not t["risk_item_ids"]:
            draft.setdefault("unmatched", []).append({"description": t.get("description", ""),
                                                      "reason": "No risk assessment item matched."})
    draft["tasks"] = [t for t in draft.get("tasks", []) if t["risk_item_ids"]]
    return {"transcript": spoken, "audio": ref, "draft": draft}


@app.post("/api/ai/incident")
def ai_incident(site_id: str = Form(...), audio: UploadFile | None = File(None), text: str = Form(""),
                ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    _limit(ctx)
    with db.session() as s:
        _, _, workers, _ = _site_context(s, ctx, site_id)
    spoken, ref = _audio_text(ctx, audio, text)
    draft = _ai(ai.incident, spoken, workers)
    ids = {w["id"] for w in workers}
    for p in draft.get("people", []):
        if p.get("worker_id") not in ids:
            p["worker_id"] = ""
    return {"transcript": spoken, "audio": ref, "draft": draft}


@app.post("/api/ai/toolbox-talk")
def ai_toolbox_talk(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    _limit(ctx)
    language = body.get("language") if body.get("language") in library.LANGUAGES else "en"
    with db.session() as s:
        _, risks, _, _ = _site_context(s, ctx, body.get("site_id", ""))
        ids = set(body.get("risk_item_ids") or [])
        chosen = [r for r in risks if r["id"] in ids]
    if not chosen and not _s(body.get("topic")):
        raise HTTPException(400, "Pick today's tasks or type a topic.")
    hazards = [{"activity": r["activity"], "hazards": r["hazards"], "ppe": r["ppe"]} for r in chosen]
    talk = _ai(ai.toolbox_talk, _s(body.get("topic")), hazards, language)
    talk["language"] = language
    talk["ai_translated"] = language != "en"
    return talk


@app.post("/api/ai/risk-draft")
def ai_risk_draft(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.MANAGE)
    _limit(ctx)
    desc = _s(body.get("description"), 500)
    if not desc:
        raise HTTPException(400, "Describe the activity.")
    return _ai(ai.risk_draft, desc)


@app.post("/api/tts")
def text_to_speech(body: dict = Body(...), ctx: Ctx = Depends(current)):
    lang = body.get("language", "en")
    if not tts.enabled(lang):
        raise HTTPException(501, "Spoken audio is not available for this language yet.")
    _limit(ctx)
    audio = _ai(tts.speak, _s(body.get("text"), 6000), lang)
    name = files.put(ctx.cid, audio, "audio/mpeg")
    return {"audio": {"file": name}, "url": files.sign(name)}


# ---------------------------------------------------------------- cron: expiry alerts

@app.post("/api/cron/expiry")
def cron_expiry(x_cron_token: str = Header(None)):
    if not config.CRON_TOKEN or x_cron_token != config.CRON_TOKEN:
        raise HTTPException(403, "Forbidden")
    sent = 0
    with db.session() as s:
        for c in s.scalars(select(db.Company)):
            lines = []
            for cr in s.scalars(select(db.Credential).where(db.Credential.company_id == c.id)
                                .options(selectinload(db.Credential.worker))):
                st = _expiry(cr.expires)
                if st in ("expired", "expiring") and cr.worker.active:
                    lines.append(f"- {cr.worker.name}: {cr.title} {st} ({cr.expires})")
            for d in s.scalars(select(db.Doc).where(db.Doc.company_id == c.id)):
                st = _expiry(d.expires)
                if st in ("expired", "expiring"):
                    lines.append(f"- Document: {d.title} {st} ({d.expires})")
            if not lines:
                continue
            for u in s.scalars(select(db.User).where(db.User.company_id == c.id, db.User.active,
                                                     db.User.role.in_(("owner", "safety")))):
                mailer.send(u.email, f"{config.APP_NAME}: {len(lines)} certificates need attention",
                            "These certificates and documents are expired or expire within "
                            f"{config.EXPIRY_WARN_DAYS} days:\n\n" + "\n".join(lines[:200])
                            + f"\n\nOpen {config.PUBLIC_URL}/app.html to update them.")
                sent += 1
    return {"emails": sent}


# ---------------------------------------------------------------- static PWA

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app.html")


app.mount("/", StaticFiles(directory=config.WEB, html=True), name="web")
