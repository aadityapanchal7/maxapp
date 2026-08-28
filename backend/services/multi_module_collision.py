"""Deterministic multi-module collision pass.

Runs AFTER each module generates its own schedule, BEFORE persistence.
Walks every active schedule for the user and applies these passes:

  1. Identical-task dedupe (skinmax_spf vs another module's spf duplicate)
  2. Adjacent same-time push (5-min separation between any two tasks across modules)
  3. Cross-module antagonism split (microneedle + dermastamp → different days)
  4. Daily total cap enforcement (≤ HARD_CAP across all modules — demote lowest-intensity)
  5. Busy-window eviction (opt-in via user_ctx) — re-place the merged day into
     its FREE intervals so nothing sits inside the user's real work/commitments

The LLM never reasons about this. Cheap and predictable.

Inputs are a dict of module schedules, e.g.:
    { "skinmax": [day, day, ...], "hairmax": [day, ...], "heightmax": [day, ...] }
Outputs the same shape, mutated.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from services.schedule_validator import MIN_TASK_GAP_MIN
from services.schedule_dsl import from_minutes
from services.task_fields import (
    TIER_OPTIONAL,
    normalize_days,
    protection_tier,
)

# Cross-module daily ceiling — a humane SOFT target for the total number of
# tasks summed across all active maxxes. A committed 3-maxx user genuinely has
# a non-negotiable hygiene+training floor (~7 essentials on a training day), so
# a hard "6 and drop the rest" rule would delete their face cleanse to hit an
# arbitrary number. Instead we KEEP every essential and trim only the
# lowest-value OPTIONAL extras down toward this target — never below a small
# allowance, so a busy day still keeps its best non-essential habits.
TARGET_DAILY_TOTAL = 8
# Always keep at least this many high-value optional tasks on a day, even when
# the essential floor alone already meets/exceeds the target — so a heavy day
# isn't reduced to nothing but chores (e.g. keep the retinoid + workout fuel).
MIN_OPTIONAL_KEEP = 2
# Absolute hard ceiling — a real notification-storm guard. Even an all-essential
# day never shows more than this many tasks.
HARD_DAILY_TASK_CAP = 11

logger = logging.getLogger(__name__)


# Cross-module pairs that should never share a day.
_CROSS_ANTAGONISM = {
    frozenset({"skin.dermastamp_pm", "hair.microneedle_pm"}),
    frozenset({"skin.retinoid_pm", "hair.microneedle_pm"}),
}

# (catalog_id_a, catalog_id_b) → keep_a (drop b). For dedup of redundant tasks.
_DEDUP_PAIRS = [
    # If both modules add SPF tasks (e.g. future bonemax/heightmax outdoor), keep skin's.
    ("skin.spf", "height.spf_outdoor"),
]

# Declared-priority → maxx_id. `priority_order` (onboarding) ranks the user's
# focus areas first→last using these tokens; we map each to the maxx module it
# drives so collision passes can favor the user's top maxx. Mirror of the
# frontend PRIORITY_KEYS (mobile/constants/profileLifestyleQuestionnaire.ts).
_PRIORITY_TOKEN_TO_MAXX = {
    "face_structure": "bonemax",
    "skin": "skinmax",
    "hair": "hairmax",
    "body": "fitmax",
    "height": "heightmax",
}
# Rank for any maxx the user didn't rank (or when no priority is declared): sort
# last, so an unranked module yields to a ranked one but ties stay deterministic.
_NO_PRIORITY_RANK = 999


def _priority_declared(user_ctx: dict | None) -> bool:
    """True when the user has a usable declared maxx priority order."""
    return (
        isinstance(user_ctx, dict)
        and isinstance(user_ctx.get("priority_order"), list)
        and len(user_ctx["priority_order"]) > 0
    )


def _maxx_priority_rank(maxx_id: str, user_ctx: dict | None) -> int:
    """Position of `maxx_id` in the user's declared priority (0 = highest).

    Unranked maxxes — or any call with no declared priority — return
    `_NO_PRIORITY_RANK` so callers fall back to their legacy tie-break.
    """
    if not _priority_declared(user_ctx):
        return _NO_PRIORITY_RANK
    for i, tok in enumerate(user_ctx["priority_order"]):  # type: ignore[index]
        if _PRIORITY_TOKEN_TO_MAXX.get(str(tok).strip().lower()) == maxx_id:
            return i
    return _NO_PRIORITY_RANK


# Suppression-ledger reason codes (the user-visible "held back" vocabulary).
REASON_DUPLICATE = "duplicate"
REASON_ANTAGONISM = "moved_conflict"
REASON_DAY_FULL = "day_full"
REASON_DAY_FULL_HARD = "day_full_hard"


def _suppress_task(
    schedules: dict[str, list[dict]],
    maxx_id: str,
    di: int,
    task: dict,
    *,
    reason_code: str,
    beaten_by: str | None = None,
    deferred_to: int | None = None,
) -> None:
    """Remove a task from its day AND write a ledger entry on that day.

    Replaces the old silent _remove_task: every drop is now visible to the
    user via GET /api/planner/held-back ("Held back today" chip). Deferred
    tasks carry an aging counter so a repeatedly-skipped habit rises in
    priority instead of starving forever.
    """
    days = schedules.get(maxx_id) or []
    if di >= len(days):
        return
    tasks = days[di].get("tasks") or []
    days[di]["tasks"] = [t for t in tasks if t is not task]
    entry = {
        "task_uuid": task.get("task_uuid"),
        "catalog_id": task.get("catalog_id"),
        "title": task.get("title"),
        "program_id": maxx_id,
        "reason_code": reason_code,
        "beaten_by": beaten_by,
        "deferred_to": deferred_to,
        "deferral_age": int(task.get("deferral_age") or 0) + 1,
    }
    days[di].setdefault("held_back", []).append(entry)


def _task_sort_uuid(task: dict) -> str:
    """Stable per-task tiebreak - never rely on dict insertion order."""
    return str(task.get("task_uuid") or task.get("catalog_id") or task.get("title") or "")


def _select_optionals_to_keep(
    optionals: list[tuple[str, dict]], slots: int, user_ctx: dict | None
) -> set[int]:
    """Pick which optional tasks survive the daily-cap trim → set of id()s to keep.

    No declared priority → legacy behavior: keep the highest-intensity optionals
    (earliest-first tie-break), identical to the old global sort.

    Declared priority → round-robin across maxxes in priority order, each maxx
    contributing its highest-intensity optional in turn. This keeps the scarce
    slots from being monopolized by whichever maxx happens to own the most
    intense extras, so the user's #1 maxx always gets first pick and a secondary
    maxx still keeps its best habit instead of being wiped out.
    """
    if slots <= 0:
        return set()
    if slots >= len(optionals):
        return {id(t) for _, t in optionals}

    def _intensity_key(item: tuple[str, dict]):
        # Aged (previously-deferred) tasks sort ahead of equal-intensity peers so
        # a habit skipped period after period eventually wins a slot back.
        return (
            -float(item[1].get("intensity") or 0.0),
            -int(item[1].get("deferral_age") or 0),
            _time_to_min(item[1].get("time")),
            _task_sort_uuid(item[1]),
        )

    if not _priority_declared(user_ctx):
        ranked = sorted(optionals, key=_intensity_key)
        return {id(t) for _, t in ranked[:slots]}

    by_maxx: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for m, t in optionals:
        by_maxx[m].append((m, t))
    for m in by_maxx:
        by_maxx[m].sort(key=_intensity_key)
    ordered = sorted(by_maxx.keys(), key=lambda m: (_maxx_priority_rank(m, user_ctx), m))

    keep: set[int] = set()
    cursors = {m: 0 for m in ordered}
    while len(keep) < slots:
        progressed = False
        for m in ordered:
            if len(keep) >= slots:
                break
            if cursors[m] < len(by_maxx[m]):
                keep.add(id(by_maxx[m][cursors[m]][1]))
                cursors[m] += 1
                progressed = True
        if not progressed:
            break
    return keep


def reconcile_schedules(
    schedules: dict[str, list[dict]],
    *,
    user_ctx: dict | None = None,
    start_date: Any = None,
) -> dict[str, list[dict]]:
    """Apply all collision passes. Returns a new dict — does not mutate input.

    When `user_ctx` + `start_date` are supplied, a FINAL busy-window eviction
    runs after the cross-module gap-pack: step 3 densifies the merged morning
    and can shove a routine task (e.g. SPF) one minute into a fixed obligation
    (the 8:15 commute). The per-module validator already cleared obligations,
    but the merge re-packs without that knowledge. The eviction restores it —
    preferring to PULL a spilled task back flush before the obligation (you
    apply SPF *before* leaving) rather than dumping it after work. Omitted args
    → no-op, so the master-view merge and unit tests are unaffected.
    """
    if not schedules or len(schedules) < 2:
        return schedules

    # Canonical task fields (task_uuid, importance, provenance, deferral_age...)
    # so every pass below can rely on them. Additive; legacy keys untouched.
    for maxx_id, days in schedules.items():
        normalize_days(days, maxx_id)

    # DATE-KEYED ALIGNMENT: active schedules are anchored to different start
    # dates (skinmax generated Monday, a course entered Thursday), so a
    # positional index-by-index merge compares tasks on DIFFERENT calendar
    # days - real collisions missed, phantom ones invented. When every day
    # carries a date (production), align all modules onto one shared date
    # axis with empty padding days; pure positional input (unit fixtures,
    # legacy rows) keeps the old behavior.
    from datetime import date as _adate, timedelta as _atd

    all_dated = all(
        all(isinstance(d.get("date"), str) and d.get("date") for d in days)
        for days in schedules.values()
        if days
    )
    aligned_anchor: Any = None
    if all_dated:
        try:
            anchors = {
                m: _adate.fromisoformat(days[0]["date"])
                for m, days in schedules.items() if days
            }
            ends = {
                m: _adate.fromisoformat(days[-1]["date"])
                for m, days in schedules.items() if days
            }
            aligned_anchor = min(anchors.values())
            max_end = max(ends.values())
            for m, days in schedules.items():
                existing = {d["date"]: d for d in days}
                unified: list[dict] = []
                cur = aligned_anchor
                while cur <= max_end:
                    iso = cur.isoformat()
                    if iso in existing:
                        unified.append(existing[iso])
                    else:
                        unified.append({"date": iso, "tasks": [], "_pad": True})
                    cur += _atd(days=1)
                schedules[m] = unified
        except (ValueError, KeyError):
            aligned_anchor = None  # malformed dates -> positional fallback

    # Normalize day count across modules — assume all schedules share length.
    day_count = max(len(d) for d in schedules.values())

    # Index every task by day for cross-module visibility.
    # Per-day list of (maxx_id, task_dict_ref).
    by_day: list[list[tuple[str, dict]]] = [[] for _ in range(day_count)]
    for maxx_id, days in schedules.items():
        for di, day in enumerate(days):
            for t in day.get("tasks") or []:
                by_day[di].append((maxx_id, t))

    # 1) Dedupe identical (catalog_id) across modules — keep the stricter/paid
    # one (highest protection tier wins; stable uuid tiebreak, never dict order).
    for di, items in enumerate(by_day):
        by_cid: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for maxx_id, task in items:
            cid = task.get("catalog_id")
            if cid:
                by_cid[cid].append((maxx_id, task))
        for cid, owners in by_cid.items():
            if len(owners) < 2:
                continue
            owners.sort(
                key=lambda mt: (
                    -protection_tier(mt[0], mt[1], user_ctx),
                    _task_sort_uuid(mt[1]),
                )
            )
            keeper_m, keeper_t = owners[0]
            for m, t in owners[1:]:
                _suppress_task(
                    schedules, m, di, t,
                    reason_code=REASON_DUPLICATE,
                    beaten_by=f"{keeper_m}:{keeper_t.get('title') or cid}",
                )
        for keep_a, drop_b in _DEDUP_PAIRS:
            cids = {t.get("catalog_id"): (m, t) for m, t in items}
            if keep_a in cids and drop_b in cids:
                m, t = cids[drop_b]
                _suppress_task(
                    schedules, m, di, t,
                    reason_code=REASON_DUPLICATE,
                    beaten_by=f"{cids[keep_a][0]}:{keep_a}",
                )

    # Recompute by_day after dedupe.
    by_day = _reindex(schedules, day_count)

    # 2) Cross-module antagonism: split to different days. The LOWER-priority
    # maxx yields its task to another day so the user's top maxx keeps its
    # planned slot. With no declared priority, fall back to moving the
    # alphabetically-second id (legacy, deterministic).
    for di in range(day_count):
        present: dict[str, tuple[str, dict]] = {}
        for maxx_id, t in by_day[di]:
            cid = t.get("catalog_id")
            if cid and cid not in present:
                present[cid] = (maxx_id, t)
        for pair in _CROSS_ANTAGONISM:
            if not pair.issubset(present.keys()):
                continue
            a, b = sorted(pair)
            ma, _ta = present[a]
            mb, tb = present[b]
            ra, rb = _maxx_priority_rank(ma, user_ctx), _maxx_priority_rank(mb, user_ctx)
            # Default (tie / no priority): move b (alphabetically second). If a's
            # maxx outranks b's, that's already what we want; if b's outranks a's,
            # move a instead so the higher-priority maxx keeps its day.
            if rb < ra:
                mover_cid, mover_m, mover_t = a, present[a][0], present[a][1]
            else:
                mover_cid, mover_m, mover_t = b, mb, tb
            target_day = _find_safe_day(by_day, mover_cid, start_after=di)
            if target_day is not None and target_day != di:
                _move_task(schedules, mover_m, di, target_day, mover_t)
                # Ledger: a move is a visible deferral, not a silent reshuffle.
                days_m = schedules.get(mover_m) or []
                if di < len(days_m):
                    days_m[di].setdefault("held_back", []).append({
                        "task_uuid": mover_t.get("task_uuid"),
                        "catalog_id": mover_t.get("catalog_id"),
                        "title": mover_t.get("title"),
                        "program_id": mover_m,
                        "reason_code": REASON_ANTAGONISM,
                        "beaten_by": None,
                        "deferred_to": target_day,
                        "deferral_age": int(mover_t.get("deferral_age") or 0) + 1,
                    })
                    mover_t["deferral_age"] = int(mover_t.get("deferral_age") or 0) + 1
    by_day = _reindex(schedules, day_count)

    # 3) Time-gap enforcement across modules. For overnight sleepers (sleep
    # crosses midnight) sort and walk in minutes-since-wake space, exactly
    # like _evict_busy_windows - otherwise a 00:30 task sorts FIRST in the
    # day and genuinely adjacent 23:55/00:05 tasks read as 24h apart.
    _gap_overnight = False
    _gap_wake = 7 * 60
    if isinstance(user_ctx, dict):
        from services.schedule_dsl import crosses_midnight as _xm, parse_clock as _pc, to_minutes as _tm
        _w_dt = _pc(str(user_ctx.get("wake_time") or "07:00"), "07:00")
        _s_dt = _pc(str(user_ctx.get("sleep_time") or "23:00"), "23:00")
        _gap_overnight = _xm(_w_dt, _s_dt)
        _gap_wake = _tm(_w_dt)

    def _gap_work(clock: int) -> int:
        return (clock - _gap_wake) % (24 * 60) if _gap_overnight else clock

    for di in range(day_count):
        items = sorted(by_day[di], key=lambda x: _gap_work(_time_to_min(x[1].get("time"))))
        last_end = -1
        for maxx_id, task in items:
            t_min = _gap_work(_time_to_min(task.get("time")))
            dur = int(task.get("duration_min") or 1)
            if t_min < last_end + MIN_TASK_GAP_MIN:
                new_t = last_end + MIN_TASK_GAP_MIN
                clock_t = (new_t + _gap_wake) % (24 * 60) if _gap_overnight else new_t
                task["time"] = from_minutes(clock_t).strftime("%H:%M")
                t_min = new_t
            last_end = t_min + dur

    # 4) Daily total ceiling — protection-tier-aware. Tier 2 (purchased/required,
    # native maxx OR creator course alike) is never trimmed while anything of a
    # lower tier survives; tier 1 (native-essential hygiene floor) survives the
    # soft trim; tier 0 optionals are trimmed toward TARGET_DAILY_TOTAL. This
    # replaces the old hardcoded native-tag logic that gave creator courses
    # priority 999 and trimmed their tasks first.
    def _tier(m: str, t: dict) -> int:
        return protection_tier(m, t, user_ctx)

    for di in range(day_count):
        items = list(by_day[di])
        if len(items) <= TARGET_DAILY_TOTAL:
            continue
        protected = [(m, t) for (m, t) in items if _tier(m, t) > TIER_OPTIONAL]
        optionals = [(m, t) for (m, t) in items if _tier(m, t) == TIER_OPTIONAL]

        # How many optionals may stay: enough to reach the target on top of the
        # protected floor, but always at least MIN_OPTIONAL_KEEP so a heavy day
        # keeps its best extras (retinoid, workout fuel) rather than only chores.
        optional_slots = max(MIN_OPTIONAL_KEEP, TARGET_DAILY_TOTAL - len(protected))
        keep_ids = _select_optionals_to_keep(optionals, optional_slots, user_ctx)

        # PAID FLOOR: every purchased program keeps >=1 task on a day it had
        # any, even over budget. If the trim would zero a paid program's day,
        # force-keep its best remaining task (highest importance, uuid tiebreak).
        from services.task_fields import entered_programs as _entered
        paid_programs = _entered(user_ctx)
        surviving_by_program: dict[str, int] = defaultdict(int)
        for m, t in protected:
            surviving_by_program[m] += 1
        for m, t in optionals:
            if id(t) in keep_ids:
                surviving_by_program[m] += 1
        for prog in paid_programs:
            had_any = any(m == prog for m, _ in items)
            if had_any and surviving_by_program.get(prog, 0) == 0:
                candidates = [(m, t) for (m, t) in optionals if m == prog]
                candidates.sort(
                    key=lambda mt: (-int(mt[1].get("importance") or 3), _task_sort_uuid(mt[1]))
                )
                if candidates:
                    keep_ids.add(id(candidates[0][1]))
                    surviving_by_program[prog] += 1

        for maxx_id, task in optionals:
            if id(task) in keep_ids:
                continue
            # REAL deferral, not a silent drop: move the task to the next day
            # that (a) doesn't already run this catalog_id and (b) has cap
            # headroom, and age it so it wins a slot back next time. Only when
            # no day in the window has room does it become a plain drop
            # (deferred_to=None -> "when your day opens up").
            target = None
            cid = task.get("catalog_id")
            for dj in range(di + 1, day_count):
                ids_there = {t.get("catalog_id") for _, t in by_day[dj]}
                if cid and cid in ids_there:
                    continue
                if len(by_day[dj]) >= TARGET_DAILY_TOTAL:
                    continue
                target = dj
                break
            if target is not None:
                _move_task(schedules, maxx_id, di, target, task)
                task["deferral_age"] = int(task.get("deferral_age") or 0) + 1
                by_day[target].append((maxx_id, task))
                days_m = schedules.get(maxx_id) or []
                if di < len(days_m):
                    days_m[di].setdefault("held_back", []).append({
                        "task_uuid": task.get("task_uuid"),
                        "catalog_id": cid,
                        "title": task.get("title"),
                        "program_id": maxx_id,
                        "reason_code": REASON_DAY_FULL,
                        "beaten_by": None,
                        "deferred_to": target,
                        "deferral_age": int(task.get("deferral_age") or 0),
                    })
            else:
                _suppress_task(
                    schedules, maxx_id, di, task,
                    reason_code=REASON_DAY_FULL,
                    deferred_to=None,
                )
            items.remove((maxx_id, task))

        # Absolute storm guard: trim down to the hard ceiling as a last resort.
        # Drop lowest-tier first, then lowest intensity; NEVER drop a tier-2
        # (paid/required) task while anything of a lower tier survives. With no
        # entitlements/priority this collapses to the legacy lowest-intensity cut.
        if len(items) > HARD_DAILY_TASK_CAP:
            over = len(items) - HARD_DAILY_TASK_CAP
            ranked = sorted(
                items,
                key=lambda mt: (
                    _tier(mt[0], mt[1]),
                    float(mt[1].get("intensity") or 0.0),
                    _task_sort_uuid(mt[1]),
                ),
            )
            for maxx_id, task in ranked[:over]:
                _suppress_task(
                    schedules, maxx_id, di, task,
                    reason_code=REASON_DAY_FULL_HARD,
                )
                items.remove((maxx_id, task))

    # 5) Final cross-module busy-window eviction (opt-in via user_ctx).
    eviction_anchor = aligned_anchor if aligned_anchor is not None else start_date
    if isinstance(user_ctx, dict) and eviction_anchor is not None:
        _evict_busy_windows(schedules, user_ctx, eviction_anchor, day_count)

    # Strip padding days that stayed empty; a pad that RECEIVED a task or a
    # ledger entry becomes a real, correctly-dated day and is kept.
    if aligned_anchor is not None:
        for m, days in schedules.items():
            kept: list[dict] = []
            for d in days:
                if d.pop("_pad", False) and not (d.get("tasks") or d.get("held_back")):
                    continue
                kept.append(d)
            schedules[m] = kept

    return schedules


def _evict_busy_windows(
    schedules: dict[str, list[dict]],
    user_ctx: dict,
    start_date: Any,
    day_count: int,
) -> None:
    """Re-place the merged task list into the day's FREE intervals.

    Per day, resolves that weekday's busy windows (override → global), subtracts
    them from the waking day to get the free gaps, then assigns every
    cross-module task to the free interval it currently sits nearest and packs
    each interval in time order. A roomy interval (e.g. the whole evening) keeps
    its tasks at their natural, spread-out times; a squeezed one (the morning
    before a commute) compacts toward back-to-back so the WHOLE run — SPF
    included — still lands before the obligation instead of spilling its last
    step past the workday. Overflow from a full interval carries into the next.
    Strict no-op for any day with no busy windows. Mutates tasks in place.
    """
    from datetime import timedelta as _td

    from services.schedule_validator import (
        _WEEKDAY_NAMES,
        _busy_intervals_from_ctx,
        _calendar_busy_for_date,
        _effective_day_ctx,
        _merge_intervals,
        _sleep_minutes_normalized,
    )
    from services.schedule_dsl import (
        crosses_midnight,
        from_minutes,
        order_minutes,
        parse_clock,
        to_minutes,
    )

    g_wake = str(user_ctx.get("wake_time") or "07:00")
    g_sleep = str(user_ctx.get("sleep_time") or "23:00")

    cache: dict[str, tuple] = {}

    def _params(wd: str):
        if wd in cache:
            return cache[wd]
        eff = _effective_day_ctx(user_ctx, wd, global_wake=g_wake, global_sleep=g_sleep)
        wake_dt = parse_clock(eff["wake_time"], "07:00")
        sleep_dt = parse_clock(eff["sleep_time"], "23:00")
        busy = _busy_intervals_from_ctx(eff)
        overnight = crosses_midnight(wake_dt, sleep_dt)
        wake_min = to_minutes(wake_dt)
        sleep_rel = _sleep_minutes_normalized(wake_dt, sleep_dt) - wake_min
        cache[wd] = (wake_min, sleep_rel, busy, overnight)
        return cache[wd]

    for di in range(day_count):
        day_date = start_date + _td(days=di)
        wd = _WEEKDAY_NAMES[day_date.weekday()]
        wake_min, sleep_rel, busy, overnight = _params(wd)
        # Real calendar events for THIS date get identical treatment to the
        # user's recurring obligations: tasks are packed into the gaps around
        # them rather than walked forward, so a morning crowded by meetings
        # compacts to fit instead of spilling into them.
        cal_busy = _calendar_busy_for_date(user_ctx, day_date.isoformat())
        if cal_busy:
            busy = _merge_intervals(list(busy) + cal_busy)
        if not busy:
            continue

        # Working-minute space: minutes-since-wake when overnight, else clock.
        def _to_work(clock: int) -> int:
            return order_minutes(clock, wake_min) if overnight else clock

        def _to_clock_str(work: int) -> str:
            return from_minutes((wake_min + work) if overnight else work).strftime("%H:%M")

        busy_w = sorted((_to_work(s), _to_work(e)) for s, e in busy)

        # Free space = the waking day minus the merged busy windows. Tasks are
        # placed INTO these gaps rather than walked forward and patched, so a
        # crowded morning compacts to fit before the commute instead of spilling
        # its last step past the workday.
        day_start_w = 0 if overnight else wake_min
        day_end_w = sleep_rel if overnight else (wake_min + sleep_rel)
        free = _free_intervals(busy_w, day_start_w, day_end_w)
        if not free:
            continue  # fully busy day (pathological) — leave tasks untouched

        items: list[dict] = []
        for days in schedules.values():
            if di < len(days):
                items.extend(days[di].get("tasks") or [])
        if not items:
            continue

        # Assign every cross-module task to the free interval it's nearest to,
        # carrying its current time as the placement anchor.
        groups: list[list[tuple[int, int, dict]]] = [[] for _ in free]
        for t in items:
            dur = max(1, int(t.get("duration_min") or t.get("duration_minutes") or 1))
            start_w = _to_work(_time_to_min(t.get("time")))
            groups[_nearest_free(start_w, free)].append((start_w, dur, t))

        # Pack each interval in time order. Anything that can't fit even when
        # compacted overflows into the NEXT interval (a too-full morning sheds
        # its lowest-priority extra into the afternoon, never into the commute).
        carry: list[tuple[int, int, dict]] = []
        for gi, (S, E) in enumerate(free):
            entries = carry + groups[gi]
            # Clamp anchors into [S, E] so the forward walk starts sensibly, then
            # order by anchor to preserve each task's relative time-of-day.
            entries = [(min(max(a, S), E), d, ref) for (a, d, ref) in entries]
            entries.sort(key=lambda x: x[0])
            placed, carry = _pack_interval(entries, S, E, MIN_TASK_GAP_MIN)
            for start_w, ref in placed:
                new_clock = _to_clock_str(start_w)
                if new_clock != ref.get("time"):
                    ref["time"] = new_clock
        # Leftover carry (couldn't fit any interval) keeps its original time —
        # safer than stacking at the day's end. The upstream daily-cap pass makes
        # this practically unreachable for real users.


def _free_intervals(
    busy_w: list[tuple[int, int]], day_start: int, day_end: int
) -> list[tuple[int, int]]:
    """[day_start, day_end] minus the busy windows → the free gaps to place in.

    All inputs are in the day's working-minute space (clock for a day schedule,
    minutes-since-wake for an overnight one). Returns [] if the day is fully
    busy; the caller then leaves that day's tasks where they are.
    """
    free: list[tuple[int, int]] = []
    cursor = day_start
    for bs, be in sorted(busy_w):
        bs = max(bs, day_start)
        be = min(be, day_end)
        if be <= bs:
            continue
        if bs > cursor:
            free.append((cursor, bs))
        cursor = max(cursor, be)
    if cursor < day_end:
        free.append((cursor, day_end))
    return free


def _nearest_free(cur: int, free: list[tuple[int, int]]) -> int:
    """Index of the free interval holding `cur`, else the nearest by distance.

    A task that currently sits INSIDE a busy window (a routine step the merge
    shoved into the commute) gets assigned to the free interval whose edge it is
    closest to — so a task that spilled just past the morning's end comes back
    to the morning, while one near the window's far end flows to the evening.
    """
    best, best_d = 0, None
    for i, (s, e) in enumerate(free):
        if s <= cur < e:
            return i
        d = min(abs(cur - s), abs(cur - e))
        if best_d is None or d < best_d:
            best, best_d = i, d
    return best


def _pack_interval(
    entries: list[tuple[int, int, dict]], S: int, E: int, gap: int
) -> tuple[list[tuple[int, dict]], list[tuple[int, int, dict]]]:
    """Place `entries` (each (anchor_start, dur, task_ref), sorted by anchor)
    inside the free interval [S, E].

    Two passes:
      1. Natural forward walk anchored to each task's current time. If the run
         already fits (last task ends by E), keep those times — a roomy interval
         (e.g. the whole evening) stays at its real, spread-out times.
      2. If the run overruns E, the interval is squeezed by the next busy window
         (the classic crowded-morning-before-the-commute case). Compact: shrink
         the inter-task gap toward back-to-back as needed, then left-align from
         the natural earliest start, pulling tasks earlier toward S only as far
         as required so the WHOLE run lands before E. This is what keeps a
         squeezed morning routine — SPF included — before the commute instead of
         dumping the last step past the workday.

    Returns (placed, overflow): placed = [(start, ref)]; overflow = entries that
    don't fit even compressed (handed to the next interval by the caller).
    """
    if not entries:
        return [], []
    durs = [d for _, d, _ in entries]
    n = len(entries)

    # Pass 1: natural forward walk.
    walk: list[int] = []
    cursor: int | None = None
    for anchor, d, _ref in entries:
        s = anchor if cursor is None else max(anchor, cursor + gap)
        walk.append(s)
        cursor = s + d
    if walk[-1] + durs[-1] <= E:
        return [(walk[i], entries[i][2]) for i in range(n)], []

    # Pass 2: compact to fit before E.
    total = sum(durs)
    room = E - S
    if n > 1:
        max_gap = (room - total) // (n - 1)
        g = gap if max_gap >= gap else max(0, max_gap)
    else:
        g = 0
    span = total + g * (n - 1)
    earliest = entries[0][0]
    if span <= room:
        start0 = max(S, min(earliest, E - span))
    else:
        start0 = S  # cannot fit even back-to-back; place what we can, overflow rest

    placed: list[tuple[int, dict]] = []
    overflow: list[tuple[int, int, dict]] = []
    cursor = start0
    for i, (anchor, d, ref) in enumerate(entries):
        if cursor + d <= E:
            placed.append((cursor, ref))
            cursor += d + g
        else:
            overflow.append(entries[i])
    return placed, overflow


def _reindex(schedules: dict[str, list[dict]], day_count: int) -> list[list[tuple[str, dict]]]:
    by_day: list[list[tuple[str, dict]]] = [[] for _ in range(day_count)]
    for maxx_id, days in schedules.items():
        for di, day in enumerate(days):
            for t in day.get("tasks") or []:
                by_day[di].append((maxx_id, t))
    return by_day



def _move_task(schedules: dict[str, list[dict]], maxx_id: str, from_di: int, to_di: int, task: dict) -> None:
    days = schedules.get(maxx_id) or []
    if from_di >= len(days) or to_di >= len(days):
        return
    days[from_di]["tasks"] = [t for t in (days[from_di].get("tasks") or []) if t is not task]
    days[to_di].setdefault("tasks", []).append(task)


def _find_safe_day(by_day: list[list], catalog_id: str, *, start_after: int) -> int | None:
    """Find the next day index where catalog_id is NOT already present."""
    for di in range(start_after + 1, len(by_day)):
        ids = {t.get("catalog_id") for _, t in by_day[di]}
        if catalog_id not in ids:
            return di
    return None


def _time_to_min(s: Any) -> int:
    if not isinstance(s, str) or ":" not in s:
        return 0
    h, m = s.split(":", 1)
    try:
        return int(h) * 60 + int(m)
    except ValueError:
        return 0
