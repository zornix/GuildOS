# 07 · CI and tooling: migration checksums, dependency sync, a linter

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first. Do exactly what each step says; if a step cannot be done as written, stop and report instead of improvising.

**Stream:** `07-ci-tooling` · **Wave:** 1 · **Agent:** Gemini 3.8 Flash medium (Antigravity CLI) · **Branch:** `fix/audit-07-ci-tooling`
**Findings:** F-016, F-040, R-01
**Goal:** an edited migration fails a test; the migration runner refuses a database whose history it does not recognise; the local bootstrap installs dependencies when the pins change; CI runs a Python linter.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-016, F-040 and Appendix C.4 (R-01).

## Global constraints

- Allowed files (paths from the repo root): `LocalDev/scripts/migrate_db.py`, `LocalDev/scripts/migration_checksums.py` (new), `LocalDev/migrations/CHECKSUMS` (new), `LocalDev/tests/test_migration_checksums.py` (new), `LocalDev/tests/test_migrate_history.py` (new), `LocalDev/ruff.toml` (new), `LocalDev/requirements-dev.txt` (new), `LocalDev/.gitignore`, `.github/workflows/ci.yml`, `local-dev-scripts/scripts/local-dev.sh`.
- Do NOT edit any file in `LocalDev/migrations/*.sql`, anything under `LocalDev/api/`, or any existing test.
- Do NOT run `scripts/migrate_db.py --prod`. Do not run the full pytest suite. Run only the two new test files.
- Commands below run from `LocalDev/` unless they say otherwise.

## Review focus

1. `migrate_db.py` must behave exactly as before on a database that is up to date and unedited (prints `schema_migrations: already up to date`, exit 0).
2. On the demo database, names in `schema_migrations` that are missing from this checkout are normal (other branches apply their migrations to the same database). That case is a warning without `--prod`, an error with `--prod`.
3. Rows applied before this change have no checksum. They must not fail; they get the current file's checksum on the next run.
4. The bootstrap must not reinstall on every run, only when `requirements.txt` changed.
5. The linter step must pass on the code as it is today, without reformatting anything.

---

### Task 1: F-016 — a committed checksum for every migration

**Files:** `scripts/migration_checksums.py`, `migrations/CHECKSUMS`, `tests/test_migration_checksums.py`

- [ ] **Step 1: write the script** `scripts/migration_checksums.py`:

```python
#!/usr/bin/env python3
"""Checksums for migrations/*.sql, so an edit to an applied migration is visible.

  python3 scripts/migration_checksums.py --update   add lines for new files (never rewrites a line)
  python3 scripts/migration_checksums.py --check    exit 1 if a listed file changed or a file is unlisted
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
MANIFEST = MIGRATIONS_DIR / "CHECKSUMS"


def file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest(manifest: Path = MANIFEST) -> dict[str, str]:
    if not manifest.exists():
        return {}
    out = {}
    for line in manifest.read_text().splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            out[name.strip()] = digest
    return out


def current(migrations_dir: Path = MIGRATIONS_DIR) -> dict[str, str]:
    return {p.name: file_checksum(p) for p in sorted(migrations_dir.glob("*.sql"))}


def changed(listed: dict[str, str], now: dict[str, str]) -> list[str]:
    """Listed files whose content no longer matches (or that were deleted)."""
    return sorted(n for n, d in listed.items() if now.get(n) != d)


def unlisted(listed: dict[str, str], now: dict[str, str]) -> list[str]:
    return sorted(n for n in now if n not in listed)


def main(argv: list[str]) -> int:
    listed, now = read_manifest(), current()
    if "--update" in argv:
        merged = dict(listed)
        for name in unlisted(listed, now):
            merged[name] = now[name]
        MANIFEST.write_text("".join(f"{merged[n]}  {n}\n" for n in sorted(merged)))
        print(f"CHECKSUMS: {len(merged)} entries")
        return 0
    bad, missing = changed(listed, now), unlisted(listed, now)
    for n in bad:
        print(f"changed after it was recorded: {n}", file=sys.stderr)
    for n in missing:
        print(f"not in CHECKSUMS (run --update): {n}", file=sys.stderr)
    return 1 if (bad or missing) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 2: write the failing test** `tests/test_migration_checksums.py`:

```python
from scripts import migration_checksums as mc


