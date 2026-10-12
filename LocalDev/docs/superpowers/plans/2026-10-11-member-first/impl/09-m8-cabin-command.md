# M8 — Officer Cabin overview and the command console (Option A)

> Read `00-README.md` first. Test first. Stay in your lane. Runs last: the overview counts come from endpoints earlier milestones wired.

**Goal:** `/cabin` shows, per permission, what needs an officer's attention; the console becomes a tested parser in `lib/` with a parsed-action preview and an attempt log (D12). No LLM.
**Spec:** `../01-phase-b-design.md` §3; `../audit/nl-controller.md` §2–§4, Option A.
**Migrations:** none.
**Allowed files:** backend `api/nl_controller/**`, tests under `tests/nl_controller/`; frontend `components/cabin/CabinOverview.tsx`, `components/command/**`, `components/CommandModule.tsx` (delete when replaced), `lib/command.ts`, `components/command-copy.test.ts` (delete/replace), `api.ts`/`types.ts` (M8 block), `routes.tsx` (`/cabin`, `/cabin/command` lines).

## T1 — Backend: attempt log

- [ ] Failing tests `tests/nl_controller/test_attempt_log.py`: `POST /api/nl-controller/commands {input_text, proposed_actions: [...], status}` stores the parsed intent JSON and a status in `{parsed, failed, executed}` (widen the existing status CHECK only if those values are missing — check `0089_nl_controller_tables.sql`; if widening is needed, that is a migration you do **not** have → `BLOCKED`); rows are chapter-scoped; `GET /commands` returns the caller's chapter only; `nl_controller:execute` required.
- [ ] Extend `CommandCreate` with optional `proposed_actions: list[dict]` and `status`. Remove the dead `review` flow? **Keep** the route (frozen paths) but leave its behaviour; just add the fields. Delete the stale `__pycache__/router.cpython-314.pyc`.
- [ ] Checkpoint: `python3 -m pytest tests/nl_controller -q`.

## T2 — `lib/command.ts`

- [ ] Pure `parseCommand(text, members, now, tz) → { ok: true, intent } | { ok: false, error, field? }` with intents `fine | assign_job | schedule_event | announce | approve_excuse`. Rules (audit Option A): verb must lead; names resolve exact → unique prefix → unique substring, otherwise `error: "Al matches Alex Kim, Sal Ortiz — be more specific"`; money `\$?(\d+(?:\.\d{1,2})?)` via `dollarsToCents`, cap $500; `assign … to NAME [by DATE]` with `parseWhen` date, no default date; `schedule … on DATE at TIME [at LOCATION]`, end time clamped to the same day or omitted; `announce: TEXT` only when the text starts with announce/post/send announcement; excuse by unique name and must match a pending excuse (else error). Character class `[\p{L}' -]`.
- [ ] `describeIntent(intent, members) → string` for the preview ("Fine **Cody Jenkins** $25.00 — missing chapter").
- [ ] Table-driven `lib/command.test.ts`: every example in the audit §2 table plus the bug cases (`fine Al $25.50 for late` → 2550 + reason kept; "assign announcement flyers to Zed" with no Zed → name error, not an announcement; `extend bid to X` → unsupported; ambiguous name error; 23:00 start).
- [ ] Checkpoint: `npm test`.

## T3 — Console UI (`/cabin/command`)

- [ ] `components/command/Console.tsx`: input with `<datalist>` of member names and a verb hint line; on submit → `parseCommand` → preview card (`describeIntent`) → Confirm → execute through the **existing** hooks/mutations (`useFinance` fine, `useJobs` create, events create, `useAnnouncements` create+send with `email: false`, excuses review) → log row marked **after** the server answers ("Done" / "Failed: …"). Every attempt (parse ok or not, executed or failed) → `POST /api/nl-controller/commands`. History list loads `GET /commands` (persisted, shared with other officers).
- [ ] Delete `extend bid`, `ATTENDANCE`, the mock terminal chrome, the hard-coded `2026-07-16`, `'Fraternity House'`, `'Brotherhood'` defaults (schedule asks for location/type if absent → preview shows "location: —" and the backend's 422 is surfaced).
- [ ] Tests: `components/console.test.ts` — preview text for a fixture intent; no "extend bid" string; log row text "Done" only present in the post-response state (render twice).
- [ ] Checkpoint: `npm test && npm run lint`.

## T4 — Cabin overview (`/cabin`)

- [ ] `components/cabin/CabinOverview.tsx`: tiles per design §3, each fetched only when the member holds the key and hidden when its count is 0 **and** it has no action (Proof queue with 0 pending still shows "Up to date"). Counts: pending submissions (`GET /payments/submissions?status=pending`), pending excuses (`GET /api/excuses/?status=pending`), jobs awaiting my sign-off (`/api/tasks/?status=done_reported` filtered by `canApprove`), events needing organizers / incomplete (calendar range 30 d), members owing (`/api/treasury/dashboard` or balances), outbox failures (`/outbox?status=failed`), invited not active (`/api/members/` status). Each tile links to its Cabin section.
- [ ] Tests: `cabin-overview.test.ts` — tile present iff key, for each tile.
- [ ] Checkpoint: `npm test && npm run lint && npm run build`.

## Definition of done

M8 acceptance row; `grep -rn "extend bid" greekos/src` empty; `lib/command.test.ts` ≥ 20 cases; parser not inside a component.

## Risks

- Treasurer lacks `nl_controller:execute` (audit §3) — a seed change is **not** in this milestone; note under HUMAN FOLLOW-UP as a product question.
