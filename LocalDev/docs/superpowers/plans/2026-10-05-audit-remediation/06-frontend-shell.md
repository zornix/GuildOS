# 06 · Frontend shell: honest feedback, permissions by key, accessible roll call

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `06-frontend-shell` · **Wave:** 1 · **Agent:** Claude Fable 5.1 (worktree agent) · **Branch:** `fix/audit-06-frontend-shell`
**Findings:** F-045, F-062, F-001, F-066, plus the `isOfficer` → `can()` convention (§11), the check-in deep link (decision D6) and the role panel's ceiling message (F-023 UI)
**Goal:** the app never claims success it has not earned, never drops an action silently, gates on permission keys, and the roll call is usable with a screen reader.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-045, F-062, F-001, F-066 and §11 "Frontend permissions"; decisions D6, D8 in `00-README.md`.

## Global constraints

- Allowed files: everything under `greekos/` EXCEPT the files stream 05 owns: `src/hooks/useFinance.ts`, `src/components/FinanceModule.tsx`, `src/components/finance/**`, `src/lib/transaction.ts`, `src/lib/dues.ts` (and their tests). In `src/App.tsx` do not touch the `FinanceModule` block (stream 05 edits it). In `src/api.ts` do not add or change treasury calls.
- No backend file. No new npm dependency (so no `focus-trap-react`; see Task 3).
- Frontend rules from the 2026-09-07 slice still hold: logic in `src/lib/*.ts` with a sibling `*.test.ts`, components stay dumb, pure functions take `now` as a parameter.
- Checks before every commit: `npm test && npm run lint` in `greekos/`; `npm run build` before the last commit.

## Review focus

1. `syncApi` already rolls back and replaces the toast on an API error (the refuter confirmed it). Do not rewrite it; the bugs are the early success toast and the silent `backendDown` return.
2. A `?checkin=` code in the URL must survive the login screen and be consumed exactly once.
3. Replacing `isOfficer` must not hide a control from someone who holds the specific permission but not `standing:view_all`, or show one to someone who lacks it.
4. Radio-group keyboard behaviour: arrow keys move within a member's row, Tab moves to the next row.
5. Removing packages must leave `npm run build` and `npm test` green from a clean `npm ci`.

---

### Task 1: F-045 — toast after the server answers; never drop silently

**Files:** `greekos/src/hooks/useBackend.ts`, `greekos/src/hooks/useEvents.ts:132-289`, `greekos/src/hooks/useAppData.ts:241-245`, other hooks that call `syncApi`, `greekos/src/lib/sync.ts` + test (new, if you extract the pure part)

- [ ] **Step 1: read `useBackend.ts` fully.** Establish what `syncApi(call, onDone)` returns and when it toasts. Then list every call site: `grep -rn "syncApi(" src`.
- [ ] **Step 2: failing test.** Extract the decision "what message does the user see" into a pure function (`src/lib/sync.ts`): given `{ backendDown: boolean, outcome: 'ok' | 'error', successMessage: string, errorMessage?: string }` it returns the toast text and whether to roll back. Tests: backend down → `"Not saved: the server is unreachable."` and rollback; error → the error message and rollback; ok → the success message, no rollback.
- [ ] **Step 3: implement.** In `useBackend.ts`, the `if (backendDown) return;` branch (line ~21) must roll back the optimistic state and show the "Not saved" toast. Make `syncApi` return a promise that resolves `true` on success, and accept the success message as an argument so the success toast is emitted by `syncApi` after the call resolves. At each call site named in the finding, delete the toast that fires right after `syncApi(...)` and pass its text in instead. Optimistic state updates may stay (they are rolled back on failure).
- [ ] **Step 4: `npm test && npm run lint`; commit** — `fix(greekos): confirm saves only after the server answers`

### Task 2: permissions by key, not `isOfficer`

**Files:** the nine files that still read `isOfficer` (`grep -rn "isOfficer" src`): `App.tsx`, `hooks/useAppData.ts`, `components/DashboardOverview.tsx`, `components/layout/AppShell.tsx`, `components/Sidebar.tsx`, `components/home/WelcomeBanner.tsx`, and tests

