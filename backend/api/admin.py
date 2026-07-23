"""
Admin API - Administrative management endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone as dt_timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from db import get_db, get_rds_db, get_rds_db_optional
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
        is_scan_user=bool(getattr(user, "is_scan_user", False)),
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
    rds_db: "AsyncSession | None" = Depends(get_rds_db_optional),
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
    reports_count = (await db.execute(select(func.count(ChannelMessageReport.id)))).scalar() or 0

    # Forum/channel counts live in the separate AWS RDS. When it's unavailable
    # (a local dev backend with no RDS, or an RDS outage) get_rds_db_optional
    # yields None — degrade those counts to 0 rather than 503-ing the whole
    # dashboard, since the Supabase-backed user stats above are still useful.
    channel_count = message_count = v2_cat = v2_sub = v2_thr = v2_post = 0
    if rds_db is not None:
        channel_count = (await rds_db.execute(select(func.count(Forum.id)))).scalar() or 0
        message_count = (await rds_db.execute(select(func.count(ChannelMessage.id)))).scalar() or 0
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
    # One INSERT..SELECT instead of materializing every user id and one ORM row
    # per user — at 10k+ users the old loop held 10k pending objects in memory
    # and pushed 10k INSERTs through the pool in a single transaction.
    result = await db.execute(
        text(
            "INSERT INTO chat_history (id, user_id, role, content, channel, created_at) "
            "SELECT gen_random_uuid(), id, 'assistant', :content, 'app', NOW() FROM app_users"
        ),
        {"content": f"[BROADCAST] {data.content}"},
    )
    await db.commit()
    return {"message": f"Broadcast sent to {result.rowcount} users"}


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


# ═══════════════════════════════════════════════════════════════════════════
#  Creator platform — approvals, provisioning & moderation
# ═══════════════════════════════════════════════════════════════════════════
from models.sqlalchemy_models import (
    CreatorApplication as _CreatorApplication,
    Creator as _Creator,
    CreatorPostComment as _CreatorPostComment,
    CreatorCommentReport as _CreatorCommentReport,
    CreatorPost as _CreatorPost,
)
from services import creator_service as _creator_service


@router.get("/creator-applications")
async def admin_list_creator_applications(
    status_filter: str = Query("pending"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Pending (default) creator applications for review."""
    q = select(_CreatorApplication)
    if status_filter in ("pending", "approved", "rejected"):
        q = q.where(_CreatorApplication.status == status_filter)
    q = q.order_by(_CreatorApplication.created_at.desc()).offset(skip).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    uids = list({r.user_id for r in rows})
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()} if uids else {}
    out = []
    for r in rows:
        u = users.get(r.user_id)
        out.append({
            "id": str(r.id),
            "user_id": str(r.user_id),
            "user_email": u.email if u else None,
            "applicant_name": r.applicant_name,
            "max_name": r.max_name,
            "max_description": r.max_description,
            "instagram_handle": r.instagram_handle,
            "tiktok_handle": r.tiktok_handle,
            "social_stats": r.social_stats or {},
            "status": r.status,
            "created_at": r.created_at,
        })
    return {"applications": out, "skip": skip, "limit": limit}


class _ApproveBody(BaseModel):
    tier: str = "t1"


