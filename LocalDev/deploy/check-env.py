#!/usr/bin/env python3
"""
Validate that required environment variables are set for the FraternityOS backend.

Usage:
  python deploy/check-env.py              # check current .env / shell env
  python deploy/check-env.py --mode prod  # stricter checks for production
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv_simple(path: Path) -> dict[str, str]:
    """Minimal .env parser — no dependencies needed."""
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip()
    return env


def check():
    mode = "local"
    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        if idx + 1 < len(sys.argv):
            mode = sys.argv[idx + 1]

    dotenv = load_dotenv_simple(REPO_ROOT / ".env")
    merged = {**dotenv, **os.environ}

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    NC = "\033[0m"

    errors = 0
    warnings = 0

    def ok(msg):
        print(f"  {GREEN}✓{NC} {msg}")

    def err(msg):
        nonlocal errors
        errors += 1
        print(f"  {RED}✗{NC} {msg}")

    def warn(msg):
        nonlocal warnings
        warnings += 1
        print(f"  {YELLOW}⚠{NC} {msg}")

    print(f"Checking environment ({mode} mode):\n")

    # --- Always required ---
    jwt = merged.get("JWT_SECRET", "")
    if not jwt:
        err("JWT_SECRET is not set")
    elif jwt in ("local-dev-secret", "local-dev-secret-key-change-in-prod") and mode == "prod":
        err("JWT_SECRET is still the dev default — generate a real one: openssl rand -hex 32")
    else:
        ok("JWT_SECRET")

    # --- DB or Supabase ---
    db_url = merged.get("DATABASE_URL", "")
    supa_url = merged.get("SUPABASE_URL", "")
    supa_anon = merged.get("SUPABASE_ANON_KEY", "")
    supa_service = merged.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if db_url:
        ok(f"DATABASE_URL set (direct Postgres mode)")
        if "localhost" in db_url or "127.0.0.1" in db_url:
            if mode == "prod":
                err("DATABASE_URL points to localhost — use Supabase connection string for prod")
            else:
                ok("DATABASE_URL points to local DB (correct for local dev)")
    elif supa_url and supa_service:
        ok("SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY set (Supabase client mode)")
        if not supa_anon:
            warn("SUPABASE_ANON_KEY not set — some queries may fail")
    else:
        err("Neither DATABASE_URL nor SUPABASE_URL+keys are set — backend cannot reach DB")

    # --- URLs ---
    frontend_url = merged.get("FRONTEND_URL", "")
    base_url = merged.get("BASE_URL", "")

    if mode == "prod":
        if not frontend_url:
            err("FRONTEND_URL not set (required for CORS in production)")
        elif "localhost" in frontend_url:
            err("FRONTEND_URL points to localhost — set to your Vercel domain")
        else:
            ok(f"FRONTEND_URL = {frontend_url}")

        if not base_url:
            warn("BASE_URL not set (used for check-in link generation)")
        elif "localhost" in base_url:
            err("BASE_URL points to localhost — set to your Vercel domain")
        else:
            ok(f"BASE_URL = {base_url}")
    else:
        ok(f"FRONTEND_URL = {frontend_url or '(default: localhost:3000)'}")
        ok(f"BASE_URL = {base_url or '(default: localhost:8001)'}")

    # --- Optional ---
    ttl = merged.get("CHECKIN_LINK_TTL_MINUTES", "")
    if ttl:
        ok(f"CHECKIN_LINK_TTL_MINUTES = {ttl}")
    else:
        ok("CHECKIN_LINK_TTL_MINUTES defaults to 10")

    # --- Frontend env ---
    fratos_env = REPO_ROOT / "fratos" / ".env.local"
    if mode != "prod":
        if fratos_env.exists():
            fe_env = load_dotenv_simple(fratos_env)
            api_base = fe_env.get("NEXT_PUBLIC_API_BASE", "")
            if api_base:
                ok(f"fratos/.env.local: NEXT_PUBLIC_API_BASE = {api_base}")
            else:
                warn("fratos/.env.local exists but NEXT_PUBLIC_API_BASE not set")
        else:
            warn("fratos/.env.local missing — frontend will try localhost:8001 auto-detection")

    # --- Summary ---
    print()
    if errors:
        print(f"{RED}{errors} error(s){NC} found.")
        return 1
    if warnings:
        print(f"{YELLOW}{warnings} warning(s){NC} — review above.")
        return 0
    print(f"{GREEN}All checks passed.{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(check())
