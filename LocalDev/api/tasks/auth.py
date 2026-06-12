"""Tasks domain permissions — thin layer over the central RBAC helper."""

from __future__ import annotations

from api.rbac.auth import require_permission  # noqa: F401  (domain re-export)

TASKS_CREATE = "tasks:create"
TASKS_ASSIGN = "tasks:assign"
TASKS_COMPLETE = "tasks:complete"
TASKS_REVIEW = "tasks:review"
