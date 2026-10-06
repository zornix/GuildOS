"""Config boot guard (imp-tenant-guards.md D5).

Deploys refuse to boot misconfigured; explicit local/test runs and Vercel
development bypass the guard. These are pure unit tests — no DB. Every
guarded field is passed explicitly so the assertions are deterministic
regardless of what the ambient environment or LocalDev/.env holds.
"""

from __future__ import annotations

import pytest

from api.config import Settings
from api.index import production_config_violations

# 32 chars — the minimum the guard accepts.
GOOD_JWT_SECRET = "K7fQ2xR9tL4wZ8vB6nM3jH5sD1gP0aYc"


def _prod_settings(**overrides) -> Settings:
    """A clean production config; override one field per test."""
    base = dict(
        VERCEL_ENV="production",
        JWT_SECRET=GOOD_JWT_SECRET,
        DATABASE_URL="postgresql://user:pass@host/db",
        DEV_AUTH_BYPASS=False,
        CRON_SECRET="a-real-cron-secret-value",
        FRONTEND_URL="https://app.guildos.example",
        BASE_URL="https://api.guildos.example",
        MESSAGE_DELIVERY_MODE="dry_run",
    )
    base.update(overrides)
    return Settings(**base)


# --- JWT_SECRET ------------------------------------------------------------


def test_default_jwt_secret_in_production_is_a_violation():
    s = _prod_settings(JWT_SECRET="local-dev-secret")
    violations = production_config_violations(s)
    assert violations
    assert any("JWT_SECRET" in v for v in violations)


def test_env_example_jwt_secret_is_a_violation():
    # The value .env.example told operators to use. It is long enough to clear the
    # length check and survived the old `== "local-dev-secret"` comparison.
    s = _prod_settings(JWT_SECRET="local-dev-secret-key-change-in-prod")
    violations = production_config_violations(s)
    assert any("JWT_SECRET" in v for v in violations)


def test_short_jwt_secret_is_a_violation():
    s = _prod_settings(JWT_SECRET="x" * 31)
    violations = production_config_violations(s)
    assert any("JWT_SECRET" in v for v in violations)


def test_no_entropy_single_char_jwt_secret_is_a_violation():
    s = _prod_settings(JWT_SECRET="x")
    assert any("JWT_SECRET" in v for v in production_config_violations(s))


def test_thirty_two_char_random_jwt_secret_is_accepted():
    assert production_config_violations(_prod_settings(JWT_SECRET=GOOD_JWT_SECRET)) == []


# --- DATABASE_URL / DEV_AUTH_BYPASS ---------------------------------------


def test_unset_database_url_in_production_is_a_violation():
    s = _prod_settings(DATABASE_URL=None)
    violations = production_config_violations(s)
    assert any("DATABASE_URL" in v for v in violations)


def test_dev_auth_bypass_in_production_is_a_violation():
    s = _prod_settings(DEV_AUTH_BYPASS=True)
    violations = production_config_violations(s)
    assert any("DEV_AUTH_BYPASS" in v for v in violations)


# --- CRON_SECRET -----------------------------------------------------------


def test_empty_cron_secret_is_a_violation():
    s = _prod_settings(CRON_SECRET="")
    violations = production_config_violations(s)
    assert any("CRON_SECRET" in v for v in violations)


def test_short_cron_secret_is_a_violation():
    s = _prod_settings(CRON_SECRET="tooshort")
    assert any("CRON_SECRET" in v for v in production_config_violations(s))


# --- FRONTEND_URL ----------------------------------------------------------


def test_localhost_frontend_url_is_a_violation():
    s = _prod_settings(FRONTEND_URL="http://localhost:3000")
    violations = production_config_violations(s)
    assert any("FRONTEND_URL" in v for v in violations)


def test_loopback_ip_frontend_url_is_a_violation():
    s = _prod_settings(FRONTEND_URL="http://127.0.0.1:3000")
    assert any("FRONTEND_URL" in v for v in production_config_violations(s))


