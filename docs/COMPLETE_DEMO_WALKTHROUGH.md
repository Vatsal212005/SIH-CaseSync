# AICTE CaseSync — Complete Prototype Demonstration & Presentation Guide

> **Demonstration boundary:** Every institution, complaint, user, notification, audit event, and metric shown by this local build is synthetic. The prototype is not connected to AICTE systems and must not be presented as an official deployment.

This guide is the presenter’s operating manual for the current CaseSync build. It was written against the repository and a live Windows/Brave session, not from mock-ups. Counts and complaint IDs change as demonstrations create real records, so describe the behavior and evidence rather than memorising a number.

## 1. The story to tell

AICTE CaseSync addresses a coordination failure: two bureaus can receive differently worded complaints about the same institution, investigate independently, and issue duplicated or conflicting actions. CaseSync creates a shared operational view, detects possible overlap with semantic and deterministic evidence, keeps a human reviewer in control, and converts an accepted relationship into accountable cross-bureau work.

The prototype proves five things end to end:

1. A complaint is a real database record with an auditable lifecycle.
2. The AI compares meaning rather than exact wording.
3. The UI explains why a pair was surfaced and never treats a similarity score as a verdict.
4. A confirmed relationship creates a coordination record, ownership, actions, deadlines, alerts, and audit events.
5. The system remains useful without an official dataset: deterministic synthetic data drives all workflows, reports, notifications, and inference, while CSV and adapter boundaries support later authorised integration.

## 2. Before judges arrive

### One-command startup

From the project root in PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-dev.ps1 -OpenBrave
```

The launcher uses the existing Python 3.12 virtual environment, SQLite, the CPU-only model cache, and the synthetic seed. It avoids duplicate CaseSync processes, writes logs under `.runlogs/`, and prints both URLs.

To stop only the CaseSync processes recorded by the launcher:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\stop-dev.ps1
```

Useful URLs:

- Product: `http://localhost:3000`
- API health: `http://localhost:8000/api/v1/health`
- OpenAPI: `http://localhost:8000/docs`

### Demo credentials

Primary presenter account:

- Email: `central@casesync.demo`
- Password: `CaseSync@2026`
- Role: Central AICTE Administrator

Role-switch accounts use the same password:

- `admin@casesync.demo` — System Administrator
- `auditor@casesync.demo` — Auditor, read-only
- `head.rb@casesync.demo` — Recognition Bureau head
- `officer1.rb@casesync.demo` — Recognition Bureau case officer
- Equivalent `head.*` and `officer1.*` accounts exist for the other seeded bureaus.

### Two-minute technical check

1. Open the health URL. Confirm `status: ok`, `database: connected`, and `demo_mode: true`.
2. Open the frontend and sign in as the central administrator.
3. Open **Reports & Analytics** once. It should render without HTTP 422; empty date filters are intentionally omitted from the request.
4. Open **Interactive Demo**. Use **Continue current session** to recover an interrupted run, or **New isolated run** for a clean narrative. A new run archives only the previous session; it never deletes its records.
5. Scenario A now includes the explicit review and coordination controls inside the studio, so a second tab is optional.
6. Do not reset or reseed the database immediately before presenting. The existing history helps demonstrate persistence and auditability.

### Recommended room setup

- Use 100–125% browser zoom and a 1080p display.
- Hide unrelated tabs and notifications.
- Keep the machine on power; the first model load can be slower than later inference.
- Have this guide open on a second device or printed.
- Keep the newest backend/frontend `.out.log` and `.err.log` files under `.runlogs/` available only as a fallback; do not lead with terminals.

## 3. Orientation: what the audience sees

After login, point out the permanent banner: **“SYNTHETIC DEMONSTRATION DATA — Not an official AICTE deployment or connected institutional record system.”** This is deliberate governance, not a disclaimer hidden in fine print.

The left navigation for a central administrator contains:

- Overview
- Interactive Demo
- Institutions
- Complaints
- Overlap Intelligence
- Coordination Center
- My Work Queue
- Alerts & Notifications
- Password & Security
- Reports & Analytics
- Audit Trail

The header provides global case/institution/ID search, **Take a Tour**, notifications, current identity and role, and sign-out.

### Dashboard talking points

The page title is **Complaint command overview**. Show:

- operational KPI cards for total, pending, in-process, overdue, disposed, transferred, escalated, overlap review, near-SLA cases, and active institutions;
- **Action Center** and **My assigned work** as the operational starting point;
- Complaint volume over time, category distribution, bureau workload, and cases requiring attention;
- that every card is computed from SQLite records, not hardcoded showcase values.

Say: “These numbers are intentionally live. Running a demo changes the database, and the dashboard reconciles with that change.”

## 4. Guided tour and role-aware navigation

Click **Take a Tour** in the header. Use it as a 30-second orientation to the command dashboard, intelligence queue, and operations areas. The tour is helpful for first-time evaluators; dismiss it before timed demonstrations.

Role switching is explicit: sign out, then sign in with another seeded account. There is no in-page role-switch impersonation control.

| Role | Scope and useful demonstration |
|---|---|
| System Administrator | Full data scope plus users, departments, and settings. |
| Central Administrator | Cross-bureau operations, review, coordination, reports, and audit. Best presenter role. |
| Bureau Head | Records for the assigned bureau; can review overlaps and coordinate within authorised scope. |
| Case Officer | Assigned complaint workload and permitted case actions. |
| Auditor | Broad read-only evidence, reports, and audit inspection; mutations are blocked server-side. |

Navigation visibility is a convenience; FastAPI enforces the same permissions and bureau scope. A hidden button is never the security boundary.

### Screen-by-screen presenter reference

Use this as the beginner-friendly map. The later sections provide the long workflows.

