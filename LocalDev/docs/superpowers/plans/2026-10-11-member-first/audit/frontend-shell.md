# Frontend shell audit — greekos (2026-10-11)

Scope: app shell, navigation, responsive layout, Member Home, login, onboarding, roster/profile.
All paths are relative to `LocalDev/greekos/` unless stated otherwise. Read-only audit; `npm test` was run: 151/151 pass across 29 test files.
Tags: **FACT** = seen in code. **INF** = inference.

---

## 1. Routing and navigation

- **FACT** There is no router library. `package.json:14-19` lists only react, react-dom, lucide-react, vite and tailwind.
- **FACT** The view is plain component state: `const [activeTab, setActiveTab] = useState('dashboard')` (`src/App.tsx:42`). The JSX picks a view with `activeTab === 'x' && <Module/>` (`src/App.tsx:76-250`).
- **FACT** The Events tab also holds a second level of state in `useEventsChrome` (view `calendar|list`, type filter, create-open, selected event) (`src/hooks/useEventsChrome.ts:9-29`).
- **FACT** Auth gating is state too: `authed` starts as `!!localStorage.getItem('g_token')` (`src/App.tsx:25`). Onboarding is a boolean (`src/App.tsx:26,33-37`).
- **FACT** The only URL handling is the `?checkin=CODE` door-code link. The code is read (`src/App.tsx:30`), parked in sessionStorage (`src/App.tsx:31`), and stripped with `history.replaceState` after use (`src/App.tsx:60`; `src/lib/checkinLink.ts`).
- **FACT** Nothing calls `pushState` and nothing listens for `popstate` or `hashchange`. The browser Back button leaves the app. A reload always lands on Home.
- **FACT** The Vercel route `{"src": "/(.*)", "dest": "/greekos/$1"}` (`LocalDev/vercel.json:35`) has no SPA fallback to `index.html`.
- **INF** Path-based deep links such as `/events/123` would 404 on Vercel today. Hash routing, or adding a fallback route, would be needed.
- **Deep-linking today: not possible**, except the door-code query parameter.
- **FACT** Only the sidebar applies nav permission gating. `App.tsx` renders whichever `activeTab` is set with no guard; for example, `outbox` at `src/App.tsx:241`. **INF** This is low risk today, because only the sidebar and Home's fixed `onNavigateTab` targets set the tab. It becomes a real hole once URLs drive the tab.

## 2. Shell layout and responsiveness

- **FACT** `AppShell` is a flex row: Sidebar plus a column holding a sticky header and `<main>` (`src/components/layout/AppShell.tsx:43-112`).
- **Sidebar** (`src/components/Sidebar.tsx:49-91`):
  - **FACT** It is a fixed `w-64 h-screen` off-canvas drawer below `lg` (`-translate-x-full`). At `lg` and above it becomes `lg:sticky lg:translate-x-0` (`:51-52`).
  - **FACT** Tapping a nav row closes the drawer (`:32`). Escape closes it (`AppShell.tsx:33-40`). Tapping the overlay closes it (`AppShell.tsx:56-62`).
  - **FACT** The closed drawer is only translated off-screen. It is never `hidden` or `inert`, and the menu button has no `aria-expanded` or `aria-controls` (`AppShell.tsx:77-83`). **INF** On mobile, keyboard and screen-reader users can still tab into the off-screen nav, and there is no focus trap.
  - **INF** `h-screen` (100vh) on iOS Safari can hide the bottom of the drawer (the Sign out button) behind the browser toolbar. `Modal` already uses `100dvh`; the sidebar does not.
  - **FACT** The footer shows the member name plus "Officer"/"Member", taken from `isOfficerView` (`:72-79`).
- **Header** (`AppShell.tsx:75-96`):
  - **FACT** It holds a hamburger (`lg:hidden`), the static text "GreekOS", and an avatar chip with initials, name and Officer/Member.
  - **FACT** There is no page title, no chapter name, no search and no notifications.
