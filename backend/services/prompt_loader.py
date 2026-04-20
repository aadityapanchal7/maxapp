"""
Load LLM / coaching prompts from the Supabase `system_prompts` table.

Prompts are loaded into an in-process cache at startup and refreshed every hour
by the APScheduler job in scheduler_job.py.  If the DB is unavailable the cache
retains its last-known-good state; on a cold start with no DB the hardcoded
fallback strings are returned by resolve_prompt().

Keys (match the `key` column in system_prompts and the PromptKey constants below):
  face_analysis_system, umax_triple_system, triple_full_system, max_chat_system,
  bonemax_new_schedule_system, schedule_generation, schedule_adaptation, maxx_schedule,
  coaching_memory_compress, coaching_tone_detect, coaching_fitmax_check_in,
  coaching_check_in_general, coaching_bedtime,
  skinmax_*, bonemax_*, heightmax_*, hairmax_*, fitmax_* with suffixes
    _coaching_reference, _notification_engine_reference, _json_directives,
  langgraph_validate_images, langgraph_analyze_face_metrics, langgraph_improvements,
  maxx_intent_system, groq_face_analyzer
"""

from __future__ import annotations

import logging

from sqlalchemy import select

logger = logging.getLogger(__name__)

_CACHE: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Stable key constants used by callers and the seed script
# ---------------------------------------------------------------------------
class PromptKey:
    FACE_ANALYSIS_SYSTEM = "face_analysis_system"
    UMAX_TRIPLE_SYSTEM = "umax_triple_system"
    TRIPLE_FULL_SYSTEM = "triple_full_system"
    MAX_CHAT_SYSTEM = "max_chat_system"
    BONEMAX_NEW_SCHEDULE_SYSTEM = "bonemax_new_schedule_system"
    SCHEDULE_GENERATION = "schedule_generation"
    SCHEDULE_ADAPTATION = "schedule_adaptation"
    MAXX_SCHEDULE = "maxx_schedule"
    COACHING_MEMORY_COMPRESS = "coaching_memory_compress"
    COACHING_TONE_DETECT = "coaching_tone_detect"
    COACHING_FITMAX_CHECK_IN = "coaching_fitmax_check_in"
    COACHING_CHECK_IN_GENERAL = "coaching_check_in_general"
    COACHING_BEDTIME = "coaching_bedtime"
    # Maxx notification engines
    SKINMAX_COACHING_REFERENCE = "skinmax_coaching_reference"
    SKINMAX_NOTIFICATION_ENGINE_REFERENCE = "skinmax_notification_engine_reference"
    SKINMAX_JSON_DIRECTIVES = "skinmax_json_directives"
    BONEMAX_COACHING_REFERENCE = "bonemax_coaching_reference"
    BONEMAX_NOTIFICATION_ENGINE_REFERENCE = "bonemax_notification_engine_reference"
    BONEMAX_JSON_DIRECTIVES = "bonemax_json_directives"
    HEIGHTMAX_COACHING_REFERENCE = "heightmax_coaching_reference"
    HEIGHTMAX_NOTIFICATION_ENGINE_REFERENCE = "heightmax_notification_engine_reference"
    HEIGHTMAX_JSON_DIRECTIVES = "heightmax_json_directives"
    HAIRMAX_COACHING_REFERENCE = "hairmax_coaching_reference"
    HAIRMAX_NOTIFICATION_ENGINE_REFERENCE = "hairmax_notification_engine_reference"
    HAIRMAX_JSON_DIRECTIVES = "hairmax_json_directives"
    FITMAX_COACHING_REFERENCE = "fitmax_coaching_reference"
    FITMAX_NOTIFICATION_ENGINE_REFERENCE = "fitmax_notification_engine_reference"
    FITMAX_JSON_DIRECTIVES = "fitmax_json_directives"
    # LangGraph face workflow
    LANGGRAPH_VALIDATE_IMAGES = "langgraph_validate_images"
    LANGGRAPH_ANALYZE_FACE_METRICS = "langgraph_analyze_face_metrics"
    LANGGRAPH_IMPROVEMENTS = "langgraph_improvements"
    # Previously hardcoded-only prompts — now DB-managed
    MAXX_INTENT_SYSTEM = "maxx_intent_system"
    GROQ_FACE_ANALYZER = "groq_face_analyzer"
    # RAG answer system prompt — the grounding rules for KNOWLEDGE turns that
    # bypass the full agent. Loaded from Supabase; the module-specific coaching
    # reference is appended at runtime based on the query classification.
    RAG_ANSWER_SYSTEM = "rag_answer_system"


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

async def refresh_prompt_cache() -> None:
    """Load all is_active=True prompts from system_prompts into _CACHE.

    Called at app startup (main.py lifespan) and every hour by the scheduler.
    On DB failure: logs the error and retains the stale cache so the app
    continues serving the last-known-good prompts without a crash.
    """
    from db.sqlalchemy import AsyncSessionLocal
    from models.sqlalchemy_models import SystemPrompt

    try:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(SystemPrompt).where(SystemPrompt.is_active == True)  # noqa: E712
                )
            ).scalars().all()
        new_cache = {row.key: row.content for row in rows}
        # Atomic swap — no await between clear and update so no coroutine can
        # observe a partially-populated cache.
        _CACHE.clear()
        _CACHE.update(new_cache)
        logger.info("Prompt cache refreshed: %d prompts loaded", len(new_cache))
    except Exception as exc:
        logger.error(
            "Failed to refresh prompt cache from DB: %s — retaining stale cache", exc
        )


def resolve_prompt(key: str, fallback: str) -> str:
    """Return the cached prompt for *key*, or *fallback* if the key is absent.

    Pure dict lookup — O(1), no I/O, safe to call from sync or async code.
    The fallback is the hardcoded constant defined in each service module;
    it is used only when the DB has not been seeded or is temporarily unavailable.
    """
    result = _CACHE.get(key)
    if result is not None:
        return result
    logger.debug("Prompt key %r not in cache, using hardcoded fallback", key)
    return fallback


def clear_prompt_cache() -> None:
    """Clear the in-process cache.  Used by tests and manual reload hooks."""
    _CACHE.clear()
