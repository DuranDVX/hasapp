"""Passwords, login sessions and roles."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import Header, HTTPException

from . import config, db

ROLES = {
    "owner": "Owner",
    "safety": "Safety officer",
    "foreman": "Foreman / site manager",
    "auditor": "Auditor (read only)",
}
MANAGE = ("owner", "safety")                    # sites, library, documents, plant
WRITE = ("owner", "safety", "foreman")          # site records and workers
_ITER = 200_000


def hash_pw(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), _ITER)
    return f"pbkdf2${_ITER}${salt}${dk.hex()}"


def check_pw(pw: str, stored: str) -> bool:
    try:
        _, it, salt, h = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), int(it))
    return hmac.compare_digest(dk.hex(), h)


def valid_pw(pw: str) -> None:
    if len(pw or "") < 8:
        raise HTTPException(400, "Use a password of 8 characters or more.")


def _th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(s, user: db.User) -> str:
    token = secrets.token_urlsafe(32)
    s.add(db.Session(token_hash=_th(token), user_id=user.id,
                     expires_at=db.utcnow() + timedelta(days=config.SESSION_DAYS)))
    return token


def end_session(s, token: str) -> None:
    s.query(db.Session).filter_by(token_hash=_th(token)).delete()


def end_all(s, user_id: str) -> None:
    s.query(db.Session).filter_by(user_id=user_id).delete()


class Ctx:
    """The logged-in user for one request."""

    def __init__(self, user: db.User, company: db.Company):
        self.user, self.company = user, company
        self.uid, self.cid, self.role = user.id, company.id, user.role

    def need(self, *roles: str) -> None:
        if self.role not in roles:
            raise HTTPException(403, "Your role cannot do this.")


def current(x_token: str = Header(None)) -> Ctx:
    if not x_token:
        raise HTTPException(401, "Please log in.")
    with db.session() as s:
        sess = s.get(db.Session, _th(x_token))
        if not sess or sess.expires_at < db.utcnow():
            raise HTTPException(401, "Please log in again.")
        user = s.get(db.User, sess.user_id)
        if not user or not user.active:
            raise HTTPException(401, "This login is switched off.")
        company = s.get(db.Company, user.company_id)
        if not company.active:
            raise HTTPException(401, "This company's account is switched off. Contact SiteBakkie.")
        return Ctx(user, company)