- **Container**: **FACT** `<main className="flex-1 p-4 sm:p-6 max-w-7xl w-full mx-auto space-y-6">` (`AppShell.tsx:98`) is the one container cap (1280px). There are no `xl:` or `2xl:` breakpoints anywhere in `src`.
- **Breakpoint usage**: **FACT** in `.tsx` files, `sm:` appears 155 times, `md:` 10 times, `lg:` 17 times, and `xl:` never. Home uses `grid-cols-1 lg:grid-cols-2` (`src/components/DashboardOverview.tsx:115`). `MyRecord` uses `grid-cols-2 sm:grid-cols-3 lg:grid-cols-6` (`src/components/home/MyRecord.tsx:49`).
- **Mobile-specific UI**:
  - **FACT** The only mobile-specific pieces are the hamburger drawer, `min-h-11` (44px) touch targets on most buttons, and tables that hide columns (`hidden sm:table-cell` / `md:table-cell`, `src/components/RosterModule.tsx:110-115`) inside `overflow-x-auto`.
  - **FACT** There is no bottom nav, no sheets or bottom drawers, no swipe and no safe-area insets.
  - **FACT** `index.html` has the viewport meta only. There is no `theme-color`, manifest or icons (`index.html:1-12`).
- **Toast**: **FACT** a single fixed bottom-right toast (`AppShell.tsx:44-54`) with `aria-live`. It stays until dismissed or replaced (`src/hooks/useToast.ts:3-9`).
- **Dialogs**: **FACT** every modal goes through `ui/Modal`, which is a centered overlay; `fixed inset-0` occurs only in Modal and in the drawer scrim. **INF** On phones the modal is a centered card, not a bottom sheet.
- **Loading flash**: **FACT** `children` render while `loading` is true (`AppShell.tsx:99-109`). Home therefore briefly shows "Welcome back, " with no name and the empty states ("No upcoming events.") before the data arrives.

## 3. Shared UI primitives (`src/components/ui/`)

| Primitive | Notes | Reuse |
|---|---|---|
| `Card.tsx` | A white rounded bordered div; padding stays with the caller. Carries a stale `key?` prop hack, whose comment says "no @types/react" (`Card.tsx:7-8`), yet `@types/react` is installed (`package.json:23`). | Used by about 12 modules (FACT) |
| `Modal.tsx` | Solid. It has a focus-on-mount panel, a Tab trap, Escape and overlay close, focus return, `aria-modal` and `aria-labelledby`, and `max-h-[calc(100dvh-2rem)]` (`Modal.tsx:21-89`). | Every dialog in the app uses it (FACT) |
| `ConfirmDialog.tsx` | Title, body, Cancel/Confirm, and a danger tone; built on Modal. | Home, Events, Attendance, Initiatives… |
| `DoorCodeField` (`home/`) | Compact and large variants of the door-code input. | Home and Attendance |

- **FACT** There is **no** Button, Input, Field, Badge, Table, Tabs, Sheet, EmptyState or Skeleton primitive. Button styles are inline strings that drift:
  - `bg-navy hover:bg-slate-800 text-gold` (`ConfirmDialog.tsx:25`)
  - `bg-navy hover:bg-[#16304f] text-white` (`LoginScreen.tsx:17`)
  - `bg-navy hover:bg-[#1e2d42] text-white` (`MyRecord.tsx:63`)
- **FACT** Input class strings are copied between `LoginScreen.tsx:13-14` and `OnboardingScreen.tsx:43-44`.
- **FACT** The `animate-in fade-in zoom-in slide-in-from-bottom-5` classes (`Modal.tsx:74`, `AppShell.tsx:46`) need `tailwindcss-animate` / `tw-animate-css`. Neither is installed or imported (`src/index.css:1-2` imports only `tailwindcss`), so these classes are no-ops.
- **FACT** The theme tokens are only `navy`, `gold`, `gold-muted` and three fonts (`src/index.css:4-12`). There is no dark mode.
- **FACT** There is a global `:focus-visible` gold outline and reduced-motion handling (`src/index.css:14-28`). The basic accessibility is good.

