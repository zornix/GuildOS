# GuildOS Codebase Review

Date: 2026-08-20

Reviewed commit: `9470275` (`zornix/code-review`)

Primary scope: active `LocalDev/` backend, the established `fratos` frontend,
and the recently wired `greekos` prototype

## Executive summary

The codebase has strong backend safety conventions: tenant-scoped queries,
permission checks, guarded production configuration, RPC-backed mutations, and
an extensive test suite. Both frontend applications compile successfully.

The most important remaining risks are concentrated in the GreekOS prototype.
Its interface mixes live data with local demo mutations, exposes a "View as"
control that does not change the authenticated backend identity, and permits
interactive mock updates while the backend is unavailable. These behaviors can
make an operator believe that financial, roster, or member-specific changes
were saved when they were not—or were saved under the seeded officer instead.

The established Fratos application also pins a Next.js release with known
production dependency vulnerabilities. The available non-major upgrade should
be applied and verified.

## Findings

### 1. High: Finance actions report success without persisting changes

The GreekOS Finance screen presents several actions as operational even though
they only modify React state:

- Recording a direct payment creates a local payment and ledger entry but makes
  no API request.
- Paying dues changes only the local member balance.
- Approving a fine payment changes only the local fine status.
- Posting a ledger correction changes only the local ledger and balance.
- Issuing a fine reaches the backend only when `relatedEventId` is present, but
  the normal Issue Fine form does not supply that field.

The handlers nevertheless display messages such as "recorded to immutable
ledger" and "fine assessed." The GreekOS README also states that every tab
outside the three explicitly demo-gated tabs reads and writes the live backend.
That makes the lack of persistence difficult for a user to detect.

Evidence:

- `LocalDev/greekos/src/hooks/useFinance.ts:43-78`
- `LocalDev/greekos/src/hooks/useFinance.ts:80-125`
- `LocalDev/greekos/src/hooks/useFinance.ts:128-168`
- `LocalDev/greekos/src/components/FinanceModule.tsx:80-115`
- `LocalDev/greekos/README.md:46-56`

Recommendation:

Remove or demo-gate unsupported actions until matching backend workflows exist.
For financial operations, prefer the existing balance-submission, verification,
invoice, and ledger RPC flows rather than simulating mutations in the browser.
Success messages should only appear after the server confirms the write.

### 2. High: "View as" does not change the authenticated backend identity

GreekOS always authenticates as the seeded officer `jake@tke.org`. The sidebar
can then change `currentMemberName` and the client-side officer/member flag, but
neither control changes the bearer token.

This causes inconsistent live behavior. For example, volunteering as an event
organizer or claiming an event/initiative job displays the selected member
optimistically, while the API performs the self-service action for Jake. Other
actions that explicitly pass a member ID may work only because Jake has officer
permissions. The result is not a reliable impersonation model.

Evidence:

- `LocalDev/greekos/src/api.ts:1-35`
- `LocalDev/greekos/src/components/Sidebar.tsx:94-155`
- `LocalDev/greekos/src/hooks/useEvents.ts:142-184`
- `LocalDev/greekos/src/hooks/useInitiatives.ts:73-116`
- `LocalDev/greekos/README.md:31-36`

Recommendation:

For a live prototype, remove the identity selector and derive role and identity
from `/api/auth/me`. If view simulation remains valuable, label it explicitly
as presentation-only and disable every mutation while viewing another member.
A real impersonation feature would require a server-authorized, audited session
mechanism rather than a client-side name change.

### 3. High: Fratos ships vulnerable production dependencies

`LocalDev/fratos/package.json` pins `next@16.2.9`. A live
`npm audit --omit=dev` reported four high-severity vulnerable production
packages in the installed dependency graph: Next.js and transitive `postcss`,
`sharp`, and `nanoid` packages. The audit offered `next@16.3.1` as a non-major
fix.

The reported Next.js advisories cover authorization bypass, denial of service,
server-side request forgery, cache confusion, and server-function disclosure.
Not every advisory is necessarily reachable in this application's current
static SPA architecture, but the pinned production release is within the
affected ranges.

Evidence:

- `LocalDev/fratos/package.json:14-17`
- `LocalDev/fratos/package-lock.json`
- Verification command: `npm audit --omit=dev --json`

Recommendation:

Upgrade Next.js and `eslint-config-next` together to at least the audit-proposed
fixed release, regenerate the lockfile, and rerun lint, unit tests, build, and
the relevant browser flows. Re-run the production-only audit after upgrading.

### 4. Medium: Backend failure leaves live tabs as writable mock screens

