"""Creator platform API.

Two audiences on one router:
  • CREATOR side (`/creators/me/*`, gated by require_creator_user) — the Studio:
    profile, posts (video/text), comments management, course lessons, blocks, stats.
  • USER side (`/creators/*`) — discovery, feed, likes, comments, reports,
    per-creator subscription (Apple verify + a dev-activate for sim testing).

Media upload reuses the backend-mediated multipart pattern (there is no
direct-to-S3 presigned upload). New-post push fan-out runs in a BackgroundTask
so the composer feels instant.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.sqlalchemy import AsyncSessionLocal, get_db
from db import get_rds_db
from middleware.auth_middleware import get_current_user, require_creator_user
from middleware.rate_limit import rate_limit
from models.sqlalchemy_models import (
    Creator,
    CreatorBlock,
    CreatorCourseLesson,
    CreatorHabit,
    CreatorPost,
    CreatorPostComment,
    CreatorPostLike,
    CreatorCommentReport,
    CreatorSubscription,
    User,
)
from services import creator_service
from services.storage_service import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/creators", tags=["Creators"])

MAX_COMMENT_LEN = 1000
MAX_BODY_LEN = 2200
MAX_VIDEO_BYTES = 300 * 1024 * 1024  # 300 MB (≈3 min H.264)
MAX_POSTER_BYTES = 12 * 1024 * 1024  # poster frame is an image — mirror the 12 MB image cap
FEED_PAGE = 20


# ═══════════════════════════════════════════════════════════════════════════
#  Serialization helpers
# ═══════════════════════════════════════════════════════════════════════════
def _post_dict(p: CreatorPost, *, locked: bool = False, liked: bool = False) -> dict:
    """A feed post. When `locked` (non-subscriber teaser) the video url + full
    body are withheld — only a one-line preview + poster cross the wire."""
    body = p.body or ""
    return {
        "id": str(p.id),
        "type": p.type,
        "body": (body[:80] + "…") if (locked and len(body) > 80) else (body if not locked else body[:80]),
        "video_url": None if locked else p.video_url,
        "poster_url": p.poster_url,
        "duration_s": p.duration_s,
        "pinned": bool(p.pinned),
        "status": p.status,
        "like_count": int(p.like_count or 0),
        "comment_count": int(p.comment_count or 0),
        "view_count": int(p.view_count or 0),
        "liked": bool(liked) and not locked,
        "locked": bool(locked),
        "created_at": (p.created_at or datetime.utcnow()).isoformat(),
    }


def _comment_dict(c: CreatorPostComment, *, author: Optional[User] = None, own: bool = False) -> dict:
    name = "You" if own else (
        (author.first_name or author.username or "Member") if author else "Member"
    )
    return {
        "id": str(c.id),
        "body": c.body,
        "pinned": bool(c.pinned),
        "status": c.status,
        "report_count": int(c.report_count or 0),
        "own": own,
        "author_name": name,
        "author_id": str(c.user_id),
        "created_at": (c.created_at or datetime.utcnow()).isoformat(),
    }


async def _liked_post_ids(user_id: str, post_ids: list[UUID], db: AsyncSession) -> set[str]:
    if not post_ids:
        return set()
    rows = (await db.execute(
        select(CreatorPostLike.post_id).where(
            (CreatorPostLike.user_id == UUID(str(user_id)))
            & (CreatorPostLike.post_id.in_(post_ids))
        )
    )).scalars().all()
    return {str(r) for r in rows}


# ═══════════════════════════════════════════════════════════════════════════
#  CREATOR SIDE — the Studio  (require_creator_user)
# ═══════════════════════════════════════════════════════════════════════════
async def _require_own_creator(current_user: dict, db: AsyncSession) -> Creator:
    creator = await creator_service.get_creator_by_user(current_user["id"], db)
    if creator is None:
        raise HTTPException(status_code=404, detail="No creator profile for this account")
    return creator


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=60)
    bio: Optional[str] = Field(None, max_length=600)
    tagline: Optional[str] = Field(None, max_length=120)
    avatar_url: Optional[str] = None
    accent_color: Optional[str] = Field(None, max_length=9)
    icon: Optional[str] = Field(None, max_length=40)
    go_live: Optional[bool] = None


@router.get("/me")
async def get_my_creator(
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    return creator_service.creator_private_dict(creator)


@router.patch("/me")
async def update_my_creator(
    body: ProfileUpdate,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    if body.display_name is not None:
        creator.display_name = body.display_name.strip() or creator.display_name
    if body.bio is not None:
        creator.bio = body.bio
    if body.tagline is not None:
        creator.tagline = body.tagline
    if body.avatar_url is not None:
        creator.avatar_url = body.avatar_url
    if body.accent_color is not None:
        creator.accent_color = body.accent_color
    if body.icon is not None:
        creator.icon = body.icon
    # Go live: only allowed once the SKU cleared Apple review (or in non-prod)
    # AND the creator has posted something — Apple 3.1.1: no empty paid listing.
    if body.go_live:
        has_content = (await db.execute(
            select(func.count()).select_from(CreatorPost).where(
                (CreatorPost.creator_id == creator.id) & (CreatorPost.status == "published")
            )
        )).scalar_one() or 0
        # In production a PAID tier must have an Apple-approved SKU — a status
        # of "none" means the SKU was never submitted, and going live would
        # list an unbuyable subscription. Free tiers have no SKU to review.
        if settings.is_production and creator.price_tier != "free":
            review_ok = creator.apple_review_status == "approved"
        else:
            review_ok = True
        if not has_content:
            raise HTTPException(status_code=400, detail="Post an intro update before going live.")
        # The daily program IS the product — a live maxx must ship 2-8 habits.
        # (The habits PUT only enforces the range on later edits; without this
        # gate a creator could go live with 0 and sell an empty schedule.)
        n_habits = int((await db.execute(
            select(func.count()).select_from(CreatorHabit).where(
                (CreatorHabit.creator_id == creator.id) & (CreatorHabit.status == "active")
            )
        )).scalar_one() or 0)
        if not (2 <= n_habits <= 8):
            raise HTTPException(status_code=400, detail="Define 2-8 daily habits before going live.")
        if not review_ok:
            raise HTTPException(status_code=400, detail="Your subscription is still in Apple review.")
        creator.status = "live"
    creator.updated_at = datetime.utcnow()
    # Keep the catalog display name fresh — WITH habits, or the re-registered
    # doc would silently drop the skeleton back to the single-task fallback.
    _habits = await creator_service.load_creator_habits(creator.id, db)
    creator_service.register_creator_doc(creator, _habits)
    await db.commit()
    return creator_service.creator_private_dict(creator)


@router.post(
    "/me/posts",
    dependencies=[Depends(rate_limit(limit=30, window_s=3600, scope="creator_post"))],
)
async def create_post(
    background: BackgroundTasks,
    type: str = Form("text"),
    body: str = Form(""),
    duration_s: Optional[int] = Form(None),
    video: Optional[UploadFile] = File(None),
    poster: Optional[UploadFile] = File(None),
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a feed update. `type` = 'video' | 'text'. Video/poster are optional
    multipart files (a text post sends neither). Fires a push fan-out in the
    background so the composer returns instantly."""
    creator = await _require_own_creator(current_user, db)
    body = (body or "").strip()[:MAX_BODY_LEN]
    ptype = "video" if (type == "video" or video is not None) else "text"
    if ptype == "text" and not body:
        raise HTTPException(status_code=422, detail="A text update needs some text.")

    video_url = None
    poster_url = None
    if video is not None:
        # Bounded read: cap+1 so an oversized body 413s without first being
        # buffered whole into RAM (OOM vector).
        data = await video.read(MAX_VIDEO_BYTES + 1)
        if len(data) > MAX_VIDEO_BYTES:
            raise HTTPException(status_code=413, detail="Video is too long (max ~3 min).")
        video_url = await storage_service.upload_video(data, current_user["id"])
        if not video_url:
            raise HTTPException(status_code=502, detail="Upload failed. Try again.")
    if poster is not None:
        pdata = await poster.read(MAX_POSTER_BYTES + 1)
        if len(pdata) > MAX_POSTER_BYTES:
            raise HTTPException(status_code=413, detail="Poster image too large (max 12 MB).")
        poster_url = await storage_service.upload_image(pdata, current_user["id"], image_type="creator")

    post = CreatorPost(
        creator_id=creator.id,
        maxx_id=creator.maxx_id,
        type=ptype,
        body=body,
        video_url=video_url,
        poster_url=poster_url,
        duration_s=int(duration_s) if duration_s else None,
        status="published",
    )
    db.add(post)
    creator.post_count = int(creator.post_count or 0) + 1
    creator.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(post)

    # Fan out "new update" push to active subscribers — off the request path.
    background.add_task(
        _fanout_new_post,
        creator_id=str(creator.id),
        maxx_id=creator.maxx_id,
        creator_name=creator.display_name,
        preview=(body[:80] if body else "Posted a new video"),
    )
    return _post_dict(post, locked=False, liked=False)


