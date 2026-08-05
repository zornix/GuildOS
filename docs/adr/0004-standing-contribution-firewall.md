# Standing and contribution are firewalled — negative-action only ever drives standing

Standing derives from exactly two inputs: unpaid fines and unexcused absences
at required events. Contribution (initiatives chaired, events helped organize
via approved jobs, events attended) lives in its own domain and is never
joined into the standing computation — not as an input, not as a reason code,
not on the same surface as standing enforcement. The `INCOMPLETE_REQUIRED_TASKS`
reason code is removed accordingly. This is a hazing-liability and
product-health constraint: the moment "didn't contribute enough" can hurt a
member's standing, the app becomes a pressure instrument, and contribution
stats become quotas.

Decided 2026-07-23 during the member-first pivot grill.

## Considered Options

- **Blend contribution into standing** (points, engagement-weighted standing) —
  rejected: converts positive signals into enforcement, recreating the OmegaFi
  failure mode and a hazing-adjacent quota system.
- **Ranked contribution roster / leaderboard** — rejected: bottom-of-list
  visibility is punishment by another name. Only positive-only shoutouts
  (top-N, personal milestones) are allowed; no full ranking is ever rendered.
- **Manual or officer-verified contribution credit** — rejected: if a stat
  requires a human to verify it, it doesn't exist. Only structurally-derived
  facts (role assignments, approved jobs, check-ins) count.

## Consequences

- Contribution counters live in their own domain package and never import
  from or feed `memberadmin` standing code; a test asserts standing inputs
  are limited to fines + unexcused absences.
- **Deliberate exception:** the officer-only engagement score
  (`api/memberadmin/services/scoring.py`), which blends attendance, excuses,
  and fines to help officers spot disengagement, is kept. It is never
  member-visible, never feeds standing, and must stay officer-only; it is an
  accepted tension with this firewall, not a precedent.
