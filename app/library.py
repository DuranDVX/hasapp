"""Starter content: risk library, checklists, safety-file index, induction text.

DRAFT. A competent person (SACPCMP-registered) must review all of this before
a customer relies on it. Starter risk items load unapproved; the app marks
them "not approved" on every record until the safety officer approves them.
"""

LANGUAGES = {
    "en": "English", "af": "Afrikaans", "zu": "isiZulu", "xh": "isiXhosa",
    "st": "Sesotho", "tn": "Setswana", "nso": "Sepedi",
}

# Azure neural voices that exist for South African languages. Check the list
# again before launch; languages without a voice fall back to text.
TTS_VOICES = {"en": "en-ZA-LeahNeural", "af": "af-ZA-AdriNeural", "zu": "zu-ZA-ThandoNeural"}


def _h(hazard, risk, *controls):
    return {"hazard": hazard, "risk": risk, "controls": list(controls)}


STARTER_RISKS = [
    {"activity": "Site establishment and hoarding",
     "hazards": [
         _h("Unauthorised public access to the site", "M", "Erect hoarding or fencing around the site", "Lock gates after hours", "Put up warning signs at all entrances"),
         _h("Contact with buried or overhead services", "H", "Get service drawings before work starts", "Scan and mark services before any digging", "Keep plant clear of overhead lines"),
         _h("Slips and trips on an untidy site", "M", "Keep walkways clear", "Remove waste daily")],
     "ppe": ["Hard hat", "Safety boots", "Reflective vest", "Gloves"]},
    {"activity": "Excavation and trenching",
     "hazards": [
         _h("Collapse of the excavation sides", "H", "Support, slope or bench the sides as the excavation plan specifies", "A competent person inspects the excavation before each shift and after rain", "Keep spoil and materials back from the edge"),
         _h("Persons or plant fall into the excavation", "H", "Barricade the excavation and put up signs", "Keep plant back from the edge", "Provide a safe ladder for access"),
         _h("Contact with buried services", "H", "Locate and mark services before digging", "Dig by hand near marked services"),
         _h("Water in the excavation", "M", "Pump out water before work", "Stop work if the sides become unstable")],
     "ppe": ["Hard hat", "Safety boots", "Reflective vest", "Gloves"]},
    {"activity": "Concrete work: mixing, placing and finishing",
     "hazards": [
         _h("Cement burns to skin and eyes", "M", "Wear gloves, long sleeves and eye protection", "Wash skin at once after contact", "Keep clean water on site for eye wash"),
         _h("Entanglement in the concrete mixer", "H", "Keep all guards in place", "Only trained persons operate the mixer", "Switch off before cleaning"),
         _h("Manual handling of heavy loads", "M", "Use wheelbarrows and pumps", "Lift with two persons for heavy items"),
         _h("Formwork failure during the pour", "H", "A competent person checks the formwork before the pour", "Keep persons clear of the area under the pour")],
     "ppe": ["Hard hat", "Gumboots", "Rubber gloves", "Safety glasses", "Reflective vest"]},
    {"activity": "Formwork and support work",
     "hazards": [
         _h("Collapse of formwork or props", "H", "Follow the formwork design drawings", "A competent person inspects before and during the pour", "Do not strip formwork before the approved time"),
         _h("Falls from height while erecting formwork", "H", "Use a working platform with guardrails", "Follow the fall protection plan"),
         _h("Cuts and puncture wounds from nails", "M", "Remove or bend protruding nails", "Keep the area clean")],
     "ppe": ["Hard hat", "Safety boots", "Gloves", "Safety glasses", "Reflective vest"]},
    {"activity": "Steel fixing (reinforcing)",
     "hazards": [
         _h("Impalement on protruding bars", "H", "Fit caps on protruding bar ends", "Bend bar ends over where possible"),
         _h("Cuts to hands", "M", "Wear gloves", "Use the correct cutting and bending tools"),
         _h("Manual handling of bundles", "M", "Use mechanical lifting for bundles", "Lift with two persons")],
     "ppe": ["Hard hat", "Safety boots", "Leather gloves", "Safety glasses"]},
    {"activity": "Brickwork and blockwork",
     "hazards": [
         _h("Falls from scaffold or trestles", "H", "Use only an inspected scaffold with guardrails", "Do not stand on loose bricks or drums"),
         _h("Falling bricks or tools", "M", "Fit toe boards", "Do not overload the platform", "Barricade the area below"),
         _h("Manual handling strain", "M", "Keep loads small", "Stack materials near the work position"),
         _h("Cement contact with skin", "L", "Wear gloves", "Wash skin after contact")],
     "ppe": ["Hard hat", "Safety boots", "Gloves", "Safety glasses"]},
    {"activity": "Work at height: scaffolding erection and use",
     "hazards": [
         _h("Falls of persons from the scaffold", "H", "Only a competent scaffold erector erects or changes the scaffold", "Fit guardrails, mid rails and toe boards", "A competent person inspects before use, weekly and after bad weather", "Tag the scaffold with its status"),
         _h("Scaffold collapse", "H", "Use sole boards and base plates on firm ground", "Tie the scaffold to the structure", "Do not overload the platform"),
         _h("Falling objects", "M", "Fit toe boards and netting", "Barricade the area below")],
     "ppe": ["Hard hat with chin strap", "Safety boots", "Full body harness where the fall protection plan requires it", "Gloves"]},
    {"activity": "Work at height: ladders",
     "hazards": [
         _h("Fall from the ladder", "H", "Inspect the ladder before use", "Secure the ladder at the top or have a second person foot it", "Keep three points of contact", "Extend the ladder 1 m above the landing"),
         _h("Ladder slips or breaks", "M", "Set the ladder at a 1-in-4 angle on firm ground", "Remove damaged ladders from use")],
     "ppe": ["Hard hat", "Safety boots"]},
    {"activity": "Roof work: trusses, sheeting and tiling",
     "hazards": [
         _h("Falls from the roof edge or through openings", "H", "Follow the fall protection plan", "Use edge protection or harnesses with anchor points", "Cover or mark openings and fragile sheets"),
         _h("Truss collapse during erection", "H", "Install temporary bracing as the truss design specifies", "Do not load the trusses before bracing is complete"),
         _h("Wind lifts sheets", "M", "Stop sheet handling in strong wind", "Fix or tie down loose sheets"),
         _h("Heat stress on the roof", "M", "Plan roof work for cooler hours", "Provide water and rest breaks")],
     "ppe": ["Hard hat with chin strap", "Safety boots with good grip", "Full body harness", "Gloves", "Sunscreen"]},
    {"activity": "Operation of construction plant (TLB, excavator, tipper, roller)",
     "hazards": [
         _h("Persons struck by moving plant", "H", "Only licensed and appointed operators operate plant", "Use a banksman when reversing", "Keep persons out of the swing radius", "Reverse alarms must work"),
         _h("Plant overturns", "H", "Do not work on slopes beyond the machine limits", "Keep back from excavation edges", "Wear the seat belt"),
         _h("Mechanical failure", "M", "Do the pre-use check every day", "Report defects and stop use of unsafe plant")],
     "ppe": ["Hard hat (outside the cab)", "Safety boots", "Reflective vest", "Hearing protection"]},
    {"activity": "Electrical work and temporary power",
     "hazards": [
         _h("Electric shock", "H", "Only a qualified electrician does electrical work", "Use earth leakage protection on all temporary supplies", "Isolate and lock out before work", "Inspect leads and DB boards"),
         _h("Fire from overloaded circuits", "M", "Do not daisy-chain multi-plugs", "Keep a fire extinguisher near the DB board")],
     "ppe": ["Safety boots", "Insulated gloves where required", "Safety glasses"]},
    {"activity": "Plumbing and drainage",
     "hazards": [
         _h("Trench collapse during pipe laying", "H", "Apply the excavation controls", "Inspect the trench before entry"),
         _h("Burns from gas torches and hot work", "M", "Keep a fire extinguisher at the work position", "Check gas hoses and fittings"),
         _h("Contact with sewage", "M", "Wear gloves", "Wash hands before eating")],
     "ppe": ["Hard hat", "Safety boots", "Gloves", "Safety glasses"]},
    {"activity": "Use of portable power tools (grinder, drill, saw)",
     "hazards": [
         _h("Cuts and amputation", "H", "Keep guards fitted", "Use the correct disc or blade for the material and speed", "Disconnect before changing discs"),
         _h("Flying particles", "M", "Wear eye or face protection", "Screen the area from other persons"),
         _h("Electric shock from damaged tools", "H", "Inspect the tool, lead and plug before use", "Use earth leakage protection"),
         _h("Noise and dust", "M", "Wear hearing protection", "Wear a dust mask", "Use wet cutting where possible")],
     "ppe": ["Safety glasses or face shield", "Hearing protection", "Dust mask", "Gloves", "Safety boots"]},
    {"activity": "Manual handling of materials",
     "hazards": [
         _h("Back injury from lifting", "M", "Lift with the legs, not the back", "Use two persons or a mechanical aid for heavy items"),
         _h("Crushed hands and feet", "M", "Wear gloves and safety boots", "Keep fingers clear of pinch points")],
     "ppe": ["Gloves", "Safety boots"]},
    {"activity": "Hot work: welding, cutting and grinding",
     "hazards": [
         _h("Fire", "H", "Get a hot work permit where the site requires it", "Remove flammable materials from the area", "Keep a fire extinguisher at the work position", "Do a fire watch after the work"),
         _h("Burns and eye damage (arc flash)", "H", "Wear a welding helmet, leather apron and gloves", "Screen the work from other persons"),
         _h("Fumes", "M", "Weld in a ventilated area", "Use extraction in confined areas"),
         _h("Gas cylinder failure", "H", "Secure cylinders upright", "Fit flashback arrestors", "Inspect hoses before use")],
     "ppe": ["Welding helmet", "Leather apron", "Welding gloves", "Safety boots", "Respirator in confined areas"]},
    {"activity": "Plastering, painting and finishes",
     "hazards": [
         _h("Chemical contact and fumes", "M", "Read the safety data sheet", "Ventilate the area", "Store chemicals in a locked area"),
         _h("Falls from trestles and mobile towers", "M", "Use stable platforms with guardrails", "Lock the wheels of mobile towers")],
     "ppe": ["Gloves", "Safety glasses", "Respirator for solvents and spray work", "Overalls"]},
    {"activity": "Demolition (small scale)",
     "hazards": [
         _h("Unplanned collapse", "H", "A competent person plans the demolition sequence", "Isolate all services first", "Keep persons out of the collapse zone"),
         _h("Asbestos exposure", "H", "Test suspect materials before demolition", "Stop work and call a registered asbestos contractor if asbestos is found"),
         _h("Dust and flying debris", "M", "Wet down the work area", "Wear dust masks and eye protection")],
     "ppe": ["Hard hat", "Safety boots", "Safety glasses", "Dust mask", "Gloves", "Hearing protection"]},
    {"activity": "Material deliveries and stacking",
     "hazards": [
         _h("Persons struck by delivery vehicles", "H", "Use a banksman for vehicles that reverse", "Keep a separate walkway for persons"),
         _h("Stacks collapse", "M", "Stack on firm, level ground", "Limit the stack height", "Do not take materials from the bottom of a stack")],
     "ppe": ["Hard hat", "Safety boots", "Reflective vest", "Gloves"]},
    {"activity": "Work in hot weather",
     "hazards": [
         _h("Heat stress and dehydration", "M", "Provide clean drinking water", "Plan heavy work for cooler hours", "Give rest breaks in the shade"),
         _h("Sunburn", "L", "Wear long sleeves and a hat brim", "Use sunscreen")],
     "ppe": ["Hat with brim or hard hat with sun brim", "Long sleeves", "Sunscreen"]},
]

