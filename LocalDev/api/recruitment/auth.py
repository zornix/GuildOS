"""Recruitment domain permissions — thin layer over the central RBAC helper."""

from __future__ import annotations

from api.rbac.auth import require_permission  # noqa: F401  (domain re-export)

PIPELINE_VIEW = "recruitment:pipeline:view"
PIPELINE_UPDATE = "recruitment:pipeline:update"