## 4. Member Home today

`DashboardOverview` is rendered at `src/App.tsx:76-97`. All of its data comes from the single `useAppData` startup load. Home makes no calls of its own, except the SMS opt-in POST.

| Block (order) | Rendered when | Data source (endpoint) | Empty state |
|---|---|---|---|
| `WelcomeBanner` (`DashboardOverview.tsx:78-91`) | Always | Role and standing come from the roster row (`GET /api/members/` plus officer-only `GET /api/standing/`). The record line uses `GET /api/contribution/me`. Balance uses `GET /api/treasury/members/{me}/dashboard`. The live door uses `GET /api/events/` plus `/api/events/upcoming-details`. | The balance line is hidden while unknown (`src/lib/balance.ts:31-33`). |
| ↳ Balance link → Treasury | `balanceLine` is non-empty (`WelcomeBanner.tsx:63-72`) | Member treasury dashboard | — |
| ↳ "Schedule event" | `calendar:event:create` (`WelcomeBanner.tsx:74-83`) | — | — |
| ↳ Door code entry or "No door open" | `!officerView` (`WelcomeBanner.tsx:87-107`) | `liveDoorEvent` = earliest event today or later with `checkInLinkActive` (`src/lib/events.ts:15-19`). POST `/api/attendance/checkin/{code}`. | The "No door open right now · Attendance →" link |
| `MyRecord` (`DashboardOverview.tsx:93`) | Always | `GET /api/contribution/me`: six counts plus a copyable résumé line (`MyRecord.tsx:18-27,15`) | All zeros when the load fails (`useAppData.ts:145-148`) |
| `SmsConsentCard` (`DashboardOverview.tsx:97`) | `currentMember` is found in the roster | `sms_consent` on own row. Opt-in: POST `/api/members/me/sms-consent`. There is no opt-out; STOP is the opt-out (`SmsConsentCard.tsx:7-12`). | — |
| Pending sign-off nudge (`DashboardOverview.tsx:101-113`) | `officerView && jobs with 'Done Reported'` | Event jobs from `GET /api/tasks/` | Hidden |
| Upcoming events tile (`:117-153`) | Always | `GET /api/events/`, filtered to today or later, first 3 (`:72`, `TILE_LIMIT=3` at `:39`). Includes a "Volunteer as organizer" button when there are 0 organizers. | "No upcoming events." |
| Announcements tile (`:156-178`) | Always | `GET /api/announcements/`, first 3. A delete X is shown with `announcements:create`. Its "Calendar →" link goes to the `events` tab. | "No announcements yet." |
| Jobs tile (`:181-193`) | Always | `GET /api/tasks/`. It shows **all open chapter jobs**, not the member's own (`:74`). | "No jobs yet." (misleading copy when jobs exist but all are done) |
| Initiatives tile (`:196-209`) | Always | `GET /api/initiatives/`, first 3 | "No initiatives yet." |

Personalization problems:
- **FACT** The banner hardcodes the chapter: `Alpha Chapter &bull; {memberCount} members` (`WelcomeBanner.tsx:52`). `chapterName` is already loaded (`useAppData.ts:169`) but is not passed in.
- **FACT** The banner has made-up fallbacks: role `'Brother'` and standing `'Good Standing'` (`WelcomeBanner.tsx:44,46`).
- **FACT** Standing is unreachable for members. `GET /api/standing/` requires `standing:view_all` (`LocalDev/api/memberadmin/api/standing.py:12`), and a member gets a 403 that is swallowed into `[]` (`useAppData.ts:128`). `adaptMembers` then defaults every member to `'Good Standing'` (`src/adapters.ts:78`).
  - So **every member always sees "Good Standing" on Home, whatever their real standing**. This breaks the "Nothing on screen that the server did not return" rule (`LocalDev/CLAUDE.md`, Frontend rules).
