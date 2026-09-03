# Permissions Matrix

Source of truth: migrations `0083_rbac_seed_rpcs.sql` (catalog + matrix),
`0121_treasury_v1_rbac_seeds.sql`, `0130`, `0144`, and
`0147_authority_one_gate.sql`, plus `api/rbac/core/policy.py` (legacy compat +
ownership scoping). This document mirrors them; if they disagree, the
code/migration wins. The table below is the 0083 baseline plus the treasury,
initiatives and one-gate additions; later seeds that add a whole **role**
rather than a key are listed under "Later additions".

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

So existing users keep working with zero data migration; migrations 0083 and
0147 also backfilled matching `member_roles` rows, and audience resolution
(announcements / SMS) now reads `member_roles` only. `LEGACY_ROLE_COMPAT`
itself stays until the roles UI is the only assignment path (imp-one-gate D6).

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

`admin` holds **every** permission. Below, ✓ marks seeded grants for the
remaining roles. `officer` is the behavior-preserving image of the deleted
`require_officer` dependency (0147 step 3) — it holds `roles:assign`, but
deliberately **not** `treasury:invoice:void` (0121 decision #5: void/waive is
Treasurer only).

| Permission | officer | member | pres | vp | treas | sec | risk | social | recruit | brother | philan | standards | nme | alumni |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| calendar:event:create | ✓ | | ✓ | ✓ | | ✓ | | ✓ | ✓ | ✓ | ✓ | | ✓ | |
| calendar:event:update | ✓ | | ✓ | ✓ | | ✓ | | ✓ | | | | | | |
| calendar:event:delete | ✓ | | ✓ | | | | | | | | | | | |
| calendar:officer:view | ✓ | | ✓ | ✓ | | ✓ | ✓ | | | | | | | ✓ |
| calendar:initiative:create | | | | | | | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| calendar:initiative:update | | | | | | | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| attendance:checkin:create | ✓ | | ✓ | | | ✓ | | | | | | | | |
| attendance:override | ✓ | | ✓ | | | ✓ | | | | | | | | |
| attendance:excuse:review | ✓ | | ✓ | ✓ | | ✓ | | | | | | ✓ | | |
| attendance:checkin_link:manage | ✓ | | | | | | | | | | | | | |
| members:invite | ✓ | | | | | | | | | | | | | |
| treasury:invoice:create | ✓ | | | | ✓ | | | | | | | | | |
| treasury:invoice:void | | | | | ✓ | | | | | | | | | |
| treasury:payment:verify | ✓ | | | | ✓ | | | | | | | | | |
| treasury:fines:issue | ✓ | | | | ✓ | | | | | | | | | |
| treasury:budget:view | ✓ | | ✓ | | ✓ | | | | | | | | | |
| treasury:audit:view | ✓ | | ✓ | | ✓ | | | | | | | | | |
| treasury:expense:create | ✓ | | | | ✓ | | | | | | | | | |
| treasury:adjustment:create | ✓ | | | | ✓ | | | | | | | | | |
| treasury:refund:create | ✓ | | | | ✓ | | | | | | | | | |
| treasury:rebuild:run | ✓ | | | | ✓ | | | | | | | | | |
| tasks:create | ✓ | | ✓ | ✓ | | | | ✓ | ✓ | ✓ | ✓ | | ✓ | |
| tasks:assign | ✓ | | ✓ | ✓ | | | | ✓ | | | | | ✓ | |
| tasks:complete | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| tasks:review | ✓ | | ✓ | ✓ | | | | | | | | | | |
| announcements:create | ✓ | | ✓ | ✓ | | ✓ | | | | | | | | |
| announcements:send | ✓ | | ✓ | ✓ | | ✓ | | | | | | | | |
| standing:view_all | ✓ | | ✓ | ✓ | ✓ | | ✓ | | | | | ✓ | | |
| standing:update | ✓ | | ✓ | | | | | | | | | ✓ | | |
| standing:remind | ✓ | | | | | | | | | | | | | |
| recruitment:pipeline:view | ✓ | | ✓ | | | | | | ✓ | | | | ✓ | |
| recruitment:pipeline:update | ✓ | | ✓ | | | | | | ✓ | | | | | |
| bylaws:query | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| bylaws:admin | | | ✓ | | | | | | | | | | | |
| nl_controller:execute | ✓ | | ✓ | ✓ | | | | | | | | | | |
| nl_controller:approve | | | ✓ | | | | | | | | | | | |
| roles:assign | ✓ | | | | | | | | | | | | | |

(Column key: pres=president, vp=vice_president, treas=treasurer,
sec=secretary, risk=risk_chair, social=social_chair,
recruit=recruitment_chair, brother=brotherhood_chair,
philan=philanthropy_chair, standards=standards_chair,
nme=new_member_educator, alumni=alumni_advisor.)

## Later additions (not table columns)

| role | added by | permissions |
|---|---|---|
| `finance_board` | 0121 | `treasury:payment:verify`, `treasury:fines:issue`, `treasury:budget:view`, `treasury:audit:view`, `bylaws:query`, `tasks:complete` |
| `treasury_viewer` | 0147 | `treasury:budget:view`, `treasury:audit:view` |

`announcements:send:sms` (0130) is held by `president` / `secretary`.

`calendar:initiative:create|update` (0144) went to the six chair roles and
`admin` only — deliberately **not** `officer`, `president` or `vice_president`
(imp-ev-ph3 D9: initiatives are chair-led). There is no
`calendar:initiative:delete` key; V1 has no delete flow.

## Treasury note

Treasury used to run its own `treasury_grants` capability table with a
`require_capability` dependency. **Migration 0147 deleted both** (ADR-0003: no
grant tables): every treasury gate is now a catalog key checked through
`require_permission` / `has_permission`, and the legacy capability strings are
mapped onto catalog keys as follows.

| legacy capability | catalog key |
|---|---|
| `treasury:read` | `treasury:budget:view` (chapter aggregates) or `treasury:audit:view` (row-level records, ledger) |
| `invoice:create` | `treasury:invoice:create` |
| `payment:review` | `treasury:payment:verify` |
| `expense:create` | `treasury:expense:create` |
| `adjustment:create` | `treasury:adjustment:create` |
| `refund:create` | `treasury:refund:create` |
| `rebuild:run` | `treasury:rebuild:run` |

The SQL helper `treasury_has_capability(chapter_id, capability)` still exists
and still takes a *legacy* capability string — many RLS policies (0006, 0010,
0020, 0030, 0040, 0050, 0120, 0123, 0124) call it. 0147 re-pointed its body at
`member_roles` × `role_permissions` using the same map, so the policies were
left untouched.

## Frontend

`GET /api/rbac/me/permissions` returns `{permissions: string[], roles:
string[]}`. The nav (`fratos/config/navigation.ts`) gates items via
`NavItem.requiredPermission`; the legacy `OFFICER_ONLY` list still applies on
top during the transition.
