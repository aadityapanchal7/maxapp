"""
Admin API - Administrative management endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from db import get_db, get_rds_db
from middleware.auth_middleware import get_current_admin_user
from models.user import UserResponse, OnboardingData, UserProfile
from models.sqlalchemy_models import User, ChatHistory, ChannelMessageReport, PartnerRule
from models.rds_models import (
    Forum,
    ChannelMessage,
    ForumCategory,
    ForumSubforum,
    ForumThread,
    ForumPost,
)


router = APIRouter(prefix="/admin", tags=["Admin"])


class BroadcastRequest(BaseModel):
    content: str


class DirectMessageRequest(BaseModel):
    user_id: str
    content: str


class AdminChatMessage(BaseModel):
    message: str


@router.post("/rag/reload")
async def reload_rag_cache(
    _admin: dict = Depends(get_current_admin_user),
):
    """Clear the in-memory BM25 index so the next query re-fetches from Supabase."""
    from services.rag_service import reload_indexes
    reload_indexes()
    return {"status": "ok", "message": "RAG index cache cleared — next query will rebuild from DB"}


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        created_at=user.created_at,
        is_paid=user.is_paid,
        subscription_status=user.subscription_status,
        subscription_end_date=user.subscription_end_date,
        onboarding=OnboardingData(**user.onboarding) if user.onboarding else OnboardingData(),
        profile=UserProfile(**user.profile) if user.profile else UserProfile(),
        first_scan_completed=user.first_scan_completed,
        is_admin=user.is_admin,
        phone_number=user.phone_number,
        subscription_tier=user.subscription_tier,
        last_username_change=user.last_username_change,
        has_apns_token=bool((user.apns_device_token or "").strip()),
    )


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    q: Optional[str] = None,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List all users with pagination and search (Admin only)"""
    query = select(User)
    if q:
        query = query.where(User.email.ilike(f"%{q}%"))

    query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()

    return [_user_to_response(u) for u in users]


@router.get("/stats")
async def get_stats(
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Get high-level system stats"""
    user_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    paid_count = (await db.execute(
        select(func.count(User.id)).where(User.is_paid == True)
    )).scalar() or 0
    premium_count = (
        await db.execute(
            select(func.count(User.id)).where(
                func.lower(func.coalesce(User.subscription_tier, "")) == "premium"
            )
        )
    ).scalar() or 0
    channel_count = (await rds_db.execute(select(func.count(Forum.id)))).scalar() or 0
    message_count = (await rds_db.execute(select(func.count(ChannelMessage.id)))).scalar() or 0
    reports_count = (await db.execute(select(func.count(ChannelMessageReport.id)))).scalar() or 0
    v2_cat = (await rds_db.execute(select(func.count(ForumCategory.id)))).scalar() or 0
    v2_sub = (await rds_db.execute(select(func.count(ForumSubforum.id)))).scalar() or 0
    v2_thr = (await rds_db.execute(select(func.count(ForumThread.id)))).scalar() or 0
    v2_post = (await rds_db.execute(select(func.count(ForumPost.id)))).scalar() or 0

    return {
        "total_users": user_count,
        "paid_users": paid_count,
        "premium_users": premium_count,
        "total_channels": channel_count,
        "total_messages": message_count,
        "channel_reports_total": reports_count,
        "forum_v2_categories": v2_cat,
        "forum_v2_boards": v2_sub,
        "forum_v2_threads": v2_thr,
        "forum_v2_posts": v2_post,
    }


@router.post("/broadcast")
async def broadcast_message(
    data: BroadcastRequest,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a message to ALL users in their Cannon AI chat"""
    result = await db.execute(select(User.id))
    user_ids = result.scalars().all()

    count = 0
    for user_id in user_ids:
        db.add(ChatHistory(
            user_id=user_id,
            role="assistant",
            content=f"[BROADCAST] {data.content}",
            channel="app",
            created_at=datetime.utcnow()
        ))
        count += 1

    await db.commit()
    return {"message": f"Broadcast sent to {count} users"}


@router.post("/direct")
async def direct_message(
    data: DirectMessageRequest,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a direct message to a specific user as Cannon"""
    try:
        user_uuid = UUID(data.user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.add(ChatHistory(
        user_id=user_uuid,
        role="assistant",
        content=data.content,
        channel="app",
        created_at=datetime.utcnow()
    ))
    await db.commit()

    return {"status": "Message sent"}


# ----- Admin ↔ User Chat (as Cannon) -----

@router.get("/users/{user_id}/chat")
async def get_user_chat(
    user_id: str,
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a user's Cannon chat history (admin only)"""
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == user_uuid)
        .order_by(ChatHistory.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()

    return {
        "user_id": user_id,
        "email": user.email,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
                "channel": getattr(m, "channel", None) or "app",
            }
            for m in reversed(messages)
        ]
    }


