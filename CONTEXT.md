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
recruitment, brotherhood, philanthropy, standards). A chair holds only that
chair role's permissions and is not an officer.
_Avoid_: assistant, supervisor (a supervisor is per-event, not a standing role)
