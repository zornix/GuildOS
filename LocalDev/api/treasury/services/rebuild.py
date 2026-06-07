"""Rebuild service — run the shadow reconstruction and return a drift report.

Thin wrapper over `RebuildEngine`. Gated on `rebuild:run` at the HTTP boundary.
`apply_repairs=True` lets the engine overwrite ONLY the balance cache; it never
mutates the append-only `big_ledger`.
"""

from __future__ import annotations

from dataclasses import asdict

from api.treasury.core.rebuild import RebuildEngine


def run_rebuild(sb, *, chapter_id: str, apply_repairs: bool = False) -> dict:
    report = RebuildEngine(sb).rebuild(chapter_id, apply_repairs=apply_repairs)
    payload = asdict(report)
    payload["is_clean"] = report.is_clean
    return payload
