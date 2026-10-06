"""The consultant's documents: baseline risk assessment and the client's H&S specification.

The AI copies the documents into structured data (ai.ra_extract, ai.spec_extract).
This module checks them, turns the risk assessment into library items, and turns the
specification into duties the Site Board can track.
"""
import re
from datetime import date

from . import aes, library

PPE_NAMES = [("glove", "Gloves"), ("dust mask", "Dust mask"), ("respirat", "Dust mask / respirator"),
             ("footwear", "Safety boots"), ("boot", "Safety boots"), ("shoe", "Safety boots"),
             ("hearing", "Hearing protection"), ("earmuff", "Hearing protection"), ("ear plug", "Hearing protection"),
             ("ear protection", "Hearing protection"), ("head", "Hard hat"), ("hard hat", "Hard hat"),
             ("long pants", "Long pants"), ("eye", "Safety glasses"), ("glasses", "Safety glasses"),
             ("vest", "Reflective vest"), ("reflect", "Reflective vest"), ("harness", "Full body harness"),
             ("overall", "Overalls")]


def norm_ppe(items) -> list[str]:
    out = []
    for x in items or []:
        low = str(x).lower()
        name = next((n for k, n in PPE_NAMES if k in low), str(x).strip().capitalize())
        if name and name not in out:
            out.append(name)
    return out


def _clean(text: str) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return t[:1].upper() + t[1:] if t else t


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def ra_check(ra: dict, sig: dict | None, spec: dict | None, today: date) -> list[dict]:
    """Findings about the risk assessment itself. Each: {level: red|amber|info, text}."""
    flags = []
    h = ra.get("header", {})
    for r in ra.get("rows", []):
        n = r.get("item") or "?"
        bad = [f"{label} {_int(r.get(k))}" for k, label in (("c", "consequence"), ("l", "likelihood"),
                                                             ("rc", "revised consequence"), ("rl", "revised likelihood"))
               if not 1 <= _int(r.get(k)) <= 5]
        if bad:
            flags.append({"level": "red", "text": f"Row {n} ({_clean(r.get('activity'))[:40]}): " + " and ".join(bad)
                          + (" are" if len(bad) > 1 else " is") + " outside the 1-5 risk matrix."})
        c, l, rc, rl = (_int(r.get(k)) for k in ("c", "l", "rc", "rl"))
        if c and l and _int(r.get("rating")) != c * l:
            flags.append({"level": "amber", "text": f"Row {n}: rating {r.get('rating')} is not {c} x {l} = {c * l}."})
        if rc and rl and _int(r.get("rrating")) != rc * rl:
            flags.append({"level": "amber", "text": f"Row {n}: revised rating {r.get('rrating')} is not {rc} x {rl} = {rc * rl}."})
        if _int(r.get("rrating")) > _int(r.get("rating")):
            flags.append({"level": "amber", "text": f"Row {n}: the risk after controls is higher than before."})
        if library.band(rc, rl) == "High":
            flags.append({"level": "red", "text": f"Row {n}: still High after controls. More controls needed before work."})
        if not r.get("controls"):
            flags.append({"level": "red", "text": f"Row {n}: no control measures."})
    rows = ra.get("rows", [])
    if rows and not any(r.get("accepted") for r in rows):
        flags.append({"level": "amber", "text": "The acceptance-of-responsibility column is empty. "
                                                "The people assigned must accept (the app can collect these signatures)."})
    if not h.get("client_approved"):
        flags.append({"level": "amber", "text": "Client approval is not filled in."})
    team = h.get("team") or []
    need = (spec or {}).get("ra_team_required") or []
    if need and len(team) < len(need):
        flags.append({"level": "amber", "text": f"The risk assessment team has {len(team)} member(s). The specification "
                                                f"requires: {', '.join(need)}, all signing the assessment."})
    rd = parse_date(h.get("review_date"))
    if rd and rd < today:
        flags.append({"level": "red", "text": f"Review date {h.get('review_date')} has passed (reg 9(1)(e) review plan)."})
    if sig is not None:
        sigs = sig.get("signatures") or []
        if not sigs:
            flags.append({"level": "info", "text": "The PDF carries no digital signature."})
        for s in sigs:
            self_signed = s.get("signer") and s.get("signer") == s.get("issuer")
            if not s.get("intact"):
                flags.append({"level": "red", "text": "The document was changed after it was signed."})
            elif self_signed:
                flags.append({"level": "info", "text": f"Digitally signed by {_who(s['signer'])} on {s.get('signing_time', '')[:10]} "
                                                       "with a self-signed certificate: valid as a simple e-signature, "
                                                       "not an accredited advanced e-signature (AES)."})
            elif s.get("trusted"):
                flags.append({"level": "info", "text": f"Signed with an advanced e-signature by {_who(s['signer'])}."})
            else:
                flags.append({"level": "info", "text": f"Digitally signed by {_who(s['signer'])} (issuer {_who(s['issuer'])}); "
                                                       "certificate chain not verified."})
    if spec and spec.get("client_hazards"):
        pass  # coverage is a separate AI check (ai.hazard_coverage)
    return flags


