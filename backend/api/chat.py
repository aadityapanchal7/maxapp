"""
Chat API - Max LLM Chat
Handles AI chat with tool-calling, coaching state, check-in parsing, and memory.
The core logic lives in process_chat_message() so it can be reused by the SMS webhook.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from db import get_db, get_rds_db_optional
from middleware.auth_middleware import require_paid_user
from models.leaderboard import ChatRequest, ChatResponse
from models.sqlalchemy_models import ChatHistory, Scan, User
from services.coaching_service import coaching_service
from services.llm_router import llm_chat
from services.nutrition_service import nutrition_service
from services.storage_service import storage_service
from services.bonemax_chat_prompt import BONEMAX_NEW_SCHEDULE_SYSTEM_PROMPT
from services.maxx_guidelines import SKINMAX_PROTOCOLS, resolve_skin_concern
from services.prompt_loader import PromptKey, resolve_prompt

logger = logging.getLogger(__name__)

# Schedule setup: wake/sleep come from signup / profile only — never re-ask in chat.
_WAKE_SLEEP_NEVER_ASK = (
    "WAKE_TIME & SLEEP_TIME — NEVER ask the user in this flow. Read wake_time and sleep_time from "
    "user_context.onboarding / GLOBAL ONBOARDING (includes schedule_preferences merge). "
    "If either field is missing, pass wake_time=07:00 and sleep_time=23:00 in generate_maxx_schedule without asking."
)


def _coerce_chat_maxx_id(raw: Optional[str]) -> Optional[str]:
    """Normalize init_context / inferred maxx id so HairMax, hair-max, etc. hit the right SYSTEM branch."""
    if not raw:
        return None
    s = re.sub(r"[\s\-_]+", "", str(raw).strip().lower())
    for mid in ("skinmax", "hairmax", "heightmax", "fitmax", "bonemax"):
        if s == mid:
            return mid
    return str(raw).strip().lower()


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


def _fitmax_next_question(profile: dict) -> str:
    missing = _fitmax_missing_fields(profile)
    if not missing:
        return ""
    field = missing[0]
    prompts = {
        "goal": "what's your main goal right now — fat loss, muscle gain, recomp, maintenance, or performance?",
        "experience_level": "what's your training experience level: beginner, intermediate, or advanced?",
        "height_cm": "quick stats check — what's your height (cm or ft/in)?",
        "weight_kg": "what's your current body weight?",
        "age": "how old are you?",
        "biological_sex": "what's your biological sex (male/female)?",
        "equipment": "what do you have available to train with?",
        "days_per_week": "how many days per week can you realistically train?",
        "session_minutes": "what session length can you commit to most days (minutes)?",
        "daily_activity_level": "outside the gym, what's your daily activity like: sedentary, lightly active, moderately active, or very active?",
        "dietary_restrictions": "any dietary restrictions i should account for?",
    }
    return prompts[field]


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


def _hairmax_next_question(profile: dict) -> str:
    missing = _hairmax_missing_fields(profile)
    if not missing:
        return ""
    prompts = {
        "hair_type": "what's your hair type — straight, wavy, curly, or coily?",
        "scalp_state": "how's your scalp: normal, dry/flaky, oily/greasy, or itchy?",
        "daily_styling": "do you use hair products or styling most days? yes or no.",
        "thinning": "noticing any thinning or receding hairline? yes or no.",
    }
    return prompts[missing[0]]


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

    if any(k in s for k in ["dumbbell", "barbell", "bench", "machine", "gym", "cable", "bands", "bodyweight", "home"]):
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


def _fitmax_activity_multiplier(level: str) -> float:
    return {
        "sedentary": 1.2,
        "lightly_active": 1.375,
        "moderately_active": 1.55,
        "very_active": 1.725,
    }.get(level or "moderately_active", 1.55)


def _fitmax_build_plan(profile: dict) -> dict:
    weight_kg = float(profile.get("weight_kg") or 75)
    height_cm = float(profile.get("height_cm") or 175)
    age = int(profile.get("age") or 25)
    sex = profile.get("biological_sex", "male")
    goal = profile.get("goal", "recomp")
    activity = profile.get("daily_activity_level", "moderately_active")
    days = int(profile.get("days_per_week") or 4)

    if sex == "female":
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161
    else:
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5

    tdee = int(round(bmr * _fitmax_activity_multiplier(activity)))
    delta = 0
    goal_label = "Recomp · Maintenance calories"
    if goal == "fat_loss":
        delta = -500
        goal_label = "Fat Loss · 500 cal deficit"
    elif goal == "muscle_gain":
        delta = 300
        goal_label = "Muscle Gain · Lean surplus"
    elif goal == "maintenance":
        delta = 0
        goal_label = "Maintenance · Bodyweight stable"
    elif goal == "performance":
        delta = 200
        goal_label = "Performance · Small surplus"

    calories = max(1400, tdee + delta)
    protein = int(round(weight_kg * 2.2 * (1.0 if goal in ("fat_loss", "muscle_gain") else 0.9)))
    fat = int(round((calories * 0.27) / 9))
    carbs = int(round((calories - (protein * 4 + fat * 9)) / 4))

    if days >= 5:
        split = "Push/Pull/Legs"
    elif days == 4:
        split = "Upper/Lower"
    elif days == 3:
        split = "Full Body 3x"
    else:
        split = "Full Body 2x"

    return {
        "bmr": int(round(bmr)),
        "tdee": tdee,
        "calories": int(round(calories)),
        "protein_g": protein,
        "carbs_g": carbs,
        "fat_g": fat,
        "goal_label": goal_label,
        "split": split,
        "days_per_week": days,
    }


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
        opt.append(f"screen/phone load already saved: {sh} — do NOT ask again")
    hwt = onboarding.get("heightmax_workout_time") or onboarding.get("preferred_workout_time")
    if hwt:
        opt.append(f"preferred workout time already saved: {hwt} — do NOT ask again")
    gp = onboarding.get("growth_plate_status") or onboarding.get("heightmax_growth_plate_status")
    if gp:
        opt.append(f"growth_plate status already saved: {gp} — do NOT ask again")
    hg = onboarding.get("heightmax_goal") or onboarding.get("height_goal")
    if hg:
        opt.append(f"height goal already saved: {hg} — do NOT ask again")
    sq = onboarding.get("heightmax_sleep_quality") or onboarding.get("sleep_quality")
    if sq:
        opt.append(f"sleep quality already saved: {sq} — do NOT ask again")
    if not bits and not opt:
        return ""
    lines = [
        "KNOWN FROM GLOBAL ONBOARDING (user_context.onboarding — signup / profile; "
        "treat as source of truth; DO NOT re-ask age, gender, height, wake, or sleep unless user asks to change): "
        + (", ".join(bits) if bits else "(no core demographics in JSON — ask only what's missing)")
    ]
    if opt:
        lines.append("ALSO ALREADY ON PROFILE (do NOT re-ask):")
        lines.extend(f"- {x}" for x in opt)
    return "\n".join(lines) + "\n\n"


def _infer_skin_concern_id_from_onboarding(ob: dict) -> Optional[str]:
    """Map questionnaire + skin_type to a SkinMax protocol id (acne, pigmentation, ...)."""
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
        lines.append(f"- workout frequency already in onboarding: {wf} — pass to generate_maxx_schedule; do NOT ask again.")
    for label, key in (
        ("TMJ / jaw history", "bonemax_tmj_history"),
        ("mastic gum regularly", "bonemax_mastic_gum_regular"),
        ("heavy screen time", "bonemax_heavy_screen_time"),
    ):
        v = ob.get(key)
        if v is None or str(v).strip() == "":
            continue
        if _yes_no_answered(v):
            lines.append(f"- {label} already in onboarding: {v} — use in tool; do NOT ask again.")
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
        lines.append(f"- {label}: {v} — use in generate_maxx_schedule; do NOT ask again.")
    hcl = str(ob.get("hair_current_loss") or "").strip().lower()
    if hcl and not ob.get("thinning") and not ob.get("hair_thinning"):
        if any(w in hcl for w in ("yes", "yeah", "yep", "reced", "thin", "losing", "balding", "some")):
            lines.append(
                "- hair questionnaire (hair_current_loss) suggests thinning — treat thinning=yes in tool unless user corrects; do NOT ask again unless unclear."
            )
        elif any(w in hcl for w in ("no", "nope", "not ", "none", "minimal")):
            lines.append(
                "- hair questionnaire suggests no major loss — treat thinning=no in tool unless user corrects."
            )
    if not lines:
        return ""
    return (
        "ALREADY KNOWN FROM ONBOARDING (do NOT re-ask):\n"
        + "\n".join(lines)
        + "\n\n"
    )


def _fitmax_seed_profile_from_onboarding(profile: dict, ob: dict) -> dict:
    """Pre-fill FitMax chat profile from global / FitMax questionnaire answers."""
    out = dict(profile or {})
    ob = ob or {}

    def take(dst: str, val, only_if_empty: bool = True) -> None:
        if val is None or val == "" or val == []:
            return
        if only_if_empty and out.get(dst) not in (None, "", []):
            return
        out[dst] = val

    fpg = str(ob.get("fitmax_primary_goal") or "").lower()
    if fpg:
        if any(k in fpg for k in ("fat", "cut", "lose weight", "shred")):
            take("goal", "fat_loss")
        elif any(k in fpg for k in ("muscle", "bulk", "gain", "hypertrophy", "mass")):
            take("goal", "muscle_gain")
        elif "recomp" in fpg:
            take("goal", "recomp")
        elif any(k in fpg for k in ("maintain", "maintenance")):
            take("goal", "maintenance")
        elif any(k in fpg for k in ("performance", "strength", "athletic")):
            take("goal", "performance")

    exp = ob.get("fitmax_training_experience") or ob.get("experience_level")
    if exp:
        e = str(exp).lower()
        if "beginner" in e:
            take("experience_level", "beginner")
        elif "intermediate" in e:
            take("experience_level", "intermediate")
        elif "advanced" in e:
            take("experience_level", "advanced")

    h = ob.get("height")
    if h is not None and str(h).strip():
        try:
            take("height_cm", float(h))
        except (TypeError, ValueError):
            pass
    w = ob.get("weight")
    if w is not None and str(w).strip():
        try:
            take("weight_kg", float(w))
        except (TypeError, ValueError):
            pass
    age_v = _safe_int_age(ob.get("age"))
    if age_v is not None:
        take("age", age_v)

    g = str(ob.get("gender") or ob.get("sex") or "").lower()
    if g:
        if any(x in g for x in ("female", "woman", "girl")):
            take("biological_sex", "female")
        elif any(x in g for x in ("male", "man", "boy")):
            take("biological_sex", "male")

    feq = ob.get("fitmax_equipment")
    if feq:
        take("equipment", ", ".join(feq) if isinstance(feq, list) else str(feq))
    elif ob.get("equipment"):
        eq = ob.get("equipment")
        take("equipment", ", ".join(eq) if isinstance(eq, list) else str(eq))

    d = ob.get("fitmax_workout_days_per_week")
    if d is not None:
        try:
            n = int(float(str(d).strip()))
            if 1 <= n <= 7:
                take("days_per_week", n)
        except (TypeError, ValueError):
            pass

    al = str(ob.get("activity_level") or "").lower()
    if al:
        if any(k in al for k in ("sedentary", "desk")):
            take("daily_activity_level", "sedentary")
        elif any(k in al for k in ("light", "lightly")):
            take("daily_activity_level", "lightly_active")
        elif any(k in al for k in ("moderate", "medium")):
            take("daily_activity_level", "moderately_active")
        elif any(k in al for k in ("very", "high", "athlete", "extreme")):
            take("daily_activity_level", "very_active")

    return out


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
    """Age + gender + height present (typical app onboarding) — no chat questions needed."""
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
    True for education / definition / why-how questions — not schedule change commands.
    Used to skip schedule tools when the model mis-fires.
    """
    if not text or len(text.strip()) < 6:
        return False
    t = text.lower().strip()
    # Schedule-change phrases that can co-occur with questions — exclude
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


