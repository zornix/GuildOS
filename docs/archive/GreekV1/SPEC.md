# GreekOS V1 Spec

**Design philosophy:** *The system proposes, logs everything, humans approve.*
Every consequential action (charges, payments, fines, SMS) has attribution, a timestamp, and an approval gate.

**Anchor user story:** A member paid yearly dues for a year he was abroad; with no paper trail, the chapter had a conflict with no resolution. V1 treasury must make that dispute impossible: every charge traceable, every payment evidenced, every correction logged.

---

## 1. Members & Roles

- Member directory (exists). Roles: President, Secretary, Treasurer / Finance Board, Chairs, Member.
- **Supervisor eligibility:** must hold a chair position.
- Existing auth (magic links) unchanged.

## 2. Calendar

- A **view**, not an entity: aggregates everything with a date.
- Shows: events (and event groups), invoice due dates.
- Overdue invoices remain visible / flagged — they do not silently scroll into the past. *(Resolved — see decision #3: overdue invoices render on the calendar at their issued/due position, flagged overdue, and are also surfaced on the member's dashboard.)*

## 3. Events

- **Type:** officer creates new or selects existing. Unique name, case-insensitive match. Seed 5–6 defaults (Chapter Meeting, Philanthropy, Brotherhood, Social, Recruitment).
- **Flags:** `required` (counts toward attendance), `finable`.
- **Group:** nullable `group_id` links related events (setup → event → cleanup). Each is a full event with its own check-in and attendance. No phase abstraction. Groups may contain any number of events.
- **Supervisor:** exactly one; volunteers or is assigned; must hold a chair. Creator ≠ necessarily supervisor.
- **Organizers:** members who volunteer (or are assigned via tasks). Soft minimum 2–3: event can be created understaffed but is publicly flagged "needs N more organizers" on calendar/dashboard. Never a hard block.
- **Audience:** `all | officers | custom list` *(resolved — decision #4)*.
- **Attendance:** existing anti-cheat check-in links, attached to the event. Attendance % = derived query over `required` events.

## 4. Tasks

- Attached to an event **or** standalone.
- Fields: title, assignee(s), status (open / committed / done), due date (optional, shows on calendar).
- **Open tasks:** members volunteer; multiple tasks per member allowed.
- **Uncommit policy:** free uncommit until **24 hours before the event start** *(resolved — decision #1)*, but every uncommit is **logged and visible** (social accountability over hard locks).
- Attribution ledger: per-member history of tasks committed/completed and events organized/supervised.

## 5. Treasury

**Entities — invoices and payments are separate, append-only. Balance is computed, never stored.**

### Invoices
- Fields: member, line items, amount, `issued_at`, `due_at`, `source` (`dues` | `fine` | `manual`), issued_by, status (`open` | `paid` | `void`).
- Remain on member's treasury dashboard until covered or voided.
- **Void/waive:** **Treasurer only** *(resolved — decision #5; no second approval required)*, requires a reason, logged. (This is the abroad-guy fix.)

### Fines
- Flat **$25** for V1 (no fine schedule yet — explicitly deferred).
- Never automatic. Finance Board may issue fine invoices **≥24h after** a required event's attendance time. System surfaces who missed; humans choose to invoice.

### Payments ("balance adjustment submissions")
- Member submits: amount, method (Venmo / Zelle / cash / check), evidence (image upload and/or reference text, e.g. Venmo memo).
- Submission enters **pending** state — visible to the member as pending balance.
- **Verification queue:** **full Finance Board** (Treasurer + Finance Board members) *(resolved — decision #2)* approve or reject (rejection requires reason). All actions logged.
- **Allocation:** verified payments apply to the member's overall balance; invoices auto-mark `paid` oldest-first as the balance covers them. Treasurer can override allocation; overrides logged.
- **Partial payments:** fully supported by construction (balance model).

### Ledger rules
- No edits, no deletes. Corrections are new entries referencing the original.
- Every entry: actor, timestamp, action, reference.

## 6. Announcements

- In-app feed (flat posts by officers; no comments/reactions in V1).
- **SMS:** send permission limited to **President and Secretary**. Confirmation step showing recipient count. Every send logged with sender, visible to exec.
- Infra: existing Resend / Twilio. Verify A2P 10DLC campaign registration covers application-initiated announcement SMS.

## 7. Explicitly cut from V1

- Per-event forum / discussion
- Temporary roles
- NLP event creation, AI minutes summarization (deferred, not dead)
- Bylaws RAG **integration** (standalone RAG already exists; wiring it as the citation layer for fines is V2)
- Automatic fines; fine schedule
- Payment auto-reconciliation (CSV import)
- Recording/transcription of meetings

## Decisions (resolved 2026-06-12)

1. **Uncommit cutoff:** 24 hours before event start.
2. **Payment verifier roles:** full Finance Board (Treasurer + Finance Board).
3. **Overdue invoices:** remain visible on the calendar as issued (flagged overdue at their due position) **and** surfaced on the member's dashboard until covered or voided.
4. **Audience model:** V1 ships with selections — `all | officers | custom list`.
5. **Void/waive authority:** Treasurer alone (reason required, logged); no second approval.

## Suggested build order

1. Event model + types + group_id; wire existing check-in links → attendance derived views
2. Tasks + volunteering + attribution ledger
3. Treasury: invoices → payments/pending → verification queue → allocation → void/waive
4. Calendar aggregation view (events + invoice due dates)
5. Announcements feed + SMS gate/logging
6. Instrumentation (event tracking) from day one — you'll want the usage data

## Engineering constraints

- Backend continues to follow **DDD** (canonical domain-package shape, `docs/services/README.md`) and **TDD** (pytest; tests written with/before implementation).
- Money is integer cents; trust-boundary mutations via plpgsql RPCs with tenant guards, idempotency, and `audit_logs`/`big_ledger` writes; append-only ledger.
- Never modify applied migrations; add new ones.
- Frontend follows the treasury color scheme: dark blue background, purple and green accents, white and green text.
