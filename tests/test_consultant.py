"""Consultant documents: RA import with checks, spec import, spec tiles, generic forms."""
import base64
import uuid

from test_api import client, co, me, png, server, sig, signup  # noqa: F401
from app import ai

RA = {"header": {"reference": "1", "ra_no": "1", "revision": "", "date": "June 2026", "review_date": "June 2027",
                 "description": "CIVILS", "location": "Eden View", "team": [{"name": "S VAN LIER", "title": "CHSM"}],
                 "client_approved": False},
      "rows": [{"item": "1", "activity": "Delivery of site offices & plant", "hazards": "Pedestrians on site",
                "consequence": "Impact with pedestrians", "c": 6, "l": 3, "rating": 18, "controls": ["Site induction for all"],
                "rc": 6, "rl": 2, "rrating": 12, "responsible": "Operator of delivery vehicle / Construction manager",
                "accepted": False, "ppe": []},
               {"item": "5", "activity": "excavations", "hazards": "Underground services",
                "consequence": "Electrical shock", "c": 3, "l": 4, "rating": 12, "controls": ["Locate underground services",
                "Barricading of excavations"], "rc": 3, "rl": 3, "rrating": 9, "responsible": "Construction manager",
                "accepted": False, "ppe": ["gloves", "head protection", "protective footwear"]}],
      "matrix": []}
SPEC = {"project": "Eden View - Phase 2", "client": "", "author": "S van Lier", "date": "June 2026",
        "frequencies": {"toolbox_talk_days": 7, "environmental_talks_min": 2, "first_drill_within_days": 90,
                        "evacuation_drill_days": 90, "committee_meeting_days": 30, "audit_days": 30,
                        "injury_report_days": 30, "scaffold_inspection_days": 7, "ladder_inspection_days": 30,
                        "temporary_works_inspection_days": 1, "observation_days": None},
        "required_documents": [{"title": "Health and Safety Policy signed by CEO", "clause": "2.1.1", "section": "policies"},
                               {"title": "Organogram", "clause": "2.4.11", "section": "organogram"}],
        "required_appointments": [{"title": "Ladder inspector", "clause": "3.7.2", "key": "other"}],
        "permits": ["hot_work", "electrical", "work_at_height"],
        "client_hazards": ["Working at Heights", "Interface with the public"],
        "required_inspections": [{"item": "Ladders", "clause": "3.7.1", "checklist": "ladder", "days": 30}],
        "ppe_minimum": ["Hard hat"], "injury_categories": ["First aid"], "facilities": {"toilet_per_workers": 30,
        "shower_per_workers": 15}, "acceptance_signatories": ["PC CEO", "Client"], "ra_team_required": ["CR 8(1)", "CR 9(1)"],
        "key_rules": [{"clause": "2.2.2", "rule": "No alcohol or drugs on site."}]}


def pdf_data():
    return "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4\n%fake\n").decode()


def load_docs(co, monkeypatch):
    monkeypatch.setattr(ai, "ra_extract", lambda name, data: RA)
    monkeypatch.setattr(ai, "spec_extract", lambda *a: SPEC)
    monkeypatch.setattr(ai, "hazard_coverage", lambda hz, items: {"results": [
        {"hazard": "Working at Heights", "status": "missing", "item_ids": [], "note": ""},
        {"hazard": "Interface with the public", "status": "covered", "item_ids": [items[0]["id"]], "note": ""}]})
    sid = co["site"]["id"]
    assert client.post("/api/consultant/spec/preview", json={"site_id": sid, "file": pdf_data()}, headers=co["h"]).status_code == 200
    assert client.post("/api/consultant/spec/confirm", json={"site_id": sid}, headers=co["h"]).status_code == 200
    r = client.post("/api/consultant/ra/preview", json={"site_id": sid, "file": pdf_data()}, headers=co["h"]).json()
    texts = " ".join(f["text"] for f in r["flags"])
    assert "consequence 6" in texts and "Client approval" in texts and "team has 1 member" in texts
    assert r["items"][1]["hazards"][0]["band"] == "Significant" and r["items"][1]["ppe"] == ["Gloves", "Hard hat", "Safety boots"]
    assert client.post("/api/consultant/ra/confirm", json={"site_id": sid, "approve": True, "ra_only": True},
                       headers=co["h"]).json()["items"] == 2
    return sid


