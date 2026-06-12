"""Domain-local schema contracts for the scaffolded services (no DB)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.announcements.api.schemas import AnnouncementCreate
from api.attendance.api.schemas import SessionCreate
from api.bylaws.api.schemas import BylawsQuery
from api.events.api.schemas import EventCreate
from api.nl_controller.api.schemas import CommandReview
from api.recruitment.api.schemas import RecruitStageUpdate
from api.tasks.api.schemas import TaskCreate, TaskStatusUpdate


def test_task_status_rejects_unknown_status():
    with pytest.raises(ValidationError):
        TaskStatusUpdate(status="finished")
    assert TaskStatusUpdate(status="done").status == "done"


def test_task_create_defaults():
    t = TaskCreate(title="Book venue")
    assert t.required is False and t.assigned_member_id is None


def test_announcement_audience_includes_treasury_seam():
    a = AnnouncementCreate(title="Dues", body="Pay up", audience="members_with_balance")
    assert a.audience == "members_with_balance"
    with pytest.raises(ValidationError):
        AnnouncementCreate(title="x", body="y", audience="everyone")


def test_session_mode_constrained():
    assert SessionCreate(event_id="e1").mode == "short_link"
    with pytest.raises(ValidationError):
        SessionCreate(event_id="e1", mode="telepathy")


def test_recruit_stage_constrained():
    assert RecruitStageUpdate(stage="bid_extended").stage == "bid_extended"
    with pytest.raises(ValidationError):
        RecruitStageUpdate(stage="ghosted")


def test_command_review_decision_constrained():
    assert CommandReview(decision="approve").decision == "approve"
    with pytest.raises(ValidationError):
        CommandReview(decision="maybe")


def test_bylaws_query_requires_question():
    with pytest.raises(ValidationError):
        BylawsQuery(question="")


def test_event_create_visibility_validated_and_defaulted():
    e = EventCreate(title="Chapter", date="2026-06-20", time="19:00", location="House")
    assert e.visibility == "chapter" and e.event_type is None
    with pytest.raises(ValidationError):
        EventCreate(title="x", date="2026-06-20", time="19:00", location="h", visibility="secret")


def test_bylaws_query_stub_never_fabricates_an_answer():
    """The bylaws Q&A boundary must stay honest until a real layer exists."""

    class _Q:
        def __init__(self):
            self.data = []

        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def order(self, *_a, **_k):
            return self

        def execute(self):
            return self

    class _Sb:
        def table(self, _name):
            return _Q()

    from api.bylaws.services.documents import query_bylaws

    result = query_bylaws(_Sb(), chapter_id="c-1", question="Can we hold elections remotely?")
    assert result["status"] == "not_implemented"
    assert result["answer"] is None