def _chat_history_channel_clause(channel: str):
    """Filter chat_history rows: app UI only sees 'app' (and legacy NULL); SMS uses its own thread."""
    if channel == "sms":
        return ChatHistory.channel == "sms"
    return or_(ChatHistory.channel == "app", ChatHistory.channel.is_(None))


def _persist_chat_history(channel: str) -> bool:
    """SMS conversations are not stored in chat_history (SMS-only surface)."""
    return channel != "sms"


async def process_chat_message(
    user_id: str,
    message_text: str,
    db: AsyncSession,
    rds_db: Optional[AsyncSession] = None,
    init_context: Optional[str] = None,
    attachment_url: Optional[str] = None,
    attachment_type: Optional[str] = None,
    channel: str = "app",
) -> str:
    """
    Core chat logic shared by the HTTP endpoint and the SMS webhook.
    Persists app turns to ChatHistory (channel=app). SMS turns are not persisted.
    In-app GET /history shows app (and legacy NULL channel) only.
    """
    from services.schedule_service import schedule_service, ScheduleLimitError
    user_uuid = UUID(user_id)

    fitmax_schedule_active = None
    hairmax_schedule_active = None

    # SMS is not persisted; use in-app thread as read-only context for the model.
    history_channel_for_load = "app" if channel == "sms" else channel
    history_result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == user_uuid)
        .where(_chat_history_channel_clause(history_channel_for_load))
        .order_by(ChatHistory.created_at.desc())
        .limit(50)
    )
    history_rows = list(reversed(history_result.scalars().all()))
    history = [
        {"role": h.role, "content": h.content, "created_at": h.created_at}
        for h in history_rows
    ]
    
    coaching_context = await coaching_service.build_full_context(user_id, db, rds_db)
    active_schedule = await schedule_service.get_current_schedule(user_id, db=db)
    user = await db.get(User, user_uuid)
    onboarding = _merge_onboarding_with_schedule_prefs(user)
    if user:
        profile = dict((user.profile or {}) or {})
        if _expire_stale_chat_pending(profile):
            user.profile = profile
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = dict((user.profile or {}) or {})
    else:
        profile = {}

    if user:
        try:
            fitmax_schedule_active = await schedule_service.get_maxx_schedule(user_id, "fitmax", db=db)
        except Exception:
            fitmax_schedule_active = None
        try:
            hairmax_schedule_active = await schedule_service.get_maxx_schedule(user_id, "hairmax", db=db)
        except Exception:
            hairmax_schedule_active = None
        if hairmax_schedule_active and profile.get("hairmax_chat_setup"):
            prof = dict(profile)
            prof.pop("hairmax_chat_setup", None)
            prof.pop("hairmax_chat_setup_at", None)
            user.profile = prof
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = dict((user.profile or {}) or {})
        elif profile.get("hairmax_chat_setup") and _hairmax_setup_stale(profile):
            prof = dict(profile)
            prof.pop("hairmax_chat_setup", None)
            prof.pop("hairmax_chat_setup_at", None)
            user.profile = prof
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = dict((user.profile or {}) or {})
        if fitmax_schedule_active and profile.get("fitmax_chat_setup"):
            prof = dict(profile)
            prof.pop("fitmax_chat_setup", None)
            prof.pop("fitmax_chat_setup_at", None)
            user.profile = prof
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = dict((user.profile or {}) or {})
        elif profile.get("fitmax_chat_setup") and _fitmax_setup_stale(profile):
            prof = dict(profile)
            prof.pop("fitmax_chat_setup", None)
            prof.pop("fitmax_chat_setup_at", None)
            user.profile = prof
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = dict((user.profile or {}) or {})

    user_context = {
        "coaching_context": coaching_context,
        "active_schedule": active_schedule,
        "onboarding": onboarding,
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
        return response_text

    # --- Init context / maxx schedule onboarding ---
    message = message_text
    maxx_id = _coerce_chat_maxx_id(init_context)
    if not maxx_id and message:
        msg_lower = message.lower()
        if "skinmax" in msg_lower or "skin max" in msg_lower:
            maxx_id = "skinmax"
        elif (
            "heightmax" in msg_lower
            or bool(re.search(r"\bheight\s+maxx?\b", msg_lower))
            or bool(re.search(r"\bonboard\b.*\bheight\b|\bheight\b.*\bonboard\b", msg_lower))
        ):
            maxx_id = "heightmax"
        elif "hairmax" in msg_lower or "hair max" in msg_lower:
            maxx_id = "hairmax"
        elif "fitmax" in msg_lower or "fit max" in msg_lower:
            maxx_id = "fitmax"
        elif "bonemax" in msg_lower or "bone max" in msg_lower or "bone maxx" in msg_lower:
            maxx_id = "bonemax"
    if maxx_id:
        maxx_id = _coerce_chat_maxx_id(maxx_id) or maxx_id

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

    if maxx_id == "fitmax" and user and not fitmax_schedule_active:
        prof = dict(profile or {})
        if not prof.get("fitmax_chat_setup"):
            prof["fitmax_chat_setup"] = True
            prof["fitmax_chat_setup_at"] = datetime.now(timezone.utc).isoformat()
            user.profile = prof
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = dict((user.profile or {}) or {})

    if maxx_id == "hairmax" and user and not hairmax_schedule_active:
        prof = dict(profile or {})
        if not prof.get("hairmax_chat_setup"):
            prof["hairmax_chat_setup"] = True
            prof["hairmax_chat_setup_at"] = datetime.now(timezone.utc).isoformat()
            user.profile = prof
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()
            profile = dict((user.profile or {}) or {})

    fitmax_pending = bool(user and str(profile.get("chat_pending_module") or "").lower() == "fitmax")
    fitmax_chat_setup = bool(profile.get("fitmax_chat_setup"))
    run_fitmax_onboarding = bool(
        user
        and not fitmax_schedule_active
        and (
            maxx_id == "fitmax"
            or fitmax_pending
            or (
                fitmax_chat_setup
                and not _fitmax_setup_stale(profile)
                and (channel == "sms" or _assistant_last_turn_is_fitmax_onboarding(history))
            )
        )
    )

    hairmax_chat_setup = bool(profile.get("hairmax_chat_setup"))
    run_hairmax_onboarding = bool(
        user
        and not hairmax_schedule_active
        and (
            maxx_id == "hairmax"
            or (
                hairmax_chat_setup
                and not _hairmax_setup_stale(profile)
                and _assistant_last_turn_is_hairmax_onboarding(history)
            )
        )
    )

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
            if nxt == "days_per_week" and "days_per_week" not in updates:
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
                    response_text = "hey, welcome to fitmax. before we build your plan, i need to know a bit about you — this takes about 3 minutes and everything we create depends on it. what's your main goal right now? losing fat, building muscle, recomp, maintain, or performance?"
                else:
                    response_text = _fitmax_next_question(fitmax_profile)

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
                return response_text

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
                    schedule = await schedule_service.generate_maxx_schedule(
                        user_id=user_id,
                        maxx_id="fitmax",
                        db=db,
                        rds_db=rds_db if rds_db else None,
                        wake_time="07:00",
                        sleep_time="23:00",
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
                        f"your fitmax profile is saved, but you already have 2 active modules ({names}). "
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
                return response_text

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
            return response_text

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
                response_text = f"your hairmax schedule is locked in.\n\n{schedule_summary}"
            except ScheduleLimitError as e:
                names = ", ".join(e.active_labels)
                response_text = (
                    f"your hairmax profile is saved, but you already have 2 active modules ({names}). "
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
            return response_text

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
            return response_text

    if maxx_id:
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
            and _coerce_chat_maxx_id(init_context) == "heightmax"
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
                    "your heightmax schedule is locked in. open the **Schedule** tab for reminders.\n\n"
                    f"{schedule_summary}"
                )
            except ScheduleLimitError as e:
                names = ", ".join(e.active_labels)
                response_text = (
                    f"you already have 2 active modules ({names}). "
                    "stop one of them first, then come back to start heightmax."
                )
            except Exception as gen_err:
                logger.exception("HeightMax fast-path schedule generation failed: %s", gen_err)
                response_text = "had trouble building your heightmax schedule — try again in a sec."
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
            return response_text

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

CRITICAL — FORBIDDEN FOR HEIGHTMAX
- NEVER ask "outside today" or "you gonna be outside today" or "will you be outside" — that is ONLY for SkinMax. HeightMax does NOT use outside_today. If you ask this, you have failed.

MAIN RULES FOR HEIGHTMAX
- do NOT ask "what is your main concern?" or any generic concern questions.
- height is already the focus. don't ask what area they want to work on.
- GLOBAL ONBOARDING: age, gender, height, wake, and sleep are usually already in user_context.onboarding from app signup. NEVER ask for any field that appears in KNOWN FROM GLOBAL ONBOARDING or ALSO ALREADY ON PROFILE above.
- {_WAKE_SLEEP_NEVER_ASK}
- your job is to grab any missing demographic info (only if not in onboarding), then call generate_maxx_schedule once. the backend builds their full HeightMax schedule in one shot (all standard tracks on). do NOT tell them to tap any in-app button, toggle, or "choose height schedule parts" — users on SMS/text have no such UI and it causes confusion. after the tool runs, tell them the schedule is locked in and to open the Schedule tab in the app for pings.

WHAT YOU'RE ALLOWED TO ASK FOR (ONLY IF MISSING FROM user_context.onboarding / not in KNOWN above)
- age — ONLY if not already known
- sex / gender — ONLY if not already known (field may be "gender")
- current height — ONLY if not already known
- (never wake/sleep — see rule above; never re-ask optional heightmax fields already on profile)

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

   the backend then creates the full schedule — same as other maxx modules.

4) after generate_maxx_schedule returns, your reply should be short: confirm heightmax is locked in and they should open the **Schedule** tab for reminders. optional one line on what HeightMax focuses on (sleep, posture/decompression, sprints, nutrition habits) if they seem unsure. never mention toggles, "below", or buttons.

STYLE
- same tone as skinmax/fitmax: friendly, casual, not overly motivational.
- stay focused on heightmax in this flow. don't switch topics to skin, hair, or gym unless a different module is explicitly opened.
- keep responses concise. no long lectures, no custom step-by-step routines you invent yourself.]\n\n{message}"""
        elif maxx_id == "hairmax":
            _hair_known = _hairmax_onboarding_known_block(onboarding)
            message = f"""[SYSTEM: you are running the HAIRMAX schedule setup.

{_hair_known}the user just opened hairmax to start a new schedule. follow the same tone and style as other maxx modules: short, casual, direct, focused on getting their schedule locked in.

CRITICAL — EVERY TURN IN THIS THREAD (until generate_maxx_schedule succeeds):
- you are ONLY in hairmax. NEVER ask skin concern, SPF, UV, "skinmax", or "focus area for skin".
- NEVER ask "outside today", "going outside", sun, or sunscreen — those are SKINMAX-only. asking them here is a failure.

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
- (never ask wake_time or sleep_time — pass from onboarding or 07:00 / 23:00 in the tool)

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
2) check the ALREADY KNOWN block above plus user_context/onboarding. only ask what's missing. STRICT ORDER — do not skip ahead:
   - ask in order: hair type → scalp → daily styling → thinning (skip any line already listed as known).
   ask one question at a time. you MUST have all four hair lines (type, scalp, daily styling, thinning) before calling the tool unless they were pre-filled.
