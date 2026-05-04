"""LLM-driven user fact extractor that runs in the background after every
chat turn. Catches any phrasing the regex extractor misses ("i don't
really do meat", "yeah i'm in arizona right now", "lifting hasn't been
a thing for me lately").

Design:
  - Runs OFF the request critical path via FastAPI BackgroundTasks.
    The HTTP response returns immediately; this fires after.
  - Uses gpt-4o-mini with structured output for a tight ~150-300 token
    round-trip per turn (~$0.0001 each).
  - Merges into user_schedule_context.user_facts via the same merger the
    regex extractor uses. Idempotent — running twice on the same turn
    yields the same dict.
  - Confidence-gated: facts < 0.7 are dropped.
  - Recency-aware: the LLM is told to ignore transient state ("i'm
    tired today", "running late this morning") and only return durable
    facts ("i'm vegetarian", "i live in arizona").

The extractor sees the LAST 2-3 turns so it catches multi-turn context
("what's your name?" → "alex" doesn't reveal a fact alone, but
"i'm 22 and from chicago" → "from chicago" does).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


_EXTRACT_SYSTEM = """You extract DURABLE personal facts about a user from a chat turn.

OUTPUT JSON (strict shape — no markdown, no commentary):
{
  "facts": [
    {"category": "<category>", "value": "<short string>", "confidence": <0.0-1.0>},
    ...
  ]
}

