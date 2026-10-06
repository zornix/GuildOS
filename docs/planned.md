# GuildOS Member-First Pivot — Planned Changes

Status: decided (grill sessions 2026-07-23 → 2026-07-26). This is the resolved
plan of record; each phase becomes its own `docs/imp-*.md` before build.
Language: see `CONTEXT.md` (Initiative, Proposal, Contribution, Shoutout, Job).
Standing/contribution firewall: `docs/adr/0004-standing-contribution-firewall.md`.

## Goal

Pivot from officer console to member app. A regular member with zero officer
permissions can: open a home screen showing their standing, week, and balance;
get an SMS reminder for a required event; check in and see their attendance
count tick up; trace any charge to its cause; propose an initiative; and view
a chapter-visible profile of their contributions. No contribution stat ever
affects standing.

## Principles

1. **Member-first surfaces.** Officer views are the exception.
2. **Standing is negative-action only** — exactly unpaid fines + unexcused
   absences — and firewalled from contribution (ADR-0004). The
   `INCOMPLETE_REQUIRED_TASKS` reason code is removed.
3. **Only auto-derived stats.** If a stat requires a human to verify it, it
   doesn't exist. (Job approval by a supervisor/chair counts as structural,
   not manual — see ADR-0004.)
4. **The algorithm absorbs the animosity.** Reminders and nags come from the
   system, neutral in tone, always paired with an action.
5. **No portal-itis.** No nav items, tabs, or domains beyond this plan.

## Frozen — do not build, extend, or polish

NL controller, Bylaws Q&A/RAG (verbatim storage stays), new task surfaces
(existing event/initiative/standalone jobs all keep working).

## Decision record

| # | Decision |
|---|----------|
| 1 | Tasks freeze = no new task features. All three job kinds keep working; standalone jobs earn no contribution credit. |
| 2 | No RSVP. "This week" is details + excuse path; zero new write paths in Phase 1. |
| 3 | Everyone — officers included — lands on the member home. The role-branched dashboard dies; officer queues stay in officer pages. |
| 4 | Notification channel is Twilio SMS (already wired in `api/announcements/services/sms.py`). A2P 10DLC registration is the ops long pole — start early. |
| 5 | Notification prefs: per-category toggles with a mandatory core. Core (locked on while SMS enabled): required-event reminders, new fine, standing changed, excuse decision, payment recorded. Toggleable: officer announcements, shoutouts. STOP (or disabling SMS) kills the whole channel; everything stays visible in-app. |
| 6 | Check-in `/c/{code}` becomes a Next.js page: logged-in members one-tap; unauthenticated phone-entry fallback preserved. Fixes the shipped 10-vs-9 digit validation bug in passing. |
| 7 | **Streaks are cut** (revised 2026-07-24). Confirmation shows the events-attended count instead — a number that only goes up. |
| 8 | Initiative proposals: chair roles keep direct creation; any member proposes; officers approve. Approval flips it live and makes the proposer creator-chair; denial requires a reason; proposer is notified either way. |
| 9 | Officer-only engagement score (`api/memberadmin/services/scoring.py`) is kept — never member-visible, never feeds standing. Recorded as a deliberate exception in ADR-0004. |
| 10 | Profiles are chapter-visible and carry exactly three count-up numbers: events attended, initiatives chaired, jobs done (event- and initiative-attached only). |
| 11 | Absence counts and attendance percentage are self-plus-officers only. A member sees their own; officers see everyone's; peers never see another member's attendance stats. |
| 12 | The event organizer roster never earns contribution credit — it stays a planning signal ("needs N more organizers"). Only approved jobs count as "helping." |

## Phase 1 — Member Home Screen

One glanceable view for every logged-in member (officers land here too).

- **My standing**: own bucket (good/warning/delinquent) with itemized reasons
  ("1 unexcused absence — Chapter Meeting, Oct 12") and an action per reason
  (submit excuse / view fine). Reasons are assembled server-side from existing
  data: `list_unexcused_absences` (`api/attendance/services/signals.py`) +
  unpaid fine invoices.
- **This week**: upcoming events, required visually distinct, details + "Can't
  make it? Submit an excuse." No RSVP.
- **My balance**: total owed via the existing
  `/api/treasury/members/{id}/balance`; one tap to the Phase 4 itemized view.
- **Shoutouts slot**: render nothing until Phase 5.

Backend work:
- New member self-standing read: any member reads their own standing, no
  permission key (matches the existing self-or-escalation route pattern).
