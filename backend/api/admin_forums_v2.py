"""
Admin-only CRUD for Forums v2 (categories, subforums / boards).
Lets admins create premium boards, official categories, etc.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_rds_db
from middleware.auth_middleware import get_current_admin_user
from models.forum_v2 import (
    AdminForumCategoryCreate,
    AdminForumCategoryUpdate,
    AdminForumSubforumCreate,
    AdminForumSubforumUpdate,
)
from models.rds_models import ForumCategory, ForumSubforum, ForumThread

router = APIRouter(prefix="/admin/forums/v2", tags=["Admin Forums V2"])

logger = logging.getLogger(__name__)


async def _commit_or_409(rds_db: AsyncSession) -> None:
    """Commit; map unique / FK violations to a clear client message (avoids opaque 500s)."""
    try:
        await rds_db.commit()
    except IntegrityError as e:
        await rds_db.rollback()
        logger.warning("admin forums RDS integrity: %s", e.orig)
        raise HTTPException(
            status_code=409,
            detail="That category or board name is already taken. Use a different name.",
        ) from e


def _slugify(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:64] or "category"


def _coerce_uuid(raw: str, *, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid {label}")


async def _unique_category_slug(
    rds_db: AsyncSession, base: str, *, exclude_category_id: uuid.UUID | None = None
) -> str:
    slug = base
    for i in range(0, 8):
        existing = (
            await rds_db.execute(select(ForumCategory).where(ForumCategory.slug == slug))
        ).scalar_one_or_none()
        if not existing or (exclude_category_id and existing.id == exclude_category_id):
            return slug
        slug = f"{base}-{i + 2}"
    return f"{base}-{uuid.uuid4().hex[:6]}"


async def _unique_subforum_slug(
    rds_db: AsyncSession, base: str, *, exclude_subforum_id: uuid.UUID | None = None
) -> str:
    slug = base
    for i in range(0, 8):
        existing = (
            await rds_db.execute(select(ForumSubforum).where(ForumSubforum.slug == slug))
        ).scalar_one_or_none()
        if not existing or (exclude_subforum_id and existing.id == exclude_subforum_id):
            return slug
        slug = f"{base}-{i + 2}"
    return f"{base}-{uuid.uuid4().hex[:6]}"


@router.get("/overview")
async def admin_forums_overview(
    admin: dict = Depends(get_current_admin_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """All categories with nested subforums (admin)."""
    cats = (await rds_db.execute(select(ForumCategory).order_by(ForumCategory.order.asc()))).scalars().all()
    subs = (await rds_db.execute(select(ForumSubforum).order_by(ForumSubforum.order.asc()))).scalars().all()
    by_cat: dict[uuid.UUID, list[ForumSubforum]] = {}
    for s in subs:
        by_cat.setdefault(s.category_id, []).append(s)

    sub_ids = [s.id for s in subs]
    counts: dict[uuid.UUID, int] = {}
    if sub_ids:
        count_res = await rds_db.execute(
            select(ForumThread.subforum_id, func.count(ForumThread.id))
            .where(ForumThread.subforum_id.in_(sub_ids))
            .group_by(ForumThread.subforum_id)
        )
        counts = {sid: int(n) for sid, n in count_res.all()}

    out_cats = []
    for c in cats:
        children = by_cat.get(c.id, [])
        out_cats.append(
            {
                "id": str(c.id),
                "name": c.name,
                "slug": c.slug,
                "description": c.description,
                "order": int(c.order or 0),
                "created_at": c.created_at,
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
                    }
                    for s in children
                ],
            }
        )
    return {"categories": out_cats}


@router.post("/categories")
async def admin_create_category(
    data: AdminForumCategoryCreate,
    admin: dict = Depends(get_current_admin_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    name = data.name.strip()
    slug = await _unique_category_slug(rds_db, _slugify(name))
    row = ForumCategory(
        id=uuid.uuid4(),
        name=name,
        slug=slug,
        description=(data.description or "").strip() or None,
        order=int(data.order),
        created_at=datetime.now(timezone.utc),
    )
    rds_db.add(row)
    await _commit_or_409(rds_db)
    await rds_db.refresh(row)
    return {"id": str(row.id), "slug": row.slug}


@router.patch("/categories/{category_id}")
async def admin_update_category(
    category_id: str,
    data: AdminForumCategoryUpdate,
    admin: dict = Depends(get_current_admin_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    cid = _coerce_uuid(category_id, label="category_id")
    row = await rds_db.get(ForumCategory, cid)
    if not row:
        raise HTTPException(status_code=404, detail="Category not found")
    if data.name is not None:
        row.name = data.name.strip()
        row.slug = await _unique_category_slug(rds_db, _slugify(row.name), exclude_category_id=row.id)
    if data.description is not None:
        row.description = data.description.strip() or None
    if data.order is not None:
        row.order = int(data.order)
    await _commit_or_409(rds_db)
    await rds_db.refresh(row)
    return {"id": str(row.id), "slug": row.slug}


@router.delete("/categories/{category_id}")
async def admin_delete_category(
    category_id: str,
    admin: dict = Depends(get_current_admin_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    cid = _coerce_uuid(category_id, label="category_id")
    row = await rds_db.get(ForumCategory, cid)
    if not row:
        raise HTTPException(status_code=404, detail="Category not found")
    await rds_db.delete(row)
    await rds_db.commit()
    return {"deleted": True}


@router.post("/subforums")
async def admin_create_subforum(
    data: AdminForumSubforumCreate,
    admin: dict = Depends(get_current_admin_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    cid = _coerce_uuid(data.category_id, label="category_id")
    cat = await rds_db.get(ForumCategory, cid)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    name = data.name.strip()
    desc = (data.description or "").strip()
    tier = (data.access_tier or "public").lower()
    if tier not in ("public", "premium"):
        raise HTTPException(status_code=400, detail="access_tier must be public or premium")
    base_slug = _slugify(f"{cat.slug}-{name}")
    slug = await _unique_subforum_slug(rds_db, base_slug)
    admin_uid = _coerce_uuid(admin["id"], label="admin_id")
    order = int(data.order) if data.order is not None else 9999
    row = ForumSubforum(
        id=uuid.uuid4(),
        category_id=cid,
        name=name,
        slug=slug,
        description=desc or None,
        order=order,
        access_tier=tier,
        is_read_only=bool(data.is_read_only),
        created_by=admin_uid,
        created_at=datetime.now(timezone.utc),
    )
    rds_db.add(row)
    await _commit_or_409(rds_db)
    await rds_db.refresh(row)
    return {"id": str(row.id), "slug": row.slug}


@router.patch("/subforums/{subforum_id}")
async def admin_update_subforum(
    subforum_id: str,
    data: AdminForumSubforumUpdate,
    admin: dict = Depends(get_current_admin_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    sid = _coerce_uuid(subforum_id, label="subforum_id")
    row = await rds_db.get(ForumSubforum, sid)
    if not row:
        raise HTTPException(status_code=404, detail="Subforum not found")
    if data.category_id is not None:
        cid = _coerce_uuid(data.category_id, label="category_id")
        cat = await rds_db.get(ForumCategory, cid)
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        row.category_id = cid
    if data.name is not None:
        row.name = data.name.strip()
        cat = await rds_db.get(ForumCategory, row.category_id)
        cslug = (cat.slug if cat else "board") or "board"
        row.slug = await _unique_subforum_slug(
            rds_db, _slugify(f"{cslug}-{row.name}"), exclude_subforum_id=row.id
        )
    if data.description is not None:
        row.description = data.description.strip() or None
    if data.access_tier is not None:
        t = data.access_tier.lower()
        if t not in ("public", "premium"):
            raise HTTPException(status_code=400, detail="access_tier must be public or premium")
        row.access_tier = t
    if data.is_read_only is not None:
        row.is_read_only = bool(data.is_read_only)
    if data.order is not None:
        row.order = int(data.order)
    await _commit_or_409(rds_db)
    await rds_db.refresh(row)
    return {"id": str(row.id), "slug": row.slug}


@router.delete("/subforums/{subforum_id}")
async def admin_delete_subforum(
    subforum_id: str,
    admin: dict = Depends(get_current_admin_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    sid = _coerce_uuid(subforum_id, label="subforum_id")
    row = await rds_db.get(ForumSubforum, sid)
    if not row:
        raise HTTPException(status_code=404, detail="Subforum not found")
    await rds_db.delete(row)
    await rds_db.commit()
    return {"deleted": True}
