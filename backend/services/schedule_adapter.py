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

DAY MAPPING (CRITICAL when the user names weekdays):
  The CURRENT SCHEDULE block lists each day with its `day_index` AND the
  weekday it lands on. When the user names a weekday — "tuesdays",
  "weekends", "fridays" — they ALWAYS mean a recurring rule, not just
  one day. The schedule covers ~14 days, so each weekday appears TWICE.
  YOU MUST EMIT ONE OP PER MATCHING TASK PER MATCHING DAY. Walk EVERY
  day in the snapshot, check its weekday, and emit ops for EVERY match.

  Concrete: "cancel gym on tuesdays" with a schedule containing 2
  Tuesdays and 3 gym tasks each → emit 6 remove ops, not 1, not 3.

  Common groupings:
    "gym"            → height.face_pulls, height.glute_bridge,
                       height.dead_hang, height.foam_roll_back, all
                       fitmax.* exercise tasks
    "skincare"       → all skin.* catalog ids
    "actives"        → skin.retinoid_pm, skin.dermastamp_pm,
                       skin.azelaic_am, skin.centella_am
    "weekends"       → Saturday + Sunday day_indices
  Examples:
    "cancel gym on tuesdays"       → emit `remove` for every face_pulls /
                                      glute_bridge / dead_hang task whose
                                      day_index has weekday=Tuesday
    "no skincare on weekends"      → remove skin.* tasks where weekday
                                      ∈ {Saturday, Sunday}
    "move tret to mondays only"    → emit `remove` for tret on non-Monday
                                      days; tret on Mondays stays
    "skip everything tomorrow"     → remove all tasks for day_index=1

PERSISTENT-PREFERENCE EXTRACTION:
  When a user expresses an ongoing rule (not a one-off), ALSO emit
  context_updates so future regenerations honor it:
    "no gym on tuesdays"           → context_updates.timing_preferences =
                                      {"no_gym_weekdays": ["tuesday"]}
    "i'm allergic to fragrance"    → context_updates.product_dislikes
                                      ["fragrance"]
    "stop suggesting mewing"       → context_updates.explicit_avoidances
                                      ["mewing"]

CONTEXT UPDATES — keys to use:
  product_preferences   {"<role>": "<brand>"}        e.g. user said "i use cerave foaming"
  product_dislikes      ["..."]                       e.g. "the ordinary niacinamide breaks me out"
  morning_friction      "high" | "low"                e.g. "i hate mornings"
  equipment_owned       ["dermastamp"]                e.g. "i just got a dermastamp"
  explicit_avoidances   ["mewing"]                    e.g. "no mewing please"
  timing_preferences    {"workout": "evening", "no_gym_weekdays": ["tuesday"]}

RULES:
- Use ONLY existing task_ids for move/remove/swap. Use ONLY catalog_ids from ELIGIBLE for swap/add.
- Don't add more than 3 tasks total in one adapt call.
- If the user mentions a weekday or "weekends", ALWAYS expand it to every
  matching day_index — never to just one day.
