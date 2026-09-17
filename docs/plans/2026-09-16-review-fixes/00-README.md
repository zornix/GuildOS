# Review fixes — 2026-09-16

Fixes for the high and medium findings from the review of the 63 unpushed
commits. Low findings are GitHub issues, not part of this work.

## Plans

| Plan | Branch | Area | Fixes |
|------|--------|------|-------|
| `01-backend-notifications.md` | `fix/review-notifications` | events email + outbox list | H1, H2, M5 |
| `02-backend-secrets-and-uploads.md` | `fix/review-secrets-uploads` | auth codes, Sentry, CSV upload | M3, M4, M6 |
| `03-frontend-money-and-roster.md` | `fix/review-frontend` | greekos UI | M1, M2, M7, M8 |

The three plans touch disjoint files. They run in parallel, one worktree each.

Skipped on purpose: `d15d0a4` failing `tsc` mid-history — already fixed at HEAD
by `d22678d`; only a history rewrite would change it.

## Decisions

| # | Decision | Why |
|---|----------|-----|
| 1 | EVENT_CREATED email goes out only when `visibility` is `chapter` (or unset). Other audiences get no automatic email. | Smallest safe fix. Per-audience fan-out is a feature, not a fix. |
| 2 | Outbox list *drops* treasury rows for callers without `treasury:audit:view`, rather than blanking the body. | The recipient name + event type alone ("PAYMENT_REJECTED — Sam") is still a leak. |
| 3 | Code payloads are wiped to `{}` only on `sent` / `simulated`. `failed` rows keep theirs. | `payload` is `NOT NULL`, and a failed row must still render on Retry. |
| 4 | Dues-run idempotency key is generated once per open modal (`useRef`) and reused on retry. | A key per click would defeat the point. |
| 5 | Money handlers get a plain `try/catch` + `showToast`, not `syncApi`. | They need the awaited result; `syncApi` is fire-and-forget. |

## Rules for every agent

- Work ONLY in your own worktree and branch. Never touch `/home/mshi/GuildOS`
  (the main checkout has the user's uncommitted work).
- Worktree setup: `git reset --hard main`, copy `/home/mshi/GuildOS/LocalDev/.env`
  to `LocalDev/.env`, and for frontend work `npm install` in `LocalDev/greekos`.
- TDD: write the failing test, watch it fail, fix, watch it pass.
- One commit per fix (the plan names each commit). Plain sentence-style subjects
  like the rest of `git log`. Stage only the files that fix touches.
- NO `Co-Authored-By`, NO "Generated with Claude", no session links in commits.
- Do not push. Do not merge. Do not open PRs.
- Read `LocalDev/CLAUDE.md` before writing code. Match surrounding style.
- Backend tests: `python3 -m pytest tests/<domain>/` from `LocalDev/`.
  Frontend: `npm test` and `npm run lint` from `LocalDev/greekos`.
- If a plan step turns out wrong against the real code, fix the problem the
  step describes in the smallest way and say so in your report.
- Final report: commit SHAs + subjects, test output summary, anything skipped.