# --- MESSAGE_DELIVERY_MODE / Twilio ---------------------------------------


def test_misspelled_delivery_mode_is_a_violation():
    s = _prod_settings(MESSAGE_DELIVERY_MODE="dryrun")
    violations = production_config_violations(s)
    assert any("MESSAGE_DELIVERY_MODE" in v for v in violations)


def test_twilio_mode_missing_auth_token_is_a_violation():
    s = _prod_settings(
        MESSAGE_DELIVERY_MODE="twilio",
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="",
        TWILIO_FROM_NUMBER="+15551234567",
    )
    violations = production_config_violations(s)
    assert any("TWILIO_AUTH_TOKEN" in v for v in violations)


def test_fully_configured_twilio_mode_is_accepted():
    s = _prod_settings(
        MESSAGE_DELIVERY_MODE="twilio",
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="secret-token",
        TWILIO_FROM_NUMBER="+15551234567",
    )
    assert production_config_violations(s) == []


# --- Twilio sender: Messaging Service vs bare From number (issue #54) ------


def test_twilio_mode_with_messaging_service_only_is_accepted():
    s = _prod_settings(
        MESSAGE_DELIVERY_MODE="twilio",
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="secret-token",
        TWILIO_MESSAGING_SERVICE_SID="MG123",
    )
    assert production_config_violations(s) == []


def test_twilio_mode_without_any_sender_is_a_violation():
    s = _prod_settings(
        MESSAGE_DELIVERY_MODE="twilio",
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="secret-token",
    )
    assert any("exactly one sender" in v for v in production_config_violations(s))


def test_twilio_mode_with_both_senders_is_a_violation():
    s = _prod_settings(
        MESSAGE_DELIVERY_MODE="twilio",
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="secret-token",
        TWILIO_MESSAGING_SERVICE_SID="MG123",
        TWILIO_FROM_NUMBER="+15551234567",
    )
    assert any("exactly one sender" in v for v in production_config_violations(s))


# --- aggregate / environment gating ---------------------------------------


def test_multiple_violations_all_reported():
    s = _prod_settings(JWT_SECRET="local-dev-secret", DATABASE_URL=None, DEV_AUTH_BYPASS=True)
    violations = production_config_violations(s)
    assert len(violations) == 3


def test_well_configured_production_boots():
    assert production_config_violations(_prod_settings()) == []


def test_explicit_local_is_not_guarded():
    s = Settings(APP_ENV="local", VERCEL_ENV="", JWT_SECRET="local-dev-secret", DATABASE_URL=None, DEV_AUTH_BYPASS=True)
    assert production_config_violations(s) == []


def test_preview_is_guarded():
    # Previews are public URLs inheriting the project's env vars, so they get the
    # same guard. This assertion is deliberately the inverse of its old form.
    s = Settings(VERCEL_ENV="preview", JWT_SECRET="local-dev-secret", DATABASE_URL=None)
    violations = production_config_violations(s)
    assert violations
    assert any("JWT_SECRET" in v for v in violations)
    assert any("DATABASE_URL" in v for v in violations)


def test_preview_with_auth_bypass_is_a_violation():
    # The hole this closes: a reachable preview URL with authentication disabled.
    s = _prod_settings(VERCEL_ENV="preview", DEV_AUTH_BYPASS=True)
    assert any("DEV_AUTH_BYPASS" in v for v in production_config_violations(s))


def test_well_configured_preview_boots():
    assert production_config_violations(_prod_settings(VERCEL_ENV="preview")) == []


def test_index_import_time_guard_raises_for_bad_production_config():
    # Reproduce the module-level check in api/index.py against a bad prod config.
    s = _prod_settings(JWT_SECRET="local-dev-secret")
    violations = production_config_violations(s)
    with pytest.raises(RuntimeError):
        if violations:
            raise RuntimeError(f"Refusing to boot in {s.VERCEL_ENV} — fix: " + "; ".join(violations))


