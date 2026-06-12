"""derive_standing — behavior-preserving thresholds + additive reason codes."""

from __future__ import annotations

from api.memberadmin.core.standing_rules import (
    HIGH_UNPAID_BALANCE,
    INCOMPLETE_REQUIRED_TASKS,
    UNEXCUSED_ABSENCES,
    UNPAID_FINES,
    derive_standing,
)


def test_clean_member_is_good_standing_with_no_reasons():
    assert derive_standing(unpaid_count=0, unpaid_total=0, unexcused=0) == ("good_standing", [])


def test_one_unpaid_fine_is_warning():
    status, reasons = derive_standing(unpaid_count=1, unpaid_total=10, unexcused=0)
    assert status == "warning"
    assert reasons == [UNPAID_FINES]


def test_legacy_delinquent_thresholds_unchanged():
    assert derive_standing(unpaid_count=2, unpaid_total=20, unexcused=0)[0] == "delinquent"
    assert derive_standing(unpaid_count=0, unpaid_total=50, unexcused=0)[0] == "delinquent"
    assert derive_standing(unpaid_count=0, unpaid_total=0, unexcused=3)[0] == "delinquent"


def test_high_balance_reason_code():
    _, reasons = derive_standing(unpaid_count=1, unpaid_total=60, unexcused=0)
    assert HIGH_UNPAID_BALANCE in reasons


def test_unexcused_absence_reason_code():
    status, reasons = derive_standing(unpaid_count=0, unpaid_total=0, unexcused=1)
    assert status == "warning"
    assert reasons == [UNEXCUSED_ABSENCES]


def test_incomplete_required_tasks_adds_reason_but_not_status():
    status, reasons = derive_standing(
        unpaid_count=0, unpaid_total=0, unexcused=0, incomplete_required_tasks=2
    )
    assert status == "good_standing"  # tasks signal is reason-only for now
    assert reasons == [INCOMPLETE_REQUIRED_TASKS]
