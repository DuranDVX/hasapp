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
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import aes, ai, auth, compliance, config, consultant, db, files, library, mailer, pdf, records, stt, tts
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
# Pilot: sign-up by invite only. Comma-separated codes, one per person, so each can be switched off.
SIGNUP_CODE = {c.strip().lower() for c in os.getenv("HAS_SIGNUP_CODE", "").split(",") if c.strip()}


def today() -> date:
    return datetime.now(SA).date()


SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "microphone=(self), camera=(self), geolocation=(self)",
}


CANONICAL = (urlparse(config.PUBLIC_URL).hostname or "").lower()


@app.middleware("http")
async def _headers(request: Request, call_next):
    host = request.headers.get("host", "").split(":")[0].lower()
    if CANONICAL.startswith("www.") and host == CANONICAL[4:]:   # one address for everyone: www
        q = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"https://{CANONICAL}{request.url.path}{q}", status_code=301)
    resp = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    path = request.url.path
    if path.startswith("/admin") or path.startswith("/api/admin"):
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
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


def site_risks_q(cid: str, site: db.Site):
    """Risk items that apply to a site. With "ra_only", only the site's own (consultant) items."""
    q = select(db.RiskItem).where(db.RiskItem.company_id == cid, db.RiskItem.active)
    if (site.settings or {}).get("ra_only"):
        return q.where(db.RiskItem.site_id == site.id)
    return q.where((db.RiskItem.site_id.is_(None)) | (db.RiskItem.site_id == site.id))


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
            "end_date": x.end_date.isoformat() if x.end_date else "", "status": x.status,
            "features": x.features or {}, "print_required": bool(x.print_required),
            "ra_only": bool((x.settings or {}).get("ra_only")),
            "facilities": (x.settings or {}).get("facilities") or {},
            "has_spec": bool((x.settings or {}).get("spec")), "has_ra": bool((x.settings or {}).get("ra"))}


def contractor_d(c: db.Contractor) -> dict:
    return {"id": c.id, "site_id": c.site_id, "name": c.name, "reg_no": c.reg_no, "scope": c.scope,
            "contact": c.contact, "phone": c.phone, "email": c.email,
            "coid_expires": c.coid_expires.isoformat() if c.coid_expires else "",
            "coid_status": _expiry(c.coid_expires) if c.coid_file else "missing",
            "coid_url": files.sign(c.coid_file), "appointed_on": c.appointed_on.isoformat() if c.appointed_on else "",
            "hs_plan_ok": c.hs_plan_ok, "active": c.active}


def aes_d(a: db.AesDoc) -> dict:
    return {"id": a.id, "site_id": a.site_id, "record_id": a.record_id, "contractor_id": a.contractor_id,
            "kind": a.kind, "kind_label": library.AES_DOCS.get(a.kind, a.kind), "title": a.title,
            "signers": a.signers, "status": a.status, "method": a.method, "signatures": a.signatures,
            "summary": aes.summary({"signatures": a.signatures}) if a.method == "aes" else
                       ("Wet-ink scan uploaded." if a.method == "wet_ink" else "Waiting for signature."),
            "note": a.note, "original_url": files.sign(a.original_file), "signed_url": files.sign(a.signed_file),
            "created_at": a.created_at.date().isoformat(),
            "signed_at": a.signed_at.date().isoformat() if a.signed_at else ""}


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
            "source": r.source, "ref": r.ref, "approved": r.approved_at is not None, "approved_by": r.approved_by,
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
    invite = _s(body.get("invite")).lower()
    with db.session() as s:
        all_codes = s.scalars(select(db.InviteCode)).all()
        codes = {c.code for c in all_codes if c.active}
    # Invite-only once any code exists, even when every code is switched off.
    if (SIGNUP_CODE or all_codes) and invite not in (SIGNUP_CODE | codes):
        raise HTTPException(403, "Sign-up needs an invite code during the pilot.")
    email = _s(body.get("email")).lower()
    if "@" not in email or not _s(body.get("company")) or not _s(body.get("name")):
        raise HTTPException(400, "Fill in the company name, your name and your email.")
    auth.valid_pw(body.get("password", ""))
    with db.session() as s:
        if s.scalar(select(db.User).where(db.User.email == email)):
            raise HTTPException(409, "That email already has an account. Log in instead.")
        c = db.Company(name=_s(body["company"]), email=email, invite=invite)
        ic = s.get(db.InviteCode, invite) if invite else None
        if ic:
            ic.uses = (ic.uses or 0) + 1
        s.add(c)
        s.flush()
        u = db.User(company_id=c.id, email=email, name=_s(body["name"]), role="owner",
                    pw_hash=auth.hash_pw(body["password"]))
        s.add(u)
        for r in library.STARTER_RISKS:
            s.add(db.RiskItem(company_id=c.id, activity=r["activity"], hazards=r["hazards"],
                              ppe=r["ppe"], source="starter"))
        s.flush()
        if invite:
            log.info("sign-up %s with invite %s", c.name, invite)
        return {"token": auth.new_session(s, u)}


