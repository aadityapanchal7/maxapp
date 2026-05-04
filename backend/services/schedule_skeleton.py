"""Deterministic skeleton-based schedule expander.

Replaces the LLM call in the schedule generator. Reads the `skeleton:`
block from a max-doc (already parsed into `MaxDoc.schedule_design`),
filters blocks by user state, distributes tasks across `cadence_days`,
and emits a fully-formed schedule the validator can finish.

A skeleton is a list of "blocks". Each block describes WHEN tasks land
(by slot + cadence) and WHICH tasks (static list or dynamic picker).

Block schema:
    id: str                     # unique within max
    slot: str                   # named window: am_open, am_active, midday,
                                # pm_active, pm_close, flexible
    cadence: str | dict         # daily | n_per_week=N | every_n_days=N | dynamic
    if: str (optional)          # DSL expression — block is dropped if false
    tasks: [catalog_id]         # static list (most blocks)
    pick_from: [{id, days_per_week, requires?, not_with?}]
                                # used when cadence == dynamic
    replaces: [block_id]        # remove these block ids before placement
    not_with_same_day: [catalog_id]
                                # cross-block: don't place same-day with these
                                # catalog_ids that are already on the day

Output: list of `cadence_days` day dicts, each with `tasks` array. Every
task has the shape the validator expects: catalog_id, time, title,
description, duration_min, tags, status, intensity. Then the validator
runs and may bump times for collisions / fix titles.

Performance: pure Python, no I/O. Typical 14-day skinmax schedule:
~2-5 ms expansion. The whole generate path becomes <100ms (warm catalog
+ DSL filter + skeleton expand + validate).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import time as dtime
from typing import Any, Optional
from uuid import uuid4

from services.schedule_dsl import (
    evaluate,
    evaluate_all,
    from_minutes,
    parse_clock,
    resolve_window,
    to_minutes,
)
from services.task_catalog_service import get_doc, get_task

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Block + schedule containers                                                #
# --------------------------------------------------------------------------- #

@dataclass
class _Block:
    id: str
    slot: str
    cadence: str          # "daily" | "n_per_week=N" | "every_n_days=N" | "dynamic"
    if_expr: Optional[str]
    tasks: list[str]
    pick_from: list[dict] = field(default_factory=list)
    replaces: list[str] = field(default_factory=list)
    not_with_same_day: list[str] = field(default_factory=list)


def _parse_block(raw: dict) -> _Block:
    if not isinstance(raw, dict):
        raise ValueError(f"skeleton block must be dict, got {type(raw).__name__}")
    bid = str(raw.get("id") or "").strip()
    if not bid:
        raise ValueError(f"skeleton block missing id: {raw}")
    slot = str(raw.get("slot") or "flexible")
    cadence = raw.get("cadence", "daily")
    if isinstance(cadence, dict):
        cadence = f"{cadence.get('type','daily')}={cadence.get('n', 1)}"
    cadence = str(cadence).strip().lower()

    return _Block(
        id=bid,
        slot=slot,
        cadence=cadence,
        if_expr=str(raw.get("if")) if raw.get("if") else None,
        tasks=[str(t) for t in (raw.get("tasks") or [])],
        pick_from=list(raw.get("pick_from") or []),
        replaces=[str(r) for r in (raw.get("replaces") or [])],
        not_with_same_day=[str(t) for t in (raw.get("not_with_same_day") or [])],
    )


# --------------------------------------------------------------------------- #
#  Public API                                                                 #
# --------------------------------------------------------------------------- #

def expand_skeleton(
    *,
    maxx_id: str,
    user_state: dict,
    wake: str,
    sleep: str,
    cadence_days: int = 14,
) -> list[dict]:
    """Return a `cadence_days`-long list of day dicts.

    Each day looks like:
        { "day_index": 0, "tasks": [ {catalog_id, time, title, ...}, ... ] }

    Tasks within the same slot are ordered by their declaration order in
    the block, and stamped with sequential times starting at the slot's
    window start. The validator handles collision-bumps if anything still
    overlaps after this pass.
    """
    doc = get_doc(maxx_id)
    if doc is None:
        raise ValueError(f"unknown max: {maxx_id}")
    sd = doc.schedule_design or {}
    raw_skeleton = sd.get("skeleton") or {}
    raw_blocks = raw_skeleton.get("blocks") or []
    if not raw_blocks:
        raise ValueError(f"max {maxx_id!r} has no skeleton.blocks defined")

    # 1) Parse + filter by `if`.
    blocks: list[_Block] = []
    for raw in raw_blocks:
        b = _parse_block(raw)
        if b.if_expr and not evaluate(b.if_expr, user_state):
            continue
        blocks.append(b)

    # 2) Honor `replaces` — later blocks remove earlier ones by id.
    removed: set[str] = set()
    for b in blocks:
        for rep in b.replaces:
            removed.add(rep)
    blocks = [b for b in blocks if b.id not in removed]

    # 3) Build `cadence_days` empty days.
    wake_t = parse_clock(wake, "07:00")
    sleep_t = parse_clock(sleep, "23:00")
    win_overrides = {
        "am_window": sd.get("am_window"),
        "pm_window": sd.get("pm_window"),
    }
    win_overrides_resolved: dict[str, list[str]] = {}
    if win_overrides["am_window"]:
        win_overrides_resolved["am_active"] = list(win_overrides["am_window"])
    if win_overrides["pm_window"]:
        win_overrides_resolved["pm_active"] = list(win_overrides["pm_window"])

    days: list[dict] = [
        {"day_index": i, "tasks": []}
        for i in range(cadence_days)
    ]

    # 4) Walk each block, distribute its tasks.
    for b in blocks:
        _place_block(
            block=b,
            user_state=user_state,
            days=days,
            maxx_id=maxx_id,
            wake=wake_t,
            sleep=sleep_t,
            window_overrides=win_overrides_resolved,
        )

    # 5) Sort tasks within each day by time so the validator gets a clean list.
    for d in days:
        d["tasks"].sort(key=lambda t: _time_to_minutes(t.get("time", "00:00")))

    return days


# --------------------------------------------------------------------------- #
#  Block placement                                                            #
# --------------------------------------------------------------------------- #

def _place_block(
    *,
    block: _Block,
    user_state: dict,
    days: list[dict],
    maxx_id: str,
    wake: dtime,
    sleep: dtime,
    window_overrides: dict[str, list[str]],
) -> None:
    """Mutate `days` to add this block's tasks at the right cadence."""
    n_days = len(days)
    cadence = block.cadence

    # Decide which day-indices receive this block.
    if cadence == "daily":
        day_indices = list(range(n_days))
    elif cadence == "dynamic":
        day_indices = list(range(n_days))   # picker decides per-day below
    elif cadence.startswith("n_per_week="):
        try:
            n = max(1, min(7, int(cadence.split("=", 1)[1])))
        except ValueError:
            n = 1
        # Spread evenly across each 7-day window. Keep going for week 2.
        day_indices = []
        for week_start in range(0, n_days, 7):
            picks = [week_start + round(i * 7 / n) for i in range(n)]
            day_indices.extend(p for p in picks if p < n_days)
    elif cadence.startswith("every_n_days="):
        try:
            n = max(1, int(cadence.split("=", 1)[1]))
        except ValueError:
            n = 7
        day_indices = list(range(0, n_days, n))
    else:
        logger.warning("unknown cadence %r in block %s, defaulting to daily", cadence, block.id)
        day_indices = list(range(n_days))

    # Resolve slot → minute window.
    win_start, win_end = resolve_window(
        block.slot, wake=wake, sleep=sleep, overrides=window_overrides,
    )

    # Static tasks vs dynamic picker.
    if cadence == "dynamic":
        _place_dynamic(
            block=block,
            user_state=user_state,
            days=days,
            day_indices=day_indices,
            maxx_id=maxx_id,
            win_start=win_start,
        )
    else:
        for di in day_indices:
            _emit_tasks(
                catalog_ids=block.tasks,
                day=days[di],
                maxx_id=maxx_id,
                user_state=user_state,
                start_minute=win_start,
                block_id=block.id,
                not_with_same_day=block.not_with_same_day,
            )


