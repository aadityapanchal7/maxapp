"""Glue: new schedule_generator + schedule_adapter ⇄ existing UserSchedule persistence.

Replaces the body of `services.schedule_service.generate_maxx_schedule`
and `adapt_schedule` for the new doc-driven path. Reuses the legacy
`_enforce_schedule_limit` and the `UserSchedule` ORM row so push
notifications, completion stats, course wiring etc all keep working.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.sqlalchemy_models import User, UserSchedule
from services.multi_module_collision import reconcile_schedules
from services.schedule_adapter import adapt_schedule as _adapt
from services.schedule_generator import generate_schedule as _generate
from services.task_catalog_service import get_doc, missing_required, warm_catalog, is_loaded
from services.user_context_service import get_context, merged_user_state

logger = logging.getLogger(__name__)


class ScheduleLimitError(Exception):
    def __init__(self, active_labels: list[str]):
        self.active_labels = active_labels
        super().__init__(f"schedule limit reached: {active_labels}")


async def _enforce_active_schedule_limit(
    *, user_id: str, db: AsyncSession, replacing_maxx_id: str, subscription_tier: str | None,
    cap: int = 2,
) -> None:
    """Allow up to `cap` active schedules. If at cap and not replacing one
    of them, raise ScheduleLimitError. (Legacy schedule_service has its own
    tier-aware version — this is a simpler fallback.)"""
    user_uuid = UUID(user_id)
    res = await db.execute(
        select(UserSchedule).where(
            (UserSchedule.user_id == user_uuid) & (UserSchedule.is_active.is_(True))
        )
    )
    actives = res.scalars().all()
    other = [s for s in actives if (s.maxx_id or "") != replacing_maxx_id]
    if len(other) >= cap:
        raise ScheduleLimitError([s.maxx_id or "?" for s in other])


async def generate_and_persist(
    *,
    user_id: str,
    maxx_id: str,
    db: AsyncSession,
    onboarding: dict | None = None,
    wake_time: str = "07:00",
    sleep_time: str = "23:00",
    subscription_tier: str | None = None,
) -> dict:
    """Run the new generator and persist as UserSchedule. Returns a dict
    matching the shape lc_agent expects (id, maxx_id, course_title, days)."""
    if not is_loaded():
        await warm_catalog()

    user_uuid = UUID(user_id)
    user = await db.get(User, user_uuid)
    if user is None:
        raise ValueError(f"user {user_id} not found")

    # Limit check before LLM call.
    await _enforce_active_schedule_limit(
        user_id=user_id, db=db, replacing_maxx_id=maxx_id, subscription_tier=subscription_tier,
    )

    extras = {"wake_time": wake_time, "sleep_time": sleep_time}
    result = await _generate(
        user_id=user_id, maxx_id=maxx_id, db=db,
        onboarding=onboarding or dict(user.onboarding or {}),
        extras=extras,
    )
    if not result.ok:
        if result.missing_fields:
            qs = ", ".join(f.get("id", "?") for f in result.missing_fields[:3])
            raise ValueError(f"missing required fields: {qs}")
        raise ValueError(result.errors[0].get("message") if result.errors else "generation failed")

    # Multi-module collision pass against any other ACTIVE schedule the user has.
    days = result.days
    other_actives = await _load_other_active_days(user_uuid, db, except_maxx=maxx_id)
    if other_actives:
        bundle = {**other_actives, maxx_id: days}
        bundle = reconcile_schedules(bundle)
        days = bundle[maxx_id]
        # Persist tweaks made to other modules (collision moved/dropped tasks).
        for other_max, other_days in bundle.items():
            if other_max == maxx_id:
                continue
            await _update_active_days(user_uuid, db, maxx_id=other_max, days=other_days)

    # Deactivate any prior active schedule for this same maxx_id.
    res = await db.execute(
        select(UserSchedule).where(
            (UserSchedule.user_id == user_uuid)
            & (UserSchedule.maxx_id == maxx_id)
            & (UserSchedule.is_active.is_(True))
        )
    )
    for prior in res.scalars().all():
        prior.is_active = False
        prior.updated_at = datetime.utcnow()

    doc = get_doc(maxx_id)
    course_title = (doc.display_name if doc else maxx_id) + " Plan"

    schedule_row = UserSchedule(
        user_id=user_uuid,
        schedule_type="maxx",
        maxx_id=maxx_id,
        course_title=course_title,
        days=days,
        preferences={"wake_time": wake_time, "sleep_time": sleep_time},
        schedule_context={"summary": result.summary, "validator_retries": result.validator_retries},
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        adapted_count=0,
        user_feedback=[],
        completion_stats={"completed": 0, "total": 0, "skipped": 0},
    )
    db.add(schedule_row)
    await db.flush()

    await _log_op(
        db,
        user_id=user_uuid,
        schedule_id=schedule_row.id,
        maxx_id=maxx_id,
        op="generate",
        elapsed_ms=result.elapsed_ms,
        task_count=sum(len(d.get("tasks") or []) for d in days),
        validator_retries=result.validator_retries,
    )

    return {
        "id": str(schedule_row.id),
        "maxx_id": maxx_id,
        "course_title": course_title,
        "days": days,
        "summary": result.summary,
    }


async def adapt_and_persist(
    *,
    user_id: str,
    schedule_id: str,
    db: AsyncSession,
    feedback: str,
) -> dict:
    """Apply diff-format adapt and persist."""
    user_uuid = UUID(user_id)
    sched_uuid = UUID(schedule_id)
    schedule_row = (await db.execute(
        select(UserSchedule).where(
            (UserSchedule.id == sched_uuid) & (UserSchedule.user_id == user_uuid)
        )
    )).scalar_one_or_none()
    if schedule_row is None:
        raise ValueError("Schedule not found")

    if not is_loaded():
        await warm_catalog()

    user = await db.get(User, user_uuid)
    onboarding = dict(user.onboarding or {}) if user else {}
    prefs = dict(schedule_row.preferences or {})
    wake = prefs.get("wake_time") or "07:00"
    sleep = prefs.get("sleep_time") or "23:00"

    result = await _adapt(
        user_id=user_id,
        schedule_id=schedule_id,
        maxx_id=schedule_row.maxx_id or "",
        days=list(schedule_row.days or []),
        feedback=feedback,
        db=db,
        onboarding=onboarding,
        wake_time=wake,
        sleep_time=sleep,
    )

    schedule_row.days = result.days
    schedule_row.adapted_count = (schedule_row.adapted_count or 0) + 1
    fb_log = list(schedule_row.user_feedback or [])
    fb_log.append({"date": datetime.utcnow().isoformat(), "feedback": feedback, "summary": result.summary})
    schedule_row.user_feedback = fb_log
    schedule_row.updated_at = datetime.utcnow()
    await db.flush()

    await _log_op(
        db,
        user_id=user_uuid,
        schedule_id=schedule_row.id,
        maxx_id=schedule_row.maxx_id or "",
        op="adapt",
        elapsed_ms=result.elapsed_ms,
        task_count=sum(len(d.get("tasks") or []) for d in result.days),
        validator_retries=0,
        feedback=feedback,
        diff_ops=result.ops_applied,
    )

    return {
        "id": str(schedule_row.id),
        "maxx_id": schedule_row.maxx_id,
        "days": result.days,
        "summary": result.summary,
        "ops_applied": result.ops_applied,
        "context_updates": result.context_updates,
        "changes_summary": result.summary,
    }


async def _load_other_active_days(user_uuid: UUID, db: AsyncSession, *, except_maxx: str) -> dict[str, list[dict]]:
    res = await db.execute(
        select(UserSchedule).where(
            (UserSchedule.user_id == user_uuid)
            & (UserSchedule.is_active.is_(True))
        )
    )
    out: dict[str, list[dict]] = {}
    for row in res.scalars().all():
        if (row.maxx_id or "") == except_maxx:
            continue
        if row.days:
            out[row.maxx_id] = list(row.days)
    return out


async def _update_active_days(user_uuid: UUID, db: AsyncSession, *, maxx_id: str, days: list[dict]) -> None:
    res = await db.execute(
        select(UserSchedule).where(
            (UserSchedule.user_id == user_uuid)
            & (UserSchedule.maxx_id == maxx_id)
            & (UserSchedule.is_active.is_(True))
        )
    )
    for row in res.scalars().all():
        row.days = days
        row.updated_at = datetime.utcnow()


async def _log_op(
    db: AsyncSession, *,
    user_id: UUID, schedule_id: UUID | None, maxx_id: str, op: str,
    elapsed_ms: int, task_count: int | None, validator_retries: int,
    feedback: str | None = None, diff_ops: Any = None,
) -> None:
    try:
        await db.execute(
            text(
                """
                INSERT INTO schedule_generation_log
                  (user_id, schedule_id, maxx_id, op, elapsed_ms, task_count, validator_retries, feedback, diff_ops)
                VALUES
                  (:uid, :sid, :mid, :op, :ms, :tc, :vr, :fb, CAST(:diff AS jsonb))
                """
            ),
            {
                "uid": user_id, "sid": schedule_id, "mid": maxx_id, "op": op,
                "ms": elapsed_ms, "tc": task_count, "vr": validator_retries,
                "fb": feedback,
                "diff": (None if diff_ops is None else __import__("json").dumps(diff_ops)),
            },
        )
    except Exception as e:
        logger.warning("schedule log insert failed (non-fatal): %s", e)
