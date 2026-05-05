"""
Chat API - Max LLM Chat
Handles AI chat with tool-calling, coaching state, check-in parsing, and memory.
The core logic lives in process_chat_message() so it can be reused by the SMS webhook.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from db import get_db, get_rds_db_optional
from middleware.auth_middleware import require_paid_user
from models.leaderboard import ChatRequest, ChatResponse
from models.sqlalchemy_models import ChatHistory, Scan, User, UserSchedule
from services.coaching_service import coaching_service
from services.chat_telemetry import fast_path_snapshot, note_chat_turn
from services.lc_agent import make_chat_tools, run_chat_agent
from services.lc_memory import history_dicts_to_lc_messages
from services.nutrition_service import nutrition_service
from services.storage_service import storage_service
from services.intent_classifier import classify_turn
from services.fast_rag_answer import answer_from_rag
from services.fast_product_links import product_links_from_context, product_brands_for_module
from services.bonemax_chat_prompt import BONEMAX_NEW_SCHEDULE_SYSTEM_PROMPT
from services.maxx_guidelines import SKINMAX_PROTOCOLS, resolve_skin_concern
from services.prompt_loader import PromptKey, resolve_prompt
from services.fitmax_plan import (
    fitmax_build_plan as _fitmax_build_plan,
    seed_fitmax_profile_from_onboarding as _fitmax_seed_profile_from_onboarding,
)
from services.rag_service import retrieve_chunks as rag_retrieve_chunks
from services.persona_prompts import tone_preamble
from services.partner_rules_service import get_matching_rule_suffix
from config import settings

logger = logging.getLogger(__name__)

# LangChain agent history + background memory/tone use the same window.
CHAT_HISTORY_WINDOW = 15

# Schedule setup: wake/sleep come from signup / profile only -- never re-ask in chat.
_WAKE_SLEEP_NEVER_ASK = (
    "WAKE_TIME & SLEEP_TIME -- NEVER ask the user in this flow. Read wake_time and sleep_time from "
    "user_context.onboarding / GLOBAL ONBOARDING (includes schedule_preferences merge). "
    "If either field is missing, pass wake_time=07:00 and sleep_time=23:00 in generate_maxx_schedule without asking."
)


def _friendly_llm_error_message(llm_err: BaseException) -> str:
    """After primary+fallback LLM both fail, map quota/rate errors to clearer copy."""
    if isinstance(llm_err, TimeoutError):
        return str(llm_err) or (
            "The assistant took too long -- please try again. Your message was saved."
        )
    blob = f"{type(llm_err).__name__} {llm_err}".lower()
    if any(
        x in blob
        for x in (
            "429",
            "quota",
            "resourceexhausted",
            "insufficient_quota",
            "rate_limit",
            "ratelimit",
            "too many requests",
        )
    ):
        return (
            "The AI service hit a usage or billing limit (not your Wi‑Fi). "
            "Try again in a few minutes. If it keeps happening, the server needs fresh API quota "
            "for Gemini and/or OpenAI. Your message was saved."
        )
    return (
        "I'm having trouble reaching my brain right now -- please try again "
        "in a moment. Your message was saved."
    )


def _chunk_audit_refs(chunks: list[dict]) -> list[str] | None:
    refs: list[str] = []
    for chunk in chunks or []:
        if not isinstance(chunk, dict):
            continue
        ref = str(chunk.get("id") or "").strip()
        if not ref:
            meta = chunk.get("metadata") or {}
            source = str(meta.get("source") or chunk.get("doc_title") or "").strip()
            section = str(meta.get("section") or chunk.get("chunk_index") or "").strip()
            if source:
                ref = f"{source}::{section}" if section else source
        if ref and ref not in refs:
            refs.append(ref)
    return refs or None


def _coerce_chat_maxx_id(raw: Optional[str]) -> Optional[str]:
    """Normalize init_context / inferred maxx id so HairMax, hair-max, etc. hit the right SYSTEM branch."""
    if not raw:
        return None
    s = re.sub(r"[\s\-_]+", "", str(raw).strip().lower())
    for mid in ("skinmax", "hairmax", "heightmax", "fitmax", "bonemax"):
        if s == mid:
            return mid
    return str(raw).strip().lower()


def _coerce_chat_intent(raw: Optional[str]) -> Optional[str]:
    """Normalize optional client-supplied chat intent."""
    if not raw:
        return None
    s = re.sub(r"[\s\-_]+", "", str(raw).strip().lower())
    if s == "startschedule":
        return "start_schedule"
    return None


def _looks_like_link_request(text: str) -> bool:
    s = (text or "").lower()
    return (
        "amazon" in s
        or "link" in s
        or "links" in s
        or "where can i buy" in s
        or "buy this" in s
    )


def _looks_like_brand_request(text: str) -> bool:
    s = (text or "").lower()
    return (
        "brand" in s
        or "brands" in s
        or "what should i buy" in s
        or "what to buy" in s
        or "product rec" in s
        or "product recommendation" in s
    )


def _expire_stale_chat_pending(profile: dict) -> bool:
    """Drop chat_pending_module if older than TTL. Returns True if profile was mutated."""
    mod = str(profile.get("chat_pending_module") or "").strip()
    if not mod:
        return False
    at_raw = profile.get("chat_pending_module_at")
    stale = False
    if not at_raw:
        stale = True
    else:
        try:
            at_s = str(at_raw).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(at_s)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - parsed > timedelta(hours=8):
                stale = True
        except Exception:
            stale = True
    if stale:
        profile.pop("chat_pending_module", None)
        profile.pop("chat_pending_module_at", None)
        return True
    return False


def _looks_like_fitmax_activation_message(text: str) -> bool:
    t = (text or "").lower()
    return "fitmax" in t or "fit max" in t


def _looks_like_completed_tasks_question(text: str) -> bool:
    t = (text or "").lower().strip()
    if len(t) > 160:
        return False
    needles = (
        "completed today",
        "complete today",
        "finished today",
        "tasks have i",
        "task have i",
        "checked off",
        "check off today",
        "knocked out today",
        "what did i do today",
        "what have i done today",
        "did i complete",
        "did i finish",
        "how many tasks",
        "tasks done today",
        "stuff i finished",
    )
    return any(n in t for n in needles)


async def _reply_today_completed_tasks_summary(user_id: str, onboarding: dict, db: AsyncSession) -> str:
    from zoneinfo import ZoneInfo

    from services.schedule_service import schedule_service

    tz_name = (onboarding or {}).get("timezone") or "UTC"
    try:
        user_tz = ZoneInfo(str(tz_name))
    except Exception:
        user_tz = ZoneInfo("UTC")
    today_iso = datetime.now(user_tz).date().isoformat()
    schedules = await schedule_service.get_all_active_schedules(user_id, db)
    lines: list[str] = []
    for s in schedules:
        label = s.get("maxx_id") or s.get("course_title") or "program"
        for day in s.get("days") or []:
            if day.get("date") != today_iso:
                continue
            for t in day.get("tasks") or []:
                if str(t.get("status", "")).lower() == "completed":
                    tm = t.get("time") or "?"
                    tit = (t.get("title") or "task").strip()
                    lines.append(f"- {tm} {tit} ({label})")
    if not lines:
        return (
            "nothing's marked complete yet today across your active schedules. "
            "when you check off tasks in the app, i can recap them here too."
        )
    body = "\n".join(lines[:15])
    extra = f"\n…+{len(lines) - 15} more" if len(lines) > 15 else ""
    return f"here's what you checked off today:\n{body}{extra}"


_TECH_LEAK_PATTERNS: tuple[re.Pattern, ...] = (
    # Python-style stack-trace markers — never appropriate in chat output.
    re.compile(r"traceback\s*\(.*?\):", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*file\s+['\"][^'\"]+['\"]\s*,\s*line\s+\d+.*$", re.IGNORECASE | re.MULTILINE),
    # Common exception class names that leak into LLM-rephrased errors.
    re.compile(r"\b(?:asyncio|sqlalchemy|httpx|openai|anthropic|google\.generativeai)\.[a-z_.]+\b", re.IGNORECASE),
    re.compile(r"\b(?:HTTPException|ValueError|KeyError|TypeError|AttributeError|JSONDecodeError|ConnectionError)\b"),
    # System-prompt leak markers — these should NEVER reach the user.
    re.compile(r"\[SYSTEM[: ][^\]]*\]"),
    re.compile(r"\bcatalog_id\b\s*[:=]"),
    re.compile(r"\b(?:user_state|user_ctx|onboarding_pending)\b"),
    # Internal status / debug noise from earlier prompt iterations.
    re.compile(r"^\s*(?:debug|status|trace|warning):\s*.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\b(?:exception|error)\s*:\s*[A-Za-z][\w.]*", re.IGNORECASE),
    # Bare URLs to internal endpoints.
    re.compile(r"https?://(?:localhost|127\.0\.0\.1|nlzsqnlk[a-z]+\.supabase\.co)\S*", re.IGNORECASE),
)


def _scrub_tech_leak(text: str) -> str:
    """Strip code-shaped strings, stack-trace fragments, system-prompt
    markers, and internal endpoints from chat output before the user
    sees them. Defensive — the LLM prompt forbids leaking these, but a
    flaky generation occasionally lets one through and the user shouldn't
    see "[SYSTEM: schedule setup]" or "asyncio.exceptions.TimeoutError"
    in their chat.
    """
    if not text:
        return text
    out = text
    for pat in _TECH_LEAK_PATTERNS:
        out = pat.sub("", out)
    # Collapse double spaces / orphan whitespace from the cuts.
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _finalize_assistant_message(text: str) -> str:
    """User-facing chat: scrub any technical leak, drop markdown
    asterisks, lowercase Max voice."""
    if not text:
        return text
    return _scrub_tech_leak(text).replace("*", "").lower()


router = APIRouter(prefix="/chat", tags=["Chat"])

FITMAX_REQUIRED_FIELDS = [
    "goal",
    "experience_level",
    "height_cm",
    "weight_kg",
    "age",
    "biological_sex",
    "equipment",
    "days_per_week",
    "session_minutes",
    "daily_activity_level",
    "dietary_restrictions",
]

FITMAX_FOOD_DB = {
    "mcdonalds mcchicken": {"calories": 400, "protein_g": 14, "carbs_g": 39, "fat_g": 21},
    "mcchicken": {"calories": 400, "protein_g": 14, "carbs_g": 39, "fat_g": 21},
    "apple": {"calories": 95, "protein_g": 1, "carbs_g": 25, "fat_g": 0},
    "banana": {"calories": 105, "protein_g": 1, "carbs_g": 27, "fat_g": 0},
    "egg": {"calories": 78, "protein_g": 6, "carbs_g": 1, "fat_g": 5},
    "eggs": {"calories": 78, "protein_g": 6, "carbs_g": 1, "fat_g": 5},
    "oatmeal": {"calories": 150, "protein_g": 5, "carbs_g": 27, "fat_g": 3},
    "chicken breast": {"calories": 165, "protein_g": 31, "carbs_g": 0, "fat_g": 4},
    "greek yogurt": {"calories": 130, "protein_g": 17, "carbs_g": 6, "fat_g": 0},
    "whey protein": {"calories": 120, "protein_g": 24, "carbs_g": 3, "fat_g": 2},
}

FITMAX_HEURISTIC_DISHES = {
    "tomato soup": {"calories": 170, "protein_g": 4, "carbs_g": 27, "fat_g": 5},
    "soup": {"calories": 190, "protein_g": 6, "carbs_g": 25, "fat_g": 7},
    "salad": {"calories": 240, "protein_g": 8, "carbs_g": 18, "fat_g": 15},
    "pasta": {"calories": 520, "protein_g": 18, "carbs_g": 78, "fat_g": 16},
    "rice bowl": {"calories": 560, "protein_g": 24, "carbs_g": 72, "fat_g": 18},
    "burrito": {"calories": 700, "protein_g": 30, "carbs_g": 74, "fat_g": 31},
    "sandwich": {"calories": 430, "protein_g": 20, "carbs_g": 42, "fat_g": 19},
    "burger": {"calories": 520, "protein_g": 26, "carbs_g": 41, "fat_g": 27},
    "pizza": {"calories": 285, "protein_g": 12, "carbs_g": 36, "fat_g": 10},
    "stir fry": {"calories": 480, "protein_g": 24, "carbs_g": 42, "fat_g": 23},
    "curry": {"calories": 520, "protein_g": 20, "carbs_g": 46, "fat_g": 28},
    "noodles": {"calories": 500, "protein_g": 16, "carbs_g": 78, "fat_g": 14},
}


def _fitmax_missing_fields(profile: dict) -> list[str]:
    return [f for f in FITMAX_REQUIRED_FIELDS if profile.get(f) in (None, "", [])]


FITMAX_QUESTION_MAP: dict[str, tuple[str, list[str]]] = {
    "goal": (
        "what's your main goal right now -- fat loss, muscle gain, recomp, maintenance, or performance?",
        ["fat loss", "muscle gain", "recomp", "maintenance", "performance"],
    ),
    "experience_level": (
        "what's your training experience level: beginner, intermediate, or advanced?",
        ["beginner", "intermediate", "advanced"],
    ),
    "height_cm": ("quick stats check -- what's your height (cm or ft/in)?", []),
    "weight_kg": ("what's your current body weight?", []),
    "age": ("how old are you?", []),
    "biological_sex": (
        "what's your biological sex (male/female)?",
        ["male", "female"],
    ),
    "equipment": (
        "what do you have available to train with?",
        ["full gym", "dumbbells", "no equipment"],
    ),
    "days_per_week": (
        "how many days per week can you realistically train?",
        ["3", "4", "5", "6"],
    ),
    "session_minutes": (
        "what session length can you commit to most days (minutes)?",
        ["30", "45", "60", "90"],
    ),
    "daily_activity_level": (
        "outside the gym, what's your daily activity like: sedentary, lightly active, moderately active, or very active?",
        ["sedentary", "lightly active", "moderately active", "very active"],
    ),
    "dietary_restrictions": (
        "any dietary restrictions i should account for?",
        ["none", "vegan", "vegetarian", "gluten-free", "lactose-free"],
    ),
}


def _fitmax_next_question(profile: dict) -> str:
    missing = _fitmax_missing_fields(profile)
    if not missing:
        return ""
    return FITMAX_QUESTION_MAP[missing[0]][0]


def _fitmax_next_choices(profile: dict) -> list[str]:
    """Return quick-reply button labels for the next missing FitMax field."""
    missing = _fitmax_missing_fields(profile)
    if not missing:
        return []
    return list(FITMAX_QUESTION_MAP[missing[0]][1])


def _to_cm_from_text(text: str) -> Optional[float]:
    s = (text or "").lower()
    ft_in = re.search(r"(\d{1,2})\s*(?:ft|')\s*(\d{1,2})?\s*(?:in|\")?", s)
    if ft_in:
        ft = int(ft_in.group(1))
        inches = int(ft_in.group(2) or 0)
        return round((ft * 30.48) + (inches * 2.54), 1)
    cm = re.search(r"(\d{3}(?:\.\d+)?)\s*cm", s)
    if cm:
        return float(cm.group(1))
    if re.search(r"\b(1[4-9]\d|2[0-2]\d)\b", s):
        value = float(re.search(r"\b(1[4-9]\d|2[0-2]\d)\b", s).group(1))
        return value
    return None


def _to_kg_from_text(text: str) -> Optional[float]:
    s = (text or "").lower()
    lbs = re.search(r"(\d{2,3}(?:\.\d+)?)\s*(?:lb|lbs|pounds?)", s)
    if lbs:
        return round(float(lbs.group(1)) * 0.45359237, 1)
    kg = re.search(r"(\d{2,3}(?:\.\d+)?)\s*kg", s)
    if kg:
        return float(kg.group(1))
    plain = re.search(r"\b(\d{2,3}(?:\.\d+)?)\b", s)
    if plain:
        return float(plain.group(1))
    return None


def _parse_days_per_week_reply(text: str) -> Optional[int]:
    """Parse training days (1–7) from short answers like '3', 'five', '5 days', '3-4', '5+', 'gym\\n3'."""
    raw = (text or "").strip()
    if not raw:
        return None
    s = raw.lower()
    wmap = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
    if s in wmap:
        return wmap[s]
    if re.fullmatch(r"([1-7])\.?", s):
        return int(s[0])
    if re.search(r"\b5\+|5\s*plus|6\s*[-–]\s*7|every\s*day|daily\b|all\s*week\b", s):
        return 6
    if re.search(r"\b3\s*[-–]\s*4\b|three\s+or\s+four\b", s):
        return 4
    if re.search(r"\b1\s*[-–]\s*2\b|one\s+or\s+two\b", s):
        return 2
    m = re.search(
        r"\b([1-7])\s*(?:days?|d/w|times?|x|sessions?)(?:\s*(?:per|a|\/)\s*(?:week|wk))?\b",
        s,
    )
    if m:
        return int(m.group(1))
    m2 = re.search(
        r"\b(one|two|three|four|five|six|seven)\s*(?:days?|times?)?(?:\s*(?:per|a)\s*week)?\b",
        s,
    )
    if m2 and m2.group(1) in wmap:
        return wmap[m2.group(1)]
    # Last non-empty line: "gym" then user sends "3", or combined "gym\n3"
    for line in reversed(s.splitlines()):
        line = line.strip()
        if not line:
            continue
        low = line.lower()
        if low in wmap:
            return wmap[low]
        if re.fullmatch(r"[1-7]\.?", line):
            return int(line[0])
    return None


HAIRMAX_REQUIRED_FIELDS = ["hair_type", "scalp_state", "daily_styling", "thinning"]


def _hairmax_missing_fields(profile: dict) -> list[str]:
    return [f for f in HAIRMAX_REQUIRED_FIELDS if profile.get(f) in (None, "", [])]


HAIRMAX_QUESTION_MAP: dict[str, tuple[str, list[str]]] = {
    "hair_type": (
        "what's your hair type -- straight, wavy, curly, or coily?",
        ["straight", "wavy", "curly", "coily"],
    ),
    "scalp_state": (
        "how's your scalp: normal, dry/flaky, oily/greasy, or itchy?",
        ["normal", "dry/flaky", "oily/greasy", "itchy"],
    ),
    "daily_styling": (
        "do you use hair products or styling most days? yes or no.",
        ["yes", "no"],
    ),
    "thinning": (
        "noticing any thinning or receding hairline? yes or no.",
        ["yes", "no"],
    ),
}


BONEMAX_REQUIRED_FIELDS = [
    "workout_frequency",
    "tmj_history",
    "mastic_gum_regular",
    "heavy_screen_time",
]


def _bonemax_missing_fields(profile: dict) -> list[str]:
    missing: list[str] = []
    wf = _coerce_to_choice(str(profile.get("workout_frequency") or ""), ["0", "1-2", "3-4", "5+"])
    if not wf:
        missing.append("workout_frequency")
    if not _yes_no_answered(profile.get("tmj_history")):
        missing.append("tmj_history")
    if not _yes_no_answered(profile.get("mastic_gum_regular")):
        missing.append("mastic_gum_regular")
    if not _yes_no_answered(profile.get("heavy_screen_time")):
        missing.append("heavy_screen_time")
    return missing


BONEMAX_QUESTION_MAP: dict[str, tuple[str, list[str]]] = {
    "workout_frequency": (
        "how many days per week do you usually work out?",
        ["0", "1-2", "3-4", "5+"],
    ),
    "tmj_history": (
        "have you ever had tmj, jaw pain, or clicking?",
        ["yes", "no"],
    ),
    "mastic_gum_regular": (
        "do you already chew mastic or hard gum regularly?",
        ["yes", "no"],
    ),
    "heavy_screen_time": (
        "do you spend many hours a day on a computer or phone?",
        ["yes", "no"],
    ),
}


def _bonemax_next_question(profile: dict) -> str:
    missing = _bonemax_missing_fields(profile)
    if not missing:
        return ""
    return BONEMAX_QUESTION_MAP[missing[0]][0]


def _bonemax_next_choices(profile: dict) -> list[str]:
    missing = _bonemax_missing_fields(profile)
    if not missing:
        return []
    return list(BONEMAX_QUESTION_MAP[missing[0]][1])


def _extract_bonemax_updates(message: str, current: dict) -> dict:
    updates: dict = {}
    missing = _bonemax_missing_fields(current)
    if not missing:
        return updates
    nxt = missing[0]
    _, choices = BONEMAX_QUESTION_MAP.get(nxt, ("", []))
    if choices:
        coerced = _coerce_to_choice(message, choices)
        if coerced is not None:
            updates[nxt] = coerced
    return updates


def _hairmax_next_question(profile: dict) -> str:
    missing = _hairmax_missing_fields(profile)
    if not missing:
        return ""
    return HAIRMAX_QUESTION_MAP[missing[0]][0]


def _hairmax_next_choices(profile: dict) -> list[str]:
    """Return quick-reply button labels for the next missing HairMax field."""
    missing = _hairmax_missing_fields(profile)
    if not missing:
        return []
    return list(HAIRMAX_QUESTION_MAP[missing[0]][1])


def _extract_hairmax_updates(message: str, current: dict) -> dict:
    s = (message or "").strip().lower()
    updates: dict = {}

    hair_types = {
        "straight": "straight", "wavy": "wavy", "curly": "curly", "coily": "coily",
        "coarse": "coily", "kinky": "coily",
    }
    for kw, val in hair_types.items():
        if kw in s:
            updates["hair_type"] = val
            break

    scalp_map = {
        "normal": "normal", "healthy": "normal",
        "dry": "dry/flaky", "flaky": "dry/flaky", "dandruff": "dry/flaky",
        "oily": "oily/greasy", "greasy": "oily/greasy",
        "itchy": "itchy", "irritated": "itchy",
    }
    for kw, val in scalp_map.items():
        if kw in s:
            updates["scalp_state"] = val
            break

    yes_words = ("yes", "y", "yeah", "yep", "yea", "sure", "definitely", "for sure")
    no_words = ("no", "n", "nope", "nah", "not really", "none", "minimal", "barely")

    if "daily_styling" not in current or current.get("daily_styling") in (None, "", []):
        for w in yes_words:
            if re.search(rf"\b{re.escape(w)}\b", s):
                updates["daily_styling"] = "yes"
                break
        if "daily_styling" not in updates:
            for w in no_words:
                if re.search(rf"\b{re.escape(w)}\b", s):
                    updates["daily_styling"] = "no"
                    break

    if "thinning" not in current or current.get("thinning") in (None, "", []):
        for w in yes_words:
            if re.search(rf"\b{re.escape(w)}\b", s):
                updates["thinning"] = "yes"
                break
        if "thinning" not in updates:
            for w in no_words:
                if re.search(rf"\b{re.escape(w)}\b", s):
                    updates["thinning"] = "no"
                    break

    return updates


def _hairmax_seed_profile_from_onboarding(profile: dict, ob: dict) -> dict:
    """Pre-fill HairMax chat profile from global onboarding answers."""
    out = dict(profile or {})
    ob = ob or {}
    for key in HAIRMAX_REQUIRED_FIELDS:
        if out.get(key) not in (None, "", []):
            continue
        v = ob.get(key)
        if v is not None and str(v).strip():
            out[key] = str(v).strip()
    hcl = str(ob.get("hair_current_loss") or "").strip().lower()
    if out.get("thinning") in (None, "", []) and hcl:
        if any(w in hcl for w in ("yes", "yeah", "yep", "reced", "thin", "losing", "balding", "some")):
            out["thinning"] = "yes"
        elif any(w in hcl for w in ("no", "nope", "not ", "none", "minimal")):
            out["thinning"] = "no"
    return out


def _bonemax_seed_profile_from_onboarding(profile: dict, ob: dict) -> dict:
    """Pre-fill BoneMax scripted intake from onboarding answers."""
    out = dict(profile or {})
    ob = ob or {}
    if out.get("workout_frequency") in (None, "", []):
        wf = _coerce_to_choice(str(ob.get("bonemax_workout_frequency") or ""), ["0", "1-2", "3-4", "5+"])
        if wf:
            out["workout_frequency"] = wf
    for key in ("tmj_history", "mastic_gum_regular", "heavy_screen_time"):
        if out.get(key) not in (None, "", []):
            continue
        val = _normalize_hair_yes_no(ob.get(f"bonemax_{key}"))
        if val:
            out[key] = val
    return out


def _hairmax_setup_stale(profile: dict, hours: float = 24) -> bool:
    at = (profile or {}).get("hairmax_chat_setup_at")
    if not at:
        return False
    try:
        at_s = str(at).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(at_s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - parsed > timedelta(hours=hours)
    except Exception:
        return True


def _assistant_last_turn_is_hairmax_onboarding(history: list) -> bool:
    """True if the latest assistant message looks like scripted HairMax intake."""
    for h in reversed(history or []):
        if h.get("role") != "assistant":
            continue
        c = (h.get("content") or "").lower()
        needles = (
            "welcome to hairmax",
            "setting up your hairmax",
            "hair type",
            "straight, wavy, curly, or coily",
            "how's your scalp",
            "normal, dry/flaky, oily/greasy, or itchy",
            "hair products or styling",
            "thinning or receding",
        )
        return any(n in c for n in needles)
    return False


def _fitmax_setup_stale(profile: dict, hours: float = 24) -> bool:
    at = (profile or {}).get("fitmax_chat_setup_at")
    if not at:
        return False
    try:
        at_s = str(at).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(at_s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - parsed > timedelta(hours=hours)
    except Exception:
        return True


def _assistant_last_turn_is_fitmax_onboarding(history: list) -> bool:
    """True if the latest assistant message looks like scripted FitMax intake (app thread)."""
    for h in reversed(history or []):
        if h.get("role") != "assistant":
            continue
        c = (h.get("content") or "").lower()
        needles = (
            "welcome to fitmax",
            "what's your main goal right now",
            "training experience level",
            "height (cm or ft/in)",
            "current body weight",
            "how old are you",
            "biological sex",
            "what do you have available to train",
            "how many days per week can you realistically train",
            "session length can you commit",
            "outside the gym, what's your daily activity",
            "dietary restrictions",
        )
        return any(n in c for n in needles)
    return False


def _bonemax_setup_stale(profile: dict, hours: float = 24) -> bool:
    at = (profile or {}).get("bonemax_chat_setup_at")
    if not at:
        return False
    try:
        at_s = str(at).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(at_s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - parsed > timedelta(hours=hours)
    except Exception:
        return True


def _assistant_last_turn_is_bonemax_onboarding(history: list) -> bool:
    """True if latest assistant turn looks like scripted BoneMax intake."""
    for h in reversed(history or []):
        if h.get("role") != "assistant":
            continue
        c = (h.get("content") or "").lower()
        needles = (
            "setting up your bonemax schedule",
            "how many days per week do you usually work out",
            "tmj, jaw pain, or clicking",
            "mastic or hard gum regularly",
            "many hours a day on a computer or phone",
        )
        return any(n in c for n in needles)
    return False


def _parse_session_minutes_reply(text: str) -> Optional[int]:
    """Parse session length when user sends '45', '60', '90 min', etc."""
    s = (text or "").strip().lower()
    if not s:
        return None
    m = re.fullmatch(r"(\d{2,3})\s*(?:min|mins|minutes?)?\.?", s)
    if m:
        v = int(m.group(1))
        if 20 <= v <= 180:
            return v
    return None


# --- Generic fuzzy choice coercion ----------------------------------------
# Used by the onboarding extractors to accept natural-language replies that
# logically map to one of the offered choices ("3" -> "3-4", "i lift weights"
# -> "dumbbells", "thinning a bit" -> "yes"). Replaces previous strict-equal
# matching that caused infinite re-ask loops when users typed valid-but-not-
# exact answers.
_CHOICE_ALIASES: dict[str, dict[str, str]] = {
    # Map of choice-canonical-form -> {alias_token: same canonical}.
    # All keys + alias tokens are lowercase. Multi-word aliases use spaces.
    "yes": {
        "yes": "yes", "y": "yes", "yeah": "yes", "yep": "yes", "yea": "yes",
        "sure": "yes", "definitely": "yes", "for sure": "yes", "true": "yes",
        "correct": "yes", "kinda": "yes", "a bit": "yes", "some": "yes",
        "noticing": "yes", "a little": "yes",
    },
    "no": {
        "no": "no", "n": "no", "nope": "no", "nah": "no", "not really": "no",
        "none": "no", "minimal": "no", "barely": "no", "false": "no",
    },
    "male": {"male": "male", "m": "male", "man": "male", "guy": "male", "boy": "male"},
    "female": {"female": "female", "f": "female", "woman": "female", "girl": "female"},
}


def _coerce_to_choice(
    text: str,
    choices: list[str],
    *,
    aliases: Optional[dict[str, str]] = None,
) -> Optional[str]:
    """Best-effort match `text` to one of `choices`. Returns None if no match.

    Strategy (highest-confidence first):
      1. Exact match (after lower+strip).
      2. Alias dictionary (caller-provided + global yes/no/sex aliases).
      3. Substring: a choice token that fully appears in the text wins.
      4. Numeric coercion against ranges ("3" -> "3-4", "5" -> "5+").
      5. Token overlap: pick the choice with the most tokens covered by text.

    The point is: if the user's reply *logically fits* a category, accept it.
    Reject only when nothing plausibly maps. Never trap them in a loop on a
    legitimate answer.
    """
    raw = (text or "").strip().lower()
    if not raw or not choices:
        return None
    norm_choices = [c.lower() for c in choices]

    # 0. Number-word substitution — "three" -> "3" so the rest of the
    # pipeline (range coercion, exact match) can handle word-form replies.
    _NUM_WORDS = {
        "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    }
    for word, digit in _NUM_WORDS.items():
        raw = re.sub(rf"\b{word}\b", digit, raw)

    # 1. Exact
    if raw in norm_choices:
        return choices[norm_choices.index(raw)]

    # 2. Aliases — exact OR substring (so "a little thinning" still hits
    # the "a little" -> "yes" alias).
    merged_aliases: dict[str, str] = {}
    for canonical_map in _CHOICE_ALIASES.values():
        for alias, canon in canonical_map.items():
            if canon.lower() in norm_choices:
                merged_aliases[alias] = canon
    if aliases:
        merged_aliases.update(aliases)
    if raw in merged_aliases:
        canon = merged_aliases[raw].lower()
        if canon in norm_choices:
            return choices[norm_choices.index(canon)]
    # Substring alias check, longest-alias-first (avoids "no" matching inside
    # "noticing" before the more specific "noticing" rule fires).
    for alias in sorted(merged_aliases.keys(), key=len, reverse=True):
        if alias and re.search(rf"\b{re.escape(alias)}\b", raw):
            canon = merged_aliases[alias].lower()
            if canon in norm_choices:
                return choices[norm_choices.index(canon)]

    # 3. Substring matching — score every choice and pick the strongest.
    # Two-stage scoring so "i'm very active" picks "very active" over
    # "moderately active" (both contain "active", but "very active" has 2
    # word-token matches and "moderately active" only has 1).
    raw_tokens_list = re.findall(r"[a-z0-9]+", raw)
    raw_tokens_set = set(raw_tokens_list)
    scored: list[tuple[int, int, str]] = []  # (whole-word-hits, prefix-hits, choice)
    for c, norm_c in zip(choices, norm_choices):
        if not norm_c:
            continue
        if norm_c in raw:
            # Full phrase appears verbatim — strongest signal.
            scored.append((100, 0, c))
            continue
        choice_toks = [t for t in norm_c.split() if len(t) >= 3]
        if not choice_toks:
            continue
        whole = sum(1 for t in choice_toks if t in raw_tokens_set)
        prefix = 0
        for t in choice_toks:
            if t in raw_tokens_set:
                continue  # already counted
            for rt in raw_tokens_list:
                if len(rt) >= 4 and (t.startswith(rt) or rt.startswith(t)):
                    prefix += 1
                    break
        if whole or prefix:
            scored.append((whole, prefix, c))
    if scored:
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return scored[0][2]

    # 4. Numeric coercion against range-like choices ("1-2", "3-4", "5+")
    num_match = re.search(r"\b(\d+)\b", raw)
    if num_match:
        n = int(num_match.group(1))
        for c, norm_c in zip(choices, norm_choices):
            # exact integer choice
            if norm_c == str(n):
                return c
            # range "a-b"
            r_match = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", norm_c)
            if r_match:
                lo, hi = int(r_match.group(1)), int(r_match.group(2))
                if lo <= n <= hi:
                    return c
            # "N+" open-upper
            plus_match = re.fullmatch(r"(\d+)\s*\+", norm_c)
            if plus_match and n >= int(plus_match.group(1)):
                return c

    # 5. Token-overlap (last resort — useful for "i train at home with dumbbells"
    # -> "dumbbells")
    raw_tokens = set(re.findall(r"[a-z0-9]+", raw))
    if raw_tokens:
        best: tuple[int, Optional[str]] = (0, None)
        for c, norm_c in zip(choices, norm_choices):
            choice_tokens = set(re.findall(r"[a-z0-9]+", norm_c))
            if not choice_tokens:
                continue
            overlap = len(raw_tokens & choice_tokens)
            if overlap > best[0]:
                best = (overlap, c)
        if best[1] and best[0] >= 1:
            return best[1]
    return None


def _parse_daily_activity_short_reply(text: str) -> Optional[str]:
    """Single-word / short aliases for the activity-level question."""
    s = (text or "").strip().lower()
    if not s:
        return None
    if s in ("sedentary", "desk", "office", "sit"):
        return "sedentary"
    if s in ("light", "lightly", "low", "easy"):
        return "lightly_active"
    if s in ("moderate", "medium", "mid", "average", "normal"):
        return "moderately_active"
    if s in ("very", "high", "active", "lots"):
        return "very_active"
    return None


def _extract_fitmax_updates(message: str, current: dict) -> dict:
    s = (message or "").strip().lower()
    updates = {}

    if any(k in s for k in ["fat loss", "lose fat", "cut", "cutting"]):
        updates["goal"] = "fat_loss"
    elif any(k in s for k in ["build muscle", "bulk", "bulking", "hypertrophy"]):
        updates["goal"] = "muscle_gain"
    elif "recomp" in s:
        updates["goal"] = "recomp"
    elif "maintain" in s:
        updates["goal"] = "maintenance"
    elif "performance" in s:
        updates["goal"] = "performance"

    if "beginner" in s:
        updates["experience_level"] = "beginner"
    elif "intermediate" in s:
        updates["experience_level"] = "intermediate"
    elif "advanced" in s:
        updates["experience_level"] = "advanced"

    height_cm = _to_cm_from_text(s)
    if height_cm:
        updates["height_cm"] = height_cm

    weight_kg = _to_kg_from_text(s)
    if weight_kg:
        updates["weight_kg"] = weight_kg

    age_match = re.search(r"\b([1-9]\d)\b", s)
    if age_match and 13 <= int(age_match.group(1)) <= 90:
        updates["age"] = int(age_match.group(1))

    if re.search(r"\bmale\b|\bman\b", s):
        updates["biological_sex"] = "male"
    elif re.search(r"\bfemale\b|\bwoman\b", s):
        updates["biological_sex"] = "female"

    equipment_keywords = [
        "dumbbell", "dumbbells", "barbell", "bench", "machine", "gym", "cable", "bands",
        "bodyweight", "home", "kettlebell", "pull-up", "pullup", "pull up", "trx", "resistance",
        "rack", "smith", "plates", "weights", "nothing", "none", "no equipment", "everything",
        "full gym", "full", "basic", "minimal", "calisthenics", "rings", "studio",
    ]
    if any(k in s for k in equipment_keywords):
        updates["equipment"] = s

    days_match = re.search(
        r"\b([1-7])\s*(?:days?|day|times?|x)(?:\s*(?:per|a|\/)\s*(?:week|wk|weeks?))?\b",
        s,
    )
    if days_match:
        days = int(days_match.group(1))
        if 1 <= days <= 7:
            updates["days_per_week"] = days

    mins_match = re.search(r"(\d{2,3})\s*(?:min|mins|minutes?)", s)
    if mins_match:
        mins = int(mins_match.group(1))
        if 20 <= mins <= 180:
            updates["session_minutes"] = mins

    if any(k in s for k in ["sedentary", "desk job"]):
        updates["daily_activity_level"] = "sedentary"
    elif any(k in s for k in ["lightly active", "some walking"]):
        updates["daily_activity_level"] = "lightly_active"
    elif any(k in s for k in ["moderately active", "on my feet"]):
        updates["daily_activity_level"] = "moderately_active"
    elif any(k in s for k in ["very active", "physical job"]):
        updates["daily_activity_level"] = "very_active"

    if any(k in s for k in ["no restrictions", "none", "nothing"]):
        updates["dietary_restrictions"] = "none"
    elif any(k in s for k in ["vegan", "vegetarian", "halal", "kosher", "allergy", "lactose", "gluten"]):
        updates["dietary_restrictions"] = s

    # avoid accidentally overwriting existing high-confidence fields with weak text
    return {k: v for k, v in updates.items() if v is not None and (not current.get(k) or current.get(k) != v)}


def _fitmax_parse_quantity(text: str) -> tuple[float, str]:
    s = (text or "").strip().lower()
    qty = 1.0

    if re.search(r"\bhalf\b|\b1/2\b", s):
        qty = 0.5
    elif re.search(r"\ban\b|\ba\b|\bone\b", s):
        qty = 1.0

    number_match = re.search(r"\b(\d+(?:\.\d+)?)\b", s)
    if number_match:
        try:
            qty = float(number_match.group(1))
        except ValueError:
            qty = 1.0

    cleaned = re.sub(r"\b(i|just|ate|had|a|an|one|serving|servings|x)\b", " ", s)
    cleaned = re.sub(r"\b\d+(?:\.\d+)?\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return max(qty, 0.25), cleaned


def _fitmax_portion_multiplier(text: str) -> float:
    s = (text or "").lower()
    mult = 1.0
    if any(k in s for k in ["small", "kid size", "cup"]):
        mult *= 0.8
    if any(k in s for k in ["large", "big", "extra large"]):
        mult *= 1.35
    if "bowl" in s:
        mult *= 1.2
    if "plate" in s:
        mult *= 1.3
    if "slice" in s:
        mult *= 0.75
    return mult


def _fitmax_heuristic_estimate(cleaned_item: str, qty: float) -> Optional[dict]:
    s = (cleaned_item or "").strip().lower()
    if not s:
        return None

    base = None
    for key in sorted(FITMAX_HEURISTIC_DISHES.keys(), key=len, reverse=True):
        if key in s:
            base = FITMAX_HEURISTIC_DISHES[key]
            break

    if not base:
        return None

    factor = max(qty, 0.25) * _fitmax_portion_multiplier(s)
    return {
        "calories": int(round(base["calories"] * factor)),
        "protein_g": int(round(base["protein_g"] * factor)),
        "carbs_g": int(round(base["carbs_g"] * factor)),
        "fat_g": int(round(base["fat_g"] * factor)),
        "matched_name": s,
        "source": "heuristic",
    }


async def _fitmax_estimate_food_log(message: str) -> Optional[dict]:
    s = (message or "").lower().strip()
    if not s:
        return None

    trigger = re.search(r"\b(i just ate|i ate|i just had|i had)\b", s)
    if not trigger:
        return None

    tail = s[trigger.end():].strip(" .,!?:;")
    if not tail:
        return None

    segments = re.split(r",| and |\+", tail)
    totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    matched_items: list[str] = []
    used_heuristic = False

    for seg in segments:
        qty, cleaned = _fitmax_parse_quantity(seg)
        if not cleaned:
            continue

        match_key = None
        for key in sorted(FITMAX_FOOD_DB.keys(), key=len, reverse=True):
            if key in cleaned:
                match_key = key
                break

        lookup = await nutrition_service.lookup_food(cleaned, qty)
        if lookup:
            totals["calories"] += int(lookup["calories"])
            totals["protein_g"] += int(lookup["protein_g"])
            totals["carbs_g"] += int(lookup["carbs_g"])
            totals["fat_g"] += int(lookup["fat_g"])
            matched_items.append(lookup.get("matched_name") or cleaned)
            if lookup.get("source") == "heuristic":
                used_heuristic = True
            continue

        if match_key:
            base = FITMAX_FOOD_DB[match_key]
            totals["calories"] += int(round(base["calories"] * qty))
            totals["protein_g"] += int(round(base["protein_g"] * qty))
            totals["carbs_g"] += int(round(base["carbs_g"] * qty))
            totals["fat_g"] += int(round(base["fat_g"] * qty))
            matched_items.append(match_key)
            continue

        heuristic = _fitmax_heuristic_estimate(cleaned, qty)
        if heuristic:
            totals["calories"] += int(heuristic["calories"])
            totals["protein_g"] += int(heuristic["protein_g"])
            totals["carbs_g"] += int(heuristic["carbs_g"])
            totals["fat_g"] += int(heuristic["fat_g"])
            matched_items.append(heuristic.get("matched_name") or cleaned)
            used_heuristic = True

    if not matched_items or totals["calories"] <= 0:
        return None

    return {
        "items": matched_items,
        "calories": totals["calories"],
        "protein_g": totals["protein_g"],
        "carbs_g": totals["carbs_g"],
        "fat_g": totals["fat_g"],
        "used_heuristic": used_heuristic,
    }


def _fitmax_consumed_from_history(history: list[dict]) -> int:
    consumed = 0
    for m in history:
        if m.get("role") != "assistant":
            continue
        text = (m.get("content") or "").lower()
        if "logged." not in text:
            continue
        cals_match = re.search(r"(\d{2,4})\s*calories?", text)
        if cals_match:
            consumed += int(cals_match.group(1))
    return consumed


def _normalize_clock_hhmm(raw: Optional[str]) -> Optional[str]:
    """Best-effort normalize to HH:MM (24h). Accepts 24h clock or 12h with am/pm."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # 12-hour with optional minutes, e.g. 7am, 7:30 pm, 11:59PM
    m12 = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?|am|pm)\s*$", s, re.I)
    if m12:
        h = int(m12.group(1))
        mn = int(m12.group(2) or 0)
        ap = m12.group(3).lower().replace(".", "")
        if mn > 59 or h < 1 or h > 12:
            return s[:32]
        if ap.startswith("a"):
            h24 = 0 if h == 12 else h
        else:
            h24 = 12 if h == 12 else h + 12
        return f"{h24:02d}:{mn:02d}"
    # Already 24h H:MM or HH:MM
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if not m:
        return s[:32]
    h, mn = int(m.group(1)), int(m.group(2))
    if h > 23 or mn > 59:
        return s[:32]
    return f"{h:02d}:{mn:02d}"


