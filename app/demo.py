"""Demo data for local testing: python -m app.demo

Creates "Demo Builders" with one site, six workers, plant and the starter
library. Login: demo@example.com / demo-pass-1 (example.com never gets email).
"""
from datetime import date, timedelta

from sqlalchemy import select

from . import auth, db, library


def main() -> None:
    db.init()
    with db.session() as s:
        if s.scalar(select(db.User).where(db.User.email == "demo@example.com")):
            print("Demo already exists. Login: demo@example.com / demo-pass-1")
            return
        c = db.Company(name="Demo Builders (Pty) Ltd", reg_no="2019/123456/07", coid_no="990012345",
                       phone="044 533 0000", email="demo@example.com", address="12 Main Street, Plettenberg Bay")
        s.add(c)
        s.flush()
        s.add(db.User(company_id=c.id, email="demo@example.com", name="Demo Owner", role="owner",
                      sacpcmp_no="CHSO/0001/2025", pw_hash=auth.hash_pw("demo-pass-1")))
        s.add(db.User(company_id=c.id, email="foreman@example.com", name="Piet Foreman", role="foreman",
                      pw_hash=auth.hash_pw("demo-pass-1")))
        for r in library.STARTER_RISKS:
            s.add(db.RiskItem(company_id=c.id, activity=r["activity"], hazards=r["hazards"], ppe=r["ppe"],
                              source="starter"))
        site = db.Site(company_id=c.id, name="Erf 1234, Plettenberg Bay", address="1234 Beacon Way, Plettenberg Bay",
                       client="Mr and Mrs Smith", client_agent="Coastal H&S Agents (Jane Agent)",
                       emergency="Mediclinic Plettenberg Bay, 044 501 5100\nAmbulance 10177 · Fire 044 501 3000",
                       start_date=date.today() - timedelta(days=20))
        s.add(site)
        s.flush()
        people = [("Sipho Dlamini", "Bricklayer", "", "zu"), ("Thabo Mokoena", "General worker", "", "st"),
                  ("Johan Botha", "TLB operator", "", "af"), ("Lwazi Ndlovu", "General worker", "", "xh"),
                  ("Andile Khumalo", "Electrician", "Bright Sparks Electrical", "zu"),
                  ("Ricardo Fortuin", "Plumber", "Coastal Plumbing", "af")]
        for i, (name, trade, emp, lang) in enumerate(people):
            w = db.Worker(company_id=c.id, name=name, trade=trade, employer=emp, language=lang,
                          id_number=f"85010{i}580008{i}", phone=f"07{i}2345678")
            s.add(w)
            s.flush()
            s.add(db.SiteWorker(site_id=site.id, worker_id=w.id))
            exp = date.today() + timedelta(days=[200, 20, 300, -5, 150, 400][i])
            s.add(db.Credential(company_id=c.id, worker_id=w.id, kind="medical", title="Medical fitness certificate",
                                issued=exp - timedelta(days=365), expires=exp))
        s.add(db.Plant(company_id=c.id, site_id=site.id, name="TLB 1", template="earthmoving", ident="CAX 123-456"))
        s.add(db.Plant(company_id=c.id, site_id=site.id, name="Concrete mixer", template="mixer", ident="MX-02"))
        s.add(db.Plant(company_id=c.id, site_id=site.id, name="Site bakkie", template="vehicle", ident="CX 98765"))
    print("Demo ready. Login: demo@example.com / demo-pass-1 (foreman@example.com / demo-pass-1)")


if __name__ == "__main__":
    main()
