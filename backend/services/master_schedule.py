"""Master schedule — consolidated view of all active maxes for one user.

Each `UserSchedule` row already stores `days` as a list of day dicts with
`date` fields stamped at generation time (per `services.schedule_runtime`).
The master view joins all `is_active=true` rows for a user, buckets tasks
by absolute date, runs the cross-module collision pass, and returns a
chronological per-date task list.

Why this is a separate service rather than a fancy SQL query:
- The collision pass needs to consider tasks across ALL modules at the
  same time, with awareness of intensity, duration, and antagonism.
- The dates can shift (when a schedule is regenerated, day_index 0
  re-anchors to "today"), so the union must be recomputed when ANY
  schedule changes.
- The mobile UI consumes a flat per-date list, not nested per-max.

Public API:
    build_master_view(user_id, db, *, days=14, today_iso=None) -> list[dict]
        → [{date, tasks: [{maxx_id, task_id, catalog_id, title, time, ...}]}]

The function does NOT mutate the underlying UserSchedule rows. It's a
read-only consolidation. The collision adjustments here are display-only;
the source-of-truth tasks (and their persisted times) live unchanged in
each module's `UserSchedule.days`.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.sqlalchemy_models import User, UserSchedule
from services.multi_module_collision import reconcile_schedules

logger = logging.getLogger(__name__)


async def build_master_view(
    user_id: str,
    db: AsyncSession,
    *,
    days: int = 14,
    today_iso: Optional[str] = None,
) -> list[dict]:
    """Return a flat per-date master schedule for the user.

    `days` controls the window length (default = 14 days starting today).
    `today_iso` lets callers anchor the window to a specific date (mobile
    can pass its local date in case the server's UTC differs from the
    user's timezone).
    """
    user_uuid = UUID(user_id)

    res = await db.execute(
        select(UserSchedule).where(
            (UserSchedule.user_id == user_uuid)
            & (UserSchedule.is_active.is_(True))
        )
    )
    actives = res.scalars().all()
    if not actives:
        return _empty_window(days, today_iso)

    # 1) Bucket each schedule's days by absolute date. DEEP-copy days AND
    # tasks: the collision pass mutates task dicts (times, deferral_age) and
    # appends held_back entries, and a shallow copy would silently mutate the
    # persisted ORM JSON without flag_modified.
    by_max: dict[str, list[dict]] = {}
    for sched in actives:
        if not sched.maxx_id:
            continue
        clean: list[dict] = []
        for d in (sched.days or []):
            d2 = dict(d)
            tasks2 = []
            for t in (d2.get("tasks") or []):
                t2 = dict(t)
                t2.setdefault("maxx_id", sched.maxx_id)
                t2.setdefault("schedule_id", str(sched.id))
                tasks2.append(t2)
            d2["tasks"] = tasks2
            d2["held_back"] = list(d2.get("held_back") or [])
            clean.append(d2)
        by_max[sched.maxx_id] = clean

    # 2) Run the collision pass WITH the user's context: without it the
    # entitlement-aware protection tiers and paid floor silently turn off at
    # read time (a purchased course's session could be trimmed from the very
    # surface the user sees). Date-keyed alignment inside reconcile handles
    # programs anchored on different start dates.
    user_row = await db.get(User, user_uuid)
    user_ctx = None
    if user_row is not None:
        from services.user_context_service import merged_user_state
        user_ctx = merged_user_state(dict(user_row.onboarding or {}), None)
        # Feed the display merge the user's real calendar too, so the plan the
        # user LOOKS at is repositioned around meetings added since the last
        # regeneration — not just the plan that was persisted.
        try:
            from services.calendar_busy import calendar_busy_by_date
            _view_anchor = _parse_iso(today_iso) or date.today()
            user_ctx["calendar_busy_by_date"] = await calendar_busy_by_date(
                user_uuid, _view_anchor, _view_anchor + timedelta(days=days + 1), db
            )
        except Exception:
            pass
    by_max = reconcile_schedules(by_max, user_ctx=user_ctx)

    # 3) Bucket by date.
    by_date: dict[str, list[dict]] = {}
    for max_id, schedule_days in by_max.items():
        for day in schedule_days:
            day_date = day.get("date") or _infer_date_from_index(day)
            if not day_date:
                continue
            for t in (day.get("tasks") or []):
                t["maxx_id"] = max_id
                by_date.setdefault(str(day_date), []).append(t)

    # 4) Build the final ordered window.
    anchor = _parse_iso(today_iso) or date.today()
    out: list[dict] = []
    for offset in range(days):
        d = anchor + timedelta(days=offset)
        diso = d.isoformat()
        tasks = by_date.get(diso, [])
        # Sort tasks by clock time within the day.
        tasks.sort(key=lambda t: _time_key(t.get("time")))
        out.append({
            "date": diso,
            "weekday": d.strftime("%A"),
            "is_today": (d == date.today()),
            "task_count": len(tasks),
            "tasks": tasks,
        })
    return out


# --------------------------------------------------------------------------- #
#  Helpers                                                                    #
# --------------------------------------------------------------------------- #

def _empty_window(days: int, today_iso: Optional[str]) -> list[dict]:
    anchor = _parse_iso(today_iso) or date.today()
    return [
        {
            "date": (anchor + timedelta(days=i)).isoformat(),
            "weekday": (anchor + timedelta(days=i)).strftime("%A"),
            "is_today": ((anchor + timedelta(days=i)) == date.today()),
            "task_count": 0,
            "tasks": [],
        }
        for i in range(days)
    ]


def _parse_iso(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        try:
            return date.fromisoformat(s)
        except Exception:
            return None


def _infer_date_from_index(day: dict) -> Optional[str]:
    """Fallback when `date` is missing — try `day_index` against an anchor.
    In practice all modern UserSchedule.days entries have `date`; this is
    just defensive."""
    return None


def _time_key(s: Any) -> int:
    if not isinstance(s, str) or ":" not in s:
        return 9999
    try:
        h, m = s.split(":", 1)
        return int(h) * 60 + int(m)
    except ValueError:
        return 9999