def _heightmax_global_profile_hint(onboarding: dict) -> str:
    """Tell the model what is already stored from signup / global onboarding."""
    if not onboarding:
        return ""
    bits = []
    a = _safe_int_age(onboarding.get("age"))
    if a is not None:
        bits.append(f"age={a}")
    g = str(onboarding.get("gender") or onboarding.get("sex") or "").strip()
    if g:
        bits.append(f"gender={g}")
    h = onboarding.get("height")
    if h is not None and str(h).strip():
        bits.append(f"height={h}")
    wt = onboarding.get("wake_time")
    st = onboarding.get("sleep_time")
    if wt:
        bits.append(f"wake_time={wt}")
    if st:
        bits.append(f"sleep_time={st}")
    opt: list[str] = []
    sh = onboarding.get("heightmax_screen_hours") or onboarding.get("screen_hours_daily")
    if sh:
        opt.append(f"screen/phone load already saved: {sh} -- do NOT ask again")
    hwt = onboarding.get("heightmax_workout_time") or onboarding.get("preferred_workout_time")
    if hwt:
        opt.append(f"preferred workout time already saved: {hwt} -- do NOT ask again")
    gp = onboarding.get("growth_plate_status") or onboarding.get("heightmax_growth_plate_status")
    if gp:
        opt.append(f"growth_plate status already saved: {gp} -- do NOT ask again")
    hg = onboarding.get("heightmax_goal") or onboarding.get("height_goal")
    if hg:
        opt.append(f"height goal already saved: {hg} -- do NOT ask again")
    sq = onboarding.get("heightmax_sleep_quality") or onboarding.get("sleep_quality")
    if sq:
        opt.append(f"sleep quality already saved: {sq} -- do NOT ask again")
    if not bits and not opt:
        return ""
    lines = [
        "KNOWN FROM GLOBAL ONBOARDING (user_context.onboarding -- signup / profile; "
        "treat as source of truth; DO NOT re-ask age, gender, height, wake, or sleep unless user asks to change): "
        + (", ".join(bits) if bits else "(no core demographics in JSON -- ask only what's missing)")
    ]
    if opt:
        lines.append("ALSO ALREADY ON PROFILE (do NOT re-ask):")
        lines.extend(f"- {x}" for x in opt)
    return "\n".join(lines) + "\n\n"


