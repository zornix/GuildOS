"""Standing statuses, reason codes, and the derived-standing rule (pure logic).

Thresholds are EXACTLY the legacy _classify_standing rules — behavior-preserving.
Reason codes are additive metadata explaining *why* a member landed in a bucket.

Standing has exactly two inputs (ADR-0004, the standing/contribution firewall):
  - treasury: unpaid fine count / amount (via memberadmin.core.engagement)
  - attendance: unexcused absence count (via memberadmin.core.engagement)

Contribution signals (tasks committed/completed, events organized or
supervised, initiatives chaired) are deliberately NOT inputs here — not as a
status driver and not as a reason code. Adding one turns positive-participation
stats into a quota that can hurt a member's standing, which is the exact
hazing-liability failure mode ADR-0004 forbids.
"""

from __future__ import annotations

STANDING_STATUSES = ("good_standing", "warning", "delinquent")

# Reason codes
UNPAID_FINES = "UNPAID_FINES"
HIGH_UNPAID_BALANCE = "HIGH_UNPAID_BALANCE"
UNEXCUSED_ABSENCES = "UNEXCUSED_ABSENCES"


def derive_standing(
    *,
    unpaid_count: int,
    unpaid_total_cents: int,
    unexcused: int,
) -> tuple[str, list[str]]:
    """Return (status, reason_codes). Status thresholds match the legacy rules:
    delinquent: 2+ unpaid fines OR $50+ unpaid OR 3+ unexcused absences;
    warning: 1+ unpaid fine OR 1+ unexcused absence.

    `unpaid_total_cents` is integer cents; the $50 cutoff is 5000 cents."""
    reasons: list[str] = []
    if unpaid_count >= 1:
        reasons.append(UNPAID_FINES)
    if unpaid_total_cents >= 5000:
        reasons.append(HIGH_UNPAID_BALANCE)
    if unexcused >= 1:
        reasons.append(UNEXCUSED_ABSENCES)

    if unpaid_count >= 2 or unpaid_total_cents >= 5000 or unexcused >= 3:
        return "delinquent", reasons
    if unpaid_count >= 1 or unexcused >= 1:
        return "warning", reasons
    return "good_standing", reasons