# --- EMAIL_DELIVERY_MODE / SMTP (ADR-0005) ---------------------------------

_SMTP_OK = dict(
    EMAIL_DELIVERY_MODE="smtp",
    SMTP_HOST="smtp.gmail.com",
    SMTP_USER="ops@chapter.example",
    SMTP_PASSWORD="app-password",
    EMAIL_FROM="GuildOS <ops@chapter.example>",
)


def test_misspelled_email_delivery_mode_is_a_violation():
    s = _prod_settings(EMAIL_DELIVERY_MODE="smpt")
    assert any("EMAIL_DELIVERY_MODE" in v for v in production_config_violations(s))


def test_email_dry_run_needs_no_smtp_settings():
    s = _prod_settings(EMAIL_DELIVERY_MODE="dry_run")
    assert not any("EMAIL" in v or "SMTP" in v for v in production_config_violations(s))


@pytest.mark.parametrize(
    "missing", ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM"]
)
def test_smtp_mode_missing_a_credential_is_a_violation(missing):
    s = _prod_settings(**{**_SMTP_OK, missing: ""})
    assert any(missing in v for v in production_config_violations(s))


def test_a_complete_smtp_config_is_clean():
    assert production_config_violations(_prod_settings(**_SMTP_OK)) == []


def test_unlabelled_environment_is_guarded():
    s = Settings(_env_file=None, VERCEL_ENV="", APP_ENV="", JWT_SECRET="local-dev-secret")
    assert any("JWT_SECRET" in v for v in production_config_violations(s))


def test_app_env_production_is_guarded_without_vercel():
    s = _prod_settings(VERCEL_ENV="", APP_ENV="production", JWT_SECRET="local-dev-secret")
    assert any("JWT_SECRET" in v for v in production_config_violations(s))
    assert s.is_production


def test_vercel_development_is_not_guarded():
    s = Settings(_env_file=None, VERCEL_ENV="development", APP_ENV="", JWT_SECRET="local-dev-secret")
    assert production_config_violations(s) == []


@pytest.mark.parametrize("variable", ["BASE_URL", "FRONTEND_URL"])
@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_production_rejects_localhost_urls(variable, host):
    s = _prod_settings(**{variable: f"http://{host}:8001"})
    assert any(variable in v for v in production_config_violations(s))


@pytest.mark.parametrize("vercel,app", [("preview", ""), ("", "")])
def test_preview_and_unknown_reject_localhost_frontend(vercel, app):
    s = _prod_settings(VERCEL_ENV=vercel, APP_ENV=app, BASE_URL="http://localhost:8001",
                       FRONTEND_URL="http://localhost:3000")
    assert any("FRONTEND_URL" in v for v in production_config_violations(s))


@pytest.mark.parametrize("vercel,app,deployed", [
    ("production", "local", True), ("preview", "test", True),
    ("development", "", False), ("", "local", False), ("", "test", False),
    ("", "preview", True), ("", "production", True), ("", "", True),
])
def test_environment_guard_matrix(vercel, app, deployed):
    assert Settings(_env_file=None, VERCEL_ENV=vercel, APP_ENV=app).is_deployed is deployed


@pytest.mark.parametrize("app_env", ["local", "test"])
def test_explicit_local_environments_allow_localhost_frontend(app_env):
    s = _prod_settings(VERCEL_ENV="", APP_ENV=app_env, FRONTEND_URL="http://localhost:3000")
    assert production_config_violations(s) == []


def test_health_database_initialization_failure_is_503(monkeypatch):
    from fastapi.testclient import TestClient
    from api import index
    def fail():
        raise RuntimeError("SQLSTATE XX000 relation private DETAIL secret")
    monkeypatch.setattr(index, "get_db", fail)
    with TestClient(index.app, raise_server_exceptions=False) as client:
        response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "error", "version": "0.1.0",
        "checks": {"database": "error"}, "detail": "database_unreachable",
    }
