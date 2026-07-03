# Authority is a permission-key check, never a role check

Officers (the exec board) currently hold every permission, which makes a plain
`role === "officer"` check look sufficient in the frontend. We decided instead
that all code — backend and frontend — gates behavior on backend-owned
permission keys (`domain:resource:action`, resolved for the frontend via
`GET /api/rbac/me/permissions`), because officer authority will later be split
per exec office (e.g. announcements restricted to president/VP/secretary).
With key-based gating, that split is a backend re-seed of `role_permissions`
with zero frontend changes; with role checks it would be a rewrite of every
gated view.

## Consequences

- Role names appear in seeds and in role-management UI only. A role comparison
  in product code is a defect, with one carve-out: rendering a *subject's*
  role state (e.g. a roster badge) is data display, and contracts expose it as
  a boolean/label rather than a comparable role string.
- New authority must be named as a key and seeded, even when "officers only"
  would do today (e.g. `members:exec:promote`, seeded officer + admin,
  tightenable to president later).
