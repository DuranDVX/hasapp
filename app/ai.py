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

INCIDENT_SYSTEM = """You turn a spoken or typed account of a site incident into an incident flash report for a South African construction site. A health and safety consultant must be able to submit it.

Rules:
- Record only facts the speaker gives. Do not guess names, times, ID numbers, injuries, diagnoses or causes. Put every gap in "questions".
- "title": a short type of incident, for example "Trench collapse: worker trapped by falling soil".
- "type": the category. near_miss, first_aid, medical (treated by a doctor or clinic), disabling (cannot do normal work the next day), lost_time, fatal, property, environmental, other. When unsure between two, pick the lower one and ask a question.
- "description": a clear, factual narrative in the third person and past tense, in short paragraphs: what work was being done, by how many people, where, what happened, how the person was freed or helped, where they were taken, and the outcome. Use the speaker's facts only.
- "immediate_actions": one action per line, starting with what was done first (stop work, secure area, call ambulance, first aid, isolate, report, investigation started).
- People: match each injured person to the worker list by id when the name is close (speech recognition misspells names). Fill body_parts, effects and disablement (Annexure 1 boxes) only from the facts; "Other" in effects needs effect_other (for example "Trapped in soil, no injury").
- Medical findings: clinic or hospital description, pre-existing defect, physiotherapy, unfit for work, date fit for light duty, date of resumption. Leave empty when not said.
- "work_type": the machine, process or type of work (Annexure 1 item 9).
- "possibly_reportable": true when the account describes a death; unconsciousness; loss of a limb or part of a limb; an injury or illness likely to cause death, a permanent defect, or at least 14 days off work; a major incident; a spill of a dangerous substance; an uncontrolled release of a substance under pressure; or machinery that broke or ran out of control and caused flying, falling or uncontrolled moving objects (OHS Act section 24). The safety officer decides.
- Write in plain English. Dates as YYYY-MM-DD where the speaker gives a date."""


def incident(transcript: str, workers: list[dict], today: str = "") -> dict:
    person = _obj({
        "name": {"type": "string"}, "worker_id": {"type": "string"}, "occupation": {"type": "string"},
        "injury": {"type": "string"}, "treatment": {"type": "string"},
        "body_parts": {"type": "array", "items": {"type": "string", "enum": library.BODY_PARTS}},
        "effects": {"type": "array", "items": {"type": "string", "enum": library.EFFECTS}},
        "effect_other": {"type": "string"},
        "disablement": {"type": "string", "enum": library.DISABLEMENT + [""]},
        "medical": _obj({"clinic": {"type": "string"}, "pre_existing": {"type": "string"},
                         "physio": {"type": ["boolean", "null"]}, "unfit": {"type": ["boolean", "null"]},
                         "light_duty_date": {"type": "string"}, "resumption_date": {"type": "string"}})})
    schema = _obj({
        "type": {"type": "string", "enum": list(library.INCIDENT_TYPES)}, "title": {"type": "string"},
        "occurred_at": {"type": "string"}, "location": {"type": "string"},
        "reported_by": {"type": "string"}, "reporter_contact": {"type": "string"},
        "work_type": {"type": "string"}, "description": {"type": "string"},
        "people": {"type": "array", "items": person},
        "damage": {"type": "array", "items": {"type": "string", "enum": library.DAMAGE}},
        "damage_note": {"type": "string"},
        "witnesses": {"type": "array", "items": {"type": "string"}},
        "immediate_actions": {"type": "string"},
        "possible_causes": {"type": "array", "items": {"type": "string"}},
        "possibly_reportable": {"type": "boolean"}, "reportable_reason": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
    })
    ctx = [{"id": w["id"], "name": w["name"], "trade": w.get("trade", "")} for w in workers]
    content = (f"Today is {today}.\nWorkers on site:\n{json.dumps(ctx, ensure_ascii=False)}\n\nAccount:\n{transcript}")
    return llm.call(INCIDENT_SYSTEM, content, schema=schema)


INVESTIGATION_SYSTEM = """You turn an investigator's spoken or typed findings into an incident investigation for a South African construction site, in the format of the consultant's "Incident/Accident Report and Investigation" form and Annexure 1 part B to D.

Rules:
- Use the incident report given and the investigator's words. Do not invent facts.
- Tick the cause checklists (agencies, unsafe acts, unsafe conditions, personal factors, job factors) only where the facts support it. The same for control steps.
- "short_description": one or two sentences for Annexure 1 B4. "suspected_cause": Annexure 1 B5.
- "actions": corrective actions, each with who is responsible and a due date (YYYY-MM-DD) when said.
- "employer_action": Annexure 1 C, what the employer did to prevent a recurrence.
- "close_out": the conditions before work may restart.
- Plain English. Gaps go in "questions"."""