| Actual screen heading | How to reach it | What to do and expect | Permission / technical note / presenter line |
|---|---|---|---|
| **Complaint command overview** | Sidebar → **Overview** | Inspect KPIs, Action Center, charts, and cases requiring attention; open a queue item to reach the complaint. | All signed-in roles see authorised aggregates. Say: “This is a live command view, not a static executive dashboard.” |
| **Global search** (header control) | Click **Search cases, institutions, IDs…** anywhere; type at least two characters | A dropdown returns authorised complaints and institutions; selecting a result opens its detail. | Results are server-scoped to the user. Shorter text deliberately sends no search. |
| **Watch CaseSync reason, decide and coordinate** | Sidebar → **Interactive Demo** | Select one of three cards, click **Start isolated demo**, then follow the evidence-first steps. Toggle **Presentation mode** or **Technical details** as needed. | System/central admins and bureau heads can advance demos. Active and completed sessions can be recovered after refresh or navigation. |
| **Institution registry** | Sidebar → **Institutions** | Search by name, ID or city; page results; select an institution. System/central admins also see **Import CSV** and **Add institution**. | The directory is role-scoped. Say: “One canonical identity prevents spelling variants from fragmenting history.” |
| **Institution intelligence overview** | **Institutions** → choose a row | Read KPIs, identity, cross-bureau evidence boundary, charts, recent activity, overlaps, coordination, and complaint history. | Database aggregation only; it does not assert wrongdoing or duplication. |
| **Complaints** | Sidebar → **Complaints** | Search, filter by status, clear filters, page results, open a case, register, or import CSV. | Auditors cannot register; CSV import is shown to system/central admins. Lists are loaded from the API. |
| **Complaint record** | **Complaints** → click a case number | Inspect metadata/history/AI findings/related cases/documents/Case Journey; perform role- and status-appropriate actions. | Each mutation is validated server-side and adds history/audit evidence. |
| **Overlap intelligence** | Sidebar → **Overlap Intelligence** | Filter queue by review state and open a finding. | Queue entries are computed and stored findings; they are not hardcoded card content. |
| **AI Case Comparison** | Overlap queue → click a finding | Compare both cases, inspect semantic and deterministic evidence, then confirm/reject/mark unrelated; choose **Coordinate Cases** when appropriate. | Decision controls require an authorised reviewer. Similarity is advisory. |
| **Coordination center** | Sidebar → **Coordination Center** | Review ownership, participating bureaus, action count, status and target; use **Assign action item** when demonstrating a mutation. | Central/system roles can complete all items; an assigned user can complete their own. Completion is immediate. |
| **My work queue** | Sidebar → **My Work Queue** | Open an active case from the table of institution, required action, priority and SLA. | Central users see a broad authorised queue; officers are assignment-scoped. |
| **Notifications** | Sidebar → **Alerts & Notifications** or bell icon | Open an alert to mark it read and navigate to its destination. | **Mark all read** is a real state change. Notifications come from workflow, overlap, coordination, and SLA services. |
| **Password & security** | Sidebar → **Password & Security** | The form asks for Current password, New password and Confirm new password; **Change password** enables only for matching values of at least 10 characters. | CSRF-protected and audited. Do not change the shared demo password during a presentation. |
| **Reports & analytics** | Sidebar → **Reports & Analytics** | Select a report, bureau, region and optional dates; inspect KPIs/charts/table; export CSV or PDF. | All signed-in roles receive authorised aggregates. Empty dates are omitted rather than sent as invalid strings. |
| **Audit trail** | Sidebar → **Audit Trail** | Read time, actor, event, entity and request columns; correlate a demo action with its event. | Visible to system admin, central admin and auditor; append-only. |
| **User & bureau management** | Sign in as system admin → sidebar item | Inspect user role/bureau/status; controls can create/deactivate users, bureaus and categories. | System-admin only. The buttons mutate persistent configuration, so show without clicking during judging. |
| **Settings** | System admin → sidebar → **Settings** | Inspect runtime backend/model, overlap thresholds, integration adapters and SLA policies; **Run SLA scan** is available. | System-admin only. Saving thresholds/SLA or running a scan is persistent and audited. |
| **CaseSync product tour** | Header → **Take a Tour** | Use **Next**, **Back**, **Skip**, and **Finish** across eight spotlights: Dashboard, Institutions, Complaints, Overlap Intelligence, Coordination Center, Action Center, Reports, Interactive Demo. | Tour position survives its route changes in session storage and completion is remembered locally. |

For every operational page, use the same four-part narration: identify the evidence on screen, perform one intentional action, state the expected database/workflow result, and connect it to prevention of duplicate or conflicting bureau work.

## 5. The Interactive Demo Center

Open **Interactive Demo**. The title is **Watch CaseSync reason, decide and coordinate**. Explain that its buttons call the same services used by the normal product. The sequence is deterministic for presentation, but outcomes are computed and persisted rather than painted into the UI. The studio has a guided step rail, a central evidence stage, and a live persisted-state panel.

Three scenario cards are available:

1. **AI detects duplicate investigations**
2. **Same institution, different complaints**
3. **SLA violation and escalation**

Each run is isolated with a demo session ID and uses clearly synthetic records. **New isolated run** archives the current session and starts another; it does not erase complaints, findings, coordination records, notifications, or audit history. **Continue current session** recovers an interrupted run. **Presentation mode** removes navigation chrome; **Technical details** exposes model, backend, dimensions, thresholds and record identifiers.

### Scenario A — AI detects duplicate investigations

Purpose: show semantic matching across paraphrases, explainable hybrid scoring, human review, and coordination.

1. Click **Start isolated demo** on **AI detects duplicate investigations**.
2. Run **Register canonical institution** and inspect the new database identity.
3. Run **Receive PGRC complaint** and **Receive Regulation Bureau complaint**. Each full allegation is displayed as a separate persisted record with different bureau ownership.
4. Run **AI overlap analysis**. The backend generates normalized 384-dimensional MiniLM embeddings, calculates cosine similarity, applies deterministic institutional/workflow evidence, and stores a reviewable finding only if policy permits.
5. Read the actual semantic score, classification, hybrid breakdown, reasons, and storage outcome. The interface labels the score as a prioritisation signal—not a probability.
6. In **Human review**, choose Confirm, Unrelated, or Reject, add reasoned notes, and click **Record explicit human decision**. Nothing is coordinated before this separate authorized action.
7. If confirmed, assign the officer, action, due date and remarks, then click **Create accountable coordination**.
8. Use the final result and **Live system state** to open the persisted complaints, finding, coordination, notifications, and audit evidence.

