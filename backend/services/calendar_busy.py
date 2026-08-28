"""Project the user's real calendar events into schedule-generation busy time.

Until this module existed, generation only knew the busy windows the user typed
during onboarding (work hours, obligations, meals — see
`schedule_validator._busy_intervals_from_ctx`). Their actual Google Calendar was
read, stored in `calendar_events`, rendered on the planner… and then ignored when
the plan was built, so Max would happily place a skincare task on top of a
meeting. `/planner/today` even told the user "Packed calendar. Plan fits around
it." — which was not true. This module makes it true.

Shape of the contract
---------------------
`{iso_date: [{"start": "HH:MM", "end": "HH:MM", "label": "busy"}]}`, injected as
`user_ctx["calendar_busy_by_date"]` and consumed per DATE by the two eviction
passes (`schedule_validator._apply_day_windows`,
`multi_module_collision._evict_busy_windows`) plus the course slot search.

Why per-date and not per-weekday: onboarding obligations recur weekly and are
keyed by weekday; real calendar events are one-off absolute datetimes. They
cannot share `_effective_day_ctx`, whose result is CACHED PER WEEKDAY — feeding
per-date data through it would serve Monday-the-3rd's meetings on
Monday-the-10th.

Privacy: labels are always the literal "busy". Event titles live in
`calendar_events.title` and stay there — `CalendarEvent`'s own docstring
promises they are "never sent to any LLM", and `user_ctx` is serialized into
generation prompts.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date as _date, timedelta as _timedelta
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings

logger = logging.getLogger(__name__)

_DAY_MIN = 24 * 60
_BUSY_LABEL = "busy"


# --------------------------------------------------------------------------- #
#  Max-authored detection (write-mirror echo guard)                            #
# --------------------------------------------------------------------------- #

def _is_max_authored(ev: Any) -> bool:
    """True when this event is one WE wrote into the user's calendar.

    Belt-and-braces. The mirror writes to a dedicated app-created "Max"
    calendar while the ingest reads only `primary`
    (`google_integration.CALENDAR_EVENTS_URL`), so our own events structurally
    never reach `calendar_events` in the first place. If the read path ever
    widens to all calendars, this stops Max's own routine from being re-ingested
    as busy time — which would make the plan collide with itself and shrink a
    little more on every regeneration.
    """
    raw = _get(ev, "raw") or {}
    if isinstance(raw, dict) and raw.get("max_authored"):
        return True
    ext = _get(ev, "external_event_id")
    return bool(ext and str(ext).startswith("max:"))


def _get(ev: Any, key: str) -> Any:
    """Read a field from an ORM row or a plain dict (tests use dicts)."""
    if isinstance(ev, dict):
        return ev.get(key)
    return getattr(ev, key, None)


# --------------------------------------------------------------------------- #
#  Pure projection                                                             #
# --------------------------------------------------------------------------- #

def project_events_to_busy_by_date(
    events: Iterable[Any],
    start: _date,
    end: _date,
) -> dict[str, list[dict]]:
    """Turn calendar rows into per-date busy intervals for [start, end).

    Kept: confirmed, busy, timed events that aren't ours.
    Dropped, each for a reason:
      * `status != "confirmed"` — Gmail-derived "proposed" commitments are
        guesses the user hasn't confirmed, and "dismissed" ones they rejected.
        Neither should silently reshape a plan.
      * `is_busy` false — the user marked it Free in Google; they're telling us
        they're available.
      * `all_day` — an all-day event is usually a label ("Sarah's birthday",
        "Q3 launch"), not 24 hours of unavailability. Blocking on it would evict
        the entire day's routine. The read side already treats these as pills
        and excludes them from `calendar_busy_minutes` (`api/planner.py`); this
        matches. A genuine all-day commitment shows up as its own timed events.

    Multi-day events are split per date and clamped to that date's [00:00,
    24:00), so an overnight flight blocks the tail of one day and the head of
    the next rather than being dropped or overflowing.

    Times are used as stored wall-clock. `google_integration._parse_gcal_time`
    deliberately discards the real UTC offset and stores the local clock face,
    which is the same convention as task `"HH:MM"` strings — so comparing them
    needs no timezone math, and DST shifts stay correct for free.
    """
    out: dict[str, list[dict]] = {}
    for ev in events or []:
        if str(_get(ev, "status") or "confirmed") != "confirmed":
            continue
        if not bool(_get(ev, "is_busy")):
            continue
        if bool(_get(ev, "all_day")):
            continue
        if _is_max_authored(ev):
            continue

        s_dt = _get(ev, "starts_at")
        e_dt = _get(ev, "ends_at")
        if s_dt is None or e_dt is None:
            continue
        try:
            s_dt = s_dt.replace(tzinfo=None)
            e_dt = e_dt.replace(tzinfo=None)
        except Exception:
            continue
        if e_dt <= s_dt:
            continue

        # Walk each calendar date the event touches.
        cur = s_dt.date()
        last = e_dt.date()
        # Guard against absurd spans (a corrupt row shouldn't spin for years).
        if (last - cur).days > 400:
            continue
        while cur <= last:
            if start <= cur < end:
                s_min = 0 if cur > s_dt.date() else s_dt.hour * 60 + s_dt.minute
                if cur < last:
                    e_min = _DAY_MIN
                else:
                    e_min = e_dt.hour * 60 + e_dt.minute
                    # An event ending exactly at midnight belongs to the prior day.
                    if e_min == 0 and cur > s_dt.date():
                        e_min = _DAY_MIN
                if e_min > s_min:
                    out.setdefault(cur.isoformat(), []).append((s_min, min(e_min, _DAY_MIN)))
            cur += _timedelta(days=1)

    # Merge overlaps per date so downstream eviction sees one continuous span
    # for back-to-back meetings instead of stepping through each separately.
    merged: dict[str, list[dict]] = {}
    for iso, spans in out.items():
        spans.sort()
        acc: list[list[int]] = [list(spans[0])]
        for s, e in spans[1:]:
            if s <= acc[-1][1]:
                acc[-1][1] = max(acc[-1][1], e)
            else:
                acc.append([s, e])
        merged[iso] = [
            {"start": _hhmm(s), "end": _hhmm(e), "label": _BUSY_LABEL}
            for s, e in acc
        ]
    return merged


def _hhmm(minute: int) -> str:
    m = max(0, min(_DAY_MIN - 1, int(minute)))
    return f"{m // 60:02d}:{m % 60:02d}"


def busy_fingerprint(events: Iterable[Any], *, horizon_days: int = 35) -> str:
    """Stable digest of the user's real busy time, for drift detection.

    Only the fields that can move a task are hashed (start/end of the events we
    would actually honor), so re-ingesting an unchanged calendar — which happens
    every 30 minutes, and again on every app foreground — produces an identical
    fingerprint and triggers no work. Adding, moving or deleting a real meeting
    changes it.
    """
    keys: list[str] = []
    for ev in events or []:
        if str(_get(ev, "status") or "confirmed") != "confirmed":
            continue
        if not bool(_get(ev, "is_busy")) or bool(_get(ev, "all_day")):
            continue
        if _is_max_authored(ev):
            continue
        s_dt, e_dt = _get(ev, "starts_at"), _get(ev, "ends_at")
        if s_dt is None or e_dt is None:
            continue
        try:
            keys.append(f"{s_dt.replace(tzinfo=None).isoformat()}|{e_dt.replace(tzinfo=None).isoformat()}")
        except Exception:
            continue
    keys.sort()
    return hashlib.sha256(json.dumps(keys).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
#  Post-humanize invariant pass                                                #
# --------------------------------------------------------------------------- #

def apply_calendar_busy(
    days: list[dict],
    busy_by_date: dict[str, list[dict]],
) -> list[dict]:
    """Final guarantee that no task sits on top of a real calendar event.

    The validator already evicts around calendar blocks, but two things happen
    afterwards that don't know about them:

      1. `human_time.humanize_days` grid-snaps and re-spaces every task to look
         natural (+10/+15 minute nudges). It can walk a task back into a meeting.
      2. `multi_module_collision.reconcile_schedules` — which has its own
         calendar-aware eviction — RETURNS EARLY for users with fewer than two
         active programs. Most users have one.

    So without this pass the end-to-end promise would hold only for
    multi-program users. It's a near-no-op when nothing drifted: tasks already
    clear of busy time are left byte-identical.
    """
    if not busy_by_date or not days:
        return days

    from services.schedule_validator import (  # local import: avoids a cycle
        MIN_TASK_GAP_MIN,
        _merge_intervals,
        _overlapping_window,
        _parse_time_field,
    )

    LAST_SLOT = _DAY_MIN - 1
    for day in days:
        iso = str(day.get("date") or "")
        spans = busy_by_date.get(iso)
        tasks = day.get("tasks") or []
        if not spans or not tasks:
            continue

        busy = _merge_intervals([
            (_parse_time_field(b.get("start")) or 0, _parse_time_field(b.get("end")) or 0)
            for b in spans
            if (_parse_time_field(b.get("end")) or 0) > (_parse_time_field(b.get("start")) or 0)
        ])
        if not busy:
            continue

        tasks.sort(key=lambda t: _parse_time_field(t.get("time")) or 0)
        floor = -1
        for t in tasks:
            original = _parse_time_field(t.get("time")) or 0
            dur = max(1, int(t.get("duration_min") or t.get("duration_minutes") or 1))
            start = original
            # Settle against the running floor and the busy spans together —
            # same 8-iteration bound as the validator's pass, so a pathological
            # wall of meetings degrades to a late pile-up instead of looping.
            for _ in range(8):
                moved = False
                if floor >= 0 and start < floor:
                    start, moved = floor, True
                win = _overlapping_window(start, dur, busy)
                if win is not None:
                    start, moved = win[1], True
                if not moved:
                    break
            if start > LAST_SLOT:
                start = LAST_SLOT
            if start != original:
                t["time"] = _hhmm(start)
            floor = start + dur + MIN_TASK_GAP_MIN

        tasks.sort(key=lambda t: _parse_time_field(t.get("time")) or 0)
        day["tasks"] = tasks
    return days


# --------------------------------------------------------------------------- #
#  DB access — the single fetch every caller shares                            #
# --------------------------------------------------------------------------- #

async def fetch_busy_events(
    user_id: UUID | str,
    start: _date,
    end: _date,
    db: AsyncSession,
) -> list[Any]:
    """One indexed SELECT of the events that could block a task in [start, end)."""
    from models.sqlalchemy_models import CalendarEvent

    from datetime import datetime as _dt, time as _time
    win_from = _dt.combine(start, _time.min)
    win_to = _dt.combine(end, _time.min)
    res = await db.execute(
        select(CalendarEvent)
        .where(
            (CalendarEvent.user_id == user_id)
            & (CalendarEvent.is_busy.is_(True))
            & (CalendarEvent.starts_at < win_to)
            & (CalendarEvent.ends_at > win_from)
        )
        .order_by(CalendarEvent.starts_at)
    )
    return list(res.scalars().all())


async def calendar_busy_by_date(
    user_id: UUID | str,
    start: _date,
    end: _date,
    db: AsyncSession,
) -> dict[str, list[dict]]:
    """Busy map for generation. Fails OPEN — a calendar problem must never
    block someone from getting a plan, so every error path returns `{}` and
    generation proceeds exactly as it did before this feature existed.
    """
    if not getattr(settings, "calendar_aware_generation_enabled", True):
        return {}
    try:
        events = await fetch_busy_events(user_id, start, end, db)
        return project_events_to_busy_by_date(events, start, end)
    except Exception as e:  # noqa: BLE001 — deliberately swallow
        logger.warning("calendar_busy_by_date failed for %s: %s", user_id, e)
        return {}
