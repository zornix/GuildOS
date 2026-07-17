# Implementation plan — e2e suite repair, dev-script paths, lint fix

Date: 2026-07-11
Order: independent of the architecture-review series, but should land **before**
`imp-hygiene.md` &co. are verified — those plans require `npm run test:e2e`
green, which is impossible today. (If `imp-hygiene.md` step 8 has already
deleted the `"member can pay a fine"` test, the fines.spec numbers below shift
by one; rebase, don't stop.)
Scope: three pre-existing breakages, none introduced by recent work. No product
behavior changes except one dev-tooling line removed from `layout.tsx` and a
seeded demo password for officers.

Decisions are settled here; the implementer executes as written and reports
drift instead of improvising.

## Root causes (verified 2026-07-11, file:line evidence)

1. **E2e: 26/28 tests fail.** `POST /api/auth/login`
   (`api/auth/api/auth.py:24-65`) now branches on role: officers with a
   `password_hash` get `403 {"code": "PASSWORD_REQUIRED"}` (`auth.py:47-52`);
   officers **without** one log in but get `password_setup_required: true`
   (`auth.py:62-63`), which the frontend routes to a Set-Password screen
   (`fratos/hooks/use-auth.tsx:91-92`). Plain members still log in email-only.
   `scripts/seed.py` never sets `password_hash` (`seed.py:202-207`), so the
   seeded officer `jake@tke.org` always lands on Set-Password — the e2e fixture
   `loginAs` (`fratos/e2e/fixtures/auth.ts:7-12`) fills email only and waits for
   `text=Dashboard`, which never appears. All 14 officer-fixture tests die
   there. On top of that, `auth.spec.ts:7,31` assert the stale copy
   `"Sign in with your chapter email"` (the app now renders `"Sign in"` —
   `components/modules/auth/login-form.tsx:39`), `auth.spec.ts:22` asserts
   `"No active member with that email"` (backend says "No active member
   **found** with that email", `auth.py:43`), and several specs assert seed
   data that doesn't exist (e.g. `members.spec.ts:8-9` expects "Alex Johnson" /
   "Marcus Lee"; seed creates "Alex Rivera" / "Marcus Johnson",
   `seed.py:40-49`).
2. **`npm run dev` is broken.** `../local-dev/` was renamed to
   `../local-dev-scripts/` (scripts live at
   `/home/mshi/GuildOS/local-dev-scripts/scripts/`), but `package.json:4-9`
   still points at the old path. Stale docs: `LocalDev/CLAUDE.md:22`,
   `docs/ARCHITECTURE.md:41`, root `CLAUDE.md:5`.
3. **`npm run lint` fails.** The `impeccable-live` dev-tooling block —
   `<script src="http://localhost:8400/live.js">` between
   `{/* impeccable-live-start */}` / `{/* impeccable-live-end */}` markers —
   was accidentally committed into `fratos/app/layout.tsx:30-32` (commit
   `d5cda1a`) and trips `@next/next/no-sync-scripts`. The impeccable tool
   injects/removes this block itself at runtime; it must not be committed.

## Settled decisions

- **D1 — Officer e2e login uses the real two-step UI flow, not `dev-login`.**
  Seed a known bcrypt password for officers; the fixture submits email, waits
  for the revealed password field, submits again. This exercises the actual
  `PASSWORD_REQUIRED` product path. The passwordless `POST /api/auth/dev-login`
  stays gated (`DEV_AUTH_BYPASS`, `auth.py:71-72`) and is not used by e2e.
- **D2 — Demo officer password is the constant `demo-officer-pw`** (satisfies
  the min-8 validator, `api/auth/api/schemas.py:9-17`). Defined once in
  `scripts/seed.py` and mirrored in `fratos/e2e/fixtures/auth.ts` with a
  cross-referencing comment in both places. No new env var.
- **D3 — Specs conform to `seed.py`, never the reverse.** Seed data is shared
  with local dev; tests adapt to it. Where seed creates near-duplicate rows
  (two events contain "Chapter Meeting"), make selectors strict-mode-safe
  (more specific text or `.first()`), don't rename seed rows.
- **D4 — E2e runs with the login form visible.** The dev-auth bypass
  (`fratos/lib/dev-auth.ts:3-5`, enabled by `fratos/.env.local`'s
  `NEXT_PUBLIC_DEV_AUTH_BYPASS=1`) auto-logs-in and never renders the form, so
  it is mutually exclusive with the auth specs. Pin it off for e2e via
  Playwright's `webServer.env` (`NEXT_PUBLIC_DEV_AUTH_BYPASS: "0"`) — a real
  environment variable beats `.env.local` in Next. Leave `.env.local` alone
  for interactive dev.
- **D5 — The `impeccable-live` block is removed from source, not
  lint-suppressed.** No `eslint-disable`, no `next/script` rewrite; a
  `localhost:8400` script has no business in a build. The tool re-injects it
  locally when running.
- **D6 — Root `CLAUDE.md` stops calling `local-dev` a sibling copy.** It's
  shared dev tooling (`local-dev-scripts/`), not a copy of the product.
- **D7 — Three separate commits**, one per problem, in the order below
  (2 → 3 → 1), because the script-path fix is needed to bring the stack up for
  e2e verification. No Claude attribution trailers on any commit.

## Steps

### Problem 2 — script paths (commit 1)

1. `LocalDev/package.json:4-9`: replace all five `../local-dev/scripts/` with
   `../local-dev-scripts/scripts/` (`dev`, `dev:seed`, `dev:docker`,
   `migrate`, `seed`).
2. `LocalDev/CLAUDE.md:22`: same path correction.
3. `LocalDev/docs/ARCHITECTURE.md:41`: same path correction.
4. Root `CLAUDE.md:5`: remove `local-dev/` from the sibling-copies list and
   mention `local-dev-scripts/` as shared dev-runner tooling (one clause, keep
   it minimal per D6).

Commit: `fix(dev): point npm scripts and docs at renamed local-dev-scripts/`

### Problem 3 — lint (commit 2)

5. `fratos/app/layout.tsx:30-32`: delete the injected block; the line becomes
   `<body className="min-h-full flex flex-col">{children}</body>`.

Commit: `fix(frontend): remove committed impeccable-live dev script from layout`

### Problem 1 — e2e suite (commit 3)

6. `scripts/seed.py`: define `OFFICER_DEMO_PASSWORD = "demo-officer-pw"` (with
   a comment pointing at `fratos/e2e/fixtures/auth.ts`); when inserting a
   member with `role == "officer"`, set
   `password_hash = bcrypt.hashpw(OFFICER_DEMO_PASSWORD.encode("utf-8"),
   bcrypt.gensalt()).decode("utf-8")` (same recipe as
   `scripts/set_officer_password.py:45`). `import bcrypt` at top.
7. `fratos/e2e/fixtures/auth.ts`: extend `loginAs(page, email, password?)`:
   fill `input[type="email"]`, click `Sign In`; when `password` is given, wait
   for `input[type="password"]` to appear (the `PASSWORD_REQUIRED` reveal,
   `login-form.tsx:48-57`), fill it, click `Sign In` again; then the existing
   `waitForSelector("text=Dashboard")`. `loginAsOfficer` passes
   `"demo-officer-pw"` (comment pointing at `scripts/seed.py`);
   `loginAsMember` stays email-only.
8. `fratos/playwright.config.ts`: add
   `webServer.env = { NEXT_PUBLIC_DEV_AUTH_BYPASS: "0" }` (D4).
9. `fratos/e2e/auth.spec.ts` — rewrite the four tests against current reality:
   - Login-screen copy assertions (`:7`, `:31`): expect the subtitle
     `"Sign in"`. Use an exact/scoped locator so it doesn't collide with the
     `Sign In` button under strict mode.
   - "valid email navigates to dashboard": split into the two real flows —
     member email-only login reaches Dashboard; officer login gets the
     `"Officers must enter a password"` reveal (`use-auth.tsx:100-102`), then
     reaches Dashboard after submitting the password.
   - Invalid-email test (`:22`): expect
     `"No active member found with that email"`.
   - Logout test: log in via the member flow (or officer helper), then assert
     return to the login screen using the corrected `"Sign in"` copy.
10. Data-assertion sweep across `checkin/events/excuses/fines/members.spec.ts`:
    update every assertion referencing seeded entities to what `seed.py`
    actually creates (known mismatches: `members.spec.ts:8-9` "Alex Johnson" →
    "Alex Rivera", "Marcus Lee" → "Marcus Johnson"; `fines.spec.ts:7`
    "Brotherhood Dinner" → a fine reason seed really inserts — read
    `seed.py:51-97` and use the real values; audit the rest the same way).
    Make `text=Chapter Meeting` style selectors strict-mode-safe (D3), e.g.
    `checkin.spec.ts:23`.
11. Run the full suite (see Verification) and fix any remaining
    assertion-vs-seed drift the static sweep missed — same D3 rule. If a test
    fails because a *feature* is missing (not data drift), stop and report;
    don't delete or skip tests beyond what `imp-hygiene.md` already settles.

Commit: `fix(e2e): password login for officers, align specs with live copy and seed data`

## Verification

1. After commit 1: `npm run seed` then `npm run dev` (from `LocalDev/`) seeds
   the Supabase demo pooler and brings up migrations + FastAPI (8001) + Next
   (3000) with no path errors. (Docker mode was removed per ADR-0002 — there is
   no `dev:seed`/`dev:docker`; e2e runs against the seeded Supabase demo DB.)
2. After commit 2: `cd fratos && npm run lint` — zero errors.
3. After commit 3, with the seeded stack running:
   `npm run test:e2e` from `LocalDev/` — 28/28 green (27/27 if
   `imp-hygiene.md` step 8 landed first). Playwright reuses the running
   server on 3000 (`reuseExistingServer: !CI`).
4. `python3 -m pytest tests/` still green (seed change touches no API code,
   but the seeded `password_hash` must not break any auth tests).
5. Sanity grep: `grep -rn "local-dev/scripts" .. --include="*.json"
   --include="*.md" | grep -v local-dev-scripts | grep -v node_modules`
   returns nothing; `grep -rn "impeccable" fratos/app` returns nothing.
