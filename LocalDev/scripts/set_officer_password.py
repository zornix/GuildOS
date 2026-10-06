#!/usr/bin/env python3
"""
Set or reset an officer's password directly in the database.

Usage:
  DATABASE_URL=postgresql://... python scripts/set_officer_password.py officer@email.com

Defaults to the demo database. --prod requires PROD_DATABASE_URL and typed
project-ref confirmation. Prompts for the password interactively (hidden input).
Useful for bootstrapping the first officer before the app is deployed,
or resetting a password without going through the UI.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

import bcrypt
import psycopg2


try:
    from scripts.db_guard import require_demo, require_prod, confirmation_matches, ProdGuardError
except ModuleNotFoundError:
    from db_guard import require_demo, require_prod, confirmation_matches, ProdGuardError

PASSWORD_SQL = (
    "UPDATE members SET password_hash = %s, token_version = token_version + 1 "
    "WHERE email = %s RETURNING id, name"
)
BURN_CODES_SQL = (
    "UPDATE member_setup_codes SET used_at = now() "
    "WHERE member_id = %s AND used_at IS NULL"
)


def guard_database(url: str, *, prod: bool) -> None:
    try:
        if prod:
            require_prod(url)
        else:
            require_demo(url, context="set_officer_password")
    except ProdGuardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    if prod:
        try:
            typed = input("Type the prod project ref to reset the password: ")
        except EOFError:
            print("error: no confirmation input — nothing changed", file=sys.stderr)
            sys.exit(1)
        if not confirmation_matches(typed, url):
            print("error: confirmation mismatch — nothing changed", file=sys.stderr)
            sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument("--prod", action="store_true")
    args = parser.parse_args()
    email = args.email.strip().lower()
    variable = "PROD_DATABASE_URL" if args.prod else "DATABASE_URL"
    db_url = os.environ.get(variable, "").strip()
    if not db_url:
        print(f"error: set {variable}", file=sys.stderr)
        sys.exit(1)
    guard_database(db_url, prod=args.prod)

    password = getpass.getpass("New password (min 8 chars): ")
    if len(password) < 8:
        print("error: password must be at least 8 characters", file=sys.stderr)
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("error: passwords do not match", file=sys.stderr)
        sys.exit(1)

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                PASSWORD_SQL,
                (hashed, email),
            )
            row = cur.fetchone()
            if not row:
                print(f"error: no member found with email '{email}'", file=sys.stderr)
                conn.rollback()
                sys.exit(1)
            cur.execute(BURN_CODES_SQL, (row[0],))
            conn.commit()
            print(f"Password set for {row[1]} (id={row[0]})")
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
