import asyncio
import re
from datetime import datetime, timezone

from sqlalchemy import select

from db.rds import RDSSessionLocal
from models.rds_models import ForumCategory, ForumSubforum


def _slugify(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:64] or "board"


async def seed_forums_v3_rds():
    now = datetime.now(timezone.utc)

    categories = [
        {"name": "Official", "description": "announcements + rules", "order": 0},
        {"name": "SkinMax", "description": "all skinmax community boards", "order": 1},
        {"name": "HairMax", "description": "all hairmax community boards", "order": 2},
        {"name": "FitMax", "description": "all fitmax community boards", "order": 3},
        {"name": "BoneMax", "description": "all bonemax community boards", "order": 4},
        {"name": "HeightMax", "description": "all heightmax community boards", "order": 5},
    ]

    subforums = [
        {"category": "Official", "name": "announcements", "description": "official updates", "access_tier": "public", "order": 0, "is_read_only": True},
        {"category": "Official", "name": "rules / guidelines", "description": "forum rules and posting guidelines", "access_tier": "public", "order": 1, "is_read_only": True},
    ]

    async with RDSSessionLocal() as rds:
        # Upsert categories by slug/name
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

        # Refresh to get IDs
        for k, row in cat_rows.items():
            await rds.refresh(row)

        # Remove any old categories that are no longer part of the curated set.
        all_cats = (await rds.execute(select(ForumCategory))).scalars().all()
        for c in all_cats:
            if (c.slug or "") not in wanted_cat_slugs:
                await rds.delete(c)
        await rds.commit()

        wanted_subforum_slugs = set()
        for s in subforums:
            cat = cat_rows.get(s["category"])
            if not cat:
                continue
            slug = _slugify(f'{s["category"]}-{s["name"]}')
            wanted_subforum_slugs.add(slug)
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

        # Remove old sample boards; keep only currently-defined boards.
        all_subs = (await rds.execute(select(ForumSubforum))).scalars().all()
        for s in all_subs:
            if (s.slug or "") not in wanted_subforum_slugs:
                await rds.delete(s)
        await rds.commit()

    print("seeded forum v2 categories/subforums on rds")


if __name__ == "__main__":
    asyncio.run(seed_forums_v3_rds())

