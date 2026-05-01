import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_prod_status.py"
SPEC = importlib.util.spec_from_file_location("check_prod_status", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_evaluate_health_payload_accepts_ok_status() -> None:
    healthy, reason = MODULE.evaluate_health_payload({"status": "ok"})
    assert healthy is True
    assert reason == "status=ok"


def test_evaluate_health_payload_rejects_non_ok_status() -> None:
    healthy, reason = MODULE.evaluate_health_payload({"status": "degraded"})
    assert healthy is False
    assert reason == "status=degraded"


def test_evaluate_health_payload_rejects_non_dict_payload() -> None:
    healthy, reason = MODULE.evaluate_health_payload("not-json")
    assert healthy is False
    assert reason == "response was not a JSON object"