- **FACT** The role badge comes from display-only `members.role`, mapped to `Officer` or `Active Member` (`src/adapters.ts:70`).
- **FACT** There is no "my jobs", "my events / RSVPs", "my excuses" or "my fines" tile. Home's personal pieces are the banner, MyRecord, the balance line and SMS.
- **FACT** The record counts appear twice: once in the banner line (`WelcomeBanner.tsx:31-35,57-59`) and again in MyRecord (`MyRecord.tsx:18-27`).

## 5. Login and session

- **FACT** `LoginScreen` has three steps: `signin | code | password` (`src/lib/auth.ts:10`; `LoginScreen.tsx:119-203`).
- **FACT** The password field is `<input type="password" autoComplete="current-password">` (`LoginScreen.tsx:125`). Email uses `autoComplete="username"` (`:103`). The new-password fields use `autoComplete="new-password"` (`:188,194`). The code field uses `one-time-code` (`:164`).
- **FACT** There is **no show/hide password toggle** and **no remember-me**.
- **FACT** The "Forgot password?" link only explains that you must ask an officer for a reset code (`LoginScreen.tsx:28-32`). There is no self-serve reset.
- **FACT** A dev bypass button shows only under `import.meta.env.DEV` (`LoginScreen.tsx:148-153`). Its email is `jake@tke.org`, hardcoded at `src/api.ts:6`.
- **Token storage**:
  - **FACT** The JWT is kept in `localStorage['g_token']` (`src/api.ts:5,54,80`). Every auth call writes it (`authPost`).
  - **FACT** Logout only removes the key (`src/api.ts:15-17`). There is no server-side logout call.
  - **FACT** `lib/session.ts` holds only permission helpers, not session storage (`src/lib/session.ts:1-15`).
- **Reload**: **FACT** `authed = !!localStorage.getItem('g_token')` (`src/App.tsx:25`). The client does not check expiry or decode the token. The app then runs the full load.
- **Token lifetime**: **FACT** the server-side TTL is 7 days (`LocalDev/api/auth/api/auth.py:31,61`), and each token carries a `ver` claim. **INF** Login is therefore effectively always "remembered" for 7 days, with no refresh and no sliding renewal.
- **401 handling**:
  - **FACT** `request()` deletes the token on a 401 and throws `AuthRequiredError` (`src/api.ts:169-172`). The `retry` parameter (`:159`) never retries; it is a misleading name.
  - **FACT** On the startup load, `useAppData` catches the error, calls `logout()` and sets `backendDown` (`useAppData.ts:185-188`). `App`'s `authed` state is **not** reset, so an expired session shows an empty app with "Can't reach the chapter server. Sign out and try again…" (`AppShell.tsx:103-107`). It is not redirected to login.
  - **FACT** A 401 mid-session on a mutation goes through `syncApi`, then `describeError`. `AuthRequiredError` has no `status`, so the user sees "Couldn't save that — the server refused the change." (`src/lib/sync.ts:44-47`). It is not reported as an expired session.
  - **FACT** There is no token refresh endpoint and no client refresh.
- **INF** Reloading during the "Choose a password" step after redeeming a code breaks the setup. Redeeming stores a full 7-day token (`api.ts:54`; `LocalDev/api/auth/api/auth.py:470-473`), so on reload `authed` becomes true and the app opens. The password step is skipped, and the single-use code is already consumed.

## 6. OnboardingScreen

