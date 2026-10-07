"""Privacy-friendly visit statistics (the same module as QuoteBakkie's; change both together). No cookies, no stored IP addresses:
a visitor is a hash of (daily secret, IP, browser) that changes every day."""
import hashlib
import json
import re
import secrets
import threading
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from . import config

SAST = ZoneInfo("Africa/Johannesburg")
DIR = config.DATA / "analytics"
DIR.mkdir(parents=True, exist_ok=True)
KEEP_DAYS = 400
_lock = threading.Lock()
_salt = {"day": None, "value": ""}

PAGES = {"/": "Home", "/index.html": "Home", "/terms.html": "Terms",
         "/privacy.html": "Privacy", "/app.html": "App", "/app": "App"}
BOT = re.compile(r"bot|crawl|spider|slurp|facebookexternalhit|whatsapp/|preview|curl|wget|python|"
                 r"headless|lighthouse|monitor|uptime|bun/|go-http|httpclient|scanner", re.I)


def _today() -> date:
    return datetime.now(SAST).date()


def _daily_salt() -> str:
    d = _today().isoformat()
    if _salt["day"] != d:
        f = DIR / ".salt"
        try:
            day, value = f.read_text().split(":", 1)
        except (OSError, ValueError):
            day, value = "", ""
        if day != d:  # new day: new secret, so yesterday's visitor ids cannot be linked to today's
            value = secrets.token_hex(16)
            f.write_text(f"{d}:{value}")
        _salt.update(day=d, value=value)
    return _salt["value"]


def _source(ref: str, query: str, host: str) -> str:
    q = parse_qs(query)
    if q.get("utm_source"):
        return q["utm_source"][0][:30].lower()
    if q.get("fbclid"):
        return "facebook"
    r = urlparse(ref).netloc.lower()
    if not r or host in r:
        return "direct"
    for key, name in (("facebook", "facebook"), ("fb.", "facebook"), ("instagram", "instagram"),
                      ("whatsapp", "whatsapp"), ("wa.me", "whatsapp"), ("google", "google"),
                      ("bing", "bing"), ("linkedin", "linkedin"), ("lnkd", "linkedin"),
                      ("t.co", "x"), ("twitter", "x"), ("tiktok", "tiktok"), ("youtube", "youtube")):
        if key in r:
            return name
    return r.removeprefix("www.")[:40]


def record(path: str, query: str, ip: str, ua: str, ref: str, host: str, event: str = "view") -> None:
    if event == "view" and (path not in PAGES or not ua or BOT.search(ua)):
        return
    vid = hashlib.sha256(f"{_daily_salt()}|{ip}|{ua}".encode()).hexdigest()[:16]
    mobile = bool(re.search(r"iphone|android|mobile|ipad", ua or "", re.I))
    row = {"t": datetime.now(SAST).isoformat(timespec="seconds"), "e": event,
           "p": PAGES.get(path, path), "v": vid, "s": _source(ref, query, host),
           "d": "phone" if mobile else "computer"}
    with _lock, open(DIR / f"{_today()}.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")


def _rows(days: int):
    today = _today()
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        f = DIR / f"{d}.jsonl"
        rows = []
        if f.exists():
            for line in f.read_text().splitlines():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
        yield d, rows


def stats(days: int = 30) -> dict:
    per_day, sources, pages, devices, recent = [], Counter(), Counter(), Counter(), []
    visitors_total, signups_total = 0, 0
    for d, rows in _rows(days):
        views = [r for r in rows if r["e"] == "view"]
        vis = {r["v"] for r in views}
        sign = sum(1 for r in rows if r["e"] == "signup")
        per_day.append({"day": d.isoformat(), "visitors": len(vis), "views": len(views), "signups": sign})
        visitors_total += len(vis)
        signups_total += sign
        first_by_visitor = {}
        for r in views:
            pages[r["p"]] += 1
            first_by_visitor.setdefault(r["v"], r)
        for r in first_by_visitor.values():   # count each visitor once per day
            sources[r["s"]] += 1
            devices[r["d"]] += 1
        recent.extend(rows)
    recent = sorted(recent, key=lambda r: r["t"], reverse=True)[:60]
    last = lambda n: sum(x["visitors"] for x in per_day[-n:])
    return {"days": per_day, "today": per_day[-1]["visitors"], "week": last(7), "month": visitors_total,
            "signups": signups_total,
            "conversion": round(100 * signups_total / visitors_total, 1) if visitors_total else 0,
            "sources": sources.most_common(12), "pages": pages.most_common(8),
            "devices": devices.most_common(), "recent": recent}


def purge() -> None:
    cutoff = _today() - timedelta(days=KEEP_DAYS)
    for f in DIR.glob("*.jsonl"):
        try:
            if date.fromisoformat(f.stem) < cutoff:
                f.unlink()
        except ValueError:
            pass
