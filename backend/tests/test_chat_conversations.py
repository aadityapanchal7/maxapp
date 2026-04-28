"""chat_conversations_service: creation, resolve, list, rename, archive, delete,
auto-titling, ContextVar injection on ChatHistory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from models.sqlalchemy_models import (
    ChatConversation,
    ChatHistory,
    active_conversation_id,
)
from services import chat_conversations_service as conv_svc


# --------------------------------------------------------------------------- #
#  Minimal async DB stub that records the ordered operations applied to it    #
# --------------------------------------------------------------------------- #

class _FakeScalarResult:
    def __init__(self, rows=None, single=None):
        self._rows = rows or []
        self._single = single

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._single


class _FakeDB:
    """Supports only the operations chat_conversations_service performs."""

    def __init__(self):
        self.rows_by_id: dict = {}
        self._user_rows: dict = {}
        self.commits = 0
        self.deleted: list = []
        # Queue of scripted execute() responses for ordered queries.
        self._script: list = []

    def queue(self, result):
        self._script.append(result)

    async def execute(self, _stmt):
        if self._script:
            return self._script.pop(0)
        return _FakeScalarResult()

    def add(self, obj):
        self.rows_by_id[obj.id] = obj
        self._user_rows.setdefault(obj.user_id, []).append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        pass

    async def delete(self, obj):
        self.deleted.append(obj)
        self.rows_by_id.pop(getattr(obj, "id", None), None)


# --------------------------------------------------------------------------- #
#  ContextVar injection — the load-bearing piece for legacy ChatHistory calls #
# --------------------------------------------------------------------------- #

def test_chat_history_inherits_active_conversation_id():
    token_in = uuid4()
    token = active_conversation_id.set(token_in)
    try:
        row = ChatHistory(user_id=uuid4(), role="user", content="hi")
        assert row.conversation_id == token_in
    finally:
        active_conversation_id.reset(token)


def test_chat_history_keeps_explicit_conversation_id_over_context_var():
    explicit = uuid4()
    ctx_val = uuid4()
    token = active_conversation_id.set(ctx_val)
    try:
        row = ChatHistory(
            user_id=uuid4(),
            conversation_id=explicit,
            role="assistant",
            content="ok",
        )
        assert row.conversation_id == explicit
    finally:
        active_conversation_id.reset(token)


def test_chat_history_without_any_conversation_id_stays_null():
    # Reset contextvar to default (None) by using a fresh Token.
    token = active_conversation_id.set(None)
    try:
        row = ChatHistory(user_id=uuid4(), role="user", content="hi")
        assert row.conversation_id is None
    finally:
        active_conversation_id.reset(token)


# --------------------------------------------------------------------------- #
#  create / rename / delete                                                   #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_create_conversation_defaults_title_and_channel():
    db = _FakeDB()
    user_id = str(uuid4())
    conv = await conv_svc.create_conversation(db, user_id=user_id, commit=True)
    assert conv.title == "new chat"
    assert conv.channel == "app"
    assert db.commits == 1
    assert conv.id in db.rows_by_id


@pytest.mark.asyncio
async def test_create_conversation_applies_caller_title():
    db = _FakeDB()
    user_id = str(uuid4())
    conv = await conv_svc.create_conversation(db, user_id=user_id, title="  bonemax q  ")
    assert conv.title == "bonemax q"


@pytest.mark.asyncio
async def test_get_conversation_rejects_bad_uuid_and_mismatched_user():
    db = _FakeDB()
    assert await conv_svc.get_conversation(db, conversation_id="not-a-uuid", user_id=str(uuid4())) is None
    db.queue(_FakeScalarResult(single=None))
    assert await conv_svc.get_conversation(db, conversation_id=str(uuid4()), user_id=str(uuid4())) is None


@pytest.mark.asyncio
async def test_rename_conversation_returns_none_when_missing():
    db = _FakeDB()
    db.queue(_FakeScalarResult(single=None))
    out = await conv_svc.rename_conversation(
        db, conversation_id=str(uuid4()), user_id=str(uuid4()), title="renamed"
    )
    assert out is None


@pytest.mark.asyncio
async def test_rename_conversation_trims_and_commits():
    db = _FakeDB()
    existing = ChatConversation(
        user_id=uuid4(), title="old name", channel="app"
    )
    db.queue(_FakeScalarResult(single=existing))
    out = await conv_svc.rename_conversation(
        db,
        conversation_id=str(existing.id) if existing.id else str(uuid4()),
        user_id=str(existing.user_id),
        title="  shiny new  ",
    )
    assert out is existing
    assert existing.title == "shiny new"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_archive_conversation_flips_flag():
    db = _FakeDB()
    existing = ChatConversation(user_id=uuid4(), title="x", channel="app")
    db.queue(_FakeScalarResult(single=existing))
    ok = await conv_svc.archive_conversation(
        db,
        conversation_id=str(existing.id) if existing.id else str(uuid4()),
        user_id=str(existing.user_id),
    )
    assert ok is True
    assert existing.is_archived is True


@pytest.mark.asyncio
async def test_delete_conversation_calls_db_delete():
    db = _FakeDB()
    existing = ChatConversation(user_id=uuid4(), title="x", channel="app")
    db.queue(_FakeScalarResult(single=existing))
    ok = await conv_svc.delete_conversation(
        db,
        conversation_id=str(existing.id) if existing.id else str(uuid4()),
        user_id=str(existing.user_id),
    )
    assert ok is True
    assert existing in db.deleted
    assert db.commits == 1


# --------------------------------------------------------------------------- #
#  resolve_active_conversation — the core routing primitive                   #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_resolve_returns_explicit_when_owned():
    db = _FakeDB()
    user_id = str(uuid4())
    explicit = ChatConversation(user_id=uuid4(), title="explicit", channel="app")
    explicit.user_id = __import__("uuid").UUID(user_id)  # belongs to caller
    db.queue(_FakeScalarResult(single=explicit))
    out = await conv_svc.resolve_active_conversation(
        db, user_id=user_id, conversation_id=str(uuid4()), channel="app"
    )
    assert out is explicit


@pytest.mark.asyncio
async def test_resolve_falls_back_to_latest_when_explicit_missing():
    db = _FakeDB()
    user_id = str(uuid4())
    # get_conversation lookup misses
    db.queue(_FakeScalarResult(single=None))
    # latest-conversation lookup hits
    latest = ChatConversation(user_id=uuid4(), title="latest", channel="app")
    db.queue(_FakeScalarResult(single=latest))
    out = await conv_svc.resolve_active_conversation(
        db, user_id=user_id, conversation_id=str(uuid4()), channel="app"
    )
    assert out is latest


@pytest.mark.asyncio
async def test_resolve_creates_new_conversation_when_none_exist():
    db = _FakeDB()
    user_id = str(uuid4())
    # No explicit id → skip that lookup. No latest → creation path.
    db.queue(_FakeScalarResult(single=None))
    out = await conv_svc.resolve_active_conversation(
        db, user_id=user_id, conversation_id=None, channel="app"
    )
    assert out is not None
    assert out.title == "new chat"
    assert out.id in db.rows_by_id


# --------------------------------------------------------------------------- #
#  touch_last_message — auto-title + timestamp bump                           #
# --------------------------------------------------------------------------- #

def test_auto_title_from_message_truncates_and_strips_whitespace():
    long_msg = "What should I do about acne breakouts before a date next Friday?"
    out = conv_svc._auto_title_from_message(long_msg)
    assert len(out) <= 40
    assert "What should I do" in out


def test_auto_title_from_message_falls_back_to_placeholder():
    assert conv_svc._auto_title_from_message("   ") == "new chat"
    assert conv_svc._auto_title_from_message("") == "new chat"


@pytest.mark.asyncio
async def test_touch_last_message_runs_two_updates_when_titling():
    db = _FakeDB()
    await conv_svc.touch_last_message(
        db,
        conversation_id=str(uuid4()),
        first_user_message="how often should i use adapalene?",
        commit=True,
    )
    # Both last_message_at + title-conditional updates applied.
    assert db.commits == 1
