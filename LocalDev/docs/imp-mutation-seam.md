# Implementation plan — give mutations a seam (useMutation + injectable client)

Date: 2026-07-11
Order: step 6 of 7 — first frontend step, after the backend plans land.
Depends on: `imp-one-gate.md` (its Phase D rewrites several of the same
views; land it first to avoid conflicts).
Scope: `fratos/` only.

Contract: decisions settled here; implementer executes as written, reports
drift. Authority on conventions: `../FrontendConventions.md`. Next.js 16
diverges from training data — read `fratos/node_modules/next/dist/docs/`
before touching anything routing-adjacent (`fratos/AGENTS.md`).

## Settled decisions

- **D1 — One mutation hook owns the lifecycle.** `hooks/use-mutation.ts`:
  `useMutation()` returns `{ mutate, saving, error, reset }` where
  `mutate(fn: () => Promise<T>, opts?: { onSuccess?: (r: T) => void })`
  wraps the try/catch, sets `saving`/`error`, and calls `onSuccess` (the
  reload hook-in). Error narrowing (`(e as Error).message`) lives here and
  nowhere else.
- **D2 — The api client crosses one seam: React context.**
  `lib/api-context.tsx` exports `ApiProvider` (prop: an `ApiClient`
  instance, defaulting to the existing singleton) and `useApiClient()`.
  The app is wrapped once (root layout / app shell). Vitest wraps components
  in `ApiProvider` with a fake — no module-global patching. The singleton
  export at `lib/api-client.ts:431` remains for the transition; new/updated
  components must not import it directly.
- **D3 — The error banner becomes a primitive.** The byte-identical inline
  banner div in the six views becomes `components/ui/inline-error.tsx`
  (semantic tone via `config/theme/tokens.ts`, per UI-primitive rules).
- **D4 — No behavior changes.** Same requests, same success/error UX,
  same reload semantics — this plan only moves where the code lives.

## Steps

1. Create `hooks/use-mutation.ts` (D1) + a vitest spec for its state
   machine (saving toggles, error captured, onSuccess fires, reset clears).
2. Create `lib/api-context.tsx` (D2); wrap the app once. Type the context as
   the `ApiClient` class's public surface.
3. Create `components/ui/inline-error.tsx` (D3).
4. Migrate the six views — `views/tasks.tsx`, `announcements.tsx`,
   `recruitment.tsx`, `bylaws.tsx`, `command.tsx`, `admin-roles.tsx` (each:
   one `actionError` state cell + two hand-written try/catch blocks +
   inline banner) → `useMutation` + `useApiClient` + `<InlineError>`.
5. Migrate the direct-singleton callers: `components/forms/excuse-form.tsx`,
   `check-in-form.tsx`, `create-event-form.tsx`, and
   `components/modules/dashboard/pending-excuses-widget.tsx` → `useApiClient`
   (+ `useMutation` where they hand-roll submit state).
6. Prove the seam with two fake-client vitest specs: `excuse-form` (submit
   success + failure renders error) and `views/tasks` (action failure shows
   `InlineError`). These are the first component tests below the e2e suite —
   that's the point of the plan.
7. Acceptance grep: `import { api }` / `from "../lib/api-client"` in
   `components/` and `views/` returns zero (the provider default in the root
   layout is the one sanctioned importer); `setActionError` returns zero.

## Verification

From `fratos/`: `npm run lint`, `npm run test:unit` (new specs included),
`npm run build`, `npm run test:e2e` (tasks/announcements/excuses flows
confirm D4 — no behavior change).

One commit: `refactor(fratos): useMutation hook + context-injected api client; InlineError primitive`
