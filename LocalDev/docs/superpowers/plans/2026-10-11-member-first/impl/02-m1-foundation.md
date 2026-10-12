# M1 — Foundation: routes, shell, navigation, session

> Read `00-README.md` first. Test first. You own everything under `greekos/` in this wave plus the `/me` response fields.

**Goal:** every screen has a URL (D1); grouped desktop sidebar and mobile bottom tabs (D5); Officer Cabin visibility by permission (D2); per-route data loading; password toggle; remember-me (D4); honest session expiry. Existing modules keep working behind their new routes; redesigning their insides is later milestones' work.
**Spec:** `../01-phase-b-design.md` §1, §9; `../audit/frontend-shell.md` §1–§3, §5, §9.
**Migrations:** none. **New dependency:** `react-router` 7.x (pin the exact resolved version). Nothing else.
**Allowed files:** `greekos/**`, `vercel.json`, `api/auth/api/auth.py` (`get_me` only), `api/dependencies.py` (select `chapters.timezone` only), `api/members/api/schemas.py` (`UserProfile` only), `tests/auth/test_me_profile.py`.

## T1 — `/api/auth/me` carries what the shell needs

- [ ] Failing test `tests/auth/test_me_profile.py`: `/me` returns `timezone` (from `chapters.timezone`, default `America/Los_Angeles`), `phone` (may be null) and `roles` (sorted `member_roles` keys).
- [ ] Extend `UserProfile` + `get_me`. `get_current_user` already joins `chapters`; add `timezone` to that select if missing. Roles via `api.rbac.db.repositories.member_roles` (read-only use).
- [ ] Checkpoint: `python3 -m pytest tests/auth -q`.

## T2 — Router and route table

- [ ] `npm i react-router@7` in `greekos/` (pin exact). Remove `autoprefixer` and `esbuild` devDependencies (unused; audit §12) and `metadata.json`; delete the `@` alias from `vite.config.ts`/`tsconfig.json` (never imported).
- [ ] `src/routes.tsx`: `createBrowserRouter` with the full route list from the README contract. Each route renders the **existing** module for now (e.g. `/calendar` → `EventsBar` + `CalendarModule`/`EventsModule`, `/jobs` → `TasksModule`, `/me/money` and `/cabin/treasury` → `FinanceModule`, `/cabin/attendance/:eventId?` → `AttendanceModule`, `/cabin/comms` → `OutboxModule`, `/cabin/command` → `CommandModule`, `/me` → a minimal page showing name/email/roles from `useMe()`). Mark later-milestone placeholders with `// M<n> owns this route`.
- [ ] `lib/session.ts`: add `CABIN_KEYS` (README contract) and `hasAnyCabinKey(perms)`. Delete `isOfficerView`; replace its presentation uses (`Sidebar.tsx:77`, `AppShell.tsx:93`, `App.tsx:83`) with `hasAnyCabinKey` for the badge ("Cabin access") and with the specific key for Home's officer-only bits. Update `shell-access.test.ts` / `home-access.test.ts` accordingly (say why in the report).
- [ ] `components/layout/RequirePermission.tsx`: `anyOf: string[]` → renders `Outlet`/children or `Navigate to="/"` + toast "You don't have access to that page". Wrap `/cabin/*` (with `CABIN_KEYS`) and each Cabin child with its own keys (treasury: `treasury:payment:verify, treasury:invoice:create, treasury:audit:view, treasury:fines:issue`; attendance: `attendance:override, attendance:excuse:review, attendance:checkin_link:manage`; comms: `announcements:create, announcements:send`; roster: `members:invite, roles:assign`; command: `nl_controller:execute`).
- [ ] Tests (`src/lib/session.test.ts`, `src/components/require-permission.test.ts`): `hasAnyCabinKey` truth table; `RequirePermission` renders children with a matching key and the redirect marker without.
- [ ] Door-code deep link: keep the `?checkin=CODE` handling on `/` exactly as today (`App.tsx:29-32,55-62`, `lib/checkinLink.ts`).
- [ ] Checkpoint: `npm test && npm run lint`.

## T3 — `useMe()` and per-route loading

- [ ] `hooks/useMe.ts`: loads `/api/auth/me` + `/api/rbac/me/permissions` once (context provider in `main.tsx`), exposes the README shape plus `refreshPermissions()` (replaces `refreshOwnPermissions`). Logout clears it.
- [ ] Dismantle the 15-call startup load in `useAppData.ts:118-193`: each route's module fetches what it shows (lift the existing domain hooks to fetch on mount; `useOutbox` already does). Home (`/`) fetches: calendar range (next 14 d via `GET /api/calendar/?start&end`), `/api/tasks/`, `/api/announcements/`, `/api/contribution/me`, `/api/treasury/members/{me}/dashboard`. **No call that is known to 403 for the caller**: gate `/api/standing/`, `/api/memberadmin/scores`, `/api/treasury/dashboard` behind `can()` before calling. Remove the fallbacks that turn a 403 into fake data (`adapters.ts:69,78` defaults for standing/balance → render "—" / hide instead).
- [ ] `lib/time.ts`: `formatEventStart(date, time, timezone)`, `hasStarted(event, timezone, now)`, `isWithin36Hours(...)` taking the chapter timezone (`Intl.DateTimeFormat` with `timeZone`; no library). Port `formatters.ts:17-28` callers. Tests with a fixed `now` and two zones.
- [ ] Test: a Home loader test asserts no officer-only call is issued for a permission set `[]`.
- [ ] Checkpoint: `npm test && npm run lint`.

