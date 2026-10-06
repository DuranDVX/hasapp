"""PDFs: one record, and the whole site safety file."""
import io
from datetime import date

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)
from xml.sax.saxutils import escape

from . import config, files, library, records

SS = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=SS["Heading1"], fontSize=16, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=SS["Heading2"], fontSize=12.5, spaceBefore=8, spaceAfter=3)
H3 = ParagraphStyle("h3", parent=SS["Heading3"], fontSize=10.5, spaceBefore=4, spaceAfter=2)
P = ParagraphStyle("p", parent=SS["BodyText"], fontSize=9, leading=11.5)
SMALL = ParagraphStyle("s", parent=P, fontSize=7.5, leading=9, textColor=colors.HexColor("#555555"))
WARN = ParagraphStyle("w", parent=P, textColor=colors.HexColor("#9a5b00"))
BAD = ParagraphStyle("b", parent=P, textColor=colors.HexColor("#b00020"))
GRID = TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8ced6")),
                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f5")),
                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                   ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                   ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)])
W = A4[0] - 30 * mm


def _p(text, style=P):
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)


def _img(name: str, w: float, h: float):
    if not name:
        return ""
    try:
        im = Image(str(files.path(name)))
        r = min(w / im.imageWidth, h / im.imageHeight)
        im.drawWidth, im.drawHeight = im.imageWidth * r, im.imageHeight * r
        return im
    except Exception:
        return _p("(image missing)", SMALL)


def _file_of(v) -> str:
    return v.get("file", "") if isinstance(v, dict) else ""


def _doc(buf, title: str, company, site):
    def frame(c, d):
        c.saveState()
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawString(15 * mm, 10 * mm, f"{company.name} · {site.name if site else ''} · {title}")
        c.drawRightString(A4[0] - 15 * mm, 10 * mm, f"{config.APP_NAME} · page {d.page}")
        c.restoreState()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=14 * mm, bottomMargin=16 * mm, title=title,
                            author=company.name)
    return doc, frame


