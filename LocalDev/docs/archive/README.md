# Archived implementation plans

Completed `imp-*.md` plans, moved here once their work shipped. Kept for history;
they are no longer live work. See the product dashboard in the root
[`README.md`](../../../README.md) for current status.

| Plan | What shipped | Landed |
|---|---|---|
| `imp-ev-ph1.md` | Events V1 Phase 1 — event times, co-supervisors, jobs core, T-36h lock | migrations 0141/0142 |
| `imp-ev-ph2.md` | Events V1 Phase 2 — notify gate + SMS blast | migration 0143 |
| `imp-ev-ph3.md` | Events V1 Phase 3 — initiatives | migration 0144 |
| `imp-ev-ph4.md` | Events V1 Phase 4 — security assignments + shift swaps | migration 0145 |
| `imp-hygiene.md` | Dead-code deletion + doc truth-up | commit `b6d4ffd` |
| `imp-standing-fines.md` | Standing reads real unpaid fines (cents) | commit `effde78` |
| `imp-e2e-and-tooling-repairs.md` | E2e suite repair, dev-script paths, officer password login | commits `1ec54fa`/`003a359`/`4dbd0bf` |
| `imp-tenant-guards.md` | Attendance tenant guards + prod fail-fast | migration 0146 |
| `imp-one-gate.md` | All authority folded into the permission catalog (incl. `/scores` off `require_officer`) | migration 0147, commit `f3856e3` |
| `MIGRATION_PLAN.md` | DDD conform pass — `api/routes/`, `api/services/`, `api/models/` folded into domain packages and deleted | — |

The Events phases are also summarized in [`../events-dev-status.md`](../events-dev-status.md).