One verified run produced approximately 73% semantic similarity and an 83% hybrid score, classified as a high-severity cross-bureau relationship. Treat those as an observed example, not a promised constant.

Important distinction: the AI analysis, human decision, and coordination creation are three separate steps. CaseSync never converts a score into an administrative decision automatically. Refreshing or navigating away no longer loses the session: return to **Interactive Demo** and choose **Continue current session**.

#### Explain the hybrid score precisely

The current formula is:

```text
hybrid = 0.62 × semantic similarity
       + 0.18 × same canonical institution
       + 0.08 × category match
       + 0.07 × cross-bureau ownership
       + 0.05 × both cases active
```

The result is capped at 1.00. This is not a probability that complaints are duplicates. It is a prioritisation score combining semantic evidence with known administrative facts.

The system labels relationships using transparent rules:

- likely duplicate: same institution, same category, semantic similarity at least 0.82;
- cross-bureau related: same institution, different bureaus, semantic similarity at least 0.52;
- shared institution activity: same institution and different bureaus, without the stronger semantic condition;
- similar, different institution: semantic similarity at least 0.86;
- unrelated otherwise.

Severity uses hybrid thresholds: critical at 0.90, high at 0.75, medium at 0.55, and low below that. Only non-unrelated candidates at or above the storage policy threshold are added to review.

### Scenario B — Same institution, different complaints

Purpose: demonstrate false-positive control and that institutional coincidence is not treated as duplication.

1. Click **Start isolated demo** on **Same institution, different complaints**.
2. Register the synthetic institution, then create the fee and laboratory complaints.
3. Inspect both complete descriptions side by side.
4. Run **AI distinction analysis** and read the actual semantic score and deterministic comparison.
5. Run **Explain the computed outcome**, then inspect the false-positive-control summary.

This is a stronger demonstration than showing only a “good match.” MiniLM still performs and displays the comparison, while storage policy can suppress an unrelated or low-confidence pair. A raw computed score is visible even when no reviewable finding is persisted; the UI clearly separates analysis from storage outcome.

Say: “Institution identity is a candidate-generation signal, not a duplicate verdict.”

### Scenario C — SLA violation and escalation

Purpose: show time-based operational control, assignment, alerting, escalation, and audit history.

1. Click **Start isolated demo** on **SLA violation and escalation**.
2. Register the institution and receive the high-priority complaint with an imminent synthetic deadline.
3. Run **Officer assigned** to create named ownership and a case-history event.
4. Run **SLA monitoring**. The studio shows the deadline path and whether a new or already-existing notification was found. Alerts are idempotent.
5. Run **Escalation recorded** to persist the status transition, reason, notifications and audit evidence.
6. Open the generated complaint. Show status, officer, SLA date, next action, and the immutable **Case Journey**.
7. Open **Alerts & Notifications** to show the “SLA deadline approaching” and “Complaint escalated” events.
8. Open **Audit Trail** and point to the corresponding `complaint.assign`, `complaint.escalate`, and `demo.advanced` events.

## 6. Normal complaint lifecycle, click by click

The Demo Center is not the only path. Use the normal screens to prove full case handling.

### Register a complaint

1. Open **Complaints**.
2. Click **Register complaint**.
3. Search for and select an institution. CaseSync stores the selected canonical institution ID, preventing name-only matching.
4. Enter **Complaint title**.
5. Enter **Full description**; at least 20 characters are required.
6. Select category, priority, source, reporting stakeholder, date received, and assigned bureau.
7. Optionally choose an officer.
8. Submit. The complaint, initial history, audit event, and overlap evaluation are persisted.

The list supports search and filters; click the complaint number to open its record.

### Read the complaint detail

The detail page shows:

- complaint number and title;
- status and priority;
- canonical institution and institution link;
- category, bureau, assigned officer, received date, SLA deadline;
- latest action and next required action;
- immutable action history;
- overlap findings and related cases;
- attachments and upload control;
- the chronological **Case Journey** and bureau flow.

Use a clean scenario record for presentation. A heavily reused development complaint can have many findings and make the story visually noisy.

### Edit and re-evaluate

Click **Edit details**. The editable fields are title, description, category, priority, and next required action. The save button deliberately says **Save and re-evaluate overlap**. A content fingerprint prevents duplicate findings for unchanged text; changed content is evaluated again.

### Start, assign, remark, transfer, accept, escalate, dispose, reopen

Available actions depend on status and role:

- **Start** moves a pending complaint into active processing.
- **Assign** selects an authorised officer.
- **Remark** records an official case note.
- **Transfer** requires a destination bureau and justification; the existing officer is cleared.
- **Accept Transfer** records receipt by the destination bureau.
- **Escalate** marks the case for elevated attention and creates operational signals.
- **Dispose** closes the active case with official remarks.
- **Reopen** returns a disposed complaint to active handling with a reason.

Every action uses the official remarks/justification field and writes history plus audit evidence. Transfers are intentionally two-sided: sending is not the same as accepting.

### Attach evidence and link a related case

The Documents panel accepts authorised PDF, image, text, and CSV evidence. Files receive private random identifiers and hashes; download still requires case access.

Central/system administrators and bureau heads can manually link a case as **Related**, **Likely duplicate**, **Shared institution**, or **Potential conflicting action**, with a justification. This is separate from an AI finding and is useful when officers know contextual evidence the model does not.

### Safe manual example for practice

Create a new record instead of editing an important seeded case:

