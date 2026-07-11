# Prod-DB Write Guards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make pytest, `npm run seed`, and the demo-migrate paths refuse to touch any database that isn't the known demo (fail-closed), and make prod migration a separate, explicitly confirmed `npm run migrate:prod` command.

**Architecture:** One new pure module, `scripts/db_guard.py`, holds checked-in Supabase project refs and pure URL-classification functions. Every writer entry point (`tests/treasury/conftest.py`, `scripts/seed.py`, `scripts/migrate_db.py`) calls it *before* opening any connection. No database-side changes, no new dependencies.

**Tech Stack:** Python 3 stdlib only (`urllib.parse`, `argparse`), pytest for unit tests. No new pip packages.

**Spec:** `docs/superpowers/specs/2026-07-11-prod-db-write-guards-design.md`

## Global Constraints

- All commands run from `LocalDev/` (`/home/mshi/GuildOS/LocalDev`).
- `scripts/db_guard.py` must stay **pure — no I/O, no imports of psycopg2, no reading `.env`**. Callers resolve URLs; the guard only classifies strings.
- Every refusal happens **before** `psycopg2.connect` — no socket is ever opened against a refused database.
- Error messages must **never contain a password or full connection URL** — only username/host/port via `redact()`. Project refs are identifiers, not credentials, and are safe to print and to commit.
- The demo project ref is `kikzdpfpprfkkbmcwnhm` (read from the current `LocalDev/.env` on 2026-07-11) — hard-code it in `db_guard.py`.
- `PROD_PROJECT_REFS` ships as an **empty frozenset with a clearly marked human TODO** — the prod ref is not discoverable from this repo and must be filled in by a human. Do not invent a value.
- Existing behavior to preserve: pytest still *skips* DB tests when no URL is set (guard only fires when a URL **is** set); `npm run migrate` output stays the same on the happy path.
- Commit per task with conventional-commit messages (`feat(scripts): …`, `test: …`, `docs(db): …`). **Never add Co-Authored-By / "Generated with Claude" trailers.**
- Do not touch `migrations/*.sql`, and do not modify any file under `Prod/`.

## Verified codebase facts (so you don't have to re-derive them)

- `npm run migrate` = `with-demo-db.sh python3 scripts/migrate_db.py`; the wrapper exports `DATABASE_URL` resolved from `.env` (`TEST_DATABASE_URL` → `SUPABASE_DB_URL` → `DATABASE_URL`). `npm run dev` auto-migrate runs `DATABASE_URL="$MIGRATE_DB_URL" python3 scripts/migrate_db.py`. So guarding `migrate_db.py`'s default path covers all demo-migrate entry points.
- `npm run seed` = `with-demo-db.sh python3 -m scripts.seed`; `npm run dev:seed` also runs `python3 -m scripts.seed` with a Docker-local URL. Guarding `scripts/seed.py` covers both.
- Every domain test package's `conftest.py` does `from tests.treasury.conftest import *`, so the session-scoped `db_url` fixture in `tests/treasury/conftest.py` is the single place all DB-backed tests get their URL.
- `scripts/` has no `__init__.py` — it works as a namespace package. `python3 -m scripts.seed` and `python3 -m pytest` (run from `LocalDev/`, cwd on `sys.path`) can both import `scripts.db_guard`. `python3 scripts/migrate_db.py` (run as a file) **cannot** — Task 4 adds a `sys.path` insert there.
- A Supabase pooler URL carries the project ref as the *username*: `postgres.<project-ref>`.
- The Docker-local URL is `postgresql://fraternityos:localdev@localhost:5434/fraternityos` (must classify as `local`).

---

### Task 1: `scripts/db_guard.py` — pure guard module with unit tests

**Files:**
- Create: `scripts/db_guard.py`
- Test: `tests/test_db_guard.py`

