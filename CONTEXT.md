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
`treasurer`). Roles determine which permissions a member holds; code never
branches on a role's name.
_Avoid_: officer flag, user type

**Officer**:
A member of the chapter's executive board (president, vice president,
secretary, treasurer, …). Officers currently hold every permission; splitting
authority per office is planned, not present.
_Avoid_: exec, admin, board member

**Chair**:
A member granted a slice of officer work in one domain (risk, social,
recruitment, brotherhood, philanthropy, standards). A chair holds only that
chair role's permissions and is not an officer.
_Avoid_: assistant, supervisor (a supervisor is per-event, not a standing role)
