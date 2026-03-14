"""
Forums API - Discussion forums and threads
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from datetime import datetime

from db import get_rds_db
from middleware.auth_middleware import require_paid_user, get_current_admin_user
from models.rds_models import Forum, ForumThread, ForumReply

router = APIRouter(prefix="/forums", tags=["Forums"])


@router.get("")
async def list_forums(
    rds_db: AsyncSession = Depends(get_rds_db),
    current_user: dict = Depends(require_paid_user)
):
    """List all forums"""
    result = await rds_db.execute(select(Forum))
    forums = result.scalars().all()

    return {"forums": [
        {
            "id": str(forum.id),
            "name": forum.name,
            "description": forum.description,
            "category": forum.category
        }
        for forum in forums
    ]}


@router.get("/{forum_id}")
async def get_forum(
    forum_id: str,
    rds_db: AsyncSession = Depends(get_rds_db),
    current_user: dict = Depends(require_paid_user)
):
    """Get forum details"""
    try:
        forum_uuid = UUID(forum_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid forum ID format")

    result = await rds_db.execute(select(Forum).where(Forum.id == forum_uuid))
    forum = result.scalar_one_or_none()

    if not forum:
        raise HTTPException(status_code=404, detail="Forum not found")

    # Get thread count
    threads_result = await rds_db.execute(
        select(func.count(ForumThread.id)).where(ForumThread.forum_id == forum_uuid)
    )
    thread_count = threads_result.scalar() or 0

    return {
        "id": str(forum.id),
        "name": forum.name,
        "description": forum.description,
        "category": forum.category,
        "thread_count": thread_count
    }


@router.get("/{forum_id}/threads")
async def get_forum_threads(
    forum_id: str,
    limit: int = 50,
    rds_db: AsyncSession = Depends(get_rds_db),
    current_user: dict = Depends(require_paid_user)
):
    """Get threads in a forum"""
    try:
        forum_uuid = UUID(forum_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid forum ID format")

    # Verify forum exists
    forum_result = await rds_db.execute(select(Forum).where(Forum.id == forum_uuid))
    if not forum_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Forum not found")

    # Get threads
    result = await rds_db.execute(
        select(ForumThread)
        .where(ForumThread.forum_id == forum_uuid)
        .order_by(ForumThread.is_pinned.desc(), ForumThread.created_at.desc())
        .limit(limit)
    )
    threads = result.scalars().all()

    return {"threads": [
        {
            "id": str(thread.id),
            "title": thread.title,
            "content": thread.content,
            "user_id": str(thread.user_id),
            "views": thread.views,
            "is_pinned": thread.is_pinned,
            "is_locked": thread.is_locked,
            "created_at": thread.created_at
        }
        for thread in threads
    ]}


@router.post("/{forum_id}/threads")
async def create_thread(
    forum_id: str,
    data: dict = None,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Create a thread in a forum"""
    if data is None:
        data = {}

    try:
        forum_uuid = UUID(forum_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid forum ID format")

    # Verify forum exists
    forum_result = await rds_db.execute(select(Forum).where(Forum.id == forum_uuid))
    if not forum_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Forum not found")

    thread = ForumThread(
        forum_id=forum_uuid,
        user_id=UUID(current_user["id"]),
        title=data.get("title"),
        content=data.get("content"),
        views=0,
        is_pinned=False,
        is_locked=False
    )

    rds_db.add(thread)
    await rds_db.commit()
    await rds_db.refresh(thread)

    return {"thread_id": str(thread.id)}


@router.get("/{forum_id}/threads/{thread_id}")
async def get_thread(
    forum_id: str,
    thread_id: str,
    rds_db: AsyncSession = Depends(get_rds_db),
    current_user: dict = Depends(require_paid_user)
):
    """Get thread details with replies"""
    try:
        forum_uuid = UUID(forum_id)
        thread_uuid = UUID(thread_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await rds_db.execute(
        select(ForumThread)
        .where((ForumThread.id == thread_uuid) & (ForumThread.forum_id == forum_uuid))
    )
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Increment view count
    thread.views = (thread.views or 0) + 1
    await rds_db.commit()

    # Get replies
    replies_result = await rds_db.execute(
        select(ForumReply)
        .where(ForumReply.thread_id == thread_uuid)
        .order_by(ForumReply.created_at.asc())
    )
    replies = replies_result.scalars().all()

    return {
        "id": str(thread.id),
        "title": thread.title,
        "content": thread.content,
        "user_id": str(thread.user_id),
        "views": thread.views,
        "is_pinned": thread.is_pinned,
        "is_locked": thread.is_locked,
        "created_at": thread.created_at,
        "replies": [
            {
                "id": str(reply.id),
                "content": reply.content,
                "user_id": str(reply.user_id),
                "likes": reply.likes,
                "created_at": reply.created_at
            }
            for reply in replies
        ]
    }


@router.post("/{forum_id}/threads/{thread_id}/replies")
async def create_reply(
    forum_id: str,
    thread_id: str,
    data: dict = None,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Create a reply to a thread"""
    if data is None:
        data = {}

    try:
        forum_uuid = UUID(forum_id)
        thread_uuid = UUID(thread_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    # Verify thread exists
    thread_result = await rds_db.execute(
        select(ForumThread)
        .where((ForumThread.id == thread_uuid) & (ForumThread.forum_id == forum_uuid))
    )
    thread = thread_result.scalar_one_or_none()

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.is_locked:
        raise HTTPException(status_code=403, detail="Thread is locked")

    reply = ForumReply(
        thread_id=thread_uuid,
        user_id=UUID(current_user["id"]),
        content=data.get("content"),
        likes=0
    )

    rds_db.add(reply)
    await rds_db.commit()
    await rds_db.refresh(reply)

    return {"reply_id": str(reply.id)}


@router.post("/{forum_id}/threads/{thread_id}/replies/{reply_id}/like")
async def like_reply(
    forum_id: str,
    thread_id: str,
    reply_id: str,
    rds_db: AsyncSession = Depends(get_rds_db),
    current_user: dict = Depends(require_paid_user)
):
    """Like a reply"""
    try:
        reply_uuid = UUID(reply_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid reply ID format")

    result = await rds_db.execute(select(ForumReply).where(ForumReply.id == reply_uuid))
    reply = result.scalar_one_or_none()

    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")

    reply.likes = (reply.likes or 0) + 1
    await rds_db.commit()

    return {"likes": reply.likes}


@router.post("")
async def create_forum(
    data: dict = None,
    admin: dict = Depends(get_current_admin_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Create forum (admin only)"""
    if data is None:
        data = {}

    forum = Forum(
        name=data.get("name"),
        description=data.get("description"),
        category=data.get("category")
    )

    rds_db.add(forum)
    await rds_db.commit()
    await rds_db.refresh(forum)

    return {"forum_id": str(forum.id)}

