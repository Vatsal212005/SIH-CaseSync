# AICTE CaseSync

AICTE CaseSync is a production-structured demonstration of an internal complaint monitoring and cross-bureau coordination platform for SIH26264. It combines a role-aware operations console, auditable complaint workflows, institution intelligence, SLA monitoring, reports, private attachments, and an explainable human-in-the-loop overlap engine.

The repository runs either as a Docker deployment with PostgreSQL/pgvector or as a fully functional native Windows development installation with SQLite. The native launcher uses the same API, workflows, synthetic records, overlap engine and user interface; no government database, private API or external institutional system is required.

> **Data notice:** AICTE supplied no official dataset, institution database, complaint history, or internal credentials. Every seeded institution, person and case is deterministic synthetic demonstration data, labeled in the database and UI. CaseSync does not claim official AICTE deployment or endorsement.

## Included capabilities

- Secure HttpOnly-cookie authentication, CSRF protection, password hashing, login lockout, server-side RBAC and bureau scoping.
- Canonical institution registry with aliases, duplicate prevention, filters, detail intelligence and validated CSV import.
- Complaint registration, assignment, remarks, transfer/acceptance, escalation, disposal, reopening, attachment storage, related-case links and immutable action history.
- Hybrid overlap detection using canonical identity, bureau/activity rules and `sentence-transformers/all-MiniLM-L6-v2` embeddings stored in PostgreSQL with pgvector; deterministic degradation preserves workflows if the model is unavailable.
- Explainable findings, severity, side-by-side comparison, persistent human review, suppression by text fingerprint, case linking and coordination creation.
- Interactive evidence studio with three deterministic scenarios, full complaint text, visible MiniLM/rule evidence, explicit human review, coordination and SLA before/after states, technical/presentation modes, and recoverable sessions.
- Central dashboard, database-backed global search, personal queues, notifications and idempotent scheduled SLA reminders.
- Coordination records, participants, owners, action items and deadlines.
- Filtered analytics plus database-derived CSV and PDF exports.
- Administrative user, SLA, threshold and integration-adapter configuration with audit events.
- Idempotent deterministic seed: 100 institutions, 1,000 coherent complaints, 4 bureaus, role-specific officials, lifecycle history and computed overlaps.
- Alembic migrations, Docker health checks, persistent PostgreSQL/upload/model volumes, OpenAPI, unit/integration tests and Playwright journeys.

## Architecture

```text
SIH/
├── frontend/                 Next.js App Router operations console
│   ├── app/                  catch-all authenticated application routes
│   ├── components/           dashboard, registry, cases, AI review, reports
│   ├── lib/                  credentialed API client and CSRF handling
│   ├── tests/                Vitest UI tests
│   └── e2e/                  Playwright user journeys
├── backend/
│   ├── app/
│   │   ├── api/              REST endpoints and exports
│   │   ├── core/             configuration, database, authentication
│   │   ├── integrations/     configurable external ingestion boundary
│   │   ├── jobs/             idempotent SLA scheduler
│   │   ├── ml/               embedding, scoring and 120-pair evaluation
│   │   ├── models/           normalized SQLAlchemy domain
│   │   ├── schemas/          Pydantic request contracts
│   │   ├── services/         audit, workflow, SLA and overlap services
│   │   └── tests/            backend workflow/integration tests
│   └── alembic/              versioned schema migration
├── docs/                     architecture, AI, API and demo guide
├── docker-compose.yml
└── .env.example
```

See [ARCHITECTURE.md](docs/ARCHITECTURE.md), [AI_ENGINE.md](docs/AI_ENGINE.md), [API.md](docs/API.md), [DEMO_GUIDE.md](docs/DEMO_GUIDE.md), the [complete prototype walkthrough](docs/COMPLETE_DEMO_WALKTHROUGH.md), and the [three-minute SIH presentation script](docs/SIH_3_MINUTE_DEMO.md).

## Product tour