class PostEdit(BaseModel):
    body: Optional[str] = Field(None, max_length=MAX_BODY_LEN)
    pinned: Optional[bool] = None


@router.patch("/me/posts/{post_id}")
async def edit_post(
    post_id: str,
    body: PostEdit,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    post = (await db.execute(
        select(CreatorPost).where(
            (CreatorPost.id == UUID(post_id)) & (CreatorPost.creator_id == creator.id)
        )
    )).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if body.body is not None:
        post.body = body.body.strip()[:MAX_BODY_LEN]
    if body.pinned is not None:
        if body.pinned:
            # only one pinned post at a time
            await db.execute(
                CreatorPost.__table__.update()
                .where((CreatorPost.creator_id == creator.id) & (CreatorPost.pinned.is_(True)))
                .values(pinned=False)
            )
        post.pinned = body.pinned
    post.updated_at = datetime.utcnow()
    await db.commit()
    return _post_dict(post)


@router.delete("/me/posts/{post_id}")
async def delete_post(
    post_id: str,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    post = (await db.execute(
        select(CreatorPost).where(
            (CreatorPost.id == UUID(post_id)) & (CreatorPost.creator_id == creator.id)
        )
    )).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status != "removed":
        post.status = "removed"
        creator.post_count = max(0, int(creator.post_count or 0) - 1)
        post.updated_at = datetime.utcnow()
        await db.commit()
    return {"ok": True}


@router.get("/me/posts")
async def my_posts(
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    rows = (await db.execute(
        select(CreatorPost).where(
            (CreatorPost.creator_id == creator.id) & (CreatorPost.status != "removed")
        ).order_by(CreatorPost.pinned.desc(), CreatorPost.created_at.desc()).limit(100)
    )).scalars().all()
    return {"posts": [_post_dict(p) for p in rows]}


@router.get("/me/posts/{post_id}/comments")
async def manage_comments(
    post_id: str,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    """All comments (incl. hidden) on the creator's own post — management view."""
    creator = await _require_own_creator(current_user, db)
    post = (await db.execute(
        select(CreatorPost).where(
            (CreatorPost.id == UUID(post_id)) & (CreatorPost.creator_id == creator.id)
        )
    )).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    rows = (await db.execute(
        select(CreatorPostComment, User).join(User, User.id == CreatorPostComment.user_id, isouter=True)
        .where((CreatorPostComment.post_id == post.id) & (CreatorPostComment.status != "removed"))
        .order_by(CreatorPostComment.pinned.desc(), CreatorPostComment.created_at.desc())
        .limit(200)
    )).all()
    return {"comments": [_comment_dict(c, author=u) for (c, u) in rows]}


@router.post("/comments/{comment_id}/pin")
async def pin_comment(
    comment_id: UUID,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    comment = (await db.execute(
        select(CreatorPostComment).where(
            (CreatorPostComment.id == comment_id) & (CreatorPostComment.creator_id == creator.id)
        )
    )).scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    await db.execute(
        CreatorPostComment.__table__.update()
        .where((CreatorPostComment.post_id == comment.post_id) & (CreatorPostComment.pinned.is_(True)))
        .values(pinned=False)
    )
    comment.pinned = True
    await db.commit()
    return {"ok": True}


@router.delete("/comments/{comment_id}/pin")
async def unpin_comment(
    comment_id: UUID,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    """Unpin was previously impossible — a pinned comment stayed pinned until
    another one displaced it."""
    creator = await _require_own_creator(current_user, db)
    comment = (await db.execute(
        select(CreatorPostComment).where(
            (CreatorPostComment.id == comment_id) & (CreatorPostComment.creator_id == creator.id)
        )
    )).scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    comment.pinned = False
    await db.commit()
    return {"ok": True}


class CommentStatusBody(BaseModel):
    status: str  # visible | hidden


@router.patch("/me/comments/{comment_id}")
async def set_comment_status(
    comment_id: UUID,
    body: CommentStatusBody,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    """Creator moderation: un-hide a falsely-reported comment (or hide one).
    Previously an auto-hidden comment stayed hidden forever with no recourse.
    Keeps the post's visible-comment counter consistent both directions."""
    if body.status not in ("visible", "hidden"):
        raise HTTPException(status_code=422, detail="status must be visible|hidden")
    creator = await _require_own_creator(current_user, db)
    comment = (await db.execute(
        select(CreatorPostComment).where(
            (CreatorPostComment.id == comment_id) & (CreatorPostComment.creator_id == creator.id)
        )
    )).scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.status == "removed":
        raise HTTPException(status_code=400, detail="Removed comments can't be restored.")
    if comment.status != body.status:
        post = await db.get(CreatorPost, comment.post_id)
        if body.status == "visible":
            comment.report_count = 0  # a creator restore clears the report state
            if post is not None:
                post.comment_count = int(post.comment_count or 0) + 1
        else:
            if post is not None:
                post.comment_count = max(0, int(post.comment_count or 0) - 1)
        comment.status = body.status
    await db.commit()
    return _comment_dict(comment)


class BlockBody(BaseModel):
    user_id: str


@router.post("/me/blocks")
async def block_user(
    body: BlockBody,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    try:
        blocked = UUID(body.user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Bad user id")
    exists = (await db.execute(
        select(CreatorBlock.id).where(
            (CreatorBlock.creator_id == creator.id) & (CreatorBlock.blocked_user_id == blocked)
        )
    )).first()
    if not exists:
        db.add(CreatorBlock(creator_id=creator.id, blocked_user_id=blocked))
        # Hide their visible comments on this creator's posts, decrementing each
        # affected post's comment_count so the badge matches the visible list.
        hidden = (await db.execute(
            select(CreatorPostComment).where(
                (CreatorPostComment.creator_id == creator.id)
                & (CreatorPostComment.user_id == blocked)
                & (CreatorPostComment.status == "visible")
            )
        )).scalars().all()
        for c in hidden:
            c.status = "hidden"
        _decr = {}
        for c in hidden:
            _decr[c.post_id] = _decr.get(c.post_id, 0) + 1
        for pid, n in _decr.items():
            post = await db.get(CreatorPost, pid)
            if post is not None:
                post.comment_count = max(0, int(post.comment_count or 0) - n)
        await db.commit()
    return {"ok": True}


@router.get("/me/blocks")
async def my_blocks(
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    rows = (await db.execute(
        select(CreatorBlock.blocked_user_id).where(CreatorBlock.creator_id == creator.id)
    )).scalars().all()
    return {"blocked_user_ids": [str(x) for x in rows]}


@router.delete("/me/blocks/{user_id}")
async def unblock_user(
    user_id: str,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    try:
        blocked = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Bad user id")
    await db.execute(
        CreatorBlock.__table__.delete().where(
            (CreatorBlock.creator_id == creator.id) & (CreatorBlock.blocked_user_id == blocked)
        )
    )
    # Restore the comments this block hid (only ones hidden by the block, i.e.
    # still 'hidden' with no open reports) and re-increment their posts' counts.
    restored = (await db.execute(
        select(CreatorPostComment).where(
            (CreatorPostComment.creator_id == creator.id)
            & (CreatorPostComment.user_id == blocked)
            & (CreatorPostComment.status == "hidden")
            & (CreatorPostComment.report_count == 0)
        )
    )).scalars().all()
    _incr = {}
    for c in restored:
        c.status = "visible"
        _incr[c.post_id] = _incr.get(c.post_id, 0) + 1
    for pid, n in _incr.items():
        post = await db.get(CreatorPost, pid)
        if post is not None:
            post.comment_count = int(post.comment_count or 0) + n
    await db.commit()
    return {"ok": True}


# ── Course lessons (course editing) ─────────────────────────────────────────
class LessonUpsert(BaseModel):
    id: Optional[str] = None
    module_number: int = Field(1, ge=1, le=99)
    sort: int = Field(0, ge=0, le=999)
    title: str = Field(..., max_length=120)
    subtitle: str = Field("", max_length=200)
    body_md: str = Field("", max_length=20000)
    video_url: Optional[str] = Field(None, max_length=1000)
    poster_url: Optional[str] = Field(None, max_length=1000)
    icon: str = Field("book-outline", max_length=40)
    status: str = "draft"  # draft | published
    is_free_preview: bool = False
    duration_minutes: Optional[int] = Field(None, ge=1, le=180)


@router.get("/me/course/lessons")
async def my_lessons(
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    rows = (await db.execute(
        select(CreatorCourseLesson).where(CreatorCourseLesson.creator_id == creator.id)
        .order_by(CreatorCourseLesson.module_number, CreatorCourseLesson.sort)
    )).scalars().all()
    return {
        "lessons": [_lesson_dict(l) for l in rows],
        "course_version": creator.course_version,
        "course_modules": creator.course_modules or {},
    }


@router.put("/me/course/lessons")
async def upsert_lesson(
    body: LessonUpsert,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    if body.status not in ("draft", "published"):
        raise HTTPException(status_code=422, detail="Bad status")
    if body.video_url and not body.video_url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="Video URL must be a full http(s) link.")
    lesson = None
    if body.id:
        lesson = (await db.execute(
            select(CreatorCourseLesson).where(
                (CreatorCourseLesson.id == _uuid_or_422(body.id)) & (CreatorCourseLesson.creator_id == creator.id)
            )
        )).scalar_one_or_none()
        if lesson is None:
            raise HTTPException(status_code=404, detail="Lesson not found")
    was_published = lesson is not None and lesson.status == "published"
    if lesson is None:
        lesson = CreatorCourseLesson(creator_id=creator.id, maxx_id=creator.maxx_id)
        db.add(lesson)
    lesson.module_number = body.module_number
    lesson.sort = body.sort
    lesson.title = body.title.strip()
    lesson.subtitle = body.subtitle
    lesson.body_md = body.body_md
    lesson.video_url = body.video_url
    lesson.poster_url = body.poster_url
    lesson.icon = body.icon or "book-outline"
    lesson.status = body.status
    lesson.is_free_preview = bool(body.is_free_preview)
    lesson.duration_minutes = body.duration_minutes
    lesson.updated_at = datetime.utcnow()
    # Any change that subscribers can SEE invalidates their cache: publishing,
    # editing a published lesson, or unpublishing one (stale-content fix).
    if body.status == "published" or was_published:
        creator.course_version = int(creator.course_version or 1) + 1
    await db.commit()
    await db.refresh(lesson)
    return _lesson_dict(lesson)


class ReorderItem(BaseModel):
    id: str
    module_number: int = Field(..., ge=1, le=99)
    sort: int = Field(..., ge=0, le=999)


class ReorderBody(BaseModel):
    items: list[ReorderItem] = Field(..., max_length=500)


@router.post("/me/course/reorder")
async def reorder_lessons(
    body: ReorderBody,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch move/reorder lessons — one transaction, ONE course_version bump
    (the per-lesson upsert would bump N times and thrash subscriber caches)."""
    creator = await _require_own_creator(current_user, db)
    if not body.items:
        return {"ok": True, "course_version": creator.course_version}
    ids = [_uuid_or_422(i.id) for i in body.items]
    rows = (await db.execute(
        select(CreatorCourseLesson).where(
            (CreatorCourseLesson.creator_id == creator.id) & (CreatorCourseLesson.id.in_(ids))
        )
    )).scalars().all()
    by_id = {str(r.id): r for r in rows}
    if len(by_id) != len({str(i) for i in ids}):
        raise HTTPException(status_code=422, detail="Unknown lesson in reorder set")
    any_published_moved = False
    for item in body.items:
        l = by_id[str(UUID(item.id))]
        if (l.module_number, l.sort) != (item.module_number, item.sort):
            if l.status == "published":
                any_published_moved = True
            l.module_number = item.module_number
            l.sort = item.sort
            l.updated_at = datetime.utcnow()
    if any_published_moved:
        creator.course_version = int(creator.course_version or 1) + 1
    await db.commit()
    return {"ok": True, "course_version": creator.course_version}


class ModuleTitleBody(BaseModel):
    module_number: int = Field(..., ge=1, le=99)
    title: str = Field("", max_length=60)


@router.patch("/me/course/modules")
async def set_module_title(
    body: ModuleTitleBody,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    """Name a module ("Foundations", "Week 2"...). Empty title clears it.
    Reassigns the whole JSON dict so SQLAlchemy flushes the change."""
    creator = await _require_own_creator(current_user, db)
    mods = dict(creator.course_modules or {})
    key = str(body.module_number)
    title = body.title.strip()
    if title:
        mods[key] = {**(mods.get(key) or {}), "title": title}
    else:
        mods.pop(key, None)
    creator.course_modules = mods
    creator.course_version = int(creator.course_version or 1) + 1
    creator.updated_at = datetime.utcnow()
    await db.commit()
    return {"course_modules": mods, "course_version": creator.course_version}


@router.delete("/me/course/lessons/{lesson_id}")
async def delete_lesson(
    lesson_id: UUID,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    await db.execute(
        CreatorCourseLesson.__table__.delete().where(
            (CreatorCourseLesson.id == lesson_id) & (CreatorCourseLesson.creator_id == creator.id)
        )
    )
    creator.course_version = int(creator.course_version or 1) + 1
    await db.commit()
    return {"ok": True}


# ── Habits (the creator's daily program → real catalog tasks) ───────────────
class HabitFrequency(BaseModel):
    type: str = "daily"                      # daily | n_per_week
    n: int = Field(1, ge=1, le=7)


class HabitIn(BaseModel):
    id: Optional[str] = None
    title: str = Field(..., max_length=60)
    description: str = Field("", max_length=300)
    duration_minutes: int = Field(10, ge=2, le=90)
    frequency: HabitFrequency = HabitFrequency()
    window: str = "any"                      # morning | evening | any
    icon: Optional[str] = Field(None, max_length=40)


class HabitsPut(BaseModel):
    habits: list[HabitIn] = Field(..., max_length=8)


def _habit_dict(h: CreatorHabit) -> dict:
    return {
        "id": str(h.id),
        "slug": h.slug,
        "title": h.title,
        "description": h.description or "",
        "duration_minutes": int(h.duration_minutes or 10),
        "frequency": {"type": h.frequency_type or "daily", "n": int(h.frequency_n or 1)},
        "window": h.window or "any",
        "icon": h.icon,
        "sort": int(h.sort or 0),
    }


@router.get("/me/habits")
async def my_habits(
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    habits = await creator_service.load_creator_habits(creator.id, db)
    return {
        "habits": [_habit_dict(h) for h in habits],
        "habits_version": int(creator.habits_version or 1),
    }


@router.put("/me/habits")
async def put_habits(
    body: HabitsPut,
    background: BackgroundTasks,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    """Whole-list save of the creator's habits (2-8 once live; 0-8 during
    onboarding so the studio isn't bricked pre-launch). Rows with `id` update
    in place — their slug (catalog identity) NEVER changes. Rows missing from
    the payload are ARCHIVED, not deleted: old schedules and per-user prefs
    still reference their catalog_ids. Saving re-registers the catalog doc and
    fans out an in-place, status-preserving regeneration to subscribers."""
    creator = await _require_own_creator(current_user, db)
    if creator.status == "live" and not (2 <= len(body.habits) <= 8):
        raise HTTPException(status_code=422, detail="A live max needs 2-8 habits.")
    for h in body.habits:
        if h.window not in ("morning", "evening", "any"):
            raise HTTPException(status_code=422, detail="window must be morning|evening|any")
        if h.frequency.type not in ("daily", "n_per_week"):
            raise HTTPException(status_code=422, detail="frequency.type must be daily|n_per_week")
        if not h.title.strip():
            raise HTTPException(status_code=422, detail="Every habit needs a title.")

    existing = (await db.execute(
        select(CreatorHabit).where(CreatorHabit.creator_id == creator.id)
    )).scalars().all()
    by_id = {str(r.id): r for r in existing}
    taken_slugs = {r.slug for r in existing}

    kept_ids: set[str] = set()
    for i, h in enumerate(body.habits):
        row = by_id.get(str(h.id)) if h.id else None
        if h.id and row is None:
            raise HTTPException(status_code=404, detail="Unknown habit id")
        if row is None:
            slug = creator_service.mint_habit_slug(h.title, taken_slugs)
            taken_slugs.add(slug)
            row = CreatorHabit(creator_id=creator.id, maxx_id=creator.maxx_id, slug=slug)
            db.add(row)
        row.title = h.title.strip()
        row.description = h.description.strip()
        row.duration_minutes = h.duration_minutes
        row.frequency_type = h.frequency.type
        row.frequency_n = h.frequency.n
        row.window = h.window
        row.icon = h.icon
        row.sort = i
        row.status = "active"
        row.updated_at = datetime.utcnow()
        if row.id is not None:
            kept_ids.add(str(row.id))
    # Archive (never delete) anything not in the payload.
    for r in existing:
        if str(r.id) not in kept_ids and r.status == "active":
            r.status = "archived"
            r.updated_at = datetime.utcnow()

    creator.habits_version = int(creator.habits_version or 1) + 1
    creator.updated_at = datetime.utcnow()
    await db.commit()

    # Re-register the catalog doc with the fresh habit set, then regenerate
    # subscribers' schedules off the request path (in-place, status-preserving).
    habits = await creator_service.load_creator_habits(creator.id, db)
    creator_service.register_creator_doc(creator, habits)
    background.add_task(_fanout_habit_regen, creator_id=str(creator.id), maxx_id=creator.maxx_id)

    return {
        "habits": [_habit_dict(h) for h in habits],
        "habits_version": int(creator.habits_version or 1),
    }


def _uuid_or_422(raw: str) -> UUID:
    """Malformed client UUIDs are a 422, never an unhandled 500."""
    try:
        return UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=422, detail="Bad id")


def _lesson_dict(l: CreatorCourseLesson) -> dict:
    return {
        "id": str(l.id),
        "module_number": l.module_number,
        "sort": l.sort,
        "title": l.title,
        "subtitle": l.subtitle or "",
        "body_md": l.body_md or "",
        "video_url": l.video_url,
        "poster_url": l.poster_url,
        "icon": l.icon or "book-outline",
        "status": l.status,
        "is_free_preview": bool(getattr(l, "is_free_preview", False)),
        "duration_minutes": l.duration_minutes,
        "updated_at": (l.updated_at or datetime.utcnow()).isoformat(),
    }


# ── Community channels (studio CRUD; rows live in RDS, gated by creator_id) ──
class ChannelCreate(BaseModel):
    name: str = Field(..., max_length=40)
    description: str = Field("", max_length=200)
    who_can_post: str = "members"        # creator | members
    allow_replies: bool = True
    icon: Optional[str] = Field(None, max_length=40)


class ChannelPatch(BaseModel):
    name: Optional[str] = Field(None, max_length=40)
    description: Optional[str] = Field(None, max_length=200)
    who_can_post: Optional[str] = None
    allow_replies: Optional[bool] = None
    icon: Optional[str] = Field(None, max_length=40)


class ChannelReorder(BaseModel):
    order: list[str] = Field(..., max_length=16)


async def _own_channel(channel_id: str, creator, rds_db: AsyncSession):
    from models.rds_models import Forum
    ch = (await rds_db.execute(
        select(Forum).where(Forum.id == _uuid_or_422(channel_id))
    )).scalar_one_or_none()
    # Ownership check via creator_id — never trust a channel id alone.
    if ch is None or str(ch.creator_id or "") != str(creator.id):
        raise HTTPException(status_code=404, detail="Channel not found")
    return ch


@router.get("/me/channels")
async def my_channels(
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    from models.rds_models import Forum, ChannelMessage
    from services import creator_channels
    creator = await _require_own_creator(current_user, db)
    await creator_channels.ensure_default_creator_channels(creator, rds_db)
    rows = (await rds_db.execute(
        select(Forum).where(
            (Forum.creator_id == creator.id) & (Forum.is_archived.isnot(True))
        ).order_by(Forum.order)
    )).scalars().all()
    counts: dict[str, int] = {}
    if rows:
        crows = (await rds_db.execute(
            select(ChannelMessage.channel_id, func.count())
            .where(ChannelMessage.channel_id.in_([r.id for r in rows]))
            .group_by(ChannelMessage.channel_id)
        )).all()
        counts = {str(k): int(n) for k, n in crows}
    return {"channels": [
        creator_channels.channel_public_dict(r, counts.get(str(r.id), 0)) for r in rows
    ]}


@router.post("/me/channels")
async def create_channel(
    body: ChannelCreate,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    from models.rds_models import Forum
    from services import creator_channels
    creator = await _require_own_creator(current_user, db)
    if body.who_can_post not in ("creator", "members"):
        raise HTTPException(status_code=422, detail="who_can_post must be creator|members")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Channel needs a name.")
    n_live = int((await rds_db.execute(
        select(func.count()).select_from(Forum).where(
            (Forum.creator_id == creator.id) & (Forum.is_archived.isnot(True))
        )
    )).scalar_one() or 0)
    if n_live >= creator_channels.MAX_CHANNELS_PER_MAXX:
        raise HTTPException(status_code=422, detail=f"Max {creator_channels.MAX_CHANNELS_PER_MAXX} channels.")
    ch = Forum(
        name=name,
        slug=creator_channels.channel_slug(creator.maxx_id, name),
        description=body.description.strip(),
        icon=body.icon or ("megaphone-outline" if body.who_can_post == "creator" else "chatbubbles-outline"),
        category="creator",
        tags=[],
        order=n_live,
        is_admin_only=False,
        maxx_id=creator.maxx_id,
        creator_id=creator.id,
        who_can_post=body.who_can_post,
        allow_replies=body.allow_replies,
        is_archived=False,
    )
    rds_db.add(ch)
    try:
        await rds_db.commit()
    except IntegrityError:
        # Per-maxx name uniqueness (partial index) — or, on an RDS whose legacy
        # global constraints survived the DROP, a cross-maxx collision.
        await rds_db.rollback()
        raise HTTPException(status_code=409, detail="You already have a channel with that name.")
    await rds_db.refresh(ch)
    from services.creator_channels import channel_public_dict
    return channel_public_dict(ch)


@router.patch("/me/channels/{channel_id}")
async def update_channel(
    channel_id: str,
    body: ChannelPatch,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    from services.creator_channels import channel_public_dict
    creator = await _require_own_creator(current_user, db)
    ch = await _own_channel(channel_id, creator, rds_db)
    if body.who_can_post is not None:
        if body.who_can_post not in ("creator", "members"):
            raise HTTPException(status_code=422, detail="who_can_post must be creator|members")
        ch.who_can_post = body.who_can_post
    if body.name is not None and body.name.strip():
        ch.name = body.name.strip()
    if body.description is not None:
        ch.description = body.description.strip()
    if body.allow_replies is not None:
        ch.allow_replies = body.allow_replies
    if body.icon is not None:
        ch.icon = body.icon
    try:
        await rds_db.commit()
    except IntegrityError:
        await rds_db.rollback()
        raise HTTPException(status_code=409, detail="You already have a channel with that name.")
    return channel_public_dict(ch)


@router.post("/me/channels/reorder")
async def reorder_channels(
    body: ChannelReorder,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    from models.rds_models import Forum
    creator = await _require_own_creator(current_user, db)
    rows = (await rds_db.execute(
        select(Forum).where(Forum.creator_id == creator.id)
    )).scalars().all()
    by_id = {str(r.id): r for r in rows}
    for i, cid in enumerate(body.order):
        r = by_id.get(cid)
        if r is not None:
            r.order = i
    await rds_db.commit()
    return {"ok": True}


@router.delete("/me/channels/{channel_id}")
async def archive_channel(
    channel_id: str,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """ARCHIVE (never hard-delete — the Forum FK cascades would destroy message
    history; retention is deliberate). Refuses to archive the last channel."""
    from models.rds_models import Forum
    creator = await _require_own_creator(current_user, db)
    ch = await _own_channel(channel_id, creator, rds_db)
    n_live = int((await rds_db.execute(
        select(func.count()).select_from(Forum).where(
            (Forum.creator_id == creator.id) & (Forum.is_archived.isnot(True))
        )
    )).scalar_one() or 0)
    if n_live <= 1 and not ch.is_archived:
        raise HTTPException(status_code=422, detail="Keep at least one channel.")
    ch.is_archived = True
    await rds_db.commit()
    return {"ok": True}


# ── Go-live checklist ────────────────────────────────────────────────────────
@router.get("/me/checklist")
async def my_checklist(
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    """Server-computed studio checklist. Shares its rules with the PATCH /me
    go_live gate via creator_service.compute_checklist, so they can't drift."""
    creator = await _require_own_creator(current_user, db)
    published_posts = int((await db.execute(
        select(func.count()).select_from(CreatorPost).where(
            (CreatorPost.creator_id == creator.id) & (CreatorPost.status == "published")
        )
    )).scalar_one() or 0)
    published_lessons = int((await db.execute(
        select(func.count()).select_from(CreatorCourseLesson).where(
            (CreatorCourseLesson.creator_id == creator.id) & (CreatorCourseLesson.status == "published")
        )
    )).scalar_one() or 0)
    active_habits = int((await db.execute(
        select(func.count()).select_from(CreatorHabit).where(
            (CreatorHabit.creator_id == creator.id) & (CreatorHabit.status == "active")
        )
    )).scalar_one() or 0)
    return creator_service.compute_checklist(
        creator,
        published_posts=published_posts,
        published_lessons=published_lessons,
        is_production=settings.is_production,
        active_habits=active_habits,
    )


# ── AI course assist ─────────────────────────────────────────────────────────
class CourseAssistBody(BaseModel):
    mode: str  # outline | lesson
    topic: str = Field("", max_length=200)
    notes: str = Field("", max_length=1000)
    module_count: int = Field(4, ge=2, le=6)
    lesson_title: str = Field("", max_length=120)


_ASSIST_SYSTEM = (
    "You are a course architect for a self-improvement app. Creators own a 'max' "
    "(a focused program: skincare, jawline, chess, coloring...). Write practical, "
    "step-by-step, no-fluff course material in the creator's voice: confident, "
    "direct, second person. No medical claims, no guarantees. Reply with RAW JSON "
    "only — no code fences, no commentary."
)


@router.post(
    "/me/course/assist",
    dependencies=[Depends(rate_limit(limit=20, window_s=3600, scope="creator_assist"))],
)
async def course_assist(
    body: CourseAssistBody,
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    """Draft a course outline or one lesson body with the LLM. The result is a
    DRAFT for the editor — nothing is persisted here; the creator reviews and
    saves through the normal upsert path."""
    creator = await _require_own_creator(current_user, db)
    from services.claude_service import claude_service

    topic = body.topic.strip() or (creator.tagline or "").strip() or creator.display_name
    if body.mode == "outline":
        prompt = (
            f"Design a course outline for a '{creator.maxx_id}' max about: {topic}.\n"
            f"{('Creator notes: ' + body.notes.strip()) if body.notes.strip() else ''}\n"
            f"Exactly {body.module_count} modules, 3-5 lessons each. Lesson subtitles "
            "are one concrete promise (what the subscriber can DO after it).\n"
            'JSON shape: {"modules":[{"title":"...","lessons":[{"title":"...","subtitle":"..."}]}]}'
        )
        raw = await claude_service.simple_completion(prompt, system_prompt=_ASSIST_SYSTEM, max_tokens=1600)
        if not raw.strip():
            raise HTTPException(status_code=503, detail="AI assist isn't available on this build.")
        parsed = creator_service.parse_outline_json(raw)
        if parsed is None:
            raise HTTPException(status_code=502, detail="Draft came back malformed — try again.")
        return parsed
    if body.mode == "lesson":
        title = body.lesson_title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="lesson_title is required for mode=lesson")
        prompt = (
            f"Write one course lesson for a '{creator.maxx_id}' max about: {topic}.\n"
            f"Lesson title: {title}\n"
            f"{('Creator notes: ' + body.notes.strip()) if body.notes.strip() else ''}\n"
            "300-600 words of markdown: a 1-2 sentence hook, then ## sections with "
            "concrete steps, exact numbers/durations where honest, and a closing "
            "'Do this today' line. "
            'JSON shape: {"subtitle":"one-line promise","body_md":"the markdown"}'
        )
        raw = await claude_service.simple_completion(prompt, system_prompt=_ASSIST_SYSTEM, max_tokens=2000)
        if not raw.strip():
            raise HTTPException(status_code=503, detail="AI assist isn't available on this build.")
        parsed = creator_service.parse_lesson_draft_json(raw)
        if parsed is None:
            raise HTTPException(status_code=502, detail="Draft came back malformed — try again.")
        return parsed
    raise HTTPException(status_code=422, detail="mode must be 'outline' or 'lesson'")


# ── Avatar upload ────────────────────────────────────────────────────────────
MAX_AVATAR_BYTES = 8 * 1024 * 1024

@router.post("/me/avatar")
async def upload_avatar(
    image: UploadFile = File(...),
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    data = await image.read(MAX_AVATAR_BYTES + 1)
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 8 MB).")
    if not data:
        raise HTTPException(status_code=422, detail="Empty upload.")
    url = await storage_service.upload_image(data, current_user["id"], image_type="creator")
    if not url:
        raise HTTPException(status_code=502, detail="Upload failed. Try again.")
    creator.avatar_url = url
    creator.updated_at = datetime.utcnow()
    await db.commit()
    return creator_service.creator_private_dict(creator)


@router.get("/me/stats")
async def my_stats(
    current_user: dict = Depends(require_creator_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await _require_own_creator(current_user, db)
    # Compute from the source-of-truth tables so the numbers never drift from a
    # stale cached counter (subs excludes time-lapsed; posts counts live rows).
    subs = await creator_service.live_subscriber_count(creator, db)
    post_count = int((await db.execute(
        select(func.count()).select_from(CreatorPost).where(
            (CreatorPost.creator_id == creator.id) & (CreatorPost.status == "published")
        )
    )).scalar_one() or 0)
    # Gross monthly, then Apple's ~30% cut → creator's estimated take.
    gross_cents = subs * int(creator.price_cents or 0)
    creator_cents = int(round(gross_cents * 0.70))
    agg = (await db.execute(
        select(
            func.coalesce(func.sum(CreatorPost.like_count), 0),
            func.coalesce(func.sum(CreatorPost.comment_count), 0),
            func.coalesce(func.sum(CreatorPost.view_count), 0),
        ).where((CreatorPost.creator_id == creator.id) & (CreatorPost.status == "published"))
    )).one()
    # Lesson counts for the studio course chip.
    lesson_rows = (await db.execute(
        select(CreatorCourseLesson.status, func.count())
        .where(CreatorCourseLesson.creator_id == creator.id)
        .group_by(CreatorCourseLesson.status)
    )).all()
    lesson_counts = {status_: int(n) for status_, n in lesson_rows}
    # New-subscriber series, last 30 days (zero-filled, oldest → newest) — the
    # studio sparkline. created_at of the sub row ≈ first activation date.
    from datetime import timedelta
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=29)
    daily_rows = (await db.execute(
        select(func.date(CreatorSubscription.created_at), func.count())
        .where(
            (CreatorSubscription.creator_id == creator.id)
            & (CreatorSubscription.created_at >= datetime(since.year, since.month, since.day, tzinfo=timezone.utc))
        )
        .group_by(func.date(CreatorSubscription.created_at))
    )).all()
    by_day = {str(d): int(n) for d, n in daily_rows}
    series = []
    for i in range(30):
        day = since + timedelta(days=i)
        series.append({"date": day.isoformat(), "count": by_day.get(day.isoformat(), 0)})
    return {
        "subscriber_count": subs,
        "price_cents": int(creator.price_cents or 0),
        "gross_monthly_cents": gross_cents,
        "est_monthly_cents": creator_cents,
        "total_likes": int(agg[0]),
        "total_comments": int(agg[1]),
        "total_views": int(agg[2]),
        "post_count": post_count,
        "published_lessons": lesson_counts.get("published", 0),
        "draft_lessons": lesson_counts.get("draft", 0),
        "course_version": int(creator.course_version or 1),
        "subscribers_30d": series,
        "apple_review_status": creator.apple_review_status,
        "status": creator.status,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  USER SIDE — discovery, feed, engagement, subscription
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/browse")
async def browse_creators(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(Creator).where(Creator.status == "live")
        .order_by(Creator.subscriber_count.desc()).limit(50)
    )).scalars().all()
    # which of these the user already subscribes to
    my = (await db.execute(
        select(CreatorSubscription.creator_id).where(
            (CreatorSubscription.user_id == UUID(current_user["id"]))
            & creator_service.active_sub_clause()
        )
    )).scalars().all()
    mine = {str(x) for x in my}
    # Published-lesson counts for all listed creators in ONE grouped query —
    # the browse cards sell "N-lesson course", not just a name.
    lesson_counts: dict[str, int] = {}
    if rows:
        lrows = (await db.execute(
            select(CreatorCourseLesson.creator_id, func.count())
            .where(
                (CreatorCourseLesson.creator_id.in_([c.id for c in rows]))
                & (CreatorCourseLesson.status == "published")
            )
            .group_by(CreatorCourseLesson.creator_id)
        )).all()
        lesson_counts = {str(cid): int(n) for cid, n in lrows}
    out = []
    for c in rows:
        d = creator_service.creator_public_dict(c)
        d["subscribed"] = str(c.id) in mine
        d["published_lesson_count"] = lesson_counts.get(str(c.id), 0)
        out.append(d)
    return {"creators": out}


@router.get("/by-maxx/{maxx_id}")
async def get_creator_by_maxx(
    maxx_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await creator_service.get_creator_by_maxx(maxx_id, db)
    if creator is None:
        raise HTTPException(status_code=404, detail="Not a creator max")
    d = creator_service.creator_public_dict(creator)
    d["subscribed"] = (await creator_service.active_subscription(current_user["id"], str(creator.id), db)) is not None
    d["is_owner"] = str(creator.user_id) == current_user["id"]
    # Course size for the paywall pitch ("12 lessons · 2 free previews").
    lrows = (await db.execute(
        select(CreatorCourseLesson.is_free_preview, func.count())
        .where(
            (CreatorCourseLesson.creator_id == creator.id)
            & (CreatorCourseLesson.status == "published")
        )
        .group_by(CreatorCourseLesson.is_free_preview)
    )).all()
    counts = {bool(k): int(n) for k, n in lrows}
    d["published_lesson_count"] = sum(counts.values())
    d["free_preview_count"] = counts.get(True, 0)
    return d


@router.get("/by-maxx/{maxx_id}/course")
async def get_creator_course(
    maxx_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The subscriber-facing course: published lessons grouped into modules.
    THE missing read-path — publish used to be a dead end. Non-subscribers get
    the full outline (titles/subtitles) with content withheld server-side,
    except free-preview lessons which are readable as the paywall's proof."""
    creator = await creator_service.get_creator_by_maxx(maxx_id, db)
    if creator is None:
        raise HTTPException(status_code=404, detail="Not a creator max")
    is_owner = str(creator.user_id) == current_user["id"]
    if creator.status == "takedown" and not (is_owner or current_user.get("is_admin")):
        raise HTTPException(status_code=404, detail="This max is unavailable.")
    access = await creator_service.has_creator_access(current_user["id"], creator, db)
    rows = (await db.execute(
        select(CreatorCourseLesson).where(
            (CreatorCourseLesson.creator_id == creator.id)
            & (CreatorCourseLesson.status == "published")
        ).order_by(CreatorCourseLesson.module_number, CreatorCourseLesson.sort)
    )).scalars().all()
    modules = creator_service.group_lessons_into_modules(
        list(rows), creator.course_modules, has_access=access
    )
    creator_dict = creator_service.creator_public_dict(creator)
    creator_dict["is_owner"] = is_owner
    return {
        "creator": creator_dict,
        "modules": modules,
        "course_version": int(creator.course_version or 1),
        "has_access": access,
        "lesson_count": len(rows),
        "free_preview_count": sum(1 for r in rows if r.is_free_preview),
    }


@router.get("/by-maxx/{maxx_id}/posts")
async def creator_feed(
    maxx_id: str,
    limit: int = Query(FEED_PAGE, ge=1, le=50),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    creator = await creator_service.get_creator_by_maxx(maxx_id, db)
    if creator is None:
        raise HTTPException(status_code=404, detail="Not a creator max")
    is_owner = str(creator.user_id) == current_user["id"]
    # A taken-down creator's paid content is gone for everyone but the owner/admin.
    if creator.status == "takedown" and not (is_owner or current_user.get("is_admin")):
        raise HTTPException(status_code=404, detail="This max is unavailable.")
    access = await creator_service.has_creator_access(current_user["id"], creator, db)
    q = (
        select(CreatorPost).where(
            (CreatorPost.creator_id == creator.id) & (CreatorPost.status == "published")
        )
        .order_by(CreatorPost.pinned.desc(), CreatorPost.created_at.desc())
        .limit(limit).offset(offset)
    )
    rows = (await db.execute(q)).scalars().all()
    total = (await db.execute(
        select(func.count()).select_from(CreatorPost).where(
            (CreatorPost.creator_id == creator.id) & (CreatorPost.status == "published")
        )
    )).scalar_one() or 0
    liked = await _liked_post_ids(current_user["id"], [p.id for p in rows], db) if access else set()
    posts = [_post_dict(p, locked=not access, liked=str(p.id) in liked) for p in rows]
    creator_dict = creator_service.creator_public_dict(creator)
    creator_dict["is_owner"] = is_owner  # client shows "Open Studio" vs subscribe
    return {"posts": posts, "total": int(total), "has_access": access, "creator": creator_dict}


@router.post(
    "/posts/{post_id}/like",
    dependencies=[Depends(rate_limit(limit=120, window_s=60, scope="creator_like"))],
)
async def like_post(
    post_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await _accessible_post(post_id, current_user["id"], db)
    exists = (await db.execute(
        select(CreatorPostLike.id).where(
            (CreatorPostLike.post_id == post.id) & (CreatorPostLike.user_id == UUID(current_user["id"]))
        )
    )).first()
    if not exists:
        db.add(CreatorPostLike(post_id=post.id, user_id=UUID(current_user["id"])))
        post.like_count = int(post.like_count or 0) + 1
        try:
            await db.commit()
        except IntegrityError:
            # Concurrent double-tap raced the uniqueness constraint — the like
            # already landed; return idempotently instead of 500ing.
            await db.rollback()
    return {"ok": True, "like_count": int(post.like_count or 0)}


@router.post(
    "/posts/{post_id}/view",
    dependencies=[Depends(rate_limit(limit=240, window_s=60, scope="creator_view"))],
)
async def record_post_view(
    post_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Count a feed impression. Before this, view_count existed in the schema
    and the stats sum — but nothing ever incremented it, so every creator
    dashboard showed 0 views forever. Client debounces (once per post per
    session); this is an approximate engagement signal, not analytics."""
    post = await _accessible_post(post_id, current_user["id"], db)
    post.view_count = int(post.view_count or 0) + 1
    await db.commit()
    return {"ok": True}


@router.delete("/posts/{post_id}/like")
async def unlike_post(
    post_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await _accessible_post(post_id, current_user["id"], db)
    res = await db.execute(
        CreatorPostLike.__table__.delete().where(
            (CreatorPostLike.post_id == post.id) & (CreatorPostLike.user_id == UUID(current_user["id"]))
        )
    )
    if res.rowcount:
        post.like_count = max(0, int(post.like_count or 0) - 1)
        await db.commit()
    return {"ok": True, "like_count": int(post.like_count or 0)}


@router.get("/posts/{post_id}/comments")
async def list_comments(
    post_id: str,
    limit: int = Query(40, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await _accessible_post(post_id, current_user["id"], db)
    rows = (await db.execute(
        select(CreatorPostComment, User).join(User, User.id == CreatorPostComment.user_id, isouter=True)
        .where((CreatorPostComment.post_id == post.id) & (CreatorPostComment.status == "visible"))
        .order_by(CreatorPostComment.pinned.desc(), CreatorPostComment.created_at.desc())
        .limit(limit).offset(offset)
    )).all()
    total = (await db.execute(
        select(func.count()).select_from(CreatorPostComment).where(
            (CreatorPostComment.post_id == post.id) & (CreatorPostComment.status == "visible")
        )
    )).scalar_one() or 0
    out = [_comment_dict(c, author=u, own=str(c.user_id) == current_user["id"]) for (c, u) in rows]
    return {"comments": out, "total": int(total)}


class CommentBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=MAX_COMMENT_LEN)


@router.post(
    "/posts/{post_id}/comments",
    dependencies=[Depends(rate_limit(limit=20, window_s=300, scope="creator_comment"))],
)
async def add_comment(
    post_id: str,
    body: CommentBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await _accessible_post(post_id, current_user["id"], db, require_sub=True)
    # blocked users can't comment on this creator's posts
    blocked = (await db.execute(
        select(CreatorBlock.id).where(
            (CreatorBlock.creator_id == post.creator_id)
            & (CreatorBlock.blocked_user_id == UUID(current_user["id"]))
        )
    )).first()
    if blocked:
        raise HTTPException(status_code=403, detail="You can't comment here.")
    text = body.body.strip()[:MAX_COMMENT_LEN]
    if not text:
        raise HTTPException(status_code=422, detail="Empty comment")
    comment = CreatorPostComment(
        post_id=post.id, creator_id=post.creator_id, user_id=UUID(current_user["id"]), body=text,
    )
    db.add(comment)
    post.comment_count = int(post.comment_count or 0) + 1
    await db.commit()
    await db.refresh(comment)
    return _comment_dict(comment, own=True)


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a comment: the comment's author, the post's creator, or an admin."""
    comment = (await db.execute(
        select(CreatorPostComment).where(CreatorPostComment.id == UUID(comment_id))
    )).scalar_one_or_none()
    if comment is None or comment.status == "removed":
        return {"ok": True}
    creator = await creator_service.get_creator_by_id(str(comment.creator_id), db)
    is_owner_creator = creator is not None and str(creator.user_id) == current_user["id"]
    is_author = str(comment.user_id) == current_user["id"]
    if not (is_author or is_owner_creator or current_user.get("is_admin")):
        raise HTTPException(status_code=403, detail="Not allowed")
    was_visible = comment.status == "visible"
    comment.status = "removed"
    # Only decrement if it was still counted (visible) — a hidden/auto-hidden
    # comment already had its count removed, so don't double-decrement.
    if was_visible:
        post = await db.get(CreatorPost, comment.post_id)
        if post is not None:
            post.comment_count = max(0, int(post.comment_count or 0) - 1)
    # Clear any open reports so a self/creator-deleted comment leaves the admin
    # moderation queue.
    await db.execute(
        CreatorCommentReport.__table__.update()
        .where((CreatorCommentReport.comment_id == comment.id) & (CreatorCommentReport.status == "open"))
        .values(status="resolved")
    )
    await db.commit()
    return {"ok": True}


class ReportBody(BaseModel):
    reason: str = Field("", max_length=2000)


@router.post(
    "/comments/{comment_id}/report",
    dependencies=[Depends(rate_limit(limit=30, window_s=3600, scope="creator_report"))],
)
async def report_comment(
    comment_id: str,
    body: ReportBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    comment = (await db.execute(
        select(CreatorPostComment).where(CreatorPostComment.id == UUID(comment_id))
    )).scalar_one_or_none()
    if comment is None or comment.status == "removed":
        raise HTTPException(status_code=404, detail="Comment not found")
    if str(comment.user_id) == current_user["id"]:
        raise HTTPException(status_code=400, detail="You can't report your own comment.")
    exists = (await db.execute(
        select(CreatorCommentReport.id).where(
            (CreatorCommentReport.comment_id == comment.id)
            & (CreatorCommentReport.reporter_user_id == UUID(current_user["id"]))
        )
    )).first()
    if exists:
        return {"ok": True, "message": "Thanks — we're already reviewing this."}
    db.add(CreatorCommentReport(
        comment_id=comment.id, creator_id=comment.creator_id,
        reporter_user_id=UUID(current_user["id"]), reason=body.reason or "",
    ))
    comment.report_count = int(comment.report_count or 0) + 1
    await creator_service.maybe_auto_hide_comment(comment, db)
    await db.commit()
    # Guideline 1.2 acknowledgement copy.
    return {"ok": True, "message": "Thank you. Our team will review this report."}


@router.get("/subscriptions")
async def my_subscriptions(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(CreatorSubscription, Creator).join(Creator, Creator.id == CreatorSubscription.creator_id)
        .where(CreatorSubscription.user_id == UUID(current_user["id"]))
        .order_by(CreatorSubscription.updated_at.desc())
    )).all()
    out = []
    for (sub, creator) in rows:
        d = creator_service.creator_public_dict(creator)
        d["subscription"] = {
            "status": sub.status,
            "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
            "auto_renew": bool(sub.auto_renew),
            "billing_provider": sub.billing_provider,
        }
        out.append(d)
    return {"subscriptions": out}


# ── Subscription activation (Apple verify + dev bypass) ─────────────────────
class CreatorVerifyBody(BaseModel):
    transaction_id: str
    product_id: Optional[str] = None


@router.post(
    "/subscribe/{maxx_id}/verify",
    dependencies=[Depends(rate_limit(limit=20, window_s=300, scope="creator_verify"))],
)
async def verify_creator_subscription(
    maxx_id: str,
    body: CreatorVerifyBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify an Apple auto-renewable purchase of a creator sub and activate it.
    Requires the Chad base sub underneath (creator subs are add-ons)."""
    if not current_user.get("is_paid", False):
        raise HTTPException(status_code=402, detail="A Chad subscription is required first.")
    creator = await creator_service.get_creator_by_maxx(maxx_id, db)
    if creator is None:
        raise HTTPException(status_code=404, detail="Not a creator max")

    from services.apple_iap_service import (
        apple_iap_configured, fetch_transaction_claims, validate_claims_for_user,
        account_token_matches, subscription_active_from_claims, expires_datetime_from_claims,
    )
    if apple_iap_configured():
        try:
            claims = await fetch_transaction_claims(body.transaction_id)
            validate_claims_for_user(claims, current_user["id"])
            # Keep the creator path STRICT on appAccountToken. The main
            # subscription path now tolerates a mismatch for an unclaimed sub
            # (Apple-ID-owned entitlement outliving the buying app account), but
            # that leniency is deliberately NOT extended here — this check is
            # part of what stops one user replaying another's creator receipt.
            if account_token_matches(claims, current_user["id"]) is False:
                raise ValueError("account_token_mismatch")
        except Exception as e:
            logger.warning("creator apple verify failed: %s", e)
            raise HTTPException(status_code=401, detail="Could not verify purchase.")
        # CRITICAL: bind the ENTITLEMENT SCOPE to the verified receipt, not the URL.
        # Without this, a user who bought creator A's SKU could replay that
        # transaction against creator B's verify endpoint and unlock B for free
        # (validate_claims_for_user only checks bundleId + appAccountToken). The
        # purchased productId MUST match the creator being subscribed to — the
        # same binding the ASN webhook does (resolve creator BY product id).
        claim_product = str(claims.get("productId") or "")
        if claim_product != (creator.apple_product_id or ""):
            logger.warning(
                "creator verify product mismatch: bought %s, requested %s",
                claim_product, creator.apple_product_id,
            )
            raise HTTPException(status_code=400, detail="This purchase is for a different creator.")
        if not subscription_active_from_claims(claims):
            await creator_service.deactivate_creator_subscription(
                user_id=current_user["id"], creator=creator, db=db, status="expired"
            )
            await db.commit()
            return {"status": "expired"}
        otxn = str(claims.get("originalTransactionId") or body.transaction_id)
        expires = expires_datetime_from_claims(claims)
        await creator_service.activate_creator_subscription(
            user_id=current_user["id"], creator=creator,
            product_id=str(claims.get("productId") or body.product_id or ""),
            original_transaction_id=otxn, provider="apple", expires_at=expires, db=db,
        )
        await db.commit()
        # Entitlement is committed — now make it REAL: the creator's habits
        # land on the subscriber's schedule (best-effort, never un-grants).
        scheduled = await creator_service.ensure_creator_schedule(current_user["id"], creator.maxx_id, db)
        # "limit" = billed but at the 5-active-schedule cap — the client MUST
        # surface this (a paid sub with no schedule is silent non-delivery).
        return {
            "status": "ok",
            "schedule_created": scheduled is True,
            "schedule_blocked": "active_limit" if scheduled == "limit" else None,
        }

    # Not server-verifiable: block in production (anti-fraud), trust client in dev.
    if settings.is_production:
        raise HTTPException(status_code=503, detail="Purchase verification unavailable. Try again shortly.")
    await creator_service.activate_creator_subscription(
        user_id=current_user["id"], creator=creator,
        product_id=body.product_id or creator.apple_product_id,
        original_transaction_id=body.transaction_id, provider="apple", expires_at=None, db=db,
    )
    await db.commit()
    scheduled = await creator_service.ensure_creator_schedule(current_user["id"], creator.maxx_id, db)
    return {
        "status": "ok",
        "schedule_created": scheduled is True,
        "schedule_blocked": "active_limit" if scheduled == "limit" else None,
    }


@router.post("/subscribe/{maxx_id}/dev-activate")
async def dev_activate_creator_subscription(
    maxx_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DEV-ONLY (production-blocked): grant a creator subscription without Apple,
    so the full loop is testable on the simulator. Mirrors /payments/test-activate."""
    if settings.is_production:
        raise HTTPException(status_code=403, detail="Only available in development mode")
    # Mirror the real verify path: creator subs are an add-on to Chad.
    if not current_user.get("is_paid", False):
        raise HTTPException(status_code=402, detail="A Chad subscription is required first.")
    creator = await creator_service.get_creator_by_maxx(maxx_id, db)
    if creator is None:
        raise HTTPException(status_code=404, detail="Not a creator max")
    await creator_service.activate_creator_subscription(
        user_id=current_user["id"], creator=creator,
        product_id=creator.apple_product_id, original_transaction_id=f"dev_{current_user['id'][:8]}",
        provider="dev", expires_at=None, db=db,
    )
    await db.commit()
    scheduled = await creator_service.ensure_creator_schedule(current_user["id"], maxx_id, db)
    return {
        "status": "ok",
        "maxx_id": maxx_id,
        "schedule_created": scheduled is True,
        "schedule_blocked": "active_limit" if scheduled == "limit" else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════════════
async def _accessible_post(
    post_id: str, user_id: str, db: AsyncSession, *, require_sub: bool = False
) -> CreatorPost:
    """Load a published post the user is allowed to engage with. `require_sub`
    forces an active subscription (for commenting); likes allow the owner too."""
    try:
        pid = UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Post not found")
    post = (await db.execute(
        select(CreatorPost).where((CreatorPost.id == pid) & (CreatorPost.status == "published"))
    )).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    creator = await creator_service.get_creator_by_id(str(post.creator_id), db)
    if creator is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if not await creator_service.has_creator_access(user_id, creator, db):
        raise HTTPException(status_code=403, detail="Subscribe to interact.")
    if require_sub:
        u = await db.get(User, UUID(str(user_id)))
        is_privileged = str(creator.user_id) == user_id or (u is not None and getattr(u, "is_admin", False))
        if not is_privileged and not (
            await creator_service.active_subscription(user_id, str(creator.id), db)
        ):
            raise HTTPException(status_code=403, detail="Subscribe to comment.")
    return post


async def _fanout_habit_regen(*, creator_id: str, maxx_id: str) -> None:
    """After a habit save: regenerate every active subscriber's schedule for
    this maxx — in place, completion-status preserving (regenerate_active_
    schedules diffs by (day_index, catalog_id)). Chunked with a breather so a
    big creator doesn't hammer the DB; per-user failures are isolated."""
    import asyncio as _aio
    from services.schedule_runtime import regenerate_active_schedules
    try:
        async with AsyncSessionLocal() as db:
            uids = (await db.execute(
                select(CreatorSubscription.user_id).where(
                    (CreatorSubscription.creator_id == UUID(creator_id))
                    & creator_service.active_sub_clause()
                )
            )).scalars().all()
        done = 0
        for i, uid in enumerate(uids):
            try:
                async with AsyncSessionLocal() as udb:
                    await regenerate_active_schedules(
                        user_id=str(uid), db=udb, only_max=maxx_id,
                        reason="creator_habits_changed",
                    )
                    await udb.commit()
                done += 1
            except Exception:
                logger.exception("habit regen failed user=%s maxx=%s", uid, maxx_id)
            if (i + 1) % 50 == 0:
                await _aio.sleep(0.5)
        if uids:
            logger.info("habit regen: %d/%d subscriber schedules updated for %s", done, len(uids), maxx_id)
    except Exception:
        logger.exception("habit regen fanout failed maxx=%s", maxx_id)


async def _fanout_new_post(*, creator_id: str, maxx_id: str, creator_name: str, preview: str) -> None:
    """Enqueue a 'new update' push for every active subscriber (own DB session,
    chunked). Uses the existing queued-notification worker for delivery + caps."""
    from models.sqlalchemy_models import ScheduledNotification
    try:
        async with AsyncSessionLocal() as db:
            subs = (await db.execute(
                select(CreatorSubscription.user_id).where(
                    (CreatorSubscription.creator_id == UUID(creator_id))
                    & creator_service.active_sub_clause()
                )
            )).scalars().all()
            if not subs:
                return
            now = datetime.now(timezone.utc)
            body = f"{creator_name} posted: {preview}" if preview else f"New update from {creator_name}"
            body = body[:140]
            for uid in subs:
                db.add(ScheduledNotification(
                    user_id=uid,
                    scheduled_for=now,
                    message=body,
                    category_id="creator_update",
                    # Tap → THIS creator's feed (route stays category-mapped).
                    deep_link_params={"maxxId": maxx_id},
                    status="pending",
                ))
            await db.commit()
            logger.info("creator fanout: queued %d pushes for maxx=%s", len(subs), maxx_id)
    except Exception:
        logger.exception("creator fanout failed maxx=%s", maxx_id)
