# GreekOS V1 — Build Plan

Parallel domain agents, each owning a migration number range (never edit applied migrations; apply own files individually, record in `schema_migrations`).

| Wave | Agent | Scope | Migrations | Tests |
|---|---|---|---|---|
| 1 | Events | event_types (seeded, ci-unique), `finable`, event_groups + `event_group_id`, supervisor (chair-only), organizers + soft-min flag, audience `all\|officers\|custom` enforced, attendance % derived read, DDD conform | 0100–0104 | tests/events/ |
| 1 | Tasks | `event_id` on tasks, `committed` status, commit/uncommit RPCs + append-only commitment log (late flag at 24h), attribution (tasks part) | 0110–0114 | tests/tasks/ |
| 1 | Treasury | `due_at`/`issued_by`/line items/`manual` kind, void w/ required reason (treasurer), balance-level payment submissions (+`check` method, image evidence), verify w/ oldest-first allocation + `payment_allocations` + treasurer override, `finance_board` role + permission seeds, flat-$25 fines ≥24h gate + missed-list, kill auto-fine cron | 0120–0126 | tests/treasury/test_v1_* |
| 1 | Announcements | `announcements:send:sms` (president+secretary), recipient-count preview + confirm step, `sms_sends` log, Twilio client (dry-run default) | 0130–0132 | tests/announcements/ |
| 2 | Calendar | `api/calendar/` read-only aggregation (events+groups+understaffed, invoice due/overdue per decision #3, task due dates), attribution extension (events organized/supervised), usage instrumentation | 0140–0142 | tests/calendar/ |
| 3 | Frontend | Treasury palette as global theme; Calendar view; Events/Tasks/Treasury/Announcements V1 flows; nav + api-client + types | — | vitest + build |
| 4 | Verify (orchestrator) | Fresh-DB migrate, full pytest, frontend build/tests, doc updates | — | all |

DB: `postgresql://fraternityos:localdev@localhost:5434/fraternityos` (docker compose, migrated through 0090 at start).

Status vocabulary mapping (API ↔ DB): invoice `open` ↔ `unpaid|partially_paid`, `void` ↔ `cancelled`; source `dues|fine|manual` ↔ `kind`.