3) call generate_maxx_schedule exactly once once hair fields are complete. pass wake_time and sleep_time from onboarding only, or 07:00 and 23:00 if missing — never ask the user for them. the backend will reject the call if hair fields are missing — pass them explicitly:
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

style:
- same as other maxx modules: friendly, casual, short.
- one question at a time.
- no long lectures, no generic concern questions.

your first response in this hairmax start flow should:
- briefly acknowledge they're starting hairmax, and
- immediately ask the first missing hair-related question (hair type / scalp / products / thinning). if all hair basics are known, call generate_maxx_schedule (wake/sleep from onboarding or defaults) — never ask wake/sleep.]\n\n{message}"""
        elif maxx_id == "skinmax":
            inferred_sc = _infer_skin_concern_id_from_onboarding(onboarding)
            wt_ok = _normalize_clock_hhmm(onboarding.get("wake_time"))
            st_ok = _normalize_clock_hhmm(onboarding.get("sleep_time"))
            known_lines: list[str] = [_WAKE_SLEEP_NEVER_ASK]
            if inferred_sc:
                known_lines.append(
                    f'SKIN CONCERN already inferred from app onboarding — use skin_concern="{inferred_sc}" in generate_maxx_schedule. '
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
            message = f"""[SYSTEM: SkinMax schedule setup — user started the module schedule from the app.

{known_block}

RULES:
- GLOBAL ONBOARDING + USER CONTEXT are source of truth.
- Before generate_maxx_schedule you need: skin_concern, wake_time, sleep_time (from onboarding or 07:00/23:00 defaults — NEVER ask), and outside_today (boolean).
- ONE question per message. Order: (1) skin concern ONLY if not pre-filled above, (2) then ONLY "planning to be outside much today?" for outside_today.
- If skin concern is already pre-filled above, greet briefly and your FIRST question must be ONLY about outside today.
- For wake/sleep in the tool: use values from onboarding if present; otherwise 07:00 and 23:00.

ANTI-REDUNDANCY (CRITICAL):
- NEVER ask the skin concern / focus question again if it appears anywhere in THIS chat thread (user already said e.g. "acne") OR if pre-filled above OR inferable from onboarding.
- If the user already answered concern + outside today in this thread, call generate_maxx_schedule immediately — do NOT rephrase the same questions.
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
            message = f"""[SYSTEM: FitMax — training & nutrition schedule. The user is starting or continuing FitMax.

CRITICAL — FORBIDDEN FOR FITMAX (not SkinMax)
- NEVER ask "outside today", "going outside", UV, sunscreen, or SPF. FitMax always uses outside_today=false in generate_maxx_schedule.
- NEVER ask wake_time or sleep_time to complete setup — use user_context.onboarding or pass wake_time="{_wt}" and sleep_time="{_st}" in the tool. Only acknowledge if the user volunteers a correction.

ANTI-REDUNDANCY
- Do NOT repeat the same question if the user already answered in this thread.
- Do NOT use the SkinMax flow (skin concern + outside today). FitMax is not a skin module.

WHAT TO DO
- If you have enough context, call generate_maxx_schedule ONCE with maxx_id="fitmax", outside_today=false, skin_concern=a short goal/phase label from the conversation, wake_time="{_wt}", sleep_time="{_st}".
- Otherwise ONE short follow-up at a time — never wake, sleep, or outside.

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
                message = f"""[SYSTEM: User wants to start their {maxx_id} schedule. CRITICAL — follow this EXACT order:
{_WAKE_SLEEP_NEVER_ASK}
1. Greet briefly and explain what the schedule does.
2. Your FIRST question MUST be: "{concern_question}" Options: {concerns_str}. Wait for their answer.
3. After they pick a concern, ask: "Are you planning to be outside much today?" — wait for answer (needed for UV / SPF logic where applicable).
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
    
    # --- LLM call ---
    result = await llm_chat(message, history, user_context, image_data)
    response_text = result.get("text", "")
    tool_calls = result.get("tool_calls", [])
    
    # --- Process tool calls ---
    modify_schedule_ran = False
    for tool in tool_calls:
        if tool["name"] == "modify_schedule" and active_schedule:
            try:
                if _looks_like_informational_question(message_text):
                    logger.info(
                        "Skipping modify_schedule — informational question: %s",
                        message_text[:80],
                    )
                    continue
                feedback = tool["args"].get("feedback")
                if feedback:
                    modify_schedule_ran = True
                    adapt_result = await schedule_service.adapt_schedule(
                        user_id=user_id,
                        schedule_id=active_schedule["id"],
                        db=db,
                        feedback=feedback,
                    )
                    summary = adapt_result.get("changes_summary", "").strip()
                    # Summary is always set (LLM or deterministic fallback)
                    if summary:
                        response_text = (response_text + "\n\n" + summary).strip() if response_text else summary
            except Exception as e:
                logger.exception("Schedule adaptation failed: %s", e)

        elif tool["name"] == "generate_maxx_schedule":
            try:
                args = tool["args"]
                req_maxx = str(args.get("maxx_id", "skinmax"))
                wf = None
                tmj_raw = None
                gum_raw = None
                scr_raw = None
                if req_maxx == "skinmax":
                    sc_arg = args.get("skin_concern")
                    sc_str = str(sc_arg).strip().lower() if sc_arg is not None and str(sc_arg).strip() else ""
                    if sc_str in SKINMAX_PROTOCOLS:
                        skin_concern = sc_str
                    else:
                        skin_concern = _infer_skin_concern_id_from_onboarding(onboarding) or resolve_skin_concern(
                            str(onboarding.get("skin_type") or "").strip() or None, None
                        )
                else:
                    skin_concern = args.get("skin_concern") or onboarding.get("skin_type")
                # For HeightMax, allow AI to pass age/sex/height from conversation
                age_raw = args.get("age")
                age = _safe_int_age(age_raw)
                sex = args.get("sex") or args.get("gender")
                height = args.get("height")
                # HeightMax REQUIRES age, sex, height — reject if missing
                if req_maxx == "heightmax":
                    has_age = age is not None or _safe_int_age(onboarding.get("age")) is not None
                    ob_gender = str(onboarding.get("gender") or onboarding.get("sex") or "").strip()
                    has_sex = bool((sex and str(sex).strip()) or ob_gender)
                    ob_h = onboarding.get("height")
                    has_height = bool(
                        (height is not None and str(height).strip())
                        or (ob_h is not None and str(ob_h).strip())
                    )
                    if not has_age or not has_sex or not has_height:
                        if not has_age:
                            response_text = "hold up — i need your age, sex, and height before i can build your schedule. how old are you?"
                        elif not has_sex:
                            response_text = "got it. what's your sex or gender?"
                        else:
                            response_text = "almost there. what's your current height? any format works."
                        continue
                # HairMax REQUIRES hair type, scalp, daily styling, thinning — reject if missing
                if req_maxx == "hairmax":
                    hair_type = args.get("hair_type") or onboarding.get("hair_type")
                    scalp_state = args.get("scalp_state") or onboarding.get("scalp_state")
                    daily_styling = args.get("daily_styling")
                    if daily_styling is None:
                        daily_styling = onboarding.get("daily_styling")
                    thinning = args.get("thinning") or args.get("hair_thinning")
                    if thinning is None:
                        thinning = onboarding.get("hair_thinning") or onboarding.get("thinning")
                    if not _yes_no_answered(thinning):
                        hcl = str(onboarding.get("hair_current_loss") or "").lower()
                        if any(
                            w in hcl
                            for w in ("yes", "yeah", "yep", "reced", "thin", "losing", "balding", "some")
                        ):
                            thinning = "yes"
                        elif any(
                            w in hcl for w in ("no", "nope", "none", "not really", "minimal", "little")
                        ):
                            thinning = "no"
                    has_ht = bool(str(hair_type or "").strip())
                    has_ss = bool(str(scalp_state or "").strip())
                    has_ds = _yes_no_answered(daily_styling)
                    has_th = _yes_no_answered(thinning)
                    if not has_ht or not has_ss or not has_ds or not has_th:
                        if not has_ht:
                            response_text = "need a bit more first — is your hair straight, wavy, curly, or coily?"
                        elif not has_ss:
                            response_text = "how's your scalp: normal, dry/flaky, oily/greasy, or itchy?"
                        elif not has_ds:
                            response_text = "do you use hair products or styling most days? yes or no."
                        else:
                            response_text = "you notice thinning or a receding hairline? yes or no."
                        continue
                if req_maxx == "bonemax":
                    wf = (args.get("workout_frequency") or onboarding.get("bonemax_workout_frequency") or "").strip()
                    tmj_raw = args.get("tmj_history")
                    if tmj_raw is None:
                        tmj_raw = onboarding.get("bonemax_tmj_history")
                    gum_raw = args.get("mastic_gum_regular")
                    if gum_raw is None:
                        gum_raw = onboarding.get("bonemax_mastic_gum_regular")
                    scr_raw = args.get("heavy_screen_time")
                    if scr_raw is None:
                        scr_raw = onboarding.get("bonemax_heavy_screen_time")
                    has_wf = bool(wf)
                    has_tmj = _yes_no_answered(tmj_raw)
                    has_gum = _yes_no_answered(gum_raw)
                    has_scr = _yes_no_answered(scr_raw)
                    if not has_wf or not has_tmj or not has_gum or not has_scr:
                        if not has_wf:
                            response_text = (
                                "quick one — how many days per week do you usually work out? "
                                "say 0, 1-2, 3-4, or 5+."
                            )
                        elif not has_tmj:
                            response_text = "ever had tmj, jaw pain, or clicking? yes or no."
                        elif not has_gum:
                            response_text = "you already chewing mastic or hard gum regularly? yes or no."
                        else:
                            response_text = "you on a computer or phone many hours most days? yes or no."
                        continue
                # Prefer tool args, then global onboarding (any prior maxx / app), then defaults
                aw = args.get("wake_time")
                asl = args.get("sleep_time")
                final_wake = _normalize_clock_hhmm(str(aw).strip()) if aw is not None and str(aw).strip() else None
                final_sleep = _normalize_clock_hhmm(str(asl).strip()) if asl is not None and str(asl).strip() else None
                if not final_wake:
                    final_wake = _normalize_clock_hhmm(onboarding.get("wake_time")) or "07:00"
                if not final_sleep:
                    final_sleep = _normalize_clock_hhmm(onboarding.get("sleep_time")) or "23:00"

                if req_maxx == "heightmax":
                    ra = _safe_int_age(age) or _safe_int_age(onboarding.get("age"))
                    rs = (str(sex).strip() if sex else "") or (str(onboarding.get("gender") or "").strip())
                    rh = (str(height).strip() if height is not None and str(height).strip() else "") or (
                        str(onboarding.get("height") or "").strip()
                    )
                    try:
                        await _persist_heightmax_onboarding_from_chat(
                            user,
                            db,
                            resolved_age=ra,
                            resolved_sex=rs,
                            resolved_height=rh,
                            final_wake=str(final_wake),
                            final_sleep=str(final_sleep),
                        )
                    except Exception as persist_err:
                        logger.warning("heightmax onboarding persist failed: %s", persist_err)
                    onboarding = _merge_onboarding_with_schedule_prefs(user)
                    try:
                        schedule = await schedule_service.generate_maxx_schedule(
                            user_id=user_id,
                            maxx_id="heightmax",
                            db=db,
                            rds_db=rds_db if rds_db else None,
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
                        onboarding = _merge_onboarding_with_schedule_prefs(user)
                        schedule_summary = _summarise_schedule(schedule)
                        if not response_text.strip():
                            response_text = schedule_summary
                        else:
                            response_text = f"{response_text.strip()}\n\n{schedule_summary}"
                    except ScheduleLimitError as e:
                        names = ", ".join(e.active_labels)
                        response_text = (
                            f"you already have 2 active modules ({names}). "
                            "you gotta stop one before starting a new one — "
                            "tell me which module to stop in the app, or open the app to stop a module there."
                        )
                    except Exception as gen_err:
                        logger.exception("HeightMax schedule generation failed: %s", gen_err)
                        response_text = (
                            (response_text.strip() + "\n\n") if response_text.strip() else ""
                        ) + "had trouble building your heightmax schedule — try again in a sec or set it up in the app."
                    continue

                schedule = await schedule_service.generate_maxx_schedule(
                    user_id=user_id,
                    maxx_id=req_maxx,
                    db=db,
                    rds_db=rds_db if rds_db else None,
                    wake_time=str(final_wake),
                    sleep_time=str(final_sleep),
                    skin_concern=skin_concern,
                    outside_today=False
                    if req_maxx == "fitmax"
                    else bool(args.get("outside_today", False)),
                    override_age=age,
                    override_sex=sex,
                    override_height=str(height) if height is not None else None,
                    override_hair_type=(args.get("hair_type") or onboarding.get("hair_type") or "").strip() or None,
                    override_scalp_state=(args.get("scalp_state") or onboarding.get("scalp_state") or "").strip() or None,
                    override_daily_styling=_normalize_hair_yes_no(
                        args.get("daily_styling") if args.get("daily_styling") is not None else onboarding.get("daily_styling")
                    ),
                    override_thinning=_normalize_hair_yes_no(
                        args.get("thinning") or args.get("hair_thinning") or onboarding.get("hair_thinning") or onboarding.get("thinning")
                    ),
                    override_workout_frequency=wf,
                    override_tmj_history=_normalize_hair_yes_no(tmj_raw),
                    override_mastic_gum_regular=_normalize_hair_yes_no(gum_raw),
                    override_heavy_screen_time=_normalize_hair_yes_no(scr_raw),
                )
                await _persist_user_wake_sleep(user, db, str(final_wake), str(final_sleep))
                onboarding = _merge_onboarding_with_schedule_prefs(user)
                schedule_summary = _summarise_schedule(schedule)
                if not response_text.strip():
                    response_text = schedule_summary
                else:
                    response_text += f"\n\n{schedule_summary}"
            except ScheduleLimitError as e:
                names = ", ".join(e.active_labels)
                response_text = (
                    f"you already have 2 active modules ({names}). "
                    "you gotta stop one before starting a new one — "
                    "tell me which module to stop, or hit the stop button on the module page in the app."
                )
            except Exception as e:
                print(f"Maxx schedule generation failed: {e}")
                response_text += "\n\nhad trouble generating your schedule. try again in a sec."

        elif tool["name"] == "stop_schedule":
            if channel == "sms":
                response_text = (
                    "stopping or changing modules can only be done in the app. "
                    "open the app and go to the module you want to stop, or ask me there."
                )
            else:
                try:
                    args = tool["args"]
                    target_maxx = str(args.get("maxx_id", "")).strip().lower()
                    if not target_maxx:
                        response_text = "which module do you want to stop? (e.g. skinmax, hairmax, fitmax, bonemax, heightmax)"
                    else:
                        result = await schedule_service.deactivate_schedule_by_maxx(user_id, target_maxx, db)
                        if result:
                            response_text = f"done — {target_maxx} has been stopped. you can restart it anytime from the module page."
                        else:
                            response_text = f"you don't have an active {target_maxx} schedule right now."
                except Exception as e:
                    logger.exception("stop_schedule failed: %s", e)
                    response_text = "couldn't stop that module. try again or use the stop button on the module page."

        elif tool["name"] == "update_schedule_context":
            try:
                args = tool["args"]
                key, value = str(args.get("key", "")), str(args.get("value", ""))
                lk = key.lower().replace("-", "_")
                if lk in ("wake_time", "sleep_time", "preferred_wake_time", "preferred_sleep_time"):
                    wk = None
                    sk = None
                    if lk in ("wake_time", "preferred_wake_time"):
                        wk = value
                    else:
                        sk = value
                    await _persist_user_wake_sleep(user, db, wk, sk)
                    onboarding = _merge_onboarding_with_schedule_prefs(user)
                if active_schedule and key:
                    await schedule_service.update_schedule_context(
                        user_id=user_id,
                        schedule_id=active_schedule["id"],
                        db=db,
                        context_updates={key: value},
                    )
            except Exception as e:
                print(f"Context update failed: {e}")

        elif tool["name"] == "log_check_in":
            try:
                args = tool["args"]
                check_in_data = {}
                if args.get("workout_done"):
                    check_in_data["workout_done"] = True
                if args.get("missed"):
                    check_in_data["missed"] = True
                if args.get("sleep_hours"):
                    check_in_data["sleep_hours"] = args["sleep_hours"]
                if args.get("calories"):
                    check_in_data["calories"] = args["calories"]
                if args.get("mood"):
                    check_in_data["mood"] = args["mood"]
                if args.get("injury_area"):
                    check_in_data["injury"] = {
                        "area": args["injury_area"],
                        "note": args.get("injury_note", ""),
                    }
                if check_in_data:
                    await coaching_service.process_check_in(user_id, db, check_in_data)
            except Exception as e:
                print(f"Check-in logging failed: {e}")

    # --- If user asked to change schedule times but the model didn't call modify_schedule, adapt anyway ---
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
        except Exception as e:
            logger.exception("Forced schedule adaptation failed: %s", e)
    # --- Enforce lowercase on all AI responses ---
    response_text = response_text.lower()

    # --- Save messages (app only; SMS is not stored) ---
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

    # --- Background: update AI memory every ~10 messages (app thread only) ---
    total_msgs = len(history) + 2
    if _persist_chat_history(channel) and total_msgs % 10 == 0:
        try:
            summary = await coaching_service.generate_conversation_summary(history[-20:])
            if summary:
                await coaching_service.update_ai_memory(user_id, db, summary)
        except Exception as e:
            print(f"AI memory update failed: {e}")

    if _persist_chat_history(channel) and total_msgs % 20 == 0:
        try:
            await coaching_service.detect_tone_preference(user_id, db, history[-30:])
        except Exception as e:
            print(f"Tone detection failed: {e}")

    return response_text


@router.post("/message", response_model=ChatResponse)
async def send_message(
    data: ChatRequest,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession | None = Depends(get_rds_db_optional),
):
    """Send message to Max AI (in-app)"""
    response_text = await process_chat_message(
        user_id=current_user["id"],
        message_text=data.message,
        db=db,
        rds_db=rds_db,
        init_context=data.init_context,
        attachment_url=data.attachment_url,
        attachment_type=data.attachment_type,
    )
    return ChatResponse(response=response_text)


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
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Get in-app chat history only (SMS thread is excluded)."""
    user_uuid = UUID(current_user["id"])
    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == user_uuid)
        .where(or_(ChatHistory.channel == "app", ChatHistory.channel.is_(None)))
        .order_by(ChatHistory.created_at.desc())
        .limit(limit)
    )
    rows = list(reversed(result.scalars().all()))
    return {
        "messages": [
        {"role": r.role, "content": r.content, "created_at": r.created_at}
        for r in rows
        ]
    }


def _summarise_schedule(schedule: dict) -> str:
    """Build a short summary of a generated schedule."""
    days = schedule.get("days", [])
    if not days:
        return "schedule created. check your Schedule tab."

    first_day = days[0]
    tasks = first_day.get("tasks", [])
    lines = [f"your {schedule.get('course_title', 'schedule')} is locked in. day 1:"]
    for t in tasks[:5]:
        lines.append(f"  {t.get('time', '??:??')} — {t.get('title', 'Task')}")
    if len(tasks) > 5:
        lines.append(f"  +{len(tasks) - 5} more")
    lines.append(f"\n{len(days)} days planned. check Schedule tab.")
    return "\n".join(lines)
