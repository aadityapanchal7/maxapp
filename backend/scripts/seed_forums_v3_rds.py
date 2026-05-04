"""
Seed forums v2 on RDS: Official (read-only), Influencers (premium, 3 boards),
one community subforum per Max line, then merge legacy boards into canonical slugs.

Run: python -m scripts.seed_forums_v3_rds  (from backend/)
"""

import asyncio
import re
from datetime import datetime, timezone

from sqlalchemy import select, update

from db.rds import RDSSessionLocal
from models.rds_models import ForumCategory, ForumSubforum, ForumThread


def _slugify(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:64] or "board"


def _sub_slug(category_name: str, subforum_name: str) -> str:
    return _slugify(f"{category_name}-{subforum_name}")


# One canonical board per Maxx category (name matches category for clarity).
_MAX_CATEGORY_NAMES = ("SkinMax", "HairMax", "FitMax", "BoneMax", "HeightMax")


async def _merge_duplicate_subforums_into_canonical(rds, cat_rows: dict[str, ForumCategory]) -> None:
    """Move threads from extra subforums onto the single canonical board per Maxx category, then delete extras."""
    for name in _MAX_CATEGORY_NAMES:
        cat = cat_rows.get(name)
        if not cat:
            continue
        canonical_slug = _sub_slug(name, name)
        res = await rds.execute(select(ForumSubforum).where(ForumSubforum.category_id == cat.id))
        subs = list(res.scalars().all())
        if len(subs) <= 1:
            continue
        keeper = next((s for s in subs if (s.slug or "") == canonical_slug), None)
        if not keeper:
            keeper = sorted(subs, key=lambda x: (int(x.order or 0), x.name or ""))[0]
        for s in subs:
            if s.id == keeper.id:
                continue
            await rds.execute(update(ForumThread).where(ForumThread.subforum_id == s.id).values(subforum_id=keeper.id))
            await rds.delete(s)
        await rds.flush()