- **FACT** This is the pre-login **chapter creation** form ("Start a chapter"). It is not member onboarding (`OnboardingScreen.tsx:5-7,73-77`).
- **FACT** It appears when the user clicks "New here? Start a chapter" on the login screen (`LoginScreen.tsx:142-147`). That sets `onboarding` (`src/App.tsx:34-36`).
- **FACT** Fields: chapter name (required), organization (optional), school (optional), your name, your email and your phone (all required), and an SMS consent checkbox that starts unchecked (`OnboardingScreen.tsx:80-120`). It POSTs `/api/chapters` without a token (`src/api.ts:103-130`).
- **FACT** On success it shows the setup code once, then "Go to sign in" (`OnboardingScreen.tsx:46-66`). The code must then be re-typed on the login screen's code step; nothing carries the email or code over.
- **FACT** Completion is not tracked on the client; the component state is all there is. There is no post-login first-run checklist or tour for either the founding officer or invited members.
- **FACT** `greekos/README.md:31` still says "There is no self-serve chapter signup", which is stale.

## 7. Roster and profile UI

- **FACT** There is **no "My Profile" view**. A member's only self-edit is the SMS opt-in on Home. Name, email, phone, password change (outside the reset-code flow) and avatar have no UI. `MemberDto` has no phone (`src/api.ts:241-249`), and `adaptMembers` sets `phone: ''` (`src/adapters.ts:75`).
- **FACT** The roster table (`src/components/RosterModule.tsx:104-194`) is visible to everyone; there is no nav permission (`src/config/navigation.ts:29`). It shows name, role and SMS state (`members:invite` only), then Class, Academic Standing/GPA, Attendance (`standing:view_all`), Unpaid fines, Risk Shifts, and a Roles button (`roles:assign`).
- **FACT** Several roster columns are filled with made-up constants, because `adaptMembers` hardcodes them (`src/adapters.ts:75-84`):
  - "Class": `memberClass: ''`, always blank (`RosterModule.tsx:142`). There is **no class column in the DB**; the class feature is deferred to #115 per memory.
  - "GPA": `gpa: 0`, so every row shows "0 GPA" (`RosterModule.tsx:148`).
  - "Room": `roomNumber` is never set, so every row shows "Room N/A" (`:126`), next to an empty `major`.
  - "Risk Shifts": `securityHoursServed: 0`, so every row shows "0 hrs" (`:172`).
  - Standing and Unpaid fines for a **member** session: the 403'd standing call makes every row "Good Standing" and "$0.00".
- **FACT** The role filter chips are `['ALL','President','Treasurer','Risk Manager','Active']`, compared by equality against `m.role` (`RosterModule.tsx:42,77`). `m.role` can only be `Officer`, `Active Member` or `Alumni` (`src/adapters.ts:70,76`), so **every chip except ALL always returns an empty table**. This is also a role-name branch.
- **FACT** The "Brother & Role" header (`:109`) and the role line show only the display role (Officer / Active Member), not real RBAC roles.
- **MemberRolesPanel** (`src/components/MemberRolesPanel.tsx`):
  - **FACT** The modal loads `GET /api/rbac/roles` and `GET /api/rbac/members/{id}/roles` (`:29-39`). It shows a checkbox per catalog role, including the raw `role.key` in monospace (`:84`).
  - **FACT** Toggles are optimistic POST/DELETE calls, rolled back on error (`:41-56`). After a change it calls `refreshOwnPermissions` when the edited member is yourself (`useAppData.ts:104-113`).
  - **FACT** Admin and president tier rules are left to the server.
- **FACT** `RosterCsvImport` (gated by `members:invite`) is all-or-nothing and lists row errors (`src/components/roster/RosterCsvImport.tsx`).

## 8. How permissions reach the UI