| Workspace | Purpose | Backing behavior |
|---|---|---|
| Overview | Command dashboard, action centre, KPI cards, trend charts, bureau workload and urgent cases | Aggregated from the current complaint, institution, overlap and SLA records |
| Interactive Demo | Guided, repeatable proof of overlap detection, false-positive control and SLA escalation | Creates isolated synthetic records through the same backend services used by the normal UI |
| Institutions | Canonical registry, aliases, filters, duplicate prevention and institution-level intelligence | Searchable SQL records with CSV intake and data provenance |
| Complaints | Registration, assignment, remarks, transfer, escalation, disposal, reopening, attachments and links | Server-authorized lifecycle transitions with immutable action history |
| Overlap Intelligence | Ranked cross-bureau findings, side-by-side evidence, human review and coordination initiation | Hybrid MiniLM plus deterministic administrative signals; no hardcoded match outcomes |
| Coordination Center | Lead bureau, participants, owner, target date and accountable action items | Persistent cross-bureau records created only after an explicit workflow action |
| My Work Queue | Bureau- and officer-scoped operational work | Derived from assignments, role scope, deadlines and unresolved actions |
| Alerts & Notifications | Overlap, transfer, coordination and SLA signals | Database-backed, recipient-scoped and idempotently generated |
| Reports & Analytics | Filters, status/category/bureau analysis, CSV export and PDF reporting | Calculated from stored records; empty date filters are omitted from API requests |
| Audit Trail | Actor, event, entity and timestamp evidence | Append-only operational audit events |
| Administration | Users, roles, bureau membership, SLA policies, AI thresholds and adapters | Restricted to authorized administrative roles |

All application routes are served by the optional catch-all Next.js page, so `/institutions`, `/complaints`, `/demo`, `/overlaps`, `/coordination`, `/reports` and detail pages work both through sidebar navigation and direct browser loads.

## Interactive demonstration scenarios

The Demo Center is intentionally deterministic at the input level so a presentation is repeatable, while every output is produced by real application services and current database state.

1. **AI detects duplicate investigations** — registers a canonical synthetic institution, receives paraphrased complaints in PGRC and the Regulation Bureau, runs actual MiniLM inference, displays explainable evidence, records a separate human decision, and creates accountable coordination.
2. **Same institution, different complaints** — proves that sharing an institution does not automatically make two cases duplicates; unrelated subject matter can be reviewed and suppressed.
3. **SLA violation and escalation** — shows configured deadlines, an overdue transition, recipient notifications, escalation and the updated lifecycle/audit evidence.

The UI distinguishes model classification, ranking score, human review state and administrative action. The overlap score is not presented as a probability or autonomous legal decision.

## Complaint and overlap lifecycle

```text
Complaint received
  -> canonical institution/category resolution
  -> bureau assignment and SLA calculation
  -> embedding plus deterministic candidate comparison
  -> explainable overlap finding
  -> authorized human review
  -> optional case link and cross-bureau coordination
  -> action ownership, notifications and audit evidence
  -> disposal or reopening
```

Candidate generation is constrained by canonical institution and lifecycle relevance. The engine then combines semantic similarity with transparent rule features such as shared institution, related category, cross-bureau ownership and active status. Review decisions persist independently of the computed classification, and text fingerprints allow stale decisions to be invalidated when complaint content materially changes.

## Fastest start on Windows 11 without Docker

### Prerequisites

- Windows 11 with PowerShell 5.1 or newer.
- 64-bit Python 3.12. Python 3.13 is not used by the native launcher because native scientific packages can be unstable with that interpreter combination.
- Node.js 20 or newer with `npm`.
- Roughly 3 GB of free space for Python packages, frontend dependencies and the MiniLM model cache.

### First-time preparation

Run these commands from the repository root:

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

Push-Location frontend
npm ci
Pop-Location
```

Download the public MiniLM model once while online. The normal launcher subsequently forces offline, CPU-only inference and reuses this cache:

```powershell
backend\.venv\Scripts\python.exe -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

Start the complete application and open it in Brave:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-dev.ps1 -OpenBrave
```

The launcher:

- validates that `backend\.venv` uses Python 3.12;
- selects SQLite without altering the PostgreSQL/Docker configuration;
- applies Alembic migrations and runs the idempotent deterministic seed;
- enables demo accounts and the clearly labeled synthetic dataset;
- configures CPU-only, offline Sentence Transformers inference;
- starts FastAPI on `http://localhost:8000` and Next.js on `http://localhost:3000`;
- waits until both services are healthy, avoids duplicate processes and records exact process identities;
- writes timestamped diagnostics under `.runlogs`.

