"""File store: photos, signatures, audio and documents.

Each file is stored once under its SHA-256 name, inside the company folder.
The name proves the content, so the record hash covers the file through it.
"""
import base64
import binascii
import hashlib
import hmac
import io
import re
import secrets
import time

from PIL import Image

from . import config

TYPES = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
    "application/pdf": ".pdf",
    "audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/mpeg": ".mp3",
    "audio/wav": ".wav", "audio/x-m4a": ".m4a", "audio/aac": ".aac",
}
EXT_TYPES = {v: k for k, v in TYPES.items()} | {".jpeg": "image/jpeg"}
MAX_BYTES = 20 * 1024 * 1024
NAME = re.compile(r"^[0-9a-f]{16}/[0-9a-f]{64}\.[a-z0-9]{2,5}$")
DATA_URL = re.compile(r"^data:([\w/+.-]+)(?:;[\w=-]+)*;base64,(.*)$", re.S)


def _secret() -> bytes:
    f = config.DATA / "secret.key"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip().encode()


SECRET = config.SECRET_KEY.encode() or _secret()


def put(company_id: str, data: bytes, mime: str) -> str:
    """Store bytes; return the relative name company/sha.ext."""
    if len(data) > MAX_BYTES:
        raise ValueError("File is too big (max 20 MB).")
    ext = TYPES.get(mime.split(";")[0].strip().lower())
    if not ext:
        raise ValueError(f"Unsupported file type: {mime}")
    if ext in (".jpg", ".png", ".webp"):
        data, ext = _shrink(data, ext)
    sha = hashlib.sha256(data).hexdigest()
    name = f"{company_id}/{sha}{ext}"
    path = config.FILES / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    return name


def _shrink(data: bytes, ext: str) -> tuple[bytes, str]:
    """Cap photos at 1600 px. Signatures (PNG with alpha) keep their format."""
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        raise ValueError("That image could not be read.")
    if ext == ".png" and im.mode in ("RGBA", "LA", "P"):
        return data, ext
    if max(im.size) <= 1600 and ext == ".jpg":
        return data, ext
    im.thumbnail((1600, 1600))
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=82)
    return out.getvalue(), ".jpg"


def put_data_url(company_id: str, value: str) -> str:
    m = DATA_URL.match(value or "")
    if not m:
        raise ValueError("Bad file data.")
    try:
        data = base64.b64decode(m.group(2), validate=False)
    except (binascii.Error, ValueError):
        raise ValueError("Bad file data.")
    return put(company_id, data, m.group(1))


def owned(company_id: str, name: str) -> bool:
    return bool(name) and NAME.match(name) is not None and name.startswith(company_id + "/") \
        and (config.FILES / name).exists()


def path(name: str):
    if not NAME.match(name or ""):
        raise ValueError("Bad file name.")
    return config.FILES / name


def read(name: str) -> bytes:
    return path(name).read_bytes()


def mime(name: str) -> str:
    return EXT_TYPES.get("." + name.rsplit(".", 1)[-1], "application/octet-stream")


def sign(name: str, ttl: int = 6 * 3600) -> str:
    """A link to one file that expires. <img> tags cannot send the login header."""
    if not name:
        return ""
    exp = int(time.time()) + ttl
    sig = hmac.new(SECRET, f"{name}|{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"/api/f/{name}?exp={exp}&sig={sig}"


def check(name: str, exp: int, sig: str) -> bool:
    if exp < time.time():
        return False
    good = hmac.new(SECRET, f"{name}|{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(good, sig or "")
