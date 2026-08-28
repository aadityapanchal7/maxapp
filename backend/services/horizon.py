"""
Plan-horizon keeper: a paying customer must NEVER open the app to an empty
week because their schedule's generated window quietly ran out.

Two cases:
  - Native maxes: generated for cadence_days (~14). When the remaining
    runway drops under HORIZON_MIN_DAYS, re-expand via the existing
    regenerate machinery (which preserves task ids/status and re-stamps
    dates from the user's local today).
  - Creator courses: built from schedule_hints for 14 days at a time. Extend
    in 14-day chunks until the course's purchased duration (weeks) is used
    up; after that the program is complete (no zombie sessions forever).

Runs lazily from /planner/today (at most once per user per local day,
tracked in reflow_state) and from the 30-min scheduler tick as a backstop.
Best-effort by contract: a horizon failure must never break Today.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from models.sqlalchemy_models import User, UserSchedule

logger = logging.getLogger(__name__)

HORIZON_MIN_DAYS = 5      # extend when fewer than this many days remain
COURSE_CHUNK_DAYS = 14


def _last_date(days: list[dict]) -> date | None:
    best: date | None = None
    for d in days or []:
        try:
            cur = date.fromisoformat(str(d.get("date")))
        except (TypeError, ValueError):
            continue
        if best is None or cur > best:
            best = cur
    return best


def _course_total_days(sched: UserSchedule, course: dict | None) -> int:
    weeks = int((course or {}).get("weeks") or 0)
    if weeks <= 0:
        return 10 * 365  # weekly-forever programs: no hard end
    return weeks * 7


async def ensure_plan_horizon(user: User, db: AsyncSession) -> dict[str, int]:
    """Extend every active schedule whose runway is about to run out."""
    from api.marketplace import _SEED_COURSES
    from services.schedule_skeleton import has_skeleton
    from services.schedule_streak import local_today_date

    ob = dict(user.onboarding or {})
    today = local_today_date(ob)
    out = {"native_regens": 0, "course_extensions": 0, "completed_courses": 0}

    # One fetch shared by every course extension below (native regens get their
    # own inside regenerate_active_schedules).
    from services.calendar_busy import calendar_busy_by_date as _cal_fetch
    _horizon_busy = await _cal_fetch(
        user.id, today, today + timedelta(days=HORIZON_MIN_DAYS + COURSE_CHUNK_DAYS + 7), db
    )

    rows = list((await db.execute(
        select(UserSchedule).where(
            (UserSchedule.user_id == user.id) & (UserSchedule.is_active.is_(True))
        )
    )).scalars().all())

    regen_targets: list[str] = []
    for sched in rows:
        last = _last_date(sched.days or [])
        if last is None or (last - today).days >= HORIZON_MIN_DAYS:
            continue

        if sched.schedule_type == "course" or str(sched.maxx_id or "").startswith("course_"):
            course = next(
                (c for c in _SEED_COURSES if c["id"] == sched.maxx_id), None
            )
            started = None
            for d in sched.days or []:
                try:
                    cur = date.fromisoformat(str(d.get("date")))
                except (TypeError, ValueError):
                    continue
                started = cur if started is None or cur < started else started
            elapsed = ((last - started).days + 1) if (started and last) else 0
            total = _course_total_days(sched, course)
            if elapsed >= total:
                # The purchased program genuinely finished. Close it out
                # cleanly instead of generating zombie sessions forever.
                sched.is_active = False
                sched.updated_at = datetime.utcnow()
                out["completed_courses"] += 1
                continue
            remaining = min(COURSE_CHUNK_DAYS, total - elapsed)
            try:
                appended = _extend_course_days(
                    sched, course, ob, start=last + timedelta(days=1),
                    n_days=remaining,
                    calendar_busy_by_date=_horizon_busy,
                )
                if appended:
                    flag_modified(sched, "days")
                    sched.updated_at = datetime.utcnow()
                    out["course_extensions"] += 1
            except Exception as e:
                logger.warning("course horizon extend failed (non-fatal): %s", e)
        elif has_skeleton(sched.maxx_id or ""):
            regen_targets.append(sched.maxx_id or "")

    if regen_targets:
        try:
            from services.schedule_runtime import regenerate_active_schedules
            for mid in regen_targets:
                await regenerate_active_schedules(
                    user_id=str(user.id), db=db, only_max=mid,
                    reason="horizon_extension",
                )
                out["native_regens"] += 1
        except Exception as e:
            logger.warning("native horizon regen failed (non-fatal): %s", e)

    await db.commit()

    # Course-day extensions append days without going through the runtime
    # engines, so they need their own nudge for the mirror to follow.
    try:
        from services.gcal_mirror import kick_gcal_mirror
        kick_gcal_mirror(str(user.id))
    except Exception:
        pass

    return out


def _extend_course_days(
    sched: UserSchedule, course: dict | None, ob: dict, *, start: date, n_days: int,
    calendar_busy_by_date: dict | None = None,
) -> int:
    """Append the next chunk of course session days, same placement logic the
    initial build used (workout window, protected spans, friendly grid)."""
    from services.human_time import (
        friendly_time,
        life_windows,
        nudge_out_of_protected,
        resolve_workout_window,
        why_line,
    )
    from services.schedule_validator import (
        _busy_intervals_from_ctx,
        _calendar_busy_for_date,
        _effective_day_ctx,
        _WEEKDAY_NAMES,
    )
    from services.task_fields import normalize_days
    from services.user_context_service import merged_user_state

    if course is None:
        return 0
    hints = course.get("schedule_hints") or {}
    sessions_per_week = max(1, min(7, int(hints.get("sessions_per_week") or 3)))
    minutes = max(5, int(hints.get("minutes") or 20))
    stride = 7 / sessions_per_week
    session_offsets = sorted({int(i * stride) for i in range(sessions_per_week)})

    state = merged_user_state(ob, None)
    g_wake = str(state.get("wake_time") or "07:00")
    g_sleep = str(state.get("sleep_time") or "23:00")
    handle = (course.get("creator") or {}).get("handle") or "creator"
    item_id = course["id"]

    days = list(sched.days or [])
    # Continue the weekly session pattern from the schedule's original start.
    started = None
    for d in days:
        try:
            cur = date.fromisoformat(str(d.get("date")))
            started = cur if started is None or cur < started else started
        except (TypeError, ValueError):
            continue
    if started is None:
        started = start

    appended = 0
    for i in range(n_days):
        d = start + timedelta(days=i)
        day_offset = (d - started).days
        tasks: list[dict] = []
        if (day_offset % 7) in session_offsets:
            wd = _WEEKDAY_NAMES[d.weekday()]
            eff = _effective_day_ctx(state, wd, global_wake=g_wake, global_sleep=g_sleep)
            day_state = {**state, **{k: v for k, v in eff.items() if v is not None}}
            w = life_windows(day_state)
            # Weekly obligations + this DATE's real calendar events, so a
            # course session lands in a genuine gap rather than mid-meeting.
            busy = sorted(
                _busy_intervals_from_ctx(eff)
                + _calendar_busy_for_date(
                    {"calendar_busy_by_date": calendar_busy_by_date or {}}, d.isoformat()
                )
            )
            win_lo, win_hi = resolve_workout_window(day_state)
            cursor = win_lo
            slot = None
            for bs, be in busy:
                if be <= cursor:
                    continue
                if bs - cursor >= minutes:
                    break
                cursor = max(cursor, be + 10)
            if cursor + minutes <= win_hi:
                slot = friendly_time(nudge_out_of_protected(cursor, w, minutes))
            if slot is not None:
                tasks.append({
                    "task_id": f"{item_id}-{d.isoformat()}",
                    "catalog_id": f"{item_id}.session",
                    "title": f"{course['title']} session",
                    "why": why_line(slot % 1440, w),
                    "description": f"Today's session. From {course['title']} by @{handle}.",
                    "time": f"{slot // 60:02d}:{slot % 60:02d}",
                    "duration_min": minutes,
                    "task_type": "routine",
                    "status": "pending",
                    "importance": 5,
                    "task_kind": "fixed",
                    "tags": ["workout"] if course.get("category") == "fitmax" else [],
                    "provenance": {"program_id": item_id, "creator_handle": handle},
                })
        days.append({"date": d.isoformat(), "tasks": tasks})
        appended += 1

    normalize_days(days, item_id)
    sched.days = days
    return appended
