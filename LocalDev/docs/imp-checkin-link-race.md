# Implementation plan — fix check-in link overwrite race in events.tsx

Date: 2026-07-12
Order: independent. Product-code fix for a latent e2e flake; land it so
`e2e/checkin.spec.ts` can't intermittently fail under parallel load.
Scope: one frontend view (`fratos/views/events.tsx`). No backend, no schema, no
API-client change.

Decisions are settled here; the implementer executes as written and reports
drift instead of improvising.

## Root cause (verified 2026-07-12, file:line evidence)

An officer can generate a new check-in link and have it silently wiped from the
UI by a slow in-flight fetch of the *existing* link.

- Selecting an event fires an effect that loads the current active link:
  `api.getActiveCheckinLink(selected).then((res) => { … setActiveLink(...) })`
  (`events.tsx:60-68`). Its cleanup only flips `cancelled` when **`selected`**
  changes (`:62`, `:67-68`).
- `generateLink` (`events.tsx:88-92`) creates a new link and calls
  `setActiveLink(link)` synchronously.
- If the officer generates a link before the `:63` fetch resolves, the fetch
  lands late and runs `setActiveLink(...)` with its own (stale) result. Since
  `selected` didn't change, `cancelled` is still `false`, so the late fetch
  overwrites the freshly generated link — usually with `null` (no prior link),
  wiping it from the UI. `killLink` (`:94-98`) has the mirror problem: a late
  fetch can resurrect a killed link.

This is a classic last-write-wins effect race. It failed once under full
parallel e2e load, then passed — exactly the signature of a timing race, not a
test bug. The fix is in `events.tsx`.

## Settled decisions

- **D1 — The fetch is the stale writer; make it yield to user actions.** The
  generate/kill mutations reflect the user's intent and must win over a
  background load of prior state. The load-effect must not clobber a value set
  after the load began.
- **D2 — Guard by request currency, not just by `selected`.** Widen the guard
  so any newer write (generate, kill, or a re-selection) invalidates an
  older in-flight `getActiveCheckinLink` response. Prefer the smallest robust
  mechanism; do not restructure the component.
- **D3 — No API/contract changes.** Backend and `api-client` are correct; this
  is purely a client-side ordering fix.

## Steps

Implement D2 with a per-fetch currency token. In `EventsPage`:

1. Add a ref that marks the latest link-state writer, e.g.
   `const linkFetchId = useRef(0)`.

2. In `generateLink` and `killLink` (`events.tsx:88-98`), bump the token
   **before** the await and set state as today, so a later fetch can detect it
   was superseded:

   ```ts
   const generateLink = async () => {
     if (!selected) return;
     const token = ++linkFetchId.current;
     const link = await api.createCheckinLink(selected);
     if (linkFetchId.current !== token) return;
     setActiveLink(link);
   };
   ```

   Apply the same `token`/guard shape to `killLink` (set `null` on success).

3. In the select effect (`events.tsx:60-68`), capture and check the token so a
   late load can't overwrite a newer write:

   ```ts
   useEffect(() => {
     if (!selected) return;
     const token = ++linkFetchId.current;
     api.getActiveCheckinLink(selected).then((res) => {
       if (linkFetchId.current !== token) return;
       setActiveLink("short_code" in res && res.short_code ? (res as CheckinLink) : null);
     });
   }, [selected]);
   ```

   The single monotonic `linkFetchId` now orders all three writers (select-load,
   generate, kill); whichever ran most recently owns `activeLink`, and any
   older in-flight promise no-ops. The old `cancelled` boolean is subsumed —
   remove it.

## Verification

- **Race repro (manual/dev).** Throttle the network (or add a temporary delay
  in the `api-client` `getActiveCheckinLink` mock) so the select-load resolves
  slowly; select an event with no existing link, immediately click Generate,
  and confirm the generated link stays visible after the slow fetch lands.
  Today it disappears.
- **Kill mirror.** With a slow select-load, select an event that has a link,
  click Kill before the load resolves, confirm the link stays gone.
- **e2e.** `cd fratos && npm run test:e2e` — `checkin.spec.ts` green; run it a
  few times (or with `--repeat-each`) under parallelism to confirm the flake is
  gone.
- **No regression.** Selecting between events still shows each event's correct
  active link.
