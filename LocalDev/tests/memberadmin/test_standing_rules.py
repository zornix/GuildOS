"""derive_standing — behavior-preserving thresholds + additive reason codes."""

from __future__ import annotations

import inspect

from api.memberadmin.core.standing_rules import (
    HIGH_UNPAID_BALANCE,
    UNEXCUSED_ABSENCES,
    UNPAID_FINES,
    derive_standing,
)


def test_clean_member_is_good_standing_with_no_reasons():
    assert derive_standing(unpaid_count=0, unpaid_total_cents=0, unexcused=0) == ("good_standing", [])


def test_one_unpaid_fine_is_warning():
    status, reasons = derive_standing(unpaid_count=1, unpaid_total_cents=1000, unexcused=0)
    assert status == "warning"
    assert reasons == [UNPAID_FINES]


def test_legacy_delinquent_thresholds_unchanged():
    assert derive_standing(unpaid_count=2, unpaid_total_cents=2000, unexcused=0)[0] == "delinquent"
    assert derive_standing(unpaid_count=0, unpaid_total_cents=5000, unexcused=0)[0] == "delinquent"
    assert derive_standing(unpaid_count=0, unpaid_total_cents=0, unexcused=3)[0] == "delinquent"


def test_high_balance_reason_code():
    _, reasons = derive_standing(unpaid_count=1, unpaid_total_cents=6000, unexcused=0)
    assert HIGH_UNPAID_BALANCE in reasons


def test_unexcused_absence_reason_code():
    status, reasons = derive_standing(unpaid_count=0, unpaid_total_cents=0, unexcused=1)
    assert status == "warning"
    assert reasons == [UNEXCUSED_ABSENCES]


# ── ADR-0004: the standing / contribution firewall ───────────────────────────
# Standing derives from unpaid fines + unexcused absences and NOTHING else.
# These tests pin the firewall structurally so a future "engagement-weighted
# standing" change fails here first rather than in production.


def test_standing_inputs_are_only_fines_and_unexcused_absences():
    params = inspect.signature(derive_standing).parameters
    assert set(params) == {"unpaid_count", "unpaid_total_cents", "unexcused"}
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params.values())


def test_no_contribution_signal_is_a_standing_input():
    """No task/event/initiative/contribution input may exist — ADR-0004."""
    forbidden = ("task", "event", "job", "initiative", "contribution", "organiz", "supervis")
    params = inspect.signature(derive_standing).parameters
    for name in params:
        assert not any(word in name for word in forbidden), (
            f"ADR-0004 violation: contribution signal '{name}' is a standing input"
        )


def test_no_contribution_reason_code_is_exported():
    import api.memberadmin.core.standing_rules as rules

    forbidden = ("TASK", "JOB", "INITIATIVE", "CONTRIBUTION", "ORGANIZ", "SUPERVIS")
    reason_codes = [
        name for name in vars(rules)
        if name.isupper() and isinstance(getattr(rules, name), str)
    ]
    for code in reason_codes:
        assert not any(word in code for word in forbidden), (
            f"ADR-0004 violation: contribution reason code '{code}' exists"
        )


def test_standing_module_does_not_import_the_contribution_domain():
    """The firewall is also an import boundary (ADR-0004 consequences)."""
    import api.memberadmin.services.standing as standing_svc

    source = inspect.getsource(standing_svc)
    assert "api.tasks" not in source
    assert "api.initiatives" not in source
