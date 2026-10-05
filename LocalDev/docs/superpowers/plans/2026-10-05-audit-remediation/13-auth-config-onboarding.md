# 13 · Auth, config and onboarding: codes die with the password, the guard fails closed, signup is atomic

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `13-auth-config-onboarding` · **Wave:** 2 (needs 01 and 02 merged) · **Agent:** GPT-6 Luna medium (Codex CLI) · **Branch:** `fix/audit-13-auth-config`
**Findings:** F-005, F-007, F-020, F-065, R-07, F-011 (chapter creation and roster import)
**Migration:** `0191_auth_code_lifecycle.sql` (0192–0194 spare)
**Goal:** setting a password or redeeming a code kills every other outstanding code and session; the production safety guard is armed everywhere except an explicitly local or test run; the break-glass password script is guarded; creating a chapter or importing a roster either fully happens or does not happen.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-005, F-007, F-020, F-065 and Appendix C.4 (R-07), F-011; decisions D18, D19 in `00-README.md`.

## Facts you can rely on

- `get_db().transaction()` exists (stream 01). Inside the block: use the yielded client for everything, never swallow a database error, and `enqueue(...)` is safe there (it uses `ON CONFLICT DO NOTHING`).
- `_issue_setup_code(sb, *, chapter_id, member_id, event_type=…)` (`api/auth/api/auth.py:132-161`) inserts the code and enqueues the mail using the `sb` it is given.
- Live definitions: `au_set_password` → `0148:119`, `au_bump_token_version` → `0148:147`, `au_consume_setup_code` → `0148:177`, `ch_create_chapter` → `0164` and `ch_import_roster` → `0163` (stream 02 replaced both; the creator is now also an `admin`).
- `settings.is_deployed` (`api/config.py:57-60`) is true only for `VERCEL_ENV in ("production", "preview")`; the boot guard `production_config_violations` (`api/index.py:27-125`), the `/dev-login` lock and the signup limiter all hang off it.

## Global constraints

- Allowed files (repo-root paths where prefixed): `LocalDev/migrations/0191_auth_code_lifecycle.sql`, `LocalDev/api/auth/api/auth.py`, `LocalDev/api/auth/notifications.py`, `LocalDev/api/config.py`, `LocalDev/api/chapters/api/chapters.py`, `LocalDev/api/chapters/services/onboarding.py`, `LocalDev/scripts/set_officer_password.py`, `LocalDev/.env.example`, `LocalDev/conftest.py` (new), `local-dev-scripts/scripts/local-dev.sh` (one line), `.github/workflows/ci.yml` (one line), `LocalDev/tests/auth/**`, `LocalDev/tests/chapters/**`, `LocalDev/tests/config/test_production_guard.py`, `LocalDev/tests/test_set_officer_password.py` (new).
- Shared file, one region only: `LocalDev/api/index.py` → `production_config_violations` (lines ~27-125). Streams 11 and 14 edit other regions of that file.
- DB functions you own this wave: `au_set_password`, `au_bump_token_version`, `au_consume_setup_code`. Keep signatures; `au_consume_setup_code`'s return value gains one key (Task 1).
- Login and redeem response shapes do not change. Route paths do not change.
- Never print or log a secret, a code or a password hash. Never read `LocalDev/.env` values into output.
- Run `python3 -m pytest tests/auth tests/chapters tests/config tests/test_set_officer_password.py -q`. Not the full suite.

## Review focus

1. After a member sets a password, every unused setup or reset code of theirs is dead, including one issued a second earlier.
2. After a code is redeemed, a JWT minted before the redeem is rejected (403 "Session no longer valid").
3. With no `VERCEL_ENV` and no `APP_ENV`, the app refuses to boot with the dev JWT secret. With `APP_ENV=local` or `APP_ENV=test` it boots as today.
4. If sending the setup code fails during chapter creation, no chapter and no officer exist afterwards and the name can be used again.
5. A roster import where the 7th row's code cannot be issued leaves zero imported members.