@router.post("/creator-applications/{application_id}/approve")
async def admin_approve_creator_application(
    application_id: str,
    body: _ApproveBody,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    rds_db: "AsyncSession | None" = Depends(get_rds_db_optional),
):
    """Approve → provision: mint the max, create the Creator, flip is_creator,
    register the catalog doc. Idempotent."""
    app_row = (await db.execute(
        select(_CreatorApplication).where(_CreatorApplication.id == UUID(application_id))
    )).scalar_one_or_none()
    if app_row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    tier = body.tier if body.tier in _creator_service.PRICE_TIERS else "t1"
    creator = await _creator_service.provision_creator_from_application(app_row, db, tier=tier)
    app_row.status = "approved"
    app_row.updated_at = datetime.utcnow()
    # Tell the applicant — approval used to be silent; they only found out by
    # reopening the app and noticing the Studio tab.
    from models.sqlalchemy_models import ScheduledNotification
    db.add(ScheduledNotification(
        user_id=app_row.user_id,
        scheduled_for=datetime.now(dt_timezone.utc),
        message=f"You're approved — \"{app_row.max_name}\" is yours. Set up your studio and publish your first lesson.",
        category_id="creator_application_decision",
        status="pending",
    ))
    await db.commit()
    # Provision the community's default channels (#announcements + #general).
    # Best-effort — RDS may be unconfigured in some environments, and the
    # member list self-heals lazily anyway.
    try:
        from services.creator_channels import ensure_default_creator_channels
        await ensure_default_creator_channels(creator, rds_db)
    except Exception:
        pass
    return {"ok": True, "creator": _creator_service.creator_private_dict(creator)}


class _RejectBody(BaseModel):
    notes: Optional[str] = None


