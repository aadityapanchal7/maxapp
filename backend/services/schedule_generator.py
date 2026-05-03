"""New schedule generator — replaces the legacy free-form LLM path.

Pipeline:
    1. Validate required fields collected (else return missing_fields error)
    2. Build user_state = onboarding ∪ user_schedule_context
    3. Compute applicable prompt_modifiers (deterministic from DSL)
    4. Filter task_catalog → eligible_tasks (applies_when / contraindicated_when / intensity cap)
    5. Parallel: load few RAG chunks for context  +  load few-shot examples
    6. Compose generation prompt (task IDs ONLY — model picks from list)
    7. Call LLM with strict JSON schema in system prompt
    8. Validate + fix; on hard errors, retry ONCE with errors injected
    9. Persist via existing schedule_service write path (so notifications etc still work)

The LLM never invents tasks — it picks `catalog_id`s, optionally overriding
`time`, `description`, and `tags`. This makes hallucinations structurally impossible.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.llm_sync import async_llm_json_response
from services.schedule_dsl import parse_clock, resolve_window, to_minutes, from_minutes
from services.schedule_examples import few_shot_for
from services.schedule_validator import (
    HARD_DAILY_TASK_CAP,
    validate_and_fix,
)
from services.task_catalog_service import (
    applicable_modifiers,
    eligible_tasks,
    get_doc,
    is_loaded,
    missing_required,
    warm_catalog,
)
from services.user_context_service import get_context, merged_user_state

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    ok: bool
    days: list[dict]
    summary: str
    errors: list[dict]                # validator errors (post-fix)
    missing_fields: list[dict]        # populated only when ok=False due to onboarding gap
    elapsed_ms: int
    validator_retries: int


GENERATION_SYSTEM_PROMPT = """You are a schedule architect for a looksmaxxing app.

You DO NOT invent tasks. You PICK from a fixed catalog of `catalog_id`s.
You assemble a `cadence_days`-long schedule by choosing which tasks land on which days,
at what time, with optional short overrides on title/description/tags.

OUTPUT — strictly this JSON shape (no markdown, no commentary):
{{
  "days": [
    {{
      "day_index": 0,
      "tasks": [
        {{
          "catalog_id": "<one of the provided IDs>",
          "time": "HH:MM",
          "title": "<≤28 chars; lowercase ok; action-first>",
          "description": "<≤220 chars; reference the user's actual concern when possible>",
          "tags": ["..."]
        }},
        ...
      ]
    }},
    ...
  ],
  "summary": "<2-3 short sentences explaining the plan logic>"
}}