def _infer_skin_concern_id_from_onboarding(ob: dict) -> Optional[str]:
    """Map questionnaire + skin_type to a Skinmax protocol id (acne, pigmentation, ...)."""
    if not ob:
        return None
    primary = str(ob.get("primary_skin_concern") or "").strip().lower()
    secondary = str(ob.get("secondary_skin_concern") or "").strip().lower()
    keyword_to_id = [
        (("acne", "breakout", "blemish", "congestion", "pimple", "blackhead"), "acne"),
        (("pigment", "dark spot", "melasma", "hyperpigmentation", "uneven tone"), "pigmentation"),
        (("texture", "scar", "scarring", "pores"), "texture"),
        (("red", "sensitive", "rosacea", "irritat"), "redness"),
        (("aging", "wrinkle", "fine line", "anti-aging"), "aging"),
    ]
    for text in (primary, secondary):
        if not text:
            continue
        if text in SKINMAX_PROTOCOLS:
            return text
        for needles, cid in keyword_to_id:
            if any(n in text for n in needles) and cid in SKINMAX_PROTOCOLS:
                return cid
    ac = ob.get("appearance_concerns")
    if isinstance(ac, list):
        blob = " ".join(str(x).lower() for x in ac if x)
        for needles, cid in keyword_to_id:
            if any(n in blob for n in needles) and cid in SKINMAX_PROTOCOLS:
                return cid
    st = str(ob.get("skin_type") or "").strip().lower()
    if st:
        return resolve_skin_concern(st, None)
    return None


def _bonemax_onboarding_known_block(ob: dict) -> str:
    if not ob:
        return ""
    lines: list[str] = []
    wf = str(ob.get("bonemax_workout_frequency") or "").strip()
    if wf:
        lines.append(f"- workout frequency already in onboarding: {wf} -- pass to generate_maxx_schedule; do NOT ask again.")
    for label, key in (
        ("TMJ / jaw history", "bonemax_tmj_history"),
        ("mastic gum regularly", "bonemax_mastic_gum_regular"),
        ("heavy screen time", "bonemax_heavy_screen_time"),
    ):
        v = ob.get(key)
        if v is None or str(v).strip() == "":
            continue
        if _yes_no_answered(v):
            lines.append(f"- {label} already in onboarding: {v} -- use in tool; do NOT ask again.")
    if not lines:
        return ""
    return (
        "ALREADY KNOWN FROM ONBOARDING (do NOT re-ask; read from user_context / GLOBAL ONBOARDING):\n"
        + "\n".join(lines)
        + "\n\n"
    )


def _hairmax_onboarding_known_block(ob: dict) -> str:
    if not ob:
        return ""
    lines: list[str] = []
    for label, key in (
        ("hair type", "hair_type"),
        ("scalp state", "scalp_state"),
        ("daily styling / products", "daily_styling"),
        ("thinning", "thinning"),
        ("thinning (alt)", "hair_thinning"),
    ):
        v = ob.get(key)
        if v is None or str(v).strip() == "":
            continue
        if key in ("thinning", "hair_thinning") and not _yes_no_answered(v):
            continue
        lines.append(f"- {label}: {v} -- use in generate_maxx_schedule; do NOT ask again.")
    hcl = str(ob.get("hair_current_loss") or "").strip().lower()
    if hcl and not ob.get("thinning") and not ob.get("hair_thinning"):
        if any(w in hcl for w in ("yes", "yeah", "yep", "reced", "thin", "losing", "balding", "some")):
            lines.append(
                "- hair questionnaire (hair_current_loss) suggests thinning -- treat thinning=yes in tool unless user corrects; do NOT ask again unless unclear."
            )
        elif any(w in hcl for w in ("no", "nope", "not ", "none", "minimal")):
            lines.append(
                "- hair questionnaire suggests no major loss -- treat thinning=no in tool unless user corrects."
            )
    if not lines:
        return ""
    return (
        "ALREADY KNOWN FROM ONBOARDING (do NOT re-ask):\n"
        + "\n".join(lines)
        + "\n\n"
    )


def _fitmax_known_from_onboarding(onboarding: dict, profile: dict) -> str:
    """Lines for FitMax [SYSTEM] so the agent skips fields already on user/onboarding."""
    lines: list[str] = []
    ob = onboarding or {}
    fp = dict(profile.get("fitmax_profile") or {}) if profile else {}

    def add(label: str, v: Any) -> None:
        if v is None or v == "" or v == []:
            return
        lines.append(f"- {label}: {v}")

    add("goal (internal)", fp.get("goal") or ob.get("fitmax_primary_goal"))
    add("weight_kg", fp.get("weight_kg") or ob.get("weight"))
    add("height_cm", fp.get("height_cm") or ob.get("height"))
    add("age", fp.get("age") or ob.get("age"))
    add("biological_sex", fp.get("biological_sex") or ob.get("gender") or ob.get("sex"))
    add("days_per_week", fp.get("days_per_week") or ob.get("fitmax_workout_days_per_week"))
    add("experience_level", fp.get("experience_level") or ob.get("fitmax_training_experience"))
    add("equipment", fp.get("equipment") or ob.get("fitmax_equipment"))
    add("session_minutes", fp.get("session_minutes") or ob.get("fitmax_session_minutes"))
    add("daily_activity_level", fp.get("daily_activity_level"))
    add("dietary_restrictions", fp.get("dietary_restrictions") or ob.get("fitmax_diet_approach"))

    if not lines:
        return "ALREADY KNOWN: nothing pre-filled -- collect all required fields via conversation.\n"
    return "ALREADY KNOWN (do NOT re-ask unless user corrects):\n" + "\n".join(lines) + "\n"


def _merge_onboarding_with_schedule_prefs(user: Optional[User]) -> dict:
    """Expose wake/sleep from onboarding, backfilled from schedule_preferences for older users."""
    if not user:
        return {}
    ob = dict(user.onboarding or {})
    sp = user.schedule_preferences or {}
    if not ob.get("wake_time") and sp.get("wake_time"):
        ob["wake_time"] = str(sp["wake_time"]).strip()
    if not ob.get("sleep_time") and sp.get("sleep_time"):
        ob["sleep_time"] = str(sp["sleep_time"]).strip()
    return ob


async def _persist_user_wake_sleep(
    user: Optional[User],
    db: AsyncSession,
    wake_time: Optional[str],
    sleep_time: Optional[str],
) -> None:
    """Store global wake/sleep on User.onboarding (+ mirror on schedule_preferences)."""
    if not user:
        return
    ob = dict(user.onboarding or {})
    changed = False
    w = _normalize_clock_hhmm(wake_time) if wake_time and str(wake_time).strip() else None
    s = _normalize_clock_hhmm(sleep_time) if sleep_time and str(sleep_time).strip() else None
    if w:
        ob["wake_time"] = w
        changed = True
    if s:
        ob["sleep_time"] = s
        changed = True
    if not changed:
        return
    user.onboarding = ob
    flag_modified(user, "onboarding")
    sp = dict(user.schedule_preferences or {})
    if w:
        sp["wake_time"] = w
    if s:
        sp["sleep_time"] = s
    user.schedule_preferences = sp
    flag_modified(user, "schedule_preferences")
    await db.flush()


def _safe_int_age(val) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, int) and 8 <= val <= 100:
        return val
    if isinstance(val, float) and not (val != val):  # not NaN
        n = int(round(val))
        if 8 <= n <= 100:
            return n
    s = str(val).strip()
    if s.isdigit():
        n = int(s)
        if 8 <= n <= 100:
            return n
    m = re.match(r"^(\d{1,2})\b", s)
    if m:
        n = int(m.group(1))
        if 8 <= n <= 100:
            return n
    return None


def _heightmax_demographics_complete(ob: dict) -> bool:
    """Age + gender + height present (typical app onboarding) -- no chat questions needed."""
    if not ob:
        return False
    if _safe_int_age(ob.get("age")) is None:
        return False
    if not str(ob.get("gender") or ob.get("sex") or "").strip():
        return False
    h = ob.get("height")
    if h is None:
        return False
    if isinstance(h, (int, float)):
        return bool(h and h > 0)
    return bool(str(h).strip())


def _is_heightmax_app_kickoff_message(text: str) -> bool:
    """Auto message from MaxChatScreen when opening HeightMax schedule flow."""
    t = (text or "").strip().lower()
    if "start" not in t or "schedule" not in t:
        return False
    return "heightmax" in t or "height max" in t or ("height" in t and "max" in t)


async def _persist_heightmax_onboarding_from_chat(
    user: Optional[User],
    db: AsyncSession,
    *,
    resolved_age: Optional[int],
    resolved_sex: str,
    resolved_height: str,
    final_wake: str,
    final_sleep: str,
) -> None:
    """Save HeightMax intake from chat tool + persist wake/sleep for profile + API."""
    if not user:
        return
    ob = dict(user.onboarding or {})
    if resolved_age is not None:
        ob["age"] = resolved_age
    if resolved_sex:
        ob["gender"] = resolved_sex
    if resolved_height:
        ob["height"] = resolved_height
    user.onboarding = ob
    flag_modified(user, "onboarding")
    await db.flush()
    await _persist_user_wake_sleep(user, db, final_wake, final_sleep)


def _looks_like_informational_question(text: str) -> bool:
    """
    True for education / definition / why-how questions -- not schedule change commands.
    Used to skip schedule tools when the model mis-fires.
    """
    if not text or len(text.strip()) < 6:
        return False
    t = text.lower().strip()
    # Schedule-change phrases that can co-occur with questions -- exclude
    if any(
        x in t
        for x in (
            "move my",
            "change my schedule",
            "reschedule",
            "push my",
            "wake up at",
            "sleep at",
            "earlier than",
            "later than",
        )
    ):
        return False
    patterns = (
        r"\bwhat (are|is|was)\s+(the\s+)?(benefits?|risks?|pros?|cons?|difference|point|deal)\b",
        r"\bwhat('s| is| are)\b",
        r"\bwhy\b",
        r"\bhow (do|does|can|should|to|much|long|often|come)\b",
        r"^explain\b",
        r"\btell me (about|why|how)\b",
        r"\bis (it|this|that|minoxidil|derma)\b",
        r"\bdoes (minoxidil|shampoo|derma|it)\b",
        r"\bcan i use\b",
        r"\bworth (it|using)\b",
        r"\bdifference between\b",
        r"\bshould i (use|take|buy|start)\b",
        r"\bdefine\b",
        r"\bmeaning of\b",
    )
    for pat in patterns:
        if re.search(pat, t, re.I):
            return True
    return False


def _user_requests_schedule_change(text: str) -> bool:
    """
    True when the user is clearly asking to change wake/sleep/times on an existing schedule.
    Used to run adapt_schedule if the model forgot to call modify_schedule.
    """
    if not text or len(text.strip()) < 15:
        return False
    if _looks_like_informational_question(text):
        return False
    t = text.lower()
    change_intent = any(
        x in t
        for x in (
            "wake",
            "waking",
            "sleep",
            "sleeping",
            "bedtime",
            "bed time",
            "earlier",
            "later",
            "change",
            "update",
            "move",
            "shift",
            "instead",
            "actually",
            "going to be",
            "gonna be",
            "from now",
            "tomorrow",
            "day after",
        )
    )
    if not change_intent:
        return False
    has_time = bool(
        re.search(r"\d{1,2}(\s*:\s*\d{2})?\s*(am|pm)|\d{1,2}:\d{2}", t, re.I)
    )
    if has_time or "wake" in t or "sleep" in t or "bed" in t:
        return True
    return False


def _looks_like_schedule_mutation_request(text: str) -> bool:
    """True when the user asks to change schedule/tasks (even if details are vague)."""
    if not text:
        return False
    t = text.lower().strip()
    if len(t) < 6:
        return False
    schedule_objs = ("schedule", "task", "tasks", "routine", "today")
    mutation_ops = (
        "update",
        "change",
        "modify",
        "edit",
        "move",
        "shift",
        "reschedule",
        "complete",
        "uncomplete",
        "delete",
        "remove",
        "mark",
    )
    if any(obj in t for obj in schedule_objs) and any(op in t for op in mutation_ops):
        return True
    # Also treat direct wake/sleep time corrections as mutation requests, even
    # when the user doesn't explicitly mention the word "schedule".
    if _user_requests_schedule_change(t):
        return True
    return False


def _looks_like_task_operation_request(text: str) -> bool:
    """True when the user is asking to operate on schedule tasks (not ask knowledge)."""
    if not text or len(text.strip()) < 3:
        return False
    t = text.lower().strip()
    # Strong task-operation verbs + objects.
    op_words = (
        "complete",
        "completed",
        "mark",
        "uncomplete",
        "undo",
        "revert",
        "pending",
        "delete",
        "remove",
        "edit",
        "update",
        "change",
        "move",
        "shift",
        "reschedule",
        "check off",
        "finish",
        "finished",
        "cancel",
        "skip",
        "done with",
        "finished with",
    )
    task_words = ("task", "tasks", "today", "schedule", "nutrition", "workout", "routine")
    has_op = any(w in t for w in op_words)
    has_task_obj = any(w in t for w in task_words)
    if has_op and has_task_obj:
        return True
    # Schedule-view requests should route to tools (get_today_tasks), not fast RAG.
    schedule_view_phrases = (
        "what's on my schedule",
        "whats on my schedule",
        "what is on my schedule",
        "show my schedule",
        "show schedule",
        "what do i have today",
        "what are my tasks",
        "what tasks do i have",
        "today tasks",
        "today's tasks",
        "todays tasks",
        "what's on my plate",
        "whats on my plate",
        "what do i have tomorrow",
        "what are my tasks tomorrow",
        "tomorrow tasks",
        "tomorrow's tasks",
        "tomorrows tasks",
        "upcoming tasks",
        "my tasks for tomorrow",
    )
    if any(p in t for p in schedule_view_phrases):
        return True
    # Natural command variants seen in chat.
    phrases = (
        "mark all",
        "mark today's",
        "mark todays",
        "mark other as",
        "mark others as",
        "set as completed",
        "set as pending",
        "set to pending",
        "only completed",
        "except these",
        "undo these",
    )
    return any(p in t for p in phrases)


def _yes_no_answered(val) -> bool:
    """True if user gave an explicit yes/no answer (for hairmax daily_styling / thinning)."""
    if val is None:
        return False
    if isinstance(val, bool):
        return True
    s = str(val).strip().lower()
    return s in ("yes", "no", "y", "n", "true", "false", "1", "0")


def _normalize_hair_yes_no(val) -> Optional[str]:
    """Normalize to 'yes' / 'no' for schedule context, or None."""
    if val is None:
        return None
    if isinstance(val, bool):
        return "yes" if val else "no"
    s = str(val).strip().lower()
    if s in ("yes", "y", "true", "1"):
        return "yes"
    if s in ("no", "n", "false", "0"):
        return "no"
    return None


def _quick_replies_from_response(text: str) -> list[str]:
    s = (text or "").strip().lower()
    if not s:
        return []

    def _dedupe(items: list[str]) -> list[str]:
        out: list[str] = []
        seen = set()
        for raw in items:
            v = raw.strip()
            if not v:
                continue
            k = v.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(v)
        return out

    if "straight, wavy, curly, or coily" in s or "what's your hair type" in s:
        return ["straight", "wavy", "curly", "coily"]
    if "normal, dry/flaky, oily/greasy, or itchy" in s or "how's your scalp" in s:
        return ["normal", "dry/flaky", "oily/greasy", "itchy"]
    if "beginner, intermediate, or advanced" in s:
        return ["beginner", "intermediate", "advanced"]
    if "fat loss, muscle gain, recomp, maintenance, or performance" in s or (
        "main goal right now" in s and ("losing fat" in s or "building muscle" in s)
    ):
        return ["fat loss", "muscle gain", "recomp", "maintenance", "performance"]
    if "sedentary, lightly active, moderately active, or very active" in s:
        return ["sedentary", "lightly active", "moderately active", "very active"]
    if "what do you have available to train" in s or "equipment" in s and "available" in s:
        return ["full gym", "dumbbells", "no equipment"]
    if "how many days per week" in s or "workout frequency" in s:
        return ["3", "4", "5", "6"]
    if "session length" in s or "how long" in s and ("session" in s or "workout" in s):
        return ["30", "45", "60", "90"]
    if "what's your biological sex" in s or "biological sex" in s:
        return ["male", "female"]
    if "dietary restriction" in s:
        return ["none", "vegan", "vegetarian", "gluten-free", "lactose-free"]
    if "planning to be outside much today" in s or "outside much today" in s:
        return ["yes", "no"]
    if "acne" in s and "dark spots" in s and "dryness" in s and "oil control" in s:
        return ["acne", "dark spots", "dryness", "oil control", "anti-aging"]
    if "products or styling most days" in s:
        return ["yes", "no"]
    if "noticing any thinning" in s or "thinning or a receding" in s:
        return ["yes", "no"]
    if ("ever had tmj" in s or "jaw pain" in s) and "yes or no" in s:
        return ["yes", "no"]
    if "mastic or hard gum" in s and "yes or no" in s:
        return ["yes", "no"]
    if "computer or phone" in s and "many hours" in s:
        return ["yes", "no"]

    return []


def _chat_history_channel_clause(channel: str):
    """Filter chat_history rows: app UI only sees 'app' (and legacy NULL); SMS uses its own thread."""
    if channel == "sms":
        return ChatHistory.channel == "sms"
    return or_(ChatHistory.channel == "app", ChatHistory.channel.is_(None))


