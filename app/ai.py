"""The AI steps. Each returns a draft that a person checks before it is signed.

Safety rule (the same idea as the QuoteBakkie price rule): the AI selects
hazards and controls only from the site's risk library, by id. The server
copies the hazard text from the database. A task with no match goes to
"unmatched" for the safety officer. The AI never writes a control into a
task sheet.
"""
import json

from . import library, llm


def _ids_schema(ids: list[str]) -> dict:
    """Constrain ids to the allowed list when there is one."""
    item = {"type": "string", "enum": ids} if ids else {"type": "string"}
    return {"type": "array", "items": item}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props),
            "additionalProperties": False}


# ---------------------------------------------------------------- task sheet

TASK_SYSTEM = """You turn a foreman's spoken description of today's work into a daily task sheet for a South African construction site.

Rules:
- Split the work into tasks. Each task is one activity at one location.
- Match each task to one or more risk assessment items by id, from the list given. Pick every item that applies (for example, brickwork on a scaffold matches brickwork AND scaffolding).
- If no item covers a task, put the task in "unmatched" with a short reason. Never invent hazards, controls or PPE.
- Assign workers by id. Speech recognition misspells names: match the closest name or trade. "Everyone" or "all the guys" means all workers listed. If you are not sure who does a task, leave worker_ids empty and add a question.
- Assign plant by id when the foreman names a machine.
- The foreman may mix English, Afrikaans and other South African languages. Write descriptions in plain English.
- Put anything else useful (weather, deliveries, visitors) in notes. Keep it short."""


def task_sheet(transcript: str, risks: list[dict], workers: list[dict], plant: list[dict]) -> dict:
    schema = _obj({
        "tasks": {"type": "array", "items": _obj({
            "description": {"type": "string"}, "location": {"type": "string"},
            "risk_item_ids": _ids_schema([r["id"] for r in risks]),
            "worker_ids": _ids_schema([w["id"] for w in workers]),
            "plant_ids": _ids_schema([p["id"] for p in plant])})},
        "unmatched": {"type": "array", "items": _obj({
            "description": {"type": "string"}, "reason": {"type": "string"}})},
        "notes": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
    })
    ctx = {
        "risk_items": [{"id": r["id"], "activity": r["activity"]} for r in risks],
        "workers": [{"id": w["id"], "name": w["name"], "trade": w.get("trade", ""),
                     "employer": w.get("employer", "")} for w in workers],
        "plant": [{"id": p["id"], "name": p["name"], "ident": p.get("ident", "")} for p in plant],
    }
    content = (f"Site data:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
               f"Foreman's description of today's work:\n{transcript}")
    return llm.call(TASK_SYSTEM, content, schema=schema)


# ---------------------------------------------------------------- toolbox talk

TALK_SYSTEM = """You write toolbox talks for South African construction workers. The foreman reads the talk aloud, or the app plays it, at the start of the shift.

Rules:
- Base the talk only on the hazards and controls given. Do not add new rules.
- Use plain words and short sentences. Many listeners read little; they listen.
- Length: about 2 minutes spoken (220 to 300 words).
- Speak to the workers directly ("you", "we"). Give one real example of how a person gets hurt.
- End with what each person must do today.
- Also give 3 to 5 key points and 2 to 3 questions the foreman asks to check understanding.
- When a target language is not English, translate the talk into that language. Use everyday spoken words, not formal terms. Keep English for equipment names that workers say in English (for example "hard hat", "harness", "TLB")."""


def toolbox_talk(topic: str, hazards: list[dict], language: str) -> dict:
    lang = library.LANGUAGES.get(language, "English")
    schema = _obj({
        "title": {"type": "string"}, "text_en": {"type": "string"},
        "text": {"type": "string"},
        "key_points_en": {"type": "array", "items": {"type": "string"}},
        "questions_en": {"type": "array", "items": {"type": "string"}},
    })
    content = (f"Topic: {topic or 'today’s work'}\n"
               f"Target language: {lang}\n"
               f"Hazards and controls for today:\n{json.dumps(hazards, ensure_ascii=False)}\n\n"
               "Give text_en in English and text in the target language "
               "(the same as text_en when the target is English).")
    return llm.call(TALK_SYSTEM, content, schema=schema)


# ---------------------------------------------------------------- incident

INCIDENT_SYSTEM = """You turn a spoken account of a site incident into a structured incident report for a South African construction site.

Rules:
- Record only facts the speaker gives. Do not guess names, times, injuries or causes. Put gaps in "questions".
- Match injured persons to the worker list by id when you can; else leave worker_id empty.
- "possible_causes": list causes the speaker states or that follow directly from the facts. Label them as possible.
- "possibly_reportable": true when the account describes a death; unconsciousness; loss of a limb or part of a limb; an injury or illness likely to cause death, a permanent defect, or at least 14 days off work; a major incident; a spill of a dangerous substance; an uncontrolled release of a substance under pressure; or machinery that broke or ran out of control and caused flying, falling or uncontrolled moving objects. These events may have to be reported to the Department of Employment and Labour under section 24 of the OHS Act. The safety officer decides.
- Write in plain English."""