- If feedback is "too hard", prefer removing high-intensity tasks first.
- If feedback names a specific task, ONLY touch that task and its replacements.
- Empty ops list is valid if feedback is purely informational ("i like the plan").
- Lower-cased summary, no markdown headings.
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

    # Post-process: when the user named a weekday or "weekends", expand
    # each remove op to ALL matching weekday days. The LLM regularly
    # under-emits here (e.g. emits 1 op for "cancel X on tuesdays" when
    # the schedule has 2 Tuesdays). This pass guarantees full coverage
    # without requiring perfect LLM output.
    ops = _expand_recurring_weekday_ops(ops=ops, days=days, feedback=feedback)
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
    # Compact view of current schedule. Stamp weekday on each day so the
    # LLM can resolve "tuesdays", "weekends", "tomorrow" → day_index.
    from datetime import date as _date, timedelta as _td
    lines: list[str] = []
    today_is_first = True   # day 0 is "today" (set during generation)
    anchor_date = _date.today()
    for di, day in enumerate(days):
        # Prefer the date stored on the day itself; fallback to anchor+offset.
        d_iso = day.get("date") or (anchor_date + _td(days=di)).isoformat()
        try:
            d_obj = _date.fromisoformat(d_iso)
            weekday = d_obj.strftime("%A")
            d_label = f"{weekday} {d_iso}"
        except Exception:
            d_label = d_iso
        # One header line per day so the LLM can see "d2 = Tuesday".
        lines.append(f"  -- d{di}  {d_label} --")
        for t in day.get("tasks") or []:
            # IMPORTANT: pass the FULL task_id, not truncated. The adapter's
            # _apply_ops matches on the full string; a truncation here means
            # every remove/move op the LLM emits will be unfindable.
            lines.append(
                f"     {t.get('time','??:??')}  task_id={t.get('task_id','?')}  "
                f"catalog={t.get('catalog_id','?')}  \"{t.get('title','')}\""
            )
    sched_block = "\n".join(lines) if lines else "  (empty)"

    elig_block = "\n".join(
        f"- {t.id} | {t.default_window} | int={t.intensity} | \"{t.title}\""
        for t in eligible
    )

    state_block = "\n".join(f"  {k}: {v}" for k, v in user_state.items() if v not in (None, "", [], {}) and not k.startswith("_"))

    # Long-term user facts (diet/allergies/etc.) — same source the chat
    # agent uses. Inject into the adapter so e.g. "swap tret for something
    # vegan-friendly" honors stored facts.
    facts_block = ""
    try:
        from services.user_facts_service import format_facts_for_prompt
        facts_block = format_facts_for_prompt(user_state.get("user_facts") or {})
    except Exception:
        pass

    return (
        f"{ADAPT_SYSTEM_PROMPT}\n\n"
        f"## MAX: {doc.maxx_id}\n"
        f"## WAKE/SLEEP: {wake} / {sleep}\n\n"
        f"## USER STATE\n{state_block or '  (empty)'}\n\n"
        + (f"{facts_block}\n\n" if facts_block else "")
        + f"## CURRENT SCHEDULE ({len(days)} days)\n{sched_block}\n\n"
        f"## ELIGIBLE TASKS (for swap/add)\n{elig_block}\n\n"
        f"## USER FEEDBACK\n\"{feedback}\"\n\n"
        f"Return the JSON object now."
    )


def _expand_recurring_weekday_ops(
    *, ops: list[dict], days: list[dict], feedback: str,
) -> list[dict]:
    """If the user mentioned weekdays / "weekends" / "every" in their
    request, expand each `remove` op to ALL matching tasks across the
    relevant days. Conservative: only expands when the feedback clearly
    signals a recurring pattern. Idempotent — running twice is safe."""
    from datetime import date as _date
    if not ops:
        return ops
    fb = (feedback or "").lower()
    weekday_names = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    targeted: set[str] = {w for w in weekday_names if w in fb or (w + "s") in fb}
    if "weekends" in fb or "weekend" in fb:
        targeted.update({"saturday", "sunday"})
    if "weekdays" in fb:
        targeted.update({"monday", "tuesday", "wednesday", "thursday", "friday"})
    if not targeted and "every" not in fb:
        return ops

    # Build day_index → weekday map.
    di_to_wd: dict[int, str] = {}
    for di, day in enumerate(days):
        d_iso = day.get("date")
        if not d_iso:
            continue
        try:
            di_to_wd[di] = _date.fromisoformat(d_iso).strftime("%A").lower()
        except Exception:
            continue

    # Collect catalog_ids the LLM wanted removed.
    remove_cids: set[str] = set()
    keep_ops: list[dict] = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        if op.get("action") == "remove" and op.get("task_id"):
            # Find the catalog_id for this task to expand the rule.
            tid = str(op["task_id"])
            for day in days:
                for t in (day.get("tasks") or []):
                    if t.get("task_id") == tid:
                        cid = t.get("catalog_id")
                        if cid:
                            remove_cids.add(cid)
                        break
            keep_ops.append(op)
        else:
            keep_ops.append(op)

    if not remove_cids or not targeted:
        return ops

    # For every task in the schedule whose catalog_id is in remove_cids
    # AND whose weekday is targeted, ensure there's a remove op.
    existing_targets: set[str] = {
        str(o.get("task_id")) for o in ops
        if isinstance(o, dict) and o.get("action") == "remove" and o.get("task_id")
    }
    extra_ops: list[dict] = []
    for di, day in enumerate(days):
        wd = di_to_wd.get(di)
        if not wd or wd not in targeted:
            continue
        for t in (day.get("tasks") or []):
            cid = t.get("catalog_id")
            tid = t.get("task_id")
            if cid in remove_cids and tid and tid not in existing_targets:
                extra_ops.append({"action": "remove", "task_id": tid})
                existing_targets.add(tid)

    return keep_ops + extra_ops


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
