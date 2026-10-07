"""Second pass for the video demo site: documents, the e-signature agreement, the last
inspections and an approved H&S plan (drafted by the AI). Run after seed.py."""
import base64
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seed as S  # noqa: E402
from seed import call, library, record, sig  # noqa: E402


def pdf(title: str) -> str:
    import io
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(60, 780, title)
    c.setFont("Helvetica", 11)
    c.drawString(60, 755, "Demo document for the SiteBakkie video.")
    c.save()
    return "data:application/pdf;base64," + base64.b64encode(buf.getvalue()).decode()


def main():
    tok = call("/api/login", {"email": "demo@example.com", "password": "demo-pass-1"})["token"]
    me = call("/api/me", token=tok)
    uid, site = me["user"]["id"], me["sites"][0]["id"]
    call("/api/esign/accept", {}, tok)
    call(f"/api/sites/{site}", {"features": {"excavations": True, "scaffolding": True, "work_at_height": True,
                                             "mobile_plant": True, "temporary_power": True, "concrete": True,
                                             "subcontractors": False}}, tok, "PUT")
    for section, title, exp in (("notification", "Notification of construction work (Annexure 2)", None),
                                ("company", "COID letter of good standing", (S.TODAY + timedelta(days=210)).isoformat()),
                                ("fall_protection", "Fall protection plan", None),
                                ("emergency", "Emergency plan and contact numbers", None)):
        call("/api/docs", {"site_id": site, "section": section, "title": title, "file": pdf(title), "expires": exp}, tok)
    workers = {x["name"].split()[0]: x["id"] for x in call(f"/api/workers?site_id={site}", token=tok)}
    for tpl, who in (("scaffold", workers["Lwazi"]), ("harness", workers["Sipho"])):
        n = len(library.CHECKLISTS[tpl]["items"])
        record(tok, site, "check", {"template": tpl, "answers": [{"answer": "ok"}] * n, "location": "East wall"},
               [sig(worker=who, role="inspector")])
    # the H&S plan: drafted by the AI, issued, signed copy uploaded
    plan = call("/api/hs-plan/draft", {"site_id": site}, tok)
    print("plan drafted:", len(plan["plan"]["text"]), "sections")
    a = call("/api/hs-plan/issue", {"site_id": site, "reviewer": "Lindiwe Mabaso", "reviewer_reg": "CHSA/0412/2024",
                                    "pc_signer": "Demo Owner", "client_signer": "Mr Smith"}, tok)
    req = urllib.request.Request(S.BASE + f"/api/hs-plan/pdf?site_id={site}", headers={"X-Token": tok})
    signed = "data:application/pdf;base64," + base64.b64encode(urllib.request.urlopen(req, timeout=60).read()).decode()
    call(f"/api/aes/{a['id']}/signed", {"method": "wet_ink", "file": signed, "note": "Signed by hand; scan uploaded."}, tok)
    print("extras done")


if __name__ == "__main__":
    main()
