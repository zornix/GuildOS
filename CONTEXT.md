# GuildOS

Operational software for fraternity chapters: events, attendance, treasury
(dues/fines), standing, tasks, announcements, roster, and access control.

## Language

**Permission**:
A backend-owned key (`domain:resource:action` — or 2-segment `resource:action` for many keys — e.g. `attendance:excuse:review` or `tasks:create`)
naming one thing an actor is allowed to do; the only primitive any code — backend
or frontend — may gate authority on.
_Avoid_: capability, role check

**Role**:
A named bundle of permissions assigned to a member (e.g. `social_chair`,
`treasurer`). A member may hold several roles at once; their permissions are
the union of every role they hold. Narrow, stackable roles (e.g. a
treasury-viewer role) are how per-person granularity is achieved — never
per-member permission grants, and never a second grant table. Code never
branches on a role's name.
_Avoid_: officer flag, user type, capability grant

**Officer**:
A member of the chapter's executive board (president, vice president,
secretary, treasurer, …). Officers currently hold every permission; splitting
authority per office is planned, not present.
_Avoid_: exec, admin, board member

**Standing**:
A member's accountability signal, computed from engagement only: unexcused
absences at required events and unpaid fines. Routine billing (dues, rent,
utilities) never affects standing — money owed for those is a treasury
concern, visible only there.
_Avoid_: total debt, balance owed

**Initiative**:
A member-led effort on the chapter calendar, run by its chairs, with jobs but
no attendance, fines, or supervisors. Chair roles create initiatives directly;
anyone else submits a proposal.
_Avoid_: project, committee event

**Proposal**:
An initiative awaiting officer approval. Approval makes it live and makes the
proposer its creator-chair; denial carries a reason back to the proposer.
_Avoid_: request, draft initiative

**Contribution**:
A member's auto-derived positive record: events attended, events organized
or supervised (with attendee counts), initiatives chaired, and every job
completed and verified, attached or standalone. It exists to help the member
— a résumé-grade record they can cite — not to measure them. Only structurally-known facts count —
nothing manually awarded or officer-verified — and contribution never feeds
standing. Counts only go up; absences and attendance percentages are not
contribution and are visible only to the member themself and officers.
_Avoid_: points, merits, engagement score

**Shoutout**:
A positive-only, auto-derived callout — a monthly top-N or a personal
milestone. There is never a ranked roster of all members; nobody is visible
at the bottom of anything.
_Avoid_: leaderboard, ranking

**Job**:
A claimable unit of work a member commits to, reports done, and a supervisor
or chair approves. A job may be attached to an event, attached to an
initiative, or standalone; every verified job counts toward contribution.
Jobs never affect standing.
_Avoid_: task (storage-layer name only), chore, assignment, house job

**Chair**:
A member granted a slice of officer work in one domain (risk, social,
rush, brotherhood, philanthropy, standards). A chair holds only that
chair role's permissions and is not an officer.
_Avoid_: assistant, supervisor (a supervisor is per-event, not a standing role)

**Dues run**:
One batch of identical dues invoices — same title, amount and due date — issued
to every active member at once, minus anyone the treasurer excludes. A fine is
an invoice too, just issued one at a time; both land in the same member view.
_Avoid_: dues cycle, billing batch, invoice blast

**Treasury board**:
Whoever holds `treasury:payment:verify` — the members who review the payments
brothers claim to have made and either verify or reject them. Not an office:
a treasurer and a narrow treasury-viewer role can both hold the key.
_Avoid_: finance committee, treasury team

**Setup code**:
The one-time, single-use code a member redeems to claim their account or reset
their password — issued on invite, chapter creation, roster import, or by an
officer. It is emailed to the member automatically and shown to the issuing
officer once as a hand-over fallback. There is no self-serve password reset.
_Avoid_: invite link, magic link, temporary password

**Channel**:
Which provider carries one queued message: `email` or `sms`. Everything
automatic is email; SMS is only the two announcement blasts an officer composes
and sends on purpose, and only those carry consent enforcement and the opt-out
footer (ADR-0005).
_Avoid_: delivery mode (that is dry_run vs. the live provider), transport

**Cancelled event**:
An event with attached history (attendance, jobs, fines) that was cancelled rather than hard-deleted (`cancelled = true`, `required = false`). Cancelled events are hidden from all lists while preserving history.
_Avoid_: deleted event, purged event

**Waived fine**:
An issued fine invoice marked `cancelled` via the void RPC, forgiving the amount owed without deleting the historical record.
_Avoid_: deleted fine, refunded fine

**Door code**:
A short-lived check-in code for an event. Check-in requires being signed in; members cannot read active codes through the API.
_Avoid_: public check-in code, open link

**Legacy display role**:
The two-value `members.role` column (`officer` or `member`), kept in step by the RPCs. It does not store the highest-precedence assigned role; permissions come from `member_roles` plus an implicit `member` baseline.
_Avoid_: system role, permission level

**Top role**:
`admin` or `president`: only an admin may grant or revoke these roles, and every
chapter must retain at least one admin. Roster import cannot assign them.
_Avoid_: highest display role, officer flag

**Heartbeat**:
The durable `cron_heartbeats` row for `drain-outbox`, recording `last_started_at`,
`last_finished_at`, delivery counts and oldest pending age after a global drain.
`/api/health` reads its finish time to report a stale drain after 15 minutes.
_Avoid_: ping check, status page
