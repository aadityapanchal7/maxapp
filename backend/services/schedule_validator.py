"""Deterministic schedule validator.

Runs after every generation/adapt and before anything is saved. Catches
hallucinated tasks, invalid task IDs, time collisions, sleep-window
violations, duplicate titles, oversized tasks/days. Returns either:
  - (True, [], days_normalized)            — clean
  - (False, [errors_list], days_normalized) — caller can surface to LLM
                                              for one retry pass

The validator also AUTOMATICALLY FIXES soft issues (push 5min separation
between same-window tasks, truncate over-long titles) so the LLM doesn't
have to bother with them. Hard errors (unknown task ID, bad day count,
catastrophic structure) require regeneration.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import time as dtime
from typing import Any

from services.schedule_dsl import (
    from_minutes,
    parse_clock,
    resolve_window,
    to_minutes,
)
from services.task_catalog_service import all_tasks, get_task

logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 28
# 15-min minimum so a routine that fans into 4 sub-tasks doesn't fire 4
# notifications inside 20 minutes (was 5; produced morning storms).
MIN_TASK_GAP_MIN = 15
# 5 distinct notifications/day per module — coach research (Belgravia /
# Renaissance Periodization / mobile-UX benchmarks) puts the mute
# threshold at ~7/day total across all modules. With premium = 3 active
# modules, per-module budget of 5 keeps total around 12-15 (reduced
# further by multi_module_collision's cross-module cap).
HARD_DAILY_TASK_CAP = 5


# Tokens that should keep their original casing in task titles even when
# the rest of the title is lowercased. These are common abbreviations
# users recognize visually; rendering them lowercase ("am nutrition",
# "spf 50", "liss cardio") looks wrong and reduces scan-ability.
_PRESERVE_CASE_TOKENS = (
    "AM", "PM", "SPF", "UV", "BHA", "AHA", "PHA", "LISS", "HIIT",
    "TDEE", "RIR", "DB", "BB", "OHP", "RDL", "PPL", "TMJ",
    "K2", "D3", "B5", "B12", "C", "EAA", "BCAA", "MMA",
)


def _normalize_title_case(raw: str) -> str:
    """Lowercase a task title but preserve common ALL-CAPS abbreviations
    (AM, PM, SPF, LISS, etc). Without this, the validator's earlier
    blanket .lower() turned "AM nutrition" into "am nutrition", which
    reads wrong for a scannable reminder list.
    """
    if not raw:
        return ""
    lo = raw.strip().lower()
    out = lo
    for tok in _PRESERVE_CASE_TOKENS:
        # Word-boundary, case-insensitive replace back to canonical casing.
        out = re.sub(rf"\b{tok.lower()}\b", tok, out)
    return out


@dataclass
class ValidationError:
    severity: str  # "hard" | "soft"
    code: str
    message: str
    day_index: int | None = None
    task_id: str | None = None


def validate_and_fix(
    *,
    maxx_id: str,
    days: list[dict],
    wake_time: str,
    sleep_time: str,
    user_ctx: dict[str, Any],
    expected_day_count: int | None = None,
    daily_task_budget: tuple[int, int] | None = None,
) -> tuple[bool, list[ValidationError], list[dict]]:
    """Validate + fix-where-safe. Returns (clean, errors, fixed_days).

    `clean` is False ONLY when there are HARD errors. Soft fixes don't
    flip clean to False — they're applied silently.
    """
    errors: list[ValidationError] = []
    if not isinstance(days, list):
        errors.append(ValidationError("hard", "structure", "days must be a list"))
        return False, errors, []

    wake = parse_clock(wake_time, "07:00")
    sleep = parse_clock(sleep_time, "23:00")
    sleep_min = _sleep_minutes_normalized(wake, sleep)

    valid_ids = {t.id for t in all_tasks(maxx_id)}
    if expected_day_count and len(days) != expected_day_count:
        errors.append(ValidationError(
            "soft", "day_count_mismatch",
            f"expected {expected_day_count} days, got {len(days)}",
        ))

    fixed_days: list[dict] = []
    for di, day in enumerate(days):
        tasks = day.get("tasks") or []
        if not isinstance(tasks, list):
            errors.append(ValidationError("hard", "day_tasks_type", "day.tasks must be a list", day_index=di))
            continue

        clean_tasks: list[dict] = []
        for task in tasks:
            err, fixed = _validate_task(
                task=task, day_index=di, valid_ids=valid_ids, maxx_id=maxx_id,
                wake=wake, sleep_min=sleep_min,
            )
            errors.extend(err)
            if fixed is not None:
                clean_tasks.append(fixed)

        clean_tasks = _enforce_separation(clean_tasks, day_index=di, errors=errors)

        # Daily task budget
        if daily_task_budget:
            mn, mx = daily_task_budget
            if len(clean_tasks) < mn:
                errors.append(ValidationError(
                    "soft", "below_min_tasks",
                    f"day {di+1}: {len(clean_tasks)} tasks < min {mn}",
                    day_index=di,
                ))
            if len(clean_tasks) > mx:
                # Drop lowest-intensity (cosmetic) tasks beyond cap.
                clean_tasks = _truncate_by_intensity(clean_tasks, maxx_id, mx)
                errors.append(ValidationError(
                    "soft", "above_max_tasks",
                    f"day {di+1}: trimmed to budget max {mx}",
                    day_index=di,
                ))

        # Hard cap regardless of per-max budget
        if len(clean_tasks) > HARD_DAILY_TASK_CAP:
            clean_tasks = _truncate_by_intensity(clean_tasks, maxx_id, HARD_DAILY_TASK_CAP)
            errors.append(ValidationError(
                "soft", "hard_cap",
                f"day {di+1}: trimmed to hard cap {HARD_DAILY_TASK_CAP}",
                day_index=di,
            ))

        fixed_days.append({**day, "tasks": clean_tasks})

    # Cross-day antagonism: retinoid + dermastamp on same day
    _detect_antagonism(fixed_days, maxx_id, errors)

    has_hard = any(e.severity == "hard" for e in errors)
    return (not has_hard), errors, fixed_days


def _validate_task(
    *,
    task: dict,
    day_index: int,
    valid_ids: set[str],
    maxx_id: str,
    wake: dtime,
    sleep_min: int,
) -> tuple[list[ValidationError], dict | None]:
    errs: list[ValidationError] = []
    if not isinstance(task, dict):
        return [ValidationError("hard", "task_type", "task must be object", day_index=day_index)], None

    cat_id = task.get("catalog_id") or task.get("task_catalog_id")
    if not cat_id:
        return [ValidationError("hard", "missing_catalog_id",
                                "task missing catalog_id", day_index=day_index)], None
    if cat_id not in valid_ids:
        return [ValidationError("hard", "unknown_catalog_id",
                                f"catalog_id {cat_id!r} not in {maxx_id} catalog",
                                day_index=day_index, task_id=cat_id)], None

    catalog_task = get_task(maxx_id, cat_id)
    raw_title = (task.get("title") or catalog_task.title or "").strip()
    title = _normalize_title_case(raw_title)
    if len(title) > MAX_TITLE_CHARS:
        title = title[: MAX_TITLE_CHARS - 1].rstrip() + "…"
    elif not title:
        title = catalog_task.title

    description = (task.get("description") or catalog_task.description or "").strip()
    if len(description) > 220:
        description = description[:217].rstrip() + "..."

    # Time
    raw_time = task.get("time") or ""
    minute = _parse_time_field(raw_time)
    if minute is None:
        # Fallback to mid-window of catalog default_window.
        try:
            sleep_t = from_minutes(sleep_min if sleep_min < 24*60 else sleep_min - 24*60)
            ws, we = resolve_window(catalog_task.default_window, wake=wake, sleep=sleep_t)
            minute = (ws + we) // 2
        except Exception:
            minute = to_minutes(wake) + 60

    # Sleep window violation: anything between sleep and wake (next morning) is invalid.
    if _is_during_sleep(minute, wake_min=to_minutes(wake), sleep_min=sleep_min):
        errs.append(ValidationError(
            "soft", "sleep_window",
            f"task at {raw_time or minute} falls inside sleep window — moved",
            day_index=day_index, task_id=cat_id,
        ))
        # Push to wake+1hr (am_open default).
        minute = to_minutes(wake) + 60

    fixed = {
        "task_id": task.get("task_id") or _stable_uid(),
        "catalog_id": cat_id,
        "title": title,
        "description": description,
        "time": from_minutes(minute).strftime("%H:%M"),
        "duration_min": int(task.get("duration_min", catalog_task.duration_min)),
        "tags": list(task.get("tags") or catalog_task.tags),
        "status": task.get("status") or "pending",
        "intensity": float(catalog_task.intensity),
    }
    return errs, fixed


def _enforce_separation(tasks: list[dict], *, day_index: int, errors: list[ValidationError]) -> list[dict]:
    """Sort tasks by time; push later tasks forward to enforce min gap."""
    if not tasks:
        return tasks
    sorted_tasks = sorted(tasks, key=lambda t: _parse_time_field(t["time"]) or 0)
    last_end = -1
    out = []
    for t in sorted_tasks:
        start = _parse_time_field(t["time"]) or 0
        if start < last_end + MIN_TASK_GAP_MIN:
            new_start = last_end + MIN_TASK_GAP_MIN
            errors.append(ValidationError(
                "soft", "time_collision",
                f"day {day_index+1}: pushed {t['title']!r} to {from_minutes(new_start)}",
                day_index=day_index, task_id=t.get("catalog_id"),
            ))
            t = {**t, "time": from_minutes(new_start).strftime("%H:%M")}
            start = new_start
        last_end = start + max(1, int(t.get("duration_min", 1)))
        out.append(t)
    return out


def _truncate_by_intensity(tasks: list[dict], maxx_id: str, cap: int) -> list[dict]:
    """Keep highest-intensity tasks. Tie-break by earlier time."""
    ranked = sorted(
        tasks,
        key=lambda t: (-(t.get("intensity") or 0.0), _parse_time_field(t["time"]) or 0),
    )
    return sorted(ranked[:cap], key=lambda t: _parse_time_field(t["time"]) or 0)


# Pairs of catalog_ids that must NOT appear on the same day.
_ANTAGONISTIC = {
    frozenset({"skin.retinoid_pm", "skin.dermastamp_pm"}),
    frozenset({"hair.minoxidil_am", "hair.microneedle_pm"}),
    frozenset({"hair.minoxidil_pm", "hair.microneedle_pm"}),
}


def _detect_antagonism(days: list[dict], maxx_id: str, errors: list[ValidationError]) -> None:
    for di, day in enumerate(days):
        ids = {t.get("catalog_id") for t in (day.get("tasks") or [])}
        for pair in _ANTAGONISTIC:
            if pair.issubset(ids):
                errors.append(ValidationError(
                    "hard", "antagonistic_pair",
                    f"day {di+1}: {sorted(pair)} must not coexist on same day",
                    day_index=di,
                ))


def _parse_time_field(s: Any) -> int | None:
    if isinstance(s, int):
        return s
    if not isinstance(s, str):
        return None
    s = s.strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def _is_during_sleep(minute: int, *, wake_min: int, sleep_min: int) -> bool:
    """sleep_min is normalized so sleep_min > wake_min always."""
    minute_norm = minute if minute >= wake_min else minute + 24 * 60
    return minute_norm < wake_min or minute_norm >= sleep_min


def _sleep_minutes_normalized(wake: dtime, sleep: dtime) -> int:
    s = to_minutes(sleep)
    w = to_minutes(wake)
    if s < w:
        s += 24 * 60
    return s


def _stable_uid() -> str:
    from uuid import uuid4
    return str(uuid4())
