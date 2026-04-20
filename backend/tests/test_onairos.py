"""Onairos service + memory-slot formatter + context-builder wiring."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from services.onairos_service import OnairosService


# --------------------------------------------------------------------------- #
#  format_traits_slot — pure, no DB                                            #
# --------------------------------------------------------------------------- #

def test_format_traits_slot_returns_none_when_no_cache():
    assert OnairosService.format_traits_slot(None) is None
    assert OnairosService.format_traits_slot({}) is None
    assert OnairosService.format_traits_slot({"traits": {}}) is None


def test_format_traits_slot_ranks_top_positive_and_improve():
    line = OnairosService.format_traits_slot({
        "traits": {
            "positive_traits": {
                "curious": 9.7,
                "driven": 8.4,
                "calm": 7.1,
                "patient": 5.2,
            },
            "traits_to_improve": {
                "impulsive": 6.3,
                "procrastination": 8.1,
            },
        }
    })
    assert line is not None
    assert line.startswith("- traits (onairos):")
    # Top-3 positive, highest first
    assert "curious (9.7)" in line
    assert "driven (8.4)" in line
    assert "calm (7.1)" in line
    assert "patient" not in line  # trimmed to top 3
    # Top-2 improve, highest first
    assert "procrastination (8.1)" in line
    assert "impulsive (6.3)" in line


def test_format_traits_slot_handles_malformed_scores_gracefully():
    line = OnairosService.format_traits_slot({
        "traits": {
            "positive_traits": {"focus": "not-a-number", "grit": 9.0},
        }
    })
    # Should still produce a line without crashing on the bad score
    assert line is not None
    assert "grit (9.0)" in line


# --------------------------------------------------------------------------- #
#  MEMORY SLOT integration inside _format_memory_slots                         #
# --------------------------------------------------------------------------- #

@dataclass
class _DummyUser:
    coaching_tone: str = "direct"


@dataclass
class _DummyState:
    primary_goal: str | None = "clear_skin"
    injuries: list = field(default_factory=list)
    preferred_tone: str | None = "direct"


def test_format_memory_slots_appends_onairos_line_when_traits_present():
    from services.coaching_service import _format_memory_slots

    onboarding = {"goals": ["clear skin"], "skin_type": "oily"}
    traits = {
        "traits": {
            "positive_traits": {"curious": 9.5, "driven": 8.8},
            "traits_to_improve": {"impulsive": 4.2},
        }
    }
    out = _format_memory_slots(
        _DummyUser(), onboarding, _DummyState(), onairos_traits=traits
    )
    assert "MEMORY SLOTS:" in out
    assert "- goals:" in out
    assert "- traits (onairos):" in out
    assert "curious (9.5)" in out


def test_format_memory_slots_skips_onairos_when_traits_absent():
    from services.coaching_service import _format_memory_slots

    onboarding = {"goals": ["clear skin"]}
    out = _format_memory_slots(_DummyUser(), onboarding, _DummyState())
    assert "- traits (onairos):" not in out
    # Core slots still present
    assert "- goals:" in out
    assert "- tone:" in out


# --------------------------------------------------------------------------- #
#  Service persistence (save_handoff, mark_revoked)                            #
# --------------------------------------------------------------------------- #

class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeDB:
    """Minimal async DB stub that understands the OnairosService query shape.

    Tracks added rows + commits so tests can assert round-trip persistence.
    """

    def __init__(self, initial_row=None):
        self._row = initial_row
        self.added: list = []
        self.commits: int = 0
        self.refreshes: int = 0

    async def execute(self, _statement):
        return _FakeResult(self._row)

    def add(self, obj):
        self.added.append(obj)
        self._row = obj

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        self.refreshes += 1


@pytest.mark.asyncio
async def test_save_handoff_creates_new_connection():
    service = OnairosService()
    db = _FakeDB()
    user_id = str(uuid4())
    conn = await service.save_handoff(
        user_id,
        db,
        api_url="https://api2.onairos.uk/inf/abc",
        access_token="eyJfake.token.payload",
        approved_requests={"personality_traits": True},
        user_basic={"basic": {"name": "nisha"}},
    )
    assert conn.api_url == "https://api2.onairos.uk/inf/abc"
    assert conn.access_token == "eyJfake.token.payload"
    assert conn.approved_requests == {"personality_traits": True}
    assert conn.user_basic == {"basic": {"name": "nisha"}}
    assert conn.revoked_at is None
    assert conn.user_id == UUID(user_id)
    assert db.commits >= 1


@pytest.mark.asyncio
async def test_save_handoff_updates_existing_and_clears_revoked():
    from models.sqlalchemy_models import UserOnairosConnection

    existing = UserOnairosConnection(
        user_id=uuid4(),
        api_url="https://old.example/inf",
        access_token="old",
        approved_requests={},
        revoked_at=datetime.now(timezone.utc),
    )
    service = OnairosService()
    db = _FakeDB(initial_row=existing)

    updated = await service.save_handoff(
        str(existing.user_id),
        db,
        api_url="https://new.example/inf",
        access_token="new",
        approved_requests={"personality_traits": True},
    )
    assert updated is existing  # same row, mutated
    assert updated.api_url == "https://new.example/inf"
    assert updated.access_token == "new"
    assert updated.revoked_at is None
    assert updated.approved_requests == {"personality_traits": True}


@pytest.mark.asyncio
async def test_mark_revoked_clears_traits_and_returns_false_when_missing():
    from models.sqlalchemy_models import UserOnairosConnection

    service = OnairosService()

    # Missing row → False
    db_missing = _FakeDB(initial_row=None)
    assert await service.mark_revoked(str(uuid4()), db_missing) is False

    # Existing row → revoked + traits cleared
    row = UserOnairosConnection(
        user_id=uuid4(),
        api_url="https://x",
        access_token="t",
        approved_requests={},
        traits_cached={"traits": {"positive_traits": {"grit": 9.0}}},
        traits_cached_at=datetime.now(timezone.utc),
    )
    db = _FakeDB(initial_row=row)
    assert await service.mark_revoked(str(row.user_id), db) is True
    assert row.revoked_at is not None
    assert row.traits_cached is None
    assert row.traits_cached_at is None


@pytest.mark.asyncio
async def test_get_active_traits_respects_revoked():
    from models.sqlalchemy_models import UserOnairosConnection

    service = OnairosService()
    row = UserOnairosConnection(
        user_id=uuid4(),
        api_url="https://x",
        access_token="t",
        approved_requests={},
        traits_cached={"traits": {"positive_traits": {"curious": 9.5}}},
        traits_cached_at=datetime.now(timezone.utc),
    )
    db_active = _FakeDB(initial_row=row)
    assert await service.get_active_traits(str(row.user_id), db_active) is not None

    row.revoked_at = datetime.now(timezone.utc)
    db_revoked = _FakeDB(initial_row=row)
    assert await service.get_active_traits(str(row.user_id), db_revoked) is None
