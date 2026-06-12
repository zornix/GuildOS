# Permissions Matrix

Source of truth: migration `0083_rbac_seed_rpcs.sql` (catalog + matrix) and
`api/rbac/core/policy.py` (legacy compat + ownership scoping). This document
mirrors them; if they disagree, the code/migration wins.

## Model

- **Roles** are a global catalog (`roles`); **assignments** are chapter-scoped
  rows in `member_roles` (unique on member, role, chapter). Roles are **not
  time-bounded** — revocation is explicit, via `roles:assign`.
- A member's effective permissions are the **union** of (a) permissions of all
  assigned `member_roles` and (b) the legacy-compat mapping of `members.role`.
- Checks go through `require_permission(*perms)` (FastAPI dependency, ANY-of)
  or `has_permission(member, perm, resource=None)` (pure). Nothing else.

## Legacy compatibility

`members.role` (TEXT, CHECK `officer|member`) is untouched. The resolver maps
it via `LEGACY_ROLE_COMPAT`:

| `members.role` | mapped RBAC role |
|---|---|
| `officer` | `officer` |
| `member` | `member` |

So existing users keep working with zero data migration; migration 0083 also
backfilled matching `member_roles` rows.

## Ownership-scoped permissions

Some permissions are scoped to a resource the member owns. The convention:
pass `resource={"owner_member_id": ...}` to `has_permission`. If the member is
not the owner, the check escalates per `OWNERSHIP_ESCALATIONS`:

| base permission | escalates to (for non-owned resources) |
|---|---|
| `tasks:complete` | `tasks:review` |

Example: any member may complete **their own** task; completing someone
else's task requires `tasks:review`.

## Roles × permissions

`admin` holds **every** permission (including `roles:assign`, which no other
role has). Below, ✓ marks seeded grants for the remaining roles.

| Permission | officer | member | pres | vp | treas | sec | risk | social | recruit | brother | philan | standards | nme | alumni |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| calendar:event:create | ✓ | | ✓ | ✓ | | ✓ | | ✓ | ✓ | ✓ | ✓ | | ✓ | |
| calendar:event:update | ✓ | | ✓ | ✓ | | ✓ | | ✓ | | | | | | |
| calendar:event:delete | ✓ | | ✓ | | | | | | | | | | | |
| calendar:officer:view | ✓ | | ✓ | ✓ | | ✓ | ✓ | | | | | | | ✓ |
| attendance:checkin:create | ✓ | | ✓ | | | ✓ | | | | | | | | |
| attendance:override | ✓ | | ✓ | | | ✓ | | | | | | | | |
| attendance:excuse:review | ✓ | | ✓ | ✓ | | ✓ | | | | | | ✓ | | |
| treasury:invoice:create | | | | | ✓ | | | | | | | | | |
| treasury:payment:verify | | | | | ✓ | | | | | | | | | |
| treasury:budget:view | | | ✓ | | ✓ | | | | | | | | | |
| treasury:audit:view | | | ✓ | | ✓ | | | | | | | | | |
| tasks:create | ✓ | | ✓ | ✓ | | | | ✓ | ✓ | ✓ | ✓ | | ✓ | |
| tasks:assign | ✓ | | ✓ | ✓ | | | | ✓ | | | | | ✓ | |
| tasks:complete | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| tasks:review | ✓ | | ✓ | ✓ | | | | | | | | | | |
| announcements:create | ✓ | | ✓ | ✓ | | ✓ | | | | | | | | |
| announcements:send | ✓ | | ✓ | ✓ | | ✓ | | | | | | | | |
| standing:view_all | ✓ | | ✓ | ✓ | ✓ | | ✓ | | | | | ✓ | | |
| standing:update | | | ✓ | | | | | | | | | ✓ | | |
| recruitment:pipeline:view | ✓ | | ✓ | | | | | | ✓ | | | | ✓ | |
| recruitment:pipeline:update | ✓ | | ✓ | | | | | | ✓ | | | | | |
| bylaws:query | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| bylaws:admin | | | ✓ | | | | | | | | | | | |
| nl_controller:execute | ✓ | | ✓ | ✓ | | | | | | | | | | |
| nl_controller:approve | | | ✓ | | | | | | | | | | | |
| roles:assign | | | | | | | | | | | | | | |

(Column key: pres=president, vp=vice_president, treas=treasurer,
sec=secretary, risk=risk_chair, social=social_chair,
recruit=recruitment_chair, brother=brotherhood_chair,
philan=philanthropy_chair, standards=standards_chair,
nme=new_member_educator, alumni=alumni_advisor.)

## Treasury note

Treasury keeps its own `treasury_grants` capability system for its internal
operations — RBAC seeds the `treasury:*` permission strings for cross-service
visibility (budgets, audit views) but did **not** replace treasury's
authorization. Unifying them is a CONFORM_TODO, not a behavior change to make
casually.

## Frontend

`GET /api/rbac/me/permissions` returns `{permissions: string[], roles:
string[]}`. The nav (`fratos/config/navigation.ts`) gates items via
`NavItem.requiredPermission`; the legacy `OFFICER_ONLY` list still applies on
top during the transition.
