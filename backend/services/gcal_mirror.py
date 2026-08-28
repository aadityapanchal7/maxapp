"""Mirror the user's Max routine into a dedicated Google calendar.

Three promises drive every decision here:

  1. The calendar shows the routine at its real times.
  2. It follows the app — edit a task, the event moves.
  3. Never a duplicate, never two Max events on top of each other.

How duplicates are made impossible
----------------------------------
Every mirrored task gets an `event_key` = uuid5 of
`(user, program, catalog_id, date)`, and the Google event id IS that key's hex.
So identity is derived from what the task *is*, not from a row id:

  * `task_id` is a fresh uuid4 on every expansion — useless as a key.
  * `task_uuid` is keyed on `day_index`, and day 0 re-anchors to "today" on
    every regeneration, so the same uuid points at a different date tomorrow.

Because Google's id is derived, a retried or raced insert collides with itself
(409) instead of creating a second event, even if our own link table were wiped.
The DB unique constraint is the second layer; the per-user single-flight is the
third.

How overlaps are made impossible
--------------------------------
Desired state comes only from `build_master_view`, the one layer that has run
the cross-module collision pass — the persisted `UserSchedule.days` have NOT.
A defensive clamp then truncates any event that would still overrun the next.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import date as _date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from config import settings

logger = logging.getLogger(__name__)

# Fixed namespace — changing it would orphan every event already mirrored.
_EVENT_NS = uuid.UUID("6f4a1c58-6f9c-5c3a-9a3f-2d1b7c4e88a1")

MIRROR_WINDOW_DAYS = 14

# A task timed before this belongs to the previous evening's routine, so it
# renders on the NEXT calendar date. Deliberately a fixed clock hour rather than
# "before wake_time": a user who hand-moves a task to 06:00 with an 07:00 wake
# should still see it on the day it was scheduled, not the day before.
_OVERNIGHT_CUTOFF_MIN = 4 * 60

_DONE_PREFIX = "✓ "

# Single-flight + coalescing state. A kick that lands while a run is in flight
# marks the user dirty rather than starting a second reconcile.
_in_flight: set[str] = set()
_dirty: set[str] = set()


# --------------------------------------------------------------------------- #
#  Identity + change detection                                                 #
# --------------------------------------------------------------------------- #

def _task_identity(task: dict) -> str:
    """The stable logical identity of a task, independent of any row id."""
    cid = task.get("catalog_id")
    if cid:
        return str(cid)
    from services.task_guide_service import _normalise_key
    return _normalise_key(str(task.get("title") or "task"), task.get("maxx_id"))


def event_key(user_id: str, task: dict, date_iso: str, occurrence: int = 1) -> uuid.UUID:
    """uuid5 over (user, program, task identity, date).

    `occurrence` disambiguates a task the plan legitimately schedules twice in
    one day (an AM and a PM skincare block share a catalog_id).
    """
    prov = task.get("provenance") or {}
    program = prov.get("program_id") or task.get("maxx_id") or "max"
    ident = _task_identity(task)
    suffix = "" if occurrence <= 1 else f":{occurrence}"
    return uuid.uuid5(_EVENT_NS, f"{user_id}:{program}:{ident}:{date_iso}{suffix}")


def fingerprint(*, title: str, date_iso: str, time_str: str,
                duration_min: int, tz_name: str) -> str:
    """Digest of everything the user would SEE on the event.

    Rendered title is hashed (not raw), so a task flipping to completed — which
    only changes the ✓ prefix — is correctly detected as a change worth pushing.
    """
    return hashlib.sha256(json.dumps(
        [title, date_iso, time_str, int(duration_min), tz_name]
    ).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
#  Desired state                                                               #
# --------------------------------------------------------------------------- #

class DesiredEvent:
    __slots__ = ("key", "title", "date_iso", "start_local", "end_local",
                 "tz_name", "fingerprint", "event_date")

    def __init__(self, key, title, date_iso, start_local, end_local, tz_name, fp, event_date):
        self.key, self.title, self.date_iso = key, title, date_iso
        self.start_local, self.end_local = start_local, end_local
        self.tz_name, self.fingerprint, self.event_date = tz_name, fp, event_date


def _hhmm(m: int) -> str:
    m = max(0, min(24 * 60 - 1, int(m)))
    return f"{m // 60:02d}:{m % 60:02d}"


def build_desired(view: list[dict], user_id: str, tz_name: str) -> dict[str, DesiredEvent]:
    """Turn a master view window into {event_id_hex: DesiredEvent}."""
    from services.schedule_validator import _parse_time_field

    desired: dict[str, DesiredEvent] = {}
    for day in view or []:
        date_iso = str(day.get("date") or "")
        if not date_iso:
            continue
        tasks = [t for t in (day.get("tasks") or []) if t]
        # Skipped tasks are deliberately absent from desired state, so the diff
        # deletes their event — the calendar shouldn't claim you're doing
        # something you already said you're not.
        tasks = [t for t in tasks if str(t.get("status") or "") != "skipped"]
        if not tasks:
            continue

        rows: list[tuple[int, int, dict]] = []
        for t in tasks:
            start = _parse_time_field(t.get("time"))
            if start is None:
                continue
            dur = max(1, int(t.get("duration_min") or t.get("duration_minutes") or 15))
            rows.append((start, dur, t))
        rows.sort(key=lambda r: r[0])

        # Defensive clamp: the master view is already collision-resolved, but a
        # malformed duration must never produce two overlapping Max events.
        for i, (start, dur, _t) in enumerate(rows):
            if i + 1 < len(rows):
                next_start = rows[i + 1][0]
                if start + dur > next_start:
                    dur = max(5, next_start - start)
                    rows[i] = (start, dur, _t)

        seen_ident: dict[str, int] = {}
        for start, dur, t in rows:
            ident = _task_identity(t)
            occurrence = seen_ident.get(ident, 0) + 1
            seen_ident[ident] = occurrence

            # Overnight tasks render on the following calendar date.
            base = _date.fromisoformat(date_iso)
            event_date = base + timedelta(days=1) if start < _OVERNIGHT_CUTOFF_MIN else base
            ev_iso = event_date.isoformat()

            title = str(t.get("title") or "Max task")
            if str(t.get("status") or "") == "completed":
                title = _DONE_PREFIX + title

            end_min = min(start + dur, 24 * 60 - 1)
            key = event_key(user_id, t, date_iso, occurrence)
            desired[key.hex] = DesiredEvent(
                key=key,
                title=title,
                date_iso=date_iso,
                start_local=f"{ev_iso}T{_hhmm(start)}:00",
                end_local=f"{ev_iso}T{_hhmm(end_min)}:00",
                tz_name=tz_name,
                fp=fingerprint(title=title, date_iso=ev_iso, time_str=_hhmm(start),
                               duration_min=dur, tz_name=tz_name),
                event_date=event_date,
            )
    return desired


def diff_desired_vs_links(
    desired: dict[str, DesiredEvent],
    links: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    """(inserts, patches, deletes) by event id hex.

    Patches fire only when the fingerprint moved, which is what keeps a steady
    state free: the reconcile runs ~48x/day per user and normally sends nothing.
    """
    inserts = [k for k in desired if k not in links]
    patches = [k for k in desired if k in links and links[k].fingerprint != desired[k].fingerprint]
    deletes = [k for k in links if k not in desired]
    return inserts, patches, deletes


# --------------------------------------------------------------------------- #
#  The reconcile                                                               #
# --------------------------------------------------------------------------- #

async def mirror_user_calendar(user_id: str, db) -> dict[str, int]:
    """Bring the user's Max calendar in line with their plan."""
    from models.sqlalchemy_models import CalendarConnection, GcalEventLink, User
    from services.gcal_write import (
        BatchOp, GcalAuthExpired, GcalRateLimited,
        create_calendar, event_body, execute_batch,
    )
    from services.google_integration import SCOPE_CALENDAR_APP, _fresh_access_token
    from services.master_schedule import build_master_view
    from services.schedule_streak import _user_tz, local_today_date

    if not getattr(settings, "gcal_write_enabled", False):
        return {"skipped": 1}

    uid = str(user_id)
    conn = (await db.execute(
        select(CalendarConnection).where(
            (CalendarConnection.user_id == uid)
            & (CalendarConnection.provider == "google")
            & (CalendarConnection.is_active.is_(True))
        )
    )).scalars().first()
    if conn is None:
        return {"not_connected": 1}

    tokens = conn.tokens_decrypted or {}
    if SCOPE_CALENDAR_APP not in str(tokens.get("scope") or ""):
        # Connected read-only: the user hasn't granted write access yet.
        return {"needs_scope": 1}

    user = await db.get(User, uid)
    if user is None:
        return {"no_user": 1}
    ob = dict(user.onboarding or {})
    if not (user.profile or {}).get("gcal_routine_sync"):
        return {"not_opted_in": 1}

    access = await _fresh_access_token(conn, db)
    if not access:
        conn.is_active = False
        await db.commit()
        return {"needs_reconnect": 1}

    tz = _user_tz(ob)
    tz_name = getattr(tz, "key", None) or "UTC"
    today = local_today_date(ob)

    # Always anchor on the USER's today. build_master_view defaults to the
    # server's UTC date, which is already tomorrow for an evening-US user.
    view = await build_master_view(
        uid, db, days=MIRROR_WINDOW_DAYS, today_iso=today.isoformat()
    )
    desired = build_desired(view, uid, tz_name)

    link_rows = (await db.execute(
        select(GcalEventLink).where(
            (GcalEventLink.user_id == uid) & (GcalEventLink.event_date >= today)
        )
    )).scalars().all()
    links = {r.gcal_event_id: r for r in link_rows}

    inserts, patches, deletes = diff_desired_vs_links(desired, links)

    if not (inserts or patches or deletes):
        await _prune_past_links(db, uid, today)
        return {"noop": 1}

    cal_id = conn.app_calendar_id
    if not cal_id:
        cal_id = await create_calendar(access, tz_name=tz_name)
        if not cal_id:
            return {"calendar_create_failed": 1}
        conn.app_calendar_id = cal_id
        await db.commit()

    ops: list[BatchOp] = []
    for k in inserts:
        d = desired[k]
        ops.append(BatchOp("POST", f"/calendar/v3/calendars/{cal_id}/events",
                           event_body(event_id=k, title=d.title, start_local=d.start_local,
                                      end_local=d.end_local, tz_name=tz_name, event_key=k), k))
    for k in patches:
        d = desired[k]
        ops.append(BatchOp("PATCH", f"/calendar/v3/calendars/{cal_id}/events/{k}",
                           event_body(event_id="", title=d.title, start_local=d.start_local,
                                      end_local=d.end_local, tz_name=tz_name, event_key=k), k))
    for k in deletes:
        ops.append(BatchOp("DELETE", f"/calendar/v3/calendars/{cal_id}/events/{k}", None, k))

    try:
        results = await execute_batch(access, ops)
    except GcalAuthExpired:
        conn.is_active = False
        await db.commit()
        return {"needs_reconnect": 1}
    except GcalRateLimited:
        # Abandon this run; the periodic job retries.
        return {"rate_limited": 1}

    # An insert that 409s means the event id already exists (a retry, or a link
    # row we lost). Update it in place rather than creating a twin.
    retry: list[BatchOp] = []
    for k in inserts:
        status = (results.get(k) or (0, {}))[0]
        if status == 409:
            d = desired[k]
            body = event_body(event_id=k, title=d.title, start_local=d.start_local,
                              end_local=d.end_local, tz_name=tz_name, event_key=k)
            body["status"] = "confirmed"  # resurrect if the user had deleted it
            retry.append(BatchOp("PUT", f"/calendar/v3/calendars/{cal_id}/events/{k}", body, k))
    if retry:
        try:
            results.update(await execute_batch(access, retry))
        except (GcalAuthExpired, GcalRateLimited):
            pass

    now = datetime.utcnow()
    applied = {"inserted": 0, "patched": 0, "deleted": 0}

    for k in inserts:
        status = (results.get(k) or (0, {}))[0]
        if status not in (200, 201, 409):
            continue
        d = desired[k]
        db.add(GcalEventLink(
            user_id=uid, event_key=d.key, gcal_calendar_id=cal_id, gcal_event_id=k,
            event_date=d.event_date, fingerprint=d.fingerprint, last_pushed_at=now,
        ))
        applied["inserted"] += 1

    for k in patches:
        status = (results.get(k) or (0, {}))[0]
        if status not in (200, 201):
            continue
        d = desired[k]
        row = links[k]
        row.fingerprint = d.fingerprint
        row.event_date = d.event_date
        row.last_pushed_at = now
        applied["patched"] += 1

    for k in deletes:
        status = (results.get(k) or (0, {}))[0]
        if status not in (200, 204, 404, 410):
            continue
        await db.delete(links[k])
        applied["deleted"] += 1

    await _prune_past_links(db, uid, today)
    await db.commit()
    return applied


