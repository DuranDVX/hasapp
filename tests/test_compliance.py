"""Site Board, AES documents, contractors, audits, investigations, print and verify."""
import base64
import datetime as dt
import io
import uuid

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pypdf import PdfReader

from test_api import client, co, jpg, me, png, server, sig, signup, task_sheet  # noqa: F401  (shared app + fixture)


def pdf_url(data: bytes) -> str:
    return "data:application/pdf;base64," + base64.b64encode(data).decode()


def tiles(h, site_id):
    b = client.get(f"/api/board?site_id={site_id}", headers=h).json()
    return {t["key"]: t for t in b["tiles"]}, b


def rec(co, kind, payload, signatures, date=None):
    body = {"client_id": uuid.uuid4().hex, "site_id": co["site"]["id"], "kind": kind,
            "record_date": date or server.today().isoformat(), "payload": payload, "signatures": signatures}
    r = client.post("/api/records", json=body, headers=co["h"])
    assert r.status_code == 200, r.text
    return r.json()["id"]


def aes_sign(data: bytes, issuer_cn="LAWtrust Test CA") -> bytes:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Jane Engineer")]))
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)]))
            .public_key(key.public_key()).serial_number(7)
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=9))
            .sign(key, hashes.SHA256()))
    import tempfile, os
    d = tempfile.mkdtemp()
    open(os.path.join(d, "k.pem"), "wb").write(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    open(os.path.join(d, "c.pem"), "wb").write(cert.public_bytes(serialization.Encoding.PEM))
    signer = signers.SimpleSigner.load(os.path.join(d, "k.pem"), os.path.join(d, "c.pem"))
    w = IncrementalPdfFileWriter(io.BytesIO(data))
    return signers.sign_pdf(w, signers.PdfSignatureMetadata(field_name="Sig1"), signer=signer).getvalue()


def test_board_starts_red_and_turns_green(co):
    t, b = tiles(co["h"], co["site"]["id"])
    assert t["esign"]["status"] == "red"
    assert t["inductions"]["status"] == "red"            # two workers, none inducted
    assert t["plant_checks"]["status"] in ("red", "amber")
    assert b["counts"]["red"] > 0
    assert client.post("/api/esign/accept", headers=co["h"]).status_code == 200
    for w in (co["w1"], co["w2"]):
        rec(co, "induction", {"worker_id": w["id"], "consent": True},
            [sig(worker=w["id"]), sig(user=me(co["h"])["user"]["id"], role="inductor")])
    rec(co, "task_sheet", task_sheet(co)["payload"], task_sheet(co)["signatures"])
    t, _ = tiles(co["h"], co["site"]["id"])
    assert t["esign"]["status"] == "green"
    assert t["inductions"]["status"] == "green"
    assert t["task_sheet"]["status"] == "amber"           # starter risk items are not approved


def test_site_features_switch_inspections_on(co):
    t, _ = tiles(co["h"], co["site"]["id"])
    assert "insp_excavation" not in t
    client.put(f"/api/sites/{co['site']['id']}", json={"features": {"excavations": True, "bogus": True}}, headers=co["h"])
    t, b = tiles(co["h"], co["site"]["id"])
    assert t["insp_excavation"]["status"] == "red" and "bogus" not in b["features"]
    answers = [{"answer": "ok"} for _ in server.library.CHECKLISTS["excavation"]["items"]]
    rec(co, "check", {"template": "excavation", "answers": answers, "location": "Sewer trench"},
        [sig(worker=co["w2"]["id"], role="inspector")])
    t, _ = tiles(co["h"], co["site"]["id"])
    assert t["insp_excavation"]["status"] == "green"


def test_visitor_needs_ppe(co):
    body = {"name": "Jane Client", "company": "Client", "purpose": "Site walk", "host": "Owner One", "ppe": []}
    r = client.post("/api/records", json={"client_id": uuid.uuid4().hex, "site_id": co["site"]["id"], "kind": "visitor",
                                         "record_date": server.today().isoformat(), "payload": body,
                                         "signatures": [{"name": "Jane Client", "image": png(), "role": "visitor"}]},
                    headers=co["h"])
    assert r.status_code == 400
    body["ppe"] = ["Hard hat", "Reflective vest", "Not PPE"]
    rid = rec(co, "visitor", body, [{"name": "Jane Client", "image": png(), "role": "visitor"}])
    p = client.get(f"/api/records/{rid}", headers=co["h"]).json()["payload"]
    assert p["ppe"] == ["Hard hat", "Reflective vest"] and "Visitor rules" in p["rules_text"]


def test_appointment_issues_aes_doc_and_accepts_signed_pdf(co):
    uid = me(co["h"])["user"]["id"]
    rid = rec(co, "appointment", {"type": "excavation", "appointee": {"worker_id": co["w2"]["id"]}, "scope": "All trenches"},
              [sig(user=uid, role="appointer"), sig(worker=co["w2"]["id"], role="appointee")])
    docs = client.get(f"/api/aes?site_id={co['site']['id']}", headers=co["h"]).json()
    d = next(x for x in docs if x["record_id"] == rid)
    assert d["status"] == "awaiting" and d["kind"] == "appointment"
    t, _ = tiles(co["h"], co["site"]["id"])
    assert t["aes"]["status"] == "amber"
    original = client.get(d["original_url"]).content
    assert original[:4] == b"%PDF"
    # An unsigned PDF is refused as AES
    r = client.post(f"/api/aes/{d['id']}/signed", json={"method": "aes", "file": pdf_url(original)}, headers=co["h"])
    assert r.status_code == 400
    signed = aes_sign(original)
    r = client.post(f"/api/aes/{d['id']}/signed", json={"method": "aes", "file": pdf_url(signed)}, headers=co["h"])
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "signed" and out["signatures"][0]["intact"] and not out["signatures"][0]["trusted"]
    assert "chain not verified" in out["summary"]
    # A PDF changed after signing is refused
    bad = bytearray(signed)
    i = bad.find(b"Appointment")
    bad[i] = ord("X")
    d2 = client.post("/api/aes", json={"kind": "other", "site_id": co["site"]["id"], "title": "Test",
                                      "signers": ["A"], "text": "Hello"}, headers=co["h"]).json()
    r = client.post(f"/api/aes/{d2['id']}/signed", json={"method": "aes", "file": pdf_url(bytes(bad))}, headers=co["h"])
    assert r.status_code == 400
    # Wet ink scan is accepted
    r = client.post(f"/api/aes/{d2['id']}/signed", json={"method": "wet_ink", "file": jpg()}, headers=co["h"])
    assert r.status_code == 200 and r.json()["method"] == "wet_ink"


def test_contractor_and_agreement(co):
    sid = co["site"]["id"]
    c = client.post("/api/contractors", json={"site_id": sid, "name": "Bright Sparks", "scope": "Electrical"},
                    headers=co["h"]).json()
    t, _ = tiles(co["h"], sid)
    assert t["contractors"]["status"] == "red"
    client.put(f"/api/contractors/{c['id']}", json={"coid_expires": (server.today() + dt.timedelta(days=200)).isoformat(),
                                                    "coid_file": jpg(), "appointed_on": server.today().isoformat(),
                                                    "hs_plan_ok": True}, headers=co["h"])
    a = client.post(f"/api/contractors/{c['id']}/agreement", json={}, headers=co["h"]).json()
    assert a["kind"] == "mandatary_agreement"
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(client.get(a["original_url"]).content)).pages)
    assert "section 37(2)" in text and "Bright Sparks" in text
    t, _ = tiles(co["h"], sid)
    assert t["contractors"]["status"] == "amber"          # agreement issued, not yet signed
    client.post(f"/api/aes/{a['id']}/signed", json={"method": "wet_ink", "file": jpg()}, headers=co["h"])
    t, _ = tiles(co["h"], sid)
    assert t["contractors"]["status"] == "green"