## T4 — Shell: grouped sidebar, bottom tabs, Sheet

- [ ] `config/navigation.ts`: `NAV_GROUPS` = Home · Chapter (Calendar, Initiatives, Jobs, Roster) · My Activity (Attendance, Money, Record, Profile) · Officer Cabin (Overview, Attendance, Treasury, Comms, Roster, Command — each with `permission: string[]`). `MOBILE_TABS` = Home `/`, Calendar `/calendar`, Jobs `/jobs`, Me `/me`.
- [ ] `Sidebar.tsx` (≥ `lg`): grouped `NavLink`s, active state from the router, icons at `lg`, labels at `xl`. Cabin group rendered only when `hasAnyCabinKey`; items filtered by `can()`.
- [ ] `components/layout/BottomTabs.tsx` (< `lg`): 4 `NavLink`s, ≥ 44px targets, `padding-bottom: env(safe-area-inset-bottom)`, `aria-current`. Remove the hamburger drawer. The "Me" tab's page lists the My Activity links and, when `hasAnyCabinKey`, an "Officer Cabin" row at the top (D5).
- [ ] `AppShell.tsx`: header shows the current route title (`handle.title`) and the real chapter name from `useMe()`; `main` becomes `max-w-screen-2xl` with `px-4 sm:px-6`; sidebar + `BottomTabs` by breakpoint; render a skeleton line instead of children while `useMe` loads.
- [ ] `ui/Sheet.tsx`: wraps `Modal`'s focus/escape/overlay logic; `side='bottom'` below `lg` (slides up, `max-h-[90dvh]`), `side='right'` at `lg+`.
- [ ] `ui/Button.tsx` and `ui/Input.tsx`: the drifting class strings consolidated (`primary | secondary | danger | ghost`; `min-h-11 sm:min-h-0`). Port **only** `LoginScreen`, `OnboardingScreen`, `ConfirmDialog` in this milestone.
- [ ] Remove the no-op `animate-in …` classes (`Modal.tsx:74`, `AppShell.tsx:46`); use a 150 ms CSS `transition`.
- [ ] `index.html`: `<meta name="theme-color">`, `apple-mobile-web-app-capable`. No manifest (YAGNI).
- [ ] Tests: `shell-access.test.ts` → Cabin group present iff a cabin key; `BottomTabs` renders 4 links; header shows the chapter name passed in.
- [ ] Checkpoint: `npm test && npm run lint && npm run build`.

## T5 — Vercel SPA fallback

- [ ] `vercel.json` routes: keep the header rule, `/api/(.*)`, `/c/(.*)`; then `{ "handle": "filesystem" }`; then `{ "src": "/(.*)", "dest": "/greekos/index.html" }`. Verify with `npm run build` and `npx vercel dev` if available; otherwise document the manual check in the report. `Prod/vercel.json` is **not** yours.

## T6 — Login: password toggle, remember me, honest expiry

- [ ] `LoginScreen.tsx`: each of the three `type="password"` inputs gets a Show/Hide button (`type="button"`, `aria-pressed`, `aria-label="Show password"`), toggling `type` only; `autocomplete` attributes unchanged. Test: markup contains the toggle for all three steps.
- [ ] Remember me (D4): checkbox "Keep me signed in on this device" default **checked**. `api.ts`: a `tokenStore` with `set(token, persist)`, `get()` (localStorage then sessionStorage), `clear()` (both). `authPost` takes the choice from the form; redeem/set-password reuse the last choice (default session until the password is set). Tests in `lib/auth.test.ts` with stubbed storages.
- [ ] Expiry: `api.ts:169,201` — treat 401 **and** auth-403 (`detail` starting "Session no longer valid" or "No active membership") as `AuthRequiredError`; clear the store; navigate to `/login?reason=expired`; `LoginScreen` shows "Your session ended. Sign in again." `sync.ts:44-47` maps `AuthRequiredError` to that message instead of "server refused". Tests for both paths.
- [ ] Remove the misleading `retry` parameter in `request()` and the unused generic `api.get/post/put/patch/del`.
- [ ] Checkpoint: `npm test && npm run lint && npm run build`.

## Responsive behaviour (acceptance)

- < `lg`: bottom tabs, no sidebar, header with title; tables keep `overflow-x-auto` for now.
- ≥ `lg`: icon sidebar; ≥ `xl`: labelled sidebar; content to `2xl`.

## Rollout / backward compatibility

There were no URLs before, so no bookmarks break. `?checkin=` still works. All existing modules render unchanged inside routes; no endpoint changes except the additive `/me` fields.

## Definition of done

M1 acceptance row in `../02-phase-c-priorities.md`; `npm run build` passes; every module reachable at its route by a member and by an admin; `grep -rn isOfficerView greekos/src` returns nothing.

## Risks

- React Router 7 import paths (`react-router` single package). Check the installed version's docs, not memory.
- Dismantling `useAppData` touches every module's props. Keep the module prop shapes identical and move only the *loading* into per-route wrappers to limit the diff.