# Checklists for plant pre-use checks and site inspections.
# "critical": a defect on this item means the plant or area must not be used.
def _c(q, critical=False):
    return {"q": q, "critical": critical}


CHECKLISTS = {
    "earthmoving": {"title": "TLB / excavator pre-use check", "kind": "plant", "items": [
        _c("Operator holds a valid licence and appointment for this machine", True),
        _c("Service brakes and park brake work", True), _c("Steering works", True),
        _c("Hooter and reverse alarm work", True), _c("Seat belt in good condition", True),
        _c("No hydraulic leaks; hoses and fittings not damaged", True),
        _c("Bucket, teeth and quick-hitch locking pin secure", True),
        _c("Lights and beacon work"), _c("Tyres or tracks not damaged"),
        _c("Mirrors and windows clean and not broken"), _c("Fire extinguisher present and charged"),
        _c("Engine oil, coolant and hydraulic oil levels correct"), _c("No loose items on the cab floor")]},
    "vehicle": {"title": "Truck / bakkie pre-use check", "kind": "plant", "items": [
        _c("Driver holds a valid licence (and PrDP where required)", True),
        _c("Brakes work", True), _c("Tyres in good condition, no cuts or bulges", True),
        _c("Seat belts work", True), _c("No persons ride on the load bin", True),
        _c("Lights, indicators and hooter work"), _c("Mirrors and windscreen not damaged"),
        _c("Load secured"), _c("Fire extinguisher and first aid kit present")]},
    "mixer": {"title": "Concrete mixer pre-use check", "kind": "plant", "items": [
        _c("All guards in place", True), _c("Stop switch works", True),
        _c("Electric mixer: lead and plug not damaged, earth leakage on the supply", True),
        _c("Petrol or diesel mixer: no fuel leaks"), _c("Mixer stands level and stable"),
        _c("Drum, gears and handle not damaged")]},
    "power_tool": {"title": "Portable power tool check", "kind": "plant", "items": [
        _c("Casing, lead and plug not damaged", True), _c("Guard fitted and adjusted", True),
        _c("Supply has earth leakage protection", True),
        _c("Correct disc or blade for the material and tool speed", True),
        _c("Switch works and returns to off"), _c("Inspection tag is current")]},
    "scaffold": {"title": "Scaffold inspection", "kind": "inspection",
                 "note": "A competent person inspects before first use, weekly, and after bad weather.", "items": [
        _c("Base plates and sole boards on firm, level ground", True),
        _c("Standards plumb; ledgers and transoms secure", True), _c("Bracing in place", True),
        _c("Working platforms fully boarded and secure", True),
        _c("Guardrails, mid rails and toe boards in place", True),
        _c("Scaffold tied to the structure as designed", True),
        _c("Safe access ladder fixed in place"), _c("Platform not overloaded"),
        _c("Scaffold tag shows the current status")]},
    "excavation": {"title": "Excavation inspection", "kind": "inspection",
                   "note": "A competent person inspects before each shift and after rain.", "items": [
        _c("Sides supported, sloped or benched as the excavation plan specifies", True),
        _c("Barricades and warning signs in place", True),
        _c("Spoil and materials kept back from the edge", True),
        _c("Plant kept back from the edge", True), _c("Safe ladder access within reach"),
        _c("No water build-up"), _c("No sign of cracks or movement at the edges"),
        _c("Nearby structures not undermined"), _c("Services located and marked")]},
    "ladder": {"title": "Ladder inspection", "kind": "inspection", "items": [
        _c("Stiles and rungs not cracked, bent or loose", True), _c("Non-slip feet in place", True),
        _c("Ladder not painted (paint hides defects)"), _c("Ladder clean, no oil or mud"),
        _c("Inspection tag is current")]},
    "electrical_db": {"title": "Temporary DB board inspection", "kind": "inspection", "items": [
        _c("Earth leakage unit trips when the test button is pressed", True),
        _c("No exposed live parts", True), _c("Cover closed and lockable"),
        _c("Leads and plugs not damaged"), _c("No daisy-chained multi-plugs"),
        _c("Fire extinguisher near the board")]},
    "fire_extinguisher": {"title": "Fire extinguisher check (monthly)", "kind": "inspection", "items": [
        _c("Extinguisher at its marked position, access clear", True),
        _c("Pressure gauge in the green", True), _c("Pin and seal intact"),
        _c("Service date valid"), _c("Sign in place")]},
    "first_aid": {"title": "First aid box check (monthly)", "kind": "inspection", "items": [
        _c("First aider with a valid certificate on site", True),
        _c("Box contents complete"), _c("Box clean and easy to find"),
        _c("Emergency numbers displayed")]},
}

