# Phase C — Prioritization and milestones

Date: 2026-10-11. Inputs: `00-phase-a-audit.md` (evidence), `01-phase-b-design.md` (decisions D1–D16).
Implementation plans: `impl/00-README.md` + `impl/01…09`.

## Priority buckets

| P | Meaning | Items | Milestone |
|---|---|---|---|
| **P0** | security / correctness / serious usability | officer self-grant of treasurer (D11); `/set-password` without current password; evidence upload accepts any type, after review, unbounded; chapter-signup returns the setup code (D10); committed demo admin password on the DB prod points at; revoked session shown as "server down"; fabricated standing/balances on member screens | **M0** (+ M1 for the two UI items) |
| **P1** | core member experience | routing + shell + mobile tabs (D1, D5); personal Home; My Profile + class (D7); onboarding checklist; password toggle + remember me (D4); calendar-first page + event sheet + attendance shortcut; job board with lifecycle guards (D3); paid-invoice history; upload UX | M1, M2, M3, M4, M5 (member half) |
| **P2** | officer productivity | Cabin overview; composer with feed + email + calendar (D8, D9); reminders per member + bulk (D14); receipt/dues/rejection emails (D15); roles legend (+ description corrections); Option A console + attempt log (D12); roll call prefilled from the roster endpoint | M5 (officer half), M6, M7, M8 |
| **P3** | optional / deferred | RSVP (#118), full email verification (#119), proposals (#120), SMS composer destination, scheduled reminders, custom roles, LLM fallback, cache library, credential-change audit rows, login lockout tuning, `login_attempts` pruning, dead-code removals not on a milestone's path | not scheduled |

## Milestones (independently deliverable)

| M | Name | Wave | Depends on | Backend | Migrations | Acceptance (measurable) |
|---|---|---|---|---|---|---|
| M0 | Security fixes | 0 | — | rbac, auth, treasury evidence, chapters, seed | 0219 | An officer POSTing `treasurer` for self gets 403 (test). `/set-password` without `current_password` → 422/403 (test). `text/plain` evidence → 415; evidence on an approved submission → 409; 4th file → 409 (tests). `POST /api/chapters` response has no `setup_code` (test). `seed.py` refuses to run without `SEED_PASSWORD`. |
| M1 | Foundation: routes, shell, nav, session | 1 | M0 | `/api/auth/me` +timezone/phone/roles | none | Every screen has a URL; reload keeps it; back button works; `/cabin/*` 403s redirect; bottom tabs < `lg`, grouped sidebar ≥ `lg`; Vercel fallback serves `index.html` for `/calendar/x`; password toggle on 3 inputs; remember-me storage choice; auth 403 → `/login` with message; Home loader issues no officer-only call for a member (test). |
| M2 | Me: Home, Profile, class, onboarding | 2 | M1 | standing self-read, `PATCH /members/me`, redeem-token scope | 0220 | Home shows real chapter name and real standing for a member; empty tiles absent from the DOM; `/me` edits phone + class with validation (tests); checklist appears for a member missing phone/class and snoozes 7 d; a redeem token cannot reach other routes before a password is set (test). |
| M3 | Calendar & events | 2 | M1 | calendar spanning/location/type id; `?event_id=` on tasks; roster audience/cancel | none | Month and week grids from `/api/calendar/`; agenda feed on phones; `/calendar/:id` opens a sheet < `lg`; edit event works; "Take attendance" lands on `/cabin/attendance/:id` prefilled; multi-day event visible in a window it starts before (test); event times render in chapter tz (test). |
| M4 | Jobs | 3 | M3 | approvals rules, `/status` removal, create gate | 0221 | Claimant cannot approve own job (RPC + API tests); `tasks:review` approves an event job (test); chair without `tasks:create` adds a job to own initiative (test); `/status` gone (test); board default shows only active statuses; one `JobCard` used by Events, Initiatives, Jobs. |
| M5 | Treasury | 3 | M1 | receipt in-tx + payload; dues-run emails; rejection reason; bulk remind; treasurer key | 0222, 0223 | Member History tab lists paid invoices + payments from `/statement`; receipt email has receipt id, method, invoices, remaining (template test); dues run enqueues N `INVOICE_ISSUED` rows deduped (test); member sees rejection reason (test); "Remind all" enqueues one per owing member, none for $0 (test); treasurer holds `standing:remind` (test). |
| M6 | Communications | 4 | M1 | PATCH + retract + email destination | 0224 | Composer creates a draft, previews recipient count, sends to feed + email in one transaction (test); edit of sent announcement changes text, writes audit, enqueues nothing (test); retract hides from members, keeps row + outbox (test); no SMS controls. |
| M7 | Roles legend | 4 | M1 | roles endpoint + descriptions | 0225 | `GET /api/rbac/roles` returns keys + descriptions per role (test); route-walk test asserts every `require_permission` key is seeded and every seeded key is checked or listed as unused; roles panel shows the legend; My Profile shows my roles with text. |
| M8 | Cabin overview + console | 5 | M4, M5, M6, M7 | nl_controller attempt log | none | `/cabin` shows only tiles the member holds (test per key); parser in `lib/command.ts` with table tests; every attempt posted to `command_requests` (test); "extend bid" gone. |

Waves run sequentially; milestones in the same wave run in parallel worktrees with disjoint file lanes (see `impl/00-README.md`).

## Dependency notes

- M1 creates the route table and the shared `useMe()`; M2–M8 fill screens behind routes M1 already registered.
- M4 waits for M3 because the shared `JobCard` replaces the job UI inside the event detail that M3 builds.
- M8 waits for everything because the Cabin overview counts come from endpoints the other milestones wire.
- M0 is independent and ships first; its frontend consequences (403 → login) land in M1.

## Not doing (ponytail)

No cache library, no component library, no design-token system beyond the three existing colours, no storybook, no e2e framework in this initiative (issue #107 tracks e2e). No new backend service. No LLM.