def test_no_recorded_migration_has_changed():
    listed = mc.read_manifest()
    assert listed, "migrations/CHECKSUMS is missing or empty"
    assert mc.changed(listed, mc.current()) == []


def test_changed_detects_an_edit_and_a_delete():
    listed = {"0001_a.sql": "aaa", "0002_b.sql": "bbb"}
    assert mc.changed(listed, {"0001_a.sql": "aaa", "0002_b.sql": "XXX"}) == ["0002_b.sql"]
    assert mc.changed(listed, {"0001_a.sql": "aaa"}) == ["0002_b.sql"]


def test_unlisted_reports_new_files_only():
    assert mc.unlisted({"0001_a.sql": "aaa"}, {"0001_a.sql": "zzz", "0003_c.sql": "ccc"}) == ["0003_c.sql"]
```

The first test deliberately does NOT fail on unlisted files: other branches add migrations before the manifest catches up. CI checks completeness (Task 4).

- [ ] **Step 3: run** `python3 -m pytest tests/test_migration_checksums.py -q` — expected: the first test FAILS (`CHECKSUMS is missing or empty`), the other two pass.
- [ ] **Step 4: create the manifest** — `python3 scripts/migration_checksums.py --update`. Expected output: `CHECKSUMS: 65 entries`. Run `python3 scripts/migration_checksums.py --check; echo $?` → `0`.
- [ ] **Step 5: run the test again, expect 3 passed. Checkpoint** — suggested message `feat(migrations): record a checksum for every migration file`.

---

### Task 2: F-016 — the runner checks history before it applies anything

**Files:** `scripts/migrate_db.py`, `tests/test_migrate_history.py`

- [ ] **Step 1: write the failing test** `tests/test_migrate_history.py`:

```python
from scripts import migrate_db as m


def test_unknown_applied_names():
    assert m.unknown_applied({"0001_a.sql", "0002_old.sql"}, ["0001_a.sql", "0003_c.sql"]) == ["0002_old.sql"]
    assert m.unknown_applied({"0001_a.sql"}, ["0001_a.sql", "0003_c.sql"]) == []


def test_edited_after_apply():
    applied = {"0001_a.sql": "aaa", "0002_b.sql": None, "0003_c.sql": "ccc"}
    files = {"0001_a.sql": "aaa", "0002_b.sql": "anything", "0003_c.sql": "CHANGED"}
    assert m.edited_after_apply(applied, files) == ["0003_c.sql"]
```

- [ ] **Step 2: run, expect FAIL** (`AttributeError: module 'scripts.migrate_db' has no attribute 'unknown_applied'`).
- [ ] **Step 3: implement in `scripts/migrate_db.py`.**

  a. Add `import hashlib` and these two pure functions above `main`:

```python
def unknown_applied(applied: set[str], files: list[str]) -> list[str]:
    """Names recorded in the database that this checkout does not contain."""
    return sorted(applied - set(files))


def edited_after_apply(applied: dict[str, str | None], files: dict[str, str]) -> list[str]:
    """Applied migrations whose recorded checksum differs from the file now on disk."""
    return sorted(n for n, d in applied.items() if d is not None and n in files and files[n] != d)
```

  b. In `_ensure_migrations_table`, after the `CREATE TABLE`, add: `cur.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT")`.

  c. Replace `_applied_names` with:

```python
def _applied(cur) -> dict[str, str | None]:
    cur.execute("SELECT name, checksum FROM schema_migrations")
    return {row[0]: row[1] for row in cur.fetchall()}
```

  d. In `main`, where it now does `applied = _applied_names(cur)`: read `applied = _applied(cur)`, build `checksums = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}`, then:

```python
        edited = edited_after_apply(applied, checksums)
        if edited:
            print("error: these migrations changed after they were applied "
                  "(never edit an applied migration; add a new file):", file=sys.stderr)
            for name in edited:
                print(f"  {name}", file=sys.stderr)
            sys.exit(1)

        unknown = unknown_applied(set(applied), [f.name for f in files])
        if unknown:
            label = "error" if args.prod else "warning"
            print(f"{label}: the database has applied migrations this checkout does not contain:",
                  file=sys.stderr)
            for name in unknown:
                print(f"  {name}", file=sys.stderr)
            if args.prod:
                print("refusing to migrate a database with an unknown history", file=sys.stderr)
                sys.exit(1)

        # Rows applied before checksums existed: record the file as it is now.
        with conn.cursor() as cur:
            for name, digest in applied.items():
                if digest is None and name in checksums:
                    cur.execute("UPDATE schema_migrations SET checksum = %s WHERE name = %s",
                                (checksums[name], name))
        conn.commit()
```

  Keep `pending = [f for f in files if f.name not in applied]` working (`applied` is now a dict; `in` still works).

  e. In the apply loop change the insert to: `"INSERT INTO schema_migrations (name, checksum) VALUES (%s, %s)", (path.name, checksums[path.name])`.

- [ ] **Step 4: run the test, expect 2 passed.**
- [ ] **Step 5: run the real thing once** against the demo database: `python3 scripts/migrate_db.py`. Expected: possibly a `warning:` block listing migrations from other branches, then `schema_migrations: already up to date` (or `applied:` lines), exit code 0. Run it a second time: same result. If it exits non-zero with "changed after they were applied", STOP and report the file names; do not edit any migration.
- [ ] **Step 6: checkpoint** — `feat(migrate): refuse edited migrations and unknown prod history`.

---

### Task 3: F-040 — reinstall Python dependencies when the pins change

**Files:** `local-dev-scripts/scripts/local-dev.sh` (section "4. Python dependencies", lines ~202-208), `LocalDev/.gitignore`

- [ ] **Step 1:** replace that section's `if ! python3 -c "import fastapi" …; fi` block with:

```bash
REQ_HASH="$(sha256sum requirements.txt | cut -d' ' -f1)"
if [ ! -f .deps-stamp ] || [ "$(cat .deps-stamp)" != "$REQ_HASH" ]; then
  echo "  Installing Python dependencies (requirements.txt changed) ..."
  pip install -r requirements.txt -q
  echo "$REQ_HASH" > .deps-stamp
fi
```

Keep the two `echo` lines around it.

- [ ] **Step 2:** add a line `.deps-stamp` to `LocalDev/.gitignore`.
- [ ] **Step 3: check the script still parses:** from the repo root, `bash -n local-dev-scripts/scripts/local-dev.sh; echo $?` → `0`. Do not run `npm run dev`.
- [ ] **Step 4: checkpoint** — `fix(dev): reinstall Python dependencies when requirements.txt changes`.

---

### Task 4: R-01 and the CI steps

**Files:** `LocalDev/ruff.toml`, `LocalDev/requirements-dev.txt`, `.github/workflows/ci.yml`

- [ ] **Step 1:** `LocalDev/requirements-dev.txt` with one line: `ruff==0.14.0`. If `pip install -r requirements-dev.txt` says that version does not exist, use the newest version pip lists and say so in the report.
- [ ] **Step 2:** `LocalDev/ruff.toml`:

```toml
# Errors only: syntax errors, undefined names, broken comparisons. No style rules, no formatting.
target-version = "py312"
extend-exclude = ["greekos", "fratos", "archive"]

[lint]
select = ["E9", "F63", "F7", "F82"]
```

- [ ] **Step 3: run it:** `pip install -r requirements-dev.txt -q && python3 -m ruff check api scripts tests`. Expected: `All checks passed!`. If it reports errors, do NOT fix files outside your allowed list: copy the full output into your report, and add each offending file to a `[lint.per-file-ignores]` table in `ruff.toml` with the rule code and a comment `# pre-existing, reported 2026-10-05` so the step passes.
- [ ] **Step 4:** in `.github/workflows/ci.yml`, backend job, after the step `Install Python dependencies` add:

```yaml
      - name: Lint (errors only)
        run: |
          pip install -r requirements-dev.txt
          python3 -m ruff check api scripts tests

      - name: Migration checksums
        run: python3 scripts/migration_checksums.py --check
```

- [ ] **Step 5: validate the YAML:** from the repo root, `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"` → `ok`.
- [ ] **Step 6: checkpoint** — `ci: lint Python for errors and check migration checksums`.

## Report

Finish with the report block from `00-README.md` ("What to hand back").
