"""Diff-format schedule adapter — replaces the legacy full-rewrite path.

Input: current schedule (list of days), user feedback (free text).
Output: a small list of operations applied deterministically.

Operations supported:
    move    {action: "move",    task_id: "...", new_day: 2, new_time: "18:30"}
    remove  {action: "remove",  task_id: "..."}
    swap    {action: "swap",    task_id: "...", with_catalog_id: "skin.azelaic_pm"}
    add     {action: "add",     day: 2, catalog_id: "...", time: "21:00"}

Plus (always):
    summary           — 1-2 line human-readable summary of changes
    context_updates   — dict to merge into user_schedule_context (e.g.
                        {"morning_friction": "high"} so future generations remember)

Tokens stay tiny: the LLM sees the current schedule as compact (id+title+time),
not full JSON, and outputs ONLY ops + summary + context_updates.
Days not referenced by any op are byte-identical after this pass.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.llm_sync import async_llm_json_response
from services.schedule_dsl import parse_clock
from services.schedule_validator import validate_and_fix
from services.task_catalog_service import (
    eligible_tasks,
    get_doc,
    get_task,
    is_loaded,
    warm_catalog,
)
from services.user_context_service import get_context, merge_context, merged_user_state

logger = logging.getLogger(__name__)


@dataclass
class AdaptResult:
    ok: bool
    days: list[dict]
    summary: str
    ops_applied: list[dict]
    context_updates: dict
    elapsed_ms: int


ADAPT_SYSTEM_PROMPT = """You modify an existing schedule from short user feedback.

You DO NOT rewrite the whole schedule. You output a SHORT list of OPERATIONS
that get applied deterministically. Days you don't touch stay byte-identical.

OPERATIONS (return as a JSON array):
  {"action": "move",   "task_id": "<existing task_id>", "new_day": <0-N>, "new_time": "HH:MM"}
  {"action": "remove", "task_id": "<existing task_id>"}
  {"action": "swap",   "task_id": "<existing task_id>", "with_catalog_id": "<from ELIGIBLE>"}
  {"action": "add",    "day": <0-N>, "catalog_id": "<from ELIGIBLE>", "time": "HH:MM"}

OUTPUT JSON shape:
{
  "ops": [...],
  "summary": "<2-3 short bullets, each starts with •. facts only.>",
  "context_updates": { "<key>": <value>, ... }
}

CONTEXT UPDATES — extract any persistent facts the user revealed (use these keys):
  product_preferences   {"<role>": "<brand>"}        e.g. user said "i use cerave foaming"
  product_dislikes      ["..."]                       e.g. "the ordinary niacinamide breaks me out"
  morning_friction      "high" | "low"                e.g. "i hate mornings"
  equipment_owned       ["dermastamp"]                e.g. "i just got a dermastamp"
  explicit_avoidances   ["mewing"]                    e.g. "no mewing please"
  timing_preferences    {"workout": "evening"}        e.g. "i can only train at night"

