# Vulcan SoA Connection — Connectathon Foundation

SMART on FHIR app for enrolling patients into research studies and tracking their
progress against a Vulcan Schedule of Activities (SoA) V2 protocol graph.

**Target:** HL7 Connectathon — FHIR R6 ballot (`6.0.0-ballot3`), Aidbox.

## Architecture

```
React/Vite SPA  →  FastAPI BFF  →  Aidbox (FHIR R6)
   :5173             :8000            :8888
```

- **SPA** — never holds a FHIR token; talks to the BFF via `HttpOnly` session cookie.
- **BFF** — SMART confidential client; holds tokens server-side; exposes a JSON API.
- **SoA engine** — pure Python module: `PlanDefinition` JSON in, computed schedule-state out.
  Subject progress is derived on every read from existing `Encounter` resources tagged back
  to their originating `PlanDefinition.action.id` — no separate state store.

## Tech stack

| Layer | Stack |
|---|---|
| Backend | Python 3.11+, FastAPI, httpx, pydantic-settings, pytest/respx |
| Frontend | React 18, Vite, TypeScript, react-router-dom, Vitest, Playwright |
| FHIR server | Aidbox `edge` image, FHIR R6 ballot (`6.0.0-ballot3`) |
| Database | PostgreSQL 16 (managed by Docker Compose) |

## Prerequisites

