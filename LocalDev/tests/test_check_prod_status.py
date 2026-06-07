import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx


MODULE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_prod_status.py"
SPEC = importlib.util.spec_from_file_location("check_prod_status", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_evaluate_health_payload_accepts_ok_status_and_db() -> None:
    healthy, reason = MODULE.evaluate_health_payload(
        {"status": "ok", "checks": {"database": "ok"}},
    )
    assert healthy is True
    assert reason == "status=ok checks.database=ok"


def test_evaluate_health_payload_rejects_non_ok_status() -> None:
    healthy, reason = MODULE.evaluate_health_payload(
        {"status": "error", "checks": {"database": "error"}},
    )
    assert healthy is False
    assert reason == "status=error"


def test_evaluate_health_payload_rejects_missing_checks() -> None:
    healthy, reason = MODULE.evaluate_health_payload({"status": "ok"})
    assert healthy is False
    assert "checks" in reason


def test_evaluate_health_payload_rejects_database_not_ok() -> None:
    healthy, reason = MODULE.evaluate_health_payload(
        {"status": "ok", "checks": {"database": "error"}},
    )
    assert healthy is False
    assert reason == "checks.database=error"


def test_evaluate_health_payload_rejects_non_dict_payload() -> None:
    healthy, reason = MODULE.evaluate_health_payload("not-json")
    assert healthy is False
    assert reason == "response was not a JSON object"


def test_run_check_retries_on_503_then_succeeds(capsys) -> None:
    ok_payload = {"status": "ok", "version": "0.1.0", "checks": {"database": "ok"}}
    bad = MagicMock()
    bad.status_code = 503
    bad.json = MagicMock()
    good = MagicMock()
    good.status_code = 200
    good.json = MagicMock(return_value=ok_payload)

    with patch.object(MODULE.httpx, "get", side_effect=[bad, good]) as mock_get:
        code = MODULE.run_check(
            "https://example.com",
            5.0,
            max_attempts=3,
            backoff_sec=0.0,
        )

    assert code == 0
    assert mock_get.call_count == 2
    out = capsys.readouterr().out
    assert "UP:" in out


def test_run_check_retries_on_db_error_then_succeeds(capsys) -> None:
    fail_payload = {"status": "error", "checks": {"database": "error"}, "detail": "database_unreachable"}
    ok_payload = {"status": "ok", "version": "0.1.0", "checks": {"database": "ok"}}
    resp_fail = MagicMock()
    resp_fail.status_code = 200
    resp_fail.json = MagicMock(return_value=fail_payload)
    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.json = MagicMock(return_value=ok_payload)

    with patch.object(MODULE.httpx, "get", side_effect=[resp_fail, resp_ok]) as mock_get:
        code = MODULE.run_check(
            "https://example.com",
            5.0,
            max_attempts=3,
            backoff_sec=0.0,
        )

    assert code == 0
    assert mock_get.call_count == 2
    assert "UP:" in capsys.readouterr().out


def test_run_check_fails_after_exhausted_retries(capsys) -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(
        return_value={"status": "error", "checks": {"database": "error"}},
    )

    with patch.object(MODULE.httpx, "get", return_value=resp):
        code = MODULE.run_check(
            "https://example.com",
            5.0,
            max_attempts=2,
            backoff_sec=0.0,
        )

    assert code == 1
    assert "DOWN:" in capsys.readouterr().out


def test_run_check_retries_on_http_error(capsys) -> None:
    ok_payload = {"status": "ok", "version": "0.1.0", "checks": {"database": "ok"}}
    good = MagicMock()
    good.status_code = 200
    good.json = MagicMock(return_value=ok_payload)

    with patch.object(
        MODULE.httpx,
        "get",
        side_effect=[httpx.ConnectError("boom"), good],
    ) as mock_get:
        code = MODULE.run_check(
            "https://example.com",
            5.0,
            max_attempts=3,
            backoff_sec=0.0,
        )

    assert code == 0
    assert mock_get.call_count == 2
