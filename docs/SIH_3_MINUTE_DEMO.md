# AICTE CaseSync — SIH Three-Minute Demo Script

This is a rehearsed 180-second path through the live application. Use `central@casesync.demo` / `CaseSync@2026`. All data is synthetic; leave the banner visible.

## Before the timer

- Start CaseSync with `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-dev.ps1 -OpenBrave`.
- Confirm frontend `http://localhost:3000` and health `http://localhost:8000/api/v1/health`.
- Sign in as the Central AICTE Administrator.
- Open **Interactive Demo**, select **AI detects duplicate investigations**, click **Start isolated demo**, and stop before running **Register canonical institution**.
- If possible, warm the model with an earlier practice run. A new run still creates separate synthetic records.
- Keep **Overlap Intelligence** or **Coordination Center** ready in a second tab only if your presentation setup supports it reliably.

## At-a-glance cue card

| Time | Screen | Exact click | What to say | Expected result |
|---|---|---|---|---|
| 0:00–0:25 | Overview | Point to banner/KPIs, click **Interactive Demo** | “One operational view prevents disconnected bureau investigations.” | Demo Center opens. |
| 0:25–0:55 | Scenario A | Register institution, then receive both complaints | “Two paraphrased synthetic complaints now exist in different bureaus.” | Two full records and bureau assignments appear. |
| 0:55–1:30 | Scenario A | Run **AI overlap analysis** | “MiniLM compares meaning; deterministic facts create explainable ranking.” | Real semantic evidence, reasons, components and classification appear. |
| 1:30–2:08 | Scenario A | **Record explicit human decision**, then **Create accountable coordination** | “The officer decides; only then does CaseSync create accountable coordination.” | Separate review proof and coordination record. |
| 2:05–2:30 | Coordination Center | Open generated coordination or sidebar item | “Discovery becomes owned actions and deadlines.” | Saved cross-bureau row is visible. |
| 2:30–2:48 | Notifications/Audit | Open **Alerts & Notifications**, then **Audit Trail** | “Signals and append-only evidence close the accountability loop.” | Related alert/events are visible. |
| 2:48–3:00 | Current clean screen | Stop clicking | “Offline-complete today; authorised adapters later.” | Take questions. |

## 0:00–0:25 — Problem and promise

**Screen:** Dashboard.

**Say:**

“AICTE bureaus can receive differently worded complaints about the same institution. Without a shared view, teams may duplicate investigation or issue conflicting actions. CaseSync is a role-aware complaint operations platform that detects potential overlap, explains the evidence, keeps an officer in control, and turns a confirmed relationship into accountable coordination.”

**Do:**

- Point to the synthetic-data banner.
- Point to live totals, overdue/SLA cards, overlap review, and bureau workload.
- Click **Interactive Demo**.

## 0:25–0:55 — Create two cross-bureau cases

**Screen:** **AI detects duplicate investigations**.

**Say:**

“This scenario calls the same backend services as normal complaint entry. The inputs are deterministic for a reliable demonstration; the records and outputs are real database results.”

**Do:**

1. Run **Register canonical institution**, then **Receive PGRC complaint**.
2. Say: “The first bureau has registered a fee complaint against a synthetic institution.”
3. Run **Receive Regulation Bureau complaint**.
4. Say: “A second bureau now receives a paraphrased complaint against the same canonical institution. There is no copied phrase or hardcoded match.”

## 0:55–1:35 — Run and explain the AI

**Do:** Run **AI overlap analysis** once and wait. Do not double-click during model warm-up.

**Say while it processes:**

“CaseSync generates normalized 384-dimensional MiniLM embeddings and compares meaning with cosine similarity. It then combines that semantic evidence with administrative facts: same canonical institution, category, cross-bureau ownership, and active lifecycle.”

When the evidence appears, point to the real semantic score, classification, severity, and reasons.

**Say:**

“The hybrid score is a prioritisation score, not a probability of duplication. The engine has surfaced a reviewable relationship; it has not made a legal or administrative decision.”

If the observed values differ from rehearsal, read the screen. Never quote a memorised percentage.

## 1:35–2:05 — Human review and coordinated action

**Say:**

“An authorised officer must now accept or reject the evidence. This human decision is separate from the engine classification.”

**Do:** Keep **Confirm relationship** selected, retain or edit the review notes, then click **Record explicit human decision**. On the next step, inspect the owner, action and due date and click **Create accountable coordination**.

**Say:**

“The recorded human confirmation is separate from the model output. Only the next explicit action creates a real cross-bureau coordination record, links both cases, assigns responsibility and a target, sends notifications, and writes audit events. The AI stops at advice; workflow governance begins after review.”

Click the generated coordination live record if it is immediately available; otherwise open **Coordination Center** from the sidebar.

## 2:05–2:30 — Operational execution

**Screen:** Coordination Center.

**Say:**

“This is where discovery becomes work. The record shows the institution, lead owner, participating bureaus, open actions, status, and target date. Teams can assign accountable action items rather than coordinate through disconnected emails.”

Do not click an action completion checkmark; it changes the record immediately.

## 2:30–2:48 — Alert and audit evidence

**Do:** Open **Alerts & Notifications**, then **Audit Trail** if time permits.

**Say:**

“Participants receive overlap and coordination signals, while the append-only audit trail records actor, event, entity, and time. Complaint history and audit evidence make the full decision chain inspectable.”

## 2:48–3:00 — Close

**Say:**

“CaseSync is fully functional offline with SQLite and synthetic data, so no unofficial government connection is required. CSV import and configurable adapters provide the path to authorised data later. The result is explainable AI tied to real case workflow: detect earlier, coordinate clearly, and remain accountable.”

## If you have 20 extra seconds

Open **Same institution, different complaints** and say:

“We also test the opposite case: two complaints about one institution can be materially unrelated. CaseSync can suppress that pair, showing that institution identity alone never proves duplication.”

## Recovery lines

- **First inference is slow:** “The model loads locally from an offline cache on first use; no complaint text is being sent to an external AI service.”
- **No new notification appears:** “The job is idempotent, so repeat runs avoid duplicate alerts; the action is still visible in case history and audit.”
- **A number changed:** “The dashboard is database-backed, so the demonstration has just changed the operational totals.”
- **Asked whether the score is confidence:** “It is a transparent ranking score, not a calibrated probability. The reviewer decides.”
- **Asked about official data:** “No official data or credentials were provided. The product is deliberately complete on clearly synthetic data and ready for authorised adapters later.”

## Five phrases to avoid

- “The AI confirmed a duplicate.”
- “The score is the probability of guilt/duplication.”
- “This is connected to AICTE production.”
- “These dashboard numbers are official statistics.”
- “The synthetic benchmark proves production accuracy.”
