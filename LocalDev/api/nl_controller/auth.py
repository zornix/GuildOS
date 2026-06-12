"""NL controller domain permissions — thin layer over the central RBAC helper."""

from __future__ import annotations

from api.rbac.auth import require_permission  # noqa: F401  (domain re-export)

NL_EXECUTE = "nl_controller:execute"
NL_APPROVE = "nl_controller:approve"
