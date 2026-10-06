# TypeScript 7 upgrade (greekos frontend)

Replaces Dependabot PR #73 (typescript 5.8.3 → 7.0.2), which fails lint.

## Goal

`LocalDev/greekos` type-checks clean under TypeScript 7.0.2. Behavior does not change.

## Why it fails today

TS 7 is strict by default. `@types/react` / `@types/react-dom` were never installed, so every
JSX element and React import is `any` (~2,600 errors). With the types installed, 11 real errors
remain (measured 2026-10-06 in a scratch copy).

## Scope

- Only `LocalDev/greekos/`. Do not touch `Prod/`, the backend, or CI config.
- No new runtime dependencies. Dev dependencies added: `@types/react`, `@types/react-dom` only.
- Keep `tsconfig.json` changes to the minimum. Do **not** turn strict off or add
  `noImplicitAny: false` — the point is to pass under the new defaults.
- No `// @ts-ignore`, `// @ts-expect-error`, or `as any` to silence errors.

## Steps

1. `npm i -D typescript@~7.0.2 @types/react@^19 @types/react-dom@^19` in `LocalDev/greekos`
   (match the installed React 19 major). Commit `package.json` + `package-lock.json`.
2. Run `npm run lint` (`tsc --noEmit`). Expected errors and fixes:
   | Error | Files | Fix |
   |---|---|---|
   | TS6133 unused `React` import | `CommandModule.tsx`, `FinanceModule.tsx`, `finance/ProofQueue.tsx` | delete the default `React` import (keep named imports) |
   | TS18048 `votesFor`/`votesAgainst` possibly undefined | `RecruitmentModule.tsx:139-140`, `hooks/useRecruitment.ts:44-45` | `?? 0` at the use site; do not change the optional fields in `types.ts` |
   | TS2882 side-effect import `./index.css` | `main.tsx:4` | add `src/vite-env.d.ts` containing `/// <reference types="vite/client" />` |
   | TS2769 no overload matches `createElement` | `components/dashboard-current-member.test.ts:24`, `components/events-access.test.ts:31` | read the full error; the test props likely drifted from the component's props type. Fix the test props to match the real component type — don't widen the component |
   If other errors appear, fix them the same way (smallest correct change, no suppressions).
3. Commit the fixes (one commit per logical change is fine: deps, then type fixes).

## Verification (all must pass, run in `LocalDev/greekos`)

```
npm ci
npx tsc -v          # Version 7.0.2
npm run lint
npm run build
npm test            # 153 pass, 0 fail
```

## Git

- Branch `chore/typescript-7` off `main`. Conventional commit subjects (`chore(deps): …`,
  `fix(types): …`). No Co-Authored-By or "Generated with" trailers.
- After merge: close Dependabot PR #73 as superseded.
