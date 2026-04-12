"""
Seed the system_prompts table with all LLM prompt bodies.

Safe to run multiple times — uses INSERT ... ON CONFLICT (key) DO NOTHING so
existing rows are never overwritten.  To update a prompt body, edit it directly
in Supabase (the admin UI or psql) and the running app will pick it up within
the next hourly cache refresh.

Run from the backend root:
  python scripts/seed_prompts.py
"""

from __future__ import annotations

import asyncio
import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

# --- prompt constants (same sources as export_s3_prompts.py) ---
from services.bonemax_chat_prompt import BONEMAX_NEW_SCHEDULE_SYSTEM_PROMPT
from services.bonemax_notification_engine import (
    BONEMAX_COACHING_REFERENCE,
    BONEMAX_JSON_DIRECTIVES,
    BONEMAX_NOTIFICATION_ENGINE_REFERENCE,
)
from services.coaching_service import (
    _COACHING_BEDTIME_FALLBACK,
    _COACHING_CHECK_IN_GENERAL_FALLBACK,
    _COACHING_FITMAX_CHECK_IN_FALLBACK,
    _COACHING_MEMORY_COMPRESS_FALLBACK,
    _COACHING_TONE_DETECT_FALLBACK,
)
from services.fitmax_notification_engine import (
    FITMAX_COACHING_REFERENCE,
    FITMAX_JSON_DIRECTIVES,
    FITMAX_NOTIFICATION_ENGINE_REFERENCE,
)
from services.gemini_service import (
    FACE_ANALYSIS_SYSTEM_PROMPT,
    MAX_CHAT_SYSTEM_PROMPT,
    TRIPLE_FULL_SYSTEM_PROMPT,
    UMAX_TRIPLE_SYSTEM_PROMPT,
)
from services.hairmax_notification_engine import (
    HAIRMAX_COACHING_REFERENCE,
    HAIRMAX_JSON_DIRECTIVES,
    HAIRMAX_NOTIFICATION_ENGINE_REFERENCE,
)
from services.heightmax_notification_engine import (
    HEIGHTMAX_COACHING_REFERENCE,
    HEIGHTMAX_JSON_DIRECTIVES,
    HEIGHTMAX_NOTIFICATION_ENGINE_REFERENCE,
)
from services.langgraph_face_prompts import (
    LANGGRAPH_ANALYZE_FACE_METRICS_FALLBACK,
    LANGGRAPH_IMPROVEMENTS_FALLBACK,
    LANGGRAPH_VALIDATE_IMAGES_FALLBACK,
)
from services.lc_maxx_intent import _SYSTEM_PROMPT as _MAXX_INTENT_FALLBACK
from services.schedule_service import (
    MAXX_SCHEDULE_PROMPT,
    SCHEDULE_ADAPTATION_PROMPT,
    SCHEDULE_GENERATION_PROMPT,
)
from services.skinmax_notification_engine import (
    SKINMAX_COACHING_REFERENCE,
    SKINMAX_JSON_DIRECTIVES,
    SKINMAX_NOTIFICATION_ENGINE_REFERENCE,
)

