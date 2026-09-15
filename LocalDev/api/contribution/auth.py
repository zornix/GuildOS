"""Contribution domain permissions.

A member always reads their own record (`/me`, no permission key). Reading
another member's record reuses the existing officer members-read gate,
`standing:view_all` — the key that already lets an officer open any member's
per-member record. No new key: the catalog already answers "may this actor
read another member's record?", and ADR-0004's firewall is about data flow
(contribution never feeds standing), not about which gate guards the read.
"""

from __future__ import annotations

MEMBER_RECORD_VIEW_ANY = "standing:view_all"
