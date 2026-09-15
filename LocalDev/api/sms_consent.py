"""SMS consent — the one definition of "may we text this member" (#57).

A member is reachable by SMS only with prior express consent that has not been
withdrawn (migration 0157):

    consented == sms_consent_at IS NOT NULL AND sms_opted_out_at IS NULL

Kept beside `api/phone.py` as a pure stdlib module for the same reason: the rule
is needed by the outbox drain, the announcement dispatcher, the roster importer
and the Twilio inbound webhook, and a rule copied into four places is a rule that
will disagree with itself.
"""

from __future__ import annotations

__all__ = ["CONSENT_COLUMNS", "has_consent", "is_truthy"]

# The columns every caller must select for has_consent() to be meaningful.
CONSENT_COLUMNS = "sms_consent_at, sms_opted_out_at"

# What counts as a "yes" in a roster CSV's consent column. Anything else —
# including an empty cell or a missing column — is not consent.
_TRUTHY = {"yes", "y", "true", "1"}


def has_consent(member: dict | None) -> bool:
    """True when this member row may be texted. A missing row is never consent."""
    row = member or {}
    return bool(row.get("sms_consent_at")) and not row.get("sms_opted_out_at")


def is_truthy(raw: str | None) -> bool:
    """Parse a CSV consent cell. Silence, blanks and 'no' all mean no."""
    return (raw or "").strip().lower() in _TRUTHY