- Institution: choose an existing institution whose name begins with `DEMO`, or create/import only if your role and rehearsal plan explicitly require it.
- Title: `Synthetic practice complaint — duplicate examination processing fee`
- Description: `Synthetic rehearsal record: the institution allegedly requested an additional examination processing payment after the published fee had already been collected.`
- Category: choose the available fee-related category.
- Priority: Medium.
- Source: choose the available portal/email-style source.
- Reporting stakeholder: Student.
- Date received: today.
- Bureau: Recognition Bureau.
- Officer: leave unassigned initially.

After submission, use **Start**, **Assign**, and **Remark** with text beginning `Synthetic rehearsal:`. To practise transfer, transfer to another bureau with an explicit rehearsal justification, sign in as an authorised recipient if needed, and use **Accept Transfer**. End by disposing and reopening only this practice record. Attach only a harmless test text/PDF, never personal data. Search its generated `CMP-...` number in **Audit Trail** and the complaint’s **Case Journey**.

## 7. Overlap Intelligence and human review

Open **Overlap Intelligence**. The queue can be filtered by **Pending review**, **Confirmed**, **Rejected**, **Unrelated**, or **All**. Columns show the finding, both complaints, institution, hybrid score, severity, and review state.

Click a finding to open **AI Case Comparison**:

- Complaint A and Complaint B appear side by side.
- The centre panel shows semantic similarity, with the wording “Similarity is advisory, not a probability of duplication.”
- Deterministic evidence lists same institution, cross-bureau ownership, lifecycle state, category and other matching reasons.
- Engine classification and human-review state are shown separately.
- The reviewer can **Confirm relationship**, **Mark unrelated**, or **Reject finding**.

The full hybrid score appears in the queue and complaint overlap chips. The comparison view emphasises semantic similarity and the evidence components rather than repeating the hybrid score; explain this before a judge asks why the two values are on different screens.

Never say “the AI confirmed a duplicate.” Say “the engine prioritised a pair; an authorised officer reviewed the evidence and recorded the decision.”

### Coordination wizard

From a confirmed/reviewable pair, choose **Coordinate Cases**. The wizard has four stages:

1. **Review cases** — confirm the pair and institution.
2. **Assign responsibility** — choose the lead owner, responsible officer, participating officers, next action, due date, and remarks.
3. **Confirm** — review the proposed cross-bureau record.
4. **Created** — the coordination record is persisted; linked complaints, participants, notifications, and audit events are created.

The final **Open Coordination Workspace** action currently opens the Coordination Center list focused on the operational area; there is not a separate rich coordination-detail route in this build. Present it accurately as a coordination record/work queue rather than claiming a dedicated chat workspace.

## 8. Coordination Center and personal work

Open **Coordination Center**. Its table shows coordination title, institution, owner, participating bureaus, action count, status, and target date.

Use **Assign action item** to choose a coordination record, required action, owner, and deadline. An authorised user can complete open actions. The completion check control acts immediately, so do not click it during a walkthrough unless you intend to change the record.

Open **My Work Queue**. It lists active, permission-scoped cases with case number, institution, required action, priority, and SLA. A central administrator sees a broad operational queue; an officer sees only assigned records. Use this screen to move the narrative from “analytics” to “what an officer must do next.”

## 9. Institution Intelligence

Open **Institutions**, search for the Demo Center institution, and open it. The **Institution intelligence overview** combines identity with:

- total, active, disposed, overdue, overlap-review, coordination, and bureau KPIs;
- **Cross-bureau activity** with an explicit evidence boundary;
- factual insight strip;
- complaint volume, category distribution, and bureau ownership charts;
- recent institutional activity;
- overlap and coordination summaries;
- the complete authorised complaint history.

Say: “This page is evidence aggregation, not an AI-generated allegation. It gives authorised staff one institutional timeline while preserving bureau ownership.”

## 10. Notifications, reports, and accountability

### Alerts & Notifications

The screen title is **Notifications** and covers assignments, transfers, SLA warnings, overlap-review signals, and coordination creation. Clicking a notification marks it read and navigates to its destination. **Mark all read** changes notification state, so avoid it if unread badges are part of the demo.

### Reports & Analytics

The reports page currently offers twelve database-backed views:

1. Institution-wise complaint history
2. Bureau-wise workload
3. Region-wise complaint statistics
4. State-wise complaint distribution
5. Pending case ageing
6. Disposal rate
7. SLA compliance
8. Overlapping and duplicate cases
9. Officer workload
10. Monthly performance
11. Quarterly performance
12. Transfer and escalation statistics

Filter by report, bureau, region, and optional date range. Empty dates are not sent to FastAPI, avoiding invalid empty-date HTTP 422 responses. The page shows filtered-record, disposed, overdue, and SLA-compliance KPIs; charts and a reconciled table; and CSV/PDF exports.

### Audit Trail

The **Audit trail** is append-only and shows time, actor, event, entity, and request reference. Demonstration actions are visible as normal business events, including `demo.started`, `demo.advanced`, `overlap.reviewed`, `coordination.created_from_overlap`, `complaint.assign`, and `complaint.escalate`.

Audit records prove who did what; complaint action history explains what happened to the case. Both are useful and intentionally distinct.

## 11. The seven recent UI/UX enhancements

### 1. Interactive Demo Center

- **Problem solved:** a judge can see a complete, repeatable workflow without hunting for the right existing records.
- **Implemented behavior:** three deterministic scenarios create and mutate genuine synthetic records through backend services. The page shows steps, outputs, and live-record links; restart archives a session.
- **Access:** sidebar → **Interactive Demo**; advance requires system/central admin or bureau head.
- **What is different:** conventional demo fixtures paint a desired result; this center persists complaints, runs the engine/workflows, and leaves notifications/audit evidence.
- **Powered by:** demo session service, complaint/workflow services, overlap engine, SLA notifications, coordination and audit services.
- **Best demonstration:** run Scenario A end to end, then use Scenario B to prove restraint and Scenario C to prove accountability.
- **Judge cue:** ask them to notice that dashboard totals and audit history change after the scenario.

