# GreekOS V1 — Gap Analysis (2026-06-12)

Baseline: `LocalDev` @ main (162 backend tests passing). Treasury domain-package pattern is canonical (`docs/services/README.md`).

## What already exists (reuse, don't rebuild)

| Area | Existing | Where |
|---|---|---|
| Treasury core | Append-only `big_ledger` + `audit_logs`, integer-cents `Money`, plpgsql RPCs w/ tenant guards + idempotency, invoices (`unpaid_invoices`), payment submissions → verify/reject w/ `payment:review`, immutable receipts, balance engine (computed, cached), adjustments w/ two-officer signoff, refunds, expenses | `api/treasury/`, migrations 0005–0081 |
| RBAC | roles/permissions/member_roles catalog, `require_permission`, legacy `members.role` compat, 15 roles incl. president/secretary/treasurer/6 chairs | `api/rbac/`, 0082–0083 |
| Events | table w/ `required`, `fine_amount`, `event_type` (free text), `visibility` (stored, unenforced), `linked_*` columns | 0001, 0090, `api/routes/events.py` |
| Attendance | check-in links (anti-cheat short codes), sessions, excuses, `list_unexcused_absences` signal | `api/attendance/` |
| Tasks | table (open/in_progress/done/cancelled), `due_at`, single `assigned_member_id`, RPCs | `api/tasks/`, 0085 |
| Announcements | draft→send feed, audience enum, transactional outbox (`message_outbox`), dry-run delivery | `api/announcements/`, 0086, 0070 |
| Frontend | single-page shell + nav w/ permission gating, typed api-client, useApi/usePermissions hooks, UI kit, treasury palette in `components/modules/treasury/treasury-dashboard.tsx` | `fratos/` |

## Gaps to close for V1

### Events
- No `event_types` entity (seeded defaults, unique case-insensitive) — `event_type` is free text.
- No `finable` boolean (only implicit `fine_amount`).
- No event **group** (`group_id` linking setup→event→cleanup). (`linked_task_group_id` is tasks, not event groups.)
- No supervisor (exactly one, chair-only). No organizers (volunteer/assigned) or "needs N more" soft-minimum flag.
- Audience: spec wants `all | officers | custom list`; visibility stored but **not enforced** in queries, no custom member list.
- No attendance % derived view.

### Tasks
- No volunteering: no commit/uncommit endpoints, single assignee only.
- No uncommit log (24h cutoff flag) — spec: always allowed, logged & visible, flagged late inside 24h of event start.
- No `committed` status; no direct `event_id` attachment (only task_groups).
- No attribution ledger.

### Treasury
- Invoices: no `due_at`, no `issued_by` column, no line items, no `manual` kind; status vocabulary maps (`unpaid|partially_paid→open`, `cancelled→void`).
- Void/waive: cancel exists but **no required reason** and gated to all officers, not Treasurer.
- Payments: submissions require an `invoice_id` — spec wants **balance-level** submissions; method enum lacks `check`; no image evidence storage.
- No allocation: verify is per-invoice; spec wants oldest-first auto-allocation across open invoices + treasurer override, all logged.
- No `finance_board` role; verification currently open to every officer.
- Fines: auto-issued by cron every 15 min (vercel.json) — spec says **never automatic**; no flat $25 rule; no ≥24h gate; no "who missed" surface.

### Calendar
- Does not exist. Needs read-only aggregation: events (+groups, understaffed flags, audience-filtered), invoice due dates with overdue flagged (decision #3), task due dates.

### Announcements
- No SMS path (President+Secretary only), no recipient-count confirmation step, no send log, no Twilio client (dry-run default retained).

### Instrumentation
- New mutations must write `audit_logs` via RPCs (covered by pattern); add lightweight usage tracking.

### Frontend
- Re-theme app to treasury palette (`#102A43` bg, `#1A3B5C` surface, purple `#6c5ce7`/`#D7C9FF`/`#C79BFF`, green `#7AE582`, white text).
- New/updated views: Calendar, Events (type/flags/group/supervisor/organizers/audience), Tasks (volunteer + uncommit log), Treasury member dashboard (balance, pending, overdue) + payment submission + verification queue + void w/ reason, Announcements SMS confirm flow.