GreekOS initializes its domains from `INITIAL_*` mock collections. The initial
load uses one broad `try/catch`; a failure from any required endpoint sets
`backendDown` and retains the mock collections. The application still renders
the active module, however, and `syncApi` silently returns whenever
`backendDown` is true.

Most handlers update local state and show success messages before calling
`syncApi`. Consequently, after an outage the interface remains interactive and
can appear to save mock events, tasks, fines, announcements, and other records
even though no request is attempted. The same mock content is visible and
potentially actionable during the initial loading window.

Evidence:

- `LocalDev/greekos/src/hooks/useBackend.ts:7-28`
- `LocalDev/greekos/src/hooks/useAppData.ts:32-68`
- `LocalDev/greekos/src/hooks/useAppData.ts:95-166`
- `LocalDev/greekos/src/components/layout/AppShell.tsx:110-124`

Recommendation:

Do not render actionable domain modules until the initial live load succeeds.
When the backend is unavailable, either show a blocking offline state or switch
the entire application into an unmistakable, explicitly acknowledged demo
mode. Mutation helpers should reject with a visible error rather than silently
returning.

### 5. Medium: Roll-call submission can partially commit

GreekOS submits attendance one member at a time in a sequential loop. Each call
is an independent RPC-backed transaction. If a later request fails, earlier
members remain updated while the shared mutation handler reports that the
operation failed and refreshes the event summary.

The current backend route also passes `p_idempotency_key: None`, so the caller
cannot safely identify a retried roll-call operation.

Evidence:

- `LocalDev/greekos/src/hooks/useAttendance.ts:26-35`
- `LocalDev/api/attendance/api/attendance.py:188-209`

Recommendation:

Add an atomic batch-attendance RPC that validates every row before committing,
accepts an idempotency key, and returns per-member results. If a batch endpoint
is deferred, the UI must track individual successes and failures and clearly
report partial completion rather than presenting roll call as one atomic save.

### 6. Medium: GreekOS mutation requests omit idempotency keys

The shared GreekOS request helper always supplies only content type and bearer
authorization headers. It has no facility for an `Idempotency-Key`, although
important backend routes—including event and task creation—accept one and pass
it to their RPCs.

Without keys, duplicate button submissions or an uncertain network outcome can
create duplicate events, jobs, initiatives, or announcements. The shared
`syncApi` helper also returns immediately rather than exposing pending state,
so components cannot consistently disable controls while a mutation is in
flight.

Evidence:

- `LocalDev/greekos/src/api.ts:24-47`
- `LocalDev/greekos/src/hooks/useBackend.ts:14-25`
- `LocalDev/api/events/api/events.py:71-100`
- `LocalDev/api/tasks/api/tasks.py:30-71`

Recommendation:

Generate one stable idempotency key for each user-initiated mutation and allow
the request helper to send it. Preserve the same key for retries of that
operation. Return a promise and pending state from the mutation layer so forms
and action buttons can prevent accidental concurrent submission.

## Verification performed

### GreekOS

- `npm run lint` — passed (`tsc --noEmit`)
- `npm run build` — passed
- `npx tsx src/selfcheck.ts` — passed
- `npm audit` — zero vulnerabilities reported for this package tree

### Fratos

- `npm run lint` — passed
- `npm run test:unit` — 13 tests passed
- `npm run build` — passed
- `npm audit --omit=dev --json` — failed with four high-severity production
  dependency findings

### Backend

- `python3 -m compileall -q api scripts` — passed
- `python3 -m pytest -q` — 307 passed, 509 skipped
- The 509 skipped tests require the configured PostgreSQL test database, which
  was not available in this workspace. Tenant isolation, migrations, triggers,
  and end-to-end RPC behavior were therefore inspected statically but were not
  runtime-verified in this review.

### Repository hygiene

- `git diff --check` — passed
- No tracked credentials or private keys were found by the review's targeted
  secret-pattern scan.

## Positive observations

- Production and preview boot guards reject weak JWT configuration, missing
  database configuration, enabled development authentication, weak cron
  secrets, unsafe CORS origins, and incomplete Twilio configuration.
- The backend consistently derives active membership and chapter identity from
  the bearer token before domain work.
- Sensitive backend domains use permission checks and RPC-backed mutation
  boundaries rather than trusting client-side role flags.
- Both frontends centralize their API calls and adapter logic instead of issuing
  ad hoc fetches throughout UI components.
- The backend has broad test coverage; restoring a database-backed test
  environment would make substantially more of that coverage executable.