def _who(name: str) -> str:
    m = re.search(r"Common Name: ([^,]+)", name or "")
    return m.group(1) if m else (name or "unknown")


MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}


def parse_date(text) -> date | None:
    t = str(text or "").strip().lower()
    if not t:
        return None
    try:
        return date.fromisoformat(t[:10])
    except ValueError:
        pass
    m = re.match(r"(?:(\d{1,2})\s+)?([a-z]+)\s+(\d{4})", t)
    if m and m.group(2) in MONTHS:
        return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1) or 28))
    return None


def ra_items(ra: dict) -> list[dict]:
    """Rows -> risk library items (one per row). The consultant's text stays as written."""
    h = ra.get("header", {})
    ref = f"RA {h.get('ra_no') or h.get('reference') or '?'}" + (f" rev {h['revision']}" if h.get("revision") else "")
    items = []
    for r in ra.get("rows", []):
        c, l, rc, rl = (_int(r.get(k)) for k in ("c", "l", "rc", "rl"))
        b, rb = library.band(c, l), library.band(rc, rl)
        hazard = {"hazard": _clean(r.get("hazards")), "consequence": _clean(r.get("consequence")),
                  "c": c, "l": l, "rating": _int(r.get("rating")), "band": b,
                  "rc": rc, "rl": rl, "rrating": _int(r.get("rrating")), "rband": rb,
                  "controls": [_clean(x) for x in r.get("controls", []) if _clean(x)],
                  "responsible": _clean(r.get("responsible")),
                  "risk": library.BAND_LEVEL.get(rb or b, "M")}
        items.append({"activity": _clean(r.get("activity")), "hazards": [hazard], "ppe": norm_ppe(r.get("ppe")),
                      "ref": f"{ref} · item {r.get('item') or len(items) + 1}"})
    return items


def ra_roles(items) -> list[str]:
    roles = []
    for it in items:
        for h in it.get("hazards", []):
            for part in re.split(r"\s*/\s*|,\s*", h.get("responsible") or ""):
                p = _clean(part.rstrip("."))
                if p and p.lower() not in [x.lower() for x in roles]:
                    roles.append(p)
    return roles


def spec_clean(spec: dict) -> dict:
    """Keep only known keys and sane values."""
    f = spec.get("frequencies") or {}
    freq = {k: (int(v) if isinstance(v, int) and 0 < v <= 400 else None) for k, v in f.items()}
    appts = [a for a in spec.get("required_appointments", []) if isinstance(a, dict)]
    for a in appts:   # map titles the AI could not place onto newer appointment keys
        if a.get("key") == "other":
            t = (a.get("title") or "").lower()
            for k, words in (("ladder_inspector", ("ladder",)), ("temporary_works_designer", ("temporary works designer",)),
                             ("temporary_works_supervisor", ("temporary works sup",)), ("machinery_inspector", ("machinery",)),
                             ("stacking_supervisor", ("stacking",)), ("scaffold_inspector", ("scaffold insp",))):
                if any(w in t for w in words):
                    a["key"] = k
    return {**{k: spec.get(k) for k in ("project", "client", "author", "date", "permits", "client_hazards",
                                        "ppe_minimum", "injury_categories", "acceptance_signatories",
                                        "ra_team_required", "key_rules", "required_documents",
                                        "required_inspections", "facilities")},
            "frequencies": freq, "required_appointments": appts}