**Interfaces:**
- Produces (later tasks import exactly these names from `scripts.db_guard`):
  - `DEMO_PROJECT_REF: str`
  - `PROD_PROJECT_REFS: frozenset[str]`
  - `class ProdGuardError(RuntimeError)`
  - `classify_url(url: str) -> str` — returns `"local" | "demo" | "prod" | "unknown"`
  - `redact(url: str) -> str`
  - `project_ref(url: str) -> str | None`
  - `require_demo(url: str, *, context: str) -> None` — raises `ProdGuardError`
  - `require_prod(url: str) -> None` — raises `ProdGuardError`
  - `confirmation_matches(typed: str, url: str) -> bool`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db_guard.py` with exactly this content:

```python
"""Unit tests for scripts/db_guard.py — pure string checks, no database needed."""

import pytest

from scripts import db_guard
from scripts.db_guard import (
    ProdGuardError,
    classify_url,
    confirmation_matches,
    project_ref,
    redact,
    require_demo,
    require_prod,
)

DEMO_URL = (
    f"postgresql://postgres.{db_guard.DEMO_PROJECT_REF}:secret-pw"
    "@aws-0-us-west-2.pooler.supabase.com:6543/postgres"
)
PROD_REF = "prodref0123456789ab"
PROD_URL = (
    f"postgresql://postgres.{PROD_REF}:secret-pw"
    "@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
)
DOCKER_URL = "postgresql://fraternityos:localdev@localhost:5434/fraternityos"
UNKNOWN_URL = (
    "postgresql://postgres.someoneelsesref:secret-pw"
    "@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
)


@pytest.fixture
def with_prod_ref(monkeypatch):
    """PROD_PROJECT_REFS ships empty (human fills it in); tests patch it."""
    monkeypatch.setattr(db_guard, "PROD_PROJECT_REFS", frozenset({PROD_REF}))


# ── classify_url ─────────────────────────────────────────────────────────

def test_classify_demo():
    assert classify_url(DEMO_URL) == "demo"


def test_classify_local_docker():
    assert classify_url(DOCKER_URL) == "local"


def test_classify_local_loopback_and_docker_hosts():
    for host in ("127.0.0.1", "host.docker.internal"):
        assert classify_url(f"postgresql://u:p@{host}:5432/db") == "local"


def test_classify_unknown():
    assert classify_url(UNKNOWN_URL) == "unknown"


def test_classify_unknown_for_garbage():
    assert classify_url("not a url at all") == "unknown"


def test_classify_prod(with_prod_ref):
    assert classify_url(PROD_URL) == "prod"


def test_classify_prod_wins_over_local_hostname(with_prod_ref):
    # A URL containing a prod ref is prod no matter what the host looks like.
    assert classify_url(f"postgresql://postgres.{PROD_REF}:pw@localhost:5432/db") == "prod"


def test_classify_prod_empty_refs_means_never_prod():
    # Until a human fills PROD_PROJECT_REFS, nothing classifies as prod...
    assert classify_url(PROD_URL) == "unknown"
    # ...which is still refused by require_demo (fail closed), see below.


# ── require_demo (fail-closed allowlist) ─────────────────────────────────

def test_require_demo_allows_demo_and_local():
    require_demo(DEMO_URL, context="test")
    require_demo(DOCKER_URL, context="test")


def test_require_demo_rejects_unknown():
    with pytest.raises(ProdGuardError):
        require_demo(UNKNOWN_URL, context="test")


def test_require_demo_rejects_prod(with_prod_ref):
    with pytest.raises(ProdGuardError):
        require_demo(PROD_URL, context="test")


def test_require_demo_error_is_redacted(with_prod_ref):
    with pytest.raises(ProdGuardError) as exc:
        require_demo(PROD_URL, context="pytest")
    msg = str(exc.value)
    assert "secret-pw" not in msg
    assert "pytest" in msg  # context is named so the operator knows what refused


# ── require_prod ─────────────────────────────────────────────────────────