### 2. AI Case Comparison

- **Problem solved:** a single score is unsafe and hard to review.
- **Implemented behavior:** two complaint panels, semantic evidence, deterministic reasons, classification, severity, human-review state, and decision controls.
- **Access:** **Overlap Intelligence** → select a finding.
- **What is different:** the model recommendation is separated visually and technically from the officer’s decision.
- **Powered by:** stored overlap finding, MiniLM cosine similarity, hybrid scoring/rules, review endpoint and audit logging.
- **Best demonstration:** point from the paraphrased descriptions to the semantic score, then to same-institution/cross-bureau evidence, then record reasoned review notes.
- **Judge cue:** the page explicitly says similarity is advisory; it does not call the score a probability.

### 3. Visual Case Journey

- **Problem solved:** a status label alone cannot explain ownership movement or accountability.
- **Implemented behavior:** complaint events appear chronologically with actors, remarks, status transitions and bureau flow alongside the immutable action history.
- **Access:** open any **Complaint record** and move to **Case Journey**.
- **What is different:** operational history is understandable visually while retaining auditable event data.
- **Powered by:** complaint actions, transfer/assignment/status events, coordination and overlap events.
- **Best demonstration:** use Scenario C so assignment, SLA attention and escalation form a clean story.
- **Judge cue:** identify the responsible actor and the exact transition instead of only the final status.

### 4. One-Click Coordination Wizard

- **Problem solved:** discovering overlap without assigning coordinated work still leaves bureaus disconnected.
- **Implemented behavior:** Review cases → Assign responsibility → Confirm → Created, with lead owner, officers, next action, due date and remarks.
- **Access:** an overlap finding → **Coordinate Cases**.
- **What is different:** an intelligence finding becomes structured inter-bureau execution rather than an email suggestion.
- **Powered by:** confirmed relationship, coordination/action services, complaint links, notifications and audit events.
- **Best demonstration:** inspect the confirmation summary before creating, then show the saved row in Coordination Center.
- **Judge cue:** ownership, participating bureaus and deadline are explicit. “Open Coordination Workspace” currently returns to the Center list, not a separate chat/detail workspace.

### 5. Institution Intelligence

- **Problem solved:** bureau-specific lists fragment the history of one institution.
- **Implemented behavior:** authorised complaint, workload, overdue, overlap, coordination and trend evidence is aggregated around a canonical institution ID.
- **Access:** **Institutions** → choose an institution.
- **What is different:** it is a factual cross-bureau evidence view with a visible evidence boundary, not an opaque institution risk score.
- **Powered by:** institution-linked SQL aggregates, complaint history, overlaps, coordination records and analytics.
- **Best demonstration:** open the institution created by Scenario A and identify both bureaus and both complaints.
- **Judge cue:** shared institution activity is never presented as duplication without semantic and human-review evidence.

### 6. Dashboard Action Center

- **Problem solved:** operational users need priorities, not just totals and charts.
- **Implemented behavior:** the dashboard surfaces authorised work requiring attention and links directly to assigned/urgent cases and queues.
- **Access:** **Overview**, near the top of **Complaint command overview**.
- **What is different:** it turns analytics into a next-action launch point.
- **Powered by:** role-scoped dashboard and complaint queries, priority/SLA state and assignments.
- **Best demonstration:** select one clean “My assigned work” item and show its required action and deadline.
- **Judge cue:** the results differ by role and current database state.

### 7. Guided Product Tour

- **Problem solved:** the application has multiple connected modules that are difficult to discover in a first session.
- **Implemented behavior:** eight route-spanning spotlight steps with Next/Back/Skip/Finish; progress survives navigation and completion is remembered locally.
- **Access:** header → **Take a Tour**.
- **What is different:** it teaches the actual workflow order across pages rather than showing a static help image.
- **Powered by:** frontend route navigation, DOM spotlight targets, session storage and local completion state.
- **Best demonstration:** show the first two steps, then skip to preserve time.
- **Judge cue:** it is onboarding assistance only; permissions and data still come from backend services.

## 12. System administration

Sign out from the header, then sign in as `admin@casesync.demo` to reveal the two system-only sidebar entries. Keep this section read-only during judging.

### User & bureau management

The user table shows **Official**, **Role**, **Bureau**, **Status**, and **Action**. Role and bureau dropdowns persist immediately; **Activate/Deactivate** changes account state. The top controls are **Bureau**, **Category**, and **User**:

- Create user asks for Name, Email, Temporary password, Role, and Bureau membership. Passwords must be at least 10 characters.
- Create bureau asks for Bureau code and Name.
- Create category asks for Category name.
- The lower cards show Active bureaus and Complaint categories, each with a real **Deactivate** action.

Say: “Organisational boundaries and permissions are data, not source-code constants.” Do not click a dropdown or Deactivate while merely pointing; these controls write immediately.

### Settings

The page heading is **Settings** and contains:

- **Overlap engine:** active embedding backend and model, plus Shared activity, Related, and Likely duplicate threshold fields and **Save thresholds**.
- **Integration adapters:** validated CSV intake and the honest state **Official API — Disabled — awaiting authorized credentials**.
- **SLA policies:** Priority, Calendar days, Category override, Bureau override, **Save SLA policy**, and existing policy cards.
- **Run SLA scan:** executes the idempotent notification scan and reports how many notifications were generated.

Important implementation boundary: the current threshold form persists and audits the setting, but the inspected overlap engine still evaluates with its code-defined constants (`0.42`, `0.52`, `0.82`, and related severity boundaries). Do not demonstrate **Save thresholds** as changing inference until that connection is implemented. SLA policies and the SLA scan are operational. Running the scan is safe only when you are prepared to explain deduplication and any new alerts.

## 13. Security and governance

