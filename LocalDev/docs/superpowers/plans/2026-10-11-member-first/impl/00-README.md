# Member-first GreekOS — directing guide

> **For agentic workers:** you were given this file plus ONE numbered plan. Read "Rules for every agent" and "What to hand back" here, then execute your plan task by task, test first. Everything else here is background you may consult. Steps use checkbox (`- [ ]`) syntax.

**Spec:** `../00-phase-a-audit.md` (what exists, with file:line evidence; the nine reports under `../audit/` go deeper), `../01-phase-b-design.md` (the product design and the binding decisions D1–D16), `../02-phase-c-priorities.md` (milestones and acceptance criteria).
**Written:** 2026-10-11/12 by the orchestrating session (Claude Fable 5.1). Product decisions were made by the user on 2026-10-11 and are recorded in `../01-phase-b-design.md` §0. They are not open for re-litigation; if one turns out to be impossible, stop and report.
**Status:** PLAN ONLY. Phase E (implementation) has not been approved. Nothing below may be executed until the user says so.

**`fn-index.txt`** lists every DB function and the migration that holds its live (last) definition. Regenerated 2026-10-12 after the working tree was restored. If you add or apply migrations, rebuild it from `LocalDev/` with:
```
python3 -c "import re,pathlib;pat=re.compile(r'CREATE\s+OR\s+REPLACE\s+FUNCTION\s+(?:public\.)?([a-z_0-9]+)\s*\(',re.I);L={};C={}
for p in sorted(pathlib.Path('migrations').glob('*.sql')):
  for i,l in enumerate(p.read_text().splitlines(),1):
    for m in pat.finditer(l): f=m.group(1).lower();C[f]=C.get(f,0)+1;L[f]=f'{p.stem}:{i}'
print('\n'.join(f'{f} {L[f]} {C[f]}' for f in sorted(L)))" > docs/superpowers/plans/2026-10-11-member-first/impl/fn-index.txt
```
Known live bodies as of 80e4f8b: `rbac_assign_role` 0164:71 · `rbac_revoke_role` 0206:4 · `ch_import_roster` 0163:4 · `ch_create_chapter` 0164:16 · `tk_approve_task` 0142:371 · `tk_reject_task` 0142 · `tk_update_task_status` 0182:2 · `tr_reject_payment` 0031:120 · `tr_verify_payment_v2` 0166 · `tr_record_payment` 0205 · `tr_bulk_create_invoices` 0169:14 · `an_send_announcement` 0188:1 · `au_set_password` 0191:3.

## Milestones

Implementation agents are **Claude Opus** dispatched by the orchestrator with the Agent tool (never forks), each in its own git worktree with the skills `ponytail`, `superpowers:test-driven-development` and `superpowers:verification-before-completion` named in the dispatch. Every milestone is reviewed by a read-only Opus reviewer before merge. The orchestrator commits and merges.

