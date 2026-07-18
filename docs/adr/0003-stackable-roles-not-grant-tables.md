# Granular authority is stackable roles — never a second grant table

A member's permissions are the union of every role they hold (`member_roles`
→ `role_permissions`). When someone needs a narrower slice of authority than
an existing role ("can view treasury but not verify payments"), the answer is
a new narrow role in the catalog (e.g. `treasury_viewer`), assigned alongside
whatever else they hold — never a per-member permission grant, and never a
domain-local grant table.

Decided 2026-07-11, resolving the open question from
`LocalDev/docs/architecture-review-2026-07-10.md` (candidate 1): treasury had
grown a parallel authorization system — `require_capability` over a
`treasury_grants` table of per-member capability rows, 21 call sites, with
capability names (`payment:review`) diverging from the permission catalog
(`treasury:payment:verify`). We chose to fold it into the central system
rather than record it as a deliberate second adapter.

Alternatives considered:

- **Keep `treasury_grants` as a second adapter.** Rejected: two permission
  systems with diverging key names means every auditor and every new domain
  must learn both, and ADR-0001's "one gate" goal is permanently scoped down.
  The flexibility it bought (per-person grants) was unused — the only seeded
  reality was "officers get everything".
- **Add per-member grants to the central system** (a `member_permissions`
  table unioned into the resolver). Rejected: maximum flexibility, but
  permissions would then come from two places, complicating "who can do
  what" audits and the role-management UI. Narrow roles express the same
  outcomes with one mechanism.

## Consequences

- `treasury_grants` and `require_capability` are deleted; treasury routes
  gate on permission keys via `require_permission` like everything else
  (executed by `LocalDev/docs/imp-one-gate.md`).
- Person-level granularity is achieved by seeding narrow roles
  (`treasury_viewer` is the first) and stacking them per member.
- Inventing a permission combination no seeded role expresses requires a new
  role seed (a migration), not an ad-hoc grant. This is deliberate friction:
  every grantable bundle has a name and appears in the catalog.
- CONTEXT.md's **Role** entry records the stackable-union semantics; "
  capability grant" joins its avoid-list.
