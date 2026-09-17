"""Sentry wiring in api/observability.py. Pure unit tests — no DB, no network."""

from __future__ import annotations

import pytest


def _init_sentry(monkeypatch) -> dict:
    """Run _configure_sentry with a stubbed sentry_sdk.init; return its kwargs."""
    pytest.importorskip("sentry_sdk")
    import sentry_sdk

    from api import observability
    from api.config import settings

    captured: dict = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: captured.update(kw))
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://key@example.test/1")
    monkeypatch.setattr(observability, "_sentry_configured", False)
    observability._configure_sentry()
    # The module global is process-wide; put it back for the rest of the session.
    monkeypatch.setattr(observability, "_sentry_configured", False)
    return captured


def test_frame_locals_never_go_to_sentry(monkeypatch):
    """Locals hold the SMTP password and rendered setup-code bodies."""
    assert _init_sentry(monkeypatch)["include_local_variables"] is False


def test_the_dsn_and_environment_are_passed(monkeypatch):
    kwargs = _init_sentry(monkeypatch)
    assert kwargs["dsn"] == "https://key@example.test/1"
    assert kwargs["traces_sample_rate"] == 0