- [ ] For each use, decide which permission key the control really needs (look at the route it calls in `api.ts` and that route's `require_permission(...)` in `../api/`), and replace the boolean with `can(permissions, '<key>')`. Where the meaning is "show the officer view of this screen", keep one named helper `isOfficerView(permissions)` (it already exists as `standing:view_all`) and use only that. Put each new gate in the matching `*-access.ts` pure module with a test, following `recruitment-access.test.ts`. `useFinance.ts` is stream 05's; leave its three uses.
- [ ] `npm test && npm run lint`; commit — `refactor(greekos): gate controls on permission keys`

### Task 3: F-062 — roll call is a radio group; modal keeps focus

**Files:** `greekos/src/components/AttendanceModule.tsx:252-270`, `greekos/src/components/ui/Modal.tsx`, `greekos/src/lib/rollCall.ts` + test

- [ ] **Step 1:** each member row's status buttons: wrapper `role="radiogroup"` with `aria-label={`Attendance for ${member.name}`}`; each option `role="radio"`, `aria-checked`, and roving `tabIndex` (checked option, or the first when none, is `0`; the rest `-1`); Left/Right arrows move and select within the row. Put the "next option for this key" logic in `rollCall.ts` (`nextStatus(current, key, options)`) with tests for both arrows, wrap-around and the unmarked state.
- [ ] **Step 2:** `Modal.tsx`: trap Tab inside the dialog with a `keydown` handler (query focusable elements inside the dialog ref; on Tab from the last go to the first, on Shift+Tab from the first go to the last) and restore focus to the opener on close. About fifteen lines; replace the `ponytail: no focus trap` comment.
- [ ] `npm test && npm run lint`; commit — `fix(greekos): accessible roll call and modal focus`

### Task 4: F-001 and F-066 — honest command console, clean manifest

**Files:** `greekos/src/components/CommandModule.tsx`, `greekos/package.json`, `greekos/package-lock.json`, `greekos/src/selfcheck.ts`, `greekos/src/lib/parseWhen.check.ts`, `greekos/src/hooks/useOutbox.ts` and its callers

- [ ] **Step 1:** command console copy: remove every claim of "plain English" / "natural language" / AI. Say what it is: `Type a command. Supported: fine NAME $AMOUNT, …` listing exactly the patterns the parser at lines ~40-100 accepts. Unrecognised input says `Not a supported command. See the list above.` Do not change the parser.
- [ ] **Step 2:** manifest: `"name": "greekos"`; remove `@google/genai`, `dotenv`, `motion` after confirming no import (`grep -rnE "@google/genai|dotenv|from 'motion|from \"motion" src vite.config.* index.html`); keep `vite` only in `devDependencies`. Run `npm install` to update the lockfile, then `rm -rf node_modules && npm ci && npm test && npm run lint && npm run build`.
- [ ] **Step 3:** delete `src/selfcheck.ts` and `src/lib/parseWhen.check.ts` if nothing imports or runs them (check `package.json` scripts and `grep -rn "selfcheck\|parseWhen.check" .`); if `parseWhen.check.ts` holds assertions worth keeping, move them into `src/lib/parseWhen.test.ts` first. Remove `enqueueOutbox` (the no-op at `hooks/useOutbox.ts:9`) and every call to it outside stream 05's files.
- [ ] Commit — `chore(greekos): honest command console copy; drop scaffold dependencies`

### Task 5: check-in deep link (decision D6) and role-panel errors (F-023)

Wave 2 removes the public phone check-in page; `/c/CODE` will redirect to `/?checkin=CODE`. The SPA must pick that up.

**Files:** `greekos/src/App.tsx` (not the FinanceModule block), `greekos/src/lib/session.ts` or a new `src/lib/checkinLink.ts` + test, `greekos/src/components/MemberRolesPanel.tsx`

- [ ] **Step 1: failing test** for a pure `readCheckinCode(search: string): string | null` (accepts 4-8 alphanumerics, upper-cases, returns null otherwise) and `stripCheckinParam(url: string): string`.
- [ ] **Step 2:** on app load, if `readCheckinCode(location.search)` is set: keep it in `sessionStorage` across the login screen; once a member is logged in, call the existing `api.checkInWithCode(code)`, toast `Checked in to EVENT.` or the server's error, then clear the stored code and `history.replaceState` the param away.
- [ ] **Step 2b:** after wave 2, `GET /api/events/{id}/checkin-link` returns `{event_id, active, expires_at}` with no `short_code` and no `url` for members who cannot manage check-in. Make `CheckInLinkDto.short_code` and `url` optional in `api.ts`, fix the adapter, and make Home show the door-code input whenever a link is active (not only when a code is present). Officer views that display the code keep working. Add an adapter test for the code-less shape.
- [ ] **Step 3:** `MemberRolesPanel.tsx:40-47`: when assign or revoke fails, revert the checkbox and show the server's message (the server now answers 403 "Only an admin can grant or revoke that role" and 409 "The chapter must keep at least one admin. Make someone else an admin first.").
- [ ] `npm test && npm run lint && npm run build`; commit — `feat(greekos): check in from a /?checkin= link; show role-change errors`

### Task 6: browser check

- [ ] Follow README "Browser check": officer and plain member, desktop and phone width. Stop the backend and confirm an edit shows "Not saved". Open `/?checkin=ABC123` logged out, log in, and confirm one check-in attempt is made. Tab through a roll-call row with a screen reader or the accessibility tree.

## Report

Finish with the report block from `00-README.md` ("What to hand back").