- **FACT** `useAppData` loads `GET /api/rbac/me/permissions` once at startup into a `Set<string>` (`useAppData.ts:124,131,166`). It reloads only after you edit your own roles (`:104-113`).
- **FACT** `can(perms, key)` is a linear scan (`src/lib/session.ts:8-11`). `App.tsx` turns it into `canX` booleans passed as props (`App.tsx:49-52,84-85,126-127,138,164,182-183,221-223,233`).
- **FACT** `isOfficerView` means `can(perms,'standing:view_all')` (`src/lib/session.ts:6,13-15`). It is still used as presentation in:
  - the "Officer"/"Member" label (`Sidebar.tsx:77`, `AppShell.tsx:93`)
  - Home's officer variant (`App.tsx:83`), which hides door-code entry for officers (`WelcomeBanner.tsx:87`), shows the "Supervised" count (`:33`), and shows the sign-off nudge (`DashboardOverview.tsx:101`)
  - `LocalDev/CLAUDE.md`'s Conventions table lists `isOfficerView` under "Do not".
- **FACT** Role-name and string branching still exists:
  - the RosterModule role chips (`:77`)
  - `standing === 'Good Standing'` colouring (`RosterModule.tsx:151`; also `EventsModule.tsx:837`, `FinanceModule.tsx:355`)
  - the adapter's `row.role === 'officer'` mapping to display text (`src/adapters.ts:70`)
  - None of these grant authority; all are presentation.
- **FACT** Nav gating covers only Outbox (`announcements:send`) and Command console (`nl_controller:execute`) (`src/config/navigation.ts:30-31`). Treasury, Roster, Attendance, Jobs, Initiatives and Events show for everyone, and each module hides its own controls.
- **INF** An officer whose roles are changed by someone else keeps a stale permission set until they reload.

## 9. Data-loading pattern

- **FACT** Everything loads up front, once, in a single `useEffect` in `useAppData` (`useAppData.ts:118-193`). Three sequential waves run before Home has real data:
  1. 5 parallel calls: `/api/auth/me`, `/api/rbac/me/permissions`, `/api/members/`, `/api/standing/`, `/api/memberadmin/scores` (`:122-130`)
  2. 9 parallel calls: events, excuses, fines, treasury dashboard, tasks, announcements, initiatives, contribution/me, member treasury dashboard (`:134-153`)
  3. `/api/events/upcoming-details` (`:159`; `src/lib/app-data.ts:6-23`)
  - In total **15 requests in 3 round-trip waves**, including the treasury dashboard and the full excuses, fines and tasks lists that Home does not need.
  - **FACT** A member session gets two guaranteed 403s per load (standing and scores), and `/api/treasury/dashboard` is a third 403 for anyone without the treasury key. The same standing/scores pair is re-fetched on finance writes (`src/hooks/useFinance.ts:164-167`) and roster refetches (`src/hooks/useRoster.ts:13-20`).
- **FACT** The domain hooks (`useEvents`, `useFinance`, …) own state and mutations but no loading of their own. The exceptions are `useOutbox` (its own effect), MemberRolesPanel, and FinanceModule effects (`FinanceModule.tsx:132,142,149`).
- **FACT** There is no cache layer: no React Query or SWR, no stale-while-revalidate, no refetch on focus or interval, no persistence. Data stays fresh only through a domain refetch after a mutation (`useBackend.ts:29-55`) or a full page reload.
- **FACT** The roster refetch exists in three copies: `useRoster.refetchMembers`, `useFinance.refetchRoster`, and the initial load. **INF** These are candidates to merge.
- **INF** Mobile Home has to wait for the slowest of the 15 calls, serially across three waves on cellular. Most of that payload (the excuses list, fines list, every task, the officer treasury dashboard) is not shown on Home. A personalized Home would do better with one `/api/home/me`-style aggregate, or with per-view lazy loading.

## 10. Existing frontend tests

- **FACT** The runner is `tsx --test 'src/**/*.test.ts'` (`package.json:12`) using `node:test`. There are 29 files and 151 tests, all passing on 2026-10-11.
- **FACT** Tests are **not** limited to `lib/`. There are 14 component tests under `src/components/*.test.ts` and `finance/add-transaction.test.ts` that render with `react-dom/server` `renderToStaticMarkup` and assert on HTML with regexes. Examples:
  - `shell-access.test.ts`: the Officer/Member label
  - `home-access.test.ts`: Schedule event, the sign-off nudge, and the door section
  - `roster-access.test.ts`
  - `member-roles.test.ts`
  - `dashboard-current-member.test.ts`