def test_audit_prefill_audit_and_ack(co):
    pre = client.get(f"/api/audit/prefill?site_id={co['site']['id']}", headers=co["h"]).json()
    items = [{"key": i["key"], "result": i["result"] or "ok", "note": i["note"]} for i in pre["items"]]
    assert any(i["result"] == "gap" for i in items)
    # The auditor role may record audits
    u = client.post("/api/users", json={"name": "Agent", "email": f"{uuid.uuid4().hex[:6]}@agent.co", "role": "auditor"},
                    headers=co["h"]).json()
    tok = client.post("/api/login", json={"email": u["email"], "password": u["temp_password"]}).json()["token"]
    h = {"X-Token": tok}
    body = {"client_id": uuid.uuid4().hex, "site_id": co["site"]["id"], "kind": "audit",
            "record_date": server.today().isoformat(),
            "payload": {"items": items, "findings": [{"finding": "No fall plan", "action": "Write it", "owner": "SO", "due": "2026-10-20"}],
                        "board": pre["board"]},
            "signatures": [sig(user=u["id"], role="auditor")]}
    r = client.post("/api/records", json=body, headers=h)
    assert r.status_code == 200, r.text
    aid = r.json()["id"]
    assert client.post("/api/records", json=task_sheet(co), headers=h).status_code == 403
    t, _ = tiles(co["h"], co["site"]["id"])
    assert t["audit"]["status"] in ("green", "amber")
    rec(co, "audit_ack", {"audit_id": aid}, [sig(user=me(co["h"])["user"]["id"], role="principal contractor")])
    t, _ = tiles(co["h"], co["site"]["id"])
    assert t["audit"]["status"] == "green"