# Safety file index. "upload" sections hold documents; "auto" sections the app
# builds from site records. Confirm against the client's H&S specification.
FILE_SECTIONS = [
    {"key": "notification", "title": "Notification of construction work / construction work permit", "type": "upload"},
    {"key": "client_spec", "title": "Client health and safety specification", "type": "upload"},
    {"key": "hs_plan", "title": "Health and safety plan (approved)", "type": "upload"},
    {"key": "company", "title": "Company registration and COID letter of good standing", "type": "upload", "expires": True},
    {"key": "appointments", "title": "Legal appointments and competency certificates", "type": "auto+upload"},
    {"key": "risk_assessments", "title": "Risk assessments", "type": "auto+upload"},
    {"key": "fall_protection", "title": "Fall protection plan", "type": "upload"},
    {"key": "method_statements", "title": "Safe work procedures and method statements", "type": "upload"},
    {"key": "emergency", "title": "Emergency plan and contact numbers", "type": "upload"},
    {"key": "workers", "title": "Worker register, medical and training certificates", "type": "auto"},
    {"key": "inductions", "title": "Induction and visitor registers", "type": "auto"},
    {"key": "task_sheets", "title": "Daily task sheets", "type": "auto"},
    {"key": "toolbox_talks", "title": "Toolbox talks", "type": "auto"},
    {"key": "inspections", "title": "Plant checks and site inspections", "type": "auto"},
    {"key": "incidents", "title": "Incident register, reports and investigations", "type": "auto"},
    {"key": "audits", "title": "Audit reports", "type": "auto+upload"},
    {"key": "subcontractors", "title": "Subcontractors: mandatary agreements and safety files", "type": "auto+upload"},
]
UPLOAD_SECTIONS = {s["key"] for s in FILE_SECTIONS if "upload" in s["type"]}

CREDENTIAL_KINDS = {
    "medical": "Medical fitness certificate", "training": "Training certificate",
    "licence": "Licence / operator certificate", "first_aid": "First aid certificate",
    "appointment": "Legal appointment", "other": "Other",
}