def test_require_prod_accepts_prod(with_prod_ref):
    require_prod(PROD_URL)


def test_require_prod_rejects_demo_local_unknown(with_prod_ref):
    for url in (DEMO_URL, DOCKER_URL, UNKNOWN_URL):
        with pytest.raises(ProdGuardError):
            require_prod(url)


def test_require_prod_refuses_when_refs_unfilled():
    # Placeholder not yet filled by a human → migrate:prod must refuse to run.
    with pytest.raises(ProdGuardError) as exc:
        require_prod(PROD_URL)
    assert "PROD_PROJECT_REFS" in str(exc.value)


# ── redact / project_ref ─────────────────────────────────────────────────

def test_redact_strips_password():
    out = redact(DEMO_URL)
    assert "secret-pw" not in out
    assert db_guard.DEMO_PROJECT_REF in out
    assert "pooler.supabase.com" in out


def test_redact_survives_garbage():
    assert "secret" not in redact("::::not::a::url")


def test_project_ref_extraction():
    assert project_ref(DEMO_URL) == db_guard.DEMO_PROJECT_REF
    assert project_ref(DOCKER_URL) is None


# ── confirmation_matches (migrate:prod typed confirmation) ───────────────

def test_confirmation_accepts_exact_ref(with_prod_ref):
    assert confirmation_matches(PROD_REF, PROD_URL) is True


def test_confirmation_accepts_surrounding_whitespace(with_prod_ref):
    assert confirmation_matches(f"  {PROD_REF}\n", PROD_URL) is True


def test_confirmation_rejects_everything_else(with_prod_ref):
    for typed in ("", "yes", "y", PROD_REF[:-1], PROD_REF.upper()):
        assert confirmation_matches(typed, PROD_URL) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_db_guard.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'scripts.db_guard'`

- [ ] **Step 3: Write the guard module**

Create `scripts/db_guard.py` with exactly this content:

```python
"""Guards that keep test data and stray migrations out of prod.

Pure string checks — no I/O, no psycopg2, no reading of .env. Every writer
entry point (pytest conftest, scripts/seed.py, scripts/migrate_db.py) imports
from here, so the project-ref lists live in exactly one place. The refs are
checked in deliberately: the guard must work even when a mispointed `.env`
is the bug. A project ref is an identifier, not a credential.

Spec: docs/superpowers/specs/2026-07-11-prod-db-write-guards-design.md
"""

from __future__ import annotations

from urllib.parse import urlsplit

# The demo Supabase project's ref (the username in a pooler URL is
# `postgres.<project-ref>`).
DEMO_PROJECT_REF = "kikzdpfpprfkkbmcwnhm"

# ── HUMAN ACTION REQUIRED ─────────────────────────────────────────────────
# Fill in the production project ref(s) from the Supabase dashboard
# (production project → Settings → General → Reference ID), e.g.
#   PROD_PROJECT_REFS: frozenset[str] = frozenset({"abcdefghijklmnopqrst"})
# Until this is filled, `npm run migrate:prod` refuses to run at all; the
# fail-closed demo guards already protect prod (any URL that is not the demo
# ref or a local host is refused).
PROD_PROJECT_REFS: frozenset[str] = frozenset()

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})


class ProdGuardError(RuntimeError):
    """A command tried to touch a database it must not. Message is redacted."""


def project_ref(url: str) -> str | None:
    """The `<ref>` of a `postgres.<ref>` pooler username, else None."""
    try:
        username = urlsplit(url).username
    except ValueError:
        return None
    if username and username.startswith("postgres."):
        return username.partition(".")[2] or None
    return None


def redact(url: str) -> str:
    """Username + host + port only — never the password, never the full URL."""
    try:
        parts = urlsplit(url)
        user = parts.username or "?"
        host = parts.hostname or "?"
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return "<unparseable database URL>"
    return f"{user}@{host}{port}"


