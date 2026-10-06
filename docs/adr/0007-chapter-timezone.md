# Chapter timezone for event and attendance timing

## Context

Event dates and times were stored as naive values and frequently evaluated as UTC. As a result, same-day future events in local time zones were marked as missed before they began (F-002), and task uncommit locks and fine issuance calculations drifted relative to chapter clocks (F-060).

## Decision

Decided 2026-10-05 (decision D5; migrations 0176, 0197):

1. **Chapter timezone:** Each chapter has a timezone in `chapters.timezone`, defaulting to `America/Los_Angeles`.
2. **Python timing:** Python uses `api/events/core/timing.py` (`chapter_timezone`, `event_start_utc`, `has_started`) to evaluate event start times.
3. **Database timing:** `tk_uncommit_task` uses `ev_local_start(chapter_id, date, time)` (migration 0197) for event and initiative timing. Fine issuance is gated in Python by `event_start_utc` in `api/treasury/api/fines_legacy.py`.

## Consequences

- No UI exists to change chapter timezone yet.
- When an event has no specified time, it defaults to the end of the day (23:59:59) for "has it started" checks and midnight for the task unclaim lock.
