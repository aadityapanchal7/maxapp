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


async def _creator_channel_guard(
    channel: Forum, current_user: dict, db: AsyncSession
) -> tuple[bool, bool]:
    """Shared gate for EVERY read/write touching a channel: archived channels
    404 for everyone (archive = retired from the member surface; history is
    retained in the DB), and creator channels 403 non-members. Returns
    (has_access, is_owner) for creator channels, (True, False) for global."""
    if channel.is_archived:
        raise HTTPException(status_code=404, detail="Channel not found")
    if not channel.maxx_id:
        return True, False
    from services import creator_channels
    has_access, is_owner, _cr = await creator_channels.channel_access(
        channel, current_user["id"], db
    )
    if not has_access and not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Subscribe to join the community.")
    return has_access, is_owner


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
    # Bounded read (was completely uncapped): mirror the 12 MB image cap used by
    # /scans and /users uploads. Reading at most cap+1 bytes means an oversized
    # body 413s instead of being buffered whole into RAM (OOM vector).
    _MAX_UPLOAD_BYTES = 12 * 1024 * 1024
    file_data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(file_data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 12 MB).")
    user_id = current_user["id"]
    
    # Use storage service (legacy upload_image for now as it handles byte data)
    file_url = await storage_service.upload_image(file_data, user_id, "chat")
    
    if not file_url:
        raise HTTPException(status_code=500, detail="Failed to upload file")
        
    return {"url": file_url}