@router.post("/creator-applications/{application_id}/reject")
async def admin_reject_creator_application(
    application_id: str,
    body: _RejectBody,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    app_row = (await db.execute(
        select(_CreatorApplication).where(_CreatorApplication.id == UUID(application_id))
    )).scalar_one_or_none()
    if app_row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    app_row.status = "rejected"
    app_row.review_notes = body.notes
    app_row.updated_at = datetime.utcnow()
    from models.sqlalchemy_models import ScheduledNotification
    db.add(ScheduledNotification(
        user_id=app_row.user_id,
        scheduled_for=datetime.now(dt_timezone.utc),
        message="Your creator application was reviewed — open the Creator tab for the decision.",
        category_id="creator_application_decision",
        status="pending",
    ))
    await db.commit()
    return {"ok": True}


@router.post("/creators/{creator_id}/art")
async def admin_set_creator_art(
    creator_id: str,
    art_url: Optional[str] = Form(None),
    art_status: Optional[str] = Form(None),  # none | pending | ready
    image: "UploadFile | None" = File(None),
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Attach marketplace card art (Higgsfield-generated, house 3D style) to a
    creator maxx. Multipart throughout: an `image` file, an `art_url` field, or
    an `art_status` transition. Manual-first pipeline; server-side auto-gen
    lives behind creator_art_autogen_enabled (stub in services/creator_art.py)."""
    creator = (await db.execute(
        select(_Creator).where(_Creator.id == UUID(creator_id))
    )).scalar_one_or_none()
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found")
    if image is not None:
        data = await image.read(12 * 1024 * 1024 + 1)  # bounded: cap+1 so oversized 413s without full RAM buffer
        if not data:
            raise HTTPException(status_code=422, detail="Empty upload")
        if len(data) > 12 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Image too large (max 12 MB)")
        from services.storage_service import storage_service
        url = await storage_service.upload_image(data, str(creator.user_id), image_type="creator")
        if not url:
            raise HTTPException(status_code=502, detail="Upload failed")
        creator.art_url = url
        creator.art_status = "ready"
    elif art_url:
        creator.art_url = art_url.strip()
        creator.art_status = "ready"
    elif art_status in ("none", "pending", "ready"):
        creator.art_status = art_status
        if art_status == "pending":
            from config import settings as _settings
            if getattr(_settings, "creator_art_autogen_enabled", False):
                from services.creator_art import request_art_generation
                await request_art_generation(creator)
    else:
        raise HTTPException(status_code=422, detail="Provide art_url, an image file, or art_status.")
    creator.updated_at = datetime.utcnow()
    await db.commit()
    return _creator_service.creator_private_dict(creator)


@router.delete("/creators/{creator_id}/art")
async def admin_clear_creator_art(
    creator_id: str,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    creator = (await db.execute(
        select(_Creator).where(_Creator.id == UUID(creator_id))
    )).scalar_one_or_none()
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found")
    creator.art_url = None
    creator.art_status = "none"
    creator.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}


@router.get("/creator-comment-reports")
async def admin_list_creator_comment_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Open creator-comment reports (UGC moderation queue, Guideline 1.2)."""
    total = (await db.execute(
        select(func.count(_CreatorCommentReport.id)).where(_CreatorCommentReport.status == "open")
    )).scalar() or 0
    rows = (await db.execute(
        select(_CreatorCommentReport).where(_CreatorCommentReport.status == "open")
        .order_by(_CreatorCommentReport.created_at.desc()).offset(skip).limit(limit)
    )).scalars().all()
    cids = list({r.comment_id for r in rows})
    comments = {c.id: c for c in (await db.execute(
        select(_CreatorPostComment).where(_CreatorPostComment.id.in_(cids))
    )).scalars().all()} if cids else {}
    uids = list({r.reporter_user_id for r in rows} | {c.user_id for c in comments.values()})
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()} if uids else {}
    out = []
    for r in rows:
        c = comments.get(r.comment_id)
        rep = users.get(r.reporter_user_id)
        author = users.get(c.user_id) if c else None
        out.append({
            "id": str(r.id),
            "created_at": r.created_at,
            "reason": r.reason or "",
            "comment_id": str(r.comment_id),
            "comment_body": (c.body[:500] if c else None),
            "comment_status": c.status if c else None,
            "author_email": author.email if author else None,
            "reporter_email": rep.email if rep else None,
        })
    return {"total": total, "reports": out, "skip": skip, "limit": limit}


@router.post("/creator-comments/{comment_id}/remove")
async def admin_remove_creator_comment(
    comment_id: str,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Uphold reports: remove the comment, resolve its reports, strike the creator's
    account is NOT struck for a user comment — only the comment is removed."""
    comment = (await db.execute(
        select(_CreatorPostComment).where(_CreatorPostComment.id == UUID(comment_id))
    )).scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    # Only decrement if it was still counted (visible) — an auto-hidden comment
    # already had its count removed, so don't double-decrement.
    was_visible = comment.status == "visible"
    comment.status = "removed"
    if was_visible:
        post = await db.get(_CreatorPost, comment.post_id)
        if post is not None:
            post.comment_count = max(0, int(post.comment_count or 0) - 1)
    await db.execute(
        _CreatorCommentReport.__table__.update()
        .where(_CreatorCommentReport.comment_id == comment.id)
        .values(status="resolved")
    )
    await db.commit()
    return {"ok": True}


@router.post("/creator-comments/{comment_id}/keep")
async def admin_keep_creator_comment(
    comment_id: str,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss reports: restore the comment to visible + clear its report count."""
    comment = (await db.execute(
        select(_CreatorPostComment).where(_CreatorPostComment.id == UUID(comment_id))
    )).scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.status == "hidden":
        comment.status = "visible"
        # Auto-hide decremented the count; restoring re-adds it.
        post = await db.get(_CreatorPost, comment.post_id)
        if post is not None:
            post.comment_count = int(post.comment_count or 0) + 1
    comment.report_count = 0
    await db.execute(
        _CreatorCommentReport.__table__.update()
        .where(_CreatorCommentReport.comment_id == comment.id)
        .values(status="dismissed")
    )
    await db.commit()
    return {"ok": True}


class _CreatorStatusBody(BaseModel):
    status: str  # live | paused | takedown


@router.post("/creators/{creator_id}/status")
async def admin_set_creator_status(
    creator_id: str,
    body: _CreatorStatusBody,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Pause / take down / re-list a creator; approve their Apple SKU review."""
    creator = (await db.execute(
        select(_Creator).where(_Creator.id == UUID(creator_id))
    )).scalar_one_or_none()
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found")
    if body.status not in ("live", "paused", "takedown", "onboarding"):
        raise HTTPException(status_code=422, detail="Bad status")
    creator.status = body.status
    if body.status == "live":
        creator.apple_review_status = "approved"
    creator.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "creator": _creator_service.creator_private_dict(creator)}