async def seed_forums_v3_rds():
    now = datetime.now(timezone.utc)

    categories = [
        {"name": "Official", "description": "Announcements and guidelines", "order": 0},
        {"name": "Influencers", "description": "Premium influencer chats", "order": 1},
        {"name": "SkinMax", "description": "SkinMax community", "order": 2},
        {"name": "HairMax", "description": "HairMax community", "order": 3},
        {"name": "FitMax", "description": "FitMax community", "order": 4},
        {"name": "BoneMax", "description": "BoneMax community", "order": 5},
        {"name": "HeightMax", "description": "HeightMax community", "order": 6},
    ]

    subforums = [
        {
            "category": "Official",
            "name": "announcements",
            "description": "Official updates (read-only)",
            "access_tier": "public",
            "order": 0,
            "is_read_only": True,
        },
        {
            "category": "Official",
            "name": "rules / guidelines",
            "description": "Forum rules and posting guidelines (read-only)",
            "access_tier": "public",
            "order": 1,
            "is_read_only": True,
        },
        {
            "category": "Influencers",
            "name": "AK Pilled",
            "description": "Premium chat — AK Pilled",
            "access_tier": "premium",
            "order": 0,
            "is_read_only": False,
        },
        {
            "category": "Influencers",
            "name": "Barclay",
            "description": "Premium chat — Barclay",
            "access_tier": "premium",
            "order": 1,
            "is_read_only": False,
        },
        {
            "category": "Influencers",
            "name": "Kiru",
            "description": "Premium chat — Kiru",
            "access_tier": "premium",
            "order": 2,
            "is_read_only": False,
        },
        {
            "category": "SkinMax",
            "name": "SkinMax",
            "description": "All SkinMax threads",
            "access_tier": "public",
            "order": 0,
            "is_read_only": False,
        },
        {
            "category": "HairMax",
            "name": "HairMax",
            "description": "All HairMax threads",
            "access_tier": "public",
            "order": 0,
            "is_read_only": False,
        },
        {
            "category": "FitMax",
            "name": "FitMax",
            "description": "All FitMax threads",
            "access_tier": "public",
            "order": 0,
            "is_read_only": False,
        },
        {
            "category": "BoneMax",
            "name": "BoneMax",
            "description": "All BoneMax threads",
            "access_tier": "public",
            "order": 0,
            "is_read_only": False,
        },
        {
            "category": "HeightMax",
            "name": "HeightMax",
            "description": "All HeightMax threads",
            "access_tier": "public",
            "order": 0,
            "is_read_only": False,
        },
    ]

    wanted_subforum_slugs = {_sub_slug(s["category"], s["name"]) for s in subforums}

    async with RDSSessionLocal() as rds:
        cat_rows: dict[str, ForumCategory] = {}
        wanted_cat_slugs = set()
        for c in categories:
            slug = _slugify(c["name"])
            wanted_cat_slugs.add(slug)
            existing = (await rds.execute(select(ForumCategory).where(ForumCategory.slug == slug))).scalar_one_or_none()
            if existing:
                existing.name = c["name"]
                existing.description = c.get("description")
                existing.order = int(c.get("order") or 0)
                cat_rows[c["name"]] = existing
            else:
                row = ForumCategory(
                    name=c["name"],
                    slug=slug,
                    description=c.get("description"),
                    order=int(c.get("order") or 0),
                    created_at=now,
                )
                rds.add(row)
                cat_rows[c["name"]] = row
        await rds.commit()

        for row in cat_rows.values():
            await rds.refresh(row)

        for s in subforums:
            cat = cat_rows.get(s["category"])
            if not cat:
                continue
            slug = _sub_slug(s["category"], s["name"])
            existing = (await rds.execute(select(ForumSubforum).where(ForumSubforum.slug == slug))).scalar_one_or_none()
            if existing:
                existing.category_id = cat.id
                existing.name = s["name"]
                existing.description = s.get("description")
                existing.order = int(s.get("order") or 0)
                existing.access_tier = s.get("access_tier", "public")
                existing.is_read_only = bool(s.get("is_read_only", False))
            else:
                rds.add(
                    ForumSubforum(
                        category_id=cat.id,
                        name=s["name"],
                        slug=slug,
                        description=s.get("description"),
                        order=int(s.get("order") or 0),
                        access_tier=s.get("access_tier", "public"),
                        is_read_only=bool(s.get("is_read_only", False)),
                        created_at=now,
                    )
                )
        await rds.commit()

        for row in cat_rows.values():
            await rds.refresh(row)

        await _merge_duplicate_subforums_into_canonical(rds, cat_rows)
        await rds.commit()

        # Reassign threads from any subforum not in the curated list, then remove it (avoid CASCADE data loss).
        fallback_res = await rds.execute(
            select(ForumSubforum).where(ForumSubforum.slug == _sub_slug("Official", "announcements"))
        )
        fallback_sub = fallback_res.scalar_one_or_none()

        async def _first_wanted_subforum_in_category(category_id) -> ForumSubforum | None:
            res = await rds.execute(select(ForumSubforum).where(ForumSubforum.category_id == category_id))
            rows = [x for x in res.scalars().all() if (x.slug or "") in wanted_subforum_slugs]
            if not rows:
                return None
            rows.sort(key=lambda x: (int(x.order or 0), x.name or ""))
            return rows[0]

        while True:
            res = await rds.execute(select(ForumSubforum))
            all_subs = list(res.scalars().all())
            orphan = next((s for s in all_subs if (s.slug or "") not in wanted_subforum_slugs), None)
            if not orphan:
                break
            target = await _first_wanted_subforum_in_category(orphan.category_id)
            target_id = target.id if target else (fallback_sub.id if fallback_sub else None)
            if target_id and target_id != orphan.id:
                await rds.execute(
                    update(ForumThread).where(ForumThread.subforum_id == orphan.id).values(subforum_id=target_id)
                )
            await rds.delete(orphan)
            await rds.flush()
        await rds.commit()

        all_cats = (await rds.execute(select(ForumCategory))).scalars().all()
        for c in all_cats:
            if (c.slug or "") in wanted_cat_slugs:
                continue
            subs_left = (
                await rds.execute(select(ForumSubforum).where(ForumSubforum.category_id == c.id).limit(1))
            ).scalar_one_or_none()
            if subs_left is None:
                await rds.delete(c)
        await rds.commit()

    print("seeded forum v2 categories/subforums on rds (Official, Influencers x3, one board per Maxx)")


if __name__ == "__main__":
    asyncio.run(seed_forums_v3_rds())
