# M7 — Roles legend

> Read `00-README.md` first. Test first. Stay in your lane. Custom roles are deferred; do not add editing.

**Goal:** anyone assigning roles can see what each role allows, from the same catalog the resolver uses; descriptions corrected; a drift test keeps code and catalog in step.
**Spec:** `../01-phase-b-design.md` §7 (roles on Profile); `../audit/rbac.md` §5, §6, DELIVERABLE table.
**Migrations:** 0225.
**Allowed files:** backend `migrations/0225_permission_descriptions.sql`, `api/rbac/**`, tests under `tests/rbac/`; frontend `components/roster/**`, `components/MemberRolesPanel.tsx`, `components/me/Roles.tsx`, `lib/roles.ts`, `api.ts`/`types.ts` (M7 block), `routes.tsx` (`/cabin/roster`, `/roster/:memberId` lines).

## T1 — Backend: catalog endpoint and corrected descriptions

- [ ] `migrations/0225_permission_descriptions.sql`: `ALTER TABLE roles ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';` then `UPDATE permissions SET description = … WHERE key = …` for every key in the audit's "Rewrite" list (`../audit/rbac.md` → "Which keys need a description"), and `UPDATE roles SET description = …` for all 16 roles using the plain-English column of the DELIVERABLE table (derived from routes, not from CONTEXT.md). Mark the two dead keys' descriptions "(no effect yet)". Keep each description ≤ 120 chars, imperative ("Verify and record payments; see any member's treasury dashboard").
- [ ] Failing tests `tests/rbac/test_roles_catalog.py`: `GET /api/rbac/roles` returns `[{key, label, description, permissions: [{key, description}]}]` for every role incl. `member`; descriptions non-empty for every seeded key; the `member` baseline is included on each role's effective list? — **no**: return explicit grants only, plus a top-level `baseline: [{key, description}]`; any authenticated member may call it (unchanged gate).
- [ ] Implement in `api/rbac/api/roles.py` + `db/repositories/member_roles.py` (one join query). Response model in `api/rbac/api/schemas.py`. Additive; the old fields stay.
- [ ] Drift test `tests/rbac/test_permission_keys_drift.py`: import `api.index.app`, walk `app.routes`, collect every key passed to `require_permission` (inspect dependency closures; the existing `require_permission` returns a dependency — add a `.keys` attribute to it so the test can read them) plus every literal used with `has_permission` (grep `api/` for `"[a-z_]+:[a-z_:]+"` in `has_permission(` calls); assert each exists in `permissions`; assert every seeded key is either used or in an explicit `KNOWN_UNUSED = {"standing:update", "calendar:initiative:update"}` set with a comment pointing at this plan.
- [ ] Update `docs/services/permissions-matrix.md`? **Not your lane** (docs). Note it under OUTSIDE MY LANE.
- [ ] Checkpoint: `python3 -m pytest tests/rbac -q`.

## T2 — Frontend: legend in the roles panel and on the profile

- [ ] `lib/roles.ts`: `groupByDomain(permissions)` → `{ announcements: [...], attendance: [...], … }` with domain labels; `diffRoles(current, candidate)` → keys gained; tests.
- [ ] `components/roster/RolesPanel.tsx` (replaces `MemberRolesPanel`): left list of roles with checkboxes (as today), right pane shows the selected/hovered role's description and its permissions grouped by domain with the server descriptions. Roles the actor cannot grant (the server will 403 under D11) are shown disabled with "You don't hold every permission in this role". Keep the optimistic toggle out: toggle → request → refetch → toast.
- [ ] `components/me/Roles.tsx` on `/me`: "Your roles" with each role's description and a collapsible list of what it allows; "Everyone can" section for the baseline.
- [ ] `/roster/:memberId`: member card (name, class, standing if allowed, roles with descriptions, Roles button for `roles:assign`).
- [ ] Tests: panel renders a description from fixture; disabled state when the fixture actor lacks a key; profile lists baseline.
- [ ] Checkpoint: `npm test && npm run lint && npm run build`.

## Definition of done

M7 acceptance row; the drift test is green on `main` after merge; no frontend file contains a permission description string.

## Risks

- Hard-coding `KNOWN_UNUSED` is a deliberate ceiling (`ponytail:` comment): the day those keys get a route, delete them from the set.