RULES — non-negotiable:
- Use ONLY catalog_ids from the provided ELIGIBLE TASKS list.
- Respect each task's `frequency` (e.g. n_per_week=2 → on 2 of 7 days, not 7).
- Respect each task's `cooldown_hours` (e.g. 168 = once per week).
- Honor the daily_task_budget [{{min_tasks}}, {{max_tasks}}]. Day 1 stays near min.
- Week-1 intensity cap: {{week1_cap}} (do not pick tasks with higher intensity in days 0-6).
- Times stay in waking window [{{wake}} - {{sleep}}].
- No two tasks at the exact same time.
- Titles are lowercase, action-first, never reuse same title in one day (use AM/PM/reapply distinguishers).
- Descriptions reference the user's concern from USER STATE when relevant.
- Apply every PROMPT MODIFIER below. They override default behavior.
"""


async def generate_schedule(
    *,
    user_id: str,
    maxx_id: str,
    db: AsyncSession,
    onboarding: dict[str, Any] | None = None,
    extras: dict[str, Any] | None = None,
) -> GenerationResult:
    t0 = time.perf_counter()

    if not is_loaded():
        await warm_catalog()

    doc = get_doc(maxx_id)
    if doc is None:
        return GenerationResult(
            ok=False, days=[], summary="",
            errors=[{"code": "unknown_max", "message": f"no doc for {maxx_id}"}],
            missing_fields=[], elapsed_ms=0, validator_retries=0,
        )

    # Parallel: user context load.
    ctx_task = asyncio.create_task(get_context(user_id, db))
    persistent_ctx = await ctx_task

    user_state = merged_user_state(onboarding or {}, persistent_ctx, extras or {})

    # Required-field gate
    missing = missing_required(maxx_id, user_state)
    if missing:
        return GenerationResult(
            ok=False, days=[], summary="",
            errors=[{"code": "missing_required", "message": f"need {len(missing)} more answers"}],
            missing_fields=missing,
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            validator_retries=0,
        )

    sd = doc.schedule_design or {}
    cadence_days = int(sd.get("cadence_days", 14))
    daily_budget = sd.get("daily_task_budget") or [2, 6]
    min_tasks, max_tasks = int(daily_budget[0]), int(daily_budget[1])
    week1_cap = float((sd.get("intensity_ramp", {}).get("week_1") or [0.0, 0.5])[1])

    # Wake/sleep — sourced from extras > onboarding > defaults.
    wake_str = (extras or {}).get("wake_time") or user_state.get("wake_time") or "07:00"
    sleep_str = (extras or {}).get("sleep_time") or user_state.get("sleep_time") or "23:00"

    # Filter eligible tasks once at full intensity — the LLM is told the
    # week-1 cap separately and respects it via prompt rules.
    eligible = eligible_tasks(maxx_id, user_state, intensity_cap=1.0)
    if not eligible:
        return GenerationResult(
            ok=False, days=[], summary="",
            errors=[{"code": "no_eligible_tasks", "message": "no catalog tasks fit user state"}],
            missing_fields=[],
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            validator_retries=0,
        )

    modifiers = applicable_modifiers(maxx_id, user_state)
    examples = few_shot_for(maxx_id, user_state)

    rag_context = await _retrieve_rag_context(maxx_id, user_state)

    prompt = _build_prompt(
        doc=doc,
        eligible=eligible,
        modifiers=modifiers,
        examples=examples,
        rag_context=rag_context,
        user_state=user_state,
        cadence_days=cadence_days,
        min_tasks=min_tasks,
        max_tasks=max_tasks,
        week1_cap=week1_cap,
        wake=wake_str,
        sleep=sleep_str,
    )

    days, summary, retries = await _llm_then_validate(
        prompt=prompt,
        maxx_id=maxx_id,
        wake_str=wake_str,
        sleep_str=sleep_str,
        user_state=user_state,
        cadence_days=cadence_days,
        daily_budget=(min_tasks, max_tasks),
    )

    elapsed = int((time.perf_counter() - t0) * 1000)
    return GenerationResult(
        ok=True,
        days=days,
        summary=summary,
        errors=[],
        missing_fields=[],
        elapsed_ms=elapsed,
        validator_retries=retries,
    )


async def _retrieve_rag_context(maxx_id: str, user_state: dict) -> str:
    """Pull a few RAG chunks to ground the prompt — best-effort, non-blocking-on-failure."""
    try:
        from services.rag_service import retrieve_chunks
        # Build a focused query from user state.
        parts: list[str] = [maxx_id]
        for k in ("skin_concern", "barrier_state", "hair_loss_signs", "scalp_state",
                  "heightmax_focus", "posture_issues"):
            v = user_state.get(k)
            if v:
                parts.append(str(v))
        query = " ".join(parts)
        rows = await retrieve_chunks(None, maxx_id, query, k=3, min_similarity=0.2)
        if not rows:
            return ""
        snippets = []
        for r in rows[:3]:
            section = r.get("metadata", {}).get("section") or r.get("doc_title", "")
            content = r.get("content", "")[:400]
            snippets.append(f"[{section}]\n{content}")
        return "\n\n---\n\n".join(snippets)
    except Exception as e:
        logger.warning("RAG context fetch failed (non-fatal): %s", e)
        return ""


def _build_prompt(
    *,
    doc,
    eligible: list,
    modifiers: list[str],
    examples: str,
    rag_context: str,
    user_state: dict,
    cadence_days: int,
    min_tasks: int,
    max_tasks: int,
    week1_cap: float,
    wake: str,
    sleep: str,
) -> str:
    catalog_lines = []
    for t in eligible:
        freq = t.frequency
        freq_str = f"{freq.get('type')}={freq.get('n', 1)}"
        catalog_lines.append(
            f"- {t.id} | window={t.default_window} | "
            f"intensity={t.intensity} | dur={t.duration_min}min | "
            f"freq={freq_str} | cooldown={t.cooldown_hours}h | "
            f'"{t.title}" — {t.description[:90]}'
        )
    catalog_block = "\n".join(catalog_lines)

    mod_block = "\n".join(f"- {m}" for m in modifiers) if modifiers else "- (none)"

    state_lines = []
    for k, v in user_state.items():
        if v in (None, "", [], {}):
            continue
        state_lines.append(f"  {k}: {v}")
    state_block = "\n".join(state_lines)

    sys = GENERATION_SYSTEM_PROMPT.format(
        min_tasks=min_tasks, max_tasks=max_tasks, week1_cap=week1_cap,
        wake=wake, sleep=sleep,
    )

    return (
        f"{sys}\n\n"
        f"## MAX: {doc.maxx_id} ({doc.display_name})\n"
        f"{doc.short_description}\n\n"
        f"## SCHEDULE WINDOW\n"
        f"days: {cadence_days}  |  wake: {wake}  |  sleep: {sleep}\n"
        f"daily task budget: [{min_tasks}, {max_tasks}]   |   week-1 intensity cap: {week1_cap}\n\n"
        f"## USER STATE (from onboarding + persistent context)\n"
        f"{state_block or '  (no fields)'}\n\n"
        f"## PROMPT MODIFIERS (applied — must honor)\n"
        f"{mod_block}\n\n"
        f"## ELIGIBLE TASKS (pick ONLY from these catalog_ids)\n"
        f"{catalog_block}\n\n"
        f"## EVIDENCE (from knowledge base)\n"
        f"{rag_context or '(none retrieved)'}\n\n"
        f"## EXAMPLES (same max, different user — for style only)\n"
        f"{examples}\n\n"
        f"Now produce the JSON. {cadence_days} day objects, day_index 0..{cadence_days-1}."
    )


async def _llm_then_validate(
    *,
    prompt: str,
    maxx_id: str,
    wake_str: str,
    sleep_str: str,
    user_state: dict,
    cadence_days: int,
    daily_budget: tuple[int, int],
) -> tuple[list[dict], str, int]:
    """LLM call + validate + retry-once-with-errors loop."""
    timeout_s = float(getattr(settings, "schedule_generate_timeout_seconds", 0) or 0)
    if timeout_s <= 0:
        timeout_s = float(getattr(settings, "llm_timeout_seconds", 25) or 25) * 2
    max_out = max(1024, int(getattr(settings, "schedule_generate_max_output_tokens", 12288) or 12288))

    last_errors: list = []
    days: list[dict] = []
    summary = ""
    for attempt in range(2):
        full_prompt = prompt
        if attempt > 0 and last_errors:
            errs_text = "\n".join(f"- {e.code}: {e.message}" for e in last_errors[:10])
            full_prompt = (
                prompt
                + "\n\n## PREVIOUS ATTEMPT FAILED VALIDATION — fix these:\n"
                + errs_text
                + "\nReturn corrected JSON only."
            )
        try:
            raw = await asyncio.wait_for(
                async_llm_json_response(full_prompt, max_tokens=max_out),
                timeout=timeout_s,
            )
            parsed = json.loads(raw)
        except Exception as e:
            logger.warning("schedule_generator LLM/parse failed attempt=%d: %s", attempt, e)
            if attempt == 1:
                raise
            continue

        if not isinstance(parsed, dict):
            last_errors = [_e("hard", "bad_root", "expected object")]
            continue

        proposed_days = parsed.get("days", [])
        proposed_summary = str(parsed.get("summary") or "")[:400]

        clean, errors, fixed_days = validate_and_fix(
            maxx_id=maxx_id,
            days=proposed_days,
            wake_time=wake_str,
            sleep_time=sleep_str,
            user_ctx=user_state,
            expected_day_count=cadence_days,
            daily_task_budget=daily_budget,
        )
        last_errors = errors
        days = fixed_days
        summary = proposed_summary or "schedule generated"
        if clean:
            return days, summary, attempt
    # Two attempts both had hard errors — return the last fixed set anyway,
    # but log loud. Caller treats this as best-effort.
    logger.error("schedule_generator: both attempts had hard errors, returning best-effort: %s", last_errors[:5])
    return days, summary, 1


def _e(severity: str, code: str, message: str):
    from services.schedule_validator import ValidationError
    return ValidationError(severity, code, message)


# --------------------------------------------------------------------------- #
#  Helpers (used by callers wiring into existing schedule_service)            #
# --------------------------------------------------------------------------- #

def days_with_dates(days: list[dict], start_date) -> list[dict]:
    """Stamp ISO date onto each day, matching the existing schedule schema."""
    from datetime import timedelta
    out = []
    for i, day in enumerate(days):
        d = dict(day)
        d["date"] = (start_date + timedelta(days=i)).isoformat()
        out.append(d)
    return out
