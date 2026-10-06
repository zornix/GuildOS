"""Fine policy constants (GreekOS V1).

Flat $25 for V1 — no fine schedule (explicitly deferred), and
fines are NEVER automatic. The Finance Board issues fine invoices by hand at
least 24 hours after a required event's attendance time.
"""

from __future__ import annotations

# Flat V1 fine, integer cents (money is integer cents everywhere — core/money.py).
FLAT_FINE_CENTS = 2500

# Fines may only be issued once this many hours have passed since the event start.
FINE_ISSUE_DELAY_HOURS = 24