- Authentication uses JWTs in `HttpOnly`, `SameSite` cookies.
- A readable CSRF cookie must match the request header for state-changing requests.
- Passwords use bcrypt with work factor 12.
- Repeated failed logins cause a temporary lockout.
- Authorization is enforced in FastAPI with role and bureau scope.
- Auditors are read-only; central/system roles have broad scope; bureau heads are bureau-scoped; officers are assignment-scoped.
- Uploaded evidence is private, allowlisted by type and size, randomly named, hashed, and permission-checked on download.
- Material actions create append-only audit events.
- SLA notifications use deduplication keys so repeated scans do not spam users.
- All demonstration data is visibly synthetic.

For production, secrets must come from the deployment secret store, TLS terminates at the approved gateway, logs and backups follow policy, and identity/federation requirements are integrated through authorised interfaces.

## 14. Technical architecture

```text
Brave / Next.js App Router
          |
          | JSON over versioned /api/v1 endpoints
          v
FastAPI + Pydantic + RBAC/CSRF dependencies
          |
          +--> SQLAlchemy --> SQLite (native demo)
          |                  PostgreSQL/pgvector preserved for deployment
          |
          +--> overlap service --> MiniLM CPU embeddings
          |                     --> deterministic evidence/rules
          |
          +--> workflow, notification, report, audit services
          |
          +--> private attachment storage
```

The local build requires no Docker, PostgreSQL, pgvector, official API, or internet connection after dependencies and the model cache are available. SQLite keeps the entire demonstration functional. The repository still preserves the PostgreSQL/Docker path.

FastAPI starts an hourly in-process SLA scheduler that calls the same idempotent service exposed by the system-admin **Run SLA scan** button. A horizontally scaled deployment should run that job from one designated scheduler/job runner rather than from every API replica.

CSV import enables authorised bulk intake now. The integration layer is configurable so future AICTE sources can be mapped, validated, and audited without rebuilding the UI or domain workflows. Official integration is intentionally disabled until credentials, schemas, and governance approval exist.

## 15. AI engine, evaluation, and limitations

The preferred backend is `sentence-transformers/all-MiniLM-L6-v2`. Complaint text is encoded into normalized 384-dimensional vectors, and cosine similarity supplies the semantic component. Candidate generation is bounded: active complaints for the same canonical institution are prioritised, with a limited recent set, rather than comparing every historical pair.

A deterministic 384-dimensional feature-hash fallback keeps development functional when the model cannot load. Health/configuration output identifies the active backend; never claim MiniLM inference if it reports fallback or not loaded. The first real analysis loads the model lazily.

Content fingerprints prevent repeated findings when neither complaint changed. Editing relevant text changes the fingerprint and triggers a fresh evaluation.

### Current synthetic evaluation artifact

`docs/evaluation-results.json` records a deterministic labelled synthetic evaluation of 120 pairs. At semantic threshold 0.55:

- precision: 1.0000
- recall: 0.8667
- F1: 0.9286
- true positives: 52
- false positives: 0
- true negatives: 60
- false negatives: 8

At 0.50, recall reached 1.00 but precision fell to about 0.8824, with eight false positives. This demonstrates the operational trade-off: lowering a threshold catches more related pairs but increases reviewer workload.

These results validate repeatability on the synthetic benchmark only. They do not establish official-data accuracy, fairness, language coverage, or production readiness. A production pilot needs authorised representative labels, bureau-specific error analysis, calibration, privacy review, monitoring, and documented human override.

## 16. Three-minute SIH demonstration

Use the dedicated timed script in `docs/SIH_3_MINUTE_DEMO.md`. The route is:

1. Dashboard and problem — 25 seconds.
2. Interactive Demo Scenario A through AI analysis — 75 seconds.
3. Explain evidence and human-in-the-loop — 35 seconds.
4. Record the human decision, create coordination, and open Coordination Center — 25 seconds.
5. Notifications/Audit/closing — 20 seconds.

If model warm-up is slow, narrate while the analysis button is processing. Do not fill the silence by clicking again.

| Time | Screen | Exact click | What to say | Expected result / transition |
|---|---|---|---|---|
| 0:00–0:25 | Complaint command overview | **Overview**, then point to banner/KPIs/Action Center | “Different bureaus can unknowingly investigate paraphrased complaints about one institution.” | Live database-backed operating picture; move to **Interactive Demo**. |
| 0:25–0:55 | Scenario A | **Start isolated demo**, register the institution and receive both complaints | “Two real synthetic complaint records are now owned by different bureaus.” | Two case identifiers, full text and bureau evidence appear. |
| 0:55–1:35 | Scenario A analysis | Run **AI overlap analysis** once | “MiniLM compares meaning; deterministic institution and workflow facts form an explainable hybrid ranking.” | Actual semantic evidence, classification, severity and component breakdown appear. |
| 1:35–2:05 | Scenario A decision | Record the human decision, then create coordination | “The officer—not the model—confirms the relationship; a separate action creates governed coordination.” | Review proof and a coordination record are saved separately. |
| 2:05–2:30 | Coordination center | Open generated coordination / sidebar **Coordination Center** | “Discovery becomes owned work with bureaus, actions and a target date.” | Saved coordination row is visible. |
| 2:30–2:48 | Notifications / Audit trail | **Alerts & Notifications**, then **Audit Trail** | “Signals reach participants and material actions remain inspectable.” | Related alert and append-only events are visible. |
| 2:48–3:00 | Final screen | Leave a clean coordination/audit screen | “Complete offline today; authorised CSV/adapters tomorrow—explainable AI tied to accountable workflow.” | Stop clicking and take questions. |

## 17. Fifteen-to-twenty-minute judge walkthrough

### 0:00–2:00 — Problem and trust boundary

Show the synthetic banner, dashboard, and live KPIs. Explain the coordination problem and the “AI advises, officer decides” principle.

### 2:00–7:00 — Scenario A end to end

