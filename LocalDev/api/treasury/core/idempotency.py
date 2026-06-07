"""Idempotency contract for Treasury mutations."""

from __future__ import annotations

IDEMPOTENCY_HEADER = "Idempotency-Key"


def idempotency_operation(name: str) -> str:
    if not name or not name.strip():
        raise ValueError("idempotency operation name is required")
    return name.strip()
