# 03 — Frontend: dues run safety, money errors, roster refresh, a11y

Branch `fix/review-frontend`. Read `00-README.md` first. All paths are under
`LocalDev/greekos/src/`. Run `npm install` in `LocalDev/greekos` first.

Frontend tests here are logic-only (`src/lib/*.test.ts`, node:test, no DOM).
Where a fix is pure wiring with no extractable logic, `npm run lint`
(`tsc --noEmit`) + `npm test` staying green is the check — do not add a DOM
test framework.

## Fix M1 — a retried dues run bills the chapter twice

**Problem.** `api.ts::bulkCreateInvoices` sends no `Idempotency-Key`. The server
(`POST /api/treasury/invoices/bulk` → `tr_bulk_create_invoices`) already honours
that header, and has no other guard against a double submit.

**Steps**
1. `api.ts::request`: add an optional `headers?: Record<string, string>`
   parameter AFTER `retry` (so no existing call site changes) and spread it into
   the fetch headers after `Authorization`.
2. `bulkCreateInvoices(invoices, idempotencyKey: string)` passes
   `{ 'Idempotency-Key': idempotencyKey }`. Confirm the exact header name in
   `LocalDev/api/treasury/api/invoices.py`.
3. `hooks/useFinance.ts::handleCreateDuesRun(draft, idempotencyKey)` threads it.
4. In the dues-run modal (`DuesRunModal`, find it via grep) hold
   `const runKey = useRef(crypto.randomUUID())` and pass `runKey.current` on
   submit. One key per opened modal: a retry after a timeout reuses it; after a
   *successful* run, set `runKey.current = crypto.randomUUID()` (or rely on the
   modal unmounting — check which happens) so the next run is not deduped away.
5. Update every type along the way (`onSubmit` prop etc.). `npm run lint` green.

**Commit:** `Send an idempotency key with a dues run so a retry cannot bill twice`

## Fix M2 — money actions fail silently

**Problem.** In `hooks/useFinance.ts`, `handleCreateDuesRun`,
`handleSubmitProof` (the `api.submitPaymentProof` call), `handleVerifyProof` and
`handleRejectProof` have no `try/catch`. A failed call is an unhandled
rejection: no toast, and on verify a 409 looks like it worked.

**Steps**
1. Wrap the API call in each of the four handlers:
   ```ts
   try {
     ...existing body...
   } catch (err) {
     console.error('Dues run failed', err);
     showToast('Could not create the dues run. Nothing was billed — try again.');
     throw err;
   }
   ```
   Re-throw so the modal's own `submit` can stay open / reset its busy state —
   then check each caller (`DuesRunModal.submit`, the proof modal,
   `ProofQueue.run`) catches it and does not leave a spinner stuck or produce an
   unhandled rejection. If a caller has no `catch`, add one that just swallows
   (the toast already told the user).
2. Toast copy, plain and specific:
   - dues run: as above
   - submit proof: `Could not submit your payment. Try again.`
   - verify: `Could not verify that payment. Refresh and try again.`
   - reject: `Could not reject that payment. Refresh and try again.`
   On verify/reject failure also call `refreshQueue()` (best-effort, inside its
   own try) so a row someone else already handled disappears.
3. Keep the existing inner evidence-upload `try/catch` exactly as it is.
4. `npm run lint && npm test` green.

**Commit:** `Tell the user when a dues run, payment proof, verify or reject fails`

## Fix M7 — roster does not update after a CSV import

**Problem.** `hooks/useRoster.ts::handleImportRoster` toasts "Invited N members"
but never refreshes `members`; new invitees appear only after a reload.

**Steps**
1. Find how `members` is first loaded (grep `getMembers` / `adaptMembers` in
   `hooks/useAppData.ts` and `adapters.ts`). Reuse that exact fetch + adapter.
2. After a successful `api.importRoster`, refetch and `setMembers(...)`. Put the
   refetch in its own `try/catch` that only `console.error`s — the import
   succeeded, a failed refresh must not read as a failed import.
3. If the loader lives in `useAppData` rather than `useRoster`, pass a
   `refetchMembers` dep into `useRoster` the way other hooks receive
   `refetchEvents` / `refetchJobs`.
4. `npm run lint && npm test` green.

**Commit:** `Refresh the roster after a CSV import so new invitees show up`

## Fix M8 — "Unmarked" is invisible to screen readers on a phone

**Problem.** `components/AttendanceModule.tsx` (~line 242): the "Unmarked" label
is `hidden sm:inline`, so at phone width it is `display:none` and status is
conveyed by button colour alone.

**Steps**
1. Change the label's classes `hidden sm:inline` → `sr-only sm:not-sr-only sm:inline`.
2. On the four status buttons in the same cell add `aria-pressed={isCur}`.
3. `npm run lint` green.

**Commit:** `Keep roll-call status readable by screen readers at phone width`
