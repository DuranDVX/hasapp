"""Fill the video demo site (port 8510) with realistic records. Fictional people only.

Run against a server started on a separate HAS_DATA / DATABASE_URL, never production:
    .venv/bin/python brand/video/seed.py
"""
import base64
import io
import json
import math
import random
import sys
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import library  # noqa: E402

BASE = "http://127.0.0.1:8510"
TODAY = date.today()
random.seed(4)


def call(path, body=None, token=None, method=None):
    req = urllib.request.Request(BASE + path, method=method or ("POST" if body is not None else "GET"),
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"X-Token": token} if token else {})})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read() or b"{}")


def signature() -> str:
    """A hand-written looking squiggle."""
    im = Image.new("RGBA", (420, 140), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x, y, pts = 20, 80, []
    for i in range(70):
        x += random.uniform(3, 7)
        y = 75 + 28 * math.sin(i / random.uniform(2.2, 3.4)) + random.uniform(-6, 6)
        pts.append((x, y))
    d.line(pts, fill=(18, 36, 51, 255), width=4, joint="curve")
    d.line([(pts[5][0], 110), (pts[-10][0] + 20, 104)], fill=(18, 36, 51, 255), width=3)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def sig(worker=None, user=None, role="worker", when=None):
    d = {"image": signature(), "role": role, "signed_at": (when or datetime.now()).astimezone().isoformat(timespec="seconds"),
         "lat": -34.0527, "lng": 23.3716}
    if worker:
        d["worker_id"] = worker
    if user:
        d["user_id"] = user
    return d


def record(tok, site, kind, payload, sigs, day=TODAY):
    return call("/api/records", {"client_id": uuid.uuid4().hex, "site_id": site, "kind": kind, "record_date": day.isoformat(),
                                 "device_time": datetime.now().astimezone().isoformat(timespec="seconds"),
                                 "lat": -34.0527, "lng": 23.3716, "payload": payload, "signatures": sigs}, tok)


def main():
    tok = call("/api/login", {"email": "demo@example.com", "password": "demo-pass-1"})["token"]
    me = call("/api/me", token=tok)
    uid, site = me["user"]["id"], me["sites"][0]["id"]
    call(f"/api/sites/{site}", {
        "features": {"excavations": True, "scaffolding": True, "work_at_height": True, "mobile_plant": True,
                     "temporary_power": True, "concrete": True, "subcontractors": True},
        "scope": "New double-storey house, 320 m²: foundations, brickwork, concrete slab, roof and services.",
        "spec_provided": False, "facilities": {"toilets": "2", "showers": "1"},
        "consultants": [{"name": "Lindiwe Mabaso", "firm": "Garden Route Safety Consulting", "reg": "CHSA/0412/2024",
                         "phone": "044 382 0000", "email": "lindiwe@example.co.za"}],
        "contacts": [{"role": "Construction manager", "name": "Demo Owner", "phone": "082 555 0101"},
                     {"role": "Site supervisor", "name": "Piet Foreman", "phone": "082 555 0102"},
                     {"role": "First aider", "name": "Thabo Mokoena", "phone": "072 345 6781"}]}, tok, "PUT")
    for r in call(f"/api/risks?site_id={site}", token=tok):
        if not r["approved"]:
            call(f"/api/risks/{r['id']}/approve", {}, tok)
    risks = call(f"/api/risks?site_id={site}", token=tok)
    workers = call(f"/api/workers?site_id={site}", token=tok)
    plant = call(f"/api/plant?site_id={site}", token=tok)
    w = {x["name"].split()[0]: x["id"] for x in workers}

    # inductions, two weeks ago
    for x in workers:
        record(tok, site, "induction", {"worker_id": x["id"], "consent": True},
               [sig(worker=x["id"]), sig(user=uid, role="inductor")], TODAY - timedelta(days=14))
    # appointments
    appts = [("construction_manager", {"user_id": uid}), ("construction_supervisor", {"worker_id": w["Sipho"]}),
             ("risk_assessor", {"user_id": uid}), ("first_aider", {"worker_id": w["Thabo"]}),
             ("excavation", {"worker_id": w["Sipho"]}), ("scaffold", {"worker_id": w["Lwazi"]}),
             ("fall_protection", {"user_id": uid}), ("operator", {"worker_id": w["Johan"]})]
    for key, who in appts:
        try:
            record(tok, site, "appointment", {"type": key, "appointee": who, "start_date": (TODAY - timedelta(days=14)).isoformat()},
                   [sig(user=uid, role="appointer"), sig(**({"worker": who["worker_id"]} if "worker_id" in who else {"user": who["user_id"]}), role="appointee")],
                   TODAY - timedelta(days=14))
        except Exception as e:
            print("appointment", key, "skipped:", e)
    # plant pre-use checks and site inspections today
    by_tpl = {p["template"]: p for p in plant}
    for tpl, who in (("earthmoving", w["Johan"]), ("mixer", w["Lwazi"]), ("vehicle", w["Sipho"])):
        n = len(library.CHECKLISTS[tpl]["items"])
        record(tok, site, "check", {"template": tpl, "plant_id": by_tpl[tpl]["id"], "answers": [{"answer": "ok"}] * n},
               [sig(worker=who, role="operator")])
    for tpl in ("excavation", "electrical_db", "fire_extinguisher", "first_aid", "ladder"):
        n = len(library.CHECKLISTS[tpl]["items"])
        record(tok, site, "check", {"template": tpl, "answers": [{"answer": "ok"}] * n, "location": "Site"},
               [sig(user=uid, role="inspector")])
    # today's task sheet
    pick = lambda words: [r["id"] for r in risks if any(k in r["activity"].lower() for k in words)][:2]
    tasks = [{"description": "Brickwork, east wall first floor", "location": "East wall", "risk_item_ids": pick(["brick", "scaffold"]),
              "worker_ids": [w["Sipho"], w["Lwazi"]], "plant_ids": []},
             {"description": "Dig sewer trench, 1.4 m deep", "location": "North boundary", "risk_item_ids": pick(["excavat", "trench"]),
              "worker_ids": [w["Johan"], w["Thabo"]], "plant_ids": [by_tpl["earthmoving"]["id"]]}]
    record(tok, site, "task_sheet", {"tasks": tasks, "notes": "Windy after 14:00"},
           [sig(worker=x) for x in (w["Sipho"], w["Lwazi"], w["Johan"], w["Thabo"])] + [sig(user=uid, role="supervisor")])
    # this week's toolbox talk
    record(tok, site, "toolbox_talk", {"topic": "Working safely next to open trenches", "title": "Open trenches",
                                       "language": "en", "text": "Stay back from the edge. Use the ladder. Report cracks.",
                                       "key_points": ["Barricade every trench", "Spoil 1 m from the edge", "Inspect before each shift"]},
           [sig(worker=x) for x in w.values()] + [sig(user=uid, role="presenter")], TODAY - timedelta(days=2))
    print("seeded:", len(workers), "workers,", len(appts), "appointments, checks, task sheet, toolbox talk")


if __name__ == "__main__":
    main()
