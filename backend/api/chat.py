"""
Chat API - Max LLM Chat
Handles AI chat with tool-calling, coaching state, check-in parsing, and memory.
The core logic lives in process_chat_message() so it can be reused by the SMS webhook.
"""

from fastapi import APIRouter, Depends
from datetime import datetime
from uuid import UUID
from typing import Optional
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from db import get_db, get_rds_db_optional
from middleware.auth_middleware import require_paid_user
from services.gemini_service import gemini_service
from services.storage_service import storage_service
from services.coaching_service import coaching_service
from services.nutrition_service import nutrition_service
from models.leaderboard import ChatRequest, ChatResponse
from models.sqlalchemy_models import ChatHistory, Scan, User

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
            continue

        if not match_key:
            continue

        base = FITMAX_FOOD_DB[match_key]
        totals["calories"] += int(round(base["calories"] * qty))
        totals["protein_g"] += int(round(base["protein_g"] * qty))
        totals["carbs_g"] += int(round(base["carbs_g"] * qty))
        totals["fat_g"] += int(round(base["fat_g"] * qty))
        matched_items.append(match_key)

    if not matched_items or totals["calories"] <= 0:
        return None

    return {
        "items": matched_items,
        "calories": totals["calories"],
        "protein_g": totals["protein_g"],
        "carbs_g": totals["carbs_g"],
        "fat_g": totals["fat_g"],
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


async def process_chat_message(
    user_id: str,
    message_text: str,
    db: AsyncSession,
    rds_db: Optional[AsyncSession] = None,
    init_context: Optional[str] = None,
    attachment_url: Optional[str] = None,
    attachment_type: Optional[str] = None,
) -> str:
    """
    Core chat logic shared by the HTTP endpoint and the SMS webhook.
    Returns the AI response text. Saves both user + assistant messages to ChatHistory.
    """
    from services.schedule_service import schedule_service
    user_uuid = UUID(user_id)

    # Load chat history
    history_result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == user_uuid)
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
    onboarding = (user.onboarding if user else {}) or {}
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
                created_at=datetime.utcnow(),
            )
            assistant_message = ChatHistory(
                user_id=user_uuid,
                role="assistant",
                content=response_text,
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

            user_message = ChatHistory(
                user_id=user_uuid,
                role="user",
                content=message_text,
                created_at=datetime.utcnow(),
            )
            assistant_message = ChatHistory(
                user_id=user_uuid,
                role="assistant",
                content=response_text,
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

            response_text = (
                f"logged. that's roughly {food_log['calories']} calories and {food_log['protein_g']}g protein "
                f"({food_log['carbs_g']}g carbs, {food_log['fat_g']}g fat). "
                f"you've got {remaining} calories left today."
            )

            user_message = ChatHistory(
                user_id=user_uuid,
                role="user",
                content=message_text,
                created_at=datetime.utcnow(),
            )
            assistant_message = ChatHistory(
                user_id=user_uuid,
                role="assistant",
                content=response_text,
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
Ask ONE question at a time. Your very first response must ask the concern question.]\n\n{message}"""
            else:
                message = f"[SYSTEM: User wants to start {maxx_id} schedule. Ask wake time, sleep time, outside today. One at a time.]\n\n{message}"

    # --- Image handling ---
    image_data = None
    if attachment_url and attachment_type == "image":
        image_data = await storage_service.get_image(attachment_url)

    # --- LLM call ---
    result = await gemini_service.chat(message, history, user_context, image_data)
    response_text = result.get("text", "")
    tool_calls = result.get("tool_calls", [])

    # --- Process tool calls ---
    for tool in tool_calls:
        if tool["name"] == "modify_schedule" and active_schedule:
            try:
                feedback = tool["args"].get("feedback")
                if feedback:
                    await schedule_service.adapt_schedule(
                        user_id=user_id,
                        schedule_id=active_schedule["id"],
                        db=db,
                        feedback=feedback,
                    )
            except Exception as e:
                print(f"Schedule adaptation failed: {e}")

        elif tool["name"] == "generate_maxx_schedule":
            try:
                args = tool["args"]
                skin_concern = args.get("skin_concern") or onboarding.get("skin_type")
                schedule = await schedule_service.generate_maxx_schedule(
                    user_id=user_id,
                    maxx_id=str(args.get("maxx_id", "skinmax")),
                    db=db,
                    rds_db=rds_db if rds_db else None,
                    wake_time=str(args.get("wake_time", "07:00")),
                    sleep_time=str(args.get("sleep_time", "23:00")),
                    skin_concern=skin_concern,
                    outside_today=bool(args.get("outside_today", False)),
                )
                schedule_summary = _summarise_schedule(schedule)
                if not response_text.strip():
                    response_text = schedule_summary
                else:
                    response_text += f"\n\n{schedule_summary}"
            except Exception as e:
                print(f"Maxx schedule generation failed: {e}")
                response_text += "\n\nhad trouble generating your schedule. try again in a sec."

        elif tool["name"] == "update_schedule_context":
            try:
                args = tool["args"]
                key, value = str(args.get("key", "")), str(args.get("value", ""))
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

    # --- Enforce lowercase on all AI responses ---
    response_text = response_text.lower()

    # --- Save messages ---
    user_message = ChatHistory(
        user_id=user_uuid,
        role="user",
        content=message_text,
        created_at=datetime.utcnow(),
    )
    assistant_message = ChatHistory(
        user_id=user_uuid,
        role="assistant",
        content=response_text,
        created_at=datetime.utcnow(),
    )
    db.add(user_message)
    db.add(assistant_message)
    await db.commit()

    # --- Background: update AI memory every ~10 messages ---
    total_msgs = len(history) + 2
    if total_msgs % 10 == 0:
        try:
            summary = await coaching_service.generate_conversation_summary(history[-20:])
            if summary:
                await coaching_service.update_ai_memory(user_id, db, summary)
        except Exception as e:
            print(f"AI memory update failed: {e}")

    if total_msgs % 20 == 0:
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
    """Get chat history"""
    user_uuid = UUID(current_user["id"])
    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == user_uuid)
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