def incident(transcript: str, workers: list[dict]) -> dict:
    schema = _obj({
        "type": {"type": "string", "enum": list(library.INCIDENT_TYPES)},
        "occurred_at": {"type": "string"}, "location": {"type": "string"},
        "description": {"type": "string"},
        "people": {"type": "array", "items": _obj({
            "name": {"type": "string"}, "worker_id": {"type": "string"},
            "injury": {"type": "string"}, "treatment": {"type": "string"}})},
        "witnesses": {"type": "array", "items": {"type": "string"}},
        "immediate_actions": {"type": "string"},
        "possible_causes": {"type": "array", "items": {"type": "string"}},
        "possibly_reportable": {"type": "boolean"},
        "reportable_reason": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
    })
    ctx = [{"id": w["id"], "name": w["name"], "trade": w.get("trade", "")} for w in workers]
    content = f"Workers on site:\n{json.dumps(ctx, ensure_ascii=False)}\n\nAccount:\n{transcript}"
    return llm.call(INCIDENT_SYSTEM, content, schema=schema)


# ---------------------------------------------------------------- risk draft

RISK_SYSTEM = """You draft one risk assessment item for a South African construction activity, for review by a competent person (SACPCMP-registered).

Rules:
- List the main hazards (3 to 6). For each, give the risk before controls (L, M or H) and practical controls a small contractor can apply.
- Use the Construction Regulations 2014 approach: eliminate, then engineer, then administrative controls, then PPE.
- List the PPE.
- Write short, plain instructions. This is a draft: the safety officer approves or changes it."""


def risk_draft(description: str) -> dict:
    schema = _obj({
        "activity": {"type": "string"},
        "hazards": {"type": "array", "items": _obj({
            "hazard": {"type": "string"}, "risk": {"type": "string", "enum": ["L", "M", "H"]},
            "controls": {"type": "array", "items": {"type": "string"}}})},
        "ppe": {"type": "array", "items": {"type": "string"}},
    })
    return llm.call(RISK_SYSTEM, f"Activity: {description}", schema=schema)


# ---------------------------------------------------------------- import a consultant's risk assessment

RA_SYSTEM = """You read a construction baseline risk assessment (South Africa) and copy it into structured data exactly.

Rules:
- Copy every row. Keep the consultant's wording for activities, hazards, consequences and controls. Do not improve, merge or add anything.
- Split the control measures into separate controls where the text lists several ("Issue gloves, dust masks" stays one control per instruction).
- Scores: copy the numbers as written. Consequence (C), likelihood (L), rating. Revised C, L, rating after controls. Use 0 when a number is missing. Do not correct numbers, even when they look wrong.
- "responsible": the text in the "action assigned to" column.
- "accepted": true only when the acceptance-of-responsibility cell holds a name or signature.
- PPE: list the PPE the controls name for that row (gloves, dust masks, hearing protection, head protection = hard hat, protective footwear = safety boots, long pants).
- Header: reference number, RA number, revision, date, review date, description of the work, location, the risk assessment team (name and title), and whether a client approval is filled in.
- Matrix: if the document has a risk matrix, give the band name for each likelihood (1-5) and consequence (1-5) cell; else leave it empty."""


def ra_extract(name: str, data: bytes) -> dict:
    row = _obj({
        "item": {"type": "string"}, "activity": {"type": "string"}, "hazards": {"type": "string"},
        "consequence": {"type": "string"}, "c": {"type": "integer"}, "l": {"type": "integer"},
        "rating": {"type": "integer"}, "controls": {"type": "array", "items": {"type": "string"}},
        "rc": {"type": "integer"}, "rl": {"type": "integer"}, "rrating": {"type": "integer"},
        "responsible": {"type": "string"}, "accepted": {"type": "boolean"},
        "ppe": {"type": "array", "items": {"type": "string"}}})
    schema = _obj({
        "header": _obj({"reference": {"type": "string"}, "ra_no": {"type": "string"}, "revision": {"type": "string"},
                        "date": {"type": "string"}, "review_date": {"type": "string"},
                        "description": {"type": "string"}, "location": {"type": "string"},
                        "team": {"type": "array", "items": _obj({"name": {"type": "string"}, "title": {"type": "string"}})},
                        "client_approved": {"type": "boolean"}}),
        "rows": {"type": "array", "items": row},
        "matrix": {"type": "array", "items": _obj({"l": {"type": "integer"}, "c": {"type": "integer"},
                                                  "band": {"type": "string"}})},
    })
    return llm.call(RA_SYSTEM, llm.file_blocks(name, data) + [{"type": "text", "text": "Copy this risk assessment."}],
                    schema=schema, max_tokens=32000)