def _place_dynamic(
    *,
    block: _Block,
    user_state: dict,
    days: list[dict],
    day_indices: list[int],
    maxx_id: str,
    win_start: int,
) -> None:
    """Per-day picker. Walks `pick_from` items in order; the first one whose
    `requires` are met AND has remaining quota AND doesn't conflict with
    already-placed-today tasks wins for that day."""
    if not block.pick_from:
        return

    quota_left: dict[str, int] = {}
    for item in block.pick_from:
        cid = str(item.get("id") or "")
        if not cid:
            continue
        per_week = int(item.get("days_per_week", 7))
        # Total quota across `len(day_indices)` days, scaled from the
        # 7-day rate. round-up so high-priority items get their full count.
        total = max(1, round(per_week * len(day_indices) / 7))
        quota_left[cid] = total

    for di in day_indices:
        day_task_ids = {t.get("catalog_id") for t in (days[di].get("tasks") or [])}
        chosen: Optional[dict] = None
        for item in block.pick_from:
            cid = str(item.get("id") or "")
            if not cid or quota_left.get(cid, 0) <= 0:
                continue
            requires = item.get("requires") or []
            if requires and not evaluate_all(list(requires), user_state):
                continue
            not_with = set(item.get("not_with") or [])
            if not_with & day_task_ids:
                continue
            chosen = item
            break
        if chosen is None:
            continue
        cid = str(chosen["id"])
        quota_left[cid] = quota_left.get(cid, 0) - 1
        _emit_tasks(
            catalog_ids=[cid],
            day=days[di],
            maxx_id=maxx_id,
            user_state=user_state,
            start_minute=win_start,
            block_id=block.id,
            not_with_same_day=block.not_with_same_day,
        )


