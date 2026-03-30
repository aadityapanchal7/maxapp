"""
Channels API - Discord-like chat channels
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from db import get_db, get_rds_db
from middleware.auth_middleware import require_paid_user, get_user_by_access_token
from services.forum_ws import forum_channel_broker
from models.forum import ChannelCreate, MessageCreate, MessageReportCreate
from services.storage_service import storage_service
from models.rds_models import Forum, ChannelMessage
from models.sqlalchemy_models import User, ChannelMessageReport
import re
import random

router = APIRouter(prefix="/forums", tags=["Channels"])

_MAX_CHANNEL_MESSAGE_CHARS = 8000


def _normalize_channel_message_text(content: str | None, has_attachment: bool) -> str:
    """Basic UGC guardrails (length, empty posts) for App Review Guideline 1.2."""
    text = (content or "").strip().replace("\x00", "")
    if not has_attachment and not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(text) > _MAX_CHANNEL_MESSAGE_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Message exceeds {_MAX_CHANNEL_MESSAGE_CHARS} characters",
        )
    return text


def _blocked_user_ids_for_viewer(viewer: User | None) -> set[str]:
    if not viewer or not viewer.profile:
        return set()
    raw = viewer.profile.get("blocked_user_ids")
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if x}


@router.post("/upload")
async def upload_chat_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_paid_user)
):
    """Upload a file or image for chat attachment"""
    file_data = await file.read()
    user_id = current_user["id"]
    
    # Use storage service (legacy upload_image for now as it handles byte data)
    file_url = await storage_service.upload_image(file_data, user_id, "chat")
    
    if not file_url:
        raise HTTPException(status_code=500, detail="Failed to upload file")
        
    return {"url": file_url}


@router.get("")
async def list_channels(
    q: str = None,
    limit: int = 200,
    offset: int = 0,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
    db: AsyncSession = Depends(get_db),
):
    limit = min(max(limit, 1), 500)
    offset = max(offset, 0)

    filters = None
    if q:
        filters = (
            (Forum.name.ilike(f"%{q}%")) |
            (Forum.description.ilike(f"%{q}%")) |
            (Forum.slug.ilike(f"%{q}%"))
        )
    count_q = select(func.count()).select_from(Forum)
    if filters is not None:
        count_q = count_q.where(filters)
    count_result = await rds_db.execute(count_q)
    total = int(count_result.scalar() or 0)

    query = select(Forum)
    if filters is not None:
        query = query.where(filters)
    query = query.order_by(Forum.order).offset(offset).limit(limit)
    result = await rds_db.execute(query)
    channels = result.scalars().all()

    creator_ids = list({ch.created_by for ch in channels if ch.created_by})
    creators_map = {}
    if creator_ids:
        creators_result = await db.execute(select(User).where(User.id.in_(creator_ids)))
        creators_map = {u.id: u for u in creators_result.scalars().all()}

    forums = []
    for ch in channels:
        count_result = await rds_db.execute(
            select(func.count(ChannelMessage.id)).where(ChannelMessage.channel_id == ch.id)
        )
        message_count = count_result.scalar() or 0
        creator = creators_map.get(ch.created_by) if ch.created_by else None
        forums.append({
            "id": str(ch.id),
            "name": ch.name,
            "slug": ch.slug,
            "description": ch.description,
            "icon": ch.icon,
            "category": ch.category,
            "tags": ch.tags or [],
            "is_admin_only": ch.is_admin_only,
            "message_count": message_count,
            "created_by": str(ch.created_by) if ch.created_by else None,
            "created_by_username": creator.username if creator else None,
            "created_by_avatar_url": (creator.profile or {}).get("avatar_url") if creator else None,
            "created_at": ch.created_at,
        })
    return {"forums": forums, "total": total, "limit": limit, "offset": offset}


@router.get("/{channel_id}/messages")
async def get_messages(
    channel_id: str,
    limit: int = 50,
    before: str = None,
    query: str = None,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
    db: AsyncSession = Depends(get_db),
):
    """Get messages in a channel with optional filtering"""
    try:
        channel_uuid = UUID(channel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid channel ID format")

    channel_result = await rds_db.execute(select(Forum).where(Forum.id == channel_uuid))
    channel = channel_result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    msg_query = select(ChannelMessage).where(ChannelMessage.channel_id == channel_uuid)

    if before:
        try:
            before_uuid = UUID(before)
            before_msg = await rds_db.get(ChannelMessage, before_uuid)
            if before_msg:
                msg_query = msg_query.where(ChannelMessage.created_at < before_msg.created_at)
        except ValueError:
            pass

    if query:
        msg_query = msg_query.where(ChannelMessage.content.ilike(f"%{query}%"))

    msg_query = msg_query.order_by(ChannelMessage.created_at.asc()).limit(limit)
    msg_result = await rds_db.execute(msg_query)
    messages = msg_result.scalars().all()

    viewer_row = await db.get(User, UUID(current_user["id"]))
    blocked_ids = _blocked_user_ids_for_viewer(viewer_row)

    user_ids = list({m.user_id for m in messages})
    users_map = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        users_map = {u.id: u for u in users_result.scalars().all()}

    payload = []
    for msg in messages:
        if str(msg.user_id) in blocked_ids:
            continue
        user = users_map.get(msg.user_id)
        payload.append({
            "id": str(msg.id),
            "channel_id": channel_id,
            "user_id": str(msg.user_id),
            "user_email": user.email.split("@")[0] if user else "Unknown",
            "username": user.username if user else None,
            "user_avatar_url": (user.profile or {}).get("avatar_url") if user else None,
            "content": msg.content,
            "attachment_url": msg.attachment_url,
            "attachment_type": msg.attachment_type,
            "created_at": msg.created_at,
            "is_admin": user.is_admin if user else False,
            "parent_id": str(msg.parent_id) if msg.parent_id else None,
            "reactions": msg.reactions or {}
        })

    return {
        "messages": payload,
        "channel_name": channel.name,
        "channel_description": channel.description,
        "channel_category": channel.category,
        "channel_tags": channel.tags or [],
        "is_admin_only": channel.is_admin_only
    }


@router.post("/{channel_id}/messages")
async def send_message(
    channel_id: str,
    data: MessageCreate,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to a channel"""
    try:
        channel_uuid = UUID(channel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid channel ID format")

    channel_result = await rds_db.execute(select(Forum).where(Forum.id == channel_uuid))
    channel = channel_result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Check admin-only permission for TOP-LEVEL messages only
    if channel.is_admin_only and not current_user.get("is_admin") and not data.parent_id:
        raise HTTPException(status_code=403, detail="Only admins can post announcements. You can still comment on them!")

    has_attachment = bool(data.attachment_url and str(data.attachment_url).strip())
    normalized_content = _normalize_channel_message_text(data.content, has_attachment)

    message = ChannelMessage(
        channel_id=channel_uuid,
        user_id=UUID(current_user["id"]),
        content=normalized_content,
        attachment_url=data.attachment_url,
        attachment_type=data.attachment_type,
        parent_id=UUID(data.parent_id) if data.parent_id else None,
        reactions={},
        created_at=datetime.utcnow()
    )
    rds_db.add(message)
    await rds_db.commit()
    await rds_db.refresh(message)

    user = await db.get(User, UUID(current_user["id"]))

    out_message = {
        "id": str(message.id),
        "channel_id": channel_id,
        "user_id": current_user["id"],
        "user_email": user.email.split("@")[0] if user else "Unknown",
        "username": user.username if user else None,
        "user_avatar_url": (user.profile or {}).get("avatar_url") if user else None,
        "content": normalized_content,
        "attachment_url": data.attachment_url,
        "attachment_type": data.attachment_type,
        "parent_id": data.parent_id,
        "reactions": {},
        "created_at": message.created_at,
        "is_admin": current_user.get("is_admin", False),
    }
    await forum_channel_broker.broadcast(channel_id, {"type": "message", "message": out_message})

    return {"message": out_message}


@router.post("/{channel_id}/messages/{message_id}/reactions")
async def toggle_reaction(
    channel_id: str,
    message_id: str,
    emoji: str,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """Add or remove an emoji reaction to a message"""
    UPVOTE = "⬆️"
    DOWNVOTE = "⬇️"
    LEGACY_UPVOTE = "â¬†ï¸"
    LEGACY_DOWNVOTE = "â¬‡ï¸"
    user_id = current_user["id"]
    try:
        message_uuid = UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid message ID format")

    message = await rds_db.get(ChannelMessage, message_uuid)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    reactions = message.reactions or {}
    normalized_emoji = UPVOTE if emoji == LEGACY_UPVOTE else DOWNVOTE if emoji == LEGACY_DOWNVOTE else emoji
    emoji = normalized_emoji
    if emoji not in reactions:
        reactions[emoji] = []
    
    if user_id in reactions[emoji]:
        reactions[emoji].remove(user_id)
        if not reactions[emoji]:
            del reactions[emoji]
    else:
        reactions[emoji].append(user_id)

    if emoji in {UPVOTE, DOWNVOTE}:
        opposite = DOWNVOTE if emoji == UPVOTE else UPVOTE
        if opposite in reactions and user_id in reactions[opposite]:
            reactions[opposite].remove(user_id)
            if not reactions[opposite]:
                del reactions[opposite]

    if LEGACY_UPVOTE in reactions:
        del reactions[LEGACY_UPVOTE]
    if LEGACY_DOWNVOTE in reactions:
        del reactions[LEGACY_DOWNVOTE]

    message.reactions = reactions
    await rds_db.commit()

    await forum_channel_broker.broadcast(
        channel_id,
        {"type": "reactions", "message_id": message_id, "reactions": reactions},
    )

    return {"reactions": reactions}


@router.post("/{channel_id}/messages/{message_id}/report")
async def report_channel_message(
    channel_id: str,
    message_id: str,
    data: MessageReportCreate,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
    db: AsyncSession = Depends(get_db),
):
    """Report offensive channel content (App Store Guideline 1.2)."""
    try:
        channel_uuid = UUID(channel_id)
        message_uuid = UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    channel_result = await rds_db.execute(select(Forum).where(Forum.id == channel_uuid))
    if not channel_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Channel not found")

    message = await rds_db.get(ChannelMessage, message_uuid)
    if not message or message.channel_id != channel_uuid:
        raise HTTPException(status_code=404, detail="Message not found")

    reporter_id = current_user["id"]
    reported_id = str(message.user_id)
    if reported_id == reporter_id:
        raise HTTPException(status_code=400, detail="You cannot report your own message")

    row = ChannelMessageReport(
        channel_message_id=message_uuid,
        channel_id=channel_uuid,
        reporter_user_id=UUID(reporter_id),
        reported_user_id=message.user_id,
        reason=(data.reason or "").strip()[:2000],
        created_at=datetime.utcnow(),
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return {"status": "already_reported", "message": "You already reported this message."}

    return {"status": "ok", "message": "Thank you. Our team will review this report."}


@router.post("")
async def create_channel(
    data: ChannelCreate,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """Create channel (community allowed, official admin only)"""
    if data.is_admin_only and not current_user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="Only admins can create official forums")

    slug = data.slug
    if not slug:
        base = re.sub(r"[^a-z0-9]+", "-", data.name.strip().lower()).strip("-")
        slug = base or f"forum-{random.randint(1000,9999)}"
    existing = await rds_db.execute(select(Forum).where(Forum.slug == slug))
    if existing.scalar_one_or_none():
        slug = f"{slug}-{random.randint(1000,9999)}"

    channel = Forum(
        name=data.name,
        slug=slug,
        description=data.description,
        icon=data.icon,
        category=data.category,
        tags=data.tags or [],
        order=data.order or 0,
        is_admin_only=data.is_admin_only,
        created_by=UUID(current_user["id"]),
        created_at=datetime.utcnow()
    )
    rds_db.add(channel)
    await rds_db.commit()
    await rds_db.refresh(channel)
    return {"channel_id": str(channel.id)}


@router.websocket("/ws/channel/{channel_id}")
async def forum_channel_websocket(
    websocket: WebSocket,
    channel_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """Realtime updates for channel messages and reactions (same-process fan-out)."""
    user = await get_user_by_access_token(db, token)
    if not user:
        await websocket.close(code=1008)
        return
    if not user.get("is_admin"):
        if not user.get("is_paid"):
            await websocket.close(code=1008)
            return
        sub_end = user.get("subscription_end_date")
        if sub_end and isinstance(sub_end, datetime):
            if sub_end < datetime.utcnow():
                await websocket.close(code=1008)
                return

    try:
        channel_uuid = UUID(channel_id)
    except ValueError:
        await websocket.close(code=1008)
        return

    channel_result = await rds_db.execute(select(Forum).where(Forum.id == channel_uuid))
    if not channel_result.scalar_one_or_none():
        await websocket.close(code=1008)
        return

    await forum_channel_broker.connect(channel_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await forum_channel_broker.disconnect(channel_id, websocket)

