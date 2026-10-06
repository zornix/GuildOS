# Plan 10 — Error mapping & config Implementation Plan (wave 2)

> **For agentic workers:** read `00-README.md` (rules, decisions, report block) first. Execute task by task, test first. You branch from a `main` that already contains wave 1.

**Goal:** no route leaks raw database text, expected domain errors stop being 500s, health checks degrade honestly, and the localhost CORS guard is back (decision D-R1).
**Spec:** `LocalDev/docs/audit/remediation-review.md` §16, §13, §14 (health + docstring), §11 (`_rpc_http_error`).
**Migrations:** none. Convention (hard rule): named domain exceptions mapped to **fixed** HTTP messages; never `HTTPException(…, f"{exc}")`.

**Allowed files:** `api/tasks/api/commitments.py`, `api/tasks/api/tasks.py`, `api/tasks/api/jobs.py`, `api/events/api/security.py`, `api/initiatives/services/initiatives.py`, `api/index.py`, `api/treasury/api/schemas.py`, `api/chapters/services/onboarding.py`, `api/auth/notifications.py`, `tests/*` for those domains (new files ok), plus the existing config/CORS test file from stream 13 (find it: `grep -rln "FRONTEND_URL" tests/`).

## Task 1 — RV-16-1 (P2, F-064 completion): three error mappers still return raw database text

`api/tasks/api/commitments.py:21-33`, `api/tasks/api/jobs.py:43-56`, `api/events/api/security.py:41-53`.

- [ ] Failing tests first (one per mapper, route-level with dependency-override clients): trigger a known RPC error and assert the HTTP body is the fixed message, **and** that an *unknown* database error comes back as a generic 500 body containing no SQLSTATE/relation/DETAIL text. Today the raw text leaks.
- [ ] Fix each mapper to the pattern the events domain already uses: match known message fragments → fixed text with the right status; anything unrecognised → re-raise/500 with a generic body.
- [ ] Checkpoint: `python3 -m pytest tests/tasks/ tests/events/ -q`.

## Task 2 — RV-16-2 (P2, R-06 completion): removing a non-chair still returns a 500

`api/initiatives/services/initiatives.py:373`: the RPC's "is not a chair" error isn't mapped.

- [ ] Failing test first: `DELETE /api/initiatives/{id}/chairs/{member-who-is-not-a-chair}` → expect 404 (or the domain's existing not-found convention), get 500 today. Then map it. Checkpoint: `python3 -m pytest tests/initiatives/ -q`.

## Task 3 — RV-11-3 (P3): `_rpc_http_error`'s fallback turns *any* unexpected error into a 400 with raw text

`api/tasks/api/tasks.py:108-113`, `api/tasks/api/jobs.py:56`: a database outage becomes a 400 carrying raw text.

- [ ] Failing test first: feed `_rpc_http_error` an unrecognised exception → assert it yields a 500-class result with generic body (today: 400 + raw). Fix the fallback. (Same files as Task 1 — do Task 1 first, this rides on its structure.)

## Task 4 — RV-13-1 (P2, decision D-R1): restore the localhost `FRONTEND_URL` refusal

`api/index.py:108-115`: preview deploys and runs with no `VERCEL_ENV`/`APP_ENV` no longer refuse a localhost `FRONTEND_URL` (the CORS allowlist). The user decided: put the old rule back.

- [ ] Failing test first, in stream 13's config test file: preview env (`VERCEL_ENV=preview`) + `FRONTEND_URL=http://localhost:3000` → boot must refuse; same for both env vars unset. Local/test `APP_ENV` still allows localhost. The stream-13 test that asserted the relaxed behaviour gets inverted (report under EXISTING TESTS CHANGED).
- [ ] Fix in `api/index.py` next to the existing boot guard. Checkpoint: the config test file passes.

## Task 5 — RV-14-1 (P3): fresh instance + database down → `/api/health` 500s

`api/index.py:217`: `get_db()` raises before the health check can answer.

- [ ] Failing test first: monkeypatch `get_db` to raise; `GET /api/health` → expect 503 with a degraded body, get 500 today. Fix: catch inside the health route. Checkpoint with the same test file.

## Task 6 — RV-16-4 (P3): roster import discloses which emails belong to another chapter

`api/chapters/services/onboarding.py:170`: the rejection row names the emails' other-chapter membership — an information leak across tenants.

- [ ] Failing test first: import a CSV containing an email registered to a different chapter → assert the rejection reason is generic ("cannot be invited" style, same text as other rejections), not "belongs to another chapter". Fix the message. Checkpoint: `python3 -m pytest tests/chapters/ -q` (or wherever the onboarding tests live — find with `grep -rln import_roster tests/`).

## Task 7 — RV-16-3 + RV-14-2 (P3): dead code and a false docstring

- [ ] Delete `TreasuryMessage` (`api/treasury/api/schemas.py:11`) after `grep -rn TreasuryMessage api/ greekos/src/ tests/` shows no live use.
- [ ] Fix `api/auth/notifications.py:10-12`: failed code rows do **not** keep their code for Retry under D21 — say what actually happens.
- [ ] Final checkpoint: `python3 -m pytest tests/tasks/ tests/initiatives/ tests/treasury/ -q` — paste the final count line.