Run all four steps. Explain paraphrase matching, semantic versus hybrid score, evidence reasons, human confirmation, and automatic coordination creation.

### 7:00–9:00 — False-positive control

Run Scenario B or show a completed record. Emphasise that same institution is insufficient and unrelated allegations can be suppressed.

### 9:00–11:00 — SLA operations

Run Scenario C or open its generated complaint. Show Case Journey, alert, escalation, and audit trail.

### 11:00–13:00 — Institution and complaint operations

Open Institution Intelligence, then a complaint. Show canonical identity, cross-bureau timeline, action history, attachments, and lifecycle controls.

### 13:00–15:00 — Review and coordination

Open Overlap Intelligence, AI Case Comparison, and the coordination wizard. If you do not want to mutate data, stop before the final confirmation screen.

### 15:00–17:00 — Reports and accountability

Select two reports and apply one bureau or date filter. Show CSV/PDF export controls and the append-only Audit Trail.

### 17:00–20:00 — Architecture, security, evaluation, questions

Use the architecture section above. State the 120-pair synthetic evaluation honestly, explain SQLite versus PostgreSQL deployment options, and invite role/access questions.

## 18. Judge questions and concise answers

1. **Is the data real?**
   No. Every displayed record is synthetic and visibly labelled. The workflows, inference, persistence, reports, and audit trail are real.

2. **Is the AI output hardcoded for the demo?**
   No. Scenario input records are deterministic, but MiniLM embedding, cosine similarity, policy scoring, persistence, and workflow calls run through production application services.

3. **Does an 83% score mean an 83% chance of duplication?**
   No. It is a weighted prioritisation score, not a calibrated probability.

4. **Why combine rules with embeddings?**
   Embeddings capture paraphrased meaning; rules add reliable administrative context such as canonical institution, bureau ownership, category, and active state.

5. **Who makes the final decision?**
   An authorised human reviewer. The model creates a reviewable finding; the reviewer confirms, rejects, or marks unrelated.

6. **How do you limit false positives?**
   Bounded candidates, explicit thresholds, deterministic evidence, a separate unrelated state, a human queue, and evaluation of precision/recall trade-offs.

7. **What happens after confirmation?**
   CaseSync links the cases, creates or reuses a coordination record, assigns responsibility/actions/deadlines, notifies participants, and writes audit events.

8. **Can two different issues at one institution be separated?**
   Yes. Scenario B demonstrates fee and laboratory allegations at one institution producing no reviewable relationship in the verified run.

9. **What if MiniLM is unavailable?**
   The engine exposes a deterministic feature-hash fallback for continuity. Health output identifies the backend so operators do not misrepresent it.

10. **Why MiniLM?**
    It offers useful semantic embeddings with modest CPU and memory needs, suitable for an offline Windows demonstration and an economical service tier.

11. **Does it require internet or an AICTE API?**
    No after dependencies/model cache are present. Synthetic seed data and SQLite make the complete product demonstrable offline.

12. **How will official data be incorporated?**
    Through validated CSV import and configurable adapters once schemas, credentials, and governance are authorised; core workflows do not need rebuilding.

13. **Why SQLite?**
    It makes native local evaluation reliable. SQLAlchemy keeps the preserved PostgreSQL/pgvector deployment path available for scale.

14. **How is access controlled?**
    JWT authentication, CSRF protection, role checks, bureau scoping, assignment scoping, and authorised attachment download are enforced in the backend.

15. **Can an auditor change a case?**
    No. Auditor access is read-only and mutations are denied server-side.

16. **Can repeated SLA jobs spam users?**
    Notifications use deduplication keys; a repeat scan can correctly create no new notification.

17. **Can an unchanged complaint create duplicate findings?**
    Content fingerprints suppress repeat evaluation outcomes; relevant edits create a new fingerprint and re-evaluation.

18. **How do you prove actions occurred?**
    Complaint history records the case journey, and append-only audit events record actor, event, entity, time, and request reference.

19. **What did the evaluation prove?**
    Repeatability on 120 labelled synthetic pairs and an explicit threshold trade-off. It does not prove official-data performance.

20. **How will you evaluate production readiness?**
    Use authorised representative labels, held-out testing, bureau and language slices, precision/recall targets, reviewer workload, override analysis, drift monitoring, and security/privacy review.

21. **What prevents conflicting bureau actions?**
    Shared institution history, cross-bureau findings, named coordination ownership, action items, deadlines, notifications, and auditable decisions.

22. **Are uploaded files public?**
    No. Files are privately stored with random names and hashes, and downloads pass the same case-authorization checks.

23. **Can thresholds be changed?**
    The system-admin UI persists and audits threshold configuration, but this prototype’s inspected scoring path still uses code-defined constants. Connecting versioned settings to inference is a known production-hardening item; do not claim a saved UI value currently changes a result.

24. **What is the largest current limitation?**
    The evaluation and dataset are synthetic. Production claims require authorised data and a monitored pilot with human adjudication.

25. **What is the innovation beyond a dashboard?**
    CaseSync joins semantic discovery to real institutional identity, lifecycle governance, human review, cross-bureau execution, notifications, reporting, and auditability.

## 19. Common presentation pitfalls

- Do not call semantic similarity a probability.
- Do not say the AI “decides” or “takes action automatically.”
- Do not quote dashboard counts as fixed product claims.
- Do not click **Mark all read** or complete a coordination action unless you intend to mutate state.
- Do not navigate away halfway through a Demo Center scenario; finish it first, then inspect live records.
- Do not expect Scenario B to display a raw score when the policy stores no finding.
- Do not present the Coordination Center as a chat room; it is a structured work and ownership register.
- Do not claim government integration, production accuracy, multilingual coverage, or official endorsement.
- Do not change model thresholds just before or during evaluation.

## 20. Troubleshooting during a demo

### Frontend does not load

Run the launcher again. It is duplicate-safe and will report whether port 3000 already belongs to a healthy CaseSync process. Check the newest `frontend-*.out.log` and `frontend-*.err.log` under `.runlogs/`.

