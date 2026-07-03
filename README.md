# GuildOS

Organization management system for fraternity chapters: events, attendance,
dues/fines treasury, standing, tasks, announcements, roster, and RBAC.

Active development happens in [`LocalDev/`](LocalDev/) (FastAPI + Next.js 16 +
PostgreSQL) — see `LocalDev/CLAUDE.md` for the project guide. Domain language
lives in [`CONTEXT.md`](CONTEXT.md); architectural decisions in
[`docs/adr/`](docs/adr/).

## Recent changes (July 2026)

- **Events V1 Phase 3 — Initiatives** (backend): chair-led initiatives as
  calendar peers of events — new `api/initiatives/` domain, migration
  `0144_initiatives_v1.sql` (`initiatives` + `initiative_chairs`, jobs attach
  via `tasks.initiative_id`), T-36h unclaim lock anchored to initiative start,
  chair approval for initiative jobs, and `kind: "initiative"` items in the
  calendar aggregator. Full pytest suite green (400 tests).
- **Frontend remediation planned**: `LocalDev/docs/imp-fe-remediation.md`
  audits `fratos/` and settles decisions D1–D6 (money always via
  `formatMoney`, adapter/contract data boundary per domain, permission-key
  gating instead of role checks, App Router segment split, token/theme
  cleanup). The 100× money display bug on the officer dashboard is already
  fixed.
- **Domain docs bootstrapped**: root `CONTEXT.md` glossary (Permission, Role,
  Officer, Chair) and ADR 0001 (authority is a permission-key check, never a
  role check).
