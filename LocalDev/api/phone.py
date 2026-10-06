"""Phone-number normalization — the ONE sanctioned conversion point.

Decision: phone numbers are stored in **E.164** everywhere (`members.phone`),
and every write path converts through `to_e164` here. There
is no second normalizer: SQL-side conversion exists only inside the one-time
backfill in `migrations/0149_phone_e164.sql`, which reproduces these exact
rules so the stored data and this function can never disagree.

Rationale: the check-in page collected a 10-digit US number while
`PhoneCheckIn` demanded exactly 9 digits, so *every* phone check-in 422'd, and
members seeded with bare 9-digit strings could never match an SMS-formatted
`+1...` number. A single canonical representation removes the whole class of
"same number, different spelling" lookup failures.

Pure module: stdlib only, no I/O, no framework imports — safe to import from
services, schemas, scripts, and tests alike.
"""

from __future__ import annotations

import re

__all__ = ["to_e164"]

_DIGITS = re.compile(r"\D")

# E.164 allows at most 15 digits; 8 is the shortest plausible national number.
_MIN_DIGITS = 8
_MAX_DIGITS = 15


def to_e164(raw: str | None) -> str | None:
    """Normalize a human-entered phone number to E.164, or return None.

    Rules, applied in order:
      1. non-string / empty            -> None
      2. leading '+' (international)   -> '+' + digits, if 8..15 digits
      3. exactly 10 digits (US local)  -> '+1' + digits
      4. 11 digits starting with '1'   -> '+' + digits
      5. anything else                 -> None

    None means "not a usable phone number" — callers must treat it as a
    validation failure or store NULL, never as an empty string.

    >>> to_e164("(555) 111-0001")
    '+15551110001'
    >>> to_e164("+1 555 111 0001")
    '+15551110001'
    >>> to_e164("555111001")   # 9 digits — the legacy seed format
    >>> to_e164("   ")
    """
    if not isinstance(raw, str):
        return None

    stripped = raw.strip()
    if not stripped:
        return None

    digits = _DIGITS.sub("", stripped)
    if not digits:
        return None

    if stripped.startswith("+"):
        if _MIN_DIGITS <= len(digits) <= _MAX_DIGITS:
            return f"+{digits}"
        return None

    if len(digits) == 10:
        return f"+1{digits}"

    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"

    return None