INCIDENT_TYPES = {
    "near_miss": "Near miss", "first_aid": "First aid case", "medical": "Medical treatment case",
    "lost_time": "Lost time injury", "property": "Property or plant damage",
    "environmental": "Environmental", "other": "Other",
}

DEFAULT_INDUCTION = """Site rules
1. Sign in every day. Attend the toolbox talk.
2. Wear your hard hat, safety boots and reflective vest on site at all times.
3. Wear the extra PPE that your task sheet lists.
4. Use only plant, tools and ladders that passed their check today.
5. Do not work at height without guardrails or a harness.
6. Keep out of excavations unless the foreman allows it.
7. No alcohol or drugs on site. No person under the influence may work.
8. Report every injury, near miss and unsafe condition to the foreman at once.
9. Know where the first aid box, the fire extinguishers and the assembly point are.
10. You have the right to refuse work that is not safe. Tell the foreman."""


# ---------------------------------------------------------------- site features
# The site manager ticks what the site has. Each feature switches on duties.
SITE_FEATURES = {
    "excavations": "Excavations or trenches",
    "scaffolding": "Scaffolding",
    "work_at_height": "Work at height (roofs, edges, openings)",
    "mobile_plant": "Construction vehicles or mobile plant",
    "temporary_power": "Temporary electrical supply / DB board",
    "material_hoist": "Material hoist",
    "demolition": "Demolition",
    "subcontractors": "Subcontractors on site",
}

# How often each inspection is due, and which feature makes it apply.
INSPECTION_SCHEDULE = {
    "excavation": {"every": "shift", "days": 1, "feature": "excavations", "reg": "13(2)(h)"},
    "scaffold": {"every": "week", "days": 7, "feature": "scaffolding", "reg": "16, SANS 10085"},
    "electrical_db": {"every": "week", "days": 7, "feature": "temporary_power", "reg": "24"},
    "material_hoist": {"every": "day", "days": 1, "feature": "material_hoist", "reg": "19(8)"},
    "fire_extinguisher": {"every": "month", "days": 30, "feature": None, "reg": "GSR 3"},
    "first_aid": {"every": "month", "days": 30, "feature": None, "reg": "GSR 3"},
    "ladder": {"every": "month", "days": 30, "feature": "work_at_height", "reg": "GSR 13A"},
}

CHECKLISTS["material_hoist"] = {
    "title": "Material hoist daily inspection", "kind": "inspection", "aes": True,
    "note": "Reg 19(8): a competent person appointed in writing inspects daily and signs the record book. "
            "Sign this record with an advanced electronic signature (AES) or wet ink.",
    "items": [
        {"q": "Guides and tower secure", "critical": True},
        {"q": "Ropes and their connections not damaged", "critical": True},
        {"q": "Drums, sheaves and pulleys serviceable", "critical": True},
        {"q": "All safety devices work (overrun, brakes, gates)", "critical": True},
        {"q": "Platform not overloaded; load limit displayed", "critical": False},
        {"q": "Landing gates close and lock", "critical": True},
    ]}

# ---------------------------------------------------------------- appointments
# Legal appointments "in writing". "aes": the appointment carries a signature
# that a regulation needs, or the risk is high enough that AES is advised.
APPOINTMENTS = {
    "construction_manager": {"title": "Construction manager", "reg": "8(1)", "who": "user", "aes": True,
        "duties": "Manage the construction work on site and the duties of the principal contractor under the "
                  "Construction Regulations 2014, the client's H&S specification and the H&S plan."},
    "construction_supervisor": {"title": "Construction supervisor", "reg": "8(7)", "who": "any", "aes": True,
        "duties": "Supervise construction work on the site named in this appointment. Make sure the work is "
                  "done safely, to the H&S plan and the risk assessments."},
    "safety_officer": {"title": "Construction health and safety officer", "reg": "8(5)", "who": "user", "aes": True,
        "duties": "Assist the principal contractor to comply with the Act and Regulations. Monitor, inspect and "
                  "report on health and safety on site. Must be registered with the SACPCMP."},
    "risk_assessor": {"title": "Risk assessor (competent person)", "reg": "9(1)", "who": "user", "aes": True,
        "duties": "Perform and review the site risk assessments: identify hazards, evaluate risks with a "
                  "documented method, and set controls, monitoring and review plans."},
    "fall_protection": {"title": "Fall protection planner (competent person)", "reg": "10(1)(a)", "who": "any", "aes": True,
        "duties": "Draw up, implement, amend and maintain the fall protection plan for the site."},
    "excavation": {"title": "Excavation supervisor (competent person)", "reg": "13(1)", "who": "any", "aes": True,
        "duties": "Supervise excavation work. Inspect every excavation daily before each shift, after blasting, "
                  "after a fall of ground, after damage to supports and after rain. Record the results in the register."},
    "scaffold": {"title": "Scaffold supervisor (competent person)", "reg": "16(1)", "who": "any", "aes": True,
        "duties": "Supervise all scaffolding work. Make sure erectors, team leaders and inspectors are competent. "
                  "Make sure scaffolds are inspected before use, weekly and after bad weather."},
    "hoist_inspector": {"title": "Material hoist inspector (competent person)", "reg": "19(8)(a)", "who": "any", "aes": True,
        "duties": "Inspect every material hoist daily and enter and sign the results in the record book."},
    "operator": {"title": "Authorisation to operate plant", "reg": "23(1)(d)(i)", "who": "worker", "aes": False,
        "duties": "Operate only the plant named in this authorisation. Do the daily pre-use check with the checklist "
                  "and record it before use. Report defects at once and do not use defective plant."},
    "first_aider": {"title": "First aider", "reg": "GSR 3", "who": "worker", "aes": False,
        "duties": "Give first aid on site. Keep the first aid box complete. Keep the first aid certificate valid."},
    "fire_fighter": {"title": "Fire fighter / fire marshal", "reg": "GSR / ERW 9", "who": "worker", "aes": False,
        "duties": "Check fire equipment monthly. Lead fire response and evacuation on site."},
    "hs_rep": {"title": "Health and safety representative", "reg": "OHS Act s17", "who": "worker", "aes": False,
        "duties": "Inspect the workplace, identify hazards, investigate incidents and complaints, and represent "
                  "employees on health and safety matters. (Required where more than 20 employees work.)"},
}