| M | Plan | Wave | Branch | Lane (backend) | Lane (frontend) | Migrations |
|---|---|---|---|---|---|---|
| M0 | `01-m0-security.md` | 0 | `feat/mf-00-security` | `api/rbac`, `api/auth`, `api/treasury/{api,services}/payments.py`, `api/chapters`, `scripts/seed.py` | none | 0219 |
| M1 | `02-m1-foundation.md` | 1 | `feat/mf-01-foundation` | `api/auth/api/auth.py` + `api/members/api/schemas.py` (`/me` fields only) | everything under `greekos/` | none |
| M2 | `03-m2-me.md` | 2 | `feat/mf-02-me` | `api/members`, `api/memberadmin`, `api/auth` (redeem scope), `api/dependencies.py` | `greekos/src/components/home/**`, `components/me/**`, `lib/profile.ts`, `lib/onboarding.ts`, `hooks/useHome.ts`, `hooks/useProfile.ts`, `adapters.ts` (member fields only) | 0220 |
| M3 | `04-m3-calendar.md` | 2 | `feat/mf-03-calendar` | `api/calendar`, `api/events`, `api/attendance`, `api/tasks/services/tasks.py` + `api/tasks/api/tasks.py` (list filter only) | `components/calendar/**`, `components/events/**`, `components/attendance/**`, `lib/calendar.ts`, `lib/events.ts`, `lib/rollCall.ts`, `hooks/useEvents.ts`, `hooks/useAttendance.ts`, `hooks/useCalendar.ts` | none |
| M4 | `05-m4-jobs.md` | 3 | `feat/mf-04-jobs` | `api/tasks/**` | `components/jobs/**`, `components/ui/JobCard.tsx`, `lib/tasks.ts`, `hooks/useTasks.ts`, `hooks/useJobs.ts`, the job sections of `components/events/EventDetail.tsx` and `components/initiatives/**` | 0221 |
| M5 | `06-m5-treasury.md` | 3 | `feat/mf-05-treasury` | `api/treasury/**`, `api/memberadmin/api/scores.py`, `api/platform/message_templates.py` (treasury templates only), `api/cron/services/outbox_drain.py` (treasury enrichment only) | `components/finance/**`, `components/me/Money*.tsx`, `components/cabin/Treasury.tsx`, `lib/dues.ts`, `lib/money-history.ts`, `hooks/useFinance.ts` | 0222, 0223 |
| M6 | `07-m6-comms.md` | 4 | `feat/mf-06-comms` | `api/announcements/**`, `api/platform/outbox.py`, `api/platform/message_templates.py` (announcement template only) | `components/comms/**`, `components/cabin/Comms.tsx`, `hooks/useAnnouncements.ts`, `hooks/useOutbox.ts`, `lib/composer.ts` | 0224 |
| M7 | `08-m7-roles-legend.md` | 4 | `feat/mf-07-roles` | `api/rbac/**` | `components/roster/**`, `components/MemberRolesPanel.tsx`, `components/me/Roles.tsx`, `lib/roles.ts` | 0225 |
| M8 | `09-m8-cabin-command.md` | 5 | `feat/mf-08-cabin` | `api/nl_controller/**` | `components/cabin/CabinOverview.tsx`, `components/command/**`, `lib/command.ts` | none |

**Waves.** A wave starts only after the previous wave is merged to `main` and the full backend suite plus `npm test && npm run lint && npm run build` are green. Inside a wave every milestone runs in parallel in its own worktree; file lanes are disjoint by construction — stay in yours.

**Shared frontend files** (`greekos/src/api.ts`, `types.ts`, `routes.tsx`): M1 owns them outright in wave 1. From wave 2 on, a milestone may **append** to `api.ts` and `types.ts` inside a block delimited by `// ── M<n> ──` comments, and may **swap exactly one placeholder** in `routes.tsx` for its own component (the line is marked `// M<n> owns this route`). No other edits to those three files.

## Decisions (user, 2026-10-11 — binding)

See `../01-phase-b-design.md` §0 for D1–D16 with consequences. Short form:

