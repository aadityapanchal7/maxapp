"""
FitMax profile seeding, merge/validation for agent tool calls, and macro plan math.

Shared by api/chat.py (scripted onboarding) and services/lc_agent.py (generate_maxx_schedule tool).
"""

from __future__ import annotations

import re
from typing import Any, Optional


def _safe_int_age(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(float(str(val).strip()))
    except (TypeError, ValueError):
        return None


def fitmax_activity_multiplier(level: str) -> float:
    return {
        "sedentary": 1.2,
        "lightly_active": 1.375,
        "moderately_active": 1.55,
        "very_active": 1.725,
    }.get(level or "moderately_active", 1.55)


def fitmax_build_plan(profile: dict) -> dict:
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

    tdee = int(round(bmr * fitmax_activity_multiplier(activity)))
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


def height_cm_from_text(text: str) -> Optional[float]:
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


def weight_kg_from_text(text: str) -> Optional[float]:
    s = (text or "").strip().lower()
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


def normalize_fitmax_goal_slug(skin_concern: Optional[str], existing_goal: Optional[str] = None) -> Optional[str]:
    """Map tool skin_concern or free text to internal goal slug."""
    if existing_goal and str(existing_goal).strip() in (
        "fat_loss",
        "muscle_gain",
        "recomp",
        "maintenance",
        "performance",
    ):
        return str(existing_goal).strip()
    blob = f"{skin_concern or ''} {existing_goal or ''}".lower()
    if not blob.strip():
        return None
    if any(k in blob for k in ("fat loss", "lose fat", "cut", "shred", "fat_loss")):
        return "fat_loss"
    if any(k in blob for k in ("muscle gain", "build muscle", "bulk", "hypertrophy", "mass", "muscle_gain")):
        return "muscle_gain"
    if "recomp" in blob:
        return "recomp"
    if any(k in blob for k in ("maintain", "maintenance")):
        return "maintenance"
    if any(k in blob for k in ("performance", "strength", "athletic")):
        return "performance"
    return None


def _slug_to_fitmax_primary_goal_text(slug: str) -> str:
    return {
        "fat_loss": "fat loss",
        "muscle_gain": "muscle gain",
        "recomp": "recomp",
        "maintenance": "maintenance",
        "performance": "performance",
    }.get(slug, slug.replace("_", " "))


def normalize_daily_activity_level(raw: Optional[str]) -> Optional[str]:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip().lower().replace(" ", "_")
    if s in ("sedentary", "lightly_active", "moderately_active", "very_active"):
        return s
    if "sedentary" in s or "desk" in s:
        return "sedentary"
    if "light" in s:
        return "lightly_active"
    if "moderate" in s or "medium" in s or "average" in s:
        return "moderately_active"
    if "very" in s or "high" in s or "extreme" in s:
        return "very_active"
    return None


def normalize_biological_sex(sex: Optional[str], gender: Optional[str]) -> Optional[str]:
    blob = f"{sex or ''} {gender or ''}".lower()
    if any(x in blob for x in ("female", "woman", "girl", "f ")):
        return "female"
    if any(x in blob for x in ("male", "man", "boy", "m ")):
        return "male"
    return None


def seed_fitmax_profile_from_onboarding(profile: dict, ob: dict) -> dict:
    """Pre-fill FitAgartha chat profile from global / FitMax questionnaire answers (same logic as chat.py)."""
    out = dict(profile or {})
    ob = ob or {}

    def take(dst: str, val: Any, only_if_empty: bool = True) -> None:
        if val is None or val == "" or val == []:
            return
        if only_if_empty and out.get(dst) not in (None, "", []):
            return
        out[dst] = val

    fpg = str(ob.get("fitmax_primary_goal") or ob.get("primary_goal") or "").lower()
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
        cm = height_cm_from_text(str(h))
        if cm is not None:
            take("height_cm", cm)
        else:
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

    d = ob.get("fitmax_workout_days_per_week") or ob.get("workout_days_per_week")
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


def merge_fitmax_tool_into_profile(
    merged: dict,
    *,
    age: Optional[int],
    sex: Optional[str],
    gender: Optional[str],
    height_str: Optional[str],
    skin_concern: Optional[str],
    body_weight_kg: Optional[float],
    training_days_per_week: Optional[int],
    training_experience: Optional[str],
    fitmax_equipment: Optional[str],
    session_minutes: Optional[int],
    daily_activity_level: Optional[str],
    dietary_restrictions: Optional[str],
) -> None:
    """Apply tool-call arguments onto merged profile (mutates merged)."""
    a = _safe_int_age(age)
    if a is not None:
        merged["age"] = a
    bio = normalize_biological_sex(sex, gender)
    if bio:
        merged["biological_sex"] = bio
    if body_weight_kg is not None:
        try:
            merged["weight_kg"] = float(body_weight_kg)
        except (TypeError, ValueError):
            pass
    if training_days_per_week is not None:
        try:
            d = int(training_days_per_week)
            if 1 <= d <= 7:
                merged["days_per_week"] = d
        except (TypeError, ValueError):
            pass
    if height_str and str(height_str).strip():
        hs = str(height_str).strip()
        cm = height_cm_from_text(hs)
        if cm is not None:
            merged["height_cm"] = cm
        else:
            try:
                merged["height_cm"] = float(hs)
            except (TypeError, ValueError):
                pass
    gslug = normalize_fitmax_goal_slug(skin_concern, merged.get("goal"))
    if gslug:
        merged["goal"] = gslug
    if training_experience and str(training_experience).strip():
        e = str(training_experience).strip().lower()
        if "beginner" in e:
            merged["experience_level"] = "beginner"
        elif "intermediate" in e:
            merged["experience_level"] = "intermediate"
        elif "advanced" in e:
            merged["experience_level"] = "advanced"
    if fitmax_equipment and str(fitmax_equipment).strip():
        merged["equipment"] = str(fitmax_equipment).strip()
    if session_minutes is not None:
        try:
            sm = int(session_minutes)
            if 15 <= sm <= 240:
                merged["session_minutes"] = sm
        except (TypeError, ValueError):
            pass
    dal = normalize_daily_activity_level(daily_activity_level)
    if dal:
        merged["daily_activity_level"] = dal
    if dietary_restrictions and str(dietary_restrictions).strip():
        merged["dietary_restrictions"] = str(dietary_restrictions).strip().lower()


def fitmax_validate_required(merged: dict) -> list[str]:
    """Return list of missing human-readable fields for FitMax schedule generation."""
    missing: list[str] = []
    if not merged.get("goal"):
        missing.append("goal (fat_loss/muscle_gain/recomp/maintenance/performance — use skin_concern in tool)")
    if merged.get("weight_kg") in (None, "", []):
        missing.append("weight (pass body_weight_kg or set in profile)")
    if merged.get("height_cm") in (None, "", []):
        missing.append("height (pass height string or set in profile)")
    if merged.get("age") in (None, "", []):
        missing.append("age")
    if not merged.get("biological_sex"):
        missing.append("biological_sex (male/female — pass sex or gender)")
    if merged.get("days_per_week") in (None, "", []):
        missing.append("training_days_per_week (3-6 typical)")
    return missing


def persist_fitmax_to_user_onboarding(user: Any, merged: dict) -> None:
    """Mirror key FitMax fields onto User.onboarding for schedule_service / resolve_fitmax_phase."""
    ob = dict(user.onboarding or {})
    if merged.get("goal"):
        ob["fitmax_primary_goal"] = _slug_to_fitmax_primary_goal_text(str(merged["goal"]))
    if merged.get("weight_kg") is not None:
        try:
            ob["weight"] = float(merged["weight_kg"])
        except (TypeError, ValueError):
            pass
    if merged.get("age") is not None:
        ob["age"] = merged["age"]
    if merged.get("biological_sex"):
        ob["gender"] = merged["biological_sex"]
    if merged.get("height_cm") is not None:
        ob["height"] = str(merged["height_cm"])
    if merged.get("days_per_week") is not None:
        ob["fitmax_workout_days_per_week"] = merged["days_per_week"]
    if merged.get("experience_level"):
        ob["fitmax_training_experience"] = merged["experience_level"]
    if merged.get("equipment"):
        ob["fitmax_equipment"] = merged["equipment"]
    if merged.get("session_minutes") is not None:
        ob["fitmax_session_minutes"] = merged["session_minutes"]
    if merged.get("daily_activity_level"):
        ob["activity_level"] = merged["daily_activity_level"].replace("_", " ")
    if merged.get("dietary_restrictions"):
        ob["fitmax_diet_approach"] = merged["dietary_restrictions"]
    user.onboarding = ob
