from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from services.coaching_service import CoachingService, _context_requirements


class _FakeScalarResult:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return list(self._value or [])


@dataclass
class _DummyUser:
    onboarding: dict = field(default_factory=lambda: {"timezone": "UTC", "goals": ["clear skin"]})
    schedule_preferences: dict = field(default_factory=dict)
    profile: dict = field(default_factory=dict)
    first_name: str = "Nisha"
    last_name: str = ""
    username: str = "nisha"
    ai_context: str = "User wants clearer skin and hates greasy products."
    coaching_tone: str = "default"


@dataclass
class _DummyState:
    streak_days: int = 2
    missed_days: int = 0
    primary_goal: str = "clear_skin"
    weight: float | None = None
    last_sleep_hours: float | None = 7.5
    last_calories: int | None = None
    last_mood: str | None = "good"
    injuries: list = field(default_factory=list)
    preferred_tone: str = "direct"


class _FakeDB:
    def __init__(self, user: _DummyUser):
        self._user = user
        self.executed: list[str] = []

    async def get(self, _model, _user_uuid):
        return self._user

    async def execute(self, statement):
        sql = str(statement)
        self.executed.append(sql)
        if "FROM scans" in sql:
            return _FakeScalarResult(None)
        if "FROM user_schedules" in sql:
            return _FakeScalarResult([])
        if "SELECT app_users.onboarding" in sql:
            return _FakeScalarResult(self._user.onboarding)
        return _FakeScalarResult(None)


def test_context_requirements_reduce_bloat_for_greetings():
    assert _context_requirements("GREETING") == {
        "schedules": False,
        "task_completions": False,
        "module_engines": False,
    }
    assert _context_requirements("CHECK_IN")["module_engines"] is True


@pytest.mark.asyncio
async def test_build_full_context_skips_schedule_queries_for_greeting(monkeypatch):
    service = CoachingService()
    fake_db = _FakeDB(_DummyUser())
    async def _fake_state(*_args, **_kwargs):
        return _DummyState()
    monkeypatch.setattr(service, "get_or_create_state", _fake_state)

    context = await service.build_full_context("00000000-0000-0000-0000-000000000000", fake_db, None, intent="GREETING")

    assert "MEMORY SLOTS:" in context
    assert "RECENT MEMORY SUMMARY:" in context
    assert "SCHEDULE (" not in context
    assert not any("FROM user_schedules" in sql for sql in fake_db.executed)


@pytest.mark.asyncio
async def test_build_full_context_queries_schedules_for_check_in(monkeypatch):
    service = CoachingService()
    fake_db = _FakeDB(_DummyUser())
    async def _fake_state(*_args, **_kwargs):
        return _DummyState()
    monkeypatch.setattr(service, "get_or_create_state", _fake_state)

    await service.build_full_context("00000000-0000-0000-0000-000000000000", fake_db, None, intent="CHECK_IN")

    assert any("FROM user_schedules" in sql for sql in fake_db.executed)