@router.post("/users/{user_id}/chat")
async def send_user_chat(
    user_id: str,
    data: AdminChatMessage,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a message to a user's Cannon chat as the assistant (admin only)"""
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_msg = ChatHistory(
        user_id=user_uuid,
        role="assistant",
        content=data.message,
        channel="app",
        created_at=datetime.utcnow()
    )
    db.add(new_msg)
    await db.commit()

    return {
        "status": "Message sent",
        "message": {
            "role": new_msg.role,
            "content": new_msg.content,
            "created_at": new_msg.created_at
        }
    }


@router.get("/channel-reports")
async def list_channel_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """
    UGC reports from community channels (App Review 1.2 — moderation queue).
    """
    total = (await db.execute(select(func.count(ChannelMessageReport.id)))).scalar() or 0
    q = (
        select(ChannelMessageReport)
        .order_by(ChannelMessageReport.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return {"total": total, "reports": [], "skip": skip, "limit": limit}

    msg_ids = list({r.channel_message_id for r in rows})
    ch_ids = list({r.channel_id for r in rows})
    uids = list({r.reporter_user_id for r in rows} | {r.reported_user_id for r in rows})

    msgs_result = await rds_db.execute(select(ChannelMessage).where(ChannelMessage.id.in_(msg_ids)))
    msgs_map = {m.id: m for m in msgs_result.scalars().all()}

    forums_result = await rds_db.execute(select(Forum).where(Forum.id.in_(ch_ids)))
    forums_map = {f.id: f for f in forums_result.scalars().all()}

    users_result = await db.execute(select(User).where(User.id.in_(uids)))
    users_map = {u.id: u for u in users_result.scalars().all()}

    reports = []
    for r in rows:
        msg = msgs_map.get(r.channel_message_id)
        forum = forums_map.get(r.channel_id)
        rep = users_map.get(r.reporter_user_id)
        tgt = users_map.get(r.reported_user_id)
        preview = (msg.content or "")[:500] if msg else ""
        reports.append(
            {
                "id": str(r.id),
                "created_at": r.created_at,
                "reason": r.reason or "",
                "channel_id": str(r.channel_id),
                "channel_name": forum.name if forum else None,
                "message_id": str(r.channel_message_id),
                "message_preview": preview or None,
                "message_has_attachment": bool(msg and msg.attachment_url),
                "reporter_user_id": str(r.reporter_user_id),
                "reporter_email": rep.email if rep else None,
                "reported_user_id": str(r.reported_user_id),
                "reported_email": tgt.email if tgt else None,
            }
        )

    return {"total": total, "reports": reports, "skip": skip, "limit": limit}


# --- Partner rules (chatbot prompt injection) ---

class PartnerRuleBody(BaseModel):
    name: str
    trigger_keywords: List[str]
    prompt_suffix: str
    active: bool = True
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


def _rule_to_dict(r: PartnerRule) -> dict:
    return {
        "id": int(r.id),
        "name": r.name,
        "trigger_keywords": list(r.trigger_keywords or []),
        "prompt_suffix": r.prompt_suffix,
        "active": bool(r.active),
        "start_date": r.start_date,
        "end_date": r.end_date,
        "created_at": r.created_at,
    }


@router.get("/partner-rules")
async def list_partner_rules(
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(PartnerRule).order_by(PartnerRule.created_at.desc()))).scalars().all()
    return [_rule_to_dict(r) for r in rows]


@router.post("/partner-rules")
async def create_partner_rule(
    body: PartnerRuleBody,
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from services.partner_rules_service import invalidate_cache

    rule = PartnerRule(
        name=body.name.strip(),
        trigger_keywords=[k.strip() for k in body.trigger_keywords if k.strip()],
        prompt_suffix=body.prompt_suffix,
        active=body.active,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    invalidate_cache()
    return _rule_to_dict(rule)


@router.patch("/partner-rules/{rule_id}")
async def update_partner_rule(
    rule_id: int,
    body: PartnerRuleBody,
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from services.partner_rules_service import invalidate_cache

    rule = await db.get(PartnerRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.name = body.name.strip()
    rule.trigger_keywords = [k.strip() for k in body.trigger_keywords if k.strip()]
    rule.prompt_suffix = body.prompt_suffix
    rule.active = body.active
    rule.start_date = body.start_date
    rule.end_date = body.end_date
    await db.commit()
    await db.refresh(rule)
    invalidate_cache()
    return _rule_to_dict(rule)


@router.delete("/partner-rules/{rule_id}")
async def delete_partner_rule(
    rule_id: int,
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from services.partner_rules_service import invalidate_cache

    rule = await db.get(PartnerRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.commit()
    invalidate_cache()
    return {"message": "deleted"}
