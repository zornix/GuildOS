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

**Chair**:
A member granted a slice of officer work in one domain (risk, social,
recruitment, brotherhood, philanthropy, standards). A chair holds only that
chair role's permissions and is not an officer.
_Avoid_: assistant, supervisor (a supervisor is per-event, not a standing role)