---

### Task 1: F-005 — codes and sessions follow the password

**Files:** `migrations/0191_auth_code_lifecycle.sql`, `api/auth/api/auth.py:398-510`, `tests/auth/test_code_lifecycle.py` (new; reuse fixtures and helpers from `tests/auth/test_invite_setup_codes.py` and `tests/auth/test_tokens.py`)

- [ ] **Step 1: failing tests.**
  - `test_setting_a_password_burns_unused_codes`: issue two codes for a member (invite, then reset), set a password through the route, then redeem either code → rejected (the route's "invalid or expired code" response).
  - `test_issuing_a_reset_burns_older_codes`: issue code A, issue reset code B; redeeming A is rejected, B works.
  - `test_redeem_revokes_earlier_sessions`: log in (token T1), issue a reset code, redeem it (token T2); `GET /api/auth/me` with T1 → 403, with T2 → 200.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: migration.** Copy each live body and add:
  - `au_set_password` and `au_bump_token_version`: `UPDATE member_setup_codes SET used_at = now() WHERE member_id = p_member_id AND used_at IS NULL;` (check the real column names in `0148:67-79`; use the same "unused" predicate `au_consume_setup_code` uses).
  - `au_consume_setup_code`: after it marks the code used and activates the member, `UPDATE members SET token_version = token_version + 1 WHERE id = <member> RETURNING token_version INTO v_version;`, burn the member's other unused codes with the same statement as above, and add `'token_version', v_version` to the JSONB it returns.
- [ ] **Step 4: route.** `redeem_setup_code` (`auth.py:398-468`) mints the JWT with the `token_version` returned by the RPC instead of the value read before the call. `issue_reset_code` (`:472-510`): call `au_bump_token_version` BEFORE `_issue_setup_code`, so the bump burns the old codes and the new one survives; wrap both in `with sb.transaction() as tx:` and pass `tx` to both.
- [ ] **Step 5: apply (`python3 scripts/migrate_db.py`), run `tests/auth -q`, expect PASS. Checkpoint** — suggested message `fix(auth): a new password or redeemed code invalidates other codes and sessions`.

---

### Task 2: F-007 — the guard fails closed (decision D19)

**Files:** `api/config.py`, `api/index.py` (`production_config_violations` only), `conftest.py` (new, in `LocalDev/`), `local-dev-scripts/scripts/local-dev.sh`, `.github/workflows/ci.yml`, `.env.example`, `tests/config/test_production_guard.py`

Rule: `APP_ENV` is one of `local`, `test`, `preview`, `production`, or empty. The app is "deployed" (guard armed, dev-login locked) unless it is explicitly local or test:

| `VERCEL_ENV` | `APP_ENV` | deployed? |
|---|---|---|
| `production` or `preview` | anything | yes |
| `development` | empty | no (`vercel dev`) |
| empty | `local` or `test` | no |
| empty | `preview` or `production` | yes |
| empty | empty | **yes** (was: no) |

- [ ] **Step 1: failing tests** in `test_production_guard.py`. The existing `test_dev_is_never_guarded` (line ~187) asserts the old rule: rewrite it as `test_explicit_local_is_not_guarded` (`APP_ENV="local"`, dev defaults → no violations) and add `test_unlabelled_environment_is_guarded` (`VERCEL_ENV=""`, `APP_ENV=""`, dev JWT secret → violations include `JWT_SECRET`), `test_app_env_production_is_guarded_without_vercel`, `test_vercel_development_is_not_guarded`, `test_production_rejects_localhost_urls` (`VERCEL_ENV="production"` with `BASE_URL` or `FRONTEND_URL` containing `localhost` → a violation naming the variable), `test_preview_allows_localhost_urls`.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement.**
  - `api/config.py`: add `APP_ENV: str = ""`. Replace the two properties:

```python
    @property
    def is_production(self) -> bool:
        return self.VERCEL_ENV == "production" or (not self.VERCEL_ENV and self.APP_ENV == "production")

    @property
    def is_deployed(self) -> bool:
        # Fail closed (F-007): anything not explicitly local or test gets the
        # production config guard and the dev-login lock.
        if self.VERCEL_ENV in ("production", "preview"):
            return True
        if self.VERCEL_ENV == "development":
            return False
        return self.APP_ENV not in ("local", "test")
```

  - `production_config_violations`: after the existing checks add, for `s.is_production` only: a violation when `"localhost" in s.BASE_URL or "127.0.0.1" in s.BASE_URL` ("BASE_URL points at localhost — set it to the public API origin"), and the same for `FRONTEND_URL` ("…set it to the public site origin; check-in links redirect there").
  - `LocalDev/conftest.py`:

```python
"""Root conftest: mark the process as a test run before api.config is imported (F-007)."""
import os

os.environ.setdefault("APP_ENV", "test")
```

  - `local-dev-scripts/scripts/local-dev.sh`: near the top, after the shebang and `set` lines, add `export APP_ENV="${APP_ENV:-local}"`.
  - `.github/workflows/ci.yml`: in the backend job's `.env` heredoc add the line `APP_ENV=test`.
- [ ] **Step 4: check every place that reads the old meaning:** `grep -rn "is_deployed\|is_production\|VERCEL_ENV" api scripts tests`. Each use must still be right under the new rule (dev-login in `api/auth/api/auth.py:272-299`, the limiter in `api/chapters/auth.py`). Tests that construct `Settings(...)` without `APP_ENV` and expect "not deployed" need `APP_ENV="local"`; list them in the report.
- [ ] **Step 5: run `tests/config tests/auth tests/chapters -q`, then `python3 -c "import api.index"` with `APP_ENV=local` in the environment → no error; and with `APP_ENV=` empty and `JWT_SECRET=local-dev-secret` → it must raise the guard error. Checkpoint** — `fix(config): the production guard is armed unless APP_ENV says local or test`.

---

### Task 3: R-07 — `.env.example` matches `Settings`

**Files:** `.env.example`, `tests/config/test_env_example.py` (new)

- [ ] **Step 1: failing test:** every field name declared on `api.config.Settings` appears as a `NAME=` line (commented or not) in `.env.example`, and every `NAME=` line in `.env.example` is a `Settings` field or one of the test-only names `TEST_DATABASE_URL`, `SUPABASE_DB_URL`, `PROD_DATABASE_URL`. Read names with `Settings.model_fields`.
- [ ] **Step 2: run, expect FAIL** (at least `PLATFORM_SECRET`, `TRUSTED_PROXY_HOPS`, `APP_ENV` missing).
- [ ] **Step 3:** add the missing names with a one-line comment each and a safe placeholder (empty for secrets, `APP_ENV=local`). Remove names nothing reads. Do not copy any value from `.env`.
- [ ] **Step 4: run, expect PASS. Checkpoint** — `docs(config): .env.example lists exactly the settings the app reads`. Under "Human follow-up" in your report: "LocalDev/.env still carries nine unused names (ESCALATION_DELAY_MINUTES, FEATURE_SECRETARY_COMMS, FEATURE_VP_OPERATIONS, MESSAGE_WEBHOOK_SECRET, SENDGRID_API_KEY, SENDGRID_FROM_EMAIL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL); delete them by hand. Add APP_ENV=local to LocalDev/.env."

---

### Task 4: F-020 — guard the break-glass password script

**Files:** `scripts/set_officer_password.py`, `tests/test_set_officer_password.py`

- [ ] **Step 1: read** `scripts/set_officer_password.py` (61 lines), `scripts/db_guard.py` (`require_demo`, `require_prod`, `confirmation_matches`) and how `scripts/migrate_db.py:100-125` uses them for `--prod`.
- [ ] **Step 2: failing tests** (pure, no DB: extract the SQL and the guard choice into functions): `test_refuses_a_non_demo_url_without_prod_flag` (a URL that `require_demo` rejects → `SystemExit`); `test_update_statement_bumps_token_version_and_burns_codes` (the statements the script will run contain `token_version = token_version + 1` and an update of `member_setup_codes`); `test_matches_by_email_only` (no `role = 'officer'` filter).
- [ ] **Step 3: implement.** Default: `require_demo(url, context="set_officer_password")`. With `--prod`: read `PROD_DATABASE_URL`, `require_prod(url)`, and require the typed project-ref confirmation exactly as `migrate_db.py` does. One transaction: `UPDATE members SET password_hash = %s, token_version = token_version + 1 WHERE email = %s RETURNING id, name`, then `UPDATE member_setup_codes SET used_at = now() WHERE member_id = %s AND used_at IS NULL`. Print the matched member's name and id, never the hash.
- [ ] **Step 4: run, expect PASS. Checkpoint** — `fix(scripts): set_officer_password is demo-guarded and revokes sessions`.

---

### Task 5: F-011 — chapter creation and roster import are all-or-nothing

**Files:** `api/chapters/services/onboarding.py:56-84, 150-185`, `tests/chapters/test_create_chapter.py`, `tests/chapters/test_roster_import.py`

- [ ] **Step 1: failing tests.**
  - `test_chapter_creation_rolls_back_when_the_code_cannot_be_issued`: monkeypatch `api.chapters.services.onboarding._issue_setup_code` to raise `RuntimeError`; call the create service (or the route) and expect the error; afterwards no chapter with that name and no member with that email exist; creating the same chapter again (patch removed) succeeds.
  - `test_roster_import_rolls_back_when_a_code_cannot_be_issued`: patch `_issue_setup_code` to raise on its third call; import five rows; expect the error; zero of the five emails exist as members.
- [ ] **Step 2: run, expect FAIL** (chapter exists; some members exist).
- [ ] **Step 3: implement.** In the chapter-creation function (lines ~56-84) wrap the `ch_create_chapter` RPC call, the consent update and `_issue_setup_code` in `with sb.transaction() as tx:` and pass `tx` to all three (`call_rpc(..., sb=tx)`). In the roster import (lines ~150-185) wrap the `ch_import_roster` RPC and the per-member `_issue_setup_code` loop the same way. Reads that happen before (role catalog, CSV parsing) stay outside. `notify_code` (`api/auth/notifications.py:31-59`) catches every exception so an invite survives a mail-queue hiccup; inside a transaction that would hide an aborted transaction. Change its `except Exception` to re-raise when the client is a transaction client (`getattr(getattr(sb, "_pool", None), "in_tx", False)`) and keep today's log-and-continue otherwise. If the route or a test passes a client without `.transaction()` (a fake), report it; do not add a fallback path.
- [ ] **Step 4: run `tests/chapters tests/auth -q`, expect PASS. Checkpoint** — `fix(chapters): chapter creation and roster import commit as one transaction`.

---

### Task 6: F-065 — the signup conflict message stops naming the field (decision D18)

**Files:** `api/chapters/api/chapters.py:51-57`, `tests/chapters/test_create_chapter.py`

- [ ] **Step 1: failing test:** creating a chapter with an email that already belongs to a member, and creating one with a chapter name that is taken, both return 409 with the identical body `{"detail": "A chapter or member with these details already exists."}`.
- [ ] **Step 2: implement:** both conflict branches raise that one message. Leave the in-process limiter alone (report §10 lists it as a deliberate choice).
- [ ] **Step 3: run, expect PASS. Checkpoint** — `fix(chapters): signup conflicts no longer say whether an email is registered`.

## Report

Finish with the report block from `00-README.md` ("What to hand back"). Under "Human follow-up" also list: "Before the next production deploy, set BASE_URL and FRONTEND_URL in Vercel to the public origins, or the app will refuse to boot."