async def _prune_past_links(db, uid: str, today: _date) -> None:
    """Forget links for days gone by.

    The Google events themselves are deliberately left alone — they're the
    user's record of what their week actually looked like, and deleting history
    would cost API calls to destroy something useful.
    """
    from models.sqlalchemy_models import GcalEventLink
    from sqlalchemy import delete as _delete
    await db.execute(
        _delete(GcalEventLink).where(
            (GcalEventLink.user_id == uid) & (GcalEventLink.event_date < today)
        )
    )


async def teardown_mirror(user_id: str, conn, access_token: str | None, db) -> None:
    """Remove the Max calendar and forget every link. Best-effort throughout."""
    from models.sqlalchemy_models import GcalEventLink
    from sqlalchemy import delete as _delete
    from services.gcal_write import delete_calendar

    try:
        if access_token and getattr(conn, "app_calendar_id", None):
            await delete_calendar(access_token, conn.app_calendar_id)
    except Exception as e:
        logger.warning("gcal teardown: calendar delete failed: %s", e)
    try:
        await db.execute(_delete(GcalEventLink).where(GcalEventLink.user_id == str(user_id)))
        if conn is not None:
            conn.app_calendar_id = None
    except Exception as e:
        logger.warning("gcal teardown: link purge failed: %s", e)