def _emit_tasks(
    *,
    catalog_ids: list[str],
    day: dict,
    maxx_id: str,
    user_state: dict,
    start_minute: int,
    block_id: str,
    not_with_same_day: list[str],
) -> None:
    """Append catalog_ids to day.tasks at sequential minutes.
    Drops a task if its catalog applies_when fails or contraindicated_when fires.
    Drops the WHOLE block for the day if any not_with_same_day task is already
    present.
    """
    existing_ids = {t.get("catalog_id") for t in (day.get("tasks") or [])}
    if not_with_same_day and any(c in existing_ids for c in not_with_same_day):
        return

    cur = start_minute
    for cid in catalog_ids:
        cat = get_task(maxx_id, cid)
        if cat is None:
            logger.warning("skeleton: %s references unknown catalog_id %s", block_id, cid)
            continue
        # Catalog-level applies_when (defensive — block-level usually handles it).
        if cat.applies_when and not evaluate_all(list(cat.applies_when), user_state):
            continue
        if cat.contraindicated_when and any(
            evaluate(e, user_state) for e in cat.contraindicated_when
        ):
            continue
        time_str = from_minutes(cur).strftime("%H:%M")
        day.setdefault("tasks", []).append({
            "task_id": str(uuid4()),
            "catalog_id": cat.id,
            "title": cat.title,
            "description": cat.description,
            "time": time_str,
            "duration_min": cat.duration_min,
            "tags": list(cat.tags),
            "status": "pending",
            "intensity": float(cat.intensity),
        })
        # 5-minute gap between tasks, or the task's duration, whichever is bigger.
        cur += max(int(cat.duration_min) + 1, 5)


# --------------------------------------------------------------------------- #
#  Helpers                                                                    #
# --------------------------------------------------------------------------- #

def _time_to_minutes(s: str) -> int:
    if not isinstance(s, str) or ":" not in s:
        return 0
    try:
        h, m = s.split(":", 1)
        return int(h) * 60 + int(m)
    except ValueError:
        return 0


def has_skeleton(maxx_id: str) -> bool:
    """True if the doc has a skeleton.blocks block (used by the generator
    to choose the LLM-free path vs falling back)."""
    doc = get_doc(maxx_id)
    if doc is None:
        return False
    sd = doc.schedule_design or {}
    sk = sd.get("skeleton") or {}
    return bool(sk.get("blocks"))