# key -> (content, description)
_PROMPTS: dict[str, tuple[str, str]] = {
    "face_analysis_system":                   (FACE_ANALYSIS_SYSTEM_PROMPT,                   "Gemini face scan analysis system prompt"),
    "umax_triple_system":                     (UMAX_TRIPLE_SYSTEM_PROMPT,                     "UMax triple-module system prompt"),
    "triple_full_system":                     (TRIPLE_FULL_SYSTEM_PROMPT,                     "Full triple-module system prompt"),
    "max_chat_system":                        (MAX_CHAT_SYSTEM_PROMPT,                        "Primary Max coaching chat system prompt"),
    "bonemax_new_schedule_system":            (BONEMAX_NEW_SCHEDULE_SYSTEM_PROMPT,            "BoneMax new schedule onboarding system prompt"),
    "schedule_generation":                    (SCHEDULE_GENERATION_PROMPT,                    "Schedule generation prompt"),
    "schedule_adaptation":                    (SCHEDULE_ADAPTATION_PROMPT,                    "Schedule adaptation/update prompt"),
    "maxx_schedule":                          (MAXX_SCHEDULE_PROMPT,                          "Maxx schedule full generation prompt"),
    "coaching_memory_compress":               (_COACHING_MEMORY_COMPRESS_FALLBACK,            "Compresses long coaching conversation history"),
    "coaching_tone_detect":                   (_COACHING_TONE_DETECT_FALLBACK,                "Detects user tone/mood for coaching response"),
    "coaching_fitmax_check_in":               (_COACHING_FITMAX_CHECK_IN_FALLBACK,            "FitMax daily check-in coaching prompt"),
    "coaching_check_in_general":              (_COACHING_CHECK_IN_GENERAL_FALLBACK,           "General daily check-in coaching prompt"),
    "coaching_bedtime":                       (_COACHING_BEDTIME_FALLBACK,                    "Bedtime coaching and progress check prompt"),
    # SkinMax notification engine
    "skinmax_coaching_reference":             (SKINMAX_COACHING_REFERENCE,                    "SkinMax coaching reference snippet"),
    "skinmax_notification_engine_reference":  (SKINMAX_NOTIFICATION_ENGINE_REFERENCE,         "SkinMax full notification engine reference"),
    "skinmax_json_directives":                (SKINMAX_JSON_DIRECTIVES,                       "SkinMax JSON output directives"),
    # BoneMax notification engine
    "bonemax_coaching_reference":             (BONEMAX_COACHING_REFERENCE,                    "BoneMax coaching reference snippet"),
    "bonemax_notification_engine_reference":  (BONEMAX_NOTIFICATION_ENGINE_REFERENCE,         "BoneMax full notification engine reference"),
    "bonemax_json_directives":                (BONEMAX_JSON_DIRECTIVES,                       "BoneMax JSON output directives"),
    # HeightMax notification engine
    "heightmax_coaching_reference":           (HEIGHTMAX_COACHING_REFERENCE,                  "HeightMax coaching reference snippet"),
    "heightmax_notification_engine_reference":(HEIGHTMAX_NOTIFICATION_ENGINE_REFERENCE,        "HeightMax full notification engine reference"),
    "heightmax_json_directives":              (HEIGHTMAX_JSON_DIRECTIVES,                     "HeightMax JSON output directives"),
    # HairMax notification engine
    "hairmax_coaching_reference":             (HAIRMAX_COACHING_REFERENCE,                    "HairMax coaching reference snippet"),
    "hairmax_notification_engine_reference":  (HAIRMAX_NOTIFICATION_ENGINE_REFERENCE,         "HairMax full notification engine reference"),
    "hairmax_json_directives":                (HAIRMAX_JSON_DIRECTIVES,                       "HairMax JSON output directives"),
    # FitMax notification engine
    "fitmax_coaching_reference":              (FITMAX_COACHING_REFERENCE,                     "FitMax coaching reference snippet"),
    "fitmax_notification_engine_reference":   (FITMAX_NOTIFICATION_ENGINE_REFERENCE,          "FitMax full notification engine reference"),
    "fitmax_json_directives":                 (FITMAX_JSON_DIRECTIVES,                        "FitMax JSON output directives"),
    # LangGraph face pipeline
    "langgraph_validate_images":              (LANGGRAPH_VALIDATE_IMAGES_FALLBACK,            "LangGraph face scan: validate uploaded images"),
    "langgraph_analyze_face_metrics":         (LANGGRAPH_ANALYZE_FACE_METRICS_FALLBACK,       "LangGraph face scan: analyse facial metrics"),
    "langgraph_improvements":                 (LANGGRAPH_IMPROVEMENTS_FALLBACK,               "LangGraph face scan: generate improvement recommendations"),
    # Previously hardcoded-only prompts
    "maxx_intent_system":                     (_MAXX_INTENT_FALLBACK,                         "LangChain Maxx module intent router/classifier"),
    "groq_face_analyzer":                     ("You are a helpful assistant that outputs JSON.", "Groq LLM system message for facial analysis recommendations"),
}


async def _ensure_table() -> None:
    """Create system_prompts table if it does not exist yet."""
    from db.sqlalchemy import engine
    from models.sqlalchemy_models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed() -> None:
    from db.sqlalchemy import AsyncSessionLocal
    from sqlalchemy import text

    await _ensure_table()

    async with AsyncSessionLocal() as session:
        inserted = 0
        skipped = 0
        for key, (content, description) in _PROMPTS.items():
            result = await session.execute(
                text(
                    """
                    INSERT INTO system_prompts (key, content, description, is_active, created_at, updated_at)
                    VALUES (:key, :content, :description, true, now(), now())
                    ON CONFLICT (key) DO NOTHING
                    """
                ),
                {"key": key, "content": content, "description": description},
            )
            if result.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        await session.commit()

    print(f"Done: {inserted} inserted, {skipped} already existed (skipped).")
    print("Total prompts registered:", len(_PROMPTS))


if __name__ == "__main__":
    asyncio.run(seed())