def classify_url(url: str) -> str:
    """Classify a connection URL: 'local' | 'demo' | 'prod' | 'unknown'.

    Pure string match, most dangerous first: a URL containing a known prod
    ref is 'prod' regardless of anything else about it.
    """
    if any(ref in url for ref in PROD_PROJECT_REFS):
        return "prod"
    if DEMO_PROJECT_REF in url:
        return "demo"
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return "unknown"
    if host in _LOCAL_HOSTS:
        return "local"
    return "unknown"


def require_demo(url: str, *, context: str) -> None:
    """Allow demo/local; refuse prod AND unknown (fail closed).

    Used by pytest, seed, and the ordinary migrate path. Anything that is not
    recognizably the demo or a local database — a mistyped ref, a brand-new
    prod, a teammate's database — is treated as unsafe.
    """
    kind = classify_url(url)
    if kind in ("demo", "local"):
        return
    raise ProdGuardError(
        f"{context}: refusing to touch {kind} database at {redact(url)} — "
        f"only the demo project ({DEMO_PROJECT_REF}) or a local database "
        "is allowed. Check DATABASE_URL/TEST_DATABASE_URL in LocalDev/.env."
    )


def require_prod(url: str) -> None:
    """Refuse anything that is not a known prod ref.

    Used only by `migrate_db.py --prod`, so migrate:prod cannot silently
    target the demo (or anything else) either.
    """
    if not PROD_PROJECT_REFS:
        raise ProdGuardError(
            "PROD_PROJECT_REFS in scripts/db_guard.py is empty — a human must "
            "fill in the production project ref before migrate:prod can run."
        )
    if classify_url(url) != "prod":
        raise ProdGuardError(
            f"migrate:prod: {redact(url)} is not a known prod database — "
            "check PROD_DATABASE_URL against PROD_PROJECT_REFS in scripts/db_guard.py."
        )


def confirmation_matches(typed: str, url: str) -> bool:
    """True iff the operator typed exactly the project ref of `url`.

    The typed-confirmation gate for migrate:prod, factored out pure so it is
    testable without a TTY.
    """
    ref = project_ref(url)
    return ref is not None and typed.strip() == ref
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_db_guard.py -v`
Expected: all 21 tests PASS

- [ ] **Step 5: Make sure the rest of the suite still collects**

Run: `python3 -m pytest --collect-only -q | tail -5`
Expected: no collection errors (count of collected tests, no tracebacks)

- [ ] **Step 6: Commit**

```bash
git add scripts/db_guard.py tests/test_db_guard.py
git commit -m "feat(scripts): add db_guard — checked-in ref allowlist for prod write protection"
```

---

### Task 2: Guard pytest at the `db_url` fixture chokepoint

**Files:**
- Modify: `tests/treasury/conftest.py` (the `db_url` fixture, lines 52–57, plus imports at top)

**Interfaces:**
- Consumes: `require_demo(url, *, context)`, `ProdGuardError` from `scripts.db_guard` (Task 1).
- Produces: unchanged fixture signature — `db_url` still session-scoped, still skips when unset; every domain conftest star-imports this file, so no other test file changes.

- [ ] **Step 1: Add the guarded import**

In `tests/treasury/conftest.py`, the current top of the module ends with:

```python
_REPO_ROOT = Path(__file__).resolve().parents[2]
```

Immediately after that line, add:

```python
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.db_guard import ProdGuardError, require_demo
```

and add `import sys` to the stdlib imports at the top of the file (next to `import os`).

- [ ] **Step 2: Guard the fixture**

Replace the existing fixture:

```python
@pytest.fixture(scope="session")
def db_url() -> str:
    url = _test_database_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL / SUPABASE_DB_URL not set — DB-backed tests skipped")
    return url
