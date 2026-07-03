"""Pure tests for the notify-gate completeness rule (no DB).

Spec §2.7 / docs/imp-ev-ph2.md §3.1: an event is "complete" (notifiable) once
it has >=1 supervisor, >=1 organizer, and >=3 non-cancelled jobs.
"""

from __future__ import annotations

from api.events.core.rules import (
    JOBS_COMPLETE_MIN,
    ORGANIZERS_COMPLETE_MIN,
    SUPERVISORS_COMPLETE_MIN,
    completeness,
)


def test_thresholds_match_spec():
    assert SUPERVISORS_COMPLETE_MIN == 1
    assert ORGANIZERS_COMPLETE_MIN == 1
    assert JOBS_COMPLETE_MIN == 3


def test_all_zero_is_incomplete():
    result = completeness(supervisor_count=0, organizer_count=0, job_count=0)
    assert result["is_complete"] is False
    by_key = {i["key"]: i for i in result["items"]}
    assert by_key["supervisors"] == {
        "key": "supervisors", "required": 1, "current": 0, "met": False,
    }
    assert by_key["organizers"] == {
        "key": "organizers", "required": 1, "current": 0, "met": False,
    }
    assert by_key["jobs"] == {
        "key": "jobs", "required": 3, "current": 0, "met": False,
    }


def test_exactly_at_thresholds_is_complete():
    result = completeness(supervisor_count=1, organizer_count=1, job_count=3)
    assert result["is_complete"] is True
    assert all(i["met"] for i in result["items"])


def test_above_thresholds_is_complete():
    result = completeness(supervisor_count=3, organizer_count=5, job_count=10)
    assert result["is_complete"] is True


def test_one_short_item_blocks_completeness():
    # 1 supervisor, 1 organizer, but only 2 jobs (< 3).
    result = completeness(supervisor_count=1, organizer_count=1, job_count=2)
    assert result["is_complete"] is False
    by_key = {i["key"]: i for i in result["items"]}
    assert by_key["jobs"]["met"] is False
    assert by_key["supervisors"]["met"] is True
    assert by_key["organizers"]["met"] is True


def test_missing_organizer_blocks_completeness():
    result = completeness(supervisor_count=2, organizer_count=0, job_count=5)
    assert result["is_complete"] is False
    by_key = {i["key"]: i for i in result["items"]}
    assert by_key["organizers"]["met"] is False


def test_missing_supervisor_blocks_completeness():
    result = completeness(supervisor_count=0, organizer_count=2, job_count=5)
    assert result["is_complete"] is False
    by_key = {i["key"]: i for i in result["items"]}
    assert by_key["supervisors"]["met"] is False


def test_items_are_returned_in_stable_order():
    result = completeness(supervisor_count=1, organizer_count=1, job_count=3)
    assert [i["key"] for i in result["items"]] == ["supervisors", "organizers", "jobs"]
