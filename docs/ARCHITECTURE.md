# CaseSync Architecture

## System context

The browser uses a Next.js App Router client against a versioned FastAPI REST API. FastAPI owns authorization and all business decisions. SQLAlchemy persists normalized state in PostgreSQL; embeddings use pgvector and files live in a private volume reachable only through an authorized download endpoint.

```text
Browser / Next.js
      │ credentialed HTTPS + CSRF token
      ▼
FastAPI API ─────────── private attachment storage
      │
      ├── workflow + audit transaction
      ├── overlap engine ── local MiniLM inference
      ├── report renderer
      └── hourly idempotent SLA job
      │
      ▼
PostgreSQL + pgvector
```

## Domain and integrity

The schema separates canonical institutions and aliases, bureaus and users, complaints, append-only actions, attachments, embeddings, overlap findings/reviews, related links, coordination participants/actions, SLA policies, notifications, audit events, imports and settings. Foreign keys prevent orphaned records; natural identities have uniqueness constraints; workload, status, date and scope fields are indexed.

`Complaint.status` is current state. `ComplaintAction` separately preserves transfers, assignments and historical transitions. No case-history endpoint performs a hard delete. Related links use an `active` flag so unlinking can retain evidence.

## Authentication and authorization

- Passwords use bcrypt with a work factor of 12.
- Signed JWT sessions are stored in HttpOnly, SameSite cookies with configured expiry.
- A separate readable SameSite CSRF cookie must match `X-CSRF-Token` on every mutation.
- Five roles are enforced on the API. Bureau heads and officers are scoped to their bureau; an officer can mutate only an assigned complaint. Auditors are read-only.
- Five consecutive failures temporarily lock login. Passwords and complaint bodies are excluded from structured logs.
- Attachments are allow-listed by content type and size, renamed with random storage IDs, hashed, stored privately and downloaded only after case-scope authorization.

## Transaction and event design

Each material mutation updates the domain record and adds an audit/action event before one commit. Workflow transitions use a finite transition map. Transfers preserve source/destination, clear assignment and require receiver acceptance. Confirmed overlaps create related-case and optional coordination records in the same transaction. Notification `dedupe_key` prevents repeated SLA/overlap alerts.

## Search, reports and performance

Lists are paginated and filtered in SQL. Global search covers complaint number/title/body plus institution name/ID. Reports reuse one authorized query for summary, CSV and PDF so totals reconcile. Eager loading prevents common list N+1 access. PostgreSQL deployment adds an HNSW cosine index; overlap detection first narrows candidates by canonical institution and active state instead of comparing the corpus exhaustively.

## Data integration

The system is synthetic-first. CSV adapters validate contract fields, resolve canonical references and persist import diagnostics. `IngestionAdapter` is the stable provider interface for an eventual authorized API/SFTP connector. Integration enablement lives in `application_settings`; the official API adapter is disabled until real authorization and credentials exist.

## Reliability and deployment

Docker Compose supplies PostgreSQL/pgvector, a persistent database volume, attachment volume and model cache. Database/backend health checks order startup. Alembic owns schema changes; startup never drops tables. Expensive model loading is lazy. When it fails, the diagnostic changes to `feature-hash-fallback`, deterministic rules still operate, and case management remains available.

For horizontally scaled production, run the idempotent SLA job from one scheduler rather than in every API replica, move uploads to encrypted object storage behind the same access service, terminate TLS at a trusted ingress, centralize JSON logs, scan uploaded content, and use managed secrets/backups.

