"""API tests. The AI and speech steps are mocked; everything else is real."""
import base64
import io
import os
import sys
import tempfile
import uuid

TMP = tempfile.mkdtemp()
os.environ["HAS_DATA"] = TMP
os.environ["DATABASE_URL"] = f"sqlite:///{TMP}/test.db"
os.environ["HAS_WARM_STT"] = "0"
os.environ["CRON_TOKEN"] = "cron-test"
os.environ["HAS_SIGNUP_CODE"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from app import ai, db, library, server  # noqa: E402

client = TestClient(server.app)
client.__enter__()   # run startup (creates tables)


def png() -> str:
    im = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
    for x in range(10, 110):
        im.putpixel((x, 20), (0, 0, 0, 255))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def jpg() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (200, 120, 40)).save(buf, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def signup(company="Acme Builders", email=None):
    email = email or f"{uuid.uuid4().hex[:8]}@test.co"
    r = client.post("/api/signup", json={"company": company, "name": "Owner One", "email": email,
                                         "password": "longenough"})
    assert r.status_code == 200, r.text
    return {"X-Token": r.json()["token"]}


@pytest.fixture()
def co():
    h = signup()
    site = client.post("/api/sites", json={"name": "Erf 123 Plett"}, headers=h).json()
    w1 = client.post("/api/workers", json={"name": "Sipho Dlamini", "trade": "Bricklayer",
                                           "site_id": site["id"], "photo": jpg()}, headers=h).json()
    w2 = client.post("/api/workers", json={"name": "Johan Botha", "trade": "TLB operator",
                                           "site_id": site["id"]}, headers=h).json()
    tlb = client.post("/api/plant", json={"name": "TLB 1", "template": "earthmoving", "ident": "CA 123",
                                          "site_id": site["id"]}, headers=h).json()
    risks = client.get(f"/api/risks?site_id={site['id']}", headers=h).json()
    return {"h": h, "site": site, "w1": w1, "w2": w2, "tlb": tlb, "risks": risks}


def sig(worker=None, user=None, role="worker"):
    d = {"image": png(), "role": role, "signed_at": "2026-10-06T07:05:00+02:00", "lat": -34.05, "lng": 23.37}
    if worker:
        d["worker_id"] = worker
    if user:
        d["user_id"] = user
    return d


def me(h):
    return client.get("/api/me", headers=h).json()


def task_sheet(co, client_id=None, risk_ids=None):
    risk_ids = risk_ids or [co["risks"][0]["id"]]
    return {"client_id": client_id or uuid.uuid4().hex, "site_id": co["site"]["id"], "kind": "task_sheet",
            "record_date": "2026-10-06", "device_time": "2026-10-06T07:00:00+02:00", "lat": -34.05, "lng": 23.37,
            "payload": {"tasks": [{"description": "Brickwork east wall", "location": "East wall",
                                   "risk_item_ids": risk_ids, "worker_ids": [co["w1"]["id"]], "plant_ids": [],
                                   # A forged control from the device must be ignored:
                                   "risks": [{"activity": "FAKE", "hazards": []}]}],
                        "notes": "Windy"},
            "signatures": [sig(worker=co["w1"]["id"]), sig(user=me(co["h"])["user"]["id"], role="supervisor")]}


# ---------------------------------------------------------------- auth and tenancy

def test_signup_seeds_unapproved_starter_library(co):
    assert len(co["risks"]) >= 15
    assert all(not r["approved"] and r["source"] == "starter" for r in co["risks"])


def test_login_and_wrong_password():
    email = f"{uuid.uuid4().hex[:8]}@test.co"
    signup(email=email)
    assert client.post("/api/login", json={"email": email, "password": "longenough"}).status_code == 200
    assert client.post("/api/login", json={"email": email, "password": "nope-nope"}).status_code == 401


def test_other_company_cannot_see_or_use_data(co):
    other = signup("Rival Co")
    assert client.get(f"/api/workers?site_id={co['site']['id']}", headers=other).status_code == 404
    assert client.get(f"/api/sync?site_id={co['site']['id']}", headers=other).status_code == 404
    body = task_sheet(co)
    assert client.post("/api/records", json=body, headers=other).status_code == 404
    rid = client.post("/api/records", json=task_sheet(co), headers=co["h"]).json()["id"]
    assert client.get(f"/api/records/{rid}", headers=other).status_code == 404
    assert client.get(f"/api/plant/by-token/{co['tlb']['qr_token']}", headers=other).status_code == 404


def test_auditor_is_read_only(co):
    r = client.post("/api/users", json={"name": "Agent Smith", "email": f"{uuid.uuid4().hex[:6]}@agent.co",
                                        "role": "auditor"}, headers=co["h"]).json()
    tok = client.post("/api/login", json={"email": r["email"], "password": r["temp_password"]}).json()["token"]
    h = {"X-Token": tok}
    assert client.post("/api/records", json=task_sheet(co), headers=h).status_code == 403
    workers = client.get(f"/api/workers?site_id={co['site']['id']}", headers=h)
    assert workers.status_code == 200


# ---------------------------------------------------------------- records

def test_task_sheet_uses_server_risk_text_and_flags_unapproved(co):
    r = client.post("/api/records", json=task_sheet(co), headers=co["h"])
    assert r.status_code == 200, r.text
    rec = client.get(f"/api/records/{r.json()['id']}", headers=co["h"]).json()
    task = rec["payload"]["tasks"][0]
    assert task["risks"][0]["activity"] == co["risks"][0]["activity"]     # not "FAKE"
    assert task["assessed"] is False                                       # starter item not approved
    assert task["workers"] == [{"id": co["w1"]["id"], "name": "Sipho Dlamini"}]
    assert len(rec["signatures"]) == 2 and rec["signatures"][0]["image_url"].startswith("/api/f/")
    assert "needs review" in rec["summary"]


def test_record_is_idempotent_on_client_id(co):
    body = task_sheet(co, client_id="device-abc-1")
    a = client.post("/api/records", json=body, headers=co["h"]).json()
    b = client.post("/api/records", json=body, headers=co["h"]).json()
    assert a["id"] == b["id"]


def test_unknown_risk_ids_are_dropped(co):
    body = task_sheet(co, risk_ids=["doesnotexist"])
    rec_id = client.post("/api/records", json=body, headers=co["h"]).json()["id"]
    rec = client.get(f"/api/records/{rec_id}", headers=co["h"]).json()
    assert rec["payload"]["tasks"][0]["risks"] == []
    assert rec["payload"]["tasks"][0]["assessed"] is False


def test_approval_needs_sacpcmp_number(co):
    rid = co["risks"][0]["id"]
    assert client.post(f"/api/risks/{rid}/approve", headers=co["h"]).status_code == 400
    client.put("/api/profile", json={"sacpcmp_no": "CHSO/123/2024"}, headers=co["h"])
    r = client.post(f"/api/risks/{rid}/approve", headers=co["h"]).json()
    assert r["approved"] and "CHSO/123/2024" in r["approved_by"]
    body = task_sheet(co, risk_ids=[rid])
    rec_id = client.post("/api/records", json=body, headers=co["h"]).json()["id"]
    assert client.get(f"/api/records/{rec_id}", headers=co["h"]).json()["payload"]["tasks"][0]["assessed"]
    # An edit clears the approval.
    r = client.put(f"/api/risks/{rid}", json={"ppe": ["Hard hat"]}, headers=co["h"]).json()
    assert not r["approved"]


def test_signature_required(co):
    body = task_sheet(co)
    body["signatures"][0]["image"] = ""
    assert client.post("/api/records", json=body, headers=co["h"]).status_code == 400


def test_plant_check_critical_defect_fails(co):
    tpl = server.library.CHECKLISTS["earthmoving"]["items"]
    answers = [{"answer": "ok"} for _ in tpl]
    answers[1] = {"answer": "defect", "note": "Park brake weak", "photo": jpg()}   # brakes: critical
    body = {"client_id": uuid.uuid4().hex, "site_id": co["site"]["id"], "kind": "check",
            "record_date": "2026-10-06", "payload": {"template": "earthmoving", "plant_id": co["tlb"]["id"],
                                                     "answers": answers},
            "signatures": [sig(worker=co["w2"]["id"], role="operator")]}
    r = client.post("/api/records", json=body, headers=co["h"])
    assert r.status_code == 200, r.text
    rec = client.get(f"/api/records/{r.json()['id']}", headers=co["h"]).json()
    assert rec["payload"]["result"] == "fail"
    assert rec["payload"]["items"][1]["photo"]["url"]
    dash = client.get(f"/api/dashboard?site_id={co['site']['id']}", headers=co["h"]).json()
    assert dash["date"]


def test_check_must_answer_all(co):
    body = {"client_id": uuid.uuid4().hex, "site_id": co["site"]["id"], "kind": "check",
            "record_date": "2026-10-06", "payload": {"template": "ladder", "answers": [{"answer": "ok"}]},
            "signatures": [sig(worker=co["w2"]["id"])]}
    assert client.post("/api/records", json=body, headers=co["h"]).status_code == 400


def test_induction_adds_worker_to_site_and_marks_inducted(co):
    w = client.post("/api/workers", json={"name": "New Guy"}, headers=co["h"]).json()
    body = {"client_id": uuid.uuid4().hex, "site_id": co["site"]["id"], "kind": "induction",
            "record_date": "2026-10-06", "payload": {"worker_id": w["id"], "consent": True},
            "signatures": [sig(worker=w["id"]), sig(user=me(co["h"])["user"]["id"], role="inductor")]}
    assert client.post("/api/records", json=body, headers=co["h"]).status_code == 200
    ws = client.get(f"/api/workers?site_id={co['site']['id']}", headers=co["h"]).json()
    assert next(x for x in ws if x["id"] == w["id"])["inducted"] is True


# ---------------------------------------------------------------- integrity

def test_hash_chain_detects_tampering(co):
    for _ in range(3):
        client.post("/api/records", json=task_sheet(co), headers=co["h"])
    v = client.get("/api/verify", headers=co["h"]).json()
    assert v["ok"] and v["records"] >= 3
    with db.session() as s:
        rec = s.query(db.Record).filter_by(company_id=me(co["h"])["company"]["id"]).order_by(db.Record.seq).first()
        rec.payload = rec.payload | {"notes": "edited later"}
    v = client.get("/api/verify", headers=co["h"]).json()
    assert not v["ok"] and v["broken"]


def test_file_links_are_signed(co):
    url = co["w1"]["photo_url"]
    assert client.get(url).status_code == 200
    assert client.get(url.replace("sig=", "sig=x")).status_code == 403


# ---------------------------------------------------------------- PDFs

def test_record_pdf_and_safety_file(co):
    rid = client.post("/api/records", json=task_sheet(co), headers=co["h"]).json()["id"]
    r = client.get(f"/api/records/{rid}/pdf", headers=co["h"])
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    client.post("/api/docs", json={"section": "company", "title": "COID letter", "expires": "2026-10-20",
                                   "file": jpg()}, headers=co["h"])
    r = client.get(f"/api/sites/{co['site']['id']}/file.pdf", headers=co["h"])
    assert r.status_code == 200, r.text
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "Health and safety file" in text and "Daily task sheets" in text and "chain intact" in text


# ---------------------------------------------------------------- AI (mocked)

def test_ai_task_sheet_drops_invented_ids(co, monkeypatch):
    real = co["risks"][0]["id"]

    def fake(transcript, risks, workers, plant):
        return {"tasks": [{"description": "Brickwork", "location": "", "risk_item_ids": [real, "invented"],
                           "worker_ids": [co["w1"]["id"], "ghost"], "plant_ids": []},
                          {"description": "Paint the moon", "location": "", "risk_item_ids": ["nope"],
                           "worker_ids": [], "plant_ids": []}],
                "unmatched": [], "notes": "", "questions": []}
    monkeypatch.setattr(ai, "task_sheet", fake)
    r = client.post("/api/ai/task-sheet", data={"site_id": co["site"]["id"], "text": "brickwork today"},
                    headers=co["h"]).json()
    assert r["draft"]["tasks"][0]["risk_item_ids"] == [real]
    assert r["draft"]["tasks"][0]["worker_ids"] == [co["w1"]["id"]]
    assert len(r["draft"]["tasks"]) == 1
    assert r["draft"]["unmatched"][0]["description"] == "Paint the moon"


def test_cron_expiry_requires_token():
    assert client.post("/api/cron/expiry").status_code == 403
    assert client.post("/api/cron/expiry", headers={"X-Cron-Token": "cron-test"}).status_code == 200


def test_invite_code_when_set(monkeypatch):
    monkeypatch.setattr(server, "SIGNUP_CODE", {"pilot", "john-ab12"})
    body = {"company": "X", "name": "Y", "email": f"{uuid.uuid4().hex[:8]}@test.co", "password": "longenough"}
    assert client.post("/api/signup", json=body).status_code == 403
    assert client.post("/api/signup", json=body | {"invite": "pilot"}).status_code == 200
    body["email"] = f"{uuid.uuid4().hex[:8]}@test.co"
    assert client.post("/api/signup", json=body | {"invite": "John-AB12 "}).status_code == 200


def test_sync_lists_todays_risk_ids(co):
    client.post("/api/records", json=task_sheet(co) | {"record_date": server.today().isoformat()}, headers=co["h"])
    d = client.get(f"/api/sync?site_id={co['site']['id']}", headers=co["h"]).json()
    assert co["risks"][0]["id"] in d["today_risk_ids"]


def test_bare_domain_redirects_to_www(monkeypatch):
    monkeypatch.setattr(server, "CANONICAL", "www.sitebakkie.co.za")
    r = client.get("/app.html?x=1", headers={"host": "sitebakkie.co.za"}, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "https://www.sitebakkie.co.za/app.html?x=1"
    assert client.get("/api/health", headers={"host": "www.sitebakkie.co.za"}).status_code == 200


def test_platform_admin():
    try:
        _platform_admin()
    finally:   # later tests sign up without an invite
        with db.session() as s:
            s.query(db.InviteCode).delete()


def _platform_admin():
    a = {"X-Admin": server.ADMIN_TOKEN}
    assert client.get("/api/admin/overview").status_code == 401
    assert client.get("/api/admin/overview", headers={"X-Admin": "wrong"}).status_code == 401
    code = client.post("/api/admin/invites", json={"label": "Benno"}, headers=a).json()["code"]
    assert code.startswith("benno-")
    email = f"{uuid.uuid4().hex[:8]}@test.co"
    r = client.post("/api/signup", json={"company": "Benno Bou", "name": "Benno", "email": email,
                                         "password": "longenough", "invite": code})
    assert r.status_code == 200
    ov = client.get("/api/admin/overview", headers=a).json()
    co_ = next(c for c in ov["companies"] if c["name"] == "Benno Bou")
    assert co_["invite"] == code and next(i for i in ov["invites"] if i["code"] == code)["uses"] == 1
    uid = co_["users"][0]["id"]
    temp = client.put(f"/api/admin/users/{uid}", json={"reset_password": True}, headers=a).json()["temp_password"]
    assert client.post("/api/login", json={"email": email, "password": "longenough"}).status_code == 401
    tok = client.post("/api/login", json={"email": email, "password": temp}).json()["token"]
    assert client.get("/api/me", headers={"X-Token": tok}).status_code == 200
    # Switching the company off logs everyone out and blocks login
    client.put(f"/api/admin/companies/{co_['id']}", json={"active": False}, headers=a)
    assert client.get("/api/me", headers={"X-Token": tok}).status_code == 401
    assert client.post("/api/login", json={"email": email, "password": temp}).status_code == 401
    r = client.post("/api/admin/companies", json={"name": "JB Test", "owner": "Jo", "email": "Jo@JBtest.co"}, headers=a).json()
    assert r["email"] == "jo@jbtest.co"
    assert client.post("/api/login", json={"email": "jo@jbtest.co", "password": r["temp_password"]}).status_code == 200
    assert client.post("/api/admin/companies", json={"name": "Again", "owner": "Jo", "email": "jo@jbtest.co"}, headers=a).status_code == 409
    client.put(f"/api/admin/invites/{code}", json={"active": False}, headers=a)
    r = client.post("/api/signup", json={"company": "X", "name": "Y", "email": f"{uuid.uuid4().hex[:8]}@t.co",
                                         "password": "longenough", "invite": code})
    assert r.status_code == 403


def test_forgot_and_reset_password():
    from datetime import timedelta

    from sqlalchemy import select

    from app import auth
    email = f"reset-{uuid.uuid4().hex[:6]}@test.co"
    r = client.post("/api/signup", json={"company": "Reset Co", "name": "Rita", "email": email, "password": "first-pass-1"})
    assert r.status_code == 200, r.text
    assert client.post("/api/password/forgot", json={"email": "nobody@example.com"}).json() == {"ok": True}
    assert client.post("/api/password/forgot", json={"email": email.upper()}).json() == {"ok": True}
    # The token goes out by email only; make a known one for the test.
    with db.session() as s:
        u = s.scalar(select(db.User).where(db.User.email == email))
        assert s.scalar(select(db.PasswordReset).where(db.PasswordReset.user_id == u.id))   # the forgot call made one
        s.add(db.PasswordReset(token_hash=auth._th("tok-123"), user_id=u.id, expires_at=db.utcnow() + timedelta(hours=1)))
    assert client.post("/api/password/reset", json={"token": "bad", "password": "new-pass-22"}).status_code == 400
    r = client.post("/api/password/reset", json={"token": "tok-123", "password": "new-pass-22"})
    assert r.status_code == 200 and r.json()["email"] == email
    assert client.post("/api/password/reset", json={"token": "tok-123", "password": "again-pass-3"}).status_code == 400
    assert client.post("/api/login", json={"email": email, "password": "first-pass-1"}).status_code == 401
    assert client.post("/api/login", json={"email": email, "password": "new-pass-22"}).status_code == 200


def test_hs_plan_draft_edit_issue_sign(co, monkeypatch):
    h, sid = co["h"], co["site"]["id"]
    client.put(f"/api/sites/{sid}", json={"features": {"excavations": True, "mobile_plant": True},
                                          "consultants": [{"name": "C. Consultant", "reg": "CHSA/1"}]}, headers=h)
    seen = {}

    def fake(data):
        seen.update(data)
        return {"text": {k: f"## {k}\n- Control for {k}\nHospital: [to complete: name] and [to complete: number]."
                         for k in library.HS_PLAN_AI}, "questions": ["Which hospital is nearest?"]}
    monkeypatch.setattr(ai, "hs_plan", fake)
    r = client.get(f"/api/hs-plan?site_id={sid}", headers=h).json()
    assert r["plan"] is None and any(not i["ok"] for i in r["inputs"])
    r = client.post("/api/hs-plan/draft", json={"site_id": sid}, headers=h).json()
    assert r["plan"]["questions"] == ["Which hospital is nearest?"]
    assert "Excavations or trenches" in seen["site"]["work_types"]
    assert any(i["ref"] == "23" for i in seen["inspections"])          # mobile plant pre-use check
    assert any(a["reg"] == "13(1)" for a in seen["appointments"])      # excavation supervisor required
    board = client.get(f"/api/board?site_id={sid}", headers=h).json()
    tile = next(t for t in board["tiles"] if t["key"] == "hs_plan")
    assert tile["status"] == "amber" and tile["action"] == "hsplan"
    assert client.put("/api/hs-plan", json={"site_id": sid, "text": {"intro": "Our own intro.", "bogus": "x"}},
                      headers=h).status_code == 200
    r = client.get(f"/api/hs-plan?site_id={sid}", headers=h).json()
    assert r["plan"]["text"]["intro"] == "Our own intro." and "bogus" not in r["plan"]["text"]
    pdf_ = client.get(f"/api/hs-plan/pdf?site_id={sid}", headers=h)
    assert pdf_.status_code == 200
    text = "".join(pg.extract_text() for pg in PdfReader(io.BytesIO(pdf_.content)).pages)
    assert "SITE-SPECIFIC HEALTH AND SAFETY PLAN" in text and "Our own intro." in text and "Excavation supervisor" in text
    assert client.post("/api/hs-plan/issue", json={"site_id": sid}, headers=h).status_code == 400   # needs reviewer
    a = client.post("/api/hs-plan/issue", json={"site_id": sid, "reviewer": "C. Consultant", "reviewer_reg": "CHSA/1"},
                    headers=h).json()
    assert a["kind"] == "hs_plan" and "v1" in a["title"] and any("C. Consultant" in x for x in a["signers"])
    r = client.post(f"/api/aes/{a['id']}/signed", json={"method": "wet_ink", "file": "data:application/pdf;base64,"
                                                         + base64.b64encode(pdf_.content).decode()}, headers=h)
    assert r.status_code == 200, r.text
    board = client.get(f"/api/board?site_id={sid}", headers=h).json()
    assert next(t for t in board["tiles"] if t["key"] == "hs_plan")["status"] == "green"


def test_company_defaults_copy_site_and_plan_without_spec(co, monkeypatch):
    h, sid = co["h"], co["site"]["id"]
    client.put("/api/company", json={"defaults": {"emergency": "Plett hospital 044 000 0000",
                                                  "contacts": [{"role": "Construction manager", "name": "John", "phone": "082"}],
                                                  "consultants": [{"name": "C. Consultant"}]}}, headers=h)
    new = client.post("/api/sites", json={"name": "Site B"}, headers=h).json()
    assert new["emergency"].startswith("Plett") and new["contacts"][0]["name"] == "John"
    assert new["consultants"][0]["name"] == "C. Consultant"
    client.put(f"/api/sites/{sid}", json={"features": {"excavations": True, "roof_work": True}, "scope": "New house, 280 m2",
                                          "other_work": ["Pool construction", "pool construction"], "spec_provided": False,
                                          "emergency": "Sedgefield clinic"}, headers=h)
    me_ = client.get("/api/me", headers=h).json()
    assert me_["company"]["defaults"]["other_work_seen"] == ["Pool construction"]
    copy = client.post("/api/sites", json={"name": "Site C", "copy_from": sid, "copy_workers": True}, headers=h).json()
    assert copy["features"]["roof_work"] and copy["scope"] == "New house, 280 m2" and copy["emergency"] == "Sedgefield clinic"
    assert len(client.get(f"/api/workers?site_id={copy['id']}", headers=h).json()) == 2
    seen = {}
    monkeypatch.setattr(ai, "hs_plan", lambda data: seen.update(data) or {"text": {}, "questions": []})
    client.post("/api/hs-plan/draft", json={"site_id": sid}, headers=h)
    assert seen["client_spec_status"] == "none" and seen["site"]["scope_of_work"] == "New house, 280 m2"
    assert "Pool construction" in seen["site"]["work_types"]
    r = client.get(f"/api/hs-plan?site_id={sid}", headers=h).json()
    assert any(i["ok"] is None and "No client H&S specification" in i["label"] for i in r["inputs"])
    text = "".join(pg.extract_text() for pg in PdfReader(io.BytesIO(
        client.get(f"/api/hs-plan/pdf?site_id={sid}", headers=h).content)).pages)
    assert "None provided for this site" in text and "provided no health and safety" in text


def test_admin_login_with_own_password(monkeypatch):
    email = f"boss-{uuid.uuid4().hex[:6]}@test.co"
    assert client.post("/api/signup", json={"company": "Boss Co", "name": "Boss", "email": email,
                                            "password": "boss-pass-1"}).status_code == 200
    assert client.post("/api/admin/login", json={"email": email, "password": "boss-pass-1"}).status_code == 403
    monkeypatch.setattr(server, "ADMIN_EMAILS", {email})
    assert client.post("/api/admin/login", json={"email": email, "password": "wrong-pass"}).status_code == 401
    tok = client.post("/api/admin/login", json={"email": email.upper(), "password": "boss-pass-1"}).json()["token"]
    assert client.get("/api/admin/overview", headers={"X-Token": tok}).status_code == 200
    monkeypatch.setattr(server, "ADMIN_EMAILS", set())
    assert client.get("/api/admin/overview", headers={"X-Token": tok}).status_code == 401
