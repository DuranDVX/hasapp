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


def _raw(html, style=P):
    """A paragraph with trusted markup (callers escape the data parts)."""
    return Paragraph(html, style)


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


def _doc(buf, title: str, company, site, numbered: bool = True):
    def frame(c, d):
        c.saveState()
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawString(15 * mm, 10 * mm, f"{company.name} · {site.name if site else ''} · {title}")
        if numbered:
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


def _score(h: dict) -> str:
    """'12 Significant → 9 Significant' when the consultant scored it, else L/M/H."""
    if h.get("rating"):
        return f"{h['rating']} {h.get('band', '')} → {h.get('rrating', '')} {h.get('rband', '')}".strip()
    return h.get("risk", "")


def _task_sheet(rec) -> list:
    p, out = rec.payload, []
    for i, t in enumerate(p.get("tasks", []), 1):
        out.append(_p(f"Task {i}: {t['description']}" + (f" — {t['location']}" if t.get("location") else ""), H3))
        if not t.get("assessed"):
            out.append(_p("Not covered by an approved risk assessment. The safety officer must review this task.", WARN))
        rows, spans = [["Hazard", "Risk", "Controls"]], []
        for r in t.get("risks", []):
            spans.append(len(rows))
            rows.append([_p(r["activity"] + ("" if r.get("approved") else " (NOT APPROVED)"), H3), "", ""])
            for h in r.get("hazards", []):
                rows.append([_p(h["hazard"] + (f"\n→ {h['consequence']}" if h.get("consequence") else "")),
                             _p(_score(h)), _p("\n".join("• " + c for c in h.get("controls", [])))])
        if len(rows) > 1:
            tb = Table(rows, colWidths=[55 * mm, 22 * mm, W - 77 * mm], repeatRows=1)
            tb.setStyle(GRID)
            tb.setStyle(TableStyle([c for i in spans for c in (
                ("SPAN", (0, i), (-1, i)), ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f6f8fa")))]))
            out.append(tb)
        out.append(_raw("<b>PPE:</b> " + escape(", ".join(t.get("ppe", [])) or "-")))
        out.append(_raw("<b>Workers:</b> " + escape(", ".join(w["name"] for w in t.get("workers", [])) or "-")))
        if t.get("plant"):
            out.append(_raw("<b>Plant:</b> " + escape(", ".join(x["name"] for x in t["plant"]))))
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
    out = [_p(f"Site induction: {p['worker_name']}", H2), _p(p["induction_text"])]
    if p.get("consent"):
        out += [_p("Worker's agreement (e-signature and POPIA)", H3), _p(p.get("consent_text", ""))]
    return out


def _visitor(rec) -> list:
    p = rec.payload
    rows = [["Visitor", p["name"]], ["Company", p.get("company") or "-"], ["Phone", p.get("phone") or "-"],
            ["ID number", p.get("id_number") or "-"], ["Purpose", p.get("purpose") or "-"],
            ["Host", p.get("host") or "-"], ["Time in", p.get("time_in") or "-"],
            ["PPE issued", ", ".join(p.get("ppe", []))]]
    t = Table([[_p(a), _p(b)] for a, b in rows], colWidths=[35 * mm, W - 35 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8ced6")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [t, Spacer(1, 4), _p(p.get("rules_text", ""))]


def _appointment(rec) -> list:
    p = rec.payload
    a = p.get("appointee", {})
    out = [_p(f"Appointment: {p['title']}", H2),
           _p(f"In terms of regulation {p['reg']} of the Construction Regulations 2014 "
              "(Occupational Health and Safety Act 85 of 1993).", SMALL),
           _raw(f"<b>Appointee:</b> {escape(a.get('name', ''))}"),
           _raw(f"<b>From:</b> {escape(p.get('start_date') or str(rec.record_date))}"
                + (f" <b>to</b> {escape(p['end_date'])}" if p.get("end_date") else "")),
           _p("Duties", H3), _p(p["duties"])]
    if p.get("scope"):
        out += [_p("Scope", H3), _p(p["scope"])]
    out.append(_p("The appointee accepts this appointment by signing below.", P))
    if p.get("aes_required"):
        out.append(_p("This appointment is also issued for an advanced electronic signature (ECT Act s13(1)). "
                      "See the signed PDF in the safety file.", SMALL))
    return out


def _audit(rec) -> list:
    p = rec.payload
    out = [_p(f"Score: {p['score']}%" + (f" · Period {p['period']}" if p.get("period") else ""), H2)]
    rows = [["Item", "Regulation", "Result", "Note"]]
    for it in p["items"]:
        mark = {"ok": "OK", "gap": "GAP", "na": "N/A"}[it["result"]]
        rows.append([_p(it["title"]), _p(it["reg"], SMALL), _p(mark, BAD if it["result"] == "gap" else P), _p(it.get("note", ""))])
    t = Table(rows, colWidths=[62 * mm, 30 * mm, 15 * mm, W - 107 * mm], repeatRows=1)
    t.setStyle(GRID)
    out.append(t)
    if p.get("findings"):
        rows = [["Finding", "Action", "Responsible", "Due"]] + [
            [_p(f["finding"]), _p(f["action"]), _p(f["owner"]), _p(f["due"])] for f in p["findings"]]
        t = Table(rows, colWidths=[60 * mm, 60 * mm, 35 * mm, W - 155 * mm], repeatRows=1)
        t.setStyle(GRID)
        out += [_p("Findings and actions", H3), t]
    b = p.get("board") or {}
    if b.get("counts"):
        c = b["counts"]
        out.append(_p(f"Site Board at the time of the audit: {c.get('green', 0)} green, {c.get('amber', 0)} amber, "
                      f"{c.get('red', 0)} red.", SMALL))
    if p.get("notes"):
        out += [_p("Notes", H3), _p(p["notes"])]
    out.append(_p("Reg 5(1)(p): the audit report goes to the principal contractor within seven days.", SMALL))
    return out


def _audit_ack(rec) -> list:
    p = rec.payload
    return [_p(f"The principal contractor received the report of the audit of {p['audit_date']} "
               f"(score {p.get('score')}%).", P)]


def _investigation(rec) -> list:
    p = rec.payload
    out = [_p(f"Investigation of the incident of {p['incident_date']}", H2), _p(p.get("incident_summary", ""), SMALL),
           _p("Findings", H3), _p(p["findings"])]
    if p.get("root_causes"):
        out += [_p("Root causes", H3)] + [_p("• " + c) for c in p["root_causes"]]
    if p.get("actions"):
        rows = [["Corrective action", "Responsible", "Due"]] + [[_p(a["action"]), _p(a["owner"]), _p(a["due"])] for a in p["actions"]]
        t = Table(rows, colWidths=[100 * mm, 45 * mm, W - 145 * mm], repeatRows=1)
        t.setStyle(GRID)
        out += [_p("Corrective actions", H3), t]
    if p.get("reportable"):
        d, c = p.get("reported_dol", {}), p.get("reported_cf", {})
        out.append(_p(f"Reported to the Department of Employment and Labour on {d.get('date') or '-'} "
                      f"(ref {d.get('ref') or '-'}); to the Compensation Fund on {c.get('date') or '-'} "
                      f"(ref {c.get('ref') or '-'}).", P))
    else:
        out.append(_p("Not reportable: " + (p.get("not_reportable_reason") or "-"), P))
    return out


def _fmt(v):
    if v is None or v == "":
        return "-"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, dict):
        return v.get("name") or v.get("summary") or "-"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) or "-"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _form(rec) -> list:
    p = rec.payload
    rows = [[_p(f["label"]), _p(_fmt(f["value"]))] for f in p.get("fields", [])]
    t = Table(rows, colWidths=[60 * mm, W - 60 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8ced6")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [_p(f"{p.get('title', '')} · {p.get('reg', '')}", SMALL), t]


BODIES = {"task_sheet": _task_sheet, "toolbox_talk": _toolbox_talk, "check": _check,
          "incident": _incident, "induction": _induction, "visitor": _visitor,
          "appointment": _appointment, "audit": _audit, "audit_ack": _audit_ack,
          "investigation": _investigation, **{k: _form for k in library.FORMS}}


def verify_url(rec) -> str:
    return f"{config.PUBLIC_URL}/v/{rec.id}?h={rec.hash[:16]}"


def _qr(url: str, size: float = 22 * mm):
    import segno
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="png", scale=4, border=1)
    buf.seek(0)
    return Image(buf, width=size, height=size)


def _verify_block(rec, printed: bool) -> list:
    text = (f"Electronic original: record #{rec.seq}, hash {rec.hash[:16]}…. Scan the code or open "
            f"{verify_url(rec)} to check that this print matches the original.")
    if printed:
        text += (" Print-out of an electronic record (ECT Act ss15-18). Certified a true reproduction: "
                 "Name ____________________ Signature ____________________ Date __________")
    t = Table([[_qr(verify_url(rec)), _p(text, SMALL)]], colWidths=[26 * mm, W - 26 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return [Spacer(1, 4), t]


def record_flowables(rec, company, site, header=True, printed=False) -> list:
    title = records.KINDS[rec.kind]
    out = _header(company, site, title, f"{rec.record_date:%A %d %B %Y}") if header else \
        [_p(f"{title} · {rec.record_date:%a %d %b %Y}", H2)]
    return out + BODIES[rec.kind](rec) + _signatures(rec) + _proof(rec) + _verify_block(rec, printed)


def record_pdf(rec, company, site, printed=False) -> bytes:
    buf = io.BytesIO()
    doc, frame = _doc(buf, records.KINDS[rec.kind], company, site)
    doc.build(record_flowables(rec, company, site, printed=printed), onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()


def records_pdf(recs: list, company, site, title: str, printed=True) -> bytes:
    """Several full records in one PDF (the print pack)."""
    buf = io.BytesIO()
    doc, frame = _doc(buf, title, company, site)
    flow = _header(company, site, title, f"{len(recs)} record(s)")
    for i, r in enumerate(recs):
        if i:
            flow.append(PageBreak())
        flow += record_flowables(r, company, site, header=False, printed=printed)
    if not recs:
        flow.append(_p("No records in this period.", SMALL))
    doc.build(flow, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()


# ---------------------------------------------------------------- registers (print)

def register_pdf(company, site, title: str, subtitle: str, columns: list, rows: list, widths: list) -> bytes:
    """A landscape register: one row per entry, with signature images."""
    from reportlab.lib.pagesizes import landscape
    buf = io.BytesIO()
    page = landscape(A4)

    def frame(c, d):
        c.saveState()
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawString(12 * mm, 8 * mm, f"{company.name} · {site.name} · {title}")
        c.drawRightString(page[0] - 12 * mm, 8 * mm, f"{config.APP_NAME} · page {d.page} · printed {date.today()}")
        c.restoreState()
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=14 * mm, title=title)
    data = [columns] + [[c if not isinstance(c, str) else _p(c) for c in r] for r in rows]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(GRID)
    doc.build([_p(title, H1), _p(f"{company.name} · {site.name} · {subtitle}", P), Spacer(1, 4), t,
               Spacer(1, 6), _p("Each row is an electronic record with its own verification code in the record PDF. "
                                "Print-out of electronic records (ECT Act ss15-18).", SMALL)],
              onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()


def sig_img(name: str):
    return _img(name, 30 * mm, 10 * mm) if name else ""


# ---------------------------------------------------------------- Annexure 1

def annexure1(company, site, inc, inv, worker_info: dict) -> bytes:
    """Incident record in the layout of GAR Annexure 1 (recording and investigation)."""
    buf = io.BytesIO()
    doc, frame = _doc(buf, "Annexure 1", company, site)
    p = inc.payload
    def row(a, b):
        return [_p(a), _p(b)]
    t1 = [row("Employer / user", f"{company.name}\n{company.address}"),
          row("Workplace (site)", f"{site.name}\n{site.address}"),
          row("Date and time of incident", p.get("occurred_at") or str(inc.record_date)),
          row("Place where it happened", p.get("location") or "-"),
          row("Type", library.INCIDENT_TYPES.get(p.get("type"), p.get("type", ""))),
          row("Description of the incident", p.get("description") or "-"),
          row("Immediate actions", p.get("immediate_actions") or "-"),
          row("Witnesses", ", ".join(p.get("witnesses", [])) or "-")]
    people = []
    for x in p.get("people", []):
        info = worker_info.get(x.get("worker_id"), {})
        people.append(row(x.get("name") or "-", f"ID: {info.get('id_number') or '-'} · Occupation: {info.get('trade') or '-'}\n"
                                                 f"Injury: {x.get('injury') or '-'}\nTreatment: {x.get('treatment') or '-'}"))
    t2 = []
    if inv:
        q = inv.payload
        t2 = [row("Investigated on", str(inv.record_date)),
              row("Findings", q.get("findings", "")),
              row("Root causes", "\n".join(q.get("root_causes", [])) or "-"),
              row("Remedial / corrective actions", "\n".join(f"{a['action']} ({a['owner']}, due {a['due']})" for a in q.get("actions", [])) or "-"),
              row("Reportable (OHS Act s24)", "Yes" if q.get("reportable") else "No: " + (q.get("not_reportable_reason") or "-")),
              row("Reported to the provincial director", f"{q.get('reported_dol', {}).get('date') or '-'} ref {q.get('reported_dol', {}).get('ref') or '-'}"),
              row("Reported to the Compensation Commissioner (COIDA s39)", f"{q.get('reported_cf', {}).get('date') or '-'} ref {q.get('reported_cf', {}).get('ref') or '-'}")]
    def table(rows):
        t = Table(rows, colWidths=[60 * mm, W - 60 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8ced6")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t
    flow = _header(company, site, "Recording and investigation of an incident",
                   "General Administrative Regulations, Annexure 1 layout (keep at least 3 years)") + [
        _p("Incident", H2), table(t1)]
    if people:
        flow += [_p("Persons injured or involved", H2), table(people)]
    flow += [_p("Investigation (within 7 days, GAR 9)", H2),
             table(t2) if t2 else _p("NOT YET INVESTIGATED. GAR 9 requires an investigation within 7 days.", BAD)]
    flow += _signatures(inc) + _proof(inc) + _verify_block(inc, True)
    if inv:
        flow += [_p("Investigation signatures", H3)] + _signatures(inv)[1:] + _proof(inv)
    flow.append(_p("Check this layout against the official Annexure 1 form before you submit it.", SMALL))
    doc.build(flow, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()


# ---------------------------------------------------------------- documents for AES signing

def _signing_block(signers: list) -> list:
    rows = [["Name and capacity", "Signature (AES or handwritten)", "Date"]]
    for s in signers:
        rows.append([_p(s), "", ""])
    t = Table(rows, colWidths=[70 * mm, 75 * mm, W - 145 * mm], rowHeights=[None] + [18 * mm] * len(signers))
    t.setStyle(GRID)
    return [Spacer(1, 8), _p("Signatures", H2), t,
            _p("Sign with an advanced electronic signature from an accredited provider (ECT Act s13(1)), "
               "or print, sign by hand and upload the scan.", SMALL)]


def aes_document(company, site, title: str, body: list, signers: list, ref: str) -> bytes:
    buf = io.BytesIO()
    doc, frame = _doc(buf, title, company, site)
    flow = _header(company, site, title, f"Document {ref} · issued {date.today()}") + body + _signing_block(signers)
    doc.build(flow, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()


def mandatary_agreement_body(company, site, c) -> list:
    clauses = [
        f"This agreement is made between {company.name} (the principal contractor) and {c.name} "
        f"(the mandatary), for the work described below on the site {site.name}.",
        f"Scope of work: {c.scope or '(to be described)'}",
        "1. The mandatary is an employer in its own right. It accepts responsibility to comply with the "
        "Occupational Health and Safety Act 85 of 1993 and the Construction Regulations 2014 for its employees "
        "and its work on the site.",
        "2. The mandatary must: comply with the client's health and safety specification and the principal "
        "contractor's health and safety plan; give the principal contractor its own health and safety plan and "
        "file before work starts (reg 7(2)); keep its COID registration in good standing; appoint the competent "
        "persons the regulations require for its work; make sure its employees are inducted, have valid medical "
        "certificates (Annexure 3), are trained and have the correct PPE; report every incident to the principal "
        "contractor at once; and take part in site audits and give access to its records.",
        "3. The principal contractor must: give the mandatary the relevant parts of the health and safety "
        "specification and site information; co-ordinate health and safety between contractors; and audit the "
        "mandatary at least every 30 days (reg 7(1)(c)(vii)).",
        "4. This agreement applies from the date of the last signature until the mandatary's work on the site "
        "is complete.",
    ]
    return [_p("Agreement in terms of section 37(2) of the Occupational Health and Safety Act 85 of 1993", H2)] + \
        [_p(x) for x in clauses] + [_p("DRAFT template: legal review pending.", SMALL)]


def excavation_decision_body(f: dict) -> list:
    rows = [["Excavation (location)", f.get("location", "")], ["Depth (m)", f.get("depth", "")],
            ["Soil conditions observed", f.get("soil", "")], ["Decision", f.get("decision", "")],
            ["Conditions / controls", f.get("conditions", "")]]
    t = Table([[_p(a), _p(b)] for a, b in rows], colWidths=[55 * mm, W - 55 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8ced6")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [_p("Decision on excavation stability (Construction Regulations 2014, reg 13(2)(b)(ii)(bb))", H2),
            _p("Where uncertainty about soil stability exists, the decision of a professional engineer or technologist "
               "is decisive and must be noted in writing and signed by both the competent person and the engineer "
               "or technologist.", SMALL), t]


def text_body(text: str) -> list:
    return [_p(text)]


# ---------------------------------------------------------------- safety file

def _section_pdf(company, site, title: str, flow: list) -> bytes:
    buf = io.BytesIO()
    doc, frame = _doc(buf, "Health and safety file", company, site, numbered=False)
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
        rows = [["Hazard → consequence", "Risk", "Controls", "Responsible"]] + [
            [_p(h["hazard"] + (f"\n→ {h['consequence']}" if h.get("consequence") else "")), _p(_score(h)),
             _p("\n".join("• " + c for c in h.get("controls", []))), _p(h.get("responsible", ""))]
            for h in r.hazards]
        t = Table(rows, colWidths=[50 * mm, 22 * mm, W - 102 * mm, 30 * mm], repeatRows=1)
        t.setStyle(GRID)
        out.append(KeepTogether([_p(r.activity + (f"  ({r.ref})" if r.ref else ""), H2),
                                 _p(status, P if r.approved_at else WARN), t, _p("PPE: " + ", ".join(r.ppe), P)]))
    return out


AES_SECTION = {"appointment": "appointments", "mandatary_agreement": "subcontractors",
               "excavation_decision": "inspections", "hoist_book": "inspections",
               "notification": "notification", "other": "appointments"}


def _contractors_flow(contractors: list) -> list:
    if not contractors:
        return [_p("No contractors recorded for this site.", SMALL)]
    rows = [["Contractor", "Scope", "Appointed", "COID expires", "H&S plan"]]
    for c in contractors:
        rows.append([_p(f"{c.name}\n{c.reg_no}"), _p(c.scope), _p(str(c.appointed_on or "NO")),
                     _p(str(c.coid_expires or "MISSING"), P if c.coid_expires and c.coid_file else BAD),
                     _p("Approved" if c.hs_plan_ok else "Not approved", P if c.hs_plan_ok else WARN)])
    t = Table(rows, colWidths=[45 * mm, 60 * mm, 22 * mm, 25 * mm, W - 152 * mm], repeatRows=1)
    t.setStyle(GRID)
    return [_p("List of contractors on site (reg 7(1)(f))", H3), t]


def safety_file(company, site, *, date_from: date, date_to: date, docs: list, workers: list,
                inducted: set, risks: list, recs: list, chain: dict, aes_docs: list = (),
                contractors: list = ()) -> bytes:
    by_kind: dict[str, list] = {}
    for r in recs:
        by_kind.setdefault(r.kind, []).append(r)
    docs_by: dict[str, list] = {}
    for d in docs:
        docs_by.setdefault(d.section, []).append(d)
    aes_by: dict[str, list] = {}
    for a in aes_docs:
        aes_by.setdefault(AES_SECTION.get(a.kind, "appointments"), []).append(a)
    auto = {
        "risk_assessments": _risks_flow(risks),
        "workers": _workers_flow(workers, inducted, date.today()),
        "subcontractors": _contractors_flow(list(contractors)),
        "inductions": ("induction", "visitor"), "task_sheets": ("task_sheet",), "toolbox_talks": ("toolbox_talk",),
        "inspections": ("check",), "incidents": ("incident", "investigation"),
        "appointments": ("appointment", "ra_acceptance"), "audits": ("audit", "audit_ack"),
        "registers": tuple(k for k in library.FORMS if k != "ra_acceptance"),
    }
    n_kinds = lambda a: sum(len(by_kind.get(k, [])) for k in a)

    parts: list[bytes] = []
    # Cover and index
    cover = io.BytesIO()
    doc, frame = _doc(cover, "Health and safety file", company, site, numbered=False)
    idx = [["#", "Section", "Contents"]]
    for i, sec in enumerate(library.FILE_SECTIONS, 1):
        n_docs = len(docs_by.get(sec["key"], [])) + len([x for x in aes_by.get(sec["key"], []) if x.status == "signed"])
        a = auto.get(sec["key"])
        n_rec = n_kinds(a) if isinstance(a, tuple) else None
        what = []
        if n_docs:
            what.append(f"{n_docs} document{'s' * (n_docs != 1)}")
        elif sec["type"] == "upload":
            what.append("MISSING")
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
            flow = list(a)
        elif isinstance(a, tuple):
            flow = []
            for r in sorted((r for k in a for r in by_kind.get(k, [])), key=lambda r: (r.record_date, r.seq)):
                flow += record_flowables(r, company, site, header=False) + [Spacer(1, 10)]
        else:
            flow = []
        sec_aes = aes_by.get(sec["key"], [])
        if sec_aes:
            flow.append(_p("Documents signed with an advanced electronic signature or wet ink", H3))
            for x in sec_aes:
                status = (f"signed ({'AES' if x.method == 'aes' else 'wet ink'}) {x.signed_at:%Y-%m-%d}: {x.note}"
                          if x.status == "signed" else "AWAITING SIGNATURE")
                flow.append(_p(f"• {x.title}: {status}", P if x.status == "signed" else BAD))
        sec_docs = docs_by.get(sec["key"], [])
        if sec_docs:
            flow.append(_p("Documents in this section", H3))
            for d in sec_docs:
                flow.append(_p(f"• {d.title}" + (f" (expires {d.expires})" if d.expires else ""), P))
        elif "upload" in sec["type"] and not isinstance(a, (list, tuple)) and not sec_aes:
            flow.append(_p("No document uploaded for this section.", BAD))
        parts.append(_section_pdf(company, site, title, flow))
        for x in sec_aes:
            if x.status == "signed" and x.signed_file:
                try:
                    parts.append(files.read(x.signed_file) if x.signed_file.endswith(".pdf") else _image_page(x.signed_file))
                except Exception:
                    parts.append(_section_pdf(company, site, x.title, [_p("This document could not be added.", BAD)]))
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
    _stamp_pages(out)
    buf = io.BytesIO()
    out.write(buf)
    return buf.getvalue()


def _stamp_pages(writer: PdfWriter) -> None:
    """Number every page of the merged file: 'page 3 of 41'."""
    from reportlab.pdfgen import canvas
    n = len(writer.pages)
    for i, page in enumerate(writer.pages, 1):
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawRightString(w - 15 * mm, 6 * mm, f"{config.APP_NAME} · page {i} of {n}")
        c.save()
        page.merge_page(PdfReader(io.BytesIO(buf.getvalue())).pages[0])


# ---------------------------------------------------------------- incident pack (flash report, Annexure 1, investigation form)

BOX = TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa5b1")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                  ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)])
SECTION = ParagraphStyle("sec", parent=H3, backColor=colors.HexColor("#e9edf2"), borderPadding=3, spaceBefore=8)


def _letterhead(company, consultants: list) -> list:
    left = [_img(company.logo_file, 38 * mm, 16 * mm), _p(company.name, SMALL)] if company.logo_file \
        else [_p(company.name, H2)]
    cons = [c for c in (consultants or []) if c.get("name")][:2]
    blocks = [[_p(c.get("firm") or "H&S consultant", SMALL), _p(c["name"], P), _p(c.get("reg") or "", SMALL),
               _p(" · ".join(x for x in (c.get("phone"), c.get("email")) if x), SMALL)] for c in cons]
    cells = [left] + blocks + [""] * (2 - len(blocks))
    t = Table([cells], colWidths=[W * 0.34, W * 0.33, W * 0.33])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.HexColor("#122433"))]))
    return [t, Spacer(1, 6)]


def _kv(rows: list, w1=55) -> Table:
    t = Table([[_p(a), _p(b if b not in (None, "") else "-")] for a, b in rows], colWidths=[w1 * mm, W - w1 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8ced6")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f6f8"))]))
    return t


def _yn(v) -> str:
    return "-" if v is None else ("Yes" if v else "No")


def _checklist(items: list, chosen: list, cols: int = 3) -> Table:
    """Boxes with an X for the chosen items, like the paper form."""
    cells = []
    for it in items:
        mark = it in (chosen or [])
        cells.append([_raw("<b>X</b>", ParagraphStyle("x", parent=P, alignment=1)) if mark else "", _p(it, SMALL)])
    rows = []
    for i in range(0, len(cells), cols):
        chunk = cells[i:i + cols] + [["", ""]] * (cols - len(cells[i:i + cols]))
        rows.append([x for pair in chunk for x in pair])
    cw = W / cols
    t = Table(rows, colWidths=[7 * mm, cw - 7 * mm] * cols)
    st = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("FONTSIZE", (0, 0), (-1, -1), 8)]
    for c in range(cols):
        st.append(("BOX", (2 * c, 0), (2 * c, -1), 0.6, colors.HexColor("#5d6c7b")))
        st.append(("INNERGRID", (2 * c, 0), (2 * c, -1), 0.6, colors.HexColor("#5d6c7b")))
    t.setStyle(TableStyle(st))
    return t


def _bullets(text_or_list) -> list:
    items = text_or_list if isinstance(text_or_list, list) else [x.strip(" •-") for x in str(text_or_list or "").splitlines()]
    return [_p("• " + x) for x in items if x]


def _sig_line(rec, role_hint: str = "") -> list:
    if not rec or not rec.signatures:
        return [_p("Signature: ______________________   Date: __________", P)]
    g = next((g for g in rec.signatures if role_hint and g.role == role_hint), rec.signatures[0])
    t = Table([[_p(f"{g.name} ({g.role})", P), _img(g.image_file, 40 * mm, 12 * mm), _p(g.signed_at[:16].replace("T", " "), SMALL)]],
              colWidths=[70 * mm, 50 * mm, W - 120 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return [t]


def flash_report_flow(company, site, inc, inv, close, consultants) -> list:
    p = inc.payload
    q = inv.payload if inv else {}
    when = p.get("occurred_at") or str(inc.record_date)
    date_s, _, time_s = when.partition(" ")
    out = _letterhead(company, consultants) + [
        _p("ACCIDENT / INCIDENT FLASH REPORT", ParagraphStyle("t", parent=H1, alignment=1)),
        _p("Prompt reporting means incidents are investigated thoroughly, so they do not happen again and workers stay protected.", SMALL),
        _p("1. Basic information", SECTION),
        _kv([("Project / site name", site.name), ("Date of incident", date_s), ("Time of incident", time_s or "-"),
             ("Location", p.get("location") or site.address), ("Reported by", p.get("reported_by") or inc.created_name),
             ("Contact number", p.get("reporter_contact"))]),
        _p("2A. Incident details", SECTION),
        _kv([("Type of incident", (p.get("title") or "") + f" ({library.INCIDENT_TYPES.get(p.get('type'), '')})")])]
    for x in p.get("people") or [{}]:
        m = x.get("medical") or {}
        out += [Spacer(1, 3), _kv([("Injured / affected person", x.get("name")), ("ID number", x.get("id_number")),
                                   ("Occupation", x.get("occupation")), ("Injury description", x.get("injury")),
                                   ("Immediate medical action", x.get("treatment"))]),
                _p("2B. Medical report findings", SECTION),
                _kv([("Clinic / hospital description", m.get("clinic")), ("Pre-existing defect or disease", m.get("pre_existing")),
                     ("Referred for physiotherapy", _yn(m.get("physio"))), ("Unfit for work", _yn(m.get("unfit"))),
                     ("Possible date fit for light duty", m.get("light_duty_date")), ("Date of resumption", m.get("resumption_date"))])]
    out += [_p("3. Incident description", SECTION)] + [_p(par) for par in (p.get("description") or "").split("\n\n") if par.strip()]
    out += [_p("4. Immediate actions taken", SECTION)] + (_bullets(p.get("immediate_actions")) or [_p("-")])
    out += [_p("5. Corrective action", SECTION)]
    out += [_p(f"• {a['action']}" + (f" ({a['owner']}" + (f", by {a['due']}" if a.get('due') else "") + ")" if a.get("owner") else ""))
            for a in q.get("actions", [])] or [_p("Investigation pending.", WARN)]
    out += [_p("6. Close-out requirements", SECTION), _p(q.get("close_out") or "To be set by the investigation.")]
    if close:
        out.append(_p(f"Closed out on {close.record_date}: " + str(next((f['value'] for f in close.payload.get('fields', []) if f['k'] == 'notes'), "")), P))
    out += [_p("Prepared by", SECTION),
            _kv([("Name", q.get("investigator") or inc.created_name), ("Position", q.get("designation") or "Incident investigator (GAR 9(2))"),
                 ("Date", str(inv.record_date) if inv else str(inc.record_date))])]
    docs = ["Annexure 1", "Incident report and investigation"]
    return out, docs


def annexure1_flow(company, site, inc, inv, person: dict, employer_sig_rec=None) -> list:
    p, q = inc.payload, (inv.payload if inv else {})
    hdr = ParagraphStyle("ah", parent=H2, alignment=1, spaceAfter=0)
    out = [_p("RECORDING AND INVESTIGATION OF INCIDENTS – ANNEXURE 1", hdr),
           _p("OCCUPATIONAL HEALTH AND SAFETY ACT NO 85 OF 1993 · GENERAL ADMINISTRATIVE REGULATIONS",
              ParagraphStyle("as", parent=SMALL, alignment=1)),
           _p("A. RECORDING OF INCIDENT", SECTION)]
    when = p.get("occurred_at") or str(inc.record_date)
    d, _, t = when.partition(" ")
    m = person.get("medical") or {}
    out += [_kv([("1. Name of employer", company.name), ("2. Name of affected person", person.get("name")),
                 ("3. Date of incident", d), ("4. Time of incident", t or "-"),
                 ("Date of resumption", m.get("resumption_date") or m.get("light_duty_date"))], 60),
            _p("5. Part of body affected", H3), _checklist(library.BODY_PARTS, person.get("body_parts"), 5),
            _p("6. Effect on person", H3), _checklist(library.EFFECTS, person.get("effects"), 4)]
    if person.get("effect_other"):
        out.append(_p(f"Other (specify): {person['effect_other']}", P))
    out += [_p("7. Expected period of disablement", H3),
            _checklist(library.DISABLEMENT, [person.get("disablement")], 3),
            _kv([("8. Description of occupational disease", "-"),
                 ("9. Machine / process involved / type of work performed / exposure", p.get("work_type")),
                 ("10. Reported to the Compensation Commissioner?",
                  f"Yes, {q['reported_cf']['date']} (ref {q['reported_cf'].get('ref') or '-'})" if q.get("reported_cf", {}).get("date") else "No"),
                 ("11. Reported to the Provincial Director?",
                  f"Yes, {q['reported_dol']['date']} (ref {q['reported_dol'].get('ref') or '-'})" if q.get("reported_dol", {}).get("date") else "No")], 75),
            _p("B. INVESTIGATION OF THE ABOVE INCIDENT BY A PERSON DESIGNATED THERETO", SECTION)]
    if inv:
        out += [_kv([("1. Name of investigator", q.get("investigator") or (inv.signatures[0].name if inv.signatures else "")),
                     ("2. Date of investigation", str(inv.record_date)),
                     ("3. Designation of investigator", q.get("designation") or "GAR 9(2)"),
                     ("4. Short description of incident", q.get("short_description") or p.get("title")),
                     ("5. Suspected cause of incident", q.get("suspected_cause") or "; ".join(q.get("root_causes", []))),
                     ("6. Recommended steps to prevent a recurrence", "; ".join(a["action"] for a in q.get("actions", [])))], 60)]
        out += _sig_line(inv, "investigator")
        out += [_p("C. ACTION TAKEN BY EMPLOYER TO PREVENT THE RECURRENCE OF A SIMILAR INCIDENT", SECTION),
                _p(q.get("employer_action") or "-")] + _sig_line(employer_sig_rec or inv)
        out += [_p("D. REMARKS BY HEALTH AND SAFETY COMMITTEE", SECTION), _p(q.get("committee_remarks") or "-"),
                _p("Signature: ______________________   Date: __________", P)]
    else:
        out.append(_p("Not yet investigated. GAR 9 requires an investigation within 7 days.", BAD))
    return out


def investigation_form_flow(company, site, inc, inv) -> list:
    p, q = inc.payload, (inv.payload if inv else {})
    people = p.get("people") or []
    out = [_p("INCIDENT / ACCIDENT REPORT AND INVESTIGATION", ParagraphStyle("it", parent=H2, alignment=1)),
           _p("REPORTING", SECTION),
           _kv([("Name", p.get("reported_by") or inc.created_name), ("Site", site.name),
                ("Day, date and time of incident", p.get("occurred_at") or str(inc.record_date)),
                ("Day, date and time of reporting", inc.device_time[:16].replace("T", " ") or str(inc.received_at)[:16])]),
           _p("DAMAGE / INJURY", SECTION), _checklist(library.DAMAGE, p.get("damage"), 3),
           _p("Description of damage / injury: " + ("; ".join(f"{x.get('name')}: {x.get('injury')}" for x in people) or p.get("damage_note") or "-"), P),
           _p("General agencies", H3), _checklist(library.AGENCIES_GENERAL, q.get("agencies_general"), 4),
           _p("Occupational hygiene agencies", H3), _checklist(library.AGENCIES_HYGIENE, q.get("agencies_hygiene"), 4),
           _p(f"Was this the person's normal work? {_yn(q.get('normal_work'))}", P),
           _p("CAUSES (IMMEDIATE AND BASIC)", SECTION),
           _p("Unsafe acts", H3), _checklist(library.UNSAFE_ACTS, q.get("unsafe_acts"), 2),
           _p("Unsafe conditions", H3), _checklist(library.UNSAFE_CONDITIONS, q.get("unsafe_conditions"), 2),
           _p("Personal factors", H3), _checklist(library.PERSONAL_FACTORS, q.get("personal_factors"), 3),
           _p("Job factors", H3), _checklist(library.JOB_FACTORS, q.get("job_factors"), 2),
           _p("CONTROL STEPS TO PREVENT A RECURRENCE", SECTION),
           _p("Personal factors", H3), _checklist(library.CONTROL_PERSONAL, q.get("control_personal"), 2),
           _p("Job factors", H3), _checklist(library.CONTROL_JOB, q.get("control_job"), 3)]
    if q.get("findings"):
        out += [_p("Investigation findings", H3), _p(q["findings"])]
    out += [Spacer(1, 6), _p("Signature of incident / accident investigator", H3)] + _sig_line(inv, "investigator")
    return out


def incident_pack(company, site, inc, inv, close, consultants, id_files: list, include: tuple = ("flash", "annexure", "form", "id", "photos")) -> bytes:
    """One PDF: flash report, Annexure 1 per person, investigation form, ID copies, photos with captions."""
    flow, docs = flash_report_flow(company, site, inc, inv, close, consultants)
    p = inc.payload
    photos = [(ph, (p.get("photo_captions") or [""] * 20)[i] if i < len(p.get("photo_captions") or []) else "")
              for i, ph in enumerate(p.get("photos") or []) if _file_of(ph)]
    if id_files and "id" in include:
        docs.append("Injured person's ID documentation")
    if photos and "photos" in include:
        docs.append(f"Photographs ({len(photos)})")
    flow += [_p("Documents collected", SECTION)] + [_p("• " + d) for d in docs] + _proof(inc)
    parts = []
    if "flash" in include:
        parts.append(flow)
    if "annexure" in include:
        for person in (p.get("people") or [{}]):
            parts.append(_letterhead(company, consultants) + annexure1_flow(company, site, inc, inv, person))
    if "form" in include:
        parts.append(_letterhead(company, consultants) + investigation_form_flow(company, site, inc, inv))
    if "photos" in include and photos:
        ph_flow = _letterhead(company, consultants) + [_p("Photographs", H1)]
        for ph, cap in photos:
            ph_flow += [KeepTogether([_p(cap or "Photo", H3), _img(_file_of(ph), W, 105 * mm), Spacer(1, 6)])]
        parts.append(ph_flow)
    buf = io.BytesIO()
    doc, frame = _doc(buf, "Incident report", company, site)
    story = []
    for i, part in enumerate(parts):
        if i:
            story.append(PageBreak())
        story += part
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    out = PdfWriter()
    for page in PdfReader(io.BytesIO(buf.getvalue())).pages:
        out.add_page(page)
    if "id" in include:   # ID copies go after the forms, as in the consultant's pack
        for name in id_files:
            try:
                data = files.read(name) if name.endswith(".pdf") else _image_page(name)
                for page in PdfReader(io.BytesIO(data)).pages:
                    out.add_page(page)
            except Exception:
                continue
    res = io.BytesIO()
    out.write(res)
    return res.getvalue()


# ---------------------------------------------------------------- H&S plan (CR 7(1)(a))

def _plan_text(text: str) -> list:
    """The plan's light markup: '## ' sub-heading, '- ' bullet, other lines paragraphs.
    '[to complete: ...]' gaps print in amber so the reviewer sees them."""
    import re
    mark = lambda t: re.sub(r"\[to complete[^\]]*\]", lambda m: f'<font color="#b45d00">{m.group(0)}</font>', escape(t))
    bullet = ParagraphStyle("pb", parent=P, leftIndent=10, firstLineIndent=-7)
    out = []
    for line in str(text or "").splitlines():
        t = line.strip()
        if not t:
            continue
        if t.startswith("## "):
            out.append(_raw(mark(t[3:]), H3))
        elif t.startswith(("- ", "• ", "* ")):
            out.append(_raw("• " + mark(t[2:].strip()), bullet))
        else:
            out.append(_raw(mark(t)))
    return out


def _table(header: list, rows: list, widths: list) -> Table:
    t = Table([[_p(h, SMALL) for h in header]] + [[_p(c) for c in r] for r in rows], colWidths=widths, repeatRows=1)
    t.setStyle(GRID)
    return t


def _plan_data_flow(key: str, data: dict, company) -> list:
    st, sp = data["site"], data.get("client_spec") or {}
    if key == "project":
        cons = "; ".join(f"{c['name']} ({c.get('firm') or ''}{', ' + c['reg'] if c.get('reg') else ''})" for c in st["consultants"])
        return [_kv([("Project / site", st["name"]), ("Address", st["address"]), ("Client", st["client"]),
                     ("Client's agent", st["client_agent"]), ("Principal contractor", company.name),
                     ("Contract period", f"{st['start_date'] or '[to complete]'} to {st['end_date'] or '[to complete]'}"),
                     ("Client H&S specification", " · ".join(x for x in (sp.get("project"), sp.get("author"), sp.get("date")) if x)
                      or "[to complete: load the client's specification]"),
                     ("H&S consultant", cons), ("Work on this site", ", ".join(st["work_types"])),
                     ("Contractors", ", ".join(c["name"] for c in data["contractors"])),
                     ("Workers on the register", str(st["workers_on_register"]))])]
    if key == "legal":
        laws = library.HS_PLAN_LAWS + [f"The client's health and safety specification ({sp.get('author') or 'author'}, "
                                       f"{sp.get('date') or 'date'})" if sp else "The client's health and safety specification"]
        if any("Scaffold" in w for w in st["work_types"]):
            laws.append("SANS 10085-1: the design, erection, use and inspection of access scaffolding")
        return [_p("This plan complies with, and must be read with:")] + _bullets(laws)
    if key == "organisation":
        return [_p("Appointments", H3), _table(["Appointment", "Regulation", "Appointed person"],
                                              [[a["title"], a["reg"], a["who"] or "To be appointed in writing"] for a in data["appointments"]],
                                              [80 * mm, 30 * mm, W - 110 * mm])]
    if key == "risk":
        rows = []
        for r in data["risk_assessment"]:
            hz = r["hazards"]
            rows.append([r["activity"], "; ".join(h["hazard"] or "" for h in hz),
                         "/".join(sorted({h.get("risk") or "" for h in hz})),
                         "; ".join(c for h in hz for c in (h["controls"] or [])[:2])])
        return [_p("Risk assessment summary (the full assessment is in the H&S file)", H3),
                _table(["Activity", "Main hazards", "Risk", "Key controls"], rows or [["[to complete]", "", "", ""]],
                       [38 * mm, 52 * mm, 12 * mm, W - 102 * mm])]
    if key == "inspections":
        return [_p("Inspection schedule", H3), _table(["What", "How often", "Regulation"],
                                                      [[i["what"], i["how_often"], i["ref"]] for i in data["inspections"]],
                                                      [90 * mm, 50 * mm, W - 140 * mm])]
    if key == "ppe":
        return [_p("Minimum PPE on site", H3)] + _bullets(data["ppe_minimum"])
    if key == "emergency":
        return [_p("Emergency details", H3), _p(st["emergency_details"] or "[to complete: hospital, ambulance, fire, police "
                                                                              "and site emergency numbers]")]
    if key == "records":
        return [_p("Sections of the H&S file", H3)] + _bullets(data["registers"])
    return []


def hs_plan(company, site, text: dict, data: dict, signers: list, ref: str, draft: bool, version: int) -> bytes:
    buf = io.BytesIO()
    title = "Site health and safety plan"
    doc, frame = _doc(buf, title, company, site)

    def page(c, d):
        frame(c, d)
        if draft:
            c.saveState()
            c.setFont("Helvetica-Bold", 70)
            c.setFillColor(colors.Color(0.85, 0.42, 0.11, alpha=0.12))
            c.translate(A4[0] / 2, A4[1] / 2)
            c.rotate(45)
            c.drawCentredString(0, 0, "DRAFT")
            c.restoreState()

    st, sp = data["site"], data.get("client_spec") or {}
    flow = _letterhead(company, st["consultants"]) + [
        Spacer(1, 30 * mm), _p("SITE-SPECIFIC HEALTH AND SAFETY PLAN", ParagraphStyle("cv", parent=H1, fontSize=22, leading=26)),
        _p(st["name"], ParagraphStyle("cv2", parent=H2, fontSize=15)), Spacer(1, 8 * mm),
        _kv([("Principal contractor", company.name), ("Client", st["client"]), ("Site address", st["address"]),
             ("Version", f"{version} · {data['today']}"), ("Status", "DRAFT for review" if draft else "Issued for signature"),
             ("Document", ref)]),
        Spacer(1, 8 * mm),
        _p("Prepared in terms of Construction Regulation 7(1)(a) of the Construction Regulations, 2014, and based on the "
           f"client's health and safety specification{' by ' + sp['author'] if sp.get('author') else ''}"
           f"{' dated ' + sp['date'] if sp.get('date') else ''}. A competent person reviews this plan before it is issued, "
           "and the client approves it before work starts (CR 5(1)(l))."),
        _p(f"Drafted with {config.APP_NAME} from the client's specification, the site details and the risk assessment. "
           "Text marked [to complete] still needs the contractor's input.", SMALL),
        PageBreak(), _p("Contents", H1)]
    flow += [_p(f"{i}. {t}") for i, (k, t, _) in enumerate(library.HS_PLAN_SECTIONS, 1)]
    flow.append(PageBreak())
    for i, (k, t, src) in enumerate(library.HS_PLAN_SECTIONS, 1):
        flow.append(_p(f"{i}. {t}", H2))
        if "ai" in src:
            flow += _plan_text(text.get(k)) or [_p("[to complete]", WARN)]
        if "data" in src:
            flow += _plan_data_flow(k, data, company)
    flow += [PageBreak(), _p("Approval", H1),
             _p("By signing, the principal contractor commits to carry out this plan; the competent person confirms the "
                "review; and the client approves the plan for use on this site (CR 5(1)(l), 7(1)(a)).")]
    flow += _signing_block(signers)
    doc.build(flow, onFirstPage=page, onLaterPages=page)
    return buf.getvalue()
