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
    # Stamp ISO dates on each day so the master view + UI calendars work.
    # Day 0 = today, day N = today + N days.
    from datetime import date as _date, timedelta as _td
    today = _date.today()
    for i, d in enumerate(days):
        d["date"] = (today + _td(days=i)).isoformat()
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


async def regenerate_active_schedules(
    *,
    user_id: str,
    db: AsyncSession,
    only_max: Optional[str] = None,
    reason: str = "context_change",
) -> list[dict]:
    """Re-expand every active doc-driven schedule for the user against
    their current onboarding + persistent context.

    Triggered any time the user's wake/sleep, required-field answers, or
    optional context changes — so the schedule reflects the new state
    without the user having to manually regenerate.

    Strategy:
      - For each active UserSchedule whose maxx_id has a doc-driven
        skeleton, expand a fresh `days` array.
      - Diff against the existing days POSITIONALLY by `(day_index,
        catalog_id)`: matching tasks keep their `task_id` and `status`
        (so completed checkmarks survive). New tasks get fresh ids.
        Tasks no longer in the skeleton drop out.
      - Update the row in-place (do NOT deactivate + re-create) so all
        downstream references (notifications, completion logs) stay
        valid.
      - Skip silently for maxes without a skeleton (legacy path).

    Returns a list of `{maxx_id, schedule_id, changed}` summaries.
    """
    from datetime import date as _date, timedelta as _td
    from services.task_catalog_service import get_doc, is_loaded, warm_catalog
    from services.schedule_skeleton import expand_skeleton, has_skeleton
    from services.schedule_validator import validate_and_fix
    from services.user_context_service import get_context, merged_user_state

    if not is_loaded():
        await warm_catalog()

    user_uuid = UUID(user_id)
    user = await db.get(User, user_uuid)
    if user is None:
        return []
    onboarding = dict(getattr(user, "onboarding", {}) or {})
    persistent = await get_context(user_id, db)
    state = merged_user_state(onboarding, persistent)
    wake = str(state.get("wake_time") or "07:00")
    sleep = str(state.get("sleep_time") or "23:00")

    res = await db.execute(
        select(UserSchedule).where(
            (UserSchedule.user_id == user_uuid) & (UserSchedule.is_active.is_(True))
        )
    )
    actives = list(res.scalars().all())

    out: list[dict] = []
    today = _date.today()
    for sched in actives:
        mid = sched.maxx_id or ""
        if only_max and mid != only_max:
            continue
        if not has_skeleton(mid):
            continue
        doc = get_doc(mid)
        if doc is None:
            continue
        sd = doc.schedule_design or {}
        cadence_days = int(sd.get("cadence_days", 14))
        budget = sd.get("daily_task_budget") or [2, 6]

        try:
            new_days = expand_skeleton(
                maxx_id=mid, user_state=state, wake=wake, sleep=sleep,
                cadence_days=cadence_days,
            )
            _, _errs, fixed_new = validate_and_fix(
                maxx_id=mid, days=new_days,
                wake_time=wake, sleep_time=sleep,
                user_ctx=state, expected_day_count=cadence_days,
                daily_task_budget=tuple(budget),
            )
        except Exception as e:
            logger.warning("regen failed for max=%s user=%s: %s", mid, user_id, e)
            continue

        # Stamp dates so master view + UI calendars stay correct.
        for i, d in enumerate(fixed_new):
            d["date"] = (today + _td(days=i)).isoformat()

        merged = _merge_preserving_status(old_days=list(sched.days or []), new_days=fixed_new)
        # Only update if anything actually changed (cheap to compare via
        # the fingerprints we already build; here we just compare lengths
        # + first day's task tuple).
        changed = _days_differ(list(sched.days or []), merged)
        if changed:
            sched.days = merged
            sched.updated_at = datetime.utcnow()
            sched.schedule_context = {
                **(sched.schedule_context or {}),
                "last_regen_reason": reason,
                "last_regen_at": datetime.utcnow().isoformat(),
            }
        out.append({
            "maxx_id": mid,
            "schedule_id": str(sched.id),
            "changed": changed,
        })
    if any(s["changed"] for s in out):
        await db.flush()
    return out


def _merge_preserving_status(*, old_days: list[dict], new_days: list[dict]) -> list[dict]:
    """Positional merge: for each day, keep the matching old task's
    `task_id` and `status` when its `catalog_id` is still present in the
    new skeleton expansion. New tasks get fresh ids. Removed tasks drop."""
    merged: list[dict] = []
    for di, nd in enumerate(new_days):
        od = old_days[di] if di < len(old_days) else {}
        old_by_cid: dict[str, dict] = {}
        for ot in (od.get("tasks") or []):
            cid = ot.get("catalog_id")
            if cid and cid not in old_by_cid:
                old_by_cid[cid] = ot
        new_tasks: list[dict] = []
        for nt in (nd.get("tasks") or []):
            cid = nt.get("catalog_id")
            ot = old_by_cid.get(cid)
            if ot:
                # Preserve identity so notifications + completion stats survive.
                nt["task_id"] = ot.get("task_id") or nt.get("task_id")
                # Preserve user-touched status (completed / skipped). Default
                # to pending for tasks the user never touched.
                ot_status = (ot.get("status") or "pending").lower()
                if ot_status in ("completed", "skipped"):
                    nt["status"] = ot_status
                else:
                    nt["status"] = "pending"
            new_tasks.append(nt)
        merged.append({**nd, "tasks": new_tasks})
    return merged


def _days_differ(a: list[dict], b: list[dict]) -> bool:
    """Cheap structural diff — used to skip a no-op write when state
    didn't actually change anything (e.g. a context merge that didn't
    touch any field the skeleton consults)."""
    if len(a) != len(b):
        return True
    for da, db_ in zip(a, b):
        ta = [(t.get("catalog_id"), t.get("time")) for t in (da.get("tasks") or [])]
        tb = [(t.get("catalog_id"), t.get("time")) for t in (db_.get("tasks") or [])]
        if ta != tb:
            return True
    return False


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
