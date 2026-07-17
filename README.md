# GuildOS

Organization management system for fraternity chapters: events, attendance,
dues/fines treasury, standing, tasks, announcements, roster, and RBAC.

Active development happens in [`LocalDev/`](LocalDev/) (FastAPI + Next.js 16 +
PostgreSQL) — see `LocalDev/CLAUDE.md` for the project guide. Domain language
lives in [`CONTEXT.md`](CONTEXT.md); architectural decisions in
[`docs/adr/`](docs/adr/).

## 📊 Product dashboard

_Updated 2026-07-16. Plan docs live in [`LocalDev/docs/`](LocalDev/docs/) (`imp-*.md`)._

### ✅ Latest additions (shipped)

- **Events V1 — full feature set, server-side.** The complete events workflow is
  built and tested on the backend:
  - Scheduling with start/end times, co-supervisors, and an invite link.
  - **Jobs** members can claim, report done, and get approved/rejected, with a
    hard "no dropping out within 36 hours" lock.
  - **"Notify members"** — a one-tap SMS blast, allowed only once an event is
    complete (has a supervisor, an organizer, and at least 3 jobs).
  - **Initiatives** — chair-led projects that sit on the calendar next to events
    and reuse the same jobs machinery.
  - **Security assignments & shift swaps** — supervisors assign security, members
    swap shifts with each other, all tracked.
- **Standing shows real money owed.** Fixed a bug where unpaid fines weren't
  counting toward a member's standing.
- **Dev & test tooling repaired.** Officer password login, a green end-to-end
  test suite, and cleaned-up dev scripts. Dead code removed.

### 🔨 In progress / next up

- **Events V1 Phase 5 — the screens.** Everything above exists on the backend but
  has **no user interface yet**: the jobs board, calendar badges/week view, the
  security & swap screens, and the SMS composer. This is the near-term critical
  path — the plan doc still needs to be written before build starts.

### 📋 Backlog

| Item | What it's for | Status |
|---|---|---|
| Architecture cleanup (7 steps) | Consolidate DB access, unify permissions, self-describing DB client, tidy the frontend data/mutation layers | **2 of 7 done** (cleanup + standing fix); steps 3–7 pending |
| Frontend remediation (B–E) | Consistent money formatting, per-domain data adapters, theme/token cleanup | Phase A shipped; B–E pending |
| Check-in link race fix | A latent UI glitch where a freshly made check-in link can be wiped by a slow background refresh | Not started |
| Reseed reliability | Let the demo database reseed cleanly on top of existing data | Not started |

### 🧭 Trajectory

**The backend is ahead of the frontend.** The entire Events V1 feature set is
finished and tested server-side; the product's most valuable next move is Phase 5,
surfacing it in the UI. Running alongside is a 7-step architecture cleanup that is
2/7 complete and paused while events work proceeds. Domain language and decisions
are captured in [`CONTEXT.md`](CONTEXT.md) and [`docs/adr/`](docs/adr/).