```

with:

```python
@pytest.fixture(scope="session")
def db_url() -> str:
    url = _test_database_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL / SUPABASE_DB_URL not set — DB-backed tests skipped")
    try:
        require_demo(url, context="pytest")
    except ProdGuardError as exc:
        # Stop the whole session before ANY test opens a connection — a test
        # run against prod would write permanent rows into append-only tables.
        pytest.exit(str(exc), returncode=1)
    return url
```

- [ ] **Step 3: Verify the guard fires on a non-demo URL**

Run (fake ref, aborts before any connection — safe):

```bash
TEST_DATABASE_URL="postgresql://postgres.notourdemoref:pw@aws-0-us-west-2.pooler.supabase.com:6543/postgres" \
  python3 -m pytest tests/treasury/test_chunk0_foundations.py -x 2>&1 | tail -5
```

Expected: session exits immediately with `pytest: refusing to touch unknown database at postgres.notourdemoref@aws-0-us-west-2.pooler.supabase.com:6543 — …` and **no test runs**. The password `pw` must not appear in the output.

- [ ] **Step 4: Verify the real suite still runs on the demo**

Run: `python3 -m pytest tests/treasury/test_chunk0_foundations.py -q`
Expected: passes (or skips if `.env` has no URL) exactly as before this change.

- [ ] **Step 5: Commit**

```bash
git add tests/treasury/conftest.py
git commit -m "test: fail-closed prod guard in the shared db_url fixture"
```

---

### Task 3: Guard the seeder

**Files:**
- Modify: `scripts/seed.py` (imports near line 17, and the top of `seed()` near line 180)

**Interfaces:**
- Consumes: `require_demo`, `ProdGuardError` from `scripts.db_guard` (Task 1).

- [ ] **Step 1: Import the guard**

`scripts/seed.py` already inserts the repo root into `sys.path` (line 15) before defining `DATABASE_URL`. Immediately **after** the existing line:

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

add:

```python
from scripts.db_guard import ProdGuardError, require_demo
```

- [ ] **Step 2: Guard before connecting**

The current start of `seed()` is:

```python
def seed():
    conn = psycopg2.connect(DATABASE_URL)
```

Change it to:

```python
def seed():
    try:
        require_demo(DATABASE_URL, context="seed")
    except ProdGuardError as exc:
        sys.exit(f"error: {exc}")

    conn = psycopg2.connect(DATABASE_URL)
```

- [ ] **Step 3: Verify refusal on a non-demo URL (no connection attempted)**

```bash
DATABASE_URL="postgresql://postgres.notourdemoref:pw@aws-0-us-west-2.pooler.supabase.com:6543/postgres" \
  python3 -m scripts.seed; echo "exit=$?"
```

Expected: single redacted error line (`error: seed: refusing to touch unknown database …`), `exit=1`, no psycopg2 connection error/timeout (proving it refused *before* connecting), and no `pw` in the output.

- [ ] **Step 4: Verify the guard passes for demo/local without seeding**

```bash
python3 -c "
from scripts.db_guard import require_demo
require_demo('postgresql://fraternityos:localdev@localhost:5434/fraternityos', context='seed')
print('local ok')
"
```

Expected: `local ok`. (Don't run a real `npm run seed` here — reseeding the shared demo is disruptive and unnecessary; the demo-URL classification is already unit-tested in Task 1.)

- [ ] **Step 5: Commit**

```bash
git add scripts/seed.py
git commit -m "feat(scripts): seed refuses any non-demo database"
```

---

### Task 4: Guard the default migrate path

**Files:**
- Modify: `scripts/migrate_db.py` (imports after line 22, and `main()` at line 59)

**Interfaces:**
- Consumes: `require_demo`, `ProdGuardError` from `scripts.db_guard` (Task 1).
- Produces: `REPO_ROOT` `sys.path` bootstrap in `migrate_db.py` that Task 5 builds on.

- [ ] **Step 1: Make `scripts.db_guard` importable when run as a file**

`migrate_db.py` runs as `python3 scripts/migrate_db.py` (both npm wrappers do this), so `sys.path[0]` is `scripts/`, not the repo root. The file currently has:

```python
import psycopg2

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"
```

Change that block to:

```python
import psycopg2

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.db_guard import ProdGuardError, require_demo
```

- [ ] **Step 2: Guard `main()` before connecting**

The current start of `main()` is:

```python
def main() -> None:
    url = _database_url()