# --------------------------------------------------------------------------- #
#  Trigger                                                                     #
# --------------------------------------------------------------------------- #

def kick_gcal_mirror(user_id: str, *, delay: float = 5.0) -> None:
    """Schedule a reconcile shortly after the caller's transaction lands.

    The delay does two jobs. It coalesces bursts — a chat-driven regeneration
    calls into the engine once per active program, and we want one reconcile,
    not three. And it steps around ownership of the transaction: the schedule
    engines only `flush()`, leaving the commit to their caller, so reading the
    plan immediately could see pre-commit state. By the time this runs, the
    request has committed and the worker opens its own session.

    Never raises: a calendar problem must not fail the user's actual request.
    """
    if not getattr(settings, "gcal_write_enabled", False):
        return
    uid = str(user_id)
    if uid in _in_flight:
        _dirty.add(uid)   # a change landed mid-run; go around again
        return
    _in_flight.add(uid)

    async def _run() -> None:
        from db.sqlalchemy import AsyncSessionLocal
        try:
            await asyncio.sleep(delay)
            while True:
                _dirty.discard(uid)
                try:
                    async with AsyncSessionLocal() as db:
                        await mirror_user_calendar(uid, db)
                except Exception:
                    logger.exception("gcal mirror failed for %s", uid)
                if uid not in _dirty:
                    break
        finally:
            _in_flight.discard(uid)

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        # No loop (sync caller / tests) — drop the claim rather than stranding it.
        _in_flight.discard(uid)