- Docker + Docker Compose
- Python 3.11+
- Node 20+
- [go-task](https://taskfile.dev) (`brew install go-task`)
- An Aidbox license key from [aidbox.app](https://aidbox.app)

## Quick start

```bash
# 1. Clone and enter
git clone <repo> && cd vulcan-soa-connection-41

# 2. Set up env files
cp docker/.env.example docker/.env          # add AIDBOX_LICENSE=<your-key>
cp backend/.env.local.example backend/.env.local   # defaults match Docker

# 3. Start Aidbox (first run pulls ~200 MB)
task aidbox:up

# 4. Install and test the backend
task backend:install
task backend:test

# 5. Load the Vulcan SoA IG fixtures into Aidbox
task fixtures:load-ig          # requires IG output/ directory — see below
task fixtures:load-app         # loads backend/fixtures/

# 6. Run the integration test against live Aidbox
task backend:test-integration

# 7. Start the BFF and frontend dev servers
task dev                       # runs both concurrently
```

Open [http://localhost:5173](http://localhost:5173) — the SPA proxies `/api`, `/launch`,
and `/callback` to the backend.

## Environment files

| File | Purpose | Committed? |
|---|---|---|
| `docker/.env.example` | Template for Docker secrets | Yes |
| `docker/.env` | Real Docker secrets (AIDBOX_LICENSE etc.) | No |
| `backend/.env.local.example` | Template for backend config | Yes |
| `backend/.env.local` | Real backend config | No |
| `backend/.env.connectathon.example` | Connectathon instance config | Yes |

`SMART_CLIENT_SECRET` must match between `docker/.env` and `backend/.env.local`.

## Local Aidbox (Docker)

```
Aidbox UI       http://localhost:8888        admin / admin (default)
FHIR base       http://localhost:8888/fhir
PostgreSQL      localhost:5433
```

The `docker/aidbox/init-bundle.json` bootstraps on first start:
- `Client/vulcan-soa-bff` — SMART confidential client (authorization_code + basic)
- `AccessPolicy/open-for-vulcan-soa-bff` — open policy for dev
- `AccessPolicy/open-for-root` — open policy for the admin/root client

```bash
task aidbox:up       # start (detached)
task aidbox:down     # stop and remove containers
task aidbox:logs     # tail Aidbox logs
task aidbox:reset    # destroy volumes and restart clean
```

## Loading IG fixtures

The Vulcan SoA IG must be cloned separately. The fixture loader is generic —
it walks any directory of `*.json` FHIR resources and PUTs them into Aidbox.

```bash
# Set the IG output path (default: ~/Documents/Devel/hl7/Vulcan-schedule-ig/output)
export VULCAN_IG_OUTPUT_DIR=/path/to/Vulcan-schedule-ig/output

task fixtures:load-ig    # loads IG output/ (PlanDefinitions, StructureDefinitions, …)
task fixtures:load-app   # loads backend/fixtures/ (demo ResearchStudy + Patient)
```

## Backend

```bash
task backend:install          # create .venv and pip install -e ".[dev]"
task backend:test             # run all unit tests (no Aidbox needed)
task backend:test-integration # golden-path test against live Aidbox
task backend:serve            # uvicorn on :8000 with --reload
```

Unit tests: **84 passed, 1 skipped** (integration test gated behind `RUN_INTEGRATION_TESTS=1`).

### Module map

```
backend/src/vulcan_soa/
  config.py          Settings (pydantic-settings, ENV_FILE driven)
  store.py           InMemoryStore[T] — sessions + pending launches
  fhir_client.py     FhirClient — thin Aidbox REST client (raw dicts, no typed models)
  auth.py            PKCE, authorize-URL builder, token exchange, fhirContext parsing
  soa_engine/
    graph.py         parse_protocol_graph → ProtocolGraph (PlanDefinition → DAG)
    conditions.py    evaluate_condition (text/x-soa-expressionplain interpreter)
    engine.py        resolve_schedule_state → ScheduleState
  scheduling.py      Encounter tagging, visit materialization, subject-context loading
  enrollment.py      enroll() — conditional-create ResearchSubject + materialize root visit
  tracking.py        withdraw_subject(), complete_visit()
  api/
    deps.py          FastAPI dependencies (session cookie → FhirClient)
    launch.py        /launch, /launch/standalone, /callback
    context.py       GET /api/context
    research_studies.py   GET /api/research-studies, POST /{id}/enroll
    research_subjects.py  GET /{id}/schedule, POST /{id}/visits/{actionId}/complete, POST /{id}/withdraw
    app.py           create_app() factory
```

## Frontend

```bash
task frontend:install    # npm install
task frontend:test       # vitest run (21 tests)
task frontend:dev        # vite dev server on :5173
task frontend:build      # tsc + vite build
task frontend:e2e        # playwright test (requires running dev servers + Aidbox)
```

### View map

```
src/
  routes.tsx          Landing (context-aware) → StudyWorklist | Enroll | SubjectDashboard
  launch/
    LaunchPending.tsx  Shown while /api/context is in flight
    LaunchError.tsx    /launch-error?reason=untrusted_iss|invalid_state
  views/
    StudyWorklist/     Browse and select a ResearchStudy
    Enroll/            Enroll patient (from launch context or manual FHIR ID entry)
    SubjectDashboard/  Progress, complete visits, decision-support prompt, withdraw
  api/
    client.ts          Typed fetch wrapper (credentials: include)
    types.ts           Shared TS interfaces
```

## SMART launch flow

```
EHR  →  GET /launch?iss=&launch=  →  Aidbox /authorize  →  GET /callback
     ←  session cookie (HttpOnly)  ←  token exchange
SPA  →  GET /api/context           →  {patientId, researchStudyId}
```

Standalone: `GET /launch/standalone` (no EHR context — browse study worklist instead).

## Connectathon switch

To point at the HL7 public Aidbox instance instead of local Docker:

```bash
cp backend/.env.connectathon.example backend/.env.connectathon
# fill in real credentials
export ENV_FILE=backend/.env.connectathon
task backend:serve
```

No code changes required — only the env file differs.

## R6 shape notes (confirmed against live Aidbox edge)

| Resource | Field | R6 shape |
|---|---|---|
| `ResearchSubject` | `status` | Required; `active`/`draft`/`retired`/`unknown` (PublicationStatus). **Withdrawal = `retired`.** |
| `ResearchSubject` | `subjectState` | `0..*` BackboneElement array: `{code: CodeableConcept, startDate: dateTime}` |
| `Encounter` | `status` | `planned` / `in-progress` / `completed` / `discharged` / `unknown`. **`finished` was removed in R6.** |