Stop only the processes recorded for this CaseSync checkout:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\stop-dev.ps1
```

Repeated starts reuse healthy CaseSync listeners. If either port is owned by an unrelated program, the launcher reports the PID and leaves it untouched.

### Verified native configuration

The native Windows workflow has been exercised with Python 3.12.7, CPU-only PyTorch, SQLite and `sentence-transformers/all-MiniLM-L6-v2`. Verification covered:

- database migration and idempotent synthetic seeding;
- authenticated dashboard, institution and complaint APIs;
- complaint registration and case-detail workflows;
- real 384-dimensional MiniLM inference and computed overlap findings;
- overlap review, transfers and cross-bureau coordination;
- reports, analytics, notifications and SLA scanning;
- a controlled stop/start cycle with SQLite data preservation;
- the complete Playwright end-to-end suite, including all three interactive demonstration journeys and refresh recovery.

## Run with Docker (recommended)

Prerequisites: Docker Desktop with Compose and roughly 6 GB of free disk space for images and the local embedding model.

```powershell
Copy-Item .env.example .env
# Replace SECRET_KEY in .env with a long random value.
docker compose up --build
```

Open:

- Operations console: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Health/AI diagnostic: `http://localhost:8000/api/v1/health`

Startup waits for PostgreSQL, applies Alembic migrations, and runs the idempotent seed command. First model use downloads the open-source model into the persistent `model_cache` volume. Core case workflows remain available if that download fails, while the health/settings response clearly identifies the fallback backend.

Stop without deleting persistent data:

```powershell
docker compose down
```

## Local development

Backend:

```powershell
cd backend
python -m pip install -r requirements.txt
$env:DATABASE_URL = "sqlite:///./casesync.db"  # local lightweight option
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

Frontend, in a second terminal:

```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_URL = "http://localhost:8000/api/v1"
npm run dev
```

For normal Windows use, prefer `start-dev.ps1`; the manual commands above are useful when debugging either service interactively.

PostgreSQL plus pgvector is the deployment target. SQLite exists only for lightweight local tests; `VectorType` switches to a native 384-dimensional pgvector column and HNSW cosine index under PostgreSQL.

## Demonstration accounts

Demo accounts are created only when `DEMO_MODE=true`. The default development password comes from `DEMO_PASSWORD`.

| Role | Email | Default development password |
|---|---|---|
| System Administrator | `admin@casesync.demo` | `CaseSync@2026` |
| Central Administrator | `central@casesync.demo` | `CaseSync@2026` |
| Auditor | `auditor@casesync.demo` | `CaseSync@2026` |
| Bureau Head | `head.rb@casesync.demo` | `CaseSync@2026` |
| Case Officer | `officer1.rb@casesync.demo` | `CaseSync@2026` |

Equivalent bureau-head and officer accounts exist for `pgrc`, `ab` and `swc`. Never enable demo seeding or reuse this password in a production environment.

## CSV ingestion

Institution CSV required columns:

```text
permanent_id,name,address,city,state,region,postal_code,institution_type,approval_status
```

Optional column: `contact_email`.

Complaint CSV required columns:

```text
institution_permanent_id,title,description,category,priority,source,stakeholder_type,date_received,bureau_code
```

Dates use `YYYY-MM-DD`; priority uses `low`, `medium`, `high`, or `critical`. Imports resolve existing canonical IDs, validate each row, prevent duplicate institutions, persist an import job and return row-numbered errors. Imported records are marked non-synthetic. `backend/app/integrations` defines the adapter protocol for a future authorized API or file-transfer source.

## Verification commands

```powershell
cd backend
python -m ruff check app
python -m pytest --cov=app
python -m app.ml.evaluate --sweep

cd ../frontend
npm test
npm run lint
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

Docker integration verification:

```powershell
docker compose config
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8000/api/v1/health
```

## Environment

All options are documented in `.env.example`. In production, use a high-entropy `SECRET_KEY`, set `DEMO_MODE=false`, provide a managed PostgreSQL/pgvector database, use TLS at the ingress, restrict `CORS_ORIGINS`, scan uploads, back up database/storage volumes, and run the idempotent SLA job from a single scheduler or job runner.

## Troubleshooting

- **Model unavailable:** inspect `/api/v1/health`. Workflows continue using identity/rule matching and a named feature-hash fallback; no semantic score is presented as transformer-derived.
- **No demo records:** ensure `DEMO_MODE=true`, then run `python -m app.seed`. The command is idempotent by seed version.
- **Browser cannot authenticate:** confirm `CORS_ORIGINS` exactly matches the frontend origin and both services use the same scheme/host family.
- **Migration failure:** verify the database health check and that the database user can create the `vector` extension.
- **CSV errors:** the response contains source line numbers and validation messages; correct those rows and re-import.

## Official integration status

No official government infrastructure is required or simulated as connected. Authorized AICTE integration would require data-owner approval, documented field mappings, credentials, network allow-listing, retention rules and a security assessment. The configured adapter boundary supports adding that source without rebuilding complaint, overlap, coordination or reporting workflows.

