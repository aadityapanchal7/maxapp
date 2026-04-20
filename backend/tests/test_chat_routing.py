from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from api import chat as chat_api
from services import lc_agent as lc_agent_mod
from services import lc_graph
from services import schedule_service as schedule_service_mod


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


@dataclass
class _DummyUser:
    profile: dict = field(default_factory=dict)
    onboarding: dict = field(default_factory=dict)
    schedule_preferences: dict = field(default_factory=dict)
    coaching_tone: str = "default"
    updated_at: object | None = None


class _FakeDB:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.user = _DummyUser()

    async def execute(self, _statement):
        return _FakeResult([])

    async def get(self, _model, _user_uuid):
        return self.user

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_process_chat_message_routes_knowledge_away_from_context_and_agent(monkeypatch):
    fake_db = _FakeDB()

    async def _no_schedule(*_args, **_kwargs):
        return None

    async def _should_not_build_context(*_args, **_kwargs):
        raise AssertionError("build_full_context should not run for strict knowledge turns")

    async def _fake_answer_from_rag(**_kwargs):
        return (
            "use the PM routine from the docs. [source: rag_docs/skinmax/routines.md > PM routine]",
            [{"id": "routines:0:abc123", "content": "PM routine", "metadata": {"source": "rag_docs/skinmax/routines.md", "section": "PM routine"}}],
        )

    monkeypatch.setattr(schedule_service_mod.schedule_service, "get_current_schedule", _no_schedule)
    monkeypatch.setattr(schedule_service_mod.schedule_service, "get_maxx_schedule", _no_schedule)
    monkeypatch.setattr(chat_api.coaching_service, "build_full_context", _should_not_build_context)
    monkeypatch.setattr(chat_api, "answer_from_rag", _fake_answer_from_rag)
    monkeypatch.setattr(chat_api, "run_chat_agent", _should_not_build_context)

    text, choices = await chat_api.process_chat_message(
        user_id="00000000-0000-0000-0000-000000000000",
        message_text="what should i do for acne at night",
        db=fake_db,
        rds_db=None,
        channel="app",
    )

    assert choices == []
    assert "source:" in text
    assistant_rows = [row for row in fake_db.added if getattr(row, "role", "") == "assistant"]
    assert assistant_rows
    assert assistant_rows[-1].retrieved_chunk_ids == ["routines:0:abc123"]


@pytest.mark.asyncio
async def test_langgraph_knowledge_node_bypasses_agent(monkeypatch):
    lc_graph.rebuild_graph()

    fake_chunks = [
        {
            "id": "bonemax-guide:0:deadbeef",
            "content": "mewing means holding proper tongue posture on the palate.",
            "doc_title": "bonemax-guide",
            "chunk_index": 0,
            "similarity": 0.82,
            "metadata": {
                "source": "rag_docs/bonemax/bonemax-guide.md",
                "section": "mewing",
            },
        }
    ]

    async def _fake_retrieve_chunks(_db, _maxx, _query, **_kwargs):
        return list(fake_chunks)

    async def _fake_answer_from_chunks(*, message: str, retrieved: list[dict], **_kwargs):
        assert message == "what is mewing"
        assert retrieved
        return "mewing is covered in the docs. [source: rag_docs/bonemax/bonemax-guide.md > mewing]"

    async def _should_not_run_agent(*_args, **_kwargs):
        raise AssertionError("agent path should not run for graph knowledge turns")

    monkeypatch.setattr("services.rag_service.retrieve_chunks", _fake_retrieve_chunks)
    monkeypatch.setattr(lc_graph, "answer_from_chunks", _fake_answer_from_chunks)
    monkeypatch.setattr(lc_agent_mod, "run_chat_agent", _should_not_run_agent)

    result = await lc_graph.run_graph_chat(
        message="what is mewing",
        history=[],
        user_context={"coaching_context": "", "active_schedule": None, "onboarding": {}},
        user_id="00000000-0000-0000-0000-000000000000",
        make_tools=lambda: [],
        maxx_id="bonemax",
        active_maxx="bonemax",
        channel="app",
    )

    assert result["intent"] == "KNOWLEDGE"
    assert "source:" in result["response"]