CATEGORIES (use exactly one of these — others rejected):
  diet         - vegetarian, vegan, no dairy, gluten-free, lactose intolerant, etc.
  allergies    - fragrance, sulfates, niacinamide, peanuts, etc.
  body         - height (e.g. "5'10\\""), weight ("165lb"), age, body fat %
  lifestyle    - location ("lives in arizona"), schedule ("night shift"),
                 climate ("dry climate"), occupation ("desk job", "student")
  preferences  - "minimalist routine", "workout in the evening", "matte finish hair"
  dislikes     - "fades", "mewing", "scrubs", "alcohol-based products"
  health       - "eczema", "psoriasis", "on accutane", "smoker", "drinks daily"
  equipment    - "owns a dermastamp", "has a foam roller", "no gym membership"
  goals        - "wants to gain 15 lbs", "fix posture for photos"

RULES:
- ONLY extract facts the user EXPLICITLY stated about themselves.
- IGNORE transient state ("i'm tired today", "haven't slept much"), the
  bot's questions, and information the bot supplied.
- Lowercase values, ≤ 60 chars each, specific (not "wants to be healthy").
- Drop anything you'd rate < 0.7 confidence — better to miss than to
  fabricate. Empty list is the right answer most turns.
- Return at most 6 facts per turn.
- DO NOT include facts already in the EXISTING USER FACTS section — only
  add NEW ones.
"""


_VALID_CATEGORIES = {
    "diet", "allergies", "body", "lifestyle", "preferences",
    "dislikes", "health", "equipment", "goals",
}


def _build_extract_prompt(
    *, user_message: str, assistant_response: str, recent_turns: list[dict],
    existing_facts: dict[str, Any],
) -> str:
    """Compact prompt: 2-3 prior turns + this turn + existing facts."""
    history_block = ""
    if recent_turns:
        lines = []
        for t in recent_turns[-4:]:
            role = t.get("role", "?")
            content = (t.get("content") or "").strip().replace("\n", " ")[:240]
            lines.append(f"[{role}] {content}")
        history_block = "\n## RECENT TURNS (context only)\n" + "\n".join(lines) + "\n"

    facts_block = ""
    if existing_facts:
        try:
            from services.user_facts_service import format_facts_for_prompt
            f = format_facts_for_prompt(existing_facts)
            if f:
                facts_block = "\n" + f + "\n(any of these → don't repeat as 'new')\n"
        except Exception:
            facts_block = ""

    return (
        f"{_EXTRACT_SYSTEM}\n"
        f"{history_block}"
        f"{facts_block}\n"
        f"## THIS TURN — extract new facts ONLY from the user's message\n"
        f"[user] {(user_message or '').strip()[:1200]}\n"
        f"[bot]  {(assistant_response or '').strip()[:600]}\n\n"
        "Return the JSON now."
    )


async def extract_and_merge(
    *,
    user_id: str,
    user_message: str,
    assistant_response: str,
    db: AsyncSession,
) -> int:
    """Run the LLM extractor against the latest turn, merge new facts
    into the persistent context. Returns the number of facts added.

    Designed to be invoked from FastAPI BackgroundTasks — never raises;
    swallows + logs on any failure since this is best-effort enrichment.
    """
    try:
        from services.user_context_service import get_context, merge_context
        from services.user_facts_service import merge_facts, FACTS_KEY
        from services.llm_sync import async_llm_json_response
        from models.sqlalchemy_models import ChatHistory
        from uuid import UUID
    except Exception as e:
        logger.warning("async fact extractor: import failed: %s", e)
        return 0

    if not user_message or not user_message.strip():
        return 0

    # Pull a few recent turns for context (last 6, before this one).
    try:
        user_uuid = UUID(user_id)
        res = await db.execute(
            select(ChatHistory)
            .where(ChatHistory.user_id == user_uuid)
            .order_by(ChatHistory.created_at.desc())
            .limit(8)
        )
        rows = list(reversed(res.scalars().all()))
        recent = [{"role": r.role, "content": r.content} for r in rows][:-2]  # exclude latest pair
    except Exception:
        recent = []

    # Existing facts so the LLM doesn't re-emit them.
    try:
        ctx = await get_context(user_id, db)
        existing = ctx.get(FACTS_KEY) or {}
    except Exception:
        existing = {}

    prompt = _build_extract_prompt(
        user_message=user_message,
        assistant_response=assistant_response,
        recent_turns=recent,
        existing_facts=existing,
    )
    try:
        raw = await asyncio.wait_for(
            async_llm_json_response(prompt, max_tokens=400),
            timeout=15.0,
        )
        parsed = json.loads(raw)
    except Exception as e:
        logger.info("async fact extractor: LLM call failed (non-fatal): %s", e)
        return 0

    facts_list = parsed.get("facts") if isinstance(parsed, dict) else None
    if not isinstance(facts_list, list):
        return 0

    new_facts: dict[str, Any] = {}
    n_added = 0
    for f in facts_list[:6]:
        if not isinstance(f, dict):
            continue
        cat = str(f.get("category") or "").strip().lower()
        val = str(f.get("value") or "").strip().lower()
        try:
            conf = float(f.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if cat not in _VALID_CATEGORIES or not val or conf < 0.7:
            continue
        # Length cap (defensive).
        val = val[:60]
        # Body becomes a sub-dict with named keys.
        if cat == "body":
            sub_key = _body_subkey(val)
            if not sub_key:
                continue
            new_facts[f"body.{sub_key}"] = val
            n_added += 1
        elif cat in ("preferences", "dislikes", "lifestyle", "diet", "allergies",
                     "health", "equipment", "goals"):
            new_facts.setdefault(cat, [])
            if val not in new_facts[cat]:
                new_facts[cat].append(val)
                n_added += 1

    if not new_facts:
        return 0

    try:
        merged = merge_facts(existing, new_facts)
        await merge_context(user_id, {FACTS_KEY: merged}, db)
        await db.commit()
    except Exception as e:
        logger.info("async fact extractor: merge failed: %s", e)
        return 0

    logger.info("async fact extractor: added %d new facts for user %s", n_added, user_id[:8])
    return n_added


def _body_subkey(value: str) -> Optional[str]:
    """Best-effort routing of a body fact to a named slot."""
    low = value.lower()
    if re.search(r"\d+'(?:\d+\")?", value) or "tall" in low:
        return "height"
    if re.search(r"\d+\s*(?:lb|lbs|pound|kg)", low):
        return "weight"
    if "%" in low or "body fat" in low or "bf" in low:
        return "body_fat_pct"
    if re.search(r"\b\d{1,2}\s*y(ears? old)?\b", low) or "age" in low:
        return "age"
    return None