@app.post("/api/login")
def login(body: dict = Body(...)):
    email = _s(body.get("email")).lower()
    with db.session() as s:
        u = s.scalar(select(db.User).where(db.User.email == email))
        if not u or not u.active or not auth.check_pw(body.get("password", ""), u.pw_hash):
            time.sleep(0.5)
            raise HTTPException(401, "Wrong email or password.")
        if not s.get(db.Company, u.company_id).active:
            raise HTTPException(401, "This company's account is switched off. Contact SiteBakkie.")
        u.last_login_at = db.utcnow()
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
    if isinstance(body.get("features"), dict):
        x.features = {k: bool(v) for k, v in body["features"].items() if k in library.SITE_FEATURES}
    if "print_required" in body:
        x.print_required = bool(body["print_required"])
    if isinstance(body.get("facilities"), dict):
        fac = {k: max(0, min(500, int(v))) for k, v in body["facilities"].items()
               if k in ("toilets", "showers") and str(v).isdigit()}
        x.settings = {**(x.settings or {}), "facilities": fac}
    if "ra_only" in body:
        x.settings = {**(x.settings or {}), "ra_only": bool(body["ra_only"])}
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
        if site_id:
            q = site_risks_q(ctx.cid, _get(s, db.Site, site_id, ctx, "Site"))
        else:
            q = select(db.RiskItem).where(db.RiskItem.company_id == ctx.cid, db.RiskItem.active)
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
        risks = s.scalars(site_risks_q(ctx.cid, site).order_by(db.RiskItem.ref, db.RiskItem.activity))
        plant = s.scalars(select(db.Plant).where(db.Plant.company_id == ctx.cid, db.Plant.active,
                                                 (db.Plant.site_id == site.id) | (db.Plant.site_id.is_(None)))
                          .order_by(db.Plant.name))
        users = s.scalars(select(db.User).where(db.User.company_id == ctx.cid, db.User.active))
        since = today() - timedelta(days=14)
        recent = s.scalars(select(db.Record).where(db.Record.site_id == site.id, db.Record.record_date >= since)
                           .options(selectinload(db.Record.signatures))
                           .order_by(db.Record.record_date.desc(), db.Record.seq.desc()))
        recent = list(recent)
        today_risks = sorted({rid for r in recent if r.kind == "task_sheet" and r.record_date == today()
                              for t in r.payload.get("tasks", []) for rid in (x["id"] for x in t.get("risks", []))})
        return {"site": site_d(site), "workers": workers, "risks": [risk_d(r) for r in risks],
                "today_risk_ids": today_risks,
                "plant": [plant_d(p) for p in plant], "users": [{"id": u.id, "name": u.name, "role": u.role} for u in users],
                "checklists": library.CHECKLISTS, "languages": library.LANGUAGES,
                "tts_languages": [l for l in library.TTS_VOICES if tts.enabled(l)],
                "incident_types": library.INCIDENT_TYPES, "credential_kinds": library.CREDENTIAL_KINDS,
                "file_sections": library.FILE_SECTIONS,
                "site_features": library.SITE_FEATURES, "appointments": library.APPOINTMENTS,
                "visitor_ppe": library.VISITOR_PPE, "visitor_rules": library.VISITOR_RULES,
                "audit_items": library.AUDIT_ITEMS, "aes_kinds": library.AES_DOCS,
                "worker_consent": library.WORKER_CONSENT, "inspection_schedule": library.INSPECTION_SCHEDULE,
                "forms": library.FORMS, "ra_roles": ((site.settings or {}).get("ra") or {}).get("roles", []),
                "matrix": {"consequence": library.CONSEQUENCE, "likelihood": library.LIKELIHOOD},
                "spec_rules": [r["rule"] for r in (((site.settings or {}).get("spec") or {}).get("key_rules") or [])],
                "esign_accepted": bool(ctx.company.esign_accepted_at),
                "required_appointments": [k for k, f in library.REQUIRED_APPOINTMENTS
                                          if f is None or (site.features or {}).get(f)],
                "contractors": [contractor_d(c) for c in s.scalars(select(db.Contractor).where(
                    db.Contractor.site_id == site.id, db.Contractor.active))],
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
    if body.get("kind") == "audit":
        ctx.need(*auth.WRITE, "auditor")
    else:
        ctx.need(*auth.WRITE)
    rid = records.create(ctx, body)
    with db.session() as s:
        rec = s.get(db.Record, rid)
        if rec.kind == "appointment" and rec.payload.get("aes_required") and not s.scalar(
                select(db.AesDoc.id).where(db.AesDoc.record_id == rec.id)):
            site = s.get(db.Site, rec.site_id)
            data = pdf.record_pdf(rec, ctx.company, site, printed=False)
            s.add(db.AesDoc(company_id=ctx.cid, site_id=rec.site_id, record_id=rec.id, kind="appointment",
                            title=f"Appointment: {rec.payload['title']} ({rec.payload['appointee']['name']})",
                            signers=[f"{ctx.user.name} (appointer)", f"{rec.payload['appointee']['name']} (appointee)"],
                            original_file=files.put(ctx.cid, data, "application/pdf")))
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
def record_pdf(rid: str, print: int = 0, ctx: Ctx = Depends(current)):
    with db.session() as s:
        rec = _get(s, db.Record, rid, ctx, "Record")
        site = s.get(db.Site, rec.site_id)
        data = pdf.record_pdf(rec, ctx.company, site, printed=bool(print))
        name = f"{rec.kind}-{rec.record_date}-{rec.seq}.pdf"
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{name}"'})


@app.get("/api/records/{rid}/annexure1.pdf")
def annexure1_pdf(rid: str, ctx: Ctx = Depends(current)):
    with db.session() as s:
        inc = _get(s, db.Record, rid, ctx, "Record")
        if inc.kind != "incident":
            raise HTTPException(400, "Annexure 1 is for incident records.")
        site = s.get(db.Site, inc.site_id)
        inv = next((r for r in s.scalars(select(db.Record).where(db.Record.company_id == ctx.cid,
                                                                  db.Record.kind == "investigation")
                                         .options(selectinload(db.Record.signatures)))
                    if r.payload.get("incident_id") == inc.id), None)
        ids = [x.get("worker_id") for x in inc.payload.get("people", []) if x.get("worker_id")]
        info = {w.id: {"id_number": w.id_number, "trade": w.trade}
                for w in s.scalars(select(db.Worker).where(db.Worker.company_id == ctx.cid, db.Worker.id.in_(ids or [""])))}
        data = pdf.annexure1(ctx.company, site, inc, inv, info)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="Annexure1-{inc.record_date}.pdf"'})


# ---------------------------------------------------------------- Site Board

@app.get("/api/board")
def site_board(site_id: str, ctx: Ctx = Depends(current)):
    with db.session() as s:
        site = _get(s, db.Site, site_id, ctx, "Site")
        company = s.get(db.Company, ctx.cid)
        return compliance.board(s, company, site, today(), datetime.now(SA).hour)


@app.get("/api/esign")
def esign_policy(ctx: Ctx = Depends(current)):
    c = ctx.company
    return {"text": library.ESIGN_POLICY.format(company=c.name, app=config.APP_NAME),
            "accepted": bool(c.esign_accepted_at), "accepted_by": c.esign_accepted_by,
            "accepted_at": c.esign_accepted_at.isoformat() if c.esign_accepted_at else ""}


@app.post("/api/esign/accept")
def esign_accept(ctx: Ctx = Depends(current)):
    ctx.need("owner")
    with db.session() as s:
        c = s.get(db.Company, ctx.cid)
        c.esign_accepted_at = db.utcnow()
        c.esign_accepted_by = f"{ctx.user.name} ({ctx.user.email})"
        return {"ok": True}


# ---------------------------------------------------------------- contractors

def _contractor_fields(c: db.Contractor, body: dict, cid: str) -> None:
    for k, n in (("name", 200), ("reg_no", 60), ("contact", 200), ("phone", 40), ("email", 200)):
        if k in body:
            setattr(c, k, _s(body[k], n))
    if "scope" in body:
        c.scope = _s(body["scope"], 2000)
    if "coid_expires" in body:
        c.coid_expires = _date(body["coid_expires"], "COID expiry date")
    if "appointed_on" in body:
        c.appointed_on = _date(body["appointed_on"], "appointment date")
    if "hs_plan_ok" in body:
        c.hs_plan_ok = bool(body["hs_plan_ok"])
    if "active" in body:
        c.active = bool(body["active"])
    if body.get("coid_file"):
        try:
            c.coid_file = files.put_data_url(cid, body["coid_file"])
        except ValueError as e:
            raise HTTPException(400, str(e))
    if not c.name:
        raise HTTPException(400, "Give the contractor's name.")


@app.get("/api/contractors")
def list_contractors(site_id: str, ctx: Ctx = Depends(current)):
    with db.session() as s:
        _get(s, db.Site, site_id, ctx, "Site")
        return [contractor_d(c) for c in s.scalars(select(db.Contractor).where(
            db.Contractor.company_id == ctx.cid, db.Contractor.site_id == site_id).order_by(db.Contractor.name))]


@app.post("/api/contractors")
def add_contractor(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    with db.session() as s:
        site = _get(s, db.Site, body.get("site_id", ""), ctx, "Site")
        c = db.Contractor(company_id=ctx.cid, site_id=site.id, name="")
        _contractor_fields(c, body, ctx.cid)
        s.add(c)
        s.flush()
        return contractor_d(c)


@app.put("/api/contractors/{cid_}")
def update_contractor(cid_: str, body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    with db.session() as s:
        c = _get(s, db.Contractor, cid_, ctx, "Contractor")
        _contractor_fields(c, body, ctx.cid)
        return contractor_d(c)


@app.post("/api/contractors/{cid_}/agreement")
def contractor_agreement(cid_: str, body: dict = Body(default={}), ctx: Ctx = Depends(current)):
    """Issue a section 37(2) mandatary agreement for advanced e-signature."""
    ctx.need(*auth.MANAGE)
    with db.session() as s:
        c = _get(s, db.Contractor, cid_, ctx, "Contractor")
        site = s.get(db.Site, c.site_id)
        a = db.AesDoc(id=db.new_id(), company_id=ctx.cid, site_id=site.id, contractor_id=c.id,
                      kind="mandatary_agreement", title=f"Section 37(2) agreement: {c.name}",
                      signers=[f"{_s(body.get('pc_signer')) or ctx.user.name} for {ctx.company.name}",
                               f"{_s(body.get('contractor_signer')) or c.contact or '__________'} for {c.name}"])
        data = pdf.aes_document(ctx.company, site, a.title, pdf.mandatary_agreement_body(ctx.company, site, c),
                                a.signers, a.id)
        a.original_file = files.put(ctx.cid, data, "application/pdf")
        s.add(a)
        s.flush()
        return aes_d(a)


# ---------------------------------------------------------------- AES documents

@app.get("/api/aes")
def list_aes(site_id: str = "", ctx: Ctx = Depends(current)):
    with db.session() as s:
        q = select(db.AesDoc).where(db.AesDoc.company_id == ctx.cid)
        if site_id:
            q = q.where((db.AesDoc.site_id == site_id) | (db.AesDoc.site_id.is_(None)))
        return [aes_d(a) for a in s.scalars(q.order_by(db.AesDoc.created_at.desc()))]


@app.post("/api/aes")
def add_aes(body: dict = Body(...), ctx: Ctx = Depends(current)):
    """Issue a document for AES: an excavation decision, a hoist record entry, or any PDF."""
    ctx.need(*auth.MANAGE)
    kind = body.get("kind")
    if kind not in library.AES_DOCS:
        raise HTTPException(400, "Pick the document type.")
    signers = [_s(x) for x in (body.get("signers") or []) if _s(x)][:6]
    if not signers:
        raise HTTPException(400, "Name at least one person who must sign.")
    with db.session() as s:
        site = _get(s, db.Site, body.get("site_id", ""), ctx, "Site")
        a = db.AesDoc(id=db.new_id(), company_id=ctx.cid, site_id=site.id, kind=kind,
                      title=_s(body.get("title"), 300) or library.AES_DOCS[kind], signers=signers)
        if body.get("file"):
            try:
                a.original_file = files.put_data_url(ctx.cid, body["file"])
            except ValueError as e:
                raise HTTPException(400, str(e))
            if not a.original_file.endswith(".pdf"):
                raise HTTPException(400, "Upload a PDF to sign.")
        else:
            fields = body.get("fields") or {}
            flow = pdf.excavation_decision_body(fields) if kind == "excavation_decision" \
                else pdf.text_body(_s(body.get("text"), 20000) or a.title)
            a.original_file = files.put(ctx.cid, pdf.aes_document(ctx.company, site, a.title, flow, signers, a.id),
                                        "application/pdf")
        s.add(a)
        s.flush()
        return aes_d(a)


@app.post("/api/aes/{aid}/signed")
def upload_signed(aid: str, body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.WRITE)
    method = body.get("method")
    if method not in ("aes", "wet_ink"):
        raise HTTPException(400, "Say how it was signed: AES or wet ink.")
    if not body.get("file"):
        raise HTTPException(400, "Choose the signed file.")
    with db.session() as s:
        a = _get(s, db.AesDoc, aid, ctx, "Document")
        try:
            name = files.put_data_url(ctx.cid, body["file"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        if method == "aes":
            if not name.endswith(".pdf"):
                raise HTTPException(400, "An AES-signed document must be a PDF.")
            orig = files.read(a.original_file) if a.original_file else None
            res = aes.inspect(files.read(name), orig)
            good = [x for x in res["signatures"] if x.get("intact") and x.get("valid")]
            if not good:
                raise HTTPException(400, res["error"] or "No intact digital signature found in this PDF. "
                                    "Upload the PDF exactly as the signing service returned it, or choose wet ink.")
            a.signatures = res["signatures"]
            a.note = ("Contains the original document unchanged. " if res["contains_original"] else "") + aes.summary(res)
        else:
            a.signatures, a.note = [], _s(body.get("note"), 500) or "Wet-ink signatures; scan uploaded."
        a.signed_file, a.method, a.status, a.signed_at = name, method, "signed", db.utcnow()
        a.uploaded_by = ctx.user.name
        return aes_d(a)


# ---------------------------------------------------------------- print centre

PRINT_PACKS = {
    "task_sheet": "Daily task sheets", "toolbox_talk": "Toolbox talks", "incident": "Incident reports",
    "investigation": "Incident investigations", "audit": "Audit reports", "appointment": "Legal appointments",
    "induction": "Inductions (full records)", "check": "Checks and inspections (full records)",
    "induction_register": "Induction register", "visitor_register": "Visitor register",
    "check_register": "Plant and inspection register",
    **{k: v["title"] + "s" for k, v in library.FORMS.items()},
}


@app.get("/api/print/packs")
def print_packs(ctx: Ctx = Depends(current)):
    return PRINT_PACKS


@app.get("/api/sites/{sid}/print.pdf")
def print_pack(sid: str, what: str, date_from: str = "", date_to: str = "", template: str = "",
               ctx: Ctx = Depends(current)):
    if what not in PRINT_PACKS:
        raise HTTPException(400, "Unknown print pack.")
    with db.session() as s:
        site = _get(s, db.Site, sid, ctx, "Site")
        d0 = _date(date_from) or site.start_date or date(2000, 1, 1)
        d1 = _date(date_to) or today()
        kind = {"induction_register": "induction", "visitor_register": "visitor", "check_register": "check"}.get(what, what)
        recs = s.scalars(select(db.Record).where(db.Record.site_id == site.id, db.Record.kind == kind,
                                                 db.Record.record_date >= d0, db.Record.record_date <= d1)
                         .options(selectinload(db.Record.signatures))
                         .order_by(db.Record.record_date, db.Record.seq)).all()
        if template:
            recs = [r for r in recs if r.payload.get("template") == template]
        title, sub = PRINT_PACKS[what], f"{d0} to {d1}"
        first = lambda r: r.signatures[0] if r.signatures else None
        if what == "induction_register":
            rows = [[str(r.record_date), r.payload.get("worker_name", ""), r.created_name,
                     pdf.sig_img(first(r).image_file if first(r) else ""), r.hash[:12]] for r in recs]
            data = pdf.register_pdf(ctx.company, site, title, sub, ["Date", "Worker", "Inducted by", "Worker signature", "Record"],
                                    rows, [25, 70, 55, 50, 40])
        elif what == "visitor_register":
            rows = [[str(r.record_date), r.payload.get("time_in", "")[11:16], r.payload.get("name", ""),
                     r.payload.get("company", ""), r.payload.get("purpose", ""), r.payload.get("host", ""),
                     ", ".join(r.payload.get("ppe", [])), pdf.sig_img(first(r).image_file if first(r) else "")] for r in recs]
            data = pdf.register_pdf(ctx.company, site, title, sub,
                                    ["Date", "In", "Visitor", "Company", "Purpose", "Host", "PPE", "Signature"],
                                    rows, [22, 12, 40, 35, 45, 30, 45, 40])
        elif what == "check_register":
            res = {"pass": "Pass", "defects": "Defects", "fail": "FAIL"}
            rows = []
            for r in recs:
                p = r.payload
                defects = "; ".join(f"{i['q']}: {i.get('note', '')}" for i in p.get("items", []) if i["answer"] == "defect")
                g = first(r)
                rows.append([str(r.record_date), p.get("title", ""), (p.get("plant_name") or p.get("location") or ""),
                             res.get(p.get("result"), ""), defects or "-", g.name if g else "",
                             pdf.sig_img(g.image_file if g else "")])
            data = pdf.register_pdf(ctx.company, site, title, sub,
                                    ["Date", "Checklist", "Item / place", "Result", "Defects", "By", "Signature"],
                                    rows, [22, 45, 40, 18, 70, 35, 40])
        else:
            data = pdf.records_pdf(recs, ctx.company, site, f"{title} · {sub}", printed=True)
    fname = re.sub(r"[^\w-]+", "-", f"{title}-{site.name}")[:60]
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}.pdf"'})


# ---------------------------------------------------------------- public verification of a print

@app.get("/v/{rid}", include_in_schema=False)
def verify_print(rid: str, h: str = ""):
    """Anyone holding a print can check it against the electronic original.

    Shows no personal information: only the record type, date, number and
    whether the stored record is intact and matches the printed hash.
    """
    with db.session() as s:
        rec = s.get(db.Record, rid)
        ok = bool(rec) and len(h) >= 12 and rec.hash.startswith(h)
        intact = False
        if rec:
            prev = rec.prev_hash
            intact = records.compute_hash(prev, rec) == rec.hash
    if not rec:
        title, msg, color = "Not found", "There is no record with this code.", "#b3261e"
    elif ok and intact:
        title, msg, color = "Verified", (f"This {records.KINDS[rec.kind].lower()} of {rec.record_date} "
                                         f"(record #{rec.seq}) matches the electronic original. "
                                         "The original has not been changed since it was signed."), "#12895a"
    elif not intact:
        title, msg, color = "Changed", "The stored record does not match its own hash. Report this.", "#b3261e"
    else:
        title, msg, color = "Does not match", "This print does not match the electronic original.", "#b3261e"
    html_ = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · {config.APP_NAME}</title><style>body{{font:17px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f3f5f8;color:#14202b}}
main{{max-width:520px;margin:40px auto;padding:0 16px}}.card{{background:#fff;border-radius:16px;padding:22px;border-top:8px solid {color}}}
h1{{margin:0 0 8px;color:{color}}}small{{color:#5d6c7b}}</style></head><body><main><div class="card"><h1>{title}</h1>
<p>{msg}</p><small>{config.APP_NAME} record verification · hash {(rec.hash[:16] + '…') if rec else '-'}</small></div></main></body></html>"""
    return HTMLResponse(html_, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


# ---------------------------------------------------------------- incidents and audits helpers

@app.get("/api/incidents")
def list_incidents(site_id: str, ctx: Ctx = Depends(current)):
    with db.session() as s:
        _get(s, db.Site, site_id, ctx, "Site")
        recs = s.scalars(select(db.Record).where(db.Record.site_id == site_id,
                                                 db.Record.kind.in_(("incident", "investigation")))
                         .options(selectinload(db.Record.signatures))
                         .order_by(db.Record.record_date.desc())).all()
        inv = {r.payload.get("incident_id"): r for r in recs if r.kind == "investigation"}
        out = []
        for r in recs:
            if r.kind != "incident":
                continue
            i = inv.get(r.id)
            out.append(records.to_dict(r, False) | {
                "type": r.payload.get("type"), "possibly_reportable": r.payload.get("possibly_reportable"),
                "investigation_id": i.id if i else "", "days_open": (today() - r.record_date).days,
                "due": (r.record_date + timedelta(days=7)).isoformat()})
        return out


AUDIT_MAP = {"plan": ["hs_plan"], "file": ["client_spec", "notification"], "appointments": ["appointments"],
             "risk": ["risk"], "induction": ["inductions", "visitors"], "medicals": ["medicals"],
             "training": ["task_sheet", "toolbox_talk", "certificates"], "fall": ["fall_plan"],
             "excavations": ["insp_excavation"], "scaffolds": ["insp_scaffold"],
             "plant": ["plant_checks", "operators"], "electrical": ["insp_electrical_db"],
             "fire": ["insp_fire_extinguisher", "insp_first_aid"], "contractors": ["contractors"],
             "incidents": ["incidents"], "housekeeping": []}


@app.get("/api/audit/prefill")
def audit_prefill(site_id: str, ctx: Ctx = Depends(current)):
    """Start an audit from the Site Board: red tiles become gaps the auditor confirms."""
    with db.session() as s:
        site = _get(s, db.Site, site_id, ctx, "Site")
        b = compliance.board(s, s.get(db.Company, ctx.cid), site, today(), 12)
    st = {t["key"]: t for t in b["tiles"]}
    items = []
    for key, title, reg in library.AUDIT_ITEMS:
        tl = [st[k] for k in AUDIT_MAP.get(key, []) if k in st]
        if not tl:
            res, note = ("na" if AUDIT_MAP.get(key) else ""), ""
        elif any(t["status"] == "red" for t in tl):
            res, note = "gap", "; ".join(t["detail"] for t in tl if t["status"] == "red")
        else:
            res, note = "ok", ""
        items.append({"key": key, "title": title, "reg": reg, "result": res, "note": note})
    return {"items": items, "board": {"counts": b["counts"], "date": b["date"]},
            "report_due": (today() + timedelta(days=7)).isoformat()}


# ---------------------------------------------------------------- consultant documents (RA, spec)

def _settings(site: db.Site, **kw) -> None:
    site.settings = {**(site.settings or {}), **kw}


def _store_upload(ctx: Ctx, body: dict) -> tuple[str, bytes, str]:
    if not body.get("file"):
        raise HTTPException(400, "Choose the file.")
    try:
        name = files.put_data_url(ctx.cid, body["file"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return name, files.read(name), _s(body.get("filename"), 200) or name.rsplit("/", 1)[-1]


@app.get("/api/consultant")
def consultant_status(site_id: str, ctx: Ctx = Depends(current)):
    with db.session() as s:
        site = _get(s, db.Site, site_id, ctx, "Site")
        st = site.settings or {}
        ra, spec = st.get("ra"), st.get("spec")
        return {"ra": ra and {k: ra[k] for k in ("header", "flags", "imported_at", "imported_by", "roles", "file", "approved")}
                      | {"file_url": files.sign(ra["file"])},
                "spec": spec and (spec | {"file_url": files.sign(spec.get("file", ""))}),
                "coverage": st.get("coverage"), "ra_only": bool(st.get("ra_only"))}


@app.post("/api/consultant/ra/preview")
def ra_preview(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.MANAGE)
    _limit(ctx)
    name, data, label = _store_upload(ctx, body)
    ra = _ai(ai.ra_extract, label if "." in label else name, data)
    sig = aes.inspect(data) if name.endswith(".pdf") else None
    with db.session() as s:
        site = _get(s, db.Site, body.get("site_id", ""), ctx, "Site")
        flags = consultant.ra_check(ra, sig, (site.settings or {}).get("spec"), today())
        items = consultant.ra_items(ra)
        _settings(site, ra_pending={"file": name, "ra": ra, "flags": flags})
    return {"header": ra.get("header", {}), "items": items, "flags": flags,
            "roles": consultant.ra_roles(items)}


def _coverage(s, ctx: Ctx, site: db.Site) -> None:
    spec = (site.settings or {}).get("spec") or {}
    hazards = spec.get("client_hazards") or []
    items = [risk_d(r) for r in s.scalars(site_risks_q(ctx.cid, site))]
    if not hazards or not items:
        return
    try:
        res = ai.hazard_coverage(hazards, items)
        _settings(site, coverage={"results": res["results"], "at": db.utcnow().isoformat(timespec="seconds")})
    except Exception:
        log.exception("coverage check failed")


@app.post("/api/consultant/ra/confirm")
def ra_confirm(body: dict = Body(...), ctx: Ctx = Depends(current)):
    """Load the previewed risk assessment into the site's library."""
    ctx.need(*auth.MANAGE)
    with db.session() as s:
        site = _get(s, db.Site, body.get("site_id", ""), ctx, "Site")
        pend = (site.settings or {}).get("ra_pending")
        if not pend:
            raise HTTPException(400, "Upload the risk assessment again.")
        ra, h = pend["ra"], pend["ra"].get("header", {})
        approve = bool(body.get("approve"))
        team = ", ".join(f"{t.get('name', '')} ({t.get('title', '')})" for t in h.get("team", [])) or "the consultant"
        for old in s.scalars(select(db.RiskItem).where(db.RiskItem.site_id == site.id,
                                                       db.RiskItem.source == "consultant_ra", db.RiskItem.active)):
            old.active = False   # a new revision replaces the old one; records keep their copies
        items = consultant.ra_items(ra)
        for it in items:
            r = db.RiskItem(company_id=ctx.cid, site_id=site.id, activity=it["activity"] or "Activity",
                            hazards=it["hazards"], ppe=it["ppe"], source="consultant_ra", ref=it["ref"])
            if approve:
                r.approved_at = db.utcnow()
                r.approved_by = (f"{team}: signed risk assessment {it['ref'].split(' · ')[0]} "
                                 f"({h.get('date') or ''}); loaded by {ctx.user.name}")
            s.add(r)
        title = f"Baseline risk assessment {h.get('ra_no') or ''} {h.get('description') or ''} ({h.get('date') or ''})".strip()
        s.add(db.Doc(company_id=ctx.cid, site_id=site.id, section="risk_assessments", title=title[:200],
                     file=pend["file"], uploaded_by=ctx.user.name))
        st = dict(site.settings or {})
        st.pop("ra_pending", None)
        st["ra"] = {"file": pend["file"], "header": h, "flags": pend["flags"], "roles": consultant.ra_roles(items),
                    "imported_at": db.utcnow().isoformat(timespec="seconds"), "imported_by": ctx.user.name,
                    "approved": approve}
        st["ra_only"] = bool(body.get("ra_only", True))
        site.settings = st
        s.flush()
        _coverage(s, ctx, site)
        return {"ok": True, "items": len(items)}


@app.post("/api/consultant/spec/preview")
def spec_preview(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.MANAGE)
    _limit(ctx)
    name, data, label = _store_upload(ctx, body)
    raw = _ai(ai.spec_extract, label if "." in label else name, data, list(library.APPOINTMENTS),
              [x["key"] for x in library.FILE_SECTIONS], list(library.CHECKLISTS))
    spec = consultant.spec_clean(raw)
    with db.session() as s:
        site = _get(s, db.Site, body.get("site_id", ""), ctx, "Site")
        _settings(site, spec_pending={"file": name, "spec": spec})
    return spec


@app.post("/api/consultant/spec/confirm")
def spec_confirm(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.MANAGE)
    with db.session() as s:
        site = _get(s, db.Site, body.get("site_id", ""), ctx, "Site")
        pend = (site.settings or {}).get("spec_pending")
        if not pend:
            raise HTTPException(400, "Upload the specification again.")
        spec = pend["spec"] | {"file": pend["file"], "imported_at": db.utcnow().isoformat(timespec="seconds"),
                               "imported_by": ctx.user.name}
        s.add(db.Doc(company_id=ctx.cid, site_id=site.id, section="client_spec",
                     title=f"Client H&S specification: {spec.get('project') or site.name} ({spec.get('date') or ''})"[:200],
                     file=pend["file"], uploaded_by=ctx.user.name))
        st = dict(site.settings or {})
        st.pop("spec_pending", None)
        st["spec"] = spec
        site.settings = st
        s.flush()
        _coverage(s, ctx, site)
        return {"ok": True}


@app.post("/api/consultant/coverage")
def recheck_coverage(body: dict = Body(...), ctx: Ctx = Depends(current)):
    ctx.need(*auth.MANAGE)
    _limit(ctx)
    with db.session() as s:
        site = _get(s, db.Site, body.get("site_id", ""), ctx, "Site")
        _coverage(s, ctx, site)
        return (site.settings or {}).get("coverage") or {}


@app.post("/api/consultant/spec/acceptance")
def spec_acceptance(body: dict = Body(default={}), ctx: Ctx = Depends(current)):
    """Issue the specification's acceptance page for AES / wet-ink signatures."""
    ctx.need(*auth.MANAGE)
    with db.session() as s:
        site = _get(s, db.Site, body.get("site_id", ""), ctx, "Site")
        spec = (site.settings or {}).get("spec")
        if not spec:
            raise HTTPException(400, "Load the client's specification first.")
        signers = spec.get("acceptance_signatories") or ["Principal contractor (CEO / s16(2))",
                                                         "Construction manager (CR 8(1))", "Safety officer", "Client"]
        a = db.AesDoc(id=db.new_id(), company_id=ctx.cid, site_id=site.id, kind="spec_acceptance",
                      title=f"Acceptance of the H&S specification: {spec.get('project') or site.name}", signers=signers)
        text = (f"We, the undersigned, received and accept the client's construction health and safety specification for "
                f"{spec.get('project') or site.name}, dated {spec.get('date') or '-'}, prepared by {spec.get('author') or '-'} "
                f"in terms of Construction Regulation 5(1)(b). The principal contractor's health and safety plan is based "
                f"on it, and its requirements form part of every contract with our contractors.")
        a.original_file = files.put(ctx.cid, pdf.aes_document(ctx.company, site, a.title, pdf.text_body(text), signers, a.id),
                                    "application/pdf")
        s.add(a)
        s.flush()
        return aes_d(a)


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
        risks = s.scalars(site_risks_q(ctx.cid, site).order_by(db.RiskItem.ref, db.RiskItem.activity)).all()
        recs = s.scalars(select(db.Record).where(db.Record.site_id == site.id, db.Record.record_date >= d0,
                                                 db.Record.record_date <= d1)
                         .options(selectinload(db.Record.signatures))).all()
        aes_docs = s.scalars(select(db.AesDoc).where(db.AesDoc.company_id == ctx.cid,
                                                     (db.AesDoc.site_id == site.id) | (db.AesDoc.site_id.is_(None)))
                             .order_by(db.AesDoc.created_at)).all()
        contractors = s.scalars(select(db.Contractor).where(db.Contractor.site_id == site.id,
                                                            db.Contractor.active).order_by(db.Contractor.name)).all()
        data = pdf.safety_file(ctx.company, site, date_from=d0, date_to=d1, docs=docs, workers=workers,
                               inducted=_inducted(s, site.id), risks=risks, recs=recs,
                               chain=records.verify(ctx.cid), aes_docs=aes_docs, contractors=contractors)
    name = re.sub(r"[^\w-]+", "-", site.name)[:40]
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="Safety-file-{name}-{d1}.pdf"'})


# ---------------------------------------------------------------- AI drafts

def _site_context(s, ctx: Ctx, site_id: str):
    site = _get(s, db.Site, site_id, ctx, "Site")
    risks = [risk_d(r) for r in s.scalars(site_risks_q(ctx.cid, site))]
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


# ---------------------------------------------------------------- platform admin (SiteBakkie owner)

def _admin_token() -> str:
    if tok := os.getenv("ADMIN_TOKEN"):
        return tok
    f = config.DATA / "admin_token.txt"
    if not f.exists():
        f.write_text(secrets.token_urlsafe(18))
    return f.read_text().strip()


ADMIN_TOKEN = _admin_token()


def admin(x_admin: str = Header(None)) -> None:
    import hmac as _h
    if not x_admin or not _h.compare_digest(x_admin, ADMIN_TOKEN):
        time.sleep(0.5)
        raise HTTPException(401, "Wrong admin code.")


def _admin_user(u: db.User) -> dict:
    return user_d(u) | {"company_id": u.company_id, "created_at": u.created_at.isoformat(timespec="minutes"),
                        "last_login_at": u.last_login_at.isoformat(timespec="minutes") if u.last_login_at else ""}


@app.get("/api/admin/overview", dependencies=[Depends(admin)])
def admin_overview():
    from sqlalchemy import func as F
    week = db.utcnow() - timedelta(days=7)
    with db.session() as s:
        count = lambda m, *w: s.scalar(select(F.count()).select_from(m).where(*w)) or 0
        companies = []
        for c in s.scalars(select(db.Company).order_by(db.Company.created_at.desc())):
            users = s.scalars(select(db.User).where(db.User.company_id == c.id).order_by(db.User.created_at)).all()
            last = s.scalar(select(F.max(db.Record.received_at)).where(db.Record.company_id == c.id))
            companies.append({
                "id": c.id, "name": c.name, "email": c.email, "active": c.active, "invite": c.invite,
                "created_at": c.created_at.isoformat(timespec="minutes"),
                "sites": count(db.Site, db.Site.company_id == c.id),
                "workers": count(db.Worker, db.Worker.company_id == c.id),
                "records": count(db.Record, db.Record.company_id == c.id),
                "records_7d": count(db.Record, db.Record.company_id == c.id, db.Record.received_at >= week),
                "last_activity": last.isoformat(timespec="minutes") if last else "",
                "users": [_admin_user(u) for u in users]})
        invites = [{"code": i.code, "label": i.label, "active": i.active, "uses": i.uses,
                    "created_at": i.created_at.date().isoformat()}
                   for i in s.scalars(select(db.InviteCode).order_by(db.InviteCode.created_at))]
        env_codes = sorted(SIGNUP_CODE - {i["code"] for i in invites})
        return {"totals": {"companies": len(companies), "users": count(db.User), "sites": count(db.Site),
                           "workers": count(db.Worker), "records": count(db.Record),
                           "records_7d": count(db.Record, db.Record.received_at >= week)},
                "companies": companies, "invites": invites, "env_invites": env_codes, "roles": auth.ROLES}


@app.post("/api/admin/invites", dependencies=[Depends(admin)])
def admin_add_invite(body: dict = Body(...)):
    code = re.sub(r"[^a-z0-9-]", "", _s(body.get("code"), 60).lower()) or f"{re.sub(r'[^a-z]', '', _s(body.get('label')).lower())[:12] or 'pilot'}-{secrets.token_hex(2)}"
    with db.session() as s:
        if s.get(db.InviteCode, code):
            raise HTTPException(409, "That code exists.")
        s.add(db.InviteCode(code=code, label=_s(body.get("label"))))
    return {"code": code}


@app.put("/api/admin/invites/{code}", dependencies=[Depends(admin)])
def admin_update_invite(code: str, body: dict = Body(...)):
    with db.session() as s:
        i = s.get(db.InviteCode, code)
        if not i:
            raise HTTPException(404, "Unknown code.")
        if "active" in body:
            i.active = bool(body["active"])
        if "label" in body:
            i.label = _s(body["label"])
    return {"ok": True}


@app.put("/api/admin/companies/{cid}", dependencies=[Depends(admin)])
def admin_update_company(cid: str, body: dict = Body(...)):
    with db.session() as s:
        c = s.get(db.Company, cid)
        if not c:
            raise HTTPException(404, "Unknown company.")
        if "active" in body:
            c.active = bool(body["active"])
            if not c.active:
                for u in s.scalars(select(db.User).where(db.User.company_id == c.id)):
                    auth.end_all(s, u.id)
        if "name" in body and _s(body["name"]):
            c.name = _s(body["name"])
    return {"ok": True}


@app.post("/api/admin/users", dependencies=[Depends(admin)])
def admin_add_user(body: dict = Body(...)):
    email, role = _s(body.get("email")).lower(), body.get("role", "owner")
    if "@" not in email or not _s(body.get("name")) or role not in auth.ROLES:
        raise HTTPException(400, "Give the name, email and role.")
    temp = secrets.token_urlsafe(6)
    with db.session() as s:
        if not s.get(db.Company, body.get("company_id", "")):
            raise HTTPException(404, "Unknown company.")
        if s.scalar(select(db.User).where(db.User.email == email)):
            raise HTTPException(409, "That email already has a login.")
        u = db.User(company_id=body["company_id"], email=email, name=_s(body["name"]), role=role,
                    pw_hash=auth.hash_pw(temp))
        s.add(u)
        s.flush()
        return _admin_user(u) | {"temp_password": temp}


@app.put("/api/admin/users/{uid}", dependencies=[Depends(admin)])
def admin_update_user(uid: str, body: dict = Body(...)):
    with db.session() as s:
        u = s.get(db.User, uid)
        if not u:
            raise HTTPException(404, "Unknown user.")
        out = {}
        if "active" in body:
            u.active = bool(body["active"])
            if not u.active:
                auth.end_all(s, u.id)
        if body.get("role") in auth.ROLES:
            u.role = body["role"]
        if "email" in body and "@" in _s(body["email"]):
            new = _s(body["email"]).lower()
            if new != u.email and s.scalar(select(db.User).where(db.User.email == new)):
                raise HTTPException(409, "That email already has a login.")
            u.email = new
        if body.get("reset_password"):
            temp = secrets.token_urlsafe(6)
            u.pw_hash = auth.hash_pw(temp)
            auth.end_all(s, u.id)
            out["temp_password"] = temp
        return _admin_user(u) | out


# ---------------------------------------------------------------- static PWA

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app.html")


app.mount("/", StaticFiles(directory=config.WEB, html=True), name="web")
