"""ADR-0004: standing's inputs stay fines + unexcused absences.

Adding a contribution signal to standing turns positive participation into a
quota. These assertions fail the moment one is wired in.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from api.memberadmin.core import standing_rules
from api.memberadmin.services import standing


def _imported_modules(path: str | Path) -> set[str]:
    """Every module imported by `path`, from the AST (docstrings don't count)."""
    tree = ast.parse(Path(path).read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_derive_standing_takes_only_fines_and_unexcused_absences():
    params = set(inspect.signature(standing_rules.derive_standing).parameters)
    assert params == {"unpaid_count", "unpaid_total_cents", "unexcused"}


def test_standing_reason_codes_name_no_contribution_signal():
    codes = {
        v for k, v in vars(standing_rules).items()
        if k.isupper() and isinstance(v, str) and k != "STANDING_STATUSES"
    }
    assert codes == {"UNPAID_FINES", "HIGH_UNPAID_BALANCE", "UNEXCUSED_ABSENCES"}


def test_standing_computation_reads_no_contribution_source():
    """The standing module imports the engagement aggregate and nothing else —
    no tasks, initiatives, organizers, supervisors or contribution package."""
    assert _imported_modules(inspect.getfile(standing)) == {
        "__future__",
        "api.memberadmin.core.engagement",
        "api.memberadmin.core.standing_rules",
    }


def test_contribution_never_imports_standing():
    """…and the firewall holds in the other direction too."""
    paths = list((Path(__file__).resolve().parents[2] / "api/contribution").rglob("*.py"))
    assert paths, "no contribution modules found — the check would pass vacuously"
    for path in paths:
        imported = _imported_modules(path)
        assert not any("memberadmin" in m for m in imported), f"{path} imports memberadmin"
