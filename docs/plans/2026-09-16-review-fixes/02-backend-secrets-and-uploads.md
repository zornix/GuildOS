# 02 — Backend: code payloads, Sentry locals, CSV upload size

Branch `fix/review-secrets-uploads`. Read `00-README.md` first. All paths are
under `LocalDev/`.

## Fix M3 — setup/reset codes stay in the database forever

**Problem.** `api/auth/notifications.py` stores the plaintext code in
`message_outbox.payload`. The drain never clears it, so every code ever issued
sits readable in the table.

**Steps**
1. Test first in `tests/cron/test_drain_email.py` (follow its fixtures):
   - drain a `SETUP_CODE` row to `sent` (or `simulated` in dry-run) → the row's
     `payload` no longer contains `"code"`;
   - drain a non-secret row (e.g. `EVENT_CREATED`) → payload untouched;
   - a `SETUP_CODE` row that ends `failed` keeps its payload (Retry must still
     render it).
2. In `api/cron/services/outbox_drain.py::_close_row`, after building `patch`:
   ```python
   if status in ("sent", "simulated") and row["event_type"] in _SECRET_EVENT_TYPES:
       # The payload is a live credential (api/auth/notifications.py); once the
       # mail is out there is no reason to keep it. `payload` is NOT NULL.
       patch["payload"] = {}
   ```
   Define `_SECRET_EVENT_TYPES` by importing `SETUP_CODE, RESET_CODE` from
   `api.auth.notifications` (check for an import cycle; if there is one, define
   the set locally with a comment naming the source).
3. Confirm the officer outbox list still works for a wiped row:
   `api/announcements/services/outbox.py::_body` already returns
   "Account code (hidden)." for these types without reading the payload. No
   change expected — just verify.
4. Update the module docstring in `api/auth/notifications.py`: the payload is
   wiped once the mail is sent.
5. `python3 -m pytest tests/cron/ tests/auth/` — all green.

**Commit:** `Wipe the setup or reset code from the outbox once it is sent`

## Fix M4 — SMTP password and code bodies can reach Sentry

**Problem.** `api/observability.py::_configure_sentry` calls `sentry_sdk.init`
with the default `include_local_variables=True`. An SMTP failure logged with
`logger.exception` ships frame locals — the SMTP password and rendered
setup-code bodies — to Sentry.

**Steps**
1. Add to the `sentry_sdk.init(...)` call:
   ```python
   # Frame locals include the SMTP password and rendered setup-code bodies.
   include_local_variables=False,
   ```
2. If `tests/` already has a test for `_configure_sentry` (grep
   `_configure_sentry` / `sentry` under `tests/`), extend it to assert the
   kwarg. If none exists, add one small test that monkeypatches
   `sentry_sdk.init` (and `settings.SENTRY_DSN`, and resets
   `_sentry_configured`) and asserts `include_local_variables is False`. Skip
   the test with `pytest.importorskip("sentry_sdk")`.
3. `python3 -m pytest tests/<wherever that test lives>` — green.

**Commit:** `Keep frame locals out of Sentry so SMTP secrets never leave the box`

## Fix M6 — roster CSV size limit is checked after reading the whole file

**Problem.** `api/chapters/api/chapters.py::import_roster_endpoint` does
`raw = await file.read()` and only then compares to `MAX_ROSTER_BYTES`, so the
limit never stops a huge upload being buffered.

**Steps**
1. Test first in `tests/chapters/test_roster_import.py`: upload
   `MAX_ROSTER_BYTES + 1` bytes → 413. (One may exist already; if so, keep it
   and add nothing — the behaviour is the same, only the memory use changes.)
2. Replace the read + check with a bounded read:
   ```python
   if file.size is not None and file.size > MAX_ROSTER_BYTES:
       raise HTTPException(413, "Roster file is too large")
   raw = await file.read(MAX_ROSTER_BYTES + 1)
   if len(raw) > MAX_ROSTER_BYTES:
       raise HTTPException(413, "Roster file is too large")
   ```
   `file.size` can be `None` (chunked upload), which is why the bounded read
   stays as the backstop.
3. `python3 -m pytest tests/chapters/` — all green.

**Commit:** `Stop reading a roster upload once it is past the size limit`
