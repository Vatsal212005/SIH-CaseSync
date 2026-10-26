# API Overview

Interactive OpenAPI is served at `/docs`; the machine-readable specification is `/openapi.json`. All business endpoints use `/api/v1`.

| Area | Representative endpoints |
|---|---|
| Health/auth | `GET /health`, `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`, `POST /auth/change-password` |
| Dashboard/search | `GET /dashboard`, `GET /search?q=` |
| Institutions | `GET/POST /institutions`, `GET/PUT /institutions/{id}`, `POST /institutions/import` |
| Complaints | `GET/POST /complaints`, `GET /complaints/{id}`, `POST /complaints/{id}/actions`, `POST /complaints/import` |
| Documents | `POST /complaints/{id}/attachments`, `GET /attachments/{id}` |
| Overlap | `GET /overlaps`, `GET /overlaps/{id}`, `POST /overlaps/{id}/review` |
| Coordination | `GET/POST /coordination`, `POST /coordination/{id}/actions`, `PATCH /coordination/actions/{id}` |
| Alerts | `GET /notifications`, `POST /notifications/read` |
| Reports | `GET /reports/summary`, `GET /reports/export.csv`, `GET /reports/export.pdf` |
| Governance | `GET /audit`, `/admin/users`, `/admin/settings`, `/admin/sla`, `/admin/run-sla` |

Login sets `casesync_session` (HttpOnly) and `casesync_csrf` cookies. Mutation clients must send the latter value as `X-CSRF-Token`. Authentication failures return 401, permission failures 403, validation errors 422 and invalid state transitions 409. Results are always re-scoped on the server; navigation visibility is only a usability aid.

