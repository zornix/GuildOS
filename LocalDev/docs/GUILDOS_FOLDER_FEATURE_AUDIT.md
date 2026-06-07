# GuildOS vs Prod Audit (Repository Snapshot)

Date: 2026-04-20  
Scope: Compare `/home/mshi/GuildOS` (repo root) with `Prod/`, then audit planned/deferred features found in `GuildOS/`.

## 1) Comparison: repo root vs `Prod/`

### Repo root (`/home/mshi/GuildOS`)

The repository root currently contains:

- `Prod/` (production-shaped app currently in active use)
- `GuildOS/` (parallel/legacy-internal app workspace with deferred scope artifacts)
- `README.md` (minimal)
- `.gitignore`

### `Prod/` (active production-shaped codebase)

`Prod/` contains the active FastAPI + Next.js stack and docs:

- `api/` backend routes/services/models
- `fratos/` frontend app, views, hooks, and API client
- `migrations/` SQL migrations
- `scripts/` operational scripts
- `docs/` product docs and architecture
- `README.md`, `requirements.txt`, `package.json`

### High-level differences

- `Prod/` is leaner and focused on the attendance MVP runtime.
- `GuildOS/` still includes explicit deferred/history surfaces such as `deferred/`, `deploy/`, and local seeding/E2E harness files.
- Both folders document similar MVP feature sets, but `GuildOS/` also preserves roadmap/deferred planning details that are mostly absent from `Prod/`.

## 2) What exists inside `GuildOS/` (top-level audit)

Core app/runtime folders:

- `api/`
- `fratos/`
- `migrations/`
- `scripts/`
- `requirements.txt`, `package.json`, `vercel.json`

Operational/testing/developer folders:

- `deploy/` (local-dev, preflight, Vercel deploy helpers)
- `docker-compose.yml`
- `fratos/e2e/` (Playwright tests)
- `RUNNING.md`

Deferred/roadmap-specific content:

- `deferred/docs/ROADMAP.md`
- `deferred/api/routes/delinquency.py`
- `deferred/api/services/delinquency.py`
- `deferred/fratos/views/delinquency.tsx`
- `deferred/fratos/mocks/mock-api.ts`
- `deferred/fratos/mocks/mock-db.ts`
- `deferred/fratos/utils/supabase/*`

Instruction/spec governance:

- `CLAUDE.md` (contains explicit MVP vs deferred scope instructions)

## 3) Planned features found in `GuildOS/`

Planned/deferred features are primarily defined in `GuildOS/deferred/docs/ROADMAP.md` and reinforced by `GuildOS/CLAUDE.md`.

### Planned (not MVP-complete) roadmap phases

1. **Phase 2: Phone-based onboarding**
   - Join flow via `/join/{slug}`
   - Name + phone registration path
   - Optional chapter passphrase

2. **Phase 3: Wire frontend to real backend**
   - Disable mock runtime and fully validate real API integration end-to-end

3. **Phase 4: Task board**
   - Task posting/claim/submission/review lifecycle
   - Fine-credit workflow linked to task completion

4. **Phase 5: Recognition + engagement**
   - Points, leaderboard, streaks, and “Pay or Do” task alternative
   - Weekly digest concept

5. **Phase 6: Additional backlog**
   - Announcements
   - Voting/polls
   - Dues processor integration
   - Calendar sync
   - Mobile app shell
   - Multi-chapter admin
   - Expanded audit log
   - RLS hardening

### Technical debt / enabling items still called out

- Add/finish phone column rollout and member population
- Rate limiting for phone check-in
- Error monitoring (e.g., Sentry)
- Reminder notification integration
- Connection pooling/perf hardening

## 4) Deferred features explicitly identified in `GuildOS/`

From `GuildOS/docs/FEATURES.md`, `GuildOS/CLAUDE.md`, and `GuildOS/deferred/*`:

- Delinquency scoring engine and advanced delinquency UI
- Security auto-assignment
- Reminder/notification integration
- Mock API/runtime mode
- Supabase SSR auth/magic-link flow pieces
- Advanced per-member event breakdown
- Task board, points, streaks, leaderboard (roadmap)
- Phone-based onboarding/join flow (roadmap)

## 5) Audit takeaway

- `Prod/` appears to be the active, tighter MVP track.
- `GuildOS/` contains both runnable MVP components and broader planning/deferred artifacts.
- If the intent is strict production readiness, planned features should continue to be treated as deferred unless they are moved into `Prod/` with explicit implementation and validation.