def _persist_chat_history(channel: str) -> bool:
    """SMS conversations are not stored in chat_history (SMS-only surface)."""
    return channel != "sms"


# Keep strong refs to background tasks so the event loop doesn't GC them mid-flight
# (asyncio only holds weakrefs to Tasks created outside a running awaited chain).
_BACKGROUND_TASKS: set = set()


# --------------------------------------------------------------------------- #
#  Per-user chat serialization                                                #
# --------------------------------------------------------------------------- #
# A user firing two messages in quick succession used to race — both ran
# concurrently and the slower reply could land AFTER the faster one,
# producing the "I asked X, got an unrelated answer to my earlier
# message" bug. Lock every chat turn behind a per-user asyncio.Lock so
# only one in-flight processing pass exists per user. The waiter is held
# in the event loop, so the second request still gets a response — just
# strictly after the first finishes.
import asyncio as _asyncio_chat_lock  # local alias to keep imports tidy
_CHAT_LOCKS: dict[str, _asyncio_chat_lock.Lock] = {}
_CHAT_LOCKS_GUARD: _asyncio_chat_lock.Lock = _asyncio_chat_lock.Lock()


async def _get_user_chat_lock(user_id: str) -> _asyncio_chat_lock.Lock:
    async with _CHAT_LOCKS_GUARD:
        lock = _CHAT_LOCKS.get(user_id)
        if lock is None:
            lock = _asyncio_chat_lock.Lock()
            _CHAT_LOCKS[user_id] = lock
        return lock


def _spawn_background_task(coro) -> None:
    """Fire-and-forget a coroutine off the request's critical path."""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def _bg_update_memory(user_id: str, recent_history: list[dict]) -> None:
    from db import AsyncSessionLocal
    try:
        summary = await coaching_service.generate_conversation_summary(recent_history)
        if not summary:
            return
        async with AsyncSessionLocal() as bg_db:
            await coaching_service.update_ai_memory(user_id, bg_db, summary)
    except Exception as e:
        logger.warning("bg AI memory update failed for %s: %s", user_id, e)


async def _bg_detect_tone(user_id: str, recent_history: list[dict]) -> None:
    from db import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as bg_db:
            await coaching_service.detect_tone_preference(user_id, bg_db, recent_history)
    except Exception as e:
        logger.warning("bg tone detection failed for %s: %s", user_id, e)