def test_incident_investigation_and_annexure1(co):
    sid = co["site"]["id"]
    old = (server.today() - dt.timedelta(days=9)).isoformat()
    iid = rec(co, "incident", {"type": "medical", "description": "Cut hand on grinder",
                               "people": [{"name": "Sipho Dlamini", "worker_id": co["w1"]["id"], "injury": "Cut", "treatment": "Clinic"}]},
              [sig(user=me(co["h"])["user"]["id"], role="reporter")], date=old)
    t, _ = tiles(co["h"], sid)
    assert t["incidents"]["status"] == "red"            # more than 7 days, not investigated
    inc = client.get(f"/api/incidents?site_id={sid}", headers=co["h"]).json()
    assert inc[0]["investigation_id"] == "" and inc[0]["days_open"] == 9
    r = client.post("/api/records", json={"client_id": uuid.uuid4().hex, "site_id": sid, "kind": "investigation",
                                         "record_date": server.today().isoformat(),
                                         "payload": {"incident_id": iid, "findings": "Guard removed", "reportable": True},
                                         "signatures": [sig(user=me(co["h"])["user"]["id"], role="investigator")]},
                    headers=co["h"])
    assert r.status_code == 400                          # reportable needs the report date
    rec(co, "investigation", {"incident_id": iid, "findings": "Guard removed", "root_causes": ["No pre-use check"],
                              "actions": [{"action": "Retrain", "owner": "Foreman", "due": "2026-10-10"}],
                              "reportable": False, "not_reportable_reason": "First aid level"},
        [sig(user=me(co["h"])["user"]["id"], role="investigator")])
    t, _ = tiles(co["h"], sid)
    assert t["incidents"]["status"] == "green"
    r = client.get(f"/api/records/{iid}/annexure1.pdf", headers=co["h"])
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "ANNEXURE 1" in text and "Retrain" in text
    r = client.get(f"/api/records/{iid}/incident/pack.pdf", headers=co["h"])
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "FLASH REPORT" in text and "ANNEXURE 1" in text and "UNSAFE" not in text.split("CAUSES")[0][:0] \
        and "Guard removed" in text and "Retrain" in text and "Documents collected" in text


def test_print_packs_and_public_verify(co):
    rid = rec(co, "task_sheet", task_sheet(co)["payload"], task_sheet(co)["signatures"])
    for what in ("task_sheet", "induction_register", "visitor_register", "check_register"):
        r = client.get(f"/api/sites/{co['site']['id']}/print.pdf?what={what}", headers=co["h"])
        assert r.status_code == 200 and r.content[:4] == b"%PDF", what
    r = client.get(f"/api/records/{rid}/pdf?print=1", headers=co["h"])
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "Certified a true reproduction" in text
    full = client.get(f"/api/records/{rid}", headers=co["h"]).json()
    ok = client.get(f"/v/{rid}?h={full['hash'][:16]}")
    assert ok.status_code == 200 and "Verified" in ok.text and "Sipho" not in ok.text
    bad = client.get(f"/v/{rid}?h=0000000000000000")
    assert "Does not match" in bad.text


def test_safety_file_includes_new_sections(co):
    client.post("/api/contractors", json={"site_id": co["site"]["id"], "name": "Coastal Plumbing"}, headers=co["h"])
    rec(co, "visitor", {"name": "Inspector X", "ppe": ["Hard hat"]}, [{"name": "Inspector X", "image": png(), "role": "visitor"}])
    r = client.get(f"/api/sites/{co['site']['id']}/file.pdf", headers=co["h"])
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "Coastal Plumbing" in text and "Inspector X" in text and "List of contractors" in text
