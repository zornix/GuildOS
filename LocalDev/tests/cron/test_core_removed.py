"""The obsolete cron core package must not return."""
from pathlib import Path


def test_obsolete_cron_core_package_is_removed():
    assert not (Path(__file__).resolve().parents[2] / "api" / "cron" / "core" / "__init__.py").exists()
