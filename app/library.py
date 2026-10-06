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
    {"key": "appointments", "title": "Legal appointments and competency certificates", "type": "upload"},
    {"key": "risk_assessments", "title": "Risk assessments", "type": "auto+upload"},
    {"key": "fall_protection", "title": "Fall protection plan", "type": "upload"},
    {"key": "method_statements", "title": "Safe work procedures and method statements", "type": "upload"},
    {"key": "emergency", "title": "Emergency plan and contact numbers", "type": "upload"},
    {"key": "workers", "title": "Worker register, medical and training certificates", "type": "auto"},
    {"key": "inductions", "title": "Induction register", "type": "auto"},
    {"key": "task_sheets", "title": "Daily task sheets", "type": "auto"},
    {"key": "toolbox_talks", "title": "Toolbox talks", "type": "auto"},
    {"key": "inspections", "title": "Plant checks and site inspections", "type": "auto"},
    {"key": "incidents", "title": "Incident register and reports", "type": "auto"},
    {"key": "audits", "title": "Audit reports", "type": "upload"},
    {"key": "subcontractors", "title": "Subcontractors: mandatary agreements and safety files", "type": "upload"},
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
