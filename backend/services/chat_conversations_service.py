"""Helpers for multi-thread chat conversations.

Keeps the chat_history writes consistent: every persisted turn has a
conversation_id, last_message_at on the parent conversation advances, and
titles auto-seed from the first user message if the caller didn't set one.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.sqlalchemy_models import ChatConversation, ChatHistory

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _auto_title_from_message(message: str) -> str:
    cleaned = re.sub(r"\s+", " ", (message or "").strip())
    if not cleaned:
        return "new chat"
    # Keep it short; mobile drawer shows ~36 chars.
    short = cleaned[:40].rstrip()
    return short or "new chat"


async def list_conversations(
    db: AsyncSession,
    *,
    user_id: str,
    include_archived: bool = False,
    limit: int = 50,
) -> list[dict]:
    user_uuid = UUID(user_id)
    stmt = (
        select(ChatConversation)
        .where(ChatConversation.user_id == user_uuid)
        .order_by(
            ChatConversation.last_message_at.desc().nullslast(),
            ChatConversation.created_at.desc(),
        )
        .limit(min(max(limit, 1), 200))
    )
    if not include_archived:
        stmt = stmt.where(ChatConversation.is_archived == False)  # noqa: E712
    rows = (await db.execute(stmt)).scalars().all()
    return [_row_to_dict(r) for r in rows]


async def get_conversation(
    db: AsyncSession, *, conversation_id: str, user_id: str
) -> Optional[ChatConversation]:
    """Fetch a conversation iff it belongs to the caller."""
    try:
        conv_uuid = UUID(conversation_id)
    except (ValueError, TypeError):
        return None
    result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_uuid,
            ChatConversation.user_id == UUID(user_id),
        )
    )
    return result.scalar_one_or_none()


async def create_conversation(
    db: AsyncSession,
    *,
    user_id: str,
    title: Optional[str] = None,
    channel: str = "app",
    commit: bool = True,
) -> ChatConversation:
    row = ChatConversation(
        user_id=UUID(user_id),
        title=(title or "").strip() or "new chat",
        channel=channel or "app",
    )
    db.add(row)
    if commit:
        await db.commit()
        await db.refresh(row)
    else:
        await db.flush()
    return row


async def rename_conversation(
    db: AsyncSession, *, conversation_id: str, user_id: str, title: str
) -> Optional[ChatConversation]:
    conv = await get_conversation(db, conversation_id=conversation_id, user_id=user_id)
    if conv is None:
        return None
    conv.title = (title or "").strip() or conv.title
    conv.updated_at = _utcnow()
    await db.commit()
    await db.refresh(conv)
    return conv


async def archive_conversation(
    db: AsyncSession, *, conversation_id: str, user_id: str
) -> bool:
    conv = await get_conversation(db, conversation_id=conversation_id, user_id=user_id)
    if conv is None:
        return False
    conv.is_archived = True
    conv.updated_at = _utcnow()
    await db.commit()
    return True


async def delete_conversation(
    db: AsyncSession, *, conversation_id: str, user_id: str
) -> bool:
    conv = await get_conversation(db, conversation_id=conversation_id, user_id=user_id)
    if conv is None:
        return False
    # chat_history.conversation_id has ON DELETE CASCADE so rows go with it.
    await db.delete(conv)
    await db.commit()
    return True


async def touch_last_message(
    db: AsyncSession,
    *,
    conversation_id: str,
    first_user_message: Optional[str] = None,
    commit: bool = True,
) -> None:
    """Bump last_message_at; optionally auto-title a brand-new conversation."""
    try:
        conv_uuid = UUID(conversation_id)
    except (ValueError, TypeError):
        return
    stmt = (
        update(ChatConversation)
        .where(ChatConversation.id == conv_uuid)
        .values(last_message_at=_utcnow())
    )
    await db.execute(stmt)

    if first_user_message:
        # Only auto-title if the current title is the default placeholder.
        auto = _auto_title_from_message(first_user_message)
        await db.execute(
            update(ChatConversation)
            .where(
                ChatConversation.id == conv_uuid,
                ChatConversation.title.in_(["new chat", "New chat", ""]),
            )
            .values(title=auto)
        )
    if commit:
        await db.commit()


async def resolve_active_conversation(
    db: AsyncSession,
    *,
    user_id: str,
    conversation_id: Optional[str],
    channel: str = "app",
) -> ChatConversation:
    """Return the conversation a message should be persisted into.

    Dispatch order:
        1. Explicit conversation_id that belongs to the user → use it.
        2. Most recent non-archived conversation for the user.
        3. Create a fresh one on the fly (and commit).
    """
    if conversation_id:
        explicit = await get_conversation(
            db, conversation_id=conversation_id, user_id=user_id
        )
        if explicit is not None and not explicit.is_archived:
            return explicit

    user_uuid = UUID(user_id)
    stmt = (
        select(ChatConversation)
        .where(
            ChatConversation.user_id == user_uuid,
            ChatConversation.is_archived == False,  # noqa: E712
            ChatConversation.channel == channel,
        )
        .order_by(
            ChatConversation.last_message_at.desc().nullslast(),
            ChatConversation.created_at.desc(),
        )
        .limit(1)
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    return await create_conversation(
        db, user_id=user_id, channel=channel, commit=True
    )


async def list_messages(
    db: AsyncSession,
    *,
    user_id: str,
    conversation_id: str,
    limit: int = 200,
    offset: int = 0,
) -> list[ChatHistory]:
    conv = await get_conversation(db, conversation_id=conversation_id, user_id=user_id)
    if conv is None:
        return []
    user_uuid = UUID(user_id)
    result = await db.execute(
        select(ChatHistory)
        .where(
            ChatHistory.user_id == user_uuid,
            ChatHistory.conversation_id == conv.id,
        )
        .order_by(ChatHistory.created_at.asc())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 500))
    )
    return list(result.scalars().all())


def _row_to_dict(conv: ChatConversation) -> dict:
    return {
        "id": str(conv.id),
        "title": conv.title,
        "channel": conv.channel,
        "is_archived": conv.is_archived,
        "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }


def row_to_dict(conv: ChatConversation) -> dict:
    return _row_to_dict(conv)