- **FACT** There is no DOM environment (no jsdom or happy-dom), no Testing Library, no interaction or event tests, no effects (SSR does not run `useEffect`), no visual or responsive tests, and no e2e (Playwright).
- **FACT** Coverage is mostly permission-gating presence checks plus the pure `lib/*` logic: auth validators, session, sync, balance, dues, transaction, checkinLink, contribution, consent, parseWhen, rollCall, app-data.
- **FACT** The test fixtures use fields the real adapter never produces (`memberClass: 'Fall 2026'`, `gpa: 3.4`, `major: 'Economics'`; e.g. `roster-access.test.ts`). **INF** So the tests do not catch the always-blank and always-0 roster columns.
- **FACT** Nothing tests `App.tsx`, `useAppData` or `api.ts` request and 401 handling.

## 11. Route-by-route inventory

| Nav id | Label | Component (App.tsx line) | Nav gate | In-module gates (App.tsx) |
|---|---|---|---|---|
| `dashboard` | Home | `DashboardOverview` (76-97) | none | `standing:view_all` (officer view), `calendar:event:create`, `announcements:create` |
| `events` | Events | `EventsBar` plus `CalendarModule` or `EventsModule`, switched by `chrome.view` (99-158) | none | `calendar:event:create/update/delete`, `attendance:checkin_link:manage`, `tasks:assign` |
| `initiatives` | Initiatives | `InitiativesModule` (160-174) | none | `calendar:initiative:create`, `tasks:assign` |
| `attendance` | Attendance | `AttendanceModule` (176-191) | none | `attendance:override` (also picks the initial sub-tab), `attendance:excuse:review`, `standing:view_all` |
| `finance` | Treasury | `FinanceModule` (193-215) | none | `permissions` passed whole → `treasuryAbilities` (`treasury:invoice:create`, `treasury:payment:verify`, `treasury:fines:issue`, `treasury:adjustment:create`) |
| `tasks` | Jobs | `TasksModule` (229-239) | none | `tasks:create` |
| `roster` | Roster | `RosterModule` (217-227) | none | `members:invite` (CSV and SMS column), `standing:view_all`, `roles:assign` |
| `outbox` | Outbox | `OutboxModule` (241) | `announcements:send` (`navigation.ts:30`) | Its own fetch; there is no render guard in App |
| `command` | Command console | `CommandModule` (243-250) | `nl_controller:execute` (`navigation.ts:31`) | — |
| (pre-auth) | — | `LoginScreen` / `OnboardingScreen` (`App.tsx:33-37`) | `!authed` | — |

The nav order is defined in `src/config/navigation.ts:22-32` as a flat list with no groups.

## 12. Over-engineering, dead code, leftovers