def test_ra_import_replaces_library_for_site(co, monkeypatch):
    sid = load_docs(co, monkeypatch)
    risks = client.get(f"/api/risks?site_id={sid}", headers=co["h"]).json()
    assert len(risks) == 2 and all(r["approved"] and r["source"] == "consultant_ra" for r in risks)
    assert "S VAN LIER (CHSM)" in risks[0]["approved_by"] and risks[0]["ref"].startswith("RA 1")
    sync = client.get(f"/api/sync?site_id={sid}", headers=co["h"]).json()
    assert "Construction manager" in sync["ra_roles"] and sync["spec_rules"] == ["No alcohol or drugs on site."]
    # A task sheet with a consultant item copies the scores
    rid = risks[0]["id"]
    body = {"client_id": uuid.uuid4().hex, "site_id": sid, "kind": "task_sheet", "record_date": server.today().isoformat(),
            "payload": {"tasks": [{"description": "Dig trench", "risk_item_ids": [rid], "worker_ids": [co["w1"]["id"]]}]},
            "signatures": [sig(worker=co["w1"]["id"])]}
    rec = client.post("/api/records", json=body, headers=co["h"]).json()
    full = client.get(f"/api/records/{rec['id']}", headers=co["h"]).json()
    assert full["payload"]["tasks"][0]["assessed"] and full["payload"]["tasks"][0]["risks"][0]["hazards"][0]["rating"]


def test_spec_tiles_and_forms(co, monkeypatch):
    sid = load_docs(co, monkeypatch)
    b = client.get(f"/api/board?site_id={sid}", headers=co["h"]).json()
    t = {x["key"]: x for x in b["tiles"]}
    assert t["ra_doc"]["status"] == "red" and t["client_hazards"]["status"] == "red"
    assert t["spec_acceptance"]["status"] == "red" and t["ppe_issue"]["status"] == "red"
    assert t["policies"]["status"] == "red" and "insp_ladder" in t and t["facilities"]["status"] == "amber"
    assert "ladder_inspector" in {k for k in server.library.APPOINTMENTS} and "Ladder inspector" in t["appointments"]["detail"] \
        or t["appointments"]["status"] == "red"
    # PPE issue for both workers turns the tile green
    for w in (co["w1"], co["w2"]):
        r = client.post("/api/records", json={"client_id": uuid.uuid4().hex, "site_id": sid, "kind": "ppe_issue",
                                              "record_date": server.today().isoformat(),
                                              "payload": {"worker": w["id"], "items": ["Hard hat", "Not PPE"], "reason": "First issue",
                                                          "understood": True},
                                              "signatures": [sig(worker=w["id"], role="worker"), sig(user=me(co["h"])["user"]["id"], role="issuer")]},
                        headers=co["h"])
        assert r.status_code == 200, r.text
    # A required yes/no must be yes
    r = client.post("/api/records", json={"client_id": uuid.uuid4().hex, "site_id": sid, "kind": "ppe_issue",
                                          "record_date": server.today().isoformat(),
                                          "payload": {"worker": co["w1"]["id"], "items": ["Hard hat"], "reason": "First issue", "understood": False},
                                          "signatures": [sig(worker=co["w1"]["id"])]}, headers=co["h"])
    assert r.status_code == 400
    # RA acceptance for both roles
    for role in ("Operator of delivery vehicle", "Construction manager"):
        client.post("/api/records", json={"client_id": uuid.uuid4().hex, "site_id": sid, "kind": "ra_acceptance",
                                          "record_date": server.today().isoformat(), "payload": {"role": role},
                                          "signatures": [sig(user=me(co["h"])["user"]["id"], role="responsible")]}, headers=co["h"])
    a = client.post("/api/consultant/spec/acceptance", json={"site_id": sid}, headers=co["h"]).json()
    assert a["kind"] == "spec_acceptance" and a["signers"] == ["PC CEO", "Client"]
    t = {x["key"]: x for x in client.get(f"/api/board?site_id={sid}", headers=co["h"]).json()["tiles"]}
    assert t["ppe_issue"]["status"] == "green" and t["ra_acceptance"]["status"] == "green"
    assert t["spec_acceptance"]["status"] == "amber"
    # Induction carries the client's site rules
    w = client.post("/api/workers", json={"name": "New Person", "site_id": sid}, headers=co["h"]).json()
    rid = client.post("/api/records", json={"client_id": uuid.uuid4().hex, "site_id": sid, "kind": "induction",
                                            "record_date": server.today().isoformat(), "payload": {"worker_id": w["id"], "consent": True},
                                            "signatures": [sig(worker=w["id"])]}, headers=co["h"]).json()["id"]
    assert "No alcohol or drugs on site." in client.get(f"/api/records/{rid}", headers=co["h"]).json()["payload"]["induction_text"]
    # Safety file builds with the registers section
    r = client.get(f"/api/sites/{sid}/file.pdf", headers=co["h"])
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