# ---------------------------------------------------------------- import a client's H&S specification

SPEC_SYSTEM = """You read a client's construction health and safety specification (South Africa, Construction Regulations 2014) and pull out the requirements a site app can track.

Rules:
- Only requirements the document states. Quote the clause number for each. Use null or an empty list when the document says nothing.
- Frequencies in days: "weekly" = 7, "monthly" = 30, "every 3 months" = 90, "daily" = 1.
- required_documents: documents that must be in the site H&S file or submitted (policies, organogram, emergency procedure, fire risk survey, fall protection plan, method statements, H&S plan, notification, COID proof, appointments, agreements, etc.). Map each to the nearest section key.
- required_appointments: map each to the nearest appointment key, or "other".
- client_hazards: the hazards the client says the risk assessment must include.
- key_rules: up to 25 short site rules for workers and visitors, in plain English, from the rules of conduct, PPE, transport and similar clauses.
- acceptance_signatories: who must sign acceptance of the specification.
- ra_team_required: the roles the specification says must be part of the risk assessment team and sign it."""


def spec_extract(name: str, data: bytes, appointment_keys: list[str], section_keys: list[str],
                 checklist_keys: list[str]) -> dict:
    nint = {"type": ["integer", "null"]}
    schema = _obj({
        "project": {"type": "string"}, "client": {"type": "string"}, "author": {"type": "string"},
        "date": {"type": "string"},
        "frequencies": _obj({"toolbox_talk_days": nint, "environmental_talks_min": nint,
                             "first_drill_within_days": nint, "evacuation_drill_days": nint,
                             "committee_meeting_days": nint, "audit_days": nint, "injury_report_days": nint,
                             "scaffold_inspection_days": nint, "ladder_inspection_days": nint,
                             "temporary_works_inspection_days": nint, "observation_days": nint}),
        "required_documents": {"type": "array", "items": _obj({
            "title": {"type": "string"}, "clause": {"type": "string"},
            "section": {"type": "string", "enum": section_keys + ["other"]}})},
        "required_appointments": {"type": "array", "items": _obj({
            "title": {"type": "string"}, "clause": {"type": "string"},
            "key": {"type": "string", "enum": appointment_keys + ["other"]}})},
        "permits": {"type": "array", "items": {"type": "string", "enum": ["hot_work", "electrical", "work_at_height",
                                                                        "excavation", "confined_space", "other"]}},
        "client_hazards": {"type": "array", "items": {"type": "string"}},
        "required_inspections": {"type": "array", "items": _obj({
            "item": {"type": "string"}, "clause": {"type": "string"},
            "checklist": {"type": "string", "enum": checklist_keys + ["other"]}, "days": nint})},
        "ppe_minimum": {"type": "array", "items": {"type": "string"}},
        "injury_categories": {"type": "array", "items": {"type": "string"}},
        "facilities": _obj({"toilet_per_workers": nint, "shower_per_workers": nint}),
        "acceptance_signatories": {"type": "array", "items": {"type": "string"}},
        "ra_team_required": {"type": "array", "items": {"type": "string"}},
        "key_rules": {"type": "array", "items": _obj({"clause": {"type": "string"}, "rule": {"type": "string"}})},
    })
    return llm.call(SPEC_SYSTEM, llm.file_blocks(name, data) + [{"type": "text", "text": "Extract the requirements."}],
                    schema=schema, max_tokens=32000)


COVER_SYSTEM = """You check whether a site's risk assessment covers each hazard that the client's specification lists.
For each client hazard, list the ids of the risk assessment items that address it directly (the activity or its hazards and controls deal with that hazard). If none does, give an empty list. Be strict: a passing mention without controls is "partial"."""


def hazard_coverage(client_hazards: list[str], items: list[dict]) -> dict:
    schema = _obj({"results": {"type": "array", "items": _obj({
        "hazard": {"type": "string"}, "status": {"type": "string", "enum": ["covered", "partial", "missing"]},
        "item_ids": _ids_schema([i["id"] for i in items]), "note": {"type": "string"}})}})
    ctx = [{"id": i["id"], "activity": i["activity"],
            "hazards": [h["hazard"] + ": " + "; ".join(h.get("controls", [])) for h in i["hazards"]]} for i in items]
    return llm.call(COVER_SYSTEM, f"Client hazards:\n{json.dumps(client_hazards)}\n\nRisk assessment items:\n"
                    f"{json.dumps(ctx, ensure_ascii=False)}", schema=schema)
