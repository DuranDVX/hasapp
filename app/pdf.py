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
