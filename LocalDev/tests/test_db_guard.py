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
