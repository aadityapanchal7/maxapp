"""
Channels API - Discord-like chat channels
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from db import get_db, get_rds_db
from middleware.auth_middleware import require_paid_user
from models.forum import ChannelCreate, MessageCreate
from services.storage_service import storage_service
from models.rds_models import Forum, ChannelMessage
from models.sqlalchemy_models import User
import re
import random

router = APIRouter(prefix="/forums", tags=["Channels"])


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
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    query = select(Forum)
    if q:
        query = query.where(
            (Forum.name.ilike(f"%{q}%")) |
            (Forum.description.ilike(f"%{q}%")) |
            (Forum.slug.ilike(f"%{q}%"))
        )
    query = query.order_by(Forum.order)
    result = await rds_db.execute(query)
    channels = result.scalars().all()

    forums = []
    for ch in channels:
        count_result = await rds_db.execute(
            select(func.count(ChannelMessage.id)).where(ChannelMessage.channel_id == ch.id)
        )
        message_count = count_result.scalar() or 0
        forums.append({
            "id": str(ch.id),
            "name": ch.name,
            "slug": ch.slug,
            "description": ch.description,
            "icon": ch.icon,
            "category": ch.category,
            "tags": ch.tags or [],
            "is_admin_only": ch.is_admin_only,
            "message_count": message_count
        })
    return {"forums": forums}


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

    user_ids = list({m.user_id for m in messages})
    users_map = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        users_map = {u.id: u for u in users_result.scalars().all()}

    payload = []
    for msg in messages:
        user = users_map.get(msg.user_id)
        payload.append({
            "id": str(msg.id),
            "channel_id": channel_id,
            "user_id": str(msg.user_id),
            "user_email": user.email.split("@")[0] if user else "Unknown",
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
    
    message = ChannelMessage(
        channel_id=channel_uuid,
        user_id=UUID(current_user["id"]),
        content=data.content,
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
    
    return {
        "message": {
            "id": str(message.id),
            "channel_id": channel_id,
            "user_id": current_user["id"],
            "user_email": user.email.split("@")[0] if user else "Unknown",
            "user_avatar_url": (user.profile or {}).get("avatar_url") if user else None,
            "content": data.content,
            "attachment_url": data.attachment_url,
            "attachment_type": data.attachment_type,
            "parent_id": data.parent_id,
            "reactions": {},
            "created_at": message.created_at,
            "is_admin": current_user.get("is_admin", False)
        }
    }


@router.post("/{channel_id}/messages/{message_id}/reactions")
async def toggle_reaction(
    channel_id: str,
    message_id: str,
    emoji: str,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """Add or remove an emoji reaction to a message"""
    user_id = current_user["id"]
    try:
        message_uuid = UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid message ID format")

    message = await rds_db.get(ChannelMessage, message_uuid)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    reactions = message.reactions or {}
    if emoji not in reactions:
        reactions[emoji] = []
    
    if user_id in reactions[emoji]:
        reactions[emoji].remove(user_id)
        if not reactions[emoji]:
            del reactions[emoji]
    else:
        reactions[emoji].append(user_id)

    message.reactions = reactions
    await rds_db.commit()
    
    return {"reactions": reactions}


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
        created_at=datetime.utcnow()
    )
    rds_db.add(channel)
    await rds_db.commit()
    await rds_db.refresh(channel)
    return {"channel_id": str(channel.id)}

