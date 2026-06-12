"""Standing statuses, reason codes, and the derived-standing rule (pure logic).

Thresholds are EXACTLY the legacy _classify_standing rules — behavior-preserving.
Reason codes are additive metadata explaining *why* a member landed in a bucket.

Cross-service signals consumed (§7 seams):
  - treasury: unpaid fine count / amount (via memberadmin.core.engagement)
  - attendance: unexcused absence count (via memberadmin.core.engagement)
  - tasks: incomplete required-task count (api.tasks.services.tasks.
    incomplete_required_tasks). TODO(standing): incomplete required tasks only
    add a reason code today; deciding whether they shift the status bucket is a
    chapter-policy question, deliberately not implemented.
"""

from __future__ import annotations

STANDING_STATUSES = ("good_standing", "warning", "delinquent")

# Reason codes
UNPAID_FINES = "UNPAID_FINES"
HIGH_UNPAID_BALANCE = "HIGH_UNPAID_BALANCE"
UNEXCUSED_ABSENCES = "UNEXCUSED_ABSENCES"
INCOMPLETE_REQUIRED_TASKS = "INCOMPLETE_REQUIRED_TASKS"


def derive_standing(
    *,
    unpaid_count: int,
    unpaid_total: float,
    unexcused: int,
    incomplete_required_tasks: int = 0,
) -> tuple[str, list[str]]:
    """Return (status, reason_codes). Status thresholds match the legacy rules:
    delinquent: 2+ unpaid fines OR $50+ unpaid OR 3+ unexcused absences;
    warning: 1+ unpaid fine OR 1+ unexcused absence."""
    reasons: list[str] = []
    if unpaid_count >= 1:
        reasons.append(UNPAID_FINES)
    if unpaid_total >= 50:
        reasons.append(HIGH_UNPAID_BALANCE)
    if unexcused >= 1:
        reasons.append(UNEXCUSED_ABSENCES)
    if incomplete_required_tasks >= 1:
        reasons.append(INCOMPLETE_REQUIRED_TASKS)

    if unpaid_count >= 2 or unpaid_total >= 50 or unexcused >= 3:
        return "delinquent", reasons
    if unpaid_count >= 1 or unexcused >= 1:
        return "warning", reasons
    return "good_standing", reasons