### API is unavailable

Open `/api/v1/health`, then inspect the newest `backend-*.out.log` and `backend-*.err.log` under `.runlogs/`. Confirm the Python path belongs to the repository’s Python 3.12 virtual environment, not Python 3.13.

### Login fails

Confirm that you are using the seeded address exactly (`central@casesync.demo`) and the local demo password. Check Caps Lock. Five repeated failures can trigger temporary lockout, so stop guessing and use another authorised seeded account or wait for the lockout window rather than altering the database.

### The browser session expires

Return to `/`, sign in again, and reopen the record from global search or Audit Trail. Work already submitted is persisted. Do not refresh while a request is visibly in progress.

### First inference is slow

The model loads lazily from the offline cache on first use. Wait for the current request; do not repeatedly click the analysis button. Subsequent inference is faster.

### Health reports `not_loaded`

This is normal immediately after a restart. Run one real overlap analysis. Then recheck health and confirm the backend remains alive.

### Health reports fallback

The app remains functional, but state clearly that fallback embeddings are active. Check model-cache and offline environment configuration before claiming MiniLM.

### Report page returns 422

Reload the current frontend build. The fixed request omits empty `from`/`to` parameters. A stale browser bundle or old frontend process can retain the earlier behavior.

### A demo creates no new notification

Check existing notifications and the audit trail. Deduplication may mean the correct number of new notifications is zero on a repeated scan.

### A demo record appears to vanish

Use global search, Complaints, or Audit Trail. Restarting/navigating can clear local Demo Center presentation state but does not delete persisted records.

### The overlap score differs from rehearsal

Read and explain the value shown. Model/runtime versions and actual input state can alter inference. The product promise is an explainable review workflow, not a fixed percentage. Verify the health/settings backend before comparing runs.

### An action says permission denied

Read the identity and role in the header. Sign out and use the central or system administrator only if the walkthrough requires that authority; otherwise demonstrate the restriction as intended RBAC. Never weaken permissions for a presentation.

### Notifications seem delayed

Reload **Alerts & Notifications** once after the triggering request completes. For SLA, run the authorised scan only when intended. If no new row appears, explain idempotent deduplication and verify the action in the complaint timeline and Audit Trail.

### Analytics is empty

Clear region/date/bureau filters, select a broad report, and confirm the role can see relevant records. An empty table is a valid filtered result; it is not evidence that the database was reset.

### Internet is unavailable

The native demonstration should continue because the frontend, backend, SQLite database, and model cache are local. Do not run dependency installation. Use the health endpoint to distinguish local service failure from network loss.

### The page is accidentally refreshed

Authentication and persisted records remain. Return to **Interactive Demo** and choose **Continue current session**; the studio restores the current step from SQLite. Start a fresh isolated session only when that is clearer for the audience.

### Port 3000 or 8000 is occupied

The launcher identifies/reuses healthy CaseSync services and refuses to kill unrelated processes. Inspect the reported PID before taking any manual action.

### Backup plan without pretending a recording is live

Before presenting, keep three already-completed synthetic records bookmarked or written down: one confirmed Scenario A finding/coordination, one Scenario B pair, and one escalated Scenario C complaint. If model warm-up or navigation is temporarily slow, open those persisted records and explicitly say, “This is the earlier result of the same live workflow.” Do not describe a screenshot or prerecorded output as current inference. The live database, case journey and audit trail still prove persistence and explainability.

## 21. Screenshot plan for submissions

Use fresh screenshots from the current build so counts and IDs agree with the narrative. Crop out unrelated browser tabs.

Recommended captures:

1. Dashboard with synthetic-data banner and KPIs.
2. Interactive Demo Center with all three scenario cards.
3. Scenario A evidence after semantic analysis.
4. AI Case Comparison with both complaint panels and reasons.
5. Coordination Center with the generated cross-bureau record.
6. Scenario C complaint showing status, SLA, and Case Journey.
7. Institution Intelligence cross-bureau overview.
8. Reports & Analytics with one filter applied.
9. Notifications showing overlap/SLA/coordination signals.
10. Audit Trail showing the matching business events.

Use captions such as “Synthetic demonstration data; computed result from local MiniLM inference” and never crop away the synthetic-data banner when the screenshot could otherwise be mistaken for an official system.

## 22. Final pre-demo checklist

- [ ] Run `start-dev.ps1 -OpenBrave`; do not reinstall or reseed.
- [ ] Backend health is `ok`, database is `connected`, and synthetic demo mode is true.
- [ ] Frontend opens at `http://localhost:3000` and central-admin login succeeds.
- [ ] Open Reports once; no 422 appears and the default report contains data.
- [ ] Run or confirm one MiniLM-backed practice analysis; health/settings identifies `sentence-transformers`, not fallback.
- [ ] Write down one clean Scenario A finding/coordination, Scenario B pair, and Scenario C complaint as backups.
- [ ] Decide whether to start a fresh Demo Center session; never reset the whole database.
- [ ] Close/hide unrelated tabs, desktop notifications, terminals, credentials, and personal content.
- [ ] Set browser zoom and projector resolution; leave the synthetic banner visible.
- [ ] Keep the three-minute cue card on a second device or printed.
- [ ] Confirm the machine is powered and the local model cache is present; internet is optional.
- [ ] Rehearse the distinction between semantic score, hybrid score, classification, and human confirmation.
- [ ] Do not change thresholds, SLA policies, accounts, bureaus, categories, or passwords during the judged run.
- [ ] Know the recovery route: global search → persisted record → Case Journey/Audit Trail.

## 23. Closing statement

“CaseSync does not replace bureau expertise. It gives that expertise a shared, explainable operating layer: one institutional view, earlier discovery of overlap, accountable coordination, deadline awareness, and a complete audit trail. This prototype proves the full workflow locally on synthetic data and is architected to accept authorised data later without making government integration a demo prerequisite.”