APPOINTMENTS.update({
    "assistant_manager": {"title": "Assistant construction manager", "reg": "8(2)", "who": "user", "aes": True,
        "duties": "Manage the section of the construction work named in this appointment, with the duties of the "
                  "construction manager for that section."},
    "assistant_supervisor": {"title": "Assistant construction supervisor", "reg": "8(8)", "who": "any", "aes": False,
        "duties": "Assist the construction supervisor with the duties set out in this appointment."},
    "ladder_inspector": {"title": "Ladder inspector (competent person)", "reg": "GSR 13A", "who": "any", "aes": False,
        "duties": "Inspect all ladders monthly and before use after any damage. Record the results in the register. "
                  "Remove defective ladders from use."},
    "temporary_works_designer": {"title": "Temporary works designer", "reg": "12(1)", "who": "any", "aes": True,
        "duties": "Design, inspect and approve the erected temporary works on site before use."},
    "temporary_works_supervisor": {"title": "Temporary works supervisor (competent person)", "reg": "12(2)", "who": "any", "aes": True,
        "duties": "Supervise all temporary works operations. Inspect before, during and after concrete placement, "
                  "after bad weather and daily, and record the results. Authorise casting and stripping in writing."},
    "machinery_inspector": {"title": "Machinery inspector (competent person)", "reg": "DMR 2, 18", "who": "any", "aes": False,
        "duties": "Inspect driven machinery regularly and make sure it is maintained. Keep the inspection records."},
    "stacking_supervisor": {"title": "Stacking and storage supervisor", "reg": "28(a)", "who": "any", "aes": False,
        "duties": "Supervise the stacking and storage of materials. Keep storage areas safe, designated and controlled."},
    "scaffold_inspector": {"title": "Scaffold inspector (competent person)", "reg": "16, SANS 10085", "who": "any", "aes": False,
        "duties": "Inspect scaffolds before first use, weekly and after bad weather. Tag each scaffold safe or unsafe "
                  "and record the results."},
})

# Which appointments each site needs, by feature (None = always).
REQUIRED_APPOINTMENTS = [
    ("construction_manager", None), ("construction_supervisor", None), ("risk_assessor", None),
    ("first_aider", None), ("fall_protection", "work_at_height"), ("excavation", "excavations"),
    ("scaffold", "scaffolding"), ("hoist_inspector", "material_hoist"), ("operator", "mobile_plant"),
]

# Documents that need an advanced electronic signature (or wet ink + scan).
AES_DOCS = {
    "appointment": "Legal appointment",
    "mandatary_agreement": "Section 37(2) mandatary agreement",
    "excavation_decision": "Excavation stability decision (reg 13(2)(b)(ii)(bb))",
    "hoist_book": "Material hoist record book entry (reg 19(8)(c))",
    "notification": "Notification of construction work / permit application (signed)",
    "other": "Other signed document",
}

VISITOR_RULES = """Visitor rules
1. Stay with your host at all times.
2. Wear the PPE you were given: hard hat, safety boots and reflective vest.
3. Keep out of barricaded areas, excavations and the swing of machines.
4. Do not climb scaffolds or ladders.
5. In an emergency, go to the assembly point with your host.
6. Report any injury or unsafe condition to your host at once."""

VISITOR_PPE = ["Hard hat", "Safety boots", "Reflective vest", "Safety glasses", "Hearing protection"]

ESIGN_POLICY = """Electronic signature agreement

{company} and the persons who sign records in {app} agree that:
1. Site records (task sheets, toolbox talks, inductions, checks, inspections, registers and reports) are signed electronically in the app. Each signature is captured on the device with the signer's name, the date and time, GPS where available, and where taken a photo of the signer.
2. Such a signature identifies the signer and shows that the signer approves the content, as section 13(3) and 13(5) of the Electronic Communications and Transactions Act 25 of 2002 (ECT Act) provide.
3. Where a law requires a signature and does not specify its type, an advanced electronic signature (AES) or a handwritten signature is used, as section 13(1) of the ECT Act requires.
4. Records are kept as data messages in terms of sections 12, 16 and 17 of the ECT Act, with integrity protection (a hash chain), and can be printed when a person asks for paper."""

WORKER_CONSENT = """I agree that:
- I sign site records on this device. My electronic signature means the same as my handwritten signature.
- The company keeps my name, ID number, photo, certificates and medical fitness certificate to meet the Construction Regulations 2014. Only people who manage health and safety for the company can see them. The company keeps them as long as the law requires and then deletes them. (POPIA)"""

AUDIT_ITEMS = [
    ("plan", "H&S plan approved and on site", "5(1)(l), 7(1)(a)"),
    ("file", "H&S file on site and up to date", "7(1)(b)"),
    ("appointments", "Legal appointments in writing", "8, 9, 13, 16, 23"),
    ("risk", "Risk assessments by a competent person, reviewed", "9"),
    ("induction", "All workers and visitors inducted", "7(5)-(7)"),
    ("medicals", "Valid medical certificates (Annexure 3)", "7(8)"),
    ("training", "Workers trained on hazards before work (task sheets, talks)", "9(3)"),
    ("fall", "Fall protection plan in place and applied", "10"),
    ("excavations", "Excavations inspected and recorded", "13(2)(h)"),
    ("scaffolds", "Scaffolds inspected and tagged", "16"),
    ("plant", "Plant pre-use checks recorded; operators authorised", "23"),
    ("electrical", "Temporary electrical installations safe", "24"),
    ("housekeeping", "Housekeeping and stacking", "27, 28"),
    ("fire", "Fire equipment and first aid", "29, GSR 3"),
    ("contractors", "Contractors appointed, COID good standing, agreements", "7(1)(c), 7(1)(f)"),
    ("incidents", "Incidents reported and investigated", "OHS s24, GAR 8-9"),
]