async def process_chat_message(
    user_id: str,
    message_text: str,
    db: AsyncSession,
    rds_db: Optional[AsyncSession] = None,
    init_context: Optional[str] = None,
    chat_intent: Optional[str] = None,
    attachment_url: Optional[str] = None,
    attachment_type: Optional[str] = None,
    channel: str = "app",
    conversation_id: Optional[str] = None,
) -> Tuple[str, list[str]]:
    """
    Core chat logic shared by the HTTP endpoint and the SMS webhook.
    Persists app turns to ChatHistory (channel=app). SMS turns are not persisted.
    In-app GET /history shows app (and legacy NULL channel) only.
    Returns (assistant_text, quick_reply_choices). Choices are only for active
    module schedule onboarding.
    """
    from services.schedule_service import schedule_service, ScheduleLimitError
    from services import chat_conversations_service as _conv
    from models.sqlalchemy_models import active_conversation_id as _active_conv_cv

    user_uuid = UUID(user_id)
    note_chat_turn()

    fitmax_schedule_active = None
    hairmax_schedule_active = None
    bonemax_schedule_active = None

    # --- Resolve the active conversation for this turn ---------------------
    # SMS stays untracked (channel != app → no persistence, no thread). For
    # app turns: use the supplied id if it belongs to this user, otherwise
    # route to the user's most-recent thread (or create one on first message).
    active_conversation = None
    active_conv_id_str: Optional[str] = None
    if channel == "app":
        try:
            active_conversation = await _conv.resolve_active_conversation(
                db,
                user_id=user_id,
                conversation_id=conversation_id,
                channel="app",
            )
            active_conv_id_str = str(active_conversation.id)
            # Every ChatHistory() constructed below inherits this id via the
            # model's contextvar default. FastAPI gives each request its own
            # asyncio Context so there's no cross-request leak.
            _active_conv_cv.set(active_conversation.id)
            # Bump recency + auto-title once per turn.
            await _conv.touch_last_message(
                db,
                conversation_id=active_conv_id_str,
                first_user_message=message_text,
                commit=False,
            )
        except Exception as e:
            logger.warning("[chat] could not resolve conversation for user=%s: %s",
                           str(user_id)[:8], e)
            return (
                _finalize_assistant_message(
                    "i hit a temporary chat-thread error. retry once and i should be back."
                ),
                [],
            )

    # SMS is not persisted; use in-app thread as read-only context for the model.
    history_channel_for_load = "app" if channel == "sms" else channel
    # AsyncSession is NOT concurrency-safe -- two awaits on the same session
    # raise InvalidRequestError. So we serialize DB calls on `db`, but batch
    # them into one query where we can: user + history are one round-trip
    # via gather only if they run on SEPARATE sessions. Keeping sequential
    # here for correctness; biggest win comes from trimming what each call does.
    # LLM window is CHAT_HISTORY_WINDOW (15) and bg jobs use last 20.
    history_stmt = (
        select(ChatHistory)
        .where(ChatHistory.user_id == user_uuid)
        .where(_chat_history_channel_clause(history_channel_for_load))
    )
    if active_conversation is not None:
        # Scope to the active thread so each conversation has its own context
        # window. Legacy rows without conversation_id are invisible once the
        # user has any active thread (they're backfilled into "Chat history"
        # at migration time, so they still show up under that thread).
        history_stmt = history_stmt.where(
            ChatHistory.conversation_id == active_conversation.id
        )
    history_result = await db.execute(
        history_stmt
        .order_by(ChatHistory.created_at.desc())
        .limit(20)
    )
    history_rows = list(reversed(history_result.scalars().all()))
    history = [
        {"role": h.role, "content": h.content, "created_at": h.created_at}
        for h in history_rows
    ]

    active_schedule = await schedule_service.get_current_schedule(user_id, db=db)
    user = await db.get(User, user_uuid)
    onboarding = _merge_onboarding_with_schedule_prefs(user)
    active_hint = str((active_schedule or {}).get("maxx_id") or "").strip() or None
    explicit_chat_intent = _coerce_chat_intent(chat_intent)
    explicit_schedule_start = explicit_chat_intent == "start_schedule"
    start_schedule_maxx = _coerce_chat_maxx_id(init_context) if explicit_schedule_start else None
    turn_intent = classify_turn(message_text, active_maxx=active_hint)
    # Batch all stale-flag cleanups into a single commit. Previously this block
    # could issue up to 5 separate commits before the LLM call even started --
    # each one a ~5-20ms round-trip. Now: mutate in memory, commit once at end.
    profile: dict = dict((user.profile or {}) or {}) if user else {}
    profile_dirty = False

    if user and _expire_stale_chat_pending(profile):
        profile_dirty = True

    if user:
        try:
            fitmax_schedule_active = await schedule_service.get_maxx_schedule(user_id, "fitmax", db=db)
        except Exception:
            fitmax_schedule_active = None
        try:
            hairmax_schedule_active = await schedule_service.get_maxx_schedule(user_id, "hairmax", db=db)
        except Exception:
            hairmax_schedule_active = None
        try:
            bonemax_schedule_active = await schedule_service.get_maxx_schedule(user_id, "bonemax", db=db)
        except Exception:
            bonemax_schedule_active = None

        def _clear_setup_flags(prefix: str) -> None:
            nonlocal profile_dirty
            if profile.pop(f"{prefix}_chat_setup", None) is not None:
                profile_dirty = True
            if profile.pop(f"{prefix}_chat_setup_at", None) is not None:
                profile_dirty = True

        if hairmax_schedule_active and profile.get("hairmax_chat_setup"):
            _clear_setup_flags("hairmax")
        elif profile.get("hairmax_chat_setup") and _hairmax_setup_stale(profile):
            _clear_setup_flags("hairmax")
        if fitmax_schedule_active and profile.get("fitmax_chat_setup"):
            _clear_setup_flags("fitmax")
        elif profile.get("fitmax_chat_setup") and _fitmax_setup_stale(profile):
            _clear_setup_flags("fitmax")
        if bonemax_schedule_active and profile.get("bonemax_chat_setup"):
            _clear_setup_flags("bonemax")
        elif profile.get("bonemax_chat_setup") and _bonemax_setup_stale(profile):
            _clear_setup_flags("bonemax")

        if profile_dirty:
            user.profile = profile
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()

    # Pull persistent context (preferences + user_facts) so the agent
    # respects long-term memory (vegetarian, allergic-to, lives-in, etc.)
    # on every turn — not just when the user says it explicitly.
    persistent_ctx: dict = {}
    user_facts: dict = {}
    try:
        from services.user_context_service import get_context as _get_ctx
        from services.user_facts_service import FACTS_KEY as _FACTS_KEY
        persistent_ctx = await _get_ctx(user_id, db)
        user_facts = persistent_ctx.get(_FACTS_KEY) or {}
    except Exception:
        pass

    user_context = {
        "coaching_context": "",
        "active_schedule": active_schedule,
        "onboarding": onboarding,
        "persistent_context": persistent_ctx,
        "user_facts": user_facts,
    }

    if user and _looks_like_completed_tasks_question(message_text):
        response_text = await _reply_today_completed_tasks_summary(user_id, onboarding, db)
        if _persist_chat_history(channel):
            user_message = ChatHistory(
                user_id=user_uuid,
                role="user",
                content=message_text,
                channel=channel,
                created_at=datetime.utcnow(),
            )
            assistant_message = ChatHistory(
                user_id=user_uuid,
                role="assistant",
                content=response_text,
                channel=channel,
                created_at=datetime.utcnow(),
            )
            db.add(user_message)
            db.add(assistant_message)
        await db.commit()
        return _finalize_assistant_message(response_text), []

    explicit_chat_intent = _coerce_chat_intent(chat_intent)
    explicit_schedule_start = explicit_chat_intent == "start_schedule"
    active_hint = str((active_schedule or {}).get("maxx_id") or "").strip() or None
    # Reuse the first intent classification to keep routing deterministic.

    # If the frontend sent start_schedule but the user typed an informational
    # question (not a schedule kickoff), treat it as a normal message so the
    # fast-knowledge path can handle it instead of entering the schedule setup.
    if explicit_schedule_start and (message_text or "").strip():
        if _looks_like_informational_question(message_text) or turn_intent.get("intent") == "KNOWLEDGE":
            explicit_schedule_start = False
            explicit_chat_intent = None

    start_schedule_maxx = _coerce_chat_maxx_id(init_context) if explicit_schedule_start else None

    # --- Maxx module routing (structured LLM; init_context is hint inside classifier) ---
    message = message_text
    if not (message_text or "").strip():
        maxx_id = start_schedule_maxx
    else:
        if start_schedule_maxx:
            maxx_id = start_schedule_maxx
        else:
            hints = turn_intent.get("maxx_hints") or []
            maxx_id = hints[0] if hints else active_hint

    if maxx_id:
        try:
            scoped_schedule = await schedule_service.get_current_schedule(
                user_id,
                db=db,
                maxx_id=maxx_id,
            )
            if scoped_schedule:
                active_schedule = scoped_schedule
                active_hint = str((active_schedule or {}).get("maxx_id") or "").strip() or active_hint
                user_context["active_schedule"] = active_schedule
        except Exception as sched_err:
            logger.warning("scoped active schedule lookup failed for %s: %s", maxx_id, sched_err)

    image_data = None
    if attachment_url and attachment_type == "image":
        image_data = await storage_service.get_image(attachment_url)

    link_maxx = list(turn_intent.get("maxx_hints") or [])
    if not link_maxx and active_hint:
        link_maxx = [active_hint]

    if (
        not explicit_schedule_start
        and not image_data
        and _looks_like_link_request(message_text)
        and link_maxx
    ):
        link_response = await product_links_from_context(
            message=message_text,
            maxx_id=str(link_maxx[0]),
        )
        if link_response:
            if _persist_chat_history(channel):
                db.add(ChatHistory(
                    user_id=user_uuid,
                    role="user",
                    content=message_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                ))
                db.add(ChatHistory(
                    user_id=user_uuid,
                    role="assistant",
                    content=link_response,
                    channel=channel,
                    created_at=datetime.utcnow(),
                ))
            await db.commit()
            fast_path_snapshot("links")
            logger.info("[FAST_LINKS] user=%s maxx=%s", str(user_id)[:8], link_maxx[0])
            return _finalize_assistant_message(link_response), []

    if (
        not explicit_schedule_start
        and not image_data
        and _looks_like_brand_request(message_text)
        and link_maxx
    ):
        brands = product_brands_for_module(str(link_maxx[0]))
        if brands:
            brand_lines = ["here's a quick brand list from the current module references:"]
            for brand in brands:
                brand_lines.append(f"- {brand}")
            brand_lines.append("if you want, ask for amazon links and i can give you quick search links.")
            brand_response = "\n".join(brand_lines)
            if _persist_chat_history(channel):
                db.add(ChatHistory(
                    user_id=user_uuid,
                    role="user",
                    content=message_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                ))
                db.add(ChatHistory(
                    user_id=user_uuid,
                    role="assistant",
                    content=brand_response,
                    channel=channel,
                    created_at=datetime.utcnow(),
                ))
            await db.commit()
            fast_path_snapshot("brands")
            logger.info("[FAST_BRANDS] user=%s maxx=%s", str(user_id)[:8], link_maxx[0])
            return _finalize_assistant_message(brand_response), []

    if (
        not explicit_schedule_start
        and not image_data
        and
        turn_intent.get("intent") == "KNOWLEDGE"
        and (turn_intent.get("maxx_hints") or active_hint)
        and not _looks_like_task_operation_request(message_text)
    ):
        # Reuse the already-fetched user_facts (saves a DB roundtrip vs
        # the previous re-fetch). `user_facts` was populated from
        # persistent_ctx earlier in this turn.
        _facts_blob: dict = user_facts or {}

        # Personal-data short-circuit: "what is my age?" / "how old am i?" /
        # "what's my gender?" must NEVER hit doc-RAG. Answer from onboarding
        # + user_facts, or admit we don't know and ASK — instead of returning
        # the canned "i don't see enough in the docs" line.
        if _looks_like_personal_data_question(message_text):
            answer = await _answer_personal_data_question(message_text, onboarding, _facts_blob)
            if answer:
                if _persist_chat_history(channel):
                    db.add(ChatHistory(user_id=user_uuid, role="user", content=message_text, channel=channel, created_at=datetime.utcnow()))
                    db.add(ChatHistory(user_id=user_uuid, role="assistant", content=answer, channel=channel, created_at=datetime.utcnow()))
                await db.commit()
                return _finalize_assistant_message(answer), []

        # Two-layer memory: recent turns + stable user profile. Both
        # paths (fast_rag and agent) consume the SAME builder so behavior
        # is consistent across routing decisions. The agent path already
        # gets a structured chat-history list; we additionally pass the
        # formatted strings here for the fast_rag path which previously
        # had zero conversational memory.
        try:
            from services.conversation_memory import build_memory_context
            _memctx = build_memory_context(
                history=history,
                user_facts=_facts_blob,
                onboarding=onboarding,
                persistent_ctx=persistent_ctx,
            )
        except Exception as _memerr:  # never block the turn on memory bugs
            logger.info("[chat] memory builder skipped: %s", _memerr)
            _memctx = None

        fast_response, fast_chunks = await answer_from_rag(
            message=message_text,
            maxx_hints=turn_intent.get("maxx_hints") or [],
            active_maxx=active_hint,
            response_length=str(onboarding.get("response_length") or "").strip().lower() or None,
            user_facts=_facts_blob,
            recent_turns=(_memctx.recent_turns if _memctx else None),
            user_profile=(_memctx.user_profile if _memctx else None),
            coaching_tone=(getattr(user, "coaching_tone", None) if user else None),
        )
        if fast_response:
            # Web-search safety net for fast-RAG too. When the doc-grounded
            # answer is "i don't see enough in the docs", try the web before
            # we ship it. Cheaper than always running the agent — fast_rag
            # is supposed to be fast.
            if _looks_like_doc_refusal(fast_response) and not _question_is_personal(message_text):
                try:
                    from services.web_search import search as _ws_search
                    q = _compress_query_for_search(message_text)
                    web_snips = await _ws_search(q, max_results=3)
                    if web_snips and "(no web results" not in web_snips and "(web search" not in web_snips:
                        import asyncio as _asyncio
                        from services.llm_sync import sync_llm_plain_text
                        prompt = (
                            "Answer the user's question concisely (3-6 sentences) using ONLY "
                            "the web snippets below as your source. Plain text, no markdown "
                            "headings. If snippets disagree, pick the most authoritative.\n\n"
                            f"USER QUESTION: {message_text}\n\n"
                            f"WEB SNIPPETS:\n{web_snips}\n\n"
                            "Answer:"
                        )
                        try:
                            web_answer = await _asyncio.wait_for(
                                _asyncio.to_thread(sync_llm_plain_text, prompt),
                                timeout=30.0,
                            )
                            if web_answer and len(web_answer) > 30:
                                fast_response = web_answer.strip()
                                logger.info("[FAST_RAG] web fallback used (doc refusal recovered)")
                        except Exception:
                            pass
                except Exception as _e:
                    logger.info("fast_rag web safety net failed: %s", _e)
            if _persist_chat_history(channel):
                db.add(ChatHistory(
                    user_id=user_uuid,
                    role="user",
                    content=message_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                ))
                db.add(ChatHistory(
                    user_id=user_uuid,
                    role="assistant",
                    content=fast_response,
                    channel=channel,
                    created_at=datetime.utcnow(),
                    retrieved_chunk_ids=_chunk_audit_refs(fast_chunks),
                ))
            await db.commit()
            fast_path_snapshot("knowledge")
            logger.info(
                "[FAST_RAG] user=%s intent=%s hints=%s chunks=%d",
                str(user_id)[:8],
                turn_intent.get("intent"),
                turn_intent.get("maxx_hints"),
                len(fast_chunks),
            )
            return _finalize_assistant_message(fast_response), []

    if maxx_id and maxx_id != "fitmax" and user:
        prof = dict(user.profile or {})
        changed = False
        if str(prof.get("chat_pending_module") or "").lower() == "fitmax":
            prof.pop("chat_pending_module", None)
            prof.pop("chat_pending_module_at", None)
            changed = True
        if prof.get("fitmax_chat_setup"):
            prof.pop("fitmax_chat_setup", None)
            prof.pop("fitmax_chat_setup_at", None)
            changed = True
        if changed:
            user.profile = prof
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = prof

    if maxx_id and maxx_id != "hairmax" and user:
        prof = dict(user.profile or {})
        if prof.get("hairmax_chat_setup"):
            prof.pop("hairmax_chat_setup", None)
            prof.pop("hairmax_chat_setup_at", None)
            user.profile = prof
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = prof

    if maxx_id and maxx_id != "bonemax" and user:
        prof = dict(user.profile or {})
        if prof.get("bonemax_chat_setup"):
            prof.pop("bonemax_chat_setup", None)
            prof.pop("bonemax_chat_setup_at", None)
            user.profile = prof
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = prof

    scripted_mx = settings.chat_scripted_fitmax_hairmax_onboarding
    scripted_bonemax = settings.chat_scripted_bonemax_onboarding

    if scripted_mx and explicit_schedule_start and start_schedule_maxx == "fitmax" and user and not fitmax_schedule_active:
        prof = dict(profile or {})
        if not prof.get("fitmax_chat_setup"):
            prof["fitmax_chat_setup"] = True
            prof["fitmax_chat_setup_at"] = datetime.now(timezone.utc).isoformat()
            user.profile = prof
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = dict((user.profile or {}) or {})

    if scripted_mx and explicit_schedule_start and start_schedule_maxx == "hairmax" and user and not hairmax_schedule_active:
        prof = dict(profile or {})
        if not prof.get("hairmax_chat_setup"):
            prof["hairmax_chat_setup"] = True
            prof["hairmax_chat_setup_at"] = datetime.now(timezone.utc).isoformat()
            user.profile = prof
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = dict((user.profile or {}) or {})

    if scripted_bonemax and explicit_schedule_start and start_schedule_maxx == "bonemax" and user and not bonemax_schedule_active:
        prof = dict(profile or {})
        if not prof.get("bonemax_chat_setup"):
            prof["bonemax_chat_setup"] = True
            prof["bonemax_chat_setup_at"] = datetime.now(timezone.utc).isoformat()
            user.profile = prof
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = dict((user.profile or {}) or {})

    fitmax_pending = bool(
        scripted_mx and user and str(profile.get("chat_pending_module") or "").lower() == "fitmax"
    )
    # ------------------------------------------------------------------
    # Legacy hardcoded scripted-onboarding gates — RETIRED.
    #
    # All five maxxes (skin/hair/height/fit/bone) now route through the
    # doc-driven onboarding system in services.onboarding_questioner,
    # invoked at the FastAPI endpoint level (chat.py:_run_onboarding_questioner)
    # BEFORE process_chat_message runs. The old hardcoded
    # *_REQUIRED_FIELDS / *_QUESTION_MAP / run_*_onboarding blocks
    # below are dead code kept only so we don't break imports if some
    # other module still references the helpers. Safe to delete in a
    # follow-up cleanup pass.
    # ------------------------------------------------------------------
    run_fitmax_onboarding = False
    run_hairmax_onboarding = False
    run_bonemax_onboarding = False

    # --- Fitmax chat onboarding (profile is populated conversationally) ---
    if run_fitmax_onboarding:
        fitmax_profile = dict(profile.get("fitmax_profile") or {})
        seeded = _fitmax_seed_profile_from_onboarding(fitmax_profile, onboarding)
        if seeded != fitmax_profile:
            fitmax_profile = seeded
            profile["fitmax_profile"] = fitmax_profile
            user.profile = profile
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
        updates = _extract_fitmax_updates(message_text, fitmax_profile)
        missing_next = _fitmax_missing_fields(fitmax_profile)
        if missing_next:
            nxt = missing_next[0]
            if nxt == "equipment" and "equipment" not in updates:
                raw = (message_text or "").strip()
                if raw:
                    updates["equipment"] = raw.lower()
            elif nxt == "days_per_week" and "days_per_week" not in updates:
                d = _parse_days_per_week_reply(message_text)
                if d is not None:
                    updates["days_per_week"] = d
            elif nxt == "session_minutes" and "session_minutes" not in updates:
                sm = _parse_session_minutes_reply(message_text)
                if sm is not None:
                    updates["session_minutes"] = sm
            elif nxt == "daily_activity_level" and "daily_activity_level" not in updates:
                act = _parse_daily_activity_short_reply(message_text)
                if act is not None:
                    updates["daily_activity_level"] = act
            elif nxt == "dietary_restrictions" and "dietary_restrictions" not in updates:
                raw = (message_text or "").strip()
                if raw:
                    updates["dietary_restrictions"] = raw.lower()
            elif nxt == "biological_sex" and "biological_sex" not in updates:
                raw = (message_text or "").strip().lower()
                if raw in ("male", "m", "man", "guy", "boy"):
                    updates["biological_sex"] = "male"
                elif raw in ("female", "f", "woman", "girl"):
                    updates["biological_sex"] = "female"

            # Generic fuzzy fallback: if the field is still missing, try to
            # coerce the user's reply to one of the offered choices for the
            # CURRENT question. This is what stops the "user typed 3 but we
            # wanted '3-4' so we re-ask forever" loop.
            if nxt not in updates:
                _, choices = FITMAX_QUESTION_MAP.get(nxt, ("", []))
                if choices:
                    coerced = _coerce_to_choice(message_text, choices)
                    if coerced is not None:
                        # Numeric fields stored as int; everything else as str.
                        if nxt in ("days_per_week", "session_minutes", "age"):
                            try:
                                updates[nxt] = int(re.search(r"\d+", coerced).group())
                            except (AttributeError, ValueError):
                                updates[nxt] = coerced
                        else:
                            updates[nxt] = coerced
        if updates:
            fitmax_profile.update(updates)
            profile["fitmax_profile"] = fitmax_profile
            user.profile = profile
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()

        abandoned_sms_fitmax = (
            fitmax_pending
            and not any(fitmax_profile.values())
            and not updates
            and not _looks_like_fitmax_activation_message(message_text)
        )
        if abandoned_sms_fitmax:
            prof = dict(user.profile or {})
            prof.pop("chat_pending_module", None)
            prof.pop("chat_pending_module_at", None)
            user.profile = prof
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = prof
        else:
            fitmax_schedule = fitmax_schedule_active
            missing = _fitmax_missing_fields(fitmax_profile)

            # Onboarding incomplete -> ask exactly one next question in chat
            if not fitmax_schedule and missing:
                if not any(fitmax_profile.values()):
                    response_text = "hey, welcome to fitmax. before we build your plan, i need to know a bit about you -- this takes about 3 minutes and everything we create depends on it. what's your main goal right now? losing fat, building muscle, recomp, maintain, or performance?"
                    choices_for_step = ["fat loss", "muscle gain", "recomp", "maintenance", "performance"]
                else:
                    response_text = _fitmax_next_question(fitmax_profile)
                    choices_for_step = _fitmax_next_choices(fitmax_profile)

                if channel == "sms" and user:
                    prof = dict(user.profile or {})
                    prof["chat_pending_module"] = "fitmax"
                    prof["chat_pending_module_at"] = datetime.now(timezone.utc).isoformat()
                    user.profile = prof
                    flag_modified(user, "profile")

                if _persist_chat_history(channel):
                    user_message = ChatHistory(
                        user_id=user_uuid,
                        role="user",
                        content=message_text,
                        channel=channel,
                        created_at=datetime.utcnow(),
                    )
                    assistant_message = ChatHistory(
                        user_id=user_uuid,
                        role="assistant",
                        content=response_text,
                        channel=channel,
                        created_at=datetime.utcnow(),
                    )
                    db.add(user_message)
                    db.add(assistant_message)
                await db.commit()
                ft = _finalize_assistant_message(response_text)
                return ft, choices_for_step

            # Onboarding complete and no fitmax schedule yet -> generate + summarize
            if not fitmax_schedule and not missing:
                plan = _fitmax_build_plan(fitmax_profile)
                profile.pop("chat_pending_module", None)
                profile.pop("chat_pending_module_at", None)
                profile.pop("fitmax_chat_setup", None)
                profile.pop("fitmax_chat_setup_at", None)
                profile["fitmax_plan"] = plan
                user.profile = profile
                flag_modified(user, "profile")
                user.updated_at = datetime.utcnow()

                try:
                    fw_fm = _normalize_clock_hhmm(onboarding.get("wake_time")) or "07:00"
                    fs_fm = _normalize_clock_hhmm(onboarding.get("sleep_time")) or "23:00"
                    schedule = await schedule_service.generate_maxx_schedule(
                        user_id=user_id,
                        maxx_id="fitmax",
                        db=db,
                        rds_db=rds_db if rds_db else None,
                        subscription_tier=(getattr(user, "subscription_tier", None) if user else None),
                        wake_time=str(fw_fm),
                        sleep_time=str(fs_fm),
                        skin_concern=plan["goal_label"],
                        outside_today=False,
                    )
                    user_context["active_maxx_schedule"] = schedule

                    response_text = (
                        "got everything i need. here's what i've built for you:\n\n"
                        "view your fitmax plan ->\n\n"
                        f"your daily calorie target is {plan['calories']} calories with {plan['protein_g']}g protein. "
                        f"your split is {plan['split']}, {plan['days_per_week']} days a week. "
                        "i'll text you each morning with what's on deck. want to start with module 1, or do you want any plan tweaks first?"
                    )
                except ScheduleLimitError as e:
                    names = ", ".join(e.active_labels)
                    response_text = (
                        f"your fitmax profile is saved, but you already have {len(e.active_labels)} active modules ({names}). "
                        "stop one of them first and then come back to start fitmax."
                    )

                if _persist_chat_history(channel):
                    user_message = ChatHistory(
                        user_id=user_uuid,
                        role="user",
                        content=message_text,
                        channel=channel,
                        created_at=datetime.utcnow(),
                    )
                    assistant_message = ChatHistory(
                        user_id=user_uuid,
                        role="assistant",
                        content=response_text,
                        channel=channel,
                        created_at=datetime.utcnow(),
                    )
                    db.add(user_message)
                    db.add(assistant_message)
                await db.commit()
                return _finalize_assistant_message(response_text), []

    # --- Hairmax chat onboarding (deterministic, same pattern as fitmax) ---
    if run_hairmax_onboarding:
        hairmax_profile = dict(profile.get("hairmax_profile") or {})
        seeded = _hairmax_seed_profile_from_onboarding(hairmax_profile, onboarding)
        if seeded != hairmax_profile:
            hairmax_profile = seeded
            profile["hairmax_profile"] = hairmax_profile
            user.profile = profile
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()

        updates = _extract_hairmax_updates(message_text, hairmax_profile)
        missing_next = _hairmax_missing_fields(hairmax_profile)
        if missing_next:
            nxt = missing_next[0]
            if nxt == "daily_styling" and "daily_styling" not in updates:
                s_low = (message_text or "").strip().lower()
                yes_words = ("yes", "y", "yeah", "yep", "yea", "sure", "definitely")
                no_words = ("no", "n", "nope", "nah", "not really", "none", "minimal", "barely")
                for w in yes_words:
                    if re.search(rf"\b{re.escape(w)}\b", s_low):
                        updates["daily_styling"] = "yes"
                        break
                if "daily_styling" not in updates:
                    for w in no_words:
                        if re.search(rf"\b{re.escape(w)}\b", s_low):
                            updates["daily_styling"] = "no"
                            break
            elif nxt == "thinning" and "thinning" not in updates:
                s_low = (message_text or "").strip().lower()
                yes_words = ("yes", "y", "yeah", "yep", "yea", "sure", "definitely")
                no_words = ("no", "n", "nope", "nah", "not really", "none", "minimal", "barely")
                for w in yes_words:
                    if re.search(rf"\b{re.escape(w)}\b", s_low):
                        updates["thinning"] = "yes"
                        break
                if "thinning" not in updates:
                    for w in no_words:
                        if re.search(rf"\b{re.escape(w)}\b", s_low):
                            updates["thinning"] = "no"
                            break

            # Generic fuzzy fallback — see fitmax block above. Stops re-asking
            # when the user's reply logically maps to one of the offered
            # choices but isn't a strict-equal string match.
            if nxt not in updates:
                _, choices = HAIRMAX_QUESTION_MAP.get(nxt, ("", []))
                if choices:
                    coerced = _coerce_to_choice(message_text, choices)
                    if coerced is not None:
                        updates[nxt] = coerced
        if updates:
            hairmax_profile.update(updates)
            profile["hairmax_profile"] = hairmax_profile
            user.profile = profile
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()

        missing = _hairmax_missing_fields(hairmax_profile)

        if not hairmax_schedule_active and missing:
            if not any(hairmax_profile.values()):
                response_text = (
                    "hey, setting up your hairmax schedule. just need a few quick answers. "
                    + _hairmax_next_question(hairmax_profile)
                )
            else:
                response_text = _hairmax_next_question(hairmax_profile)
            choices_for_step = _hairmax_next_choices(hairmax_profile)

            if _persist_chat_history(channel):
                user_message = ChatHistory(
                    user_id=user_uuid,
                    role="user",
                    content=message_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                assistant_message = ChatHistory(
                    user_id=user_uuid,
                    role="assistant",
                    content=response_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                db.add(user_message)
                db.add(assistant_message)
            await db.commit()
            ft = _finalize_assistant_message(response_text)
            return ft, choices_for_step

        if not hairmax_schedule_active and not missing:
            profile.pop("hairmax_chat_setup", None)
            profile.pop("hairmax_chat_setup_at", None)
            user.profile = profile
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()

            wake = str(onboarding.get("wake_time") or "07:00")
            sleep = str(onboarding.get("sleep_time") or "23:00")

            try:
                schedule = await schedule_service.generate_maxx_schedule(
                    user_id=user_id,
                    maxx_id="hairmax",
                    db=db,
                    rds_db=rds_db if rds_db else None,
                    subscription_tier=(getattr(user, "subscription_tier", None) if user else None),
                    wake_time=wake,
                    sleep_time=sleep,
                    skin_concern=None,
                    outside_today=False,
                    override_hair_type=hairmax_profile.get("hair_type"),
                    override_scalp_state=hairmax_profile.get("scalp_state"),
                    override_daily_styling=_normalize_hair_yes_no(hairmax_profile.get("daily_styling")),
                    override_thinning=_normalize_hair_yes_no(hairmax_profile.get("thinning")),
                )
                user_context["active_maxx_schedule"] = schedule
                schedule_summary = _summarise_schedule(schedule)
                response_text = schedule_summary
            except ScheduleLimitError as e:
                names = ", ".join(e.active_labels)
                response_text = (
                    f"your hairmax profile is saved, but you already have {len(e.active_labels)} active modules ({names}). "
                    "stop one of them first and then come back to start hairmax."
                )

            if _persist_chat_history(channel):
                user_message = ChatHistory(
                    user_id=user_uuid,
                    role="user",
                    content=message_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                assistant_message = ChatHistory(
                    user_id=user_uuid,
                    role="assistant",
                    content=response_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                db.add(user_message)
                db.add(assistant_message)
            await db.commit()
            return _finalize_assistant_message(response_text), []

    # --- Bonemax chat onboarding (deterministic, mirrors fit/hair pattern) ---
    if run_bonemax_onboarding:
        bonemax_profile = dict(profile.get("bonemax_profile") or {})
        seeded = _bonemax_seed_profile_from_onboarding(bonemax_profile, onboarding)
        if seeded != bonemax_profile:
            bonemax_profile = seeded
            profile["bonemax_profile"] = bonemax_profile
            user.profile = profile
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()

        updates = _extract_bonemax_updates(message_text, bonemax_profile)
        missing_next = _bonemax_missing_fields(bonemax_profile)
        if missing_next:
            nxt = missing_next[0]
            if nxt not in updates:
                _, choices = BONEMAX_QUESTION_MAP.get(nxt, ("", []))
                if choices:
                    coerced = _coerce_to_choice(message_text, choices)
                    if coerced is not None:
                        updates[nxt] = coerced

        if updates:
            bonemax_profile.update(updates)
            profile["bonemax_profile"] = bonemax_profile
            user.profile = profile
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()

        missing = _bonemax_missing_fields(bonemax_profile)
        if not bonemax_schedule_active and missing:
            if not any(bonemax_profile.values()):
                response_text = (
                    "hey, setting up your bonemax schedule. just need a few quick answers. "
                    + _bonemax_next_question(bonemax_profile)
                )
            else:
                response_text = _bonemax_next_question(bonemax_profile)
            choices_for_step = _bonemax_next_choices(bonemax_profile)

            if _persist_chat_history(channel):
                user_message = ChatHistory(
                    user_id=user_uuid,
                    role="user",
                    content=message_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                assistant_message = ChatHistory(
                    user_id=user_uuid,
                    role="assistant",
                    content=response_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                db.add(user_message)
                db.add(assistant_message)
            await db.commit()
            return _finalize_assistant_message(response_text), choices_for_step

        if not bonemax_schedule_active and not missing:
            profile.pop("bonemax_chat_setup", None)
            profile.pop("bonemax_chat_setup_at", None)
            profile["bonemax_profile"] = bonemax_profile
            user.profile = profile
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()

            wake = _normalize_clock_hhmm(onboarding.get("wake_time")) or "07:00"
            sleep = _normalize_clock_hhmm(onboarding.get("sleep_time")) or "23:00"
            wf = _coerce_to_choice(str(bonemax_profile.get("workout_frequency") or ""), ["0", "1-2", "3-4", "5+"])
            tmj = _normalize_hair_yes_no(bonemax_profile.get("tmj_history")) or "no"
            gum = _normalize_hair_yes_no(bonemax_profile.get("mastic_gum_regular")) or "no"
            screen = _normalize_hair_yes_no(bonemax_profile.get("heavy_screen_time")) or "no"

            # Persist canonical BoneMax fields so future schedule refreshes skip intake.
            merged_onboarding = dict(onboarding or {})
            merged_onboarding["bonemax_workout_frequency"] = wf
            merged_onboarding["bonemax_tmj_history"] = tmj
            merged_onboarding["bonemax_mastic_gum_regular"] = gum
            merged_onboarding["bonemax_heavy_screen_time"] = screen
            user.onboarding = merged_onboarding
            flag_modified(user, "onboarding")
            onboarding = merged_onboarding

            try:
                schedule = await schedule_service.generate_maxx_schedule(
                    user_id=user_id,
                    maxx_id="bonemax",
                    db=db,
                    rds_db=rds_db if rds_db else None,
                    subscription_tier=(getattr(user, "subscription_tier", None) if user else None),
                    wake_time=str(wake),
                    sleep_time=str(sleep),
                    skin_concern=None,
                    outside_today=False,
                    override_workout_frequency=wf,
                    override_tmj_history=tmj,
                    override_mastic_gum_regular=gum,
                    override_heavy_screen_time=screen,
                )
                user_context["active_maxx_schedule"] = schedule
                response_text = _summarise_schedule(schedule)
            except ScheduleLimitError as e:
                names = ", ".join(e.active_labels)
                response_text = (
                    f"your bonemax profile is saved, but you already have {len(e.active_labels)} active modules ({names}). "
                    "stop one of them first and then come back to start bonemax."
                )

            if _persist_chat_history(channel):
                user_message = ChatHistory(
                    user_id=user_uuid,
                    role="user",
                    content=message_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                assistant_message = ChatHistory(
                    user_id=user_uuid,
                    role="assistant",
                    content=response_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                db.add(user_message)
                db.add(assistant_message)
            await db.commit()
            return _finalize_assistant_message(response_text), []

    # --- Fitmax meal logging from natural language (average macro lookup) ---
    if user:
        is_fitmax_context = (
            maxx_id == "fitmax"
            or str((profile or {}).get("chat_pending_module") or "").lower() == "fitmax"
            or bool((profile or {}).get("fitmax_plan"))
            or (active_schedule and str(active_schedule.get("maxx_id", "")).lower() == "fitmax")
        )
        food_log = await _fitmax_estimate_food_log(message_text) if is_fitmax_context else None
        if food_log:
            plan = (profile or {}).get("fitmax_plan") or {}
            calorie_target = int(plan.get("calories") or 2340)
            consumed_before = _fitmax_consumed_from_history(history)
            consumed_now = consumed_before + int(food_log["calories"])
            remaining = max(0, calorie_target - consumed_now)
            heuristic_note = (
                " i estimated this from a typical dish portion since exact product data wasn't available."
                if food_log.get("used_heuristic")
                else ""
            )

            response_text = (
                f"logged. that's roughly {food_log['calories']} calories and {food_log['protein_g']}g protein "
                f"({food_log['carbs_g']}g carbs, {food_log['fat_g']}g fat). "
                f"you've got {remaining} calories left today.{heuristic_note}"
            )

            if _persist_chat_history(channel):
                user_message = ChatHistory(
                    user_id=user_uuid,
                    role="user",
                    content=message_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                assistant_message = ChatHistory(
                    user_id=user_uuid,
                    role="assistant",
                    content=response_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                db.add(user_message)
                db.add(assistant_message)
            await db.commit()
            return _finalize_assistant_message(response_text), []

    existing_maxx = None
    if maxx_id and explicit_schedule_start:
        if maxx_id == "fitmax":
            existing_maxx = fitmax_schedule_active
        elif maxx_id == "hairmax":
            existing_maxx = hairmax_schedule_active
        elif maxx_id == "bonemax":
            existing_maxx = bonemax_schedule_active
        else:
            try:
                existing_maxx = await schedule_service.get_maxx_schedule(user_id, maxx_id, db=db)
            except Exception:
                existing_maxx = None

        # App "Start schedule" for HeightMax + full onboarding → generate immediately (no redundant LLM Q&A).
        if (
            maxx_id == "heightmax"
            and not existing_maxx
            and user
            and init_context
            and maxx_id == "heightmax"
            and _heightmax_demographics_complete(onboarding)
            and _is_heightmax_app_kickoff_message(message_text)
        ):
            final_wake = _normalize_clock_hhmm(onboarding.get("wake_time")) or "07:00"
            final_sleep = _normalize_clock_hhmm(onboarding.get("sleep_time")) or "23:00"
            ra = _safe_int_age(onboarding.get("age"))
            rs = str(onboarding.get("gender") or onboarding.get("sex") or "").strip()
            rh_raw = onboarding.get("height")
            rh = str(rh_raw).strip() if rh_raw is not None else ""
            try:
                await _persist_heightmax_onboarding_from_chat(
                    user=user,
                    db=db,
                    resolved_age=ra,
                    resolved_sex=rs,
                    resolved_height=rh,
                    final_wake=str(final_wake),
                    final_sleep=str(final_sleep),
                )
            except Exception as persist_err:
                logger.warning("heightmax fast-path persist failed: %s", persist_err)
            try:
                schedule = await schedule_service.generate_maxx_schedule(
                    user_id=user_id,
                    maxx_id="heightmax",
                    db=db,
                    rds_db=rds_db if rds_db else None,
                    subscription_tier=(getattr(user, "subscription_tier", None) if user else None),
                    wake_time=str(final_wake),
                    sleep_time=str(final_sleep),
                    skin_concern=None,
                    outside_today=False,
                    override_age=ra,
                    override_sex=rs if rs else None,
                    override_height=rh if rh else None,
                    height_components=None,
                )
                await _persist_user_wake_sleep(user, db, str(final_wake), str(final_sleep))
                schedule_summary = _summarise_schedule(schedule)
                response_text = (
                    "your heightmax schedule is locked in. open the schedule tab for reminders.\n\n"
                    f"{schedule_summary}"
                )
            except ScheduleLimitError as e:
                names = ", ".join(e.active_labels)
                response_text = (
                    f"you already have {len(e.active_labels)} active modules ({names}). "
                    "stop one of them first, then come back to start heightmax."
                )
            except Exception as gen_err:
                logger.exception("HeightMax fast-path schedule generation failed: %s", gen_err)
                response_text = "had trouble building your heightmax schedule -- try again in a sec."
            if _persist_chat_history(channel):
                user_message = ChatHistory(
                    user_id=user_uuid,
                    role="user",
                    content=message_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                assistant_message = ChatHistory(
                    user_id=user_uuid,
                    role="assistant",
                    content=response_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                db.add(user_message)
                db.add(assistant_message)
            await db.commit()
            return _finalize_assistant_message(response_text), []

        if existing_maxx:
            user_context["active_maxx_schedule"] = existing_maxx
            message = f"[SYSTEM: User opened {maxx_id} and already has an active schedule.]\n\n{message}"
        elif maxx_id == "heightmax":
            _hp = _heightmax_global_profile_hint(onboarding)
            _h_demo_ok = _heightmax_demographics_complete(onboarding)
            _h_first_turn_rule = (
                "FIRST TURN WHEN AGE + GENDER + HEIGHT ARE ALREADY IN THE \"KNOWN\" BLOCK ABOVE: "
                "do not greet with questions. call generate_maxx_schedule immediately (one tool call) using ONLY those values plus wake_time/sleep_time from that block or 07:00/23:00. "
                "do NOT re-ask age, sex/gender, height, wake, sleep, or anything listed under \"ALSO ALREADY ON PROFILE\"."
                if _h_demo_ok
                else (
                    "FIRST TURN: greet very briefly that you're setting up heightmax, then ask ONLY the first missing field among age, sex/gender, height (one question). "
                    "never re-ask anything already in the KNOWN or ALSO ALREADY ON PROFILE blocks."
                )
            )
            message = f"""[SYSTEM: you are running the HEIGHTMAX schedule setup.

{_hp}the user just opened heightmax to start a new schedule. follow the same tone and style you use for other maxx modules: short, casual, direct, and focused on getting their schedule locked in.

CRITICAL -- FORBIDDEN FOR HEIGHTMAX
- NEVER ask "outside today" or "you gonna be outside today" or "will you be outside" -- that is ONLY for Skinmax. HeightMax does NOT use outside_today. If you ask this, you have failed.

MAIN RULES FOR HEIGHTMAX
- do NOT ask "what is your main concern?" or any generic concern questions.
- height is already the focus. don't ask what area they want to work on.
- GLOBAL ONBOARDING: age, gender, height, wake, and sleep are usually already in user_context.onboarding from app signup. NEVER ask for any field that appears in KNOWN FROM GLOBAL ONBOARDING or ALSO ALREADY ON PROFILE above.
- {_WAKE_SLEEP_NEVER_ASK}
- your job is to grab any missing demographic info (only if not in onboarding), then call generate_maxx_schedule once. the backend builds their full HeightMax schedule in one shot (all standard tracks on). do NOT tell them to tap any in-app button, toggle, or "choose height schedule parts" -- users on SMS/text have no such UI and it causes confusion. after the tool runs, tell them the schedule is locked in and to open the Schedule tab in the app for pings.

WHAT YOU'RE ALLOWED TO ASK FOR (ONLY IF MISSING FROM user_context.onboarding / not in KNOWN above)
- age -- ONLY if not already known
- sex / gender -- ONLY if not already known (field may be "gender")
- current height -- ONLY if not already known
- (never wake/sleep -- see rule above; never re-ask optional heightmax fields already on profile)

HOW TO RUN THE FLOW
1) {_h_first_turn_rule}

2) read user_context.onboarding first. ONLY ask for fields that are missing.
   - if age is missing: ask "how old are you?"
   - if sex / gender is missing: ask "what's your sex or gender?"
   - if height is missing: ask "what's your current height?" (any format is fine)

   ask ONE question at a time when something is missing. if age, gender, and height are already known, do NOT ask them again. do NOT ask about outside today. do NOT ask wake or sleep.

3) once you have age, sex, and height (from onboarding and/or user answers), call generate_maxx_schedule exactly once with:
   - maxx_id = "heightmax"
   - wake_time = from onboarding, else 07:00
   - sleep_time = from onboarding, else 23:00
   - skin_concern = null / empty (heightmax doesn't use concerns)
   - outside_today = false (heightmax doesn't use outside_today)
   - age = their age (number, if known)
   - sex = their sex/gender (if known)
   - height = their current height in any format, e.g. "5'10" or "178cm" (if known)

   the backend then creates the full schedule -- same as other maxx modules.

4) after generate_maxx_schedule returns, your reply should be short: confirm heightmax is locked in and they should open the schedule tab for reminders. optional one line on what HeightMax focuses on (sleep, posture/decompression, sprints, nutrition habits) if they seem unsure. never mention toggles, "below", or buttons. never use * or ** (no markdown).

STYLE
- same tone as skinmax/fitmax: friendly, casual, not overly motivational.
- stay focused on heightmax in this flow. don't switch topics to skin, hair, or gym unless a different module is explicitly opened.
- keep responses concise. no long lectures, no custom step-by-step routines you invent yourself.]\n\n{message}"""
        elif maxx_id == "hairmax":
            _hair_known = _hairmax_onboarding_known_block(onboarding)
            message = f"""[SYSTEM: you are running the HAIRMAX schedule setup.

{_hair_known}the user just opened hairmax to start a new schedule. follow the same tone and style as other maxx modules: short, casual, direct, focused on getting their schedule locked in.

CRITICAL -- EVERY TURN IN THIS THREAD (until generate_maxx_schedule succeeds):
- you are ONLY in hairmax. NEVER ask skin concern, SPF, UV, "skinmax", or "focus area for skin".
- NEVER ask "outside today", "going outside", sun, or sunscreen -- those are SKINMAX-only. asking them here is a failure.

DO NOT:
- do not ask "what is your main concern?" or any generic concern questions.
- do not ask if they will be outside today (that's only for skin).
- do not invent your own detailed routine; the backend schedule handles tasks and timings.
- stay inside hairmax. don't switch to skin, height, or fit here.
- {_WAKE_SLEEP_NEVER_ASK}

what you're allowed to ask for (only if missing in user_context or onboarding):
- hair basics:
  - hair type: straight, wavy, curly, coily
  - scalp state: normal, dry/flaky, oily/greasy, itchy
  - daily styling/product use: "do you use hair products or styling most days?" (yes/no)
- thinning:
  - "do you notice hair thinning or a receding hairline?" (yes/no)
- (never ask wake_time or sleep_time -- pass from onboarding or 07:00 / 23:00 in the tool)

guiding rules (for how you talk; backend does final schedule):
- shampoo/conditioner:
  - default shampoo suggestion is gentle, sulfate-free, paraben-free, scalp-focused, not harsh stripping.
  - default conditioner: always on hair strands, not on scalp unless clearly scalp-safe. leave-in conditioner is a safe generic rec.
  - anti-dandruff shampoo is only relevant if flakes are oily/yellow/persistent or scalp stays itchy despite gentle products.
  - never push "no shampoo"; "less often" is okay when over-washed.
- when to wash:
  - straight/wavy: about 2–3x/week.
  - curly: shampoo less often with fixed wash days; optional co-wash between.
  - daily product users: enough washing to clear buildup every couple days.
  - if dry with small white flakes/over-washed: reduce frequency.
  - if greasy/itchy/buildup: increase frequency.
- thinning + minoxidil:
  - only for users who say they have thinning/receding.
  - minoxidil is daily (non-negotiable).
  - main anchor: pm skincare/night routine; optional second morning application for advanced users.
  - reminder style: "minoxidil. thinning areas only." with consistency pressure like "miss days = lose gains." and identity framing like "you either maintain your hairline or watch it go."
  - if they skip a lot, tone can escalate slightly. if they're consistent, keep reminders cleaner and fewer (e.g., 1/day).
- dermastamp/roller:
  - only for users with thinning.
  - default frequency: 1x/week, max 2x/week (never more).
  - timing: evening, near pm routine / before bed, ideally same day each week.
  - reminder style: "dermastamp tonight. hairline/crown only."

flow for a new hairmax schedule:
1) greet briefly and say you're setting up their hairmax schedule.
2) check the ALREADY KNOWN block above plus user_context/onboarding. only ask what's missing. STRICT ORDER -- do not skip ahead:
   - ask in order: hair type → scalp → daily styling → thinning (skip any line already listed as known).
   ask one question at a time. you MUST have all four hair lines (type, scalp, daily styling, thinning) before calling the tool unless they were pre-filled.
3) call generate_maxx_schedule exactly once once hair fields are complete. pass wake_time and sleep_time from onboarding only, or 07:00 and 23:00 if missing -- never ask the user for them. the backend will reject the call if hair fields are missing -- pass them explicitly:
   - maxx_id = "hairmax"
   - hair_type = e.g. "curly"
   - scalp_state = e.g. "oily/greasy"
   - daily_styling = "yes" or "no"
   - thinning = "yes" or "no"
   - wake_time = user's wake time
   - sleep_time = user's sleep time
   - skin_concern = null/empty (hairmax does not use concerns)
   - outside_today = false (hairmax does not use outside_today)
4) after generate_maxx_schedule runs and the backend appends a schedule summary, confirm in your usual short style, e.g.:
   - "your hairmax schedule is locked in. check your schedule tab."
   do not invent new tasks or times; the backend already scheduled everything.
   never use * or ** in your reply (no markdown bold).

style:
- same as other maxx modules: friendly, casual, short.
- one question at a time.
- no long lectures, no generic concern questions.

your first response in this hairmax start flow should:
- briefly acknowledge they're starting hairmax, and
- immediately ask the first missing hair-related question (hair type / scalp / products / thinning). if all hair basics are known, call generate_maxx_schedule (wake/sleep from onboarding or defaults) -- never ask wake/sleep.]\n\n{message}"""
        elif maxx_id == "skinmax":
            inferred_sc = _infer_skin_concern_id_from_onboarding(onboarding)
            wt_ok = _normalize_clock_hhmm(onboarding.get("wake_time"))
            st_ok = _normalize_clock_hhmm(onboarding.get("sleep_time"))
            known_lines: list[str] = [_WAKE_SLEEP_NEVER_ASK]
            if inferred_sc:
                known_lines.append(
                    f'SKIN CONCERN already inferred from app onboarding -- use skin_concern="{inferred_sc}" in generate_maxx_schedule. '
                    "Do NOT ask the user to pick acne vs pigmentation etc. unless they explicitly want to change focus."
                )
            if wt_ok:
                known_lines.append(f"(for the tool) use wake_time={wt_ok} from onboarding.")
            if st_ok:
                known_lines.append(f"(for the tool) use sleep_time={st_ok} from onboarding.")
            sl = onboarding.get("skincare_routine_level")
            if sl:
                known_lines.append(f"skincare_routine_level={sl} (use as context; do not re-ask).")
            known_block = "\n".join(known_lines)
            message = f"""[SYSTEM: Skinmax schedule setup -- user started the module schedule from the app.

{known_block}

RULES:
- GLOBAL ONBOARDING + USER CONTEXT are source of truth.
- Before generate_maxx_schedule you need: skin_concern, wake_time, sleep_time (from onboarding or 07:00/23:00 defaults -- NEVER ask), and outside_today (boolean).
- ONE question per message. Order: (1) skin concern ONLY if not pre-filled above, (2) then ONLY "planning to be outside much today?" for outside_today.
- If skin concern is already pre-filled above, greet briefly and your FIRST question must be ONLY about outside today.
- For wake/sleep in the tool: use values from onboarding if present; otherwise 07:00 and 23:00.

STAY IN SKINMAX (CRITICAL):
- you are ONLY in skinmax. NEVER ask hair-type, scalp state, daily styling, hair-product use, thinning, or any other hairmax-only question -- those belong to a different module.
- NEVER ask about workouts, training days, gym, weight, or any fitmax/bonemax topic.
- if the user replies with something off-topic (e.g. "wavy", "curly", "3 days a week"), do NOT pivot to that topic. politely re-ask the current skinmax question (skin concern or outside_today).

ANTI-REDUNDANCY (CRITICAL):
- NEVER ask the skin concern / focus question again if it appears anywhere in THIS chat thread (user already said e.g. "acne") OR if pre-filled above OR inferable from onboarding.
- If the user already answered concern + outside today in this thread, call generate_maxx_schedule immediately -- do NOT rephrase the same questions.
- Do NOT repeat "what's your main skin concern" in different wording after they already answered once.

Call generate_maxx_schedule once when you have skin_concern + outside_today (wake/sleep never from user chat). maxx_id=\"skinmax\".]\n\n{message}"""
        elif maxx_id == "bonemax":
            _bone_pre = _bonemax_onboarding_known_block(onboarding)
            bone_sys = await asyncio.to_thread(
                resolve_prompt,
                PromptKey.BONEMAX_NEW_SCHEDULE_SYSTEM,
                BONEMAX_NEW_SCHEDULE_SYSTEM_PROMPT,
            )
            message = f"{_bone_pre}{bone_sys}\n\n{message}"
        elif maxx_id == "fitmax":
            _wt = _normalize_clock_hhmm(onboarding.get("wake_time")) or "07:00"
            _st = _normalize_clock_hhmm(onboarding.get("sleep_time")) or "23:00"
            _fitmax_known = _fitmax_known_from_onboarding(onboarding, profile)
            message = f"""[SYSTEM: you are running the FITMAX schedule setup (training & nutrition).

{_fitmax_known}

CRITICAL -- FORBIDDEN FOR FITMAX (not Skinmax)
- NEVER ask "outside today", "going outside", UV, sunscreen, or SPF. FitMax always uses outside_today=false in generate_maxx_schedule.
- NEVER ask wake_time or sleep_time to complete setup -- use user_context.onboarding or pass wake_time="{_wt}" and sleep_time="{_st}" in the tool. Only acknowledge if the user volunteers a correction.

WHAT TO COLLECT (only if missing from ALREADY KNOWN above)
- goal: fat loss, muscle gain, recomp, maintenance, or performance (map to skin_concern in tool, e.g. "muscle gain" or "muscle_gain")
- weight in kg (pass body_weight_kg in the tool, or user says lbs -- convert)
- height (pass height as string, e.g. 5'9 or 175cm -- same as heightmax)
- age (pass age integer)
- biological sex male/female (pass sex or gender)
- training days per week 3–6 (pass training_days_per_week integer)

OPTIONAL (nice to have; not required to call the tool)
- training experience: beginner / intermediate / advanced (pass training_experience)
- equipment (pass fitmax_equipment)
- session length minutes (pass session_minutes)
- daily activity outside gym (pass daily_activity_level: sedentary, lightly active, moderately active, very active)
- dietary restrictions (pass dietary_restrictions)

HOW TO CALL generate_maxx_schedule (once all required fields are known)
- maxx_id = "fitmax"
- outside_today = false
- wake_time = "{_wt}", sleep_time = "{_st}"
- skin_concern = short goal phrase from the user (used with other args for routing)
- age, sex or gender, height, body_weight_kg, training_days_per_week -- pass explicitly from the conversation
- optional: training_experience, fitmax_equipment, session_minutes, daily_activity_level, dietary_restrictions

If the tool returns "missing required fields for fitmax: ...", ask ONLY for the listed items, one at a time.

ANTI-REDUNDANCY
- Do not repeat questions for fields already listed under ALREADY KNOWN.
- Do not use the Skinmax flow (skin concern + outside today).

STYLE: short, casual, same as other maxxes.]\n\n{message}"""
        else:
            concern_question, concerns = None, []
            if rds_db:
                try:
                    from models.rds_models import Maxx
                    result = await rds_db.execute(select(Maxx).where(Maxx.id == maxx_id))
                    maxx_row = result.scalar_one_or_none()
                    if maxx_row and maxx_row.concern_question and maxx_row.concerns:
                        concern_question = maxx_row.concern_question
                        concerns = maxx_row.concerns or []
                except Exception:
                    pass
            if not concern_question or not concerns:
                from services.maxx_guidelines import MAXX_GUIDELINES
                fallback = MAXX_GUIDELINES.get(maxx_id)
                if fallback:
                    concern_question = fallback.get("concern_question")
                    concerns = fallback.get("concerns") or []

            if concern_question and concerns:
                concerns_str = ", ".join(c.get("label", c.get("id", "")) for c in concerns)
                concern_ids = ", ".join(c.get("id", "") for c in concerns if c.get("id"))
                message = f"""[SYSTEM: User wants to start their {maxx_id} schedule. CRITICAL -- follow this EXACT order:
{_WAKE_SLEEP_NEVER_ASK}
1. Greet briefly and explain what the schedule does.
2. Your FIRST question MUST be: "{concern_question}" Options: {concerns_str}. Wait for their answer.
3. After they pick a concern, ask: "Are you planning to be outside much today?" -- wait for answer (needed for UV / SPF logic where applicable).
4. Call generate_maxx_schedule with maxx_id="{maxx_id}", skin_concern=their chosen concern ({concern_ids}), wake_time and sleep_time from user_context.onboarding (or 07:00 and 23:00 if missing), and outside_today.
Ask ONE question at a time. Your very first response must ask the concern question.]\n\n{message}"""
            else:
                message = (
                    f"[SYSTEM: User wants to start {maxx_id} schedule. {_WAKE_SLEEP_NEVER_ASK} "
                    "Ask outside today only if this module needs UV context; otherwise call generate_maxx_schedule with wake/sleep from onboarding or 07:00/23:00.]\n\n"
                    + message
                )

    # --- Image handling ---
    image_data = None
    if attachment_url and attachment_type == "image":
        image_data = await storage_service.get_image(attachment_url)

    # --- Fast product-link path ---
    link_maxx = list(turn_intent.get("maxx_hints") or [])
    if not link_maxx and active_hint:
        link_maxx = [active_hint]
    if not link_maxx and user:
        try:
            all_active = await schedule_service.get_all_active_schedules(user_id, db)
            for s in all_active:
                mid = s.get("maxx_id")
                if mid:
                    link_maxx.append(mid)
        except Exception:
            pass
    if (
        not explicit_schedule_start
        and not image_data
        and _looks_like_link_request(message_text)
        and link_maxx
    ):
        link_response = ""
        for _lm in link_maxx[:3]:
            link_response = await product_links_from_context(
                message=message_text,
                maxx_id=str(_lm),
            )
            if link_response:
                break
        if link_response:
            if _persist_chat_history(channel):
                user_message = ChatHistory(
                    user_id=user_uuid,
                    role="user",
                    content=message_text,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                assistant_message = ChatHistory(
                    user_id=user_uuid,
                    role="assistant",
                    content=link_response,
                    channel=channel,
                    created_at=datetime.utcnow(),
                )
                db.add(user_message)
                db.add(assistant_message)
            await db.commit()
            logger.info("[FAST_LINKS] user=%s maxx=%s", str(user_id)[:8], link_maxx[0])
            return _finalize_assistant_message(link_response), []

    # --- RAG retrieval (legacy agent path only; fast knowledge turns return earlier) ---
    # retrieve_chunks returns [] on any failure, so chat degrades gracefully.
    retrieved_chunks: list[dict] = []
    partner_rule_ids: list[int] = []
    try:
        _maxx = maxx_id or ((active_schedule or {}).get("maxx_id") if active_schedule else None)
        if _maxx and turn_intent.get("intent") != "KNOWLEDGE":
            retrieved_chunks = await rag_retrieve_chunks(
                db,
                maxx_id=str(_maxx),
                query=message_text,
                k=int(getattr(settings, "rag_top_k", 4) or 4),
                min_similarity=float(getattr(settings, "rag_score_threshold", 0.35) or 0.35),
            )
    except Exception as rag_err:
        logger.warning("RAG retrieval skipped: %s", rag_err)

    user_context["coaching_context"] = await coaching_service.build_full_context(
        user_id,
        db,
        rds_db,
        intent=str(turn_intent.get("intent") or "OTHER"),
    )

    # --- Inject tone preamble + RAG context + partner suffix into coaching_context ---
    # user_context.coaching_context is later rendered as `## USER CONTEXT:` by the
    # chat system prompt builder, so appending here is sufficient -- no agent tool
    # wiring needed.
    existing_ctx = user_context.get("coaching_context") or ""
    extras: list[str] = []
    tone_prefix = tone_preamble(getattr(user, "coaching_tone", None) if user else None)
    if tone_prefix:
        extras.append(tone_prefix)
    if retrieved_chunks:
        lines = [
            "[COURSE CONTEXT -- answer using this when the user asks about the course. "
            "If the answer isn't here, say so rather than guessing.]"
        ]
        for i, c in enumerate(retrieved_chunks, 1):
            title = c.get("doc_title") or ""
            sim = c.get("similarity") or 0.0
            lines.append(f"\n--- Chunk {i} ({title}, sim={sim:.2f}) ---\n{c.get('content','').strip()}")
        extras.append("\n".join(lines))
    try:
        partner_suffix, partner_rule_ids = await get_matching_rule_suffix(
            db, message_text, [c.get("content", "") for c in retrieved_chunks]
        )
        if partner_suffix:
            extras.append(partner_suffix)
    except Exception as partner_err:
        logger.warning("partner rule match skipped: %s", partner_err)
    if extras:
        user_context["coaching_context"] = (existing_ctx + "\n\n" + "\n\n".join(extras)).strip()

    # --- Agent call ---
    # Two paths: the LangGraph pipeline (CHAT_USE_LANGGRAPH=true) or the direct
    # AgentExecutor (legacy). Both return (response_text, modify_schedule_ran).
    logger.info("[CHAT] user=%s | %.100s", str(user_id)[:8], message or "")

    def _mk_tools():
        return make_chat_tools(
            db=db,
            rds_db=rds_db,
            user_id=user_id,
            user=user,
            onboarding=onboarding,
            active_schedule=active_schedule,
            channel=channel,
            user_context=user_context,
        )

    user_turn_persisted = False
    if _persist_chat_history(channel):
        db.add(
            ChatHistory(
                user_id=user_uuid,
                role="user",
                content=message_text,
                channel=channel,
                created_at=datetime.utcnow(),
            )
        )
        await db.commit()
        user_turn_persisted = True

    if getattr(settings, "chat_use_langgraph", False):
        from services.lc_graph import run_graph_chat

        try:
            graph_result = await run_graph_chat(
                message=message,
                history=history[-CHAT_HISTORY_WINDOW:],
                user_context=user_context,
                user_id=user_id,
                make_tools=_mk_tools,
                maxx_id=maxx_id,
                active_maxx=(active_schedule or {}).get("maxx_id") if active_schedule else None,
                channel=channel,
                image_data=image_data,
            )
            response_text = graph_result["response"]
            modify_schedule_ran = graph_result["schedule_mutated"]
            # Graph-retrieved chunks override the pre-retrieval we did above, so the
            # audit trail reflects what actually informed the answer.
            if graph_result.get("retrieved"):
                retrieved_chunks = graph_result["retrieved"]
        except Exception as llm_err:
            logger.exception("lc_graph failed for user %s: %s", user_id, llm_err)
            if _persist_chat_history(channel):
                db.add(
                    ChatHistory(
                        user_id=user_uuid,
                        role="assistant",
                        content=_friendly_llm_error_message(llm_err),
                        channel=channel,
                        created_at=datetime.utcnow(),
                    )
                )
                await db.commit()
            return _finalize_assistant_message(_friendly_llm_error_message(llm_err)), []
    else:
        tools = _mk_tools()
        lc_history = history_dicts_to_lc_messages(history[-CHAT_HISTORY_WINDOW:])
        try:
            response_text, modify_schedule_ran = await run_chat_agent(
                message=message,
                lc_history=lc_history,
                user_context=user_context,
                image_data=image_data,
                delivery_channel=channel,
                tools=tools,
                db=db,
                maxx_id=maxx_id,
            )
            # Web-search safety net: the agent sometimes ignores its own
            # web_search tool and falls back to "i don't see enough in the
            # docs" even though the question is web-answerable. Detect that
            # specific refusal pattern and re-run with explicit grounding.
            logger.info("[web safety net] refusal=%s personal=%s text_preview=%r",
                        _looks_like_doc_refusal(response_text),
                        _question_is_personal(message_text),
                        (response_text or "")[:100])
            if _looks_like_doc_refusal(response_text) and not _question_is_personal(message_text):
                try:
                    from services.web_search import search as _ws_search
                    q = _compress_query_for_search(message_text)
                    logger.info("[web safety net] firing search q=%r", q)
                    web_snips = await _ws_search(q, max_results=3)
                    logger.info("[web safety net] got %d chars of snippets", len(web_snips or ""))
                    if web_snips and "(no web results" not in web_snips and "(web search" not in web_snips:
                        # Re-prompt the agent with the web results as
                        # explicit context. This is a single LLM call —
                        # cheap, and produces a real answer instead of a
                        # canned refusal.
                        forced_msg = (
                            f"{message_text}\n\n"
                            "(internal: doc-RAG returned nothing useful. here are 3 fresh web "
                            "results — answer the user's question grounded in these, no preamble):\n\n"
                            f"{web_snips}"
                        )
                        response_text2, _ = await run_chat_agent(
                            message=forced_msg,
                            lc_history=lc_history,
                            user_context=user_context,
                            image_data=image_data,
                            delivery_channel=channel,
                            tools=tools,
                            db=db,
                            maxx_id=maxx_id,
                        )
                        if response_text2 and not _looks_like_doc_refusal(response_text2):
                            response_text = response_text2
                except Exception as _e:
                    logger.info("web search safety net failed (non-fatal): %s", _e)
        except Exception as llm_err:
            logger.exception("run_chat_agent failed for user %s: %s", user_id, llm_err)
            if _persist_chat_history(channel):
                db.add(
                    ChatHistory(
                        user_id=user_uuid,
                        role="assistant",
                        content=_friendly_llm_error_message(llm_err),
                        channel=channel,
                        created_at=datetime.utcnow(),
                    )
                )
                await db.commit()
            return _finalize_assistant_message(_friendly_llm_error_message(llm_err)), []

    # --- Safety net: if user clearly requested a schedule change but agent missed it ---
    # --- If user asked to change schedule times but the model didn't call modify_schedule, adapt anyway ---
    requested_schedule_mutation = (
        _looks_like_schedule_mutation_request(message_text)
        or _user_requests_schedule_change(message_text)
    )
    forced_schedule_adapted = False
    if (
        active_schedule
        and not modify_schedule_ran
        and not _looks_like_informational_question(message_text)
        and _user_requests_schedule_change(message_text)
    ):
        try:
            adapt_result = await schedule_service.adapt_schedule(
                user_id=user_id,
                schedule_id=active_schedule["id"],
                db=db,
                feedback=message_text,
            )
            summ = adapt_result.get("changes_summary", "").strip()
            if summ:
                response_text = (response_text + "\n\n" + summ).strip() if response_text else summ
            modify_schedule_ran = True
            forced_schedule_adapted = True
        except Exception as e:
            logger.exception("Forced schedule adaptation failed: %s", e)

    # Never claim "updated" when no mutation actually ran.
    if requested_schedule_mutation and not modify_schedule_ran:
        response_text = (
            "i can update your schedule, but i need the exact change. "
            "tell me what to change (for example: wake 08:00, move workout to 18:30, "
            "or mark today's fitmax post-workout task complete)."
        )
        if forced_schedule_adapted:
            logger.warning("schedule mutation guard overridden despite forced adaptation flag")


    # --- Enforce lowercase on all AI responses ---
    response_text = response_text.lower()

    # --- Save messages (app only; SMS is not stored) ---
    if _persist_chat_history(channel):
        assistant_message = ChatHistory(
            user_id=user_uuid,
            role="assistant",
            content=response_text,
            channel=channel,
            created_at=datetime.utcnow(),
            retrieved_chunk_ids=_chunk_audit_refs(retrieved_chunks),
            partner_rule_ids=partner_rule_ids or None,
        )
        if not user_turn_persisted:
            db.add(ChatHistory(
                user_id=user_uuid,
                role="user",
                content=message_text,
                channel=channel,
                created_at=datetime.utcnow(),
            ))
        db.add(assistant_message)
        await db.commit()

    # Invalidate cached context if we mutated state this turn (new schedule,
    # schedule adapt, completed/check-in). Next message will see fresh data.
    if modify_schedule_ran:
        coaching_service.invalidate_context_cache(user_id)

    # --- Background: update AI memory every ~10 messages (app thread only) ---
    # These each fire a secondary LLM call (~1-3s) and MUST NOT block the user's
    # response. We fire-and-forget on a fresh DB session because `db` closes
    # when this endpoint returns.
    total_msgs = len(history) + 2
    if _persist_chat_history(channel) and total_msgs % 10 == 0:
        _spawn_background_task(_bg_update_memory(user_id, history[-CHAT_HISTORY_WINDOW:]))

    if _persist_chat_history(channel) and total_msgs % 20 == 0:
        _spawn_background_task(_bg_detect_tone(user_id, history[-CHAT_HISTORY_WINDOW:]))

    choices_out: list[str] = []
    if maxx_id and not existing_maxx:
        choices_out = _quick_replies_from_response(response_text)
    return response_text, choices_out


async def _handle_context_change(
    user_id: str,
    message_text: str,
    db: AsyncSession,
) -> Optional[Tuple[str, list[str], Optional[dict]]]:
    """Detect schedule-impacting changes the user volunteers in chat and
    apply them deterministically — runs BEFORE the agent so the agent
    doesn't have to recognize the intent (it often won't).

    Three modes:
      A) Specific time mention → apply + regenerate active schedules
         e.g. "i wake up at 10", "going to bed at midnight"
      B) Vague timing change → store pending intent + emit slider
         e.g. "im going to wake up later", "sleeping in more"
      C) Other context (training/posture/equipment/outdoor) → merge_context
         (which itself triggers regen via the hook in the context service)

    If a previous turn left a `_pending_intent` in user_schedule_context
    and the current message looks like an answer (a number or HH:MM),
    we apply the pending intent here instead of re-detecting.

    Returns (text, choices, input_widget) when handled, or None to fall
    through.
    """
    try:
        from services.chat_intent_detector import detect_intent, get_pending_intent, hour_to_hhmm, PENDING_KEY
        from services.schedule_runtime import regenerate_active_schedules
        from services.user_context_service import get_context, merge_context, merged_user_state
        from services.lc_agent import _persist_user_wake_sleep
    except Exception as _e:  # pragma: no cover
        logger.exception("context-change import failed: %s", _e)
        return None

    user_uuid = UUID(user_id)
    user = await db.get(User, user_uuid)
    if user is None:
        return None
    onb = dict(getattr(user, "onboarding", {}) or {})
    persistent = await get_context(user_id, db)
    state = merged_user_state(onb, persistent)

    msg = (message_text or "").strip()

    # 0) Pending intent? If the user is answering a slider question we asked.
    pending = get_pending_intent(state)
    if pending:
        kind = pending.get("kind")
        # Try to parse as a number (slider answer) or HH:MM.
        m = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", msg, re.IGNORECASE)
        if m:
            h = int(m.group(1))
            mm = int(m.group(2)) if m.group(2) else 0
            suf = (m.group(3) or "").lower()
            if suf == "pm" and h < 12:
                h += 12
            elif suf == "am" and h == 12:
                h = 0
            elif kind == "wake_time" and h <= 11 and not suf:
                pass   # natural reading
            elif kind == "sleep_time" and h <= 11 and not suf and h >= 9:
                h += 12   # bedtime hours typically PM
            value = f"{h:02d}:{mm:02d}"
            await merge_context(user_id, {PENDING_KEY: None}, db)
            if kind == "wake_time":
                await _persist_user_wake_sleep(user, db, value, None)
            elif kind == "sleep_time":
                await _persist_user_wake_sleep(user, db, None, value)
            await db.commit()
            return (
                f"got it — {kind.replace('_',' ')} now {value}. retimed your active schedules.",
                [], None,
            )
        # Otherwise fall through and treat as new turn (cancel pending).
        await merge_context(user_id, {PENDING_KEY: None}, db)

    intent = detect_intent(msg, state)
    if intent is None:
        return None

    kind = intent["kind"]

    # B) Vague — emit slider.
    if intent.get("vague"):
        await merge_context(user_id, {PENDING_KEY: {"kind": kind}}, db)
        return (intent.get("hint") or "what time?", [], intent.get("slider"))

    value = intent.get("value")

    # A) Wake/sleep specific.
    if kind in ("wake_time", "sleep_time"):
        if kind == "wake_time":
            await _persist_user_wake_sleep(user, db, value, None)
        else:
            await _persist_user_wake_sleep(user, db, None, value)
        await db.commit()
        return (
            f"got it — {kind.replace('_',' ')} now {value}. retimed your active schedules.",
            [], None,
        )

    # C) Other context (training, posture, equipment, outdoor) — merging
    #    fires the regen hook in update_schedule_context's path; here we
    #    call regenerate_active_schedules explicitly since we bypass the tool.
    await merge_context(user_id, {kind: value}, db)
    try:
        await regenerate_active_schedules(user_id=user_id, db=db, reason=f"chat:{kind}")
    except Exception as _e:
        logger.warning("regen after chat intent failed (non-fatal): %s", _e)
    await db.commit()
    pretty_kind = kind.replace("_", " ")
    return (f"got it — saved {pretty_kind} = {value}. updated your active schedules.", [], None)


# (Old _handle_context_change body removed — replaced by the chat_intent_detector
#  -based version above. See services/chat_intent_detector.py for the patterns.)


# --------------------------------------------------------------------------- #
#  Tier 3 — generic schedule modification fallback                            #
#                                                                             #
#  When the user's message looks like an ad-hoc schedule change ("cancel gym  #
#  on tuesdays", "skip everything tomorrow", "move tret to mondays") that     #
#  doesn't match our regex intent patterns, we route to the diff-format LLM   #
#  adapter (services.schedule_adapter). The adapter is built for exactly      #
#  these one-shot edits — it knows day-of-week semantics now.                 #
# --------------------------------------------------------------------------- #

_SCHEDULE_MOD_VERBS = (
    "cancel", "skip", "remove", "drop", "stop", "delete", "kill",
    "add", "include", "schedule",
    "move", "shift", "push", "swap", "replace", "change",
    "no ", "not on", "don't ", "dont ",
    "less ", "more ", "fewer ", "extra ",
)
_SCHEDULE_MOD_TOKENS = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "weekday", "weekend", "today", "tomorrow", "this week", "next week",
    "morning", "afternoon", "evening", "night", "tonight",
    "task", "schedule", "routine",
)


def _looks_like_schedule_modification(message: str) -> bool:
    if not message:
        return False
    low = message.lower().strip()
    if "?" in low and any(low.startswith(q) for q in ("what", "when", "how", "why", "should i", "is")):
        # Question about the schedule, not a modification request.
        return False
    has_verb = any(v in low for v in _SCHEDULE_MOD_VERBS)
    has_token = any(t in low for t in _SCHEDULE_MOD_TOKENS)
    return has_verb and has_token


async def _handle_generic_schedule_modification(
    user_id: str,
    message_text: str,
    db: AsyncSession,
) -> Optional[Tuple[str, list[str], Optional[dict]]]:
    """If the message reads like an ad-hoc schedule edit, run it through
    the diff-format adapter. Returns the adapter's summary as the chat
    reply and persists any context_updates so future regenerations honor
    the user's standing rules ("no gym tuesdays")."""
    if not _looks_like_schedule_modification(message_text):
        return None

    user_uuid = UUID(user_id)
    res = await db.execute(
        select(UserSchedule).where(
            (UserSchedule.user_id == user_uuid)
            & (UserSchedule.is_active.is_(True))
        ).order_by(UserSchedule.updated_at.desc())
    )
    actives = list(res.scalars().all())
    if not actives:
        return None  # nothing to modify; fall through to agent (may answer informationally)

    # If the user named a max ("cancel gym" implies fitmax/heightmax;
    # "skip skin" implies skinmax) prefer that one. Otherwise touch all
    # actives so e.g. "no skincare on weekends" applies broadly.
    targets = _filter_actives_by_name(actives, message_text)
    if not targets:
        targets = actives

    try:
        from services.schedule_runtime import adapt_and_persist
    except Exception as _e:
        logger.exception("adapter import failed: %s", _e)
        return None

    summaries: list[str] = []
    op_count = 0
    for sched in targets:
        try:
            res = await adapt_and_persist(
                user_id=user_id,
                schedule_id=str(sched.id),
                db=db,
                feedback=message_text,
            )
            if res.get("ops_applied"):
                op_count += len(res["ops_applied"])
            summaries.append(f"{sched.maxx_id}: {res.get('summary') or 'updated'}")
        except Exception as e:
            logger.warning("adapter failed for max=%s: %s", sched.maxx_id, e)
            summaries.append(f"{sched.maxx_id}: couldn't apply ({e})")
    await db.commit()

    if op_count == 0:
        # Adapter understood the message but produced no ops — usually
        # means the LLM thinks the request is already satisfied. Don't
        # gaslight the user; let the chat agent fall through with a
        # natural reply instead.
        return None

    body = "; ".join(summaries)
    return (f"updated — {body}.", [], None)


def _filter_actives_by_name(actives: list, message_text: str) -> list:
    """Pick active schedules whose maxx_id is name-mentioned in the
    message. e.g. "cancel gym tuesdays" → fitmax + heightmax (since
    'gym' is workout-coded); "skip skincare" → skinmax."""
    low = (message_text or "").lower()
    names: dict[str, tuple[str, ...]] = {
        "skinmax":   ("skin", "skinmax", "skincare", "cleanse", "tret", "retinoid", "spf", "dermastamp"),
        "hairmax":   ("hair", "hairmax", "scalp", "minox", "shampoo", "haircut", "beard"),
        "heightmax": ("height", "heightmax", "posture", "stretch", "decompress", "mobility", "wall", "decompression"),
        "bonemax":   ("bone", "bonemax", "mew", "jaw", "chew", "masseter", "gum"),
        "fitmax":    ("fit", "fitmax", "gym", "lift", "workout", "training", "cardio", "press", "squat"),
    }
    hit: list = []
    for sched in actives:
        mid = (sched.maxx_id or "").lower()
        keywords = names.get(mid, ())
        if any(kw in low for kw in keywords):
            hit.append(sched)
    return hit


async def _run_onboarding_questioner(
    user_id: str,
    message_text: str,
    db: AsyncSession,
) -> Optional[Tuple[str, list[str], Optional[dict]]]:
    """If the user is mid-onboarding for a doc-driven max, drive the next
    question deterministically using onboarding_questioner. Returns
    (text, choices, input_widget) if the driver handled the turn, or None
    to fall through to the legacy/agent path.
    """
    try:
        from services.onboarding_questioner import (
            get_pending,
            make_pending,
            clear_pending,
            peek_next_question,
            field_to_question_payload,
            coerce_answer,
            detect_max_start_intent,
        )
        from services.task_catalog_service import warm_catalog, is_loaded, get_doc
        from services.user_context_service import get_context, merge_context, merged_user_state
    except Exception as _e:  # pragma: no cover
        logger.exception("question driver import failed: %s", _e)
        return None

    if not is_loaded():
        await warm_catalog()

    user_uuid = UUID(user_id)
    user = await db.get(User, user_uuid)
    onboarding = dict(getattr(user, "onboarding", {}) or {})
    persistent = await get_context(user_id, db)
    state = merged_user_state(onboarding, persistent)
    pending = get_pending(state)
    msg = (message_text or "").strip()

    # 1) Detect new start-intent — even if there's a pending onboarding for a
    # DIFFERENT max. Without this, "I want to start skinmax" mid-hairmax
    # gets coerced as the next hairmax field answer, fails, re-asks.
    # When a pending exists for a different max, we abandon the half-finished
    # one and start the new one fresh. (Prior answers stay in
    # user_schedule_context for when they come back to that maxx later.)
    new_max = detect_max_start_intent(msg)
    if new_max:
        if pending and pending.get("max") != new_max:
            logger.info(
                "[onboarding] mid-pending switch: %s -> %s; abandoning prior pending",
                pending.get("max"), new_max,
            )
        if not pending or pending.get("max") != new_max:
            next_field = peek_next_question(new_max, state)
            if next_field is None:
                # All required fields already known — let the agent handle it
                # (it'll trigger generation directly).
                return None
            await merge_context(
                user_id,
                {**clear_pending(), **{"_onboarding_pending": make_pending(new_max, next_field["id"])}},
                db,
            )
            payload = field_to_question_payload(next_field)
            switch_note = (
                f"switching to your {get_doc(new_max).display_name.lower()} schedule. "
                if pending and pending.get("max") != new_max
                else f"let's get your {get_doc(new_max).display_name.lower()} schedule going. "
            )
            text = switch_note + payload["text"].lower()
            return _finish_onboarding_turn(text, payload)
        # else: pending already matches new_max — just continue (treat as
        # repeated start of the same flow; coerce step below handles it).

    # If no pending and no start-intent, hand off to other paths.
    if not pending:
        return None

    # 2) Pending → coerce the user's answer, persist, advance.
    maxx_id = pending["max"]
    last_qid = pending["last_question"]
    doc = get_doc(maxx_id)
    if doc is None:
        # Doc disappeared (unlikely) → bail to legacy path.
        await merge_context(user_id, clear_pending(), db)
        return None

    last_field = next((f for f in doc.required_fields if f.get("id") == last_qid), None)
    if last_field is None:
        await merge_context(user_id, clear_pending(), db)
        return None

    coerced = coerce_answer(last_field, msg)
    if coerced is None:
        # Re-ask, but keep state as-is.
        payload = field_to_question_payload(last_field)
        return _finish_onboarding_turn(
            "didn't quite catch that — " + payload["text"].lower(),
            payload,
        )

    # Save the answer to persistent context (also lives in onboarding overlay
    # for the generator).
    update = {last_qid: coerced}
    next_state = {**state, **update}
    next_field = peek_next_question(maxx_id, next_state)
    if next_field is not None:
        # More to ask. Update pending pointer + persist answer.
        new_pending = make_pending(maxx_id, next_field["id"])
        await merge_context(user_id, {**update, "_onboarding_pending": new_pending}, db)
        payload = field_to_question_payload(next_field)
        return _finish_onboarding_turn(
            "got it. " + payload["text"].lower(),
            payload,
        )

    # All required fields collected → clear pending and generate.
    await merge_context(user_id, {**update, **clear_pending()}, db)
    try:
        from services.schedule_runtime import generate_and_persist
        result = await generate_and_persist(
            user_id=user_id,
            maxx_id=maxx_id,
            db=db,
            onboarding={**onboarding, **persistent, **update},
            wake_time=str(state.get("wake_time") or "07:00"),
            sleep_time=str(state.get("sleep_time") or "23:00"),
            subscription_tier=getattr(user, "subscription_tier", None),
        )
        await db.commit()
        n_days = len(result.get("days") or [])
        text = f"perfect. your {doc.display_name.lower()} schedule is live — {n_days} days, day 1 starts now. tap schedule to see today."
        return text, [], None
    except Exception as e:
        logger.exception("onboarding completion → generate failed: %s", e)
        return f"i collected everything but generation hit a snag: {e}. retry?", [], None


def _finish_onboarding_turn(text: str, payload: dict) -> Tuple[str, list[str], Optional[dict]]:
    """Pack a question payload into the chat-response 3-tuple."""
    choices = list(payload.get("choices") or [])
    iw = payload.get("input_widget")
    return text, choices, iw


# --------------------------------------------------------------------------- #
#  Personal-data Q&A short-circuit                                            #
#                                                                             #
#  Questions like "what is my age" / "what gender am i" / "how old am i"      #
#  must NEVER go to doc-RAG (the docs don't know the user). Pull the answer   #
#  from user.onboarding + user_schedule_context.user_facts and reply directly #
#  — or admit we don't know and ask, instead of "i don't see enough in docs". #
# --------------------------------------------------------------------------- #

_PERSONAL_Q_RE = re.compile(
    r"\bwhat(?:'?s| is)?\s+(?:my|i'?m my)\s+(name|age|gender|sex|height|weight|"
    r"body fat|diet|allergies|skin type|hair type|skin concern|wake time|"
    r"sleep time|bedtime)\b"
    r"|\bhow\s+old\s+am\s+i\b"
    r"|\b(?:what|which)\s+gender\s+am\s+i\b"
    r"|\bhow\s+(?:tall|much do i weigh)\s+am\s+i\b"
    r"|\bdo\s+you\s+(?:know|remember)\s+(?:my|what|how)\b",
    re.IGNORECASE,
)


def _looks_like_personal_data_question(text: str) -> bool:
    if not text:
        return False
    return bool(_PERSONAL_Q_RE.search(text))


async def _answer_personal_data_question(
    message: str, onboarding: dict, user_facts: dict
) -> Optional[str]:
    """If the question maps to a known user attribute, answer from onboarding /
    user_facts. If not, return a friendly 'don't have that, mind sharing?' line
    — NEVER the canned doc-RAG refusal."""
    if not message:
        return None
    low = message.lower()

    # Map question keywords → field lookups.
    facts_body = (user_facts or {}).get("body") or {}

    def _say_or_ask(value, attr_label: str, friendly_ask: str) -> str:
        if value not in (None, "", []):
            if isinstance(value, list):
                return f"based on what you've told me, your {attr_label} is {', '.join(str(v) for v in value)}."
            return f"based on what you've told me, your {attr_label} is {value}."
        return f"i don't have that — {friendly_ask}"

    if "age" in low or "old am i" in low:
        v = onboarding.get("age") or facts_body.get("age")
        return _say_or_ask(v, "age", "how old are you?")
    if re.search(r"\b(gender|sex)\b", low):
        v = onboarding.get("gender") or onboarding.get("sex")
        return _say_or_ask(v, "gender", "what's your gender?")
    if "height" in low or re.search(r"how tall am i", low):
        v = onboarding.get("height") or facts_body.get("height")
        return _say_or_ask(v, "height", "how tall are you?")
    if "weight" in low or "weigh" in low:
        v = onboarding.get("weight") or facts_body.get("weight")
        return _say_or_ask(v, "weight", "how much do you weigh?")
    if "body fat" in low:
        v = onboarding.get("body_fat") or facts_body.get("body_fat_pct")
        return _say_or_ask(v, "body fat", "what's your body fat estimate?")
    if "diet" in low:
        v = (user_facts or {}).get("diet") or onboarding.get("diet")
        return _say_or_ask(v, "diet", "what's your diet?")
    if "allergies" in low or re.search(r"\ballergic", low):
        v = (user_facts or {}).get("allergies")
        return _say_or_ask(v, "allergies", "any allergies i should know about?")
    if "skin type" in low:
        v = onboarding.get("skin_type")
        return _say_or_ask(v, "skin type", "what's your skin type — oily, dry, combo, normal?")
    if "hair type" in low:
        v = onboarding.get("hair_type")
        return _say_or_ask(v, "hair type", "what's your hair type — straight, wavy, curly?")
    if "skin concern" in low:
        v = onboarding.get("primary_skin_concern") or onboarding.get("skin_concern")
        return _say_or_ask(v, "main skin concern", "what's your main skin concern?")
    if "wake" in low:
        v = onboarding.get("wake_time")
        return _say_or_ask(v, "wake time", "what time do you wake up?")
    if "sleep" in low or "bedtime" in low:
        v = onboarding.get("sleep_time")
        return _say_or_ask(v, "bedtime", "what time do you go to bed?")
    if "name" in low:
        v = onboarding.get("first_name") or onboarding.get("name")
        return _say_or_ask(v, "name", "what should i call you?")

    return None


_DOC_REFUSAL_PATTERNS = re.compile(
    r"(don'?t see enough in the (current )?docs?"
    r"|don'?t have enough (info|information) in the docs?"
    r"|i don'?t have (info|information|details) (about|on) (this|that|it)"
    r"|not (mentioned|covered|in) the docs?"
    r"|the docs? don'?t (cover|mention|specify))",
    re.IGNORECASE,
)

# Personal-data heuristic — if the user is asking about THEIR own
# schedule / progress / data, web search won't help. Skip the safety net.
_PERSONAL_RE = re.compile(
    r"\b(my|i'?m|i am|i've|i have|me|mine|myself|today's|tomorrow|tonight)\b",
    re.IGNORECASE,
)


def _looks_like_doc_refusal(text: str) -> bool:
    if not text or len(text) < 20:
        return False
    return bool(_DOC_REFUSAL_PATTERNS.search(text))


def _question_is_personal(message: str) -> bool:
    """If the user is asking about their own data, web search won't help."""
    if not message:
        return False
    # Strong signals — schedule operations, completion stats, etc.
    if re.search(r"\b(my schedule|my routine|my plan|today's tasks|what should i do today)\b", message, re.IGNORECASE):
        return True
    return False


def _compress_query_for_search(message: str) -> str:
    """Condense a chat message into a 3-10 word search query."""
    if not message:
        return ""
    # Strip pronouns / question chrome that hurts SEO retrieval.
    text = re.sub(r"\b(i|me|my|mine|myself|you|your|please|could|would|can|should|tell me|do you know|what is|what are|how do i|how do you)\b",
                  " ", message, flags=re.IGNORECASE)
    text = re.sub(r"[?.!,]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Cap length.
    return text[:120]


async def _extract_facts_bg(user_id: str, user_msg: str, assistant_response: str) -> None:
    """Background-safe fact extractor. Opens its own AsyncSession since the
    request session is already closed by the time this fires. Never raises."""
    try:
        from db.sqlalchemy import AsyncSessionLocal
        from services.user_facts_async_extractor import extract_and_merge
        async with AsyncSessionLocal() as bg_session:
            try:
                await extract_and_merge(
                    user_id=user_id,
                    user_message=user_msg,
                    assistant_response=assistant_response,
                    db=bg_session,
                )
            except Exception as e:
                logger.info("bg fact extract failed (non-fatal): %s", e)
    except Exception as e:
        logger.info("bg fact extract setup failed (non-fatal): %s", e)


@router.post("/message", response_model=ChatResponse)
async def send_message(
    data: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession | None = Depends(get_rds_db_optional),
):
    """Send message to Max AI (in-app)"""
    from services import chat_conversations_service as _conv

    user_id = current_user["id"]

    # Per-user serialization. Two concurrent requests for the same user
    # would otherwise race and reply out-of-order. Wait for any in-flight
    # turn to finish before processing this one.
    user_lock = await _get_user_chat_lock(user_id)
    async with user_lock:
        return await _send_message_locked(data, background_tasks, current_user, db, rds_db)


async def _send_message_locked(
    data: "ChatRequest",
    background_tasks: BackgroundTasks,
    current_user: dict,
    db: AsyncSession,
    rds_db: AsyncSession | None,
) -> "ChatResponse":
    from services import chat_conversations_service as _conv

    user_id = current_user["id"]

    # Tier 0 — passive fact extraction. Catches vegetarian/allergic-to/lives-in/
    # weighs-X/has-eczema/etc. and merges into user_schedule_context.user_facts.
    # Pure regex, ~1ms, never blocks or returns a reply — just builds the
    # long-term user profile so every downstream LLM call sees it.
    try:
        from services.user_facts_service import (
            extract_facts_from_message, merge_facts, FACTS_KEY,
        )
        from services.user_context_service import get_context, merge_context
        new_facts = extract_facts_from_message(data.message)
        if new_facts:
            existing_ctx = await get_context(user_id, db)
            merged_facts = merge_facts(existing_ctx.get(FACTS_KEY) or {}, new_facts)
            await merge_context(user_id, {FACTS_KEY: merged_facts}, db)
    except Exception as _e:
        logger.warning("fact extractor failed (non-fatal): %s", _e)

    # Context-change hook (runs FIRST — before the questioner / agent).
    # When the user volunteers a wake/sleep change mid-conversation, we
    # retime every active schedule and reply with a confirmation in one
    # turn. Without this the agent verbally acknowledges but persisted
    # schedules stay on the old times.
    iw: Optional[dict] = None
    ctx_out = await _handle_context_change(
        user_id=user_id,
        message_text=data.message,
        db=db,
    )
    if ctx_out is not None:
        response_text, choices, iw = ctx_out
        try:
            user_uuid = UUID(user_id)
            db.add(ChatHistory(user_id=user_uuid, role="user", content=data.message, channel="app"))
            db.add(ChatHistory(user_id=user_uuid, role="assistant", content=response_text, channel="app"))
            await db.commit()
        except Exception:
            await db.rollback()
        conv_id = data.conversation_id
        if not conv_id:
            conv = await _conv.resolve_active_conversation(
                db, user_id=user_id, conversation_id=None, channel="app",
            )
            conv_id = str(conv.id)
        return ChatResponse(
            response=response_text,
            choices=choices,
            input_widget=iw,
            conversation_id=conv_id,
        )

    # NEW: deterministic onboarding questioner. Owns the conversation when
    # the user is collecting required fields for a doc-driven max schedule.
    # Returns None to fall through to the legacy/agent path.
    driver_out = await _run_onboarding_questioner(
        user_id=user_id,
        message_text=data.message,
        db=db,
    )
    if driver_out is not None:
        response_text, choices, iw = driver_out
        # Persist the user message + assistant reply to ChatHistory so the
        # transcript matches what the user sees (the agent path does this
        # internally; we have to do it explicitly when bypassing).
        try:
            user_uuid = UUID(user_id)
            db.add(ChatHistory(user_id=user_uuid, role="user", content=data.message, channel="app"))
            db.add(ChatHistory(user_id=user_uuid, role="assistant", content=response_text, channel="app"))
            await db.commit()
        except Exception:
            await db.rollback()
    else:
        # Tier 3 — generic schedule-modification fallback. Catches ad-hoc
        # edits the regex detector won't ("cancel gym on tuesdays",
        # "skip everything tomorrow", "move tret to mondays only") by
        # routing to the diff-format LLM adapter.
        mod_out = await _handle_generic_schedule_modification(
            user_id=user_id, message_text=data.message, db=db,
        )
        if mod_out is not None:
            response_text, choices, iw = mod_out
            try:
                user_uuid = UUID(user_id)
                db.add(ChatHistory(user_id=user_uuid, role="user", content=data.message, channel="app"))
                db.add(ChatHistory(user_id=user_uuid, role="assistant", content=response_text, channel="app"))
                await db.commit()
            except Exception:
                await db.rollback()
        else:
            response_text, choices = await process_chat_message(
                user_id=user_id,
                message_text=data.message,
                db=db,
                rds_db=rds_db,
                init_context=data.init_context,
                chat_intent=data.chat_intent,
                attachment_url=data.attachment_url,
                attachment_type=data.attachment_type,
                conversation_id=data.conversation_id,
            )

    conv_id = data.conversation_id
    if not conv_id:
        conv = await _conv.resolve_active_conversation(
            db,
            user_id=user_id,
            conversation_id=None,
            channel="app",
        )
        conv_id = str(conv.id)

    # Background fact extraction. Fires after the response is returned, so
    # zero added latency for the user. Catches any phrasing the regex
    # extractor missed; facts will be visible on the NEXT turn.
    try:
        background_tasks.add_task(
            _extract_facts_bg,
            user_id=user_id,
            user_msg=data.message or "",
            assistant_response=response_text or "",
        )
    except Exception as _e:
        logger.warning("could not schedule bg fact extractor: %s", _e)

    return ChatResponse(
        response=response_text,
        choices=choices,
        input_widget=iw,
        conversation_id=conv_id,
    )


@router.post("/trigger-check-in")
async def trigger_check_in(
    check_in_type: str = "midday",
    missed_today: int = 0,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession | None = Depends(get_rds_db_optional),
):
    """
    Trigger a check-in message immediately (for testing).
    Bypasses time and cooldown checks. Sends an AI-generated check-in to the current user.
    Types: morning, midday, night, missed_task, weekly
    """
    user_id = current_user["id"]
    user_uuid = UUID(user_id)

    msg_text = await coaching_service.generate_check_in_message(
        user_id, db, rds_db, check_in_type, missed_today
    )

    chat_msg = ChatHistory(
        user_id=user_uuid,
        role="assistant",
        content=msg_text,
        channel="app",
        created_at=datetime.utcnow(),
    )
    db.add(chat_msg)
    await db.commit()

    return {"message": msg_text, "check_in_type": check_in_type}


@router.get("/history")
async def get_chat_history(
    limit: int = 50,
    offset: int = 0,
    conversation_id: Optional[str] = None,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Get in-app chat history.

    Without conversation_id: returns the user's most-recent thread (matches
    legacy single-thread mobile behavior).
    With conversation_id: returns that specific thread, or 404 if it doesn't
    belong to the caller.
    """
    from services import chat_conversations_service as _conv

    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    user_id = current_user["id"]
    user_uuid = UUID(user_id)

    # Decide which conversation to read.
    target_conv = None
    if conversation_id:
        target_conv = await _conv.get_conversation(
            db, conversation_id=conversation_id, user_id=user_id
        )
        if target_conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        convs = await _conv.list_conversations(db, user_id=user_id, limit=1)
        target_conv = None if not convs else await _conv.get_conversation(
            db, conversation_id=convs[0]["id"], user_id=user_id
        )

    stmt = (
        select(ChatHistory)
        .where(ChatHistory.user_id == user_uuid)
        .where(or_(ChatHistory.channel == "app", ChatHistory.channel.is_(None)))
    )
    if target_conv is not None:
        stmt = stmt.where(ChatHistory.conversation_id == target_conv.id)
    result = await db.execute(
        stmt.order_by(ChatHistory.created_at.desc())
            .offset(offset)
            .limit(limit)
    )
    rows = list(reversed(result.scalars().all()))

    # If the user has an in-flight doc-driven onboarding (e.g. they
    # answered question 1 of HairMax then closed the app), surface the
    # NEXT question's chips / input_widget alongside the history so the
    # mobile UI can re-render the answer chooser. Without this, the
    # question text shows in the transcript but the chip row underneath
    # disappears on reload — the user has to type or wait for a re-ask.
    pending_question: Optional[dict] = None
    try:
        from services.onboarding_questioner import (
            get_pending,
            peek_next_question,
            field_to_question_payload,
        )
        from services.user_context_service import get_context, merged_user_state
        from services.task_catalog_service import is_loaded, warm_catalog, get_doc

        if not is_loaded():
            await warm_catalog()

        user_obj = await db.get(User, user_uuid)
        onboarding = dict(getattr(user_obj, "onboarding", {}) or {})
        persistent = await get_context(user_id, db)
        state = merged_user_state(onboarding, persistent)
        pending = get_pending(state)
        if pending and get_doc(pending.get("max", "")):
            next_field = peek_next_question(pending["max"], state)
            if next_field is not None:
                payload = field_to_question_payload(next_field)
                pending_question = {
                    "max": pending["max"],
                    "field_id": next_field.get("id"),
                    "text": payload.get("text"),
                    "choices": payload.get("choices") or [],
                    "input_widget": payload.get("input_widget"),
                }
    except Exception as _e:
        logger.warning("history pending-question hydrate failed: %s", _e)
        pending_question = None

    return {
        "conversation_id": str(target_conv.id) if target_conv else None,
        "messages": [
            {"role": r.role, "content": r.content, "created_at": r.created_at}
            for r in rows
        ],
        "pending_question": pending_question,
    }


# -----------------------------------------------------------------------
#  Conversations CRUD — list / create / rename / archive / delete
# -----------------------------------------------------------------------

class ConversationCreateBody(BaseModel):
    title: Optional[str] = None


class ConversationRenameBody(BaseModel):
    title: str


@router.get("/conversations")
async def list_chat_conversations(
    include_archived: bool = False,
    limit: int = 50,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Return this user's chat threads, most recent first."""
    from services import chat_conversations_service as _conv
    items = await _conv.list_conversations(
        db,
        user_id=current_user["id"],
        include_archived=include_archived,
        limit=limit,
    )
    return {"conversations": items}


@router.post("/conversations")
async def create_chat_conversation(
    body: ConversationCreateBody,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new chat thread. Returns the thread for immediate use."""
    from services import chat_conversations_service as _conv
    conv = await _conv.create_conversation(
        db,
        user_id=current_user["id"],
        title=body.title,
        channel="app",
    )
    return {"conversation": _conv.row_to_dict(conv)}


@router.patch("/conversations/{conversation_id}")
async def rename_chat_conversation(
    conversation_id: str,
    body: ConversationRenameBody,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    from services import chat_conversations_service as _conv
    conv = await _conv.rename_conversation(
        db,
        conversation_id=conversation_id,
        user_id=current_user["id"],
        title=body.title,
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": _conv.row_to_dict(conv)}


@router.delete("/conversations/{conversation_id}")
async def delete_chat_conversation(
    conversation_id: str,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete the thread and its messages."""
    from services import chat_conversations_service as _conv
    removed = await _conv.delete_conversation(
        db,
        conversation_id=conversation_id,
        user_id=current_user["id"],
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


def _summarise_schedule(schedule: dict) -> str:
    """Build a short summary of a generated schedule."""
    days = schedule.get("days", [])
    if not days:
        return "schedule created. check your Schedule tab."

    first_day = days[0]
    tasks = first_day.get("tasks", [])
    title = (schedule.get("course_title") or schedule.get("maxx_id") or "schedule").strip()
    lines = [f"your {title} schedule is locked in.", "", "day 1:"]
    for t in tasks[:5]:
        lines.append(f"  {t.get('time', '??:??')} -- {t.get('title', 'Task')}")
    if len(tasks) > 5:
        lines.append(f"  +{len(tasks) - 5} more")
    lines.append(f"\n{len(days)} days planned. check Schedule tab.")
    return "\n".join(lines)
