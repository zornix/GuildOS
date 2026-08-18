# GuildOS — Feature Overview

Operational software for fraternity chapters: one system for events, money,
and accountability. This is the presentable feature list (see
`docs/ARCHITECTURE.md` for how it's built).

## Daily operations

### Dashboard
One screen for the state of the chapter: upcoming events, open tasks, dues
status, and who needs attention.

### Events
- Exec creates events; each has a time range, description, type (Chapter
  Meeting, Philanthropy, Brotherhood, Social, Recruitment), and audience
  (all / officers / custom).
- **Supervisors (officers):** the creator is a supervisor automatically and
  can add co-supervisors. They own the event and approve finished jobs.
- **Organizers (chairs):** run the event on the ground. An event with zero
  organizers is publicly flagged **Organizers Needed** — any chair can
  volunteer from the calendar in one tap.
- **Jobs:** events decompose into claimable jobs, open to any member.
  Lifecycle: To-do → In progress (first claim; each job has a people-needed
  count and shows fill state like 2/4) → Done-reported (any claimant reports,
  one report covers the job) → Approved (supervisor signs off). Rejection
  requires a written reason and notifies the claimants — work is never
  silently undone.
- **36-hour lock:** members can unclaim a job until 36 hours before start;
  after that unclaiming closes but claiming stays open. Late help is welcome,
  late bailing isn't.
- **Notify gate:** the "Notify members" button stays locked until the event
  is actually planned (≥1 supervisor, ≥1 organizer, ≥3 jobs), with an inline
  checklist showing exactly what's missing. No half-planned spam.
- **Security (optional):** a pre-assigned job type. Officers assign members
  directly from a table of member stats instead of waiting for volunteers.
  Assigned members can request a swap; the other member must accept, and both
  sides are notified.

### Attendance, check-ins, and excuses
- Live check-in links: share a link at the door and attendance records itself
  in real time. Officers can generate and kill links per event.
- Excuse requests: members submit excuses for missed events; officers approve
  or deny.

### Initiatives
Chair-led projects — created and run entirely by chairs, no officer required.
Any number of assigned chairs (never zero — the last chair can't be removed).
Same job machinery as events, but the initiative's chairs approve the work.
No supervisors, security, or notify gate.

### Calendar
Events, initiatives, and announcements all render on one chapter calendar,
color-coded by type, with badges for Organizers Needed and incomplete events.

### Tasks
Assign chapter work to members and track what's actually getting done.

### Announcements
Exec text blast — lands on the calendar and goes out to every member by SMS.

## Money

### Treasury
Dues, invoices, receivables, and payments. Every member's balance is always
current and every charge traceable to why it exists. All money is integer
cents end to end — no float rounding errors.

### Fines
Issue fines manually or automatically from missed events. Fines land on the
member's balance like any other charge.

### Append-only audit ledger
Every financial event is written to a permanent ledger (`big_ledger` +
`audit_logs`) that can't be edited or deleted — corrections are new entries
that reference the original. Disputes are settled by reading the history, not
by arguing.

## People & accountability

### Members
The chapter roster as the single source of truth.

### Standing
Good standing, probation, and status changes tracked per member — driven by
attendance and dues, not memory.

### Roles & access (RBAC)
Fine-grained permissions per role: the treasurer sees money, the social chair
doesn't, and handoffs at elections take minutes. Every screen and API route
respects roles automatically.

## Officer tools

### Recruitment
A rush pipeline: track every PNM from first contact to bid.

### Command (natural language)
Type what you want in plain English — "fine Jake $20 for missing chapter" —
and GuildOS executes it through the same permission-checked, audited path as
everything else.

### Bylaws
One canonical, versioned copy of the chapter's bylaws lives in the app —
everyone reads the same document. (Q&A over bylaws is not implemented yet;
the API returns an honest `not_implemented` rather than a made-up answer.)

## Behind the scenes

- **Notifications outbox:** transactional enqueue for SMS/notifications
  (event notify, announcements, security swaps, job rejections).
- **Scheduled jobs (cron):** recurring background work.
- **Multi-tenant by chapter:** every table carries `chapter_id`; tenant
  isolation is enforced server-side on every mutation, with row-level
  security as defense-in-depth.
- **Idempotent, audited writes:** every trust-boundary mutation goes through
  a database RPC that enforces tenant guards, idempotency keys, and audit
  logging.
