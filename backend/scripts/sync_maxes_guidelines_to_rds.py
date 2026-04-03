"""
Upsert all maxx program data from services.maxx_guidelines (canonical Python, including
services/fitmax_course_modules.py) into RDS maxes table so the API reads from the database.

Safe to run repeatedly (updates existing rows by id).

Usage:
    cd backend
    python scripts/sync_maxes_guidelines_to_rds.py

Requires AWS RDS env vars (same as app): DATABASE_URL / aws_rds_* in config.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update

from models.rds_models import Maxx
from db.rds import init_rds_db, close_rds_db, RDSSessionLocal
from services.maxx_guidelines import MAXX_GUIDELINES

# Icons/colors for app UI (not in MAXX_GUIDELINES)
DISPLAY: dict[str, dict[str, str]] = {
    "skinmax": {"icon": "sparkles-outline", "color": "#8B5CF6"},
    "hairmax": {"icon": "cut-outline", "color": "#3B82F6"},
    "fitmax": {"icon": "fitness-outline", "color": "#10B981"},
    "heightmax": {"icon": "resize-outline", "color": "#6366F1"},
    "bonemax": {"icon": "body-outline", "color": "#F59E0B"},
}

MAXX_IDS = tuple(DISPLAY.keys())


def json_safe(obj: Any) -> Any:
    """Tuples → lists for JSONB (e.g. BoneMax protocol task_families)."""
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, tuple):
        return [json_safe(x) for x in obj]
    if isinstance(obj, list):
        return [json_safe(x) for x in obj]
    return obj


def row_payload(maxx_id: str) -> dict[str, Any]:
    g = MAXX_GUIDELINES.get(maxx_id) or {}
    meta = DISPLAY[maxx_id]
    return {
        "id": maxx_id,
        "label": g.get("label") or maxx_id,
        "description": g.get("description") or "",
        "icon": meta["icon"],
        "color": meta["color"],
        "modules": json_safe(g.get("modules") or []),
        "protocols": json_safe(g.get("protocols") or {}),
        "schedule_rules": json_safe(g.get("schedule_rules") or {}),
        "concern_mapping": json_safe(g.get("concern_mapping") or {}),
        "concern_question": g.get("concern_question"),
        "concerns": json_safe(g.get("concerns") or []),
        "protocol_prompt_template": g.get("protocol_prompt_template"),
        "is_active": True,
    }


async def sync() -> None:
    await init_rds_db()
    now = datetime.now(timezone.utc)
    try:
        async with RDSSessionLocal() as session:
            for mid in MAXX_IDS:
                data = row_payload(mid)
                result = await session.execute(select(Maxx).where(Maxx.id == mid))
                existing = result.scalar_one_or_none()
                if existing:
                    await session.execute(
                        update(Maxx)
                        .where(Maxx.id == mid)
                        .values(
                            label=data["label"],
                            description=data["description"],
                            icon=data["icon"],
                            color=data["color"],
                            modules=data["modules"],
                            protocols=data["protocols"],
                            schedule_rules=data["schedule_rules"],
                            concern_mapping=data["concern_mapping"],
                            concern_question=data["concern_question"],
                            concerns=data["concerns"],
                            protocol_prompt_template=data["protocol_prompt_template"],
                            is_active=data["is_active"],
                            updated_at=now,
                        )
                    )
                    print(f"Updated {mid} (modules={len(data['modules'])})")
                else:
                    row = Maxx(
                        id=data["id"],
                        label=data["label"],
                        description=data["description"],
                        icon=data["icon"],
                        color=data["color"],
                        modules=data["modules"],
                        protocols=data["protocols"],
                        schedule_rules=data["schedule_rules"],
                        concern_mapping=data["concern_mapping"],
                        concern_question=data["concern_question"],
                        concerns=data["concerns"],
                        protocol_prompt_template=data["protocol_prompt_template"],
                        is_active=data["is_active"],
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(row)
                    print(f"Created {mid} (modules={len(data['modules'])})")
            await session.commit()
    finally:
        await close_rds_db()


if __name__ == "__main__":
    asyncio.run(sync())