- Migrate the roster standing view off legacy `require_officer`
  (`api/memberadmin/api/standing.py`) onto the already-seeded
  `standing:view_all` key — pays down an ADR-0001 violation.
- Remove `INCOMPLETE_REQUIRED_TASKS` from
  `api/memberadmin/core/standing_rules.py` (glossary alignment; it never
  shifted the bucket, so no behavior change).

## Phase 2 — Real notifications

- **Delivery worker**: a Vercel cron route draining pending `message_outbox`
  rows (pattern from migration 0070; the outbox currently has no drainer).
  `MESSAGE_DELIVERY_MODE=twilio` goes live.
- **System notification types** (additive `event_type` CHECK rebuild):
  `EVENT_REMINDER_24H`, `EVENT_REMINDER_MORNING`, `EXCUSE_DECIDED`,
  `STANDING_CHANGED`, `FINE_ISSUED`, `PAYMENT_RECORDED`. Dedup keys like
  `EVENT_REMINDER_24H:{event_id}:{member_id}`.
- **Standing change detection**: standing is computed on read today, so
  `STANDING_CHANGED` needs persisted last-known standing per member plus a
  scheduled diff.
- **Preferences**: per-category toggles per decision #5; STOP handling kills
  the channel.
- All copy neutral and actionable ("Fine issued: $25 — Chapter Meeting Oct 12.
  View or excuse: <link>").

## Phase 3 — The check-in moment

- `/c/{code}` moves from the backend inline-HTML page
  (`api/attendance/api/checkin_page.py`) to a Next.js page. Logged-in: one-tap
  check-in. Not logged in: phone-entry fallback (fix: page JS demands 10
  digits, `PhoneCheckIn` demands 9 — the phone path is broken as shipped).
- Confirmation: full-screen green check, event name, timestamp, and the
  member's events-attended count. No streaks, no percentage.
- Attendance percentage appears only on the member's own self-view and in
  officer views.
- Deferred/optional: live chapter attendance ticker on the officer session view.

## Phase 4 — Member money view

Mostly frontend: the backend reads already exist and are unwired —
`/api/treasury/members/{id}/balance`, `/dashboard`, `/statement`, and the
self-scoped `GET /api/fines`.

- Itemized own invoices: dues, rent, fines. Each fine links to its event via
  `unpaid_invoices.source_event_id`; the excuse decision is reconstructed in
  the read service via `(source_event_id, member_id, kind='fine')` — one
  excuse per member per event makes this unambiguous. **No schema change.**
- Payment history + running balance from the ledger. Read-only; no payment
  processing.

## Phase 5 — Initiatives as contribution + Profile

- **Proposal lifecycle** on initiatives (no status column exists today —
  migration 0144): status column + `propose`/`approve` permission keys.
  Chair roles keep `calendar:initiative:create` for direct creation. Approval
  flips live and inserts the proposer as creator-chair (reuse
  `initiative_chairs` mechanics); denial requires a reason; both notify via
  Phase 2.
- **Contribution domain**: its own domain package, computed on read (no
  materialization at chapter scale), never importing `memberadmin` standing
  code. Three counters: events attended (check-ins), initiatives chaired
  (`initiative_chairs`), jobs done (approved `task_commitments` on event- and
  initiative-attached jobs; `GET /api/tasks/attribution/*` is the
  storage-level ancestor). Add the test asserting standing inputs are limited
  to fines + unexcused absences (ADR-0004).
- **Profile**: chapter-visible, the three counters + tenure, screenshot-worthy.
  Self-view adds an own-attendance block. Standing and money never appear here.
- **Shoutouts**: home-screen module gets monthly top-N callouts + personal
  milestones. Never a ranked roster; nobody is visible at the bottom of
  anything.

## Cross-cutting guardrails

- Follow treasury patterns for anything new: integer cents, append-only,
  idempotent audited RPCs, `chapter_id` tenant guards in RPC bodies.
- New permission checks via `api/rbac` only; explicit self-vs-roster keys.
- Any new array-typed RPC param must be registered in
  `_ARRAY_TYPED_RPC_PARAMS` (`api/postgres_client.py`) or it works on Supabase
  and fails locally (`in_create_initiative.p_chair_member_ids` was the first).
- Migrations: new numbered files only; `event_type` CHECK extended by
  rebuilding from the live constraint.
- Mobile-first layouts for every member surface; module-component layering per
  `FrontendConventions.md`.
- Ship phases independently; each is demo-able before the next starts.