- **FACT** `metadata.json` is a Google AI Studio leftover (`"MAJOR_CAPABILITY_SERVER_SIDE_GEMINI_API"`).
- **FACT** `vite.config.ts:15-19` holds AI Studio `DISABLE_HMR` comments, with mojibake ("Do not modifyâfile watching").
- **FACT** The `@` alias (`vite.config.ts:11`; `tsconfig.json` `paths`) is never imported.
- **FACT** `autoprefixer` and `esbuild` devDependencies have no config or usage; Tailwind v4 needs neither.
- **FACT** The `animate-in` classes are no-ops because no plugin is installed (§3).
- **FACT** `types.ts` has a `MemberRole` union with nine officer titles (`src/types.ts:1-13`) and a `MemberStanding` union, but the adapter only ever produces `Officer`, `Active Member` or `Alumni`. The `Member` fields `gpa`, `major`, `memberClass`, `roomNumber`, `securityHoursServed` and `phone` are never populated from the server (`src/adapters.ts:75-84`). These are prototype-era fields that now drive UI showing made-up values.
- **FACT** `Member.duesBalance` (in dollars) is duplicated next to `duesBalanceCents`. RosterModule uses `formatMoney(mem.duesBalanceCents || mem.duesBalance * 100)` (`RosterModule.tsx:167`), a float fallback that is redundant and could never differ.
- **FACT** `SyncOutcome.rollback` (`src/lib/sync.ts:21`) is computed and tested but never read by `useBackend`.
- **FACT** The `request(..., retry = true)` parameter (`src/api.ts:159`) never retries.
- **FACT** The generic `api.get/post/put/patch/del` (`src/api.ts:569-573`) have no callers.
- **FACT** The command console advertises `extend bid to NAME` (`src/components/CommandModule.tsx:47,266`), and `command-copy.test.ts` asserts it. No parser branch handles it; recruitment vocabulary survived migration 0218's cleanup.
- **FACT** The `Card` `key?` prop rests on a false premise (§3).
- **FACT** The `safeMembers = members || []` style guards (`DashboardOverview.tsx:62-66`, `RosterModule.tsx:37`) protect against null props that the types never allow.
- **FACT** README.md:31 is stale (§6).
- **INF** `useAppData.handleExecuteCommand` takes a `payload: any` (`useAppData.ts:212`) and builds announcements optimistically with a local random id (`:231-232`). It is the one untyped seam in the data layer.

---

## Gaps vs desired state

- **Member Home personalization**:
  - The chapter name is hardcoded "Alpha Chapter", and member standing is always faked as "Good Standing".
  - There is no "my jobs", my upcoming RSVPs or required events, my excuses, or my fines/invoices list; only a one-line balance.
  - The Jobs tile shows chapter-wide open jobs. There is no time-of-day or next-action logic.
  - Home needs a member-readable standing source (a `/api/standing/me` does not exist) and ideally one Home aggregate endpoint instead of the 15-call load.
- **Mobile bottom nav**: none exists. The only mobile navigation is the hamburger drawer. There are no safe-area insets and no `theme-color` or manifest.
- **Desktop sidebar regrouping (Home / Chapter / My Activity / Officer Cabin)**:
  - Today `NAV_ITEMS` is a flat list of nine with no `group` field. Only two items carry a permission.
  - An "Officer Cabin" group needs per-item permission keys for officer surfaces: Outbox, Command, and officer slices of Treasury, Attendance and Roster. Today those modules are shared views that branch internally.
  - "My Activity" has no backing views; the per-member data is scattered across Home, Treasury, Attendance and Jobs.
- **Large-screen layout**:
  - A single `max-w-7xl` container and `lg:grid-cols-2` on Home are all there is. There are no `xl:` or `2xl:` breakpoints, no multi-column or rail layout, and no right-hand panel. The sidebar is a fixed `w-64` with no collapse.
- **Show/hide password**: missing on all three password inputs (`LoginScreen.tsx:125,188,194`).
- **Remember me**:
  - Missing. The token always goes to localStorage with a fixed 7-day server TTL, and there is no refresh.
  - Expiry gives a misleading "can't reach server" screen instead of a return to login (`useAppData.ts:187-188`, `App.tsx:25`).
  - A mid-session 401 is reported as "server refused".
- **My Profile**:
  - There is no view. Members cannot see their own standing, roles (RBAC role keys), phone or email, nor change their password or phone.
  - The roster's Class, GPA, Room and Risk Shifts columns are blank or 0 placeholders, and class has no DB column (#115).
- **Onboarding**:
  - Only chapter creation exists before login, and it requires re-typing the setup code on the login screen.
  - There is no post-login first-run flow for the founding officer (invite roster, set dues, first event) or for invited members (set password, then profile, SMS consent, tour).
  - Reloading mid-"Choose a password" skips password setup.
  - No deep link (for example an emailed `?code=` link) pre-fills the setup-code form.