```

Change it to:

```python
def main() -> None:
    url = _database_url()

    try:
        require_demo(url, context="migrate")
    except ProdGuardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 3: Verify refusal on a non-demo URL**

```bash
DATABASE_URL="postgresql://postgres.notourdemoref:pw@aws-0-us-west-2.pooler.supabase.com:6543/postgres" \
  python3 scripts/migrate_db.py; echo "exit=$?"
```

Expected: `error: migrate: refusing to touch unknown database at postgres.notourdemoref@…`, `exit=1`, no connection attempt, no `pw` in output.

- [ ] **Step 4: Verify the demo path still works**

Run: `npm run migrate`
Expected: `schema_migrations: already up to date` (unchanged happy-path output).

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_db.py
git commit -m "feat(scripts): demo migrate path refuses any non-demo database"
```

---

### Task 5: `--prod` migrate path with typed confirmation, plus wiring

**Files:**
- Modify: `scripts/migrate_db.py` (restructure `main()`; add `--prod` / `--yes`; add `_env_value`)
- Modify: `package.json` (add `migrate:prod` script)
- Modify: `.env.example` (document `PROD_DATABASE_URL`)

**Interfaces:**
- Consumes: `require_prod`, `confirmation_matches`, `redact`, `ProdGuardError` from `scripts.db_guard` (Task 1); the import bootstrap from Task 4.
- Produces: `npm run migrate:prod` → `python3 scripts/migrate_db.py --prod`; reads **only** `PROD_DATABASE_URL` (env, falling back to `LocalDev/.env`), never `DATABASE_URL`.

- [ ] **Step 1: Extend the guard import (from Task 4) to the prod helpers**

In `scripts/migrate_db.py`, change:

```python
from scripts.db_guard import ProdGuardError, require_demo
```

to:

```python
from scripts.db_guard import (
    ProdGuardError,
    confirmation_matches,
    redact,
    require_demo,
    require_prod,
)
```

and add `import argparse` to the stdlib imports (next to `import os`).

- [ ] **Step 2: Add arg parsing and a `.env`-fallback reader**

`npm run migrate:prod` will invoke the script directly (no `with-demo-db.sh` wrapper), so `.env` values are not exported; the script reads `PROD_DATABASE_URL` itself. Add these two functions right after `_database_url()`:

```python
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply pending SQL migrations.")
    parser.add_argument(
        "--prod",
        action="store_true",
        help="migrate the production database (reads PROD_DATABASE_URL only)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the interactive prod confirmation (CI)",
    )
    return parser.parse_args()


def _env_value(key: str) -> str:
    """Read a key from the process env, falling back to LocalDev/.env."""
    value = os.environ.get(key, "").strip()
    if value:
        return value
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith(f"{key}="):
                return line.partition("=")[2].strip().strip('"')
    return ""
