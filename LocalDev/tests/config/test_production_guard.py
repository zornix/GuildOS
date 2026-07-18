"""Config boot guard (imp-tenant-guards.md D5).

Production refuses to boot misconfigured; dev (empty VERCEL_ENV) boots as today.
These are pure unit tests — no DB. Explicit Settings kwargs so the assertions are
deterministic regardless of what LocalDev/.env holds.
"""

from __future__ import annotations

import pytest

from api.config import Settings
from api.index import production_config_violations


def _prod_settings(**overrides) -> Settings:
    base = dict(
        VERCEL_ENV="production",
        JWT_SECRET="a-real-strong-secret",
        DATABASE_URL="postgresql://user:pass@host/db",
        DEV_AUTH_BYPASS=False,
    )
    base.update(overrides)
    return Settings(**base)


def test_default_jwt_secret_in_production_is_a_violation():
    s = _prod_settings(JWT_SECRET="local-dev-secret")
    violations = production_config_violations(s)
    assert violations
    assert any("JWT_SECRET" in v for v in violations)


def test_unset_database_url_in_production_is_a_violation():
    s = _prod_settings(DATABASE_URL=None)
    violations = production_config_violations(s)
    assert any("DATABASE_URL" in v for v in violations)


def test_dev_auth_bypass_in_production_is_a_violation():
    s = _prod_settings(DEV_AUTH_BYPASS=True)
    violations = production_config_violations(s)
    assert any("DEV_AUTH_BYPASS" in v for v in violations)


def test_multiple_violations_all_reported():
    s = _prod_settings(JWT_SECRET="local-dev-secret", DATABASE_URL=None, DEV_AUTH_BYPASS=True)
    violations = production_config_violations(s)
    assert len(violations) == 3


def test_well_configured_production_boots():
    assert production_config_violations(_prod_settings()) == []


def test_dev_is_never_guarded():
    # Empty VERCEL_ENV (local/dev) — even the insecure default is allowed.
    s = Settings(VERCEL_ENV="", JWT_SECRET="local-dev-secret", DATABASE_URL=None, DEV_AUTH_BYPASS=True)
    assert production_config_violations(s) == []


def test_preview_is_never_guarded():
    s = Settings(VERCEL_ENV="preview", JWT_SECRET="local-dev-secret", DATABASE_URL=None)
    assert production_config_violations(s) == []


def test_index_import_time_guard_raises_for_bad_production_config():
    # Reproduce the module-level check in api/index.py against a bad prod config.
    s = _prod_settings(JWT_SECRET="local-dev-secret")
    violations = production_config_violations(s)
    with pytest.raises(RuntimeError):
        if violations:
            raise RuntimeError("Refusing to boot in production — fix: " + "; ".join(violations))