def _header(company, site, title: str, when: str) -> list:
    left = [_p(title, H1), _p(f"{company.name} · {site.name}", P), _p(when, SMALL)]
    logo = _img(company.logo_file, 40 * mm, 16 * mm) if company.logo_file else ""
    t = Table([[left, logo]], colWidths=[W - 45 * mm, 45 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    return [t, Spacer(1, 4)]


# ---------------------------------------------------------------- record bodies

def _signatures(rec) -> list:
    rows = [["Name", "Role", "Signature", "Photo", "Signed (device time)"]]
    for g in rec.signatures:
        rows.append([_p(g.name), _p(g.role), _img(g.image_file, 32 * mm, 11 * mm),
                     _img(g.photo_file, 14 * mm, 14 * mm), _p(g.signed_at, SMALL)])
    t = Table(rows, colWidths=[45 * mm, 25 * mm, 38 * mm, 20 * mm, W - 128 * mm], repeatRows=1)
    t.setStyle(GRID)
    return [_p("Signatures", H3), t]


def _proof(rec) -> list:
    gps = f"{rec.lat:.5f}, {rec.lng:.5f}" if rec.lat is not None and rec.lng is not None else "not recorded"
    return [Spacer(1, 3), _p(f"Captured by {rec.created_name} · device time {rec.device_time or '-'} · "
                             f"received {rec.received_at:%Y-%m-%d %H:%M} UTC · GPS {gps} · "
                             f"record #{rec.seq} · hash {rec.hash[:16]}…", SMALL)]


def _task_sheet(rec) -> list:
    p, out = rec.payload, []
    for i, t in enumerate(p.get("tasks", []), 1):
        out.append(_p(f"Task {i}: {t['description']}" + (f" — {t['location']}" if t.get("location") else ""), H3))
        if not t.get("assessed"):
            out.append(_p("Not covered by an approved risk assessment. The safety officer must review this task.", WARN))
        rows = [["Hazard", "Risk", "Controls"]]
        for r in t.get("risks", []):
            rows.append([_p(r["activity"] + ("" if r.get("approved") else " (NOT APPROVED)"), H3), "", ""])
            for h in r.get("hazards", []):
                rows.append([_p(h["hazard"]), _p(h.get("risk", "")),
                             _p("\n".join("• " + c for c in h.get("controls", [])))])
        if len(rows) > 1:
            tb = Table(rows, colWidths=[55 * mm, 12 * mm, W - 67 * mm], repeatRows=1)
            tb.setStyle(GRID)
            out.append(tb)
        out.append(_p("<b>PPE:</b> " + escape(", ".join(t.get("ppe", [])) or "-"), P))
        out.append(_p("<b>Workers:</b> " + escape(", ".join(w["name"] for w in t.get("workers", [])) or "-"), P))
        if t.get("plant"):
            out.append(_p("<b>Plant:</b> " + escape(", ".join(x["name"] for x in t["plant"])), P))
    if p.get("unmatched"):
        out.append(_p("Tasks without a risk assessment", H3))
        for u in p["unmatched"]:
            out.append(_p(f"• {u['description']} — {u.get('reason', '')}", WARN))
    if p.get("notes"):
        out += [_p("Notes", H3), _p(p["notes"])]
    return out


def _toolbox_talk(rec) -> list:
    p = rec.payload
    out = [_p(p.get("title") or p.get("topic"), H2),
           _p(f"Language: {library.LANGUAGES.get(p.get('language'), 'English')}"
              + (" (AI translation — check with a speaker)" if p.get("ai_translated") else ""), SMALL)]
    if p.get("text"):
        out.append(_p(p["text"]))
    if p.get("text_en") and p.get("language") != "en":
        out += [_p("English", H3), _p(p["text_en"])]
    if p.get("key_points"):
        out += [_p("Key points", H3)] + [_p("• " + k) for k in p["key_points"]]
    if p.get("questions"):
        out += [_p("Questions asked", H3)] + [_p("• " + k) for k in p["questions"]]
    if gp := _file_of(p.get("group_photo")):
        out += [_p("Attendance photo", H3), _img(gp, 90 * mm, 60 * mm)]
    return out


def _check(rec) -> list:
    p = rec.payload
    res = {"pass": ("PASS", P), "defects": ("PASS WITH DEFECTS", WARN), "fail": ("FAIL — DO NOT USE", BAD)}[p["result"]]
    out = [_p(f"{p['title']}" + (f": {p['plant_name']} {p.get('plant_ident', '')}" if p.get("plant_name") else ""), H2),
           _p(f"Result: {res[0]}", res[1])]
    rows = [["Item", "Result", "Note"]]
    for it in p["items"]:
        mark = {"ok": "OK", "defect": "DEFECT", "na": "N/A"}[it["answer"]]
        rows.append([_p(it["q"] + (" *" if it["critical"] else "")), _p(mark, BAD if it["answer"] == "defect" else P),
                     [_p(it.get("note", ""))] + ([_img(_file_of(it["photo"]), 30 * mm, 22 * mm)] if it.get("photo") else [])])
    tb = Table(rows, colWidths=[95 * mm, 20 * mm, W - 115 * mm], repeatRows=1)
    tb.setStyle(GRID)
    out += [tb, _p("* critical item: a defect means the item must not be used.", SMALL)]
    if p.get("notes"):
        out.append(_p(p["notes"]))
    return out


def _incident(rec) -> list:
    p = rec.payload
    out = [_p(library.INCIDENT_TYPES.get(p["type"], "Incident"), H2)]
    if p.get("possibly_reportable"):
        out.append(_p("POSSIBLY REPORTABLE under section 24 of the OHS Act: " + p.get("reportable_reason", "")
                      + " The safety officer must decide and report within the legal time.", BAD))
    for label, key in (("When", "occurred_at"), ("Where", "location"), ("What happened", "description"),
                       ("Immediate actions", "immediate_actions")):
        if p.get(key):
            out += [_p(label, H3), _p(p[key])]
    if p.get("people"):
        rows = [["Person", "Injury", "Treatment"]] + [[_p(x["name"]), _p(x["injury"]), _p(x["treatment"])] for x in p["people"]]
        tb = Table(rows, colWidths=[50 * mm, 70 * mm, W - 120 * mm], repeatRows=1)
        tb.setStyle(GRID)
        out += [_p("People involved", H3), tb]
    if p.get("witnesses"):
        out += [_p("Witnesses", H3), _p(", ".join(p["witnesses"]))]
    if p.get("possible_causes"):
        out += [_p("Possible causes", H3)] + [_p("• " + c) for c in p["possible_causes"]]
    photos = [_img(_file_of(x), 55 * mm, 40 * mm) for x in p.get("photos", []) if _file_of(x)]
    if photos:
        out += [_p("Photos", H3), Table([photos[i:i + 3] for i in range(0, len(photos), 3)])]
    return out


def _induction(rec) -> list:
    p = rec.payload
    return [_p(f"Site induction: {p['worker_name']}", H2), _p(p["induction_text"])]


BODIES = {"task_sheet": _task_sheet, "toolbox_talk": _toolbox_talk, "check": _check,
          "incident": _incident, "induction": _induction}


def record_flowables(rec, company, site, header=True) -> list:
    title = records.KINDS[rec.kind]
    out = _header(company, site, title, f"{rec.record_date:%A %d %B %Y}") if header else \
        [_p(f"{title} · {rec.record_date:%a %d %b %Y}", H2)]
    return out + BODIES[rec.kind](rec) + _signatures(rec) + _proof(rec)


def record_pdf(rec, company, site) -> bytes:
    buf = io.BytesIO()
    doc, frame = _doc(buf, records.KINDS[rec.kind], company, site)
    doc.build(record_flowables(rec, company, site), onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()


# ---------------------------------------------------------------- safety file

def _section_pdf(company, site, title: str, flow: list) -> bytes:
    buf = io.BytesIO()
    doc, frame = _doc(buf, "Health and safety file", company, site)
    doc.build([_p(title, H1), Spacer(1, 4)] + (flow or [_p("No records in this period.", SMALL)]),
              onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()


def _image_page(name: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm)
    doc.build([_img(name, W, A4[1] - 30 * mm)])
    return buf.getvalue()


def _workers_flow(workers: list, inducted: set, today: date) -> list:
    rows = [["Name", "ID number", "Trade", "Employer", "Inducted", "Certificates (expiry)"]]
    for w in workers:
        certs = []
        for c in w.credentials:
            mark = ""
            if c.expires and c.expires < today:
                mark = " EXPIRED"
            certs.append(f"{library.CREDENTIAL_KINDS.get(c.kind, c.kind)}: {c.title} ({c.expires or 'no expiry'}){mark}")
        rows.append([_p(w.name), _p(w.id_number), _p(w.trade), _p(w.employer or "Own staff"),
                     _p("Yes" if w.id in inducted else "NO", P if w.id in inducted else BAD),
                     _p("\n".join(certs) or "None on file", P if certs else WARN)])
    t = Table(rows, colWidths=[35 * mm, 27 * mm, 22 * mm, 25 * mm, 15 * mm, W - 124 * mm], repeatRows=1)
    t.setStyle(GRID)
    return [t]


def _risks_flow(risks: list) -> list:
    out = []
    for r in risks:
        status = f"Approved by {r.approved_by} on {r.approved_at:%Y-%m-%d}" if r.approved_at else "NOT APPROVED"
        rows = [["Hazard", "Risk", "Controls"]] + [
            [_p(h["hazard"]), _p(h.get("risk", "")), _p("\n".join("• " + c for c in h.get("controls", [])))]
            for h in r.hazards]
        t = Table(rows, colWidths=[55 * mm, 12 * mm, W - 67 * mm], repeatRows=1)
        t.setStyle(GRID)
        out.append(KeepTogether([_p(r.activity, H2), _p(status, P if r.approved_at else WARN), t,
                                 _p("PPE: " + ", ".join(r.ppe), P)]))
    return out


def safety_file(company, site, *, date_from: date, date_to: date, docs: list, workers: list,
                inducted: set, risks: list, recs: list, chain: dict) -> bytes:
    by_kind: dict[str, list] = {}
    for r in recs:
        by_kind.setdefault(r.kind, []).append(r)
    docs_by: dict[str, list] = {}
    for d in docs:
        docs_by.setdefault(d.section, []).append(d)
    auto = {
        "risk_assessments": _risks_flow(risks),
        "workers": _workers_flow(workers, inducted, date.today()),
        "inductions": "induction", "task_sheets": "task_sheet", "toolbox_talks": "toolbox_talk",
        "inspections": "check", "incidents": "incident",
    }

    parts: list[bytes] = []
    # Cover and index
    cover = io.BytesIO()
    doc, frame = _doc(cover, "Health and safety file", company, site)
    idx = [["#", "Section", "Contents"]]
    for i, sec in enumerate(library.FILE_SECTIONS, 1):
        n_docs = len(docs_by.get(sec["key"], []))
        a = auto.get(sec["key"])
        n_rec = len(by_kind.get(a, [])) if isinstance(a, str) else None
        what = []
        if "upload" in sec["type"]:
            what.append(f"{n_docs} document{'s' * (n_docs != 1)}" if n_docs else "MISSING")
        if n_rec is not None:
            what.append(f"{n_rec} record{'s' * (n_rec != 1)}")
        elif sec["key"] == "workers":
            what.append(f"{len(workers)} workers")
        elif sec["key"] == "risk_assessments":
            what.append(f"{len(risks)} activities")
        idx.append([str(i), _p(sec["title"]), _p(", ".join(what), BAD if "MISSING" in what else P)])
    t = Table(idx, colWidths=[8 * mm, 110 * mm, W - 118 * mm], repeatRows=1)
    t.setStyle(GRID)
    doc.build(_header(company, site, "Health and safety file", f"Period {date_from} to {date_to}") + [
        _p(f"Principal contractor: {company.name}" + (f" · Reg {company.reg_no}" if company.reg_no else "")
           + (f" · COID {company.coid_no}" if company.coid_no else ""), P),
        _p(f"Site: {site.name} · {site.address}", P),
        _p(f"Client: {site.client or '-'} · Client's agent: {site.client_agent or '-'}", P),
        Spacer(1, 6), _p("Index", H2), t, Spacer(1, 8),
        _p(f"Record integrity: {chain['records']} records checked, "
           f"{'chain intact' if chain['ok'] else 'CHAIN BROKEN — investigate'} · head {chain['head'][:16]}… · "
           f"checked {chain['checked_at']}", SMALL),
        _p(f"Generated by {config.APP_NAME}. Each record carries the device time, the server time, GPS "
           "and a SHA-256 hash that links it to the record before it. Any change to a stored record breaks the chain.", SMALL),
    ], onFirstPage=frame, onLaterPages=frame)
    parts.append(cover.getvalue())

    for i, sec in enumerate(library.FILE_SECTIONS, 1):
        title = f"{i}. {sec['title']}"
        a = auto.get(sec["key"])
        if isinstance(a, list):
            flow = a
        elif isinstance(a, str):
            flow = []
            for r in sorted(by_kind.get(a, []), key=lambda r: (r.record_date, r.seq)):
                flow += record_flowables(r, company, site, header=False) + [Spacer(1, 10)]
        else:
            flow = []
        sec_docs = docs_by.get(sec["key"], [])
        if sec_docs:
            flow.append(_p("Documents in this section", H3))
            for d in sec_docs:
                flow.append(_p(f"• {d.title}" + (f" (expires {d.expires})" if d.expires else ""), P))
        elif "upload" in sec["type"] and not isinstance(a, (list, str)):
            flow.append(_p("No document uploaded for this section.", BAD))
        parts.append(_section_pdf(company, site, title, flow))
        for d in sec_docs:
            try:
                parts.append(files.read(d.file) if d.file.endswith(".pdf") else _image_page(d.file))
            except Exception:
                parts.append(_section_pdf(company, site, d.title, [_p("This document could not be added.", BAD)]))

    out = PdfWriter()
    for part in parts:
        try:
            for page in PdfReader(io.BytesIO(part)).pages:
                out.add_page(page)
        except Exception:
            continue
    buf = io.BytesIO()
    out.write(buf)
    return buf.getvalue()