def investigation(transcript: str, incident: dict) -> dict:
    lst = lambda e: {"type": "array", "items": {"type": "string", "enum": e}}
    schema = _obj({
        "investigator": {"type": "string"}, "designation": {"type": "string"},
        "short_description": {"type": "string"}, "suspected_cause": {"type": "string"},
        "findings": {"type": "string"}, "root_causes": {"type": "array", "items": {"type": "string"}},
        "agencies_general": lst(library.AGENCIES_GENERAL), "agencies_hygiene": lst(library.AGENCIES_HYGIENE),
        "normal_work": {"type": ["boolean", "null"]},
        "unsafe_acts": lst(library.UNSAFE_ACTS), "unsafe_conditions": lst(library.UNSAFE_CONDITIONS),
        "personal_factors": lst(library.PERSONAL_FACTORS), "job_factors": lst(library.JOB_FACTORS),
        "control_personal": lst(library.CONTROL_PERSONAL), "control_job": lst(library.CONTROL_JOB),
        "actions": {"type": "array", "items": _obj({"action": {"type": "string"}, "owner": {"type": "string"},
                                                    "due": {"type": "string"}})},
        "employer_action": {"type": "string"}, "close_out": {"type": "string"},
        "reportable": {"type": "boolean"}, "not_reportable_reason": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
    })
    content = (f"Incident report:\n{json.dumps(incident, ensure_ascii=False)}\n\n"
               f"Investigator's findings:\n{transcript}")
    return llm.call(INVESTIGATION_SYSTEM, content, schema=schema)


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


# ---------------------------------------------------------------- H&S plan

PLAN_SYSTEM = """You draft parts of a principal contractor's site-specific health and safety plan for a construction site
in South Africa (Construction Regulations 2014, regulation 7(1)(a)). The plan must be based on the client's health and
safety specification and must fit this site: its work types, its risk assessment, and the client's rules and frequencies.

Rules:
- Write plain, direct English. Use short sentences and the active voice. Say who must do what and how often, for example
  "The excavation supervisor inspects every excavation before each shift."
- Use the facts in the SITE DATA. Where the client's specification sets a rule or a frequency, follow it and cite its
  clause as "(spec 2.9.3)".
- Never invent facts. Do not write names, phone numbers, addresses, hospital names, distances, dates or quantities that
  are not in the SITE DATA. Write "[to complete: what is missing]" in the text instead, and add a question.
- Cite only these legal references, and only where they apply: {refs} Do not cite any other regulation or section.
- Format: a line that starts with "## " is a sub-heading; a line that starts with "- " is a bullet point; any other line
  is a paragraph. Use no other markup: no bold, no tables, no numbered lists.
- Keep each section to what a site manager needs: about 80 to 300 words. The hazards section may be longer: one
  sub-heading per hazard group that applies to this site, with bullet-point controls.
- The app adds these tables itself, so do not repeat their contents: project details, the list of laws, the appointment
  table, the risk assessment table, the inspection schedule, the minimum PPE list and the register list. Refer to them
  as "the table below" where it helps.
- questions: short questions about facts the plan still needs from the contractor (at most 5 for your sections).""".format(
    refs=library.HS_PLAN_REFS)

