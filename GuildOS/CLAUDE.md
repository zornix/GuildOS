You are a senior full-stack engineer and product-focused technical lead. You are working inside my existing FraternityOS codebase. Your job is to aggressively reduce scope, isolate deferred features, and leave me with a clean MVP that is deployable to Vercel and testable against a local Postgres-backed setup.

You must operate with a “ship the smallest useful product” mindset.

==================================================
PRODUCT GOAL
==================================================

Build and leave production-ready only this MVP:

1. Officer auth
2. Members roster
3. Events CRUD
4. Open / close check-in link
5. Phone-based member check-in
6. Attendance roster per event
7. Excuse submit + approve/deny
8. Automatic fine administration based on attendance
9. Simple member standing based on attendance
10. Vercel deployment readiness:
Refactor the repo into deferred and prod folders.
In prod:
fraternityos/
  apps/
    web/                  # Next.js frontend
    api/                  # FastAPI backend
  packages/
    ui/                   # shared React UI components
    config/               # shared tsconfig/eslint/prettier/env helpers
    types/                # shared DTOs / API contract types
  infra/
    docker/
    scripts/
  .github/
  turbo.json
  package.json
  pnpm-workspace.yaml
  README.md

Create a clear backend API surface:
/api/v1/auth/*
/api/v1/members/*
/api/v1/attendance/*
/api/v1/excuses/*
/api/v1/fines/*


Then on the frontend:

one API client layer
one place for base URL config
one place for auth token/cookie handling
one place for typed response parsing

Do not let React components call raw endpoints all over the codebase.

A good shape is:

apps/web/src/lib/api/client.ts
apps/web/src/lib/api/attendance.ts
apps/web/src/lib/api/fines.ts

That way UI stays decoupled from deployment details.

For the FastAPI project, keep the app entrypoint in one of Vercel’s supported locations such as app.py, index.py, server.py, or src/index.py.


Keep one source of truth in the backend:

apps/api/
  alembic/
  app/
    models/
    schemas/
    services/

Use:

SQLAlchemy models for persistence
Pydantic schemas for request/response
service layer for business logic

Do not put business logic in route handlers.

For example:

attendance_service.py
fine_service.py
excuse_service.py

This will matter a lot because fraternity logic gets messy fast:

excuse approved but already fined
attendance scanned twice
member status inactive but billed
manual fine override after payment

Refactor into modules, not by random file type.

Backend module structure
app/
  core/          # settings, auth, db, dependencies
  modules/
    members/
    attendance/
    fines/
    excuses/
    tasks/

Each module should contain:

router
schemas
models
service
repository if needed

That makes future extraction possible if the system grows.

Do not import backend logic concepts directly into frontend structure. Share only stable DTO/type shapes.

Only extract shared code when duplicated twice or more.

Fraternity ops software has infinite feature creep. Attendance + excuses + fines alone is enough for a credible first deployment.


==================================================
IMPORTANT STRATEGIC RULES
==================================================

- Do not expand scope.
- Do not preserve unfinished complexity just because it already exists.
- Prefer deletion, hiding, or moving code over “keeping future flexibility.”
- Optimize for the fastest path to a working deployed MVP.
- Assume a small chapter-sized dataset. Optimize for simplicity, reliability, and clean UX, not premature scale.
- Leave the codebase cleaner than you found it.

==================================================
DEFERRED FEATURES TO REMOVE FROM MVP SURFACE
==================================================

These features must be treated as deferred and moved out of the active MVP code path:

- questboard / task board / task submissions / task credits
- recognition systems
- points
- streaks
- leaderboard
- weekly digest
- reminders / notification integrations
- security auto-assignment
- advanced delinquency scoring UI and related nonessential endpoints
- phone-based onboarding / join flow
- announcements
- voting / polls
- dues processor integrations
- calendar sync
- multi-chapter admin
- audit log extras not required for MVP
- any mock/demo-only surfaces not needed for MVP deployment

==================================================
REQUIRED WORK
==================================================

PHASE 1 — AUDIT AND CLASSIFY
1. Audit the repository and identify:
   - files and folders required for MVP
   - files and folders tied to deferred features
   - files that are mock-only, dead, duplicate, or misleading
2. Produce a short internal plan before making changes.
3. If a feature is partially entangled with MVP code, separate it carefully instead of breaking MVP functionality.

PHASE 2 — MOVE DEFERRED FEATURES TO A CLEAR SEPARATE FOLDER
Create a top-level folder for deferred work, for example one of:
- deferred/
- archive/deferred/
- experimental/deferred/

Choose the cleanest option and be consistent.

Move deferred feature code there where practical:
- frontend pages/components/hooks/services tied only to deferred features
- backend routes/services/models tied only to deferred features
- docs for deferred features
- mock data or utilities only used by deferred features

Rules:
- preserve git-friendly structure
- update imports if needed
- if fully moving a file is unsafe, leave the file in place but strip the deferred feature from the active app and add a clear TODO/deferred note
- do not leave broken imports
- do not leave deferred routes registered in the active app
- do not leave deferred nav items visible in the UI

PHASE 3 — CREATE THE REAL MVP
The active product after refactor must contain only:

A. AUTH
- officer email login flow that works for MVP
- remove demo auth and mock auth from the active runtime path
- wire the real auth/session path so the frontend talks to the real backend (two vercel projects)
- ensure API requests include auth token where needed

B. MEMBERS
- active member roster page
- simple role display
- only functionality needed for MVP
- exec has role change ability

C. EVENTS
- list events
- create event
- view event detail
- update/delete
- check-in link open/close
- clear event detail page as operations hub

D. CHECK-IN
- preserve the standalone phone check-in flow
- verify end-to-end:
  officer opens check-in
  member visits link
  member enters phone
  attendance is recorded
- keep UX fast on mobile

E. ATTENDANCE / EXCUSES / FINES
- event attendance roster
- excuse submission and officer review
- fine processing
- simple fine list and basic management
- support either:
  1. existing cron flow if already reliable, or
  2. a manual “process absences/fines” button if that is faster and safer for MVP
Choose the smallest reliable path.

F. MEMBER STANDING
Replace or minimize advanced delinquency logic.
For MVP, use simple explicit standing rules, such as:
- good_standing
- warning
- delinquent

PHASE 4 — REMOVE MOCK MODE FROM ACTIVE PRODUCT
- remove or disable mock-mode code paths from the active runtime
- keep mock code only if safely archived in deferred or clearly separated for dev use
- MVP should run against real backend/services, not demo data
- no active page should depend on mock-only data

PHASE 5 — CLEAN DEPLOYMENT FOR VERCEL
Make the codebase deployment-ready for Vercel.

Required:
- ensure FastAPI entrypoint is correct
- ensure frontend build config is correct
- ensure routing is correct for frontend and API
- ensure environment variables are clearly documented
- ensure dependencies are fully declared
- add missing package manifests or Python dependency files if absent
- add missing __init__.py files if needed
- remove obvious deployment footguns
- ensure no dead imports break build
- verify same-origin or configured API base behavior is correct
- verify phone check-in page still works when deployed

PHASE 6 — LOCAL TESTING READINESS
Assume I will test on a local Postgres  setup first.

Do what is necessary so that:
- local env setup is obvious
- environment variables are documented
- DB prerequisites are explicit
- migrations/schema expectations are clear
- phone field requirement is documented
- basic seed path or manual test path is documented

==================================================
IMPLEMENTATION PREFERENCES
==================================================

Backend:
- prefer simple, explicit service logic
- remove nonessential abstractions
- preserve working validation and business rules where useful
- avoid introducing new infrastructure

Frontend:
- reduce page count
- reduce navigation complexity
- prefer one strong event operations page over many fragmented screens
- optimize officer workflows for desktop and member check-in for mobile
- keep styling clean and functional, not fancy

Performance:
- optimize for fewer requests and simpler flows
- do not waste time micro-optimizing for scale
- avoid unnecessary client-side complexity
- preserve fast load for the phone check-in page

Code quality:
- consistent naming
- delete dead code where confidence is high
- leave comments where they add operational clarity
- no TODO spam
- no UI that is disconnected from the backend

==================================================
EXPECTED OUTPUTS
==================================================

When done, provide:

1. A concise summary of what you changed
2. A list of what was moved to the deferred folder
3. A list of what remains in the MVP
4. Any schema/env changes required
5. Exact local run steps
6. Exact Vercel deployment steps
7. A short “manual smoke test checklist” covering:
   - auth
   - members
   - event creation
   - open check-in
   - phone attendance
   - excuse flow
   - fines flow
   - standing display

==================================================
CONSTRAINTS
==================================================

- Do not ask me to make product decisions unless absolutely necessary.
- Make the best sensible engineering decisions yourself.
- Favor minimalism.
- Favor shipping.
- Do not build new large features.
- Do not redesign the whole stack.
- Do not preserve deferred features in the main navigation or main route registration.
- Do not leave the repo in a partially broken state.

Start by auditing the repo and then make the refactor, when I say "begin".