# ---------------------------------------------------------------- risk matrix
# 5x5 consequence x likelihood, as used by SA construction H&S consultants
# (for example the Eden View baseline risk assessment). Band per cell.
CONSEQUENCE = {1: "Insignificant", 2: "Minor", 3: "Moderate", 4: "Major", 5: "Catastrophic"}
LIKELIHOOD = {1: "Rare", 2: "Unlikely", 3: "Possible", 4: "Likely", 5: "Almost certain"}
BANDS = {  # BANDS[likelihood][consequence]
    5: {1: "Medium", 2: "Significant", 3: "Significant", 4: "High", 5: "High"},
    4: {1: "Medium", 2: "Medium", 3: "Significant", 4: "High", 5: "High"},
    3: {1: "Low", 2: "Medium", 3: "Significant", 4: "Significant", 5: "High"},
    2: {1: "Low", 2: "Low", 3: "Medium", 4: "Significant", 5: "Significant"},
    1: {1: "Low", 2: "Low", 3: "Medium", 4: "Medium", 5: "Significant"},
}
BAND_LEVEL = {"Low": "L", "Medium": "M", "Significant": "H", "High": "H"}


def band(c, l) -> str:
    try:
        return BANDS[int(l)][int(c)]
    except (KeyError, TypeError, ValueError):
        return ""


# ---------------------------------------------------------------- generic forms
# Records that follow one simple pattern: fields, then signatures. One UI, one
# normaliser and one PDF layout serve all of them ("one set format").
PPE_ITEMS = ["Hard hat", "Safety boots", "Overalls", "Reflective vest", "Safety glasses", "Gloves",
             "Hearing protection", "Dust mask / respirator", "Double-lanyard full body harness", "Gumboots",
             "Welding helmet", "Face shield"]
PERMIT_TYPES = {"hot_work": "Hot work", "electrical": "Electrical work", "work_at_height": "Work at height",
                "excavation": "Excavation", "confined_space": "Confined space", "other": "Other"}

FORMS = {
    "drill": {"title": "Emergency evacuation drill", "reg": "ERW 9, CR 29, client spec", "icon": "🚨",
              "purpose": "Practise the evacuation: within 3 months of site start, then at least every 3 months.",
              "fields": [
                  {"k": "scenario", "label": "Scenario", "type": "text", "ph": "Fire at the site office"},
                  {"k": "alarm", "label": "How people were alerted", "type": "text", "ph": "Air horn, 3 long blasts"},
                  {"k": "minutes", "label": "Minutes until everyone was at the assembly point", "type": "number"},
                  {"k": "people", "label": "People evacuated", "type": "number"},
                  {"k": "all_counted", "label": "Everyone accounted for", "type": "yesno", "req": True},
                  {"k": "findings", "label": "What went well and what to improve", "type": "textarea"}],
              "signers": [{"role": "conductor", "who": "me", "label": "Person who ran the drill"}]},
    "meeting": {"title": "H&S committee meeting", "reg": "OHS Act s19, client spec", "icon": "👥",
                "purpose": "Monthly meeting of the H&S committee. Keep the minutes.",
                "fields": [
                    {"k": "attendees", "label": "Attendees", "type": "textarea", "req": True, "ph": "Names and roles"},
                    {"k": "agenda", "label": "Agenda", "type": "textarea"},
                    {"k": "minutes", "label": "Minutes and decisions", "type": "textarea", "req": True},
                    {"k": "actions", "label": "Actions (who, what, by when)", "type": "textarea"}],
                "signers": [{"role": "chair", "who": "me", "label": "Chairperson"}]},
    "observation": {"title": "Planned task observation", "reg": "CR 9(3), client spec", "icon": "👁️",
                    "purpose": "Watch a worker do a task and check it against the safe work procedure.",
                    "fields": [
                        {"k": "worker", "label": "Worker observed", "type": "worker", "req": True},
                        {"k": "task", "label": "Task", "type": "text", "req": True},
                        {"k": "procedure", "label": "Safe work procedure followed", "type": "select",
                         "options": ["Yes", "Partly", "No"], "req": True},
                        {"k": "ppe_ok", "label": "Correct PPE worn", "type": "yesno", "req": True},
                        {"k": "unsafe", "label": "Unsafe acts or conditions seen", "type": "textarea"},
                        {"k": "feedback", "label": "Feedback given to the worker", "type": "textarea"}],
                    "signers": [{"role": "observer", "who": "me", "label": "Observer"},
                                {"role": "worker", "who": "field:worker", "label": "Worker"}]},
    "ppe_issue": {"title": "PPE issue", "reg": "GSR 2, client spec", "icon": "🦺",
                  "purpose": "Record the PPE a worker receives. The worker confirms they understand its use.",
                  "fields": [
                      {"k": "worker", "label": "Worker", "type": "worker", "req": True},
                      {"k": "items", "label": "PPE issued", "type": "multi", "options": PPE_ITEMS, "req": True},
                      {"k": "reason", "label": "Reason", "type": "select",
                       "options": ["First issue", "Replacement: worn out or damaged", "Replacement: lost or stolen"], "req": True},
                      {"k": "understood", "label": "The worker understands why, where and how to use this PPE", "type": "yesno", "req": True}],
                  "signers": [{"role": "worker", "who": "field:worker", "label": "Worker"},
                              {"role": "issuer", "who": "me", "label": "Issued by"}]},
    "permit": {"title": "Permit to work", "reg": "Client spec, CR 10, 24", "icon": "🎫",
               "purpose": "Before hot work, electrical work or work at height: check the precautions, then issue the permit.",
               "fields": [
                   {"k": "type", "label": "Permit type", "type": "select", "options": list(PERMIT_TYPES.values()), "req": True},
                   {"k": "location", "label": "Where", "type": "text", "req": True},
                   {"k": "work", "label": "Work to be done", "type": "textarea", "req": True},
                   {"k": "valid_until", "label": "Valid until (time today)", "type": "time", "req": True},
                   {"k": "precautions", "label": "Precautions in place", "type": "multi", "req": True, "options": [
                       "Area barricaded and signs up", "Fire extinguisher at the work position", "Flammables removed",
                       "Fire watch arranged after the work", "Power isolated, locked and tagged out", "Tested for dead",
                       "Fall protection plan applies; harness and anchor checked", "Edge protection in place",
                       "Rescue plan in place", "Workers briefed on the risk assessment"]},
                   {"k": "notes", "label": "Other conditions", "type": "textarea"}],
               "signers": [{"role": "issuer", "who": "me", "label": "Permit issuer"},
                           {"role": "receiver", "who": "pick", "label": "Person in charge of the work"}]},
    "permit_close": {"title": "Permit closed", "reg": "Client spec", "icon": "✅",
                     "purpose": "Close the permit when the work is done and the area is safe.",
                     "fields": [
                         {"k": "permit", "label": "Permit", "type": "open_permit", "req": True},
                         {"k": "complete", "label": "Work complete and area left safe", "type": "yesno", "req": True},
                         {"k": "notes", "label": "Notes", "type": "textarea"}],
                     "signers": [{"role": "issuer", "who": "me", "label": "Permit issuer"}]},
    "ra_acceptance": {"title": "Risk assessment: acceptance of responsibility", "reg": "CR 9(1), client spec", "icon": "🤝",
                      "purpose": "The person assigned to actions in the risk assessment accepts responsibility for them.",
                      "fields": [
                          {"k": "role", "label": "Role in the risk assessment", "type": "ra_role", "req": True},
                          {"k": "statement", "label": "Statement", "type": "fixed",
                           "value": "I accept responsibility for the controls and actions assigned to my role in the "
                                    "risk assessment for this site, and I will see that they are applied."}],
                      "signers": [{"role": "responsible", "who": "pick", "label": "Responsible person"}]},
}