PLAN_BRIEF = {
    "intro": "Purpose of the plan; the scope of the works on this site; who the plan applies to (employees, contractors, "
             "visitors); that it is based on the client's specification and the risk assessment; that it is kept on site.",
    "policy": "A short health and safety policy statement for the chief executive officer to sign (OHS Act s7, s8): "
              "commitments, consultation, legal compliance, and that every person must stop unsafe work.",
    "organisation": "Responsibilities of the chief executive officer (s16), construction manager (CR 8(1)), construction "
                    "supervisors (CR 8(7)), safety officer (CR 8(5)), competent persons, H&S representatives, employees "
                    "(s14) and contractors. Refer to the appointment table below.",
    "risk": "How risk is managed (CR 9): the client's baseline risk assessment, the contractor's risk assessment by a "
            "competent person, review when work or conditions change, daily task briefings before work. Then a "
            "'## Method statements' list of the safe work procedures this site needs for its high-risk work. "
            "Refer to the risk assessment table below.",
    "training": "Induction of every worker and visitor before they enter the site; medical certificates of fitness "
                "(Annexure 3, CR 7(8)); task training and certificates (operators, scaffold erectors, fall protection, "
                "first aid); toolbox talks and daily task briefings with their frequency.",
    "communication": "H&S representatives (s17) and the H&S committee (s19) with how often it meets (spec frequency, or at "
                     "least every three months); site meetings; notice board; toolbox talks; how contractors take part.",
    "inspections": "Who inspects what and how often (refer to the inspection schedule below); site inspections by the "
                   "safety officer; audits of contractors by the principal contractor (spec frequency, or every 30 days); "
                   "client audits; how findings are closed out.",
    "hazards": "One '## ' sub-heading per hazard group that applies to this site, from the work types, the risk assessment "
               "and the client's listed hazards (for example '## Excavations (CR 13)'). Under each, bullet-point controls "
               "that are specific and checkable. Include general hazards every site has: manual handling, hand and power "
               "tools, electricity, fire, weather and heat.",
    "permits": "Which permits to work apply on this site (from the specification and the work types), who issues and "
               "closes them, and that work stops when conditions change.",
    "ppe": "How PPE is chosen, issued, replaced and recorded (General Safety Regulations 2); task-specific PPE from the risk "
           "assessment; no PPE, no work. Refer to the minimum PPE list below.",
    "contractors": "Appointment of contractors in writing (CR 7(1)(c)); the s37(2) agreement; each contractor's H&S plan and "
                   "file approved before work starts; induction; audits; stopping unsafe contractor work.",
    "incidents": "Report every incident and near miss at once; first aid; investigation within 7 days with Annexure 1 "
                 "(General Administrative Regulations 9); reporting of serious incidents to the Department of Employment "
                 "and Labour (s24); the Compensation Fund report (COIDA); the incident register; lessons shared in toolbox talks.",
    "emergency": "The emergency plan: how to raise the alarm, emergency contacts (from the site data only), first aiders and "
                 "first aid boxes, fire equipment (CR 29), evacuation and the assembly point, rescue from excavations and "
                 "heights, and drills (spec frequency).",
    "health": "Medical certificates of fitness; facilities (CR 30, Facilities Regulations) with the specification's ratios; "
              "drinking water, eating area, changing area; noise, dust, heat and sun; alcohol and drug rules; fatigue.",
    "site": "Housekeeping (CR 27); stacking and storage (CR 28); site fencing and access control; public and visitor safety "
            "(s9); signs; traffic and pedestrian routes; waste, spills and dust.",
    "records": "Records are kept in the SiteBakkie app as electronic records (ECT Act s12-s17), signed electronically, "
               "protected against change, and printed when a person asks for paper. The H&S file is available on site "
               "(CR 7(1)(b)). Refer to the register list below.",
    "review": "When the plan is reviewed (change of scope, new hazards, after a serious incident, a change to the client's "
              "specification); version control; client approval before work starts and after changes (CR 5(1)(l)).",
}
PLAN_GROUPS = [["intro", "policy", "organisation", "risk", "training", "communication"],
               ["hazards", "permits", "ppe", "inspections"],
               ["contractors", "incidents", "emergency", "health", "site", "records", "review"]]


def _plan_part(keys: list[str], data: dict) -> dict:
    schema = _obj({**{k: {"type": "string"} for k in keys}, "questions": {"type": "array", "items": {"type": "string"}}})
    brief = "\n".join(f"- {k} ({library.HS_PLAN_TITLES[k]}): {PLAN_BRIEF[k]}" for k in keys)
    return llm.call(PLAN_SYSTEM, f"Write these sections:\n{brief}\n\nSITE DATA:\n{json.dumps(data, ensure_ascii=False)}",
                    schema=schema, max_tokens=12000)


def hs_plan(data: dict) -> dict:
    """Draft the plan text in three parallel calls; returns {"text": {key: str}, "questions": [...]}."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(len(PLAN_GROUPS)) as ex:
        parts = list(ex.map(lambda g: _plan_part(g, data), PLAN_GROUPS))
    text, questions = {}, []
    for part in parts:
        questions += [q for q in part.pop("questions", []) if q and q not in questions]
        text.update({k: v for k, v in part.items() if k in library.HS_PLAN_TITLES})
    return {"text": text, "questions": questions[:12]}
