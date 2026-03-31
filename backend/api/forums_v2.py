"""
Forums v2 API - classic threads (categories -> subforums -> threads -> posts)

Routes are versioned under /forums/v2 so the legacy channel-chat forums can coexist.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db, get_rds_db
from middleware.auth_middleware import get_current_user
from models.forum_v2 import (
    ForumPostCreate,
    ForumReportCreate,
    ForumSubforumCreate,
    ForumThreadCreate,
    ForumVoteRequest,
)
from models.rds_models import (
    ForumCategory,
    ForumNotification,
    ForumPost,
    ForumPostReport,
    ForumPostVote,
    ForumSubforum,
    ForumThread,
    ForumThreadWatch,
)
from models.sqlalchemy_models import User


router = APIRouter(prefix="/forums/v2", tags=["ForumsV2"])

_MAX_POST_CHARS = 8000
_MAX_TITLE_CHARS = 200
_TAG_RX = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,23}$", re.I)
_MENTION_RX = re.compile(r"@([a-z0-9_]{3,24})", re.I)


def _slugify(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:64] or "board"


def _coerce_uuid(raw: str, *, label: str) -> UUID:
    try:
        return UUID(str(raw))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid {label}")


def _require_subforum_access(subforum: ForumSubforum, viewer: dict) -> None:
    board_tier = (subforum.access_tier or "public").lower()
    if board_tier == "public":
        return
    if bool(viewer.get("is_admin")):
        return
    if not bool(viewer.get("is_paid")):
        raise HTTPException(status_code=402, detail="Premium forum. Subscribe to access.")
    user_tier = (viewer.get("subscription_tier") or "basic").lower()
    if board_tier == "premium" and user_tier != "premium":
        raise HTTPException(status_code=403, detail="Premium forum. Upgrade to Premium to access.")


def _can_access_subforum_row(subforum: ForumSubforum, viewer: dict) -> bool:
    try:
        _require_subforum_access(subforum, viewer)
        return True
    except HTTPException:
        return False


def _normalize_tags(tags: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in tags or []:
        t = str(raw or "").strip()
        if not t:
            continue
        if t.startswith("#"):
            t = t[1:]
        if not _TAG_RX.match(t):
            continue
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(k)
        if len(out) >= 8:
            break
    return out


def _extract_entities(text: str, *, quote_post_id: str | None = None) -> dict:
    mentions = list({m.group(1).lower() for m in _MENTION_RX.finditer(text or "")})
    ent: dict = {}
    if mentions:
        ent["mentions"] = mentions[:12]
    if quote_post_id:
        ent["quote_post_id"] = quote_post_id
    return ent


@router.get("/categories")
async def list_categories(
    rds_db: AsyncSession = Depends(get_rds_db),
):
    res = await rds_db.execute(select(ForumCategory).order_by(ForumCategory.order.asc()))
    cats = res.scalars().all()
    return {
        "categories": [
            {
                "id": str(c.id),
                "name": c.name,
                "slug": c.slug,
                "description": c.description,
                "order": int(c.order or 0),
                "created_at": c.created_at,
            }
            for c in cats
        ]
    }


@router.get("/subforums")
async def list_subforums(
    category_id: str | None = None,
    rds_db: AsyncSession = Depends(get_rds_db),
):
    q = select(ForumSubforum)
    if category_id:
        cid = _coerce_uuid(category_id, label="category_id")
        q = q.where(ForumSubforum.category_id == cid)
    q = q.order_by(ForumSubforum.order.asc())
    res = await rds_db.execute(q)
    subs = res.scalars().all()

    # thread counts + last activity
    sub_ids = [s.id for s in subs]
    counts: dict[UUID, int] = {}
    last: dict[UUID, datetime] = {}
    if sub_ids:
        count_res = await rds_db.execute(
            select(ForumThread.subforum_id, func.count(ForumThread.id))
            .where(ForumThread.subforum_id.in_(sub_ids))
            .group_by(ForumThread.subforum_id)
        )
        counts = {sid: int(n) for sid, n in count_res.all()}
        last_res = await rds_db.execute(
            select(ForumThread.subforum_id, func.max(ForumThread.last_post_at))
            .where(ForumThread.subforum_id.in_(sub_ids))
            .group_by(ForumThread.subforum_id)
        )
        last = {sid: ts for sid, ts in last_res.all() if ts}

    return {
        "subforums": [
            {
                "id": str(s.id),
                "category_id": str(s.category_id),
                "name": s.name,
                "slug": s.slug,
                "description": s.description,
                "order": int(s.order or 0),
                "access_tier": (s.access_tier or "public").lower(),
                "is_read_only": bool(s.is_read_only),
                "thread_count": counts.get(s.id, 0),
                "last_activity": last.get(s.id),
            }
            for s in subs
        ]
    }


@router.post("/subforums")
async def create_subforum(
    data: ForumSubforumCreate,
    current_user: dict = Depends(get_current_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    # Users can create PUBLIC boards only. Premium boards are system-curated.
    cid = _coerce_uuid(data.category_id, label="category_id")
    cat = await rds_db.get(ForumCategory, cid)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    if (cat.slug or "").lower() in ("official", "premium", "influence") and not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="You can't create boards in this category.")

    name = (data.name or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Name too short")
    desc = (data.description or "").strip()
    slug = _slugify(f"{cat.slug}-{name}")

    # Ensure slug uniqueness
    base = slug
    for i in range(0, 6):
        existing = (await rds_db.execute(select(ForumSubforum).where(ForumSubforum.slug == slug))).scalar_one_or_none()
        if not existing:
            break
        slug = f"{base}-{i+2}"

    row = ForumSubforum(
        category_id=cid,
        name=name,
        slug=slug,
        description=desc,
        order=9999,
        access_tier="public",
        is_read_only=False,
        created_by=_coerce_uuid(current_user["id"], label="user_id"),
        created_at=datetime.now(timezone.utc),
    )
    rds_db.add(row)
    await rds_db.commit()
    await rds_db.refresh(row)
    return {"id": str(row.id), "slug": row.slug    }


@router.get("/search/threads")
async def search_threads_global(
    q: str = Query(..., min_length=1),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    rds_db: AsyncSession = Depends(get_rds_db),
    db: AsyncSession = Depends(get_db),
):
    """Search thread titles across all boards the viewer can access."""
    needle = f"%{q.strip()}%"
    qq = (
        select(ForumThread, ForumSubforum)
        .join(ForumSubforum, ForumThread.subforum_id == ForumSubforum.id)
        .where(ForumThread.title.ilike(needle))
        .order_by(ForumThread.last_post_at.desc(), ForumThread.created_at.desc())
    )
    res = await rds_db.execute(qq.limit(400))
    rows = res.all()

    filtered: list[tuple[ForumThread, ForumSubforum]] = []
    for t, sub in rows:
        if _can_access_subforum_row(sub, current_user):
            filtered.append((t, sub))

    total = len(filtered)
    page = filtered[offset : offset + limit]

    uids = list({t.user_id for t, _ in page})
    users_map: dict[UUID, User] = {}
    if uids:
        ures = await db.execute(select(User).where(User.id.in_(uids)))
        users_map = {u.id: u for u in ures.scalars().all()}

    return {
        "threads": [
            {
                "id": str(t.id),
                "subforum_id": str(sub.id),
                "title": t.title,
                "tags": t.tags or [],
                "is_sticky": bool(t.is_sticky),
                "is_locked": bool(t.is_locked),
                "view_count": int(t.view_count or 0),
                "reply_count": int(t.reply_count or 0),
                "last_post_at": t.last_post_at,
                "created_at": t.created_at,
                "created_by": str(t.user_id),
                "created_by_username": (users_map.get(t.user_id).username if users_map.get(t.user_id) else None),
                "subforum": {
                    "id": str(sub.id),
                    "name": sub.name,
                    "slug": sub.slug,
                    "access_tier": (sub.access_tier or "public").lower(),
                    "is_read_only": bool(sub.is_read_only),
                },
            }
            for t, sub in page
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/subforums/{subforum_id}/threads")
async def list_threads(
    subforum_id: str,
    sort: str = Query("new", pattern="^(new|hot|top)$"),
    q: str | None = None,
    tag: str | None = None,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    rds_db: AsyncSession = Depends(get_rds_db),
    db: AsyncSession = Depends(get_db),
):
    sid = _coerce_uuid(subforum_id, label="subforum_id")
    sub = await rds_db.get(ForumSubforum, sid)
    if not sub:
        raise HTTPException(status_code=404, detail="Subforum not found")
    _require_subforum_access(sub, current_user)

    qq = select(ForumThread).where(ForumThread.subforum_id == sid)
    if q:
        qq = qq.where(ForumThread.title.ilike(f"%{q.strip()}%"))
    if tag:
        # basic JSON contains filter (portable enough for JSONB via @> would be nicer)
        t = str(tag).strip().lstrip("#").lower()
        if t:
            qq = qq.where(func.cast(ForumThread.tags, str).ilike(f"%{t}%"))

    if sort == "new":
        qq = qq.order_by(ForumThread.is_sticky.desc(), ForumThread.last_post_at.desc())
    elif sort == "top":
        qq = qq.order_by(ForumThread.is_sticky.desc(), ForumThread.reply_count.desc(), ForumThread.last_post_at.desc())
    else:  # hot
        # simple hot proxy: replies / age_hours
        age_hours = func.extract("epoch", func.now() - ForumThread.created_at) / 3600.0
        hot = (ForumThread.reply_count + 1) / func.greatest(1.0, age_hours)
        qq = qq.order_by(ForumThread.is_sticky.desc(), hot.desc(), ForumThread.last_post_at.desc())

    total_res = await rds_db.execute(select(func.count()).select_from(qq.subquery()))
    total = int(total_res.scalar() or 0)

    res = await rds_db.execute(qq.offset(offset).limit(limit))
    threads = res.scalars().all()

    # map creators
    uids = list({t.user_id for t in threads})
    users_map: dict[UUID, User] = {}
    if uids:
        ures = await db.execute(select(User).where(User.id.in_(uids)))
        users_map = {u.id: u for u in ures.scalars().all()}

    return {
        "threads": [
            {
                "id": str(t.id),
                "subforum_id": str(t.subforum_id),
                "title": t.title,
                "tags": t.tags or [],
                "is_sticky": bool(t.is_sticky),
                "is_locked": bool(t.is_locked),
                "view_count": int(t.view_count or 0),
                "reply_count": int(t.reply_count or 0),
                "last_post_at": t.last_post_at,
                "created_at": t.created_at,
                "created_by": str(t.user_id),
                "created_by_username": (users_map.get(t.user_id).username if users_map.get(t.user_id) else None),
            }
            for t in threads
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "subforum": {
            "id": str(sub.id),
            "name": sub.name,
            "slug": sub.slug,
            "access_tier": (sub.access_tier or "public").lower(),
            "is_read_only": bool(sub.is_read_only),
        },
    }


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    current_user: dict = Depends(get_current_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    tid = _coerce_uuid(thread_id, label="thread_id")
    thread = await rds_db.get(ForumThread, tid)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    sub = await rds_db.get(ForumSubforum, thread.subforum_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subforum not found")
    _require_subforum_access(sub, current_user)

    # bump view count best-effort (no need to be exact)
    try:
        thread.view_count = int(thread.view_count or 0) + 1
        await rds_db.commit()
    except Exception:
        await rds_db.rollback()

    return {
        "thread": {
            "id": str(thread.id),
            "subforum_id": str(thread.subforum_id),
            "title": thread.title,
            "tags": thread.tags or [],
            "is_sticky": bool(thread.is_sticky),
            "is_locked": bool(thread.is_locked),
            "view_count": int(thread.view_count or 0),
            "reply_count": int(thread.reply_count or 0),
            "last_post_at": thread.last_post_at,
            "created_at": thread.created_at,
            "created_by": str(thread.user_id),
        }
    }


@router.get("/threads/{thread_id}/posts")
async def list_posts(
    thread_id: str,
    sort: str = Query("new", pattern="^(new|top)$"),
    limit: int = Query(40, ge=1, le=120),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    rds_db: AsyncSession = Depends(get_rds_db),
    db: AsyncSession = Depends(get_db),
):
    tid = _coerce_uuid(thread_id, label="thread_id")
    thread = await rds_db.get(ForumThread, tid)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    sub = await rds_db.get(ForumSubforum, thread.subforum_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subforum not found")
    _require_subforum_access(sub, current_user)

    pq = select(ForumPost).where(ForumPost.thread_id == tid)
    if sort == "top":
        pq = pq.order_by(ForumPost.score.desc(), ForumPost.created_at.asc())
    else:
        pq = pq.order_by(ForumPost.created_at.asc())
    total_res = await rds_db.execute(select(func.count()).select_from(pq.subquery()))
    total = int(total_res.scalar() or 0)
    res = await rds_db.execute(pq.offset(offset).limit(limit))
    posts = res.scalars().all()

    uids = list({p.user_id for p in posts})
    users_map: dict[UUID, User] = {}
    if uids:
        ures = await db.execute(select(User).where(User.id.in_(uids)))
        users_map = {u.id: u for u in ures.scalars().all()}

    my_vote_by_post: dict[UUID, int] = {}
    if posts:
        post_ids = [p.id for p in posts]
        me = _coerce_uuid(current_user["id"], label="user_id")
        vres = await rds_db.execute(
            select(ForumPostVote.post_id, ForumPostVote.value)
            .where(ForumPostVote.user_id == me)
            .where(ForumPostVote.post_id.in_(post_ids))
        )
        my_vote_by_post = {pid: int(v or 0) for pid, v in vres.all()}

    return {
        "posts": [
            {
                "id": str(p.id),
                "thread_id": str(p.thread_id),
                "user_id": str(p.user_id),
                "username": (users_map.get(p.user_id).username if users_map.get(p.user_id) else None),
                "user_avatar_url": (users_map.get(p.user_id).profile or {}).get("avatar_url")
                if users_map.get(p.user_id)
                else None,
                "content": p.content,
                "entities": p.entities or {},
                "attachment_url": p.attachment_url,
                "attachment_type": p.attachment_type,
                "parent_post_id": str(p.parent_post_id) if p.parent_post_id else None,
                "score": int(p.score or 0),
                "upvotes": int(p.upvotes or 0),
                "downvotes": int(p.downvotes or 0),
                "my_vote": int(my_vote_by_post.get(p.id, 0)),
                "created_at": p.created_at,
            }
            for p in posts
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "thread": {"id": str(thread.id), "title": thread.title, "is_locked": bool(thread.is_locked)},
    }


@router.post("/threads")
async def create_thread(
    data: ForumThreadCreate,
    current_user: dict = Depends(get_current_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    sid = _coerce_uuid(data.subforum_id, label="subforum_id")
    sub = await rds_db.get(ForumSubforum, sid)
    if not sub:
        raise HTTPException(status_code=404, detail="Subforum not found")
    _require_subforum_access(sub, current_user)
    if sub.is_read_only and not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="This board is read-only.")

    title = (data.title or "").strip().replace("\x00", "")
    if not title:
        raise HTTPException(status_code=400, detail="Title required")
    if len(title) > _MAX_TITLE_CHARS:
        raise HTTPException(status_code=400, detail="Title too long")

    body = (data.body or "").strip().replace("\x00", "")
    if not body:
        raise HTTPException(status_code=400, detail="Body required")
    if len(body) > _MAX_POST_CHARS:
        raise HTTPException(status_code=400, detail="Post too long")

    tags = _normalize_tags(data.tags)
    now = datetime.now(timezone.utc)

    thread = ForumThread(
        subforum_id=sid,
        user_id=_coerce_uuid(current_user["id"], label="user_id"),
        title=title,
        tags=tags,
        is_sticky=False,
        is_locked=False,
        view_count=0,
        reply_count=0,
        last_post_at=now,
        last_post_user_id=_coerce_uuid(current_user["id"], label="user_id"),
        created_at=now,
    )
    rds_db.add(thread)
    await rds_db.commit()
    await rds_db.refresh(thread)

    post = ForumPost(
        thread_id=thread.id,
        user_id=_coerce_uuid(current_user["id"], label="user_id"),
        content=body,
        entities=_extract_entities(body),
        attachment_url=data.attachment_url,
        attachment_type=data.attachment_type,
        parent_post_id=None,
        score=0,
        upvotes=0,
        downvotes=0,
        created_at=now,
        updated_at=now,
    )
    rds_db.add(post)
    await rds_db.commit()
    await rds_db.refresh(post)

    return {"thread_id": str(thread.id), "post_id": str(post.id)}


@router.post("/threads/{thread_id}/posts")
async def create_post(
    thread_id: str,
    data: ForumPostCreate,
    current_user: dict = Depends(get_current_user),
    rds_db: AsyncSession = Depends(get_rds_db),
    db: AsyncSession = Depends(get_db),
):
    tid = _coerce_uuid(thread_id, label="thread_id")
    thread = await rds_db.get(ForumThread, tid)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    sub = await rds_db.get(ForumSubforum, thread.subforum_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subforum not found")
    _require_subforum_access(sub, current_user)
    if thread.is_locked and not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Thread is locked.")
    if sub.is_read_only and not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="This board is read-only.")

    has_attachment = bool(data.attachment_url and str(data.attachment_url).strip())
    text = (data.content or "").strip().replace("\x00", "")
    if not has_attachment and not text:
        raise HTTPException(status_code=400, detail="Post cannot be empty")
    if len(text) > _MAX_POST_CHARS:
        raise HTTPException(status_code=400, detail="Post too long")

    parent_post_uuid = _coerce_uuid(data.parent_post_id, label="parent_post_id") if data.parent_post_id else None
    quote_post_uuid = _coerce_uuid(data.quote_post_id, label="quote_post_id") if data.quote_post_id else None
    if quote_post_uuid:
        qp = await rds_db.get(ForumPost, quote_post_uuid)
        if not qp or qp.thread_id != tid:
            raise HTTPException(status_code=400, detail="Invalid quote_post_id")
        if parent_post_uuid is None:
            parent_post_uuid = quote_post_uuid

    ent = _extract_entities(text, quote_post_id=str(quote_post_uuid) if quote_post_uuid else None)
    now = datetime.now(timezone.utc)
    post = ForumPost(
        thread_id=tid,
        user_id=_coerce_uuid(current_user["id"], label="user_id"),
        content=text,
        entities=ent,
        attachment_url=data.attachment_url,
        attachment_type=data.attachment_type,
        parent_post_id=parent_post_uuid,
        score=0,
        upvotes=0,
        downvotes=0,
        created_at=now,
        updated_at=now,
    )
    rds_db.add(post)

    # update thread summary fields
    thread.reply_count = int(thread.reply_count or 0) + 1
    thread.last_post_at = now
    thread.last_post_user_id = _coerce_uuid(current_user["id"], label="user_id")

    await rds_db.commit()
    await rds_db.refresh(post)

    # notifications (best-effort)
    try:
        author_id = str(thread.user_id)
        actor_id = current_user["id"]
        if author_id != actor_id:
            rds_db.add(
                ForumNotification(
                    user_id=_coerce_uuid(author_id, label="user_id"),
                    type="reply",
                    entity_id=tid,
                    actor_user_id=_coerce_uuid(actor_id, label="actor_user_id"),
                    payload={"thread_id": str(tid), "post_id": str(post.id)},
                    is_read=False,
                    created_at=now,
                )
            )
        for uname in (ent.get("mentions") or []):
            ures = await db.execute(select(User).where(func.lower(User.username) == uname))
            urow = ures.scalar_one_or_none()
            if not urow:
                continue
            if str(urow.id) == actor_id:
                continue
            rds_db.add(
                ForumNotification(
                    user_id=urow.id,
                    type="mention",
                    entity_id=UUID(str(post.id)),
                    actor_user_id=_coerce_uuid(actor_id, label="actor_user_id"),
                    payload={"thread_id": str(tid), "post_id": str(post.id), "username": uname},
                    is_read=False,
                    created_at=now,
                )
            )
        # watchers
        wres = await rds_db.execute(select(ForumThreadWatch.user_id).where(ForumThreadWatch.thread_id == tid))
        watchers = [str(x) for x in wres.scalars().all()]
        for wid in watchers:
            if wid in (actor_id, author_id):
                continue
            rds_db.add(
                ForumNotification(
                    user_id=_coerce_uuid(wid, label="user_id"),
                    type="watch",
                    entity_id=tid,
                    actor_user_id=_coerce_uuid(actor_id, label="actor_user_id"),
                    payload={"thread_id": str(tid), "post_id": str(post.id)},
                    is_read=False,
                    created_at=now,
                )
            )
        await rds_db.commit()
    except Exception:
        await rds_db.rollback()

    return {"post_id": str(post.id)}


@router.post("/posts/{post_id}/vote")
async def vote_post(
    post_id: str,
    data: ForumVoteRequest,
    current_user: dict = Depends(get_current_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    pid = _coerce_uuid(post_id, label="post_id")
    post = await rds_db.get(ForumPost, pid)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    v = int(data.value)
    if v not in (1, -1):
        raise HTTPException(status_code=400, detail="Vote must be +1 or -1")

    uid = _coerce_uuid(current_user["id"], label="user_id")
    existing_res = await rds_db.execute(
        select(ForumPostVote).where(ForumPostVote.post_id == pid).where(ForumPostVote.user_id == uid)
    )
    existing = existing_res.scalar_one_or_none()

    up = int(post.upvotes or 0)
    down = int(post.downvotes or 0)
    score = int(post.score or 0)

    if not existing:
        rds_db.add(ForumPostVote(post_id=pid, user_id=uid, value=v, created_at=datetime.now(timezone.utc)))
        if v == 1:
            up += 1
        else:
            down += 1
        score += v
        my_vote = v
    else:
        prev = int(existing.value or 0)
        if prev == v:
            # toggle off
            await rds_db.delete(existing)
            if v == 1:
                up = max(0, up - 1)
            else:
                down = max(0, down - 1)
            score -= v
            my_vote = 0
        else:
            # switch vote
            existing.value = v
            if prev == 1:
                up = max(0, up - 1)
                score -= 1
            elif prev == -1:
                down = max(0, down - 1)
                score += 1
            if v == 1:
                up += 1
                score += 1
            else:
                down += 1
                score -= 1
            my_vote = v

    post.upvotes = up
    post.downvotes = down
    post.score = score

    await rds_db.commit()
    return {"score": int(post.score or 0), "upvotes": int(post.upvotes or 0), "downvotes": int(post.downvotes or 0), "my_vote": int(my_vote)}


@router.post("/threads/{thread_id}/watch")
async def watch_thread(
    thread_id: str,
    watch: bool = True,
    current_user: dict = Depends(get_current_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    tid = _coerce_uuid(thread_id, label="thread_id")
    thread = await rds_db.get(ForumThread, tid)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    uid = _coerce_uuid(current_user["id"], label="user_id")

    existing_res = await rds_db.execute(
        select(ForumThreadWatch).where(ForumThreadWatch.thread_id == tid).where(ForumThreadWatch.user_id == uid)
    )
    existing = existing_res.scalar_one_or_none()
    if watch:
        if not existing:
            rds_db.add(ForumThreadWatch(thread_id=tid, user_id=uid, created_at=datetime.now(timezone.utc)))
            try:
                await rds_db.commit()
            except IntegrityError:
                await rds_db.rollback()
        return {"watching": True}
    else:
        if existing:
            await rds_db.delete(existing)
            await rds_db.commit()
        return {"watching": False}


@router.get("/notifications")
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(40, ge=1, le=120),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    uid = _coerce_uuid(current_user["id"], label="user_id")
    nq = select(ForumNotification).where(ForumNotification.user_id == uid)
    if unread_only:
        nq = nq.where(ForumNotification.is_read == False)  # noqa: E712
    nq = nq.order_by(ForumNotification.created_at.desc()).offset(offset).limit(limit)
    res = await rds_db.execute(nq)
    items = res.scalars().all()
    return {
        "notifications": [
            {
                "id": str(n.id),
                "type": n.type,
                "entity_id": str(n.entity_id),
                "actor_user_id": str(n.actor_user_id) if n.actor_user_id else None,
                "payload": n.payload or {},
                "is_read": bool(n.is_read),
                "created_at": n.created_at,
            }
            for n in items
        ],
        "limit": limit,
        "offset": offset,
    }


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    nid = _coerce_uuid(notification_id, label="notification_id")
    uid = _coerce_uuid(current_user["id"], label="user_id")
    notif = await rds_db.get(ForumNotification, nid)
    if not notif or notif.user_id != uid:
        raise HTTPException(status_code=404, detail="Not found")
    notif.is_read = True
    await rds_db.commit()
    return {"ok": True}


@router.post("/posts/{post_id}/report")
async def report_post(
    post_id: str,
    data: ForumReportCreate,
    current_user: dict = Depends(get_current_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    pid = _coerce_uuid(post_id, label="post_id")
    post = await rds_db.get(ForumPost, pid)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    uid = _coerce_uuid(current_user["id"], label="user_id")

    existing = (
        await rds_db.execute(
            select(ForumPostReport)
            .where(ForumPostReport.post_id == pid)
            .where(ForumPostReport.reporter_user_id == uid)
        )
    ).scalar_one_or_none()
    if existing:
        return {"ok": True, "message": "Already reported"}

    reason = (data.reason or "").strip()
    rds_db.add(
        ForumPostReport(
            post_id=pid,
            reporter_user_id=uid,
            reason=reason,
            status="open",
            created_at=datetime.now(timezone.utc),
        )
    )
    try:
        await rds_db.commit()
    except IntegrityError:
        await rds_db.rollback()
        return {"ok": True, "message": "Already reported"}
    return {"ok": True}