@router.get("")
async def list_channels(
    q: str = None,
    maxx_id: str = None,
    limit: int = 200,
    offset: int = 0,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
    db: AsyncSession = Depends(get_db),
):
    limit = min(max(limit, 1), 500)
    offset = max(offset, 0)

    if maxx_id:
        # Creator-maxx channels: members-only. Gate BEFORE listing — the list
        # itself (names/descriptions) is part of the paid surface.
        from services import creator_service, creator_channels
        creator = await creator_service.get_creator_by_maxx(maxx_id, db)
        if creator is None:
            raise HTTPException(status_code=404, detail="Not a creator max")
        is_owner = str(creator.user_id) == current_user["id"]
        if not is_owner and not current_user.get("is_admin"):
            if not await creator_service.has_creator_access(current_user["id"], creator, db):
                raise HTTPException(status_code=403, detail="Subscribe to join the community.")
        # Self-heal: creators provisioned before channels existed get defaults.
        await creator_channels.ensure_default_creator_channels(creator, rds_db)
        base = (Forum.maxx_id == maxx_id) & (Forum.is_archived.isnot(True))
    else:
        # GLOBAL list: creator channels must never leak here — they're paid,
        # per-maxx surfaces (this filter is a paywall boundary, not cosmetics).
        base = Forum.maxx_id.is_(None) & (Forum.is_archived.isnot(True))

    filters = base
    if q:
        filters = base & (
            (Forum.name.ilike(f"%{q}%")) |
            (Forum.description.ilike(f"%{q}%")) |
            (Forum.slug.ilike(f"%{q}%"))
        )
    count_q = select(func.count()).select_from(Forum).where(filters)
    count_result = await rds_db.execute(count_q)
    total = int(count_result.scalar() or 0)

    query = select(Forum).where(filters)
    query = query.order_by(Forum.order).offset(offset).limit(limit)
    result = await rds_db.execute(query)
    channels = result.scalars().all()

    creator_ids = list({ch.created_by for ch in channels if ch.created_by})
    creators_map = {}
    if creator_ids:
        creators_result = await db.execute(select(User).where(User.id.in_(creator_ids)))
        creators_map = {u.id: u for u in creators_result.scalars().all()}

    forums = []
    channel_ids = [ch.id for ch in channels]
    message_count_map: dict[str, int] = {}
    if channel_ids:
        counts_result = await rds_db.execute(
            select(ChannelMessage.channel_id, func.count(ChannelMessage.id))
            .where(ChannelMessage.channel_id.in_(channel_ids))
            .group_by(ChannelMessage.channel_id)
        )
        for cid, cnt in counts_result.all():
            # cid is UUID; stringify for stable dict keys
            message_count_map[str(cid)] = int(cnt or 0)

    for ch in channels:
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
            # Creator-channel fields (null/defaults for global channels).
            "maxx_id": ch.maxx_id,
            "who_can_post": ch.who_can_post or "members",
            "allow_replies": bool(ch.allow_replies) if ch.allow_replies is not None else True,
            "message_count": message_count_map.get(str(ch.id), 0),
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

    # Archived channels 404; creator channels are members-only (owner/admin
    # exempt) — same 403 as the list so the client's locked state is consistent.
    _, _is_owner = await _creator_channel_guard(channel, current_user, db)

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

    # Fetch the NEWEST `limit` (order DESC + limit), then restore ascending order
    # for display. The old ASC+limit returned the OLDEST messages, so recent ones
    # were unreachable and there was no way to page forward. With `before`
    # (created_at < cursor) the client pages BACKWARD through older messages.
    msg_query = msg_query.order_by(ChannelMessage.created_at.desc()).limit(limit)
    msg_result = await rds_db.execute(msg_query)
    fetched = msg_result.scalars().all()
    has_more = len(fetched) == limit  # a full page → older messages likely remain
    messages = list(reversed(fetched))  # oldest → newest for the client to render bottom-anchored

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

    # Server-driven composer state: who may start top-level threads here.
    if channel.maxx_id:
        from services.creator_channels import can_post_top_level
        _can_post = can_post_top_level(
            channel, is_owner=_is_owner, is_admin=bool(current_user.get("is_admin"))
        )
    else:
        _can_post = (not channel.is_admin_only) or bool(current_user.get("is_admin"))

    return {
        "messages": payload,
        "has_more": has_more,
        "channel_name": channel.name,
        "channel_description": channel.description,
        "channel_category": channel.category,
        "channel_tags": channel.tags or [],
        "is_admin_only": channel.is_admin_only,
        "maxx_id": channel.maxx_id,
        "who_can_post": channel.who_can_post or "members",
        "allow_replies": bool(channel.allow_replies) if channel.allow_replies is not None else True,
        "can_post": _can_post,
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

    # Archived 404 + creator-channel membership gate.
    await _creator_channel_guard(channel, current_user, db)

    # parent_id must be a real message IN THIS CHANNEL — an unvalidated parent
    # id let anyone bypass announcement-only ("reply" to a fabricated uuid) and
    # thread onto messages in other channels. Applies to ALL channels (also
    # closes the legacy is_admin_only variant of the same hole).
    if data.parent_id:
        try:
            parent_uuid = UUID(str(data.parent_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid parent message ID")
        parent = await rds_db.get(ChannelMessage, parent_uuid)
        if parent is None or parent.channel_id != channel_uuid:
            raise HTTPException(status_code=404, detail="Parent message not found")

    # Creator channels: announcement-only + reply + block gates.
    if channel.maxx_id:
        from services import creator_channels
        _has, is_owner, cr = await creator_channels.channel_access(
            channel, current_user["id"], db
        )
        if data.parent_id:
            if channel.allow_replies is False:
                raise HTTPException(status_code=403, detail="Replies are off in this channel.")
        elif not creator_channels.can_post_top_level(
            channel, is_owner=is_owner, is_admin=bool(current_user.get("is_admin"))
        ):
            name = cr.display_name if cr else "the creator"
            raise HTTPException(
                status_code=403,
                detail=f"Only {name} posts here. You can reply to their posts.",
            )
        # A creator block silences the user across the maxx (comments AND chat).
        if cr is not None and not is_owner:
            from models.sqlalchemy_models import CreatorBlock
            blocked = (await db.execute(
                select(CreatorBlock.id).where(
                    (CreatorBlock.creator_id == cr.id)
                    & (CreatorBlock.blocked_user_id == UUID(current_user["id"]))
                )
            )).first()
            if blocked:
                raise HTTPException(status_code=403, detail="You can't post in this community.")

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
    db: AsyncSession = Depends(get_db),
):
    """Add or remove an emoji reaction to a message"""
    UPVOTE = "⬆️"
    DOWNVOTE = "⬇️"
    LEGACY_UPVOTE = "â¬†ï¸"
    LEGACY_DOWNVOTE = "â¬‡ï¸"
    user_id = current_user["id"]
    try:
        channel_uuid = UUID(channel_id)
        message_uuid = UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid message ID format")

    # The path channel was previously IGNORED — any paid user could react to a
    # members-only message by uuid. Load it, bind the message to it, gate it.
    channel = (await rds_db.execute(
        select(Forum).where(Forum.id == channel_uuid)
    )).scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    await _creator_channel_guard(channel, current_user, db)

    message = await rds_db.get(ChannelMessage, message_uuid)
    if not message or message.channel_id != channel_uuid:
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
    report_channel = channel_result.scalar_one_or_none()
    if not report_channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    # Members-only channels: non-members can't see messages, so they can't
    # report them either (prevents blind report-bombing by uuid).
    await _creator_channel_guard(report_channel, current_user, db)

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


@router.delete("/{channel_id}/messages/{message_id}")
async def delete_channel_message(
    channel_id: str,
    message_id: str,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
    db: AsyncSession = Depends(get_db),
):
    """Delete a message: the AUTHOR, an admin, or — in a creator channel — the
    owning creator (their room, their moderation). Broadcasts a removal event
    so open clients drop it live."""
    try:
        channel_uuid = UUID(channel_id)
        message_uuid = UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid id format")
    channel = (await rds_db.execute(
        select(Forum).where(Forum.id == channel_uuid)
    )).scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    message = await rds_db.get(ChannelMessage, message_uuid)
    if not message or message.channel_id != channel_uuid:
        raise HTTPException(status_code=404, detail="Message not found")

    is_author = str(message.user_id) == current_user["id"]
    is_admin = bool(current_user.get("is_admin"))
    is_owning_creator = False
    if channel.maxx_id and not (is_author or is_admin):
        from services import creator_channels
        _has, is_owning_creator, _cr = await creator_channels.channel_access(
            channel, current_user["id"], db
        )
    if not (is_author or is_admin or is_owning_creator):
        raise HTTPException(status_code=403, detail="You can't delete this message.")

    await rds_db.delete(message)
    await rds_db.commit()
    await forum_channel_broker.broadcast(
        channel_id, {"type": "message_deleted", "message_id": message_id}
    )
    return {"ok": True}


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
    ws_channel = channel_result.scalar_one_or_none()
    if not ws_channel or ws_channel.is_archived:
        await websocket.close(code=1008)
        return

    # Creator channels: the WS stream is the same paid surface as the message
    # list — without this gate any paid user could stream a members-only room.
    if ws_channel.maxx_id and not user.get("is_admin"):
        from services import creator_channels
        has_access, _o, _c = await creator_channels.channel_access(
            ws_channel, user["id"], db
        )
        if not has_access:
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