```

- [ ] **Step 3: Restructure `main()`**

Replace the entire `main()` function with:

```python
def main() -> None:
    args = _parse_args()

    if args.prod:
        url = _env_value("PROD_DATABASE_URL")
        if not url:
            print(
                "error: set PROD_DATABASE_URL (env or LocalDev/.env) — "
                "it is read only by migrate:prod, never by dev/test",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            require_prod(url)
        except ProdGuardError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        url = _database_url()
        try:
            require_demo(url, context="migrate")
        except ProdGuardError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

    if not MIGRATIONS_DIR.is_dir():
        print(f"error: migrations directory missing: {MIGRATIONS_DIR}", file=sys.stderr)
        sys.exit(1)

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print("no migrations/*.sql files found", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(url)

    try:
        conn.autocommit = False

        with conn.cursor() as cur:
            _ensure_migrations_table(cur)
        conn.commit()

        with conn.cursor() as cur:
            applied = _applied_names(cur)

        pending = [f for f in files if f.name not in applied]
        if not pending:
            print("schema_migrations: already up to date")
            return

        if args.prod:
            print(f"target: {redact(url)} (PROD)")
            print(f"pending migrations ({len(pending)}):")
            for path in pending:
                print(f"  {path.name}")
            if not args.yes:
                try:
                    typed = input("Type the prod project ref to apply them: ")
                except EOFError:
                    print("error: no confirmation input — nothing applied", file=sys.stderr)
                    sys.exit(1)
                if not confirmation_matches(typed, url):
                    print("error: confirmation mismatch — nothing applied", file=sys.stderr)
                    sys.exit(1)

        for path in pending:
            sql = _read_sql(path)
            if not sql:
                print(f"skip empty migration: {path.name}")
                continue

            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (name) VALUES (%s)",
                        (path.name,),
                    )
                conn.commit()
                print(f"applied: {path.name}")
            except Exception:
                conn.rollback()
                print(f"failed: {path.name}", file=sys.stderr)
                raise

        print("done.")

    finally:
        conn.close()
```

(The migration-apply loop is byte-identical to the current one; the changes are the arg-dependent URL resolution at the top and the prod pending-list + confirmation block. The confirmation itself is `confirmation_matches`, already unit-tested in Task 1.)

- [ ] **Step 4: Wire `npm run migrate:prod`**

In `package.json`, after the `"migrate"` line, add:

```json
"migrate:prod": "python3 scripts/migrate_db.py --prod",
```

- [ ] **Step 5: Document `PROD_DATABASE_URL` in `.env.example`**

In `.env.example`, immediately after the `TEST_DATABASE_URL=` line, add:

```bash
# ── PROD migrations ONLY ──────────────────────────────────────────────────
# Read exclusively by `npm run migrate:prod` (scripts/migrate_db.py --prod).
# Dev, tests, and seed NEVER read this. Leave commented unless migrating prod.
# PROD_DATABASE_URL=postgresql://postgres.<prod-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:6543/postgres
```

- [ ] **Step 6: Verify the prod path fail-closes end to end**

Missing URL:

```bash
python3 scripts/migrate_db.py --prod; echo "exit=$?"
```

Expected: `error: set PROD_DATABASE_URL …`, `exit=1`.

Unfilled placeholder (fake URL, refused before connecting — safe):

```bash
PROD_DATABASE_URL="postgresql://postgres.notarealref:pw@aws-0-us-east-1.pooler.supabase.com:6543/postgres" \
  python3 scripts/migrate_db.py --prod; echo "exit=$?"
```

Expected: `error: PROD_PROJECT_REFS in scripts/db_guard.py is empty — …`, `exit=1`. (Once a human fills the ref, this same command with a *wrong* ref reports "not a known prod database" instead.)

Also confirm `npm run migrate:prod` runs the script (same output as the first command):

```bash
npm run migrate:prod; echo "exit=$?"
```

Expected: the same `error: set PROD_DATABASE_URL …` message via npm, nonzero exit.

- [ ] **Step 7: Verify the demo path is unaffected and units pass**

```bash
npm run migrate
python3 -m pytest tests/test_db_guard.py -q
```

Expected: `schema_migrations: already up to date`; all unit tests pass.

- [ ] **Step 8: Commit**

```bash
git add scripts/migrate_db.py package.json .env.example
git commit -m "feat(scripts): migrate:prod — PROD_DATABASE_URL only, guarded, typed confirmation"
```

---

### Task 6: Documentation — retire the "guard doesn't exist yet" caveats

**Files:**
- Modify: `docs/DATABASE.md`
- Verify (expect no change): `/home/mshi/GuildOS/docs/adr/0002-supabase-is-hosted-postgres-only.md`

**Interfaces:**
- Consumes: the behavior shipped in Tasks 1–5 (nothing programmatic).

- [ ] **Step 1: Update the "Connect to prod" warning paragraph**

In `docs/DATABASE.md`, replace this paragraph (currently lines 73–77):

```markdown
**Never point `LocalDev/.env`'s `DATABASE_URL` at prod.** pytest and
`npm run dev` (which auto-migrates and can seed) read it. The conftest guard
that refuses prod URLs is part of the ADR-0002 cleanup; until it exists,
nothing but your attention prevents a test run from writing permanent rows
into the prod ledger.
```

with:

```markdown
**Never point `LocalDev/.env`'s `DATABASE_URL` at prod.** If it happens
anyway, the guards in `scripts/db_guard.py` fail closed: pytest,
`npm run seed`, `npm run migrate`, and the `npm run dev` auto-migrate all
refuse any URL that is not the checked-in demo project ref or a local
database — the run aborts before a connection is opened. Fix `.env` and
re-run.
```

- [ ] **Step 2: Replace the "Migrations → On prod" section**

Replace the whole `### On prod` section (currently lines 96–115, from `### On prod` through the `npm run migrate:prod` code fence) with:

```markdown
### On prod

Prod migration is a separate, deliberate command. It reads
**`PROD_DATABASE_URL`** (from the environment or `LocalDev/.env`) and never
`DATABASE_URL`:

```bash
npm run migrate:prod
```

The script verifies the URL matches a known prod project ref
(`PROD_PROJECT_REFS` in `scripts/db_guard.py`), prints the pending
migrations, and requires you to type the prod project ref before applying
anything. For CI, `python3 scripts/migrate_db.py --prod --yes` skips the
prompt.

The old one-off `DATABASE_URL="<prod URL>" python3 scripts/migrate_db.py`
no longer works: the default path allowlists the demo and refuses
everything else.
```

- [ ] **Step 3: Update the quick-reference table**

In the `## Quick reference` table, replace the two rows

```markdown
| Migrate prod (today) | `DATABASE_URL="<prod pooler URL>" python3 scripts/migrate_db.py` |
| Migrate prod (target) | `npm run migrate:prod` |
```

with the single row

```markdown
| Migrate prod | `npm run migrate:prod` (reads `PROD_DATABASE_URL`; typed confirmation) |
```

- [ ] **Step 4: Verify ADR-0002 needs no edit**

Read `/home/mshi/GuildOS/docs/adr/0002-supabase-is-hosted-postgres-only.md` → its Consequences already state, in the present tense, that "pytest refuses to run against a URL containing the prod project ref" and that "`PROD_DATABASE_URL` exists solely for `npm run migrate:prod`". Both are now true, so no edit is required. If you find its wording contradicts the shipped behavior, fix the wording — otherwise leave the file untouched.

- [ ] **Step 5: Update the design spec status line**

In `docs/superpowers/specs/2026-07-11-prod-db-write-guards-design.md`, change:

```markdown
**Status:** approved design, not yet implemented
```

to:

```markdown
**Status:** implemented (see docs/superpowers/plans/2026-07-11-prod-db-write-guards.md)
```

- [ ] **Step 6: Commit**

```bash
git add docs/DATABASE.md docs/superpowers/specs/2026-07-11-prod-db-write-guards-design.md
git commit -m "docs(db): document the shipped prod-db write guards and migrate:prod ritual"
```

---

## Post-plan follow-up (human, not part of execution)

- Fill `PROD_PROJECT_REFS` in `scripts/db_guard.py` with the real production project ref (Supabase dashboard → production project → Settings → General → Reference ID). Until then `migrate:prod` refuses to run; the fail-closed test/seed/demo-migrate guards are already fully effective.
- If the demo project is ever recreated, update `DEMO_PROJECT_REF` in the same file — it is the single source of truth.
