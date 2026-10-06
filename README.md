# SiteSafe (working name)

Construction site health and safety for South African builders, without the paper.

The foreman tells the app the day's work. The app builds the daily task sheet
from the site's approved risk assessment. The workers sign on the foreman's
phone or the site tablet. Toolbox talks, plant pre-use checks, inspections,
incidents and inductions work the same way. Every record goes into a live
health and safety file that exports as one PDF for the client's agent.

The app works with no signal. Records wait on the device and send when the
signal comes back.

## What the app does

| Screen | What happens |
|---|---|
| Today | Status for the day: task sheet, toolbox talk, plant checks, inductions, medicals, expiring certificates, missing file sections |
| Daily task sheet | Voice or text → AI splits the work into tasks and picks activities from the risk library → the foreman checks → each worker signs (with the hazards, controls and PPE for their task on screen) → the supervisor signs |
| Toolbox talk | AI writes a 2-minute talk from today's activities, in English, Afrikaans, isiZulu, isiXhosa, Sesotho, Setswana or Sepedi → optional audio → attendance signatures and a group photo |
| Checks | Plant pre-use checks (QR code on each machine) and site inspections (scaffold, excavation, ladder, DB board, fire extinguisher, first aid). A defect on a critical item gives FAIL — DO NOT USE |
| Incident | Voice → AI fills the report and flags a possible section 24 (OHS Act) reportable incident for the safety officer |
| Induction | Site rules + emergency info → worker signs with a photo → inductor signs |
| Workers | Register with photo, ID number, trade, employer, language, and certificates with expiry dates |
| Safety file | Index of 17 sections, uploads per section, one-tap PDF export, record integrity check |

## The safety rule

The AI never writes a hazard, a control or PPE into a record.

1. `app/ai.py` gives the AI only the ids and names of the site's risk library
   items. The JSON schema restricts the answer to those ids.
2. `server.ai_task_sheet` drops any id that is not in the site's lists. A task
   without a matching item goes to "unmatched" for the safety officer.
3. `records._task_sheet` copies the hazard, control and PPE text from the
   database into the record. It ignores any hazard text from the device.
4. An item counts as assessed only after a user with a SACPCMP number approves
   it. An edit clears the approval. Records show "NOT APPROVED" until then.

The starter library (`app/library.py`) is a DRAFT. A competent person must
review it, the checklists and the safety-file index before a customer relies
on them.

## Record integrity

- The device sends a finished record with all signatures in one request.
  `client_id` makes the request idempotent, so the outbox can retry safely.
- Each record stores the device time, the server time and GPS.
- Files are stored under their SHA-256 name. The record hash covers the names,
  so it covers the content.
- Each record hash includes the previous record hash (one chain per company).
  `GET /api/verify` recomputes the chain. Any change to a stored record breaks it.
- Records are append-only. A correction is a new record.

## Roles

| Role | Can do |
|---|---|
| Owner | Everything, including logins |
| Safety officer | Sites, risk library approval, documents, plant, all site records |
| Foreman | Site records, workers, plant |
| Auditor | Read and export only (for the client's H&S agent). Sees masked ID numbers |

## Code

```
app/
  server.py    HTTP API + static PWA
  db.py        SQLAlchemy models (SQLite dev, Postgres prod)
  records.py   normalise, store, hash-chain and verify signed records
  ai.py        task sheet, toolbox talk, incident and risk-draft prompts
  library.py   starter risk library, checklists, safety-file index (DRAFT)
  pdf.py       record PDF and the merged safety-file PDF
  files.py     content-addressed file store + signed links
  auth.py      passwords, sessions, roles
  stt.py llm.py  shared with QuoteBakkie (faster-whisper, Claude)
  tts.py       optional Azure text to speech
  demo.py      demo company for local testing
web/
  app.js       shell, offline cache, outbox, Today/Records/File/More
  forms.js     task sheet, toolbox talk, checks, incident, induction
  manage.js    workers, certificates, risk library, plant + QR, logins
  sign.js      signature pad, photos, voice recorder, GPS
  idb.js       IndexedDB (cached site data, drafts, outbox)
  sw.js        service worker (app shell offline)
```

## Run

```
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env          # add ANTHROPIC_API_KEY
.venv/bin/python -m app.demo  # demo@example.com / demo-pass-1
.venv/bin/uvicorn app.server:app --port 8500 --reload
```

Open http://localhost:8500. Tests: `.venv/bin/python -m pytest -q tests`.

## Deploy (Railway)

1. Add a Postgres database. Railway sets `DATABASE_URL`.
2. Add a volume at `/data` (photos, signatures, documents).
3. Set `ANTHROPIC_API_KEY`, `PUBLIC_URL`, `HAS_SECRET_KEY`, `HAS_SIGNUP_CODE`,
   `CRON_TOKEN` and `RESEND_API_KEY`.
4. Add a daily cron that calls `POST /api/cron/expiry` with the header
   `X-Cron-Token` (expiry emails to owners and safety officers).

## Before the pilot

- [ ] SACPCMP advisor reviews `library.py`: risk items, checklists, safety-file index.
- [ ] John's real forms: compare with the task sheet, talk register and checks.
- [ ] Client's H&S agent: accepts a digital file and electronic signatures?
- [ ] Statutory appointments stay wet-ink + scan (ECT Act s13).
- [ ] isiZulu / isiXhosa / Sesotho speakers check AI talks; record the core talks if needed.
- [ ] Azure Speech key for spoken talks (check the voice list).
- [ ] POPIA: privacy notice, consent wording for worker photos and medicals, retention period.
- [ ] Terms, liability wording and professional indemnity cover.
- [ ] Product name and domain.
- [ ] Cloud speech-to-text (faster-whisper on CPU is slow for long notes).
- [ ] Alembic migrations before the first schema change in production.
