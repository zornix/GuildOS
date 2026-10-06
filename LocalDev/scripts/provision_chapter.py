#!/usr/bin/env python3
"""Provision a new chapter and its first officer — the vetted onboarding path.

There is no self-serve signup and no API endpoint that writes to `chapters`
(GTM checklist 3.1). Until there is, onboarding a real chapter runs through
this script instead of hand-written SQL, so every new tenant gets the same
rows, the same guards, and the same audit-able summary.

Usage (demo — reads DATABASE_URL):

  python3 scripts/provision_chapter.py \
      --name "Alpha Beta" \
      --organization "TKE" \
      --school "State University" \
      --officer-email jane@example.edu \
      --officer-name "Jane Roe" \
      --officer-phone +15551234567

Production adds `--prod`, which reads PROD_DATABASE_URL *only* and demands the
same typed confirmation `scripts/migrate_db.py --prod` demands:

  python3 scripts/provision_chapter.py --prod --name ... --organization ...

What it creates, in one transaction:
  chapters      one row
  members       the first officer (role='officer', status='active')
  member_roles  ('officer', 'admin') when the RBAC catalog is present
                the officer can administer the chapter and hand off admin access

The password is prompted for (never argv, never env). The script refuses to
run if a chapter with the same name, or a member with the same email, already
exists — it never upserts, so re-running it is safe but not idempotent.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path

import bcrypt
import psycopg2

REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.db_guard import (  # noqa: E402
    ProdGuardError,
    classify_url,
    confirmation_matches,
    redact,
    require_demo,
    require_prod,
)

MIN_PASSWORD_LENGTH = 8

# E.164: leading +, country code 1-9, 8-15 digits total.
E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")

# Columns provision writes on `members`. The auth work package may add columns
# (status='invited', token_version, …); we only ever name the ones we need, and
# only those that actually exist on the connected database.
_MEMBER_REQUIRED_COLUMNS = ("chapter_id", "name", "email", "role", "status")
_MEMBER_OPTIONAL_COLUMNS = ("phone", "password_hash")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a chapter and its first officer.",
        epilog=(
            "The officer password is prompted for interactively — never pass "
            "secrets on the command line."
        ),
    )
    parser.add_argument("--name", required=True, help='chapter name, e.g. "Alpha Beta"')
    parser.add_argument(
        "--organization",
        required=True,
        help='national organization, e.g. "TKE" (chapters.organization is NOT NULL)',
    )
    parser.add_argument(
        "--school",
        required=True,
        help='school/university, e.g. "State University" (chapters.school is NOT NULL)',
    )
    parser.add_argument("--officer-email", required=True, help="first officer's email (lowercased)")
    parser.add_argument("--officer-name", required=True, help='first officer\'s name, e.g. "Jane Roe"')
    parser.add_argument(
        "--officer-phone",
        default=None,
        help="optional E.164 phone, e.g. +15551234567",
    )
    parser.add_argument(
        "--prod",
        action="store_true",
        help="provision on production (reads PROD_DATABASE_URL only)",
    )
    return parser.parse_args()


def _env_value(key: str) -> str:
    """Read a key from the process env, falling back to LocalDev/.env.

    Mirrors scripts/migrate_db.py so both prod entry points resolve their URL
    the same way.
    """
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


def _fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def _resolve_url(prod: bool) -> str:
    """The connection URL for this run, already past the write guards."""
    if prod:
        url = _env_value("PROD_DATABASE_URL")
        if not url:
            _fail(
                "set PROD_DATABASE_URL (env or LocalDev/.env) — it is read only "
                "by --prod, never by dev/test"
            )
        try:
            require_prod(url)
        except ProdGuardError as exc:
            _fail(str(exc))
        return url

    url = _env_value("DATABASE_URL")
    if not url:
        _fail("set DATABASE_URL (e.g. from .env)")
    try:
        require_demo(url, context="provision_chapter")
    except ProdGuardError as exc:
        _fail(str(exc))
    return url


def _normalize_phone(raw: str | None) -> str | None:
    if raw is None:
        return None
    phone = raw.strip()
    if not phone:
        return None
    if not E164_RE.match(phone):
        _fail(f"--officer-phone {phone!r} is not E.164 (expected e.g. +15551234567)")
    return phone


def _prompt_password() -> str:
    """Ask twice, hidden. The only way a password enters this script."""
    try:
        password = getpass.getpass(f"Officer password (min {MIN_PASSWORD_LENGTH} chars): ")
        confirm = getpass.getpass("Confirm password: ")
    except EOFError:
        _fail("no password input — nothing created")
    if len(password) < MIN_PASSWORD_LENGTH:
        _fail(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    if password != confirm:
        _fail("passwords do not match")
    return password


def _confirm_prod(url: str, args: argparse.Namespace) -> None:
    """The same typed-confirmation gate migrate_db.py --prod uses."""
    print(f"target: {redact(url)} (PROD)")
    print("about to create:")
    print(f"  chapter  {args.name} — {args.organization} @ {args.school}")
    print(f"  officer  {args.officer_name} <{args.officer_email.strip().lower()}>")
    try:
        typed = input("Type the prod project ref to create them: ")
    except EOFError:
        _fail("no confirmation input — nothing created")
    if not confirmation_matches(typed, url):
        _fail("confirmation mismatch — nothing created")


def _table_exists(cur, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{table}",))
    return bool(cur.fetchone()[0])


def _existing_columns(cur, table: str) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table,),
    )
    return {row[0] for row in cur.fetchall()}


def _assert_absent(cur, args: argparse.Namespace, email: str) -> None:
    """Refuse rather than upsert if either the chapter or the officer exists."""
    cur.execute("SELECT id FROM chapters WHERE lower(name) = lower(%s)", (args.name,))
    row = cur.fetchone()
    if row:
        _fail(f"a chapter named {args.name!r} already exists (id={row[0]}) — refusing to modify it")

    cur.execute("SELECT id, chapter_id FROM members WHERE lower(email) = %s", (email,))
    row = cur.fetchone()
    if row:
        _fail(
            f"a member with email {email!r} already exists (id={row[0]}, "
            f"chapter_id={row[1]}) — members.email is globally unique"
        )


def _insert_chapter(cur, args: argparse.Namespace) -> str:
    cur.execute(
        "INSERT INTO chapters (name, organization, school) VALUES (%s, %s, %s) RETURNING id",
        (args.name, args.organization, args.school),
    )
    return cur.fetchone()[0]


def _insert_officer(
    cur,
    *,
    chapter_id: str,
    name: str,
    email: str,
    phone: str | None,
    password_hash: str,
) -> str:
    """Insert the first officer, naming only columns this database has."""
    columns = _existing_columns(cur, "members")

    missing = [c for c in _MEMBER_REQUIRED_COLUMNS if c not in columns]
    if missing:
        _fail(f"members is missing expected column(s): {', '.join(missing)} — run migrations first")
    if "password_hash" not in columns:
        _fail("members has no password_hash column — apply migration 0004 before provisioning")

    values: dict[str, object] = {
        "chapter_id": chapter_id,
        "name": name,
        "email": email,
        "role": "officer",
        "status": "active",
        "password_hash": password_hash,
    }
    if phone is not None:
        if "phone" not in columns:
            _fail("members has no phone column — omit --officer-phone or run migrations")
        values["phone"] = phone

    names = [c for c in (*_MEMBER_REQUIRED_COLUMNS, *_MEMBER_OPTIONAL_COLUMNS) if c in values]
    placeholders = ", ".join(["%s"] * len(names))
    cur.execute(
        f"INSERT INTO members ({', '.join(names)}) VALUES ({placeholders}) RETURNING id",
        tuple(values[c] for c in names),
    )
    return cur.fetchone()[0]


def _grant_officer_role(cur, *, chapter_id: str, member_id: str) -> bool:
    """Grant officer and admin authority. No-op when the catalog isn't there yet.

    member_roles.role_key is an FK onto roles(key), whose rows are seeded by
    migration 0083 — on a database that predates it the insert would fail, so
    we skip with a warning rather than abort the whole provision.
    """
    if not _table_exists(cur, "member_roles") or not _table_exists(cur, "roles"):
        print("warning: member_roles/roles not present — skipping RBAC role grant")
        return False

    granted = True
    for role_key in ("officer", "admin"):
        cur.execute("SELECT 1 FROM roles WHERE key = %s", (role_key,))
        if not cur.fetchone():
            print(f"warning: roles catalog has no '{role_key}' row (migration 0083) — skipping role grant")
            granted = False
            continue

        cur.execute(
            "INSERT INTO member_roles (chapter_id, member_id, role_key) VALUES (%s, %s, %s) "
            "ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING",
            (chapter_id, member_id, role_key),
        )
    return granted


def main() -> None:
    args = _parse_args()

    email = args.officer_email.strip().lower()
    if "@" not in email:
        _fail(f"--officer-email {args.officer_email!r} does not look like an email address")
    phone = _normalize_phone(args.officer_phone)

    url = _resolve_url(args.prod)

    if args.prod:
        _confirm_prod(url, args)
    else:
        print(f"target: {redact(url)} ({classify_url(url).upper()})")

    password = _prompt_password()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = psycopg2.connect(url)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            _assert_absent(cur, args, email)
            chapter_id = _insert_chapter(cur, args)
            member_id = _insert_officer(
                cur,
                chapter_id=chapter_id,
                name=args.officer_name,
                email=email,
                phone=phone,
                password_hash=password_hash,
            )
            role_granted = _grant_officer_role(cur, chapter_id=chapter_id, member_id=member_id)
        conn.commit()
    except SystemExit:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        print("failed: nothing was created (transaction rolled back)", file=sys.stderr)
        raise
    finally:
        conn.close()

    print("provisioned:")
    print(f"  chapter_id   {chapter_id}  ({args.name} — {args.organization} @ {args.school})")
    print(f"  member_id    {member_id}  ({args.officer_name} <{email}>, role=officer, status=active)")
    print(f"  member_roles {'officer and admin granted' if role_granted else 'incomplete (RBAC catalog absent or missing role)'}")
    print(f"  target       {redact(url)}")
    print("The officer can now sign in with the password you just set.")


if __name__ == "__main__":
    main()
