"""
Chat API - Max LLM Chat
Handles AI chat with tool-calling, coaching state, check-in parsing, and memory.
The core logic lives in process_chat_message() so it can be reused by the SMS webhook.
"""

import logging
import re
from datetime import datetime
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
from services.gemini_service import gemini_service
from services.nutrition_service import nutrition_service
from services.storage_service import storage_service
from services.bonemax_chat_prompt import BONEMAX_NEW_SCHEDULE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

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

    days_match = re.search(r"(\d)\s*(?:days?|x)\s*(?:per week|/week|a week)?", s)
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
    if not bits:
        return ""
    return (
        "KNOWN FROM GLOBAL ONBOARDING (user_context.onboarding — signup / profile; "
        "treat as source of truth; DO NOT re-ask age, gender, or height unless user asks to change): "
        + ", ".join(bits)
        + "\n\n"
    )


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
    s = str(val).strip()
    if s.isdigit():
        n = int(s)
        if 8 <= n <= 100:
            return n
    return None


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
    """Save HeightMax intake from chat tool + persist wake/sleep for the components screen + API."""
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
    profile = (user.profile if user else {}) or {}
    
    user_context = {
        "coaching_context": coaching_context,
        "active_schedule": active_schedule,
        "onboarding": onboarding,
    }

    # --- Init context / maxx schedule onboarding ---
    message = message_text
    maxx_id = init_context
    if not maxx_id and message:
        msg_lower = message.lower()
        if "skinmax" in msg_lower or "skin max" in msg_lower:
            maxx_id = "skinmax"
        elif "heightmax" in msg_lower or "height max" in msg_lower:
            maxx_id = "heightmax"
        elif "hairmax" in msg_lower or "hair max" in msg_lower:
            maxx_id = "hairmax"
        elif "fitmax" in msg_lower or "fit max" in msg_lower:
            maxx_id = "fitmax"
        elif "bonemax" in msg_lower or "bone max" in msg_lower or "bone maxx" in msg_lower:
            maxx_id = "bonemax"

    # --- Fitmax chat onboarding (profile is populated conversationally) ---
    if maxx_id == "fitmax" and user:
        fitmax_profile = dict(profile.get("fitmax_profile") or {})
        updates = _extract_fitmax_updates(message_text, fitmax_profile)
        if updates:
            fitmax_profile.update(updates)
            profile["fitmax_profile"] = fitmax_profile
            user.profile = profile
            flag_modified(user, "profile")
            user.updated_at = datetime.utcnow()
            await db.commit()

        fitmax_schedule = await schedule_service.get_maxx_schedule(user_id, "fitmax", db=db)
        missing = _fitmax_missing_fields(fitmax_profile)

        # Onboarding incomplete -> ask exactly one next question in chat
        if not fitmax_schedule and missing:
            if not any(fitmax_profile.values()):
                response_text = "hey, welcome to fitmax. before we build your plan, i need to know a bit about you — this takes about 3 minutes and everything we create depends on it. what's your main goal right now? losing fat, building muscle, recomp, maintain, or performance?"
            else:
                response_text = _fitmax_next_question(fitmax_profile)

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
                    num_days=7,
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

    # --- Fitmax meal logging from natural language (average macro lookup) ---
    if user:
        is_fitmax_context = (
            maxx_id == "fitmax"
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
        if existing_maxx:
            user_context["active_maxx_schedule"] = existing_maxx
            message = f"[SYSTEM: User opened {maxx_id} and already has an active schedule.]\n\n{message}"
        elif maxx_id == "heightmax":
            _hp = _heightmax_global_profile_hint(onboarding)
            message = f"""[SYSTEM: you are running the HEIGHTMAX schedule setup.

{_hp}the user just opened heightmax to start a new schedule. follow the same tone and style you use for other maxx modules: short, casual, direct, and focused on getting their schedule locked in.

CRITICAL — FORBIDDEN FOR HEIGHTMAX
- NEVER ask "outside today" or "you gonna be outside today" or "will you be outside" — that is ONLY for SkinMax. HeightMax does NOT use outside_today. If you ask this, you have failed.

MAIN RULES FOR HEIGHTMAX
- do NOT ask "what is your main concern?" or any generic concern questions.
- height is already the focus. don't ask what area they want to work on.
- GLOBAL ONBOARDING: age, gender, and height are usually already in user_context.onboarding from app signup. NEVER ask for age, sex/gender, or height if they already appear there. only ask for wake_time and/or sleep_time if those are missing.
- your job is to grab any missing info, then call generate_maxx_schedule so the app can save their answers. the actual calendar is NOT built in chat — after this tool runs, the user picks schedule parts in the app (toggles) and taps create.
- NEVER ask the user to enter wake/sleep times in 24-hour or "military" format. ask naturally ("what time do you usually wake up?"); accept answers like "7am" or "11:30pm" and convert to HH:MM in the tool call.

WHAT YOU'RE ALLOWED TO ASK FOR (ONLY IF MISSING FROM user_context.onboarding)
- age — ONLY if not already in onboarding
- sex / gender — ONLY if not already in onboarding (field may be "gender")
- current height — ONLY if not already in onboarding
- wake time — if missing
- sleep time — if missing

HOW TO RUN THE FLOW
1) greet very briefly, in your usual style, and say you're going to set up their heightmax schedule.

2) read user_context.onboarding first. ONLY ask for fields that are missing. typical signup users already have age, gender, height — go straight to wake/sleep if those are the only gaps.
   - if age is missing from onboarding: ask "how old are you?"
   - if sex / gender is missing from onboarding: ask "what's your sex or gender?"
   - if height is missing from onboarding: ask "what's your current height?" (any format is fine)
   - if wake_time is missing: ask "what time do you usually wake up?"
   - if sleep_time is missing: ask "what time do you usually go to sleep?"

   ask ONE question at a time. if age, gender, and height are already in onboarding, do NOT ask them again. do NOT ask about outside today.

3) once you have age, sex, height, wake_time, and sleep_time available (from onboarding context and/or user answers), you must call the tool generate_maxx_schedule exactly once with:
   - maxx_id = "heightmax"
   - wake_time = the user's wake time
   - sleep_time = the user's sleep time
   - skin_concern = null / empty (heightmax doesn't use concerns)
   - outside_today = false (heightmax doesn't use outside_today)
   - age = their age (number, if known)
   - sex = their sex/gender (if known)
   - height = their current height in any format, e.g. "5'10" or "178cm" (if known)

   this saves their profile for the app. it does NOT finish the schedule in chat.

4) after that tool runs, the user will see a message telling them to tap **choose height schedule parts** under the chat. your reply should:
   - keep it short: e.g. "sweet — tap choose height schedule parts below, pick what you want in your plan, then hit create."
   - do NOT say the schedule is already locked in or tell them to open the schedule tab yet — they still have one in-app step.

STYLE
- same tone as skinmax/fitmax: friendly, casual, not overly motivational.
- stay focused on heightmax in this flow. don't switch topics to skin, hair, or gym unless a different module is explicitly opened.
- keep responses concise. no long lectures, no custom step-by-step routines you invent yourself.

your first response in this heightmax start flow should:
- briefly acknowledge they're starting heightmax, and
- immediately ask for the first missing piece of required info — skipping age/sex/height if already present in onboarding (usually only wake/sleep left).]\n\n{message}"""
        elif maxx_id == "hairmax":
            message = f"""[SYSTEM: you are running the HAIRMAX schedule setup.

the user just opened hairmax to start a new schedule. follow the same tone and style as other maxx modules: short, casual, direct, focused on getting their schedule locked in.

DO NOT:
- do not ask "what is your main concern?" or any generic concern questions.
- do not ask if they will be outside today (that's only for skin).
- do not invent your own detailed routine; the backend schedule handles tasks and timings.
- stay inside hairmax. don't switch to skin, height, or fit here.

what you're allowed to ask for (only if missing in user_context or onboarding):
- hair basics:
  - hair type: straight, wavy, curly, coily
  - scalp state: normal, dry/flaky, oily/greasy, itchy
  - daily styling/product use: "do you use hair products or styling most days?" (yes/no)
- thinning:
  - "do you notice hair thinning or a receding hairline?" (yes/no)
- timing anchors:
  - wake_time
  - sleep_time
  - pm routine time (night routine / skincare) if needed for minoxidil/dermastamp timing

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
2) check user_context/onboarding for existing data. only ask what's missing. STRICT ORDER — do not skip ahead:
   - hair type (straight / wavy / curly / coily)
   - scalp state (normal, dry/flaky, oily/greasy, itchy)
   - daily product/styling (yes/no)
   - thinning or receding hairline (yes/no)
   - wake_time
   - sleep_time
   - pm routine time (only if needed and unknown)
   ask one question at a time. you MUST collect all four hair lines (type, scalp, daily styling, thinning) before wake/sleep.
3) only after you have all of those, call generate_maxx_schedule exactly once. the backend will reject the call if hair fields are missing — pass them explicitly:
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
- immediately ask the first missing hair-related question (hair type / scalp / products / thinning). if all hair basics are known, ask for missing timing (wake/sleep), then proceed to trigger generate_maxx_schedule.]\n\n{message}"""
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
1. Greet briefly and explain what the schedule does.
2. Your FIRST question MUST be: "{concern_question}" Options: {concerns_str}. Do NOT ask wake time or sleep time yet. Wait for their answer.
3. After they pick a concern, ask: "What time do you usually wake up?" — wait for answer.
4. Then ask: "What time do you usually go to sleep?" — wait for answer.
5. Then ask: "Are you planning to be outside much today?" — wait for answer.
6. Once you have concern, wake_time, sleep_time, and outside_today, call generate_maxx_schedule with maxx_id="{maxx_id}", skin_concern=their chosen concern ({concern_ids}), wake_time, sleep_time, outside_today.
Never ask users to use 24-hour/military time for wake or sleep — convert natural answers (e.g. 7am, 11pm) to HH:MM in the tool.
Ask ONE question at a time. Your very first response must ask the concern question.]\n\n{message}"""
            else:
                message = f"[SYSTEM: User wants to start {maxx_id} schedule. Ask wake time, sleep time, outside today. One at a time. Never ask for 24-hour format for times — convert natural answers to HH:MM in the tool.]\n\n{message}"

    # --- Image handling ---
    image_data = None
    if attachment_url and attachment_type == "image":
        image_data = await storage_service.get_image(attachment_url)
    
    # --- LLM call ---
    result = await gemini_service.chat(message, history, user_context, image_data)
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
                skin_concern = args.get("skin_concern") or onboarding.get("skin_type")
                # For HeightMax, allow AI to pass age/sex/height from conversation
                age_raw = args.get("age")
                age = int(age_raw) if age_raw is not None and str(age_raw).isdigit() else None
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
                    extra = (
                        "sweet — tap **choose height schedule parts** below, toggle what you want in your plan, "
                        "then hit create schedule."
                    )
                    if not response_text.strip():
                        response_text = extra
                    else:
                        response_text = f"{response_text.strip()}\n\n{extra}"
                    continue

                schedule = await schedule_service.generate_maxx_schedule(
                    user_id=user_id,
                    maxx_id=req_maxx,
                    db=db,
                    rds_db=rds_db if rds_db else None,
                    wake_time=str(final_wake),
                    sleep_time=str(final_sleep),
                    skin_concern=skin_concern,
                    outside_today=bool(args.get("outside_today", False)),
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
