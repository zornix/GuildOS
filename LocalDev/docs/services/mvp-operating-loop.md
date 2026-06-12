# MVP Operating Loop

The weekly chapter cycle the services exist to run. Each step names the
service and the trust boundary it crosses.

## 1. Plan the week (Calendar)

An officer with `calendar:event:create` creates events, setting `event_type`
(chapter meeting, social, philanthropy, …) and `visibility` (`chapter` by
default; `officer` events are hidden from non-officers via
`calendar:officer:view`).

## 2. Prepare the event (Tasks + Operations)

Setup work becomes tasks (`tasks:create`/`tasks:assign`), optionally grouped
in a `task_group` linked from the event (`events.linked_task_group_id`). The
operations template engine can stamp out standard checklists for recurring
event types.

## 3. Run the event (Attendance)

An officer with `attendance:checkin:create` opens an attendance session
(`/api/attendance/sessions`), which creates a short-code check-in link.
Members check in by phone/short code exactly as before — that path is
unchanged. Manual overrides require `attendance:override`.

## 4. Settle the aftermath (Excuses → Fines → Treasury)

Members submit excuses; officers with `attendance:excuse:review` review them.
Unexcused absences on required events flow through the existing
`FineToInvoice` boundary into treasury invoices (integer cents, ledger-backed,
idempotent). Nothing bypasses the ledger.

## 5. Communicate (Announcements)

Officers draft announcements (`announcements:create`) and send them
(`announcements:send`). Sending is the trust boundary: a plpgsql RPC flips
draft→sent, enqueues to `message_outbox`, and audits. Delivery is **dry-run
only** — no real SMS/email yet. The `members_with_balance` audience is the
treasury seam for dues nags.

## 6. Review members (Standing)

Standing derives from the signals: unpaid fines and balance (treasury),
unexcused absences (attendance), incomplete required tasks (tasks,
reason-code-only). Officers with `standing:view_all` see the roster;
`standing:update` is reserved for explicit status interventions.

## 7. Grow (Recruitment)

Recruitment chairs track recruits through
lead → contacted → attended_event → bid_extended → bid_accepted (or dropped).
Recruit-facing events are normal calendar events.

## 8. Govern (Bylaws + RBAC)

Bylaws documents are stored verbatim; the Q&A endpoint honestly returns
`not_implemented` until a real retrieval layer exists. Admins (and only
admins — `roles:assign`) adjust who can do what; every assignment is
idempotent, tenant-guarded, and audited.

## 9. (Future) Command it (NL Controller)

An officer types "set up Thursday's meeting with attendance and a task list".
Today that creates a `command_request` pending approval and **nothing else** —
there is no parser and no executor. The loop above is what an approved command
would orchestrate, via the same service APIs.