# Permit types that the work in a task sheet calls for (by activity name).
PERMIT_TRIGGERS = {"Hot work": ("hot work", "welding", "cutting", "grinding"),
                   "Electrical work": ("electrical",),
                   "Work at height": ("height", "roof", "scaffold")}

INCIDENT_TYPES.update({"disabling": "Disabling injury", "fatal": "Fatality"})

# Extra checklists the client spec asks for (2.15.1, 3.6, 3.8).
CHECKLISTS["harness"] = {"title": "Safety harness inspection", "kind": "inspection", "items": [
    {"q": "Double-lanyard full body harness (no safety belts on site)", "critical": True},
    {"q": "Webbing not cut, frayed, burnt or stained by chemicals", "critical": True},
    {"q": "Stitching complete", "critical": True}, {"q": "Buckles, D-rings and snap hooks work and lock", "critical": True},
    {"q": "Lanyards and shock absorber not deployed or damaged", "critical": True},
    {"q": "Inspection tag current"}]}
CHECKLISTS["stacking"] = {"title": "Stacking and storage inspection", "kind": "inspection", "items": [
    {"q": "Stacks on firm, level ground and stable", "critical": True},
    {"q": "Stack height within limits; no material taken from the bottom", "critical": True},
    {"q": "Storage area barricaded where people could enter"}, {"q": "Walkways clear"},
    {"q": "Flammables and gas cylinders stored apart and upright", "critical": True}]}
CHECKLISTS["hand_tools"] = {"title": "Hand tool inspection", "kind": "inspection", "items": [
    {"q": "Handles sound and tight", "critical": True}, {"q": "Heads not mushroomed or cracked", "critical": True},
    {"q": "Cutting edges sharp and guarded"}, {"q": "Right tool for the job"}]}
CHECKLISTS["temporary_works"] = {"title": "Temporary works inspection", "kind": "inspection",
    "note": "CR 12(3)(f): inspect before, during and after concrete placement, after bad weather, and at least daily.",
    "items": [{"q": "Erected to the temporary works design drawing", "critical": True},
              {"q": "Props, braces and ties in place and secure", "critical": True},
              {"q": "Foundation / base sound", "critical": True}, {"q": "No damage or weakening", "critical": True},
              {"q": "Safe access to the work above", "critical": False},
              {"q": "Written authorisation before casting (CR 12(3)(g))", "critical": False}]}
CHECKLISTS["earthmoving"]["items"][3] = {"q": "Hooter, reverse siren and rotating orange beacon work", "critical": True}
CHECKLISTS["vehicle"]["items"][4] = {"q": "Workers carried only in a covered load area with proper seats; "
                                          "no more than 2 passengers in an LDV cab", "critical": True}

INSPECTION_SCHEDULE["harness"] = {"every": "month", "days": 30, "feature": "work_at_height", "reg": "GSR 6, spec 2.15"}
INSPECTION_SCHEDULE["temporary_works"] = {"every": "day", "days": 1, "feature": "temporary_works", "reg": "12(3)(f)"}
SITE_FEATURES["temporary_works"] = "Temporary works (formwork, propping)"

FILE_SECTIONS.insert(0, {"key": "policies", "title": "Company policies: OHS, alcohol and drugs, HIV/AIDS, environmental", "type": "upload"})
FILE_SECTIONS.insert(5, {"key": "organogram", "title": "Organogram: H&S site management structure", "type": "upload"})
FILE_SECTIONS.insert(9, {"key": "fire_survey", "title": "Fire risk survey", "type": "upload"})
FILE_SECTIONS.append({"key": "registers", "title": "Registers: drills, committee minutes, observations, PPE issue, permits",
                      "type": "auto"})
UPLOAD_SECTIONS = {s["key"] for s in FILE_SECTIONS if "upload" in s["type"]}

AES_DOCS["spec_acceptance"] = "Acceptance of the client's H&S specification"


# ---------------------------------------------------------------- incident forms
# Annexure 1 (General Administrative Regulations) and the investigation form that
# SA H&S consultants use (loss-causation checklists).
INCIDENT_TYPES.update({"disabling": "Disabling injury", "fatal": "Fatality"})
BODY_PARTS = ["Head/Neck", "Eye", "Trunk", "Finger", "Hand", "Arm", "Foot", "Leg", "Internal", "Multiple"]
EFFECTS = ["Sprain/Strain", "Contusion/Wound", "Fractures", "Burns", "Amputations", "Electric shock", "Asphyxiation",
           "Unconsciousness", "Poisoning", "Occupational disease", "Multiple", "Other"]
DISABLEMENT = ["0-13 days", "2-4 weeks", ">4-16 weeks", ">16-52 weeks", ">52 weeks or permanent disablement", "Killed"]
DAMAGE = ["Buildings", "Floors", "Machinery", "Equipment", "Vehicles", "Product"]
AGENCIES_GENERAL = ["Struck by", "Struck against", "Fall", "Falling object", "Handling", "Machine", "Transport", "Electricity"]
AGENCIES_HYGIENE = ["Chemical", "Fumes", "Fire", "Gas", "Dust", "Noise", "Vapour"]
UNSAFE_ACTS = ["Operating without authority", "Operating at unsafe speed", "Making safety devices inoperative",
               "Using unsafe equipment", "Using equipment unsafely", "Unsafe loading, placing or mixing",
               "Taking an unsafe position", "Working on moving or unsafe equipment", "Distracting, teasing, horseplay",
               "Failure to use protective equipment", "Safety regulations ignored"]
