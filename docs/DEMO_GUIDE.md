# Demonstration Guide

Use `central@casesync.demo` / `CaseSync@2026` after running the synthetic seed.

1. **Login:** point out the explicit synthetic-data notice and secure session behavior.
2. **Overview:** show the ten live KPIs, monthly trend, categories, bureau workload and urgent queue. Values are SQL aggregates, not static cards.
3. **Institution intelligence:** open Institutions, search a `DEMO-AICTE-` ID and drill into the cross-bureau complaint history.
4. **Register a complaint:** choose that canonical institution, Unauthorized fee collection, a bureau and a detailed description. Submit and note the generated case ID, action-history event and SLA.
5. **Create overlap:** register a paraphrased fee complaint at the same institution in another bureau. The real matching service produces the finding and notifications.
6. **Explainability:** open Overlap Intelligence and select the new finding. Compare descriptions, identity evidence, bureau ownership, semantic score, hybrid score and risk. Stress that it is advisory.
7. **Human review:** confirm with reasoned notes. CaseSync creates the durable link and a coordination record; reject/unrelated decisions are also retained and suppressed until a meaningful text change.
8. **Coordination:** open Coordination Center to show owner, participating bureaus, action items and deadline.
9. **Case movement:** open a pending complaint, Start it, Transfer it to a different bureau, then use an authorized receiver to Accept Transfer. The timeline retains both ownership points.
10. **SLA:** use Settings → Run SLA scan. Open Notifications and the Work Queue to show deadline/overdue alerts. Re-running the same daily window creates no duplicates.
11. **Reports:** select bureau, region and date range, inspect reconciled metrics, then download CSV and PDF. The filter contract is shared by screen and exports.
12. **Permission proof:** log in as `auditor@casesync.demo`; mutation controls disappear. A direct mutation API request still returns 403. Log in as `officer1.rb@casesync.demo` to demonstrate bureau scoping and assigned-case mutation.

Nothing in this flow depends on an AICTE network, paid AI API, or hardcoded finding. Every showcased outcome is calculated and persisted against clearly synthetic records.