| Id | Decision |
|---|---|
| D1 | Path routing with **React Router 7** (`react-router`, pin exact version). Vercel SPA fallback required. |
| D2 | Officer Cabin visible iff the member holds any Cabin permission; each tile gated by its own key. `isOfficerView` retired. |
| D3 | Jobs: `tasks:create` holders **or** supervisor/chair of the parent may create; approver must not hold an active claim; `tasks:review` is a fallback approver on event/initiative jobs. |
| D4 | Remember me = `sessionStorage` (unchecked) vs `localStorage` (checked). 7-day TTL unchanged. |
| D5 | Mobile tabs: Home · Calendar · Jobs · Me. Cabin is the top row inside Me. |
| D6 | RSVP deferred (#118). |
| D7 | Class = `^(Spring|Summer|Fall|Winter) \d{4}$`, self-editable, `roles:assign` holders may edit anyone's. |
| D8 | Composer destinations: feed, email, calendar slot. **No SMS.** |
| D9 | Sent announcements: title/body editable with audit, never re-send. Delete = retract (hide, keep row and outbox). |
| D10 | Chapter signup stops returning the setup code. Full email verification deferred (#119). |
| D11 | Role grants: grant only what you hold (permission subset rule), also for roster import. |
| D12 | Console: Option A parser in `lib/command.ts`; every attempt logged to `command_requests`. |
| D13 | P0 fixes are M0 and ship first. |
| D14 | Reminders: per-member + "remind all" with preview; treasurer gets `standing:remind`; no schedule. |
| D15 | Receipt email enriched and enqueued inside the payment transaction; dues runs email per invoice; rejection reason exposed to the member and in the rejection email. |
| D16 | Proposals out of scope (#120). |

## Rules for every agent

1. **Test first.** Every behaviour change starts with a test that fails on your untouched branch. Backend: real-DB pytest using the existing fixtures (`tests/treasury/conftest.py`: `db_url`, `cursor`, `chapter_id`, `member_factory`, `sb_client`; API tests use the dependency-override client pattern in `tests/initiatives/conftest.py` / `tests/calendar_view/conftest.py`). Frontend: `node:test` with `renderToStaticMarkup` for presence/gating, and plain unit tests for everything in `lib/`. If you cannot make the test fail first, say so in the report.
2. **Stay in your lane.** Change only files under your plan's "Allowed files". If a change seems to need another file, stop that task and report `BLOCKED` with the file and reason. Never edit `Prod/`, `archive/`, another milestone's lane, `.env`, or a migration that already exists on `main`.
3. **No scratch files in the repo.** Use your scratchpad. Do not edit a `conftest.py` unless your plan lists it.
4. **Database.** One shared demo database (Supabase). Never point anything at production. Never run seeds.
   1. Use only the migration numbers assigned to your milestone. Apply with `python3 scripts/migrate_db.py` from `LocalDev/`, then `python3 scripts/migration_checksums.py --update`.
   2. An applied migration is frozen. A file you wrote but have not applied yet may still be edited.
   3. Replace only the DB functions your plan says you own, with `CREATE OR REPLACE FUNCTION`, the exact live signature and return shape. `fn-index.txt` says which migration holds the live body (the last definition wins; verify with `grep -n "FUNCTION.*<name>" migrations/*.sql`). Base your new body on the live body.
   4. Every statement must be safe to run twice. Every NEW function gets `REVOKE ALL ON FUNCTION … FROM PUBLIC;`.
   5. Widening a CHECK catalog (`audit_logs.action`, `message_outbox.event_type`) uses the dynamic rebuild pattern from `0160_outbox_retry_audit.sql` / `0159` §3.
   6. Tests create their own chapter (`chapter_id` fixture) and assert only inside it.
5. **Tests to run.** Backend: `python3 -m pytest <folders your plan names> -q` from `LocalDev/`. Never the full suite (11 min, shared DB) unless your plan says so. Frontend: `npm test && npm run lint && npm run build` in `LocalDev/greekos/`. A test you changed on purpose goes in your report with one line of reason.
6. **Code style.** Match the file you are in. Smallest change that fixes the root cause. No new dependencies beyond the ones your plan names. No drive-by refactors. A deliberate shortcut gets a `// ponytail: <ceiling>, <upgrade path>` comment. Money is integer cents. Permission checks go through `api.rbac` only; the frontend uses `can(permissions, key)` and never role names.
7. **Frontend rules (CLAUDE.md).** A success toast only after the server answers. Nothing on screen that the server did not return — no optimistic rows with fake ids, no default values standing in for a 403. New logic goes in `lib/` with a test. Every interactive control ≥ 44px tall below `sm`. Dialogs use `ui/Modal` or the new `ui/Sheet`.
8. **Git: do not commit, do not stage, do not run any state-changing git command.** At a "Checkpoint", make sure the named tests pass and carry on. The orchestrator commits (no attribution trailers, one commit per logical change).
9. **Secrets.** Never print, log or copy values from `.env`. Never put a code, password or token in a test name, log line or report.
10. **When stuck.** Two failed attempts at the same step → stop that task, report `BLOCKED` with the exact error, continue with the next independent task. Never weaken a test, delete an assertion or widen a guard to get to green.

## What to hand back

End your run with exactly this block as your final message (plain text):

```
MILESTONE: <id and name>
TASKS:
  T<n>: DONE | PARTIAL | BLOCKED — one line
  …
FILES CHANGED: <path>, …
DELETED FILES: <path>, … (or none)
MIGRATIONS: <file> applied yes/no, …
DB FUNCTIONS REPLACED: <name>, …
TESTS: <command> → <final count line, verbatim>
EXISTING TESTS CHANGED: <test id> — why; … (or none)
OUTSIDE MY LANE: anything you noticed in files you were not allowed to touch
HUMAN FOLLOW-UP: … (or none)
SUGGESTED COMMITS: one line per checkpoint: <message> — <files>
```

## Contracts between milestones

- **Migration numbers are assigned above and never traded.** Need one more → `BLOCKED`.
- **Routes** (M1 registers all of these; later milestones only swap the component): `/`, `/login`, `/start`, `/calendar`, `/calendar/:eventId`, `/initiatives`, `/initiatives/:id`, `/jobs`, `/roster`, `/roster/:memberId`, `/me`, `/me/attendance`, `/me/money`, `/me/record`, `/cabin`, `/cabin/attendance/:eventId?`, `/cabin/treasury`, `/cabin/comms`, `/cabin/comms/new`, `/cabin/comms/:id`, `/cabin/roster`, `/cabin/command`.
- **`useMe()`** (M1) returns `{ memberId, name, email, phone, chapterId, chapterName, timezone, roles: string[], permissions: Set<string>, can(key), refreshPermissions() }` from `/api/auth/me` + `/api/rbac/me/permissions`. Everyone consumes it; nobody re-fetches those two endpoints.
- **`RequirePermission`** (M1): `<RequirePermission anyOf={[...]}>` route wrapper → redirects to `/` with a toast on failure. `CABIN_KEYS` (M1, in `lib/session.ts`) decides Cabin visibility: `treasury:payment:verify, treasury:invoice:create, treasury:audit:view, treasury:fines:issue, attendance:override, attendance:excuse:review, attendance:checkin_link:manage, announcements:create, announcements:send, members:invite, roles:assign, nl_controller:execute, calendar:event:update, standing:remind`.
- **`ui/Sheet`** (M1): bottom sheet below `lg`, side panel ≥ `lg`; same props as `Modal` plus `side: 'bottom' | 'right'`.
- **`JobCard`** (M4) is the only job renderer after wave 3. M3 builds `EventDetail` with a `<JobsSection />` slot that M4 fills.
- **Chapter timezone** comes from `useMe().timezone` (M1). Date/time helpers in `lib/time.ts` (M1) take it as a parameter; nobody uses the browser zone for event times after M1.
- **Identity**: `useMe().memberId` is the only "me" check. No module compares display names after its milestone lands.
- **Outbox event types** added: `ANNOUNCEMENT_EMAIL` (M6). **Audit actions** added: `UPDATE_ANNOUNCEMENT`, `RETRACT_ANNOUNCEMENT` (M6). No other catalog widening.
- M1 owns `vercel.json` (SPA fallback). `Prod/vercel.json` is regenerated by `scripts/build_prod.sh` later, on the user's go-ahead, not by any agent.

## Runbook (orchestrator)

For each milestone: create worktree from current `main` (`git worktree add -b <branch> /home/mshik/GuildOS-wt/mf-<id> main`), copy `LocalDev/.env`, `npm ci` in `greekos/` → dispatch Opus with this README + the plan → read the report → dispatch an Opus reviewer (read-only, adversarial, against `git diff` + the plan + the acceptance row in `../02-phase-c-priorities.md`) → fix gaps → commit per suggested checkpoints → `git merge --no-ff` → delete branch + worktree → milestone tests green. After each wave: full backend suite + `greekos` tests, lint and build from merged `main`.