RULES:
- Use only existing task_ids for move/remove/swap. Use only catalog_ids from ELIGIBLE for swap/add.
- Don't add more than 3 tasks total in one adapt call.
- If feedback is "too hard", prefer removing high-intensity tasks first.
- If feedback names a task, ONLY touch that task and its replacements — leave everything else alone.
- Empty ops list is valid if feedback is just informational.
"""


async def adapt_schedule(
    *,
    user_id: str,
    schedule_id: str,
    maxx_id: str,
    days: list[dict],
    feedback: str,
    db: AsyncSession,
    onboarding: dict | None = None,
    wake_time: str = "07:00",
    sleep_time: str = "23:00",
) -> AdaptResult:
    t0 = time.perf_counter()

    if not is_loaded():
        await warm_catalog()

    doc = get_doc(maxx_id)
    if doc is None:
        raise ValueError(f"unknown max: {maxx_id}")

    persistent_ctx = await get_context(user_id, db)
    user_state = merged_user_state(onboarding or {}, persistent_ctx)
    eligible = eligible_tasks(maxx_id, user_state, intensity_cap=1.0)

    prompt = _build_adapt_prompt(
        doc=doc,
        days=days,
        feedback=feedback,
        eligible=eligible,
        user_state=user_state,
        wake=wake_time,
        sleep=sleep_time,
    )

    timeout_s = float(getattr(settings, "schedule_adapt_timeout_seconds", 0) or 0)
    if timeout_s <= 0:
        timeout_s = float(getattr(settings, "llm_timeout_seconds", 25) or 25) * 2
    max_out = max(512, int(getattr(settings, "schedule_adapt_max_output_tokens", 4096) or 4096))

    try:
        raw = await asyncio.wait_for(
            async_llm_json_response(prompt, max_tokens=max_out),
            timeout=timeout_s,
        )
        parsed = json.loads(raw)
    except Exception as e:
        logger.error("schedule_adapter LLM/parse failed: %s", e)
        raise

    ops = parsed.get("ops") or []
    summary = str(parsed.get("summary") or "schedule updated").strip()[:400]
    context_updates = parsed.get("context_updates") or {}

    new_days, applied = _apply_ops(days=days, ops=ops, maxx_id=maxx_id)

    # Validate the result. Soft fixes only — adapter failures don't retry; we
    # apply what we got and surface validator notes via summary if needed.
    _, errors, fixed_days = validate_and_fix(
        maxx_id=maxx_id,
        days=new_days,
        wake_time=wake_time,
        sleep_time=sleep_time,
        user_ctx=user_state,
        expected_day_count=len(days),
        daily_task_budget=tuple(doc.schedule_design.get("daily_task_budget") or [2, 6]),
    )

    if context_updates and isinstance(context_updates, dict):
        try:
            await merge_context(user_id, context_updates, db)
        except Exception as e:
            logger.warning("context merge failed (non-fatal): %s", e)

    return AdaptResult(
        ok=True,
        days=fixed_days,
        summary=summary,
        ops_applied=applied,
        context_updates=context_updates if isinstance(context_updates, dict) else {},
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
    )


def _build_adapt_prompt(
    *,
    doc,
    days: list[dict],
    feedback: str,
    eligible,
    user_state: dict,
    wake: str,
    sleep: str,
) -> str:
    # Compact view of current schedule.
    lines = []
    for di, day in enumerate(days):
        for t in day.get("tasks") or []:
            lines.append(
                f"  d{di} {t.get('time','??:??')}  task_id={t.get('task_id','?')[:8]}  "
                f"catalog={t.get('catalog_id','?')}  \"{t.get('title','')}\""
            )
    sched_block = "\n".join(lines) if lines else "  (empty)"

    elig_block = "\n".join(
        f"- {t.id} | {t.default_window} | int={t.intensity} | \"{t.title}\""
        for t in eligible
    )

    state_block = "\n".join(f"  {k}: {v}" for k, v in user_state.items() if v not in (None, "", [], {}))

    return (
        f"{ADAPT_SYSTEM_PROMPT}\n\n"
        f"## MAX: {doc.maxx_id}\n"
        f"## WAKE/SLEEP: {wake} / {sleep}\n\n"
        f"## USER STATE\n{state_block or '  (empty)'}\n\n"
        f"## CURRENT SCHEDULE ({len(days)} days)\n{sched_block}\n\n"
        f"## ELIGIBLE TASKS (for swap/add)\n{elig_block}\n\n"
        f"## USER FEEDBACK\n\"{feedback}\"\n\n"
        f"Return the JSON object now."
    )


def _apply_ops(*, days: list[dict], ops: list[dict], maxx_id: str) -> tuple[list[dict], list[dict]]:
    """Apply ops left-to-right. Skip invalid ops with a log.
    Returns (new_days, list_of_applied_ops).
    """
    new_days = copy.deepcopy(days)
    applied: list[dict] = []

    # Build task_id → (day_index, task_index) map.
    def index() -> dict[str, tuple[int, int]]:
        m = {}
        for di, day in enumerate(new_days):
            for ti, t in enumerate(day.get("tasks") or []):
                tid = t.get("task_id")
                if tid:
                    m[tid] = (di, ti)
        return m

    for op in ops or []:
        if not isinstance(op, dict):
            continue
        action = op.get("action")
        try:
            if action == "remove":
                tid = op.get("task_id")
                idx = index().get(tid)
                if not idx:
                    logger.info("adapter: remove unknown task_id %s — skipped", tid)
                    continue
                di, ti = idx
                new_days[di]["tasks"].pop(ti)
                applied.append(op)

            elif action == "move":
                tid = op.get("task_id")
                idx = index().get(tid)
                if not idx:
                    continue
                di, ti = idx
                task = new_days[di]["tasks"].pop(ti)
                new_di = max(0, min(len(new_days) - 1, int(op.get("new_day", di))))
                if op.get("new_time"):
                    task["time"] = str(op["new_time"])
                new_days[new_di]["tasks"].append(task)
                applied.append(op)

            elif action == "swap":
                tid = op.get("task_id")
                with_cid = op.get("with_catalog_id")
                cat = get_task(maxx_id, with_cid) if with_cid else None
                if not cat:
                    logger.info("adapter: swap unknown catalog_id %s — skipped", with_cid)
                    continue
                idx = index().get(tid)
                if not idx:
                    continue
                di, ti = idx
                old = new_days[di]["tasks"][ti]
                new_days[di]["tasks"][ti] = {
                    "task_id": old.get("task_id") or str(uuid4()),
                    "catalog_id": cat.id,
                    "title": cat.title,
                    "description": cat.description,
                    "time": old.get("time"),
                    "duration_min": cat.duration_min,
                    "tags": list(cat.tags),
                    "status": "pending",
                    "intensity": cat.intensity,
                }
                applied.append(op)

            elif action == "add":
                cid = op.get("catalog_id")
                cat = get_task(maxx_id, cid) if cid else None
                if not cat:
                    continue
                day_idx = max(0, min(len(new_days) - 1, int(op.get("day", 0))))
                tt = op.get("time") or "09:00"
                new_days[day_idx].setdefault("tasks", []).append({
                    "task_id": str(uuid4()),
                    "catalog_id": cat.id,
                    "title": cat.title,
                    "description": cat.description,
                    "time": str(tt),
                    "duration_min": cat.duration_min,
                    "tags": list(cat.tags),
                    "status": "pending",
                    "intensity": cat.intensity,
                })
                applied.append(op)

            else:
                logger.info("adapter: unknown action %r — skipped", action)
        except Exception as e:
            logger.warning("adapter: op %s failed: %s", op, e)
            continue

    return new_days, applied