UNSAFE_CONDITIONS = ["Inadequately guarded", "Unguarded", "Defective tools, equipment or substance", "Hazardous arrangement",
                     "Unsafe design or construction", "Poor lighting", "Unsafe clothing", "Poor floor condition",
                     "Poor ventilation", "Other"]
PERSONAL_FACTORS = ["Lack of knowledge or skill", "Physical or mental defect", "Improper attitude or motivation"]
JOB_FACTORS = ["Inadequate work standards", "Unsafe conditions"]
CONTROL_PERSONAL = ["Attend a training course", "Instruct how to do the job or follow the revised work standard",
                    "Medical examination (hearing, eyesight, alcohol, drugs, disability)", "Transfer to another job",
                    "Attend safety committee meetings", "Enforce / warn"]
CONTROL_JOB = ["Write a work standard", "Revise the work standard", "Guard", "Repair", "Modify", "Lockout",
               "Housekeeping", "Remove", "Provide protection"]
CREDENTIAL_KINDS["id_document"] = "ID document copy"

FORMS["incident_close"] = {
    "title": "Incident closed out", "reg": "GAR 9, investigation close-out", "icon": "✅",
    "purpose": "Confirm the corrective actions are in place and work may restart.",
    "fields": [
        {"k": "incident", "label": "Incident", "type": "open_incident", "req": True},
        {"k": "actions_done", "label": "All corrective actions are implemented", "type": "yesno", "req": True},
        {"k": "safe", "label": "A competent person confirmed the area and work are safe", "type": "yesno", "req": True},
        {"k": "notes", "label": "What was done", "type": "textarea", "req": True}],
    "signers": [{"role": "competent person", "who": "me", "label": "Competent person"}]}


# ---------------------------------------------------------------- H&S plan
# The principal contractor's site-specific plan (CR 7(1)(a)). The app drafts the
# "ai" text from the client's specification, the site and the risk assessment; a
# competent person checks it. "data" parts are built from the app's records each
# time the PDF is made, so they stay current.
HS_PLAN_SECTIONS = [
    ("intro", "Introduction and scope", "ai"),
    ("project", "Project information", "data"),
    ("legal", "Legal requirements", "data"),
    ("policy", "Health and safety policy", "ai"),
    ("organisation", "Organisation, appointments and responsibilities", "ai+data"),
    ("risk", "Risk assessment and method statements", "ai+data"),
    ("training", "Induction, training and competence", "ai"),
    ("communication", "Communication and consultation", "ai"),
    ("inspections", "Inspections, monitoring and audits", "ai+data"),
    ("hazards", "Site hazards and controls", "ai"),
    ("permits", "Permits to work", "ai"),
    ("ppe", "Personal protective equipment", "ai+data"),
    ("contractors", "Contractor management", "ai"),
    ("incidents", "Incident reporting and investigation", "ai"),
    ("emergency", "Emergency preparedness", "ai+data"),
    ("health", "Occupational health and welfare facilities", "ai"),
    ("site", "Housekeeping, public safety and environment", "ai"),
    ("records", "Records and registers", "ai+data"),
    ("review", "Review of this plan", "ai"),
]
HS_PLAN_TITLES = {k: t for k, t, _ in HS_PLAN_SECTIONS}
HS_PLAN_AI = [k for k, _, src in HS_PLAN_SECTIONS if "ai" in src]

HS_PLAN_LAWS = [
    "Occupational Health and Safety Act 85 of 1993 (OHS Act)",
    "Construction Regulations, 2014",
    "General Administrative Regulations, 2003",
    "General Safety Regulations, 1986",
    "Facilities Regulations, 2004",
    "Environmental Regulations for Workplaces, 1987",
    "Driven Machinery Regulations, 2015",
    "Electrical Installation Regulations, 2009, and Electrical Machinery Regulations, 2011",
    "Regulations for Hazardous Chemical Agents, 2021",
    "Noise-Induced Hearing Loss Regulations, 2003",
    "Ergonomics Regulations, 2019",
    "Compensation for Occupational Injuries and Diseases Act 130 of 1993 (COIDA)",
    "Electronic Communications and Transactions Act 25 of 2002 (electronic records and signatures)",
    "Protection of Personal Information Act 4 of 2013 (POPIA)",
]

# The only references the AI may cite. Anything else is left out.
HS_PLAN_REFS = (
    "OHS Act s7, s8, s9, s13, s14, s16, s17, s19, s24, s37(2); "
    "Construction Regulations (CR) 3, 4, 5(1)(l), 7(1)(a), 7(1)(b), 7(1)(c), 7(8), 8(1), 8(5), 8(7), 9, 10, 11, 12, 13, "
    "14, 16, 17, 18, 19, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30; General Administrative Regulations 9 and Annexure 1; "
    "General Safety Regulations 2 (PPE) and 3 (first aid); Environmental Regulations for Workplaces 9 (fire); "
    "Facilities Regulations; Regulations for Hazardous Chemical Agents; Noise-Induced Hearing Loss Regulations; "
    "Ergonomics Regulations; Driven Machinery Regulations 18 (lifting machinery); Electrical Installation Regulations; "
    "COIDA; ECT Act s12-s17; Annexure 3 (medical certificate of fitness); SANS 10085-1 (scaffolding).")

HS_PLAN_DEFAULT_PPE = ["Hard hat", "Safety boots", "Reflective vest", "Overalls or long-sleeved work clothes",
                       "Safety glasses where there is a risk to the eyes", "Gloves suited to the task"]

HS_PLAN_SIGNERS = ["Principal contractor: chief executive officer or s16(2) appointee",
                   "Competent person who reviewed this plan",
                   "Client or client's agent: approval (CR 5(1)(l))"]

AES_DOCS["hs_plan"] = "Site health and safety plan (CR 7(1)(a))"
