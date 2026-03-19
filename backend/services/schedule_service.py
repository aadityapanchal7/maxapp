"""
Schedule Service - AI-powered personalised schedule generation using Gemini
Generates, adapts, and manages user schedules for course modules.
"""

import copy
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from zoneinfo import ZoneInfo
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from config import settings
from services.gemini_service import GeminiService
from services.guideline_service import (
    get_maxx_guideline_async,
    resolve_concern,
    build_protocol_prompt_section,
)
from models.sqlalchemy_models import User, UserSchedule, Scan
from models.rds_models import Course

logger = logging.getLogger(__name__)

SCHEDULE_GENERATION_PROMPT = """You are an expert fitness and self-improvement coach specialising in lookmaxxing.
Your job is to create a PERSONALISED daily schedule for a user working on a specific module.

## MODULE INFO
Title: {module_title}
Description: {module_description}

## MODULE GUIDELINES (loose — use your expertise to flesh these out)
Exercises: {exercises}
Frequency hints: {frequency_hints}
Duration ranges: {duration_ranges}
Tips: {tips}
Difficulty progression: {difficulty_progression}
Focus areas: {focus_areas}

## USER CONTEXT
Wake time: {wake_time}
Sleep time: {sleep_time}
Preferred workout times: {preferred_times}
Days to generate: {num_days}
{user_history_context}

## INSTRUCTIONS
1. Create a schedule for {num_days} days.
2. Space tasks throughout the day between wake and sleep times.
3. Make each day slightly different to prevent boredom.
4. Gradually increase intensity / duration over the days.
5. Include motivational messages for each day.
6. Each task must have: task_id (uuid), time (HH:MM), title, description, task_type (exercise/routine/reminder/checkpoint), duration_minutes.
7. Adapt based on user history if provided — if they skip certain tasks, reduce those; if they complete everything, ramp up.

## OUTPUT FORMAT
Return ONLY valid JSON matching this structure (no markdown fences):
{{
  "days": [
    {{
      "day_number": 1,
      "tasks": [
        {{
          "task_id": "uuid-string",
          "time": "07:00",
          "title": "Morning Mewing Session",
          "description": "Place tongue flat against roof of mouth...",
          "task_type": "exercise",
          "duration_minutes": 15
        }}
      ],
      "motivation_message": "Day 1! Let's build that jawline. Consistency is king."
    }}
  ]
}}
"""

SCHEDULE_ADAPTATION_PROMPT = """You are an expert fitness coach. A user wants to ADAPT their existing schedule.

## CURRENT SCHEDULE
{current_schedule_json}

## COMPLETION STATS
Tasks completed: {completed_count}/{total_count}
Most skipped task types: {most_skipped}
Average completion rate: {completion_rate}%

## USER FEEDBACK
"{user_feedback}"

## INSTRUCTIONS
Modify the remaining days of the schedule based on the feedback and completion data.
- If the user says "too hard", reduce intensity/duration.
- If "too easy", increase it.
- If they skip morning tasks, move them later.
- Keep the same JSON structure as the input.
- Preserve task_id for existing tasks so notifications work. For new tasks, generate a uuid string.

Return ONLY valid JSON with this structure (no markdown fences):
{{
  "days": [ ... ],
  "changes_summary": "REQUIRED. 1-3 lines, each starts with •. Facts only: what moved/added/removed. No filler, no 'i updated' or 'hope this helps'."
}}
"""


MAXX_SCHEDULE_PROMPT = """You are an expert self-improvement coach specialising in lookmaxxing.
Your job is to create a PERSONALISED recurring daily/weekly schedule for a user.

## MAXX TYPE: {maxx_label}

{protocol_section}

## USER CONTEXT
Wake time: {wake_time}
Sleep time: {sleep_time}
Profile hint: {profile_hint}
Selected concern: {selected_concern}
Outside today: {outside_today}
{user_profile_context}

## PERSONALIZATION (HeightMax)
When building a HeightMax schedule, USE the user's age, sex, and height from USER CONTEXT:
- Age: affects growth-plate status (adults vs teens), recovery needs, and intensity
- Sex: affects typical frame, hormone context, and protocol emphasis
- Height: affects baseline and goal framing
Personalize task types, timing, and messaging accordingly.

## INSTRUCTIONS
1. Create a schedule for {num_days} days.
2. Use the protocol and schedule rules for this maxx, not skincare assumptions unless the protocol explicitly says so.
3. Schedule morning tasks shortly after wake time and evening tasks with enough runway before sleep to actually get done.
4. Spread weekly or higher-intensity tasks across different days.
5. If the protocol involves outside exposure reminders, only add them when outside_today is true.
6. Include a short morning check-in task at wake time.
7. Each task must have: task_id (uuid), time (HH:MM in 24h), title, description, task_type (routine/reminder/checkpoint), duration_minutes.
8. task_type "routine" = core habit block, "reminder" = cue or anti-habit push, "checkpoint" = weekly treatment, harder session, or review.
9. Keep daily routines consistent but vary weekly treatments, sprint sessions, and review tasks across days.
10. Include brief motivational messages for each day.

## OUTPUT FORMAT
Return ONLY valid JSON matching this structure (no markdown fences):
{{
  "days": [
    {{
      "day_number": 1,
      "tasks": [
        {{
          "task_id": "uuid-string",
          "time": "07:00",
          "title": "Morning Check-in",
          "description": "Let me know you're awake! Say 'I'm awake' in chat.",
          "task_type": "reminder",
          "duration_minutes": 1
        }},
        {{
          "task_id": "uuid-string",
          "time": "07:15",
          "title": "AM Skincare Routine",
          "description": "Gentle cleanser → serum → moisturizer → sunscreen",
          "task_type": "routine",
          "duration_minutes": 10
        }}
      ],
      "motivation_message": "Day 1! Your skin transformation starts now."
    }}
  ]
}}
"""


class ScheduleService:
    """AI-powered schedule generation and management"""

    def __init__(self):
        self.gemini = GeminiService()

    async def generate_schedule(
        self,
        user_id: str,
        course_id: str,
        module_number: int,
        db: AsyncSession,
        rds_db: AsyncSession,
        preferences: Optional[dict] = None,
        num_days: int = 7,
    ) -> dict:
        """Generate a personalised schedule for a user's course module."""
        try:
            course_uuid = UUID(course_id)
        except ValueError:
            raise ValueError("Course not found")

        course_result = await rds_db.execute(select(Course).where(Course.id == course_uuid))
        course = course_result.scalar_one_or_none()
        if not course:
            raise ValueError("Course not found")

        module = None
        for m in (course.modules or []):
            if m.get("module_number") == module_number:
                module = m
                break
        if not module:
            raise ValueError(f"Module {module_number} not found in course")

        user_uuid = UUID(user_id)
        user = await db.get(User, user_uuid)
        user_history_context = await self._build_user_context(db, user_id, course_id)

        tz_name = (user.onboarding if user else {}).get("timezone", "UTC")
        try:
            user_tz = ZoneInfo(tz_name)
        except Exception:
            user_tz = ZoneInfo("UTC")

        prefs = preferences or {}
        wake_time = prefs.get("wake_time", "07:00")
        sleep_time = prefs.get("sleep_time", "23:00")
        preferred_times = prefs.get("preferred_workout_times", ["08:00", "18:00"])

        guidelines = module.get("guidelines", {}) or {}
        if num_days == 7 and guidelines.get("recommended_days"):
            num_days = guidelines["recommended_days"]

        prompt = SCHEDULE_GENERATION_PROMPT.format(
            module_title=module.get("title", ""),
            module_description=module.get("description", ""),
            exercises=", ".join(guidelines.get("exercises", ["General exercises"])),
            frequency_hints=", ".join(guidelines.get("frequency_hints", ["Daily"])),
            duration_ranges=", ".join(guidelines.get("duration_ranges", ["15-30 min"])),
            tips=", ".join(guidelines.get("tips", ["Stay consistent"])),
            difficulty_progression=guidelines.get("difficulty_progression", "gradual"),
            focus_areas=", ".join(guidelines.get("focus_areas", ["Overall improvement"])),
            wake_time=wake_time,
            sleep_time=sleep_time,
            preferred_times=", ".join(preferred_times),
            num_days=num_days,
            user_history_context=user_history_context,
        )

        try:
            import google.generativeai as genai
            model = genai.GenerativeModel(settings.gemini_model)
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(response_mime_type="application/json"),
            )
            schedule_data = json.loads(response.text)
        except Exception as e:
            logger.error(f"Gemini schedule generation failed: {e}")
            schedule_data = self._generate_fallback_schedule(module, num_days, wake_time)

        for day in schedule_data.get("days", []):
            for task in day.get("tasks", []):
                if not task.get("task_id"):
                    task["task_id"] = str(uuid.uuid4())
                task.setdefault("status", "pending")
                task.setdefault("notification_sent", False)

        start_date = datetime.now(user_tz).date() + timedelta(days=1)
        for day in schedule_data.get("days", []):
            day_num = day.get("day_number", 1)
            day["date"] = (start_date + timedelta(days=day_num - 1)).isoformat()

        # Deactivate existing active schedule for this module
        existing_result = await db.execute(
            select(UserSchedule)
            .where(
                (UserSchedule.user_id == user_uuid) &
                (UserSchedule.course_id == course_uuid) &
                (UserSchedule.module_number == module_number) &
                (UserSchedule.is_active == True)
            )
        )
        for sched in existing_result.scalars().all():
            sched.is_active = False
            sched.updated_at = datetime.utcnow()
        await db.commit()

        schedule_row = UserSchedule(
            user_id=user_uuid,
            course_id=course_uuid,
            course_title=course.title,
            module_number=module_number,
            days=schedule_data.get("days", []),
            preferences=prefs,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            adapted_count=0,
            user_feedback=[],
            completion_stats={"completed": 0, "total": 0, "skipped": 0},
        )
        db.add(schedule_row)
        await db.commit()
        await db.refresh(schedule_row)

        return self._schedule_to_dict(schedule_row)

    async def generate_maxx_schedule(
        self,
        user_id: str,
        maxx_id: str,
        db: AsyncSession,
        rds_db: Optional[AsyncSession] = None,
        wake_time: str = "07:00",
        sleep_time: str = "23:00",
        skin_concern: Optional[str] = None,
        outside_today: bool = False,
        num_days: int = 7,
        override_age: Optional[int] = None,
        override_sex: Optional[str] = None,
        override_height: Optional[str] = None,
        override_hair_type: Optional[str] = None,
        override_scalp_state: Optional[str] = None,
        override_daily_styling: Optional[str] = None,
        override_thinning: Optional[str] = None,
    ) -> dict:
        """Generate a personalised recurring schedule for a maxx module."""
        guideline = await get_maxx_guideline_async(maxx_id, rds_db)
        if not guideline:
            raise ValueError(f"Unknown maxx: {maxx_id}")

        user_uuid = UUID(user_id)
        user = await db.get(User, user_uuid)
        onboarding = (user.onboarding if user else {}) or {}

        skin_type = onboarding.get("skin_type", "normal")
        concern = resolve_concern(guideline, skin_type, skin_concern)
        protocol_section = build_protocol_prompt_section(guideline, concern)
        profile_hint = skin_type if maxx_id == "skinmax" else onboarding.get("goal", "none")

        profile_parts = []
        gender_val = override_sex or onboarding.get("gender")
        if gender_val:
            profile_parts.append(f"Gender: {gender_val}")
        age_val = override_age if override_age is not None else onboarding.get("age")
        if age_val is not None:
            profile_parts.append(f"Age: {age_val}")
        height_val = override_height or onboarding.get("height")
        if height_val:
            profile_parts.append(f"Height: {height_val}")
        if maxx_id == "hairmax":
            ht = override_hair_type or onboarding.get("hair_type")
            ss = override_scalp_state or onboarding.get("scalp_state")
            ds = override_daily_styling if override_daily_styling is not None else onboarding.get("daily_styling")
            th = override_thinning if override_thinning is not None else (
                onboarding.get("hair_thinning") if onboarding.get("hair_thinning") is not None else onboarding.get("thinning")
            )
            if ht:
                profile_parts.append(f"Hair type: {ht}")
            if ss:
                profile_parts.append(f"Scalp: {ss}")
            if ds is not None and str(ds).strip() != "":
                profile_parts.append(f"Daily styling/products most days: {ds}")
            if th is not None and str(th).strip() != "":
                profile_parts.append(f"Thinning/receding: {th}")
        user_profile_context = ", ".join(profile_parts) if profile_parts else "No profile data yet."

        prompt = MAXX_SCHEDULE_PROMPT.format(
            maxx_label=guideline["label"],
            protocol_section=protocol_section,
            wake_time=wake_time,
            sleep_time=sleep_time,
            profile_hint=profile_hint,
            selected_concern=concern,
            outside_today="Yes" if outside_today else "No",
            user_profile_context=user_profile_context,
            num_days=num_days,
        )

        try:
            import google.generativeai as genai
            model = genai.GenerativeModel(settings.gemini_model)
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(response_mime_type="application/json"),
            )
            schedule_data = json.loads(response.text)
        except Exception as e:
            logger.error(f"Gemini maxx schedule generation failed: {e}")
            schedule_data = self._generate_maxx_fallback(maxx_id, num_days, wake_time, sleep_time)

        tz_name = onboarding.get("timezone", "UTC")
        try:
            user_tz = ZoneInfo(tz_name)
        except Exception:
            user_tz = ZoneInfo("UTC")

        start_date = datetime.now(user_tz).date()
        for day in schedule_data.get("days", []):
            day_num = day.get("day_number", 1)
            day["date"] = (start_date + timedelta(days=day_num - 1)).isoformat()
            for task in day.get("tasks", []):
                if not task.get("task_id"):
                    task["task_id"] = str(uuid.uuid4())
                task.setdefault("status", "pending")
                task.setdefault("notification_sent", False)

        existing_result = await db.execute(
            select(UserSchedule).where(
                (UserSchedule.user_id == user_uuid)
                & (UserSchedule.maxx_id == maxx_id)
                & (UserSchedule.is_active == True)
            )
        )
        for sched in existing_result.scalars().all():
            sched.is_active = False
            sched.updated_at = datetime.utcnow()
        await db.commit()

        prefs = {
            "wake_time": wake_time,
            "sleep_time": sleep_time,
            "notifications_enabled": True,
            "notification_minutes_before": 5,
        }

        start_date_iso = datetime.now(user_tz).date().isoformat()
        schedule_row = UserSchedule(
            user_id=user_uuid,
            schedule_type="maxx",
            maxx_id=maxx_id,
            course_title=guideline["label"],
            days=schedule_data.get("days", []),
            preferences=prefs,
            schedule_context={
                "selected_concern": concern,
                "skin_concern": concern,
                "skin_type": skin_type,
                "outside_today": outside_today,
                "outside_today_date": start_date_iso,
                "wake_time": wake_time,
                "sleep_time": sleep_time,
            },
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            adapted_count=0,
            user_feedback=[],
            completion_stats={"completed": 0, "total": 0, "skipped": 0},
        )
        db.add(schedule_row)
        await db.commit()
        await db.refresh(schedule_row)

        return self._schedule_to_dict(schedule_row)

    def _generate_maxx_fallback(self, maxx_id: str, num_days: int, wake_time: str, sleep_time: str) -> dict:
        """Fallback schedule when Gemini fails for maxx schedules."""
        if maxx_id == "heightmax":
            return self._generate_heightmax_fallback(num_days, wake_time, sleep_time)

        days = []
        wh, wm = map(int, wake_time.split(":"))
        sh, sm = map(int, sleep_time.split(":"))
        pm_hour = max(0, sh - 1)

        for day_num in range(1, num_days + 1):
            tasks = [
                {
                    "task_id": str(uuid.uuid4()),
                    "time": f"{wh:02d}:{wm:02d}",
                    "title": "Morning Check-in",
                    "description": "Let me know you're awake! Say 'I'm awake' in chat.",
                    "task_type": "reminder",
                    "duration_minutes": 1,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": f"{wh:02d}:{wm + 15:02d}" if wm + 15 < 60 else f"{wh + 1:02d}:{(wm + 15) % 60:02d}",
                    "title": "AM Skincare Routine",
                    "description": "Gentle cleanser → serum → moisturizer → sunscreen",
                    "task_type": "routine",
                    "duration_minutes": 10,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": f"{pm_hour:02d}:{sm:02d}",
                    "title": "PM Skincare Routine",
                    "description": "Cleanser → treatment → moisturizer",
                    "task_type": "routine",
                    "duration_minutes": 10,
                },
            ]
            days.append({
                "day_number": day_num,
                "tasks": tasks,
                "motivation_message": f"Day {day_num} — consistency is everything!",
            })

        return {"days": days}

    def _generate_heightmax_fallback(self, num_days: int, wake_time: str, sleep_time: str) -> dict:
        days = []
        wh, wm = map(int, wake_time.split(":"))
        sh, sm = map(int, sleep_time.split(":"))
        morning_minute = (wm + 10) % 60
        morning_hour = wh + ((wm + 10) // 60)
        wind_down_hour = max(0, sh - 3)
        evening_hour = max(0, sh - 1)
        posture_times = ["11:30", "16:30"]
        sprint_days = {2, 4, 6}

        for day_num in range(1, num_days + 1):
            tasks = [
                {
                    "task_id": str(uuid.uuid4()),
                    "time": f"{wh:02d}:{wm:02d}",
                    "title": "Morning Check-in",
                    "description": "You're up. Own posture early and stop donating height to bad mechanics.",
                    "task_type": "reminder",
                    "duration_minutes": 1,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": f"{morning_hour:02d}:{morning_minute:02d}",
                    "title": "Dead Hang + Decompress",
                    "description": "Dead hang 2 x 20-30 sec, then open hips and hamstrings before desk posture crushes you.",
                    "task_type": "routine",
                    "duration_minutes": 8,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": posture_times[(day_num - 1) % len(posture_times)],
                    "title": "Posture Reset",
                    "description": "Chin back x 10, ribs stacked over pelvis, shoulder blades down and back, then walk tall for 60 sec.",
                    "task_type": "reminder",
                    "duration_minutes": 3,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": f"{wind_down_hour:02d}:{sm:02d}",
                    "title": "Sleep Protection",
                    "description": "No caffeine from here, stop the late sugar spiral, and set up the same bedtime again tonight.",
                    "task_type": "reminder",
                    "duration_minutes": 5,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": f"{evening_hour:02d}:{sm:02d}",
                    "title": "Night Height Routine",
                    "description": "Screens off, posture relaxed, and get to bed on time so recovery isn't fake.",
                    "task_type": "routine",
                    "duration_minutes": 15,
                },
            ]

            if day_num in sprint_days and day_num <= num_days:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": "17:30",
                        "title": "Sprint Session",
                        "description": "Warm up, then 6-10 sprints of 8-12 seconds with 60-90 sec rest. Keep it explosive, not cardio.",
                        "task_type": "checkpoint",
                        "duration_minutes": 20,
                    }
                )
            else:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": "14:00",
                        "title": "Height Killer Check",
                        "description": "Audit slouching, under-eating, all-day sitting, and recovery debt before they flatten your frame.",
                        "task_type": "reminder",
                        "duration_minutes": 2,
                    }
                )

            days.append(
                {
                    "day_number": day_num,
                    "tasks": tasks,
                    "motivation_message": f"Day {day_num} — stop leaking inches and make your frame read the way it should.",
                }
            )

        return {"days": days}

    async def get_current_schedule(
        self, user_id: str, db: AsyncSession, course_id: str = None, module_number: int = None
    ) -> Optional[dict]:
        """Get the user's current active schedule(s)."""
        user_uuid = UUID(user_id)
        query = select(UserSchedule).where(
            (UserSchedule.user_id == user_uuid) & (UserSchedule.is_active == True)
        )
        if course_id:
            try:
                course_uuid = UUID(course_id)
                query = query.where(UserSchedule.course_id == course_uuid)
            except ValueError:
                return None
        if module_number:
            query = query.where(UserSchedule.module_number == module_number)
        query = query.order_by(UserSchedule.created_at.desc()).limit(1)
        result = await db.execute(query)
        schedule = result.scalar_one_or_none()
        return self._schedule_to_dict(schedule) if schedule else None

    async def get_schedule_by_id(self, schedule_id: str, user_id: str, db: AsyncSession) -> Optional[dict]:
        """Get a specific schedule"""
        try:
            schedule_uuid = UUID(schedule_id)
        except ValueError:
            return None
        schedule = await db.get(UserSchedule, schedule_uuid)
        if schedule and schedule.user_id == UUID(user_id):
            return self._schedule_to_dict(schedule)
        return None

    async def complete_task(
        self, user_id: str, schedule_id: str, task_id: str, db: AsyncSession, feedback: Optional[str] = None
    ) -> dict:
        schedule = await self._load_schedule(schedule_id, user_id, db)
        if not schedule:
            raise ValueError("Schedule not found")

        updated = False
        days = schedule.days or []
        for day in days:
            for task in day.get("tasks", []):
                if task.get("task_id") == task_id:
                    task["status"] = "completed"
                    task["completed_at"] = datetime.utcnow().isoformat()
                    updated = True
                    break
            if updated:
                break

        if not updated:
            raise ValueError("Task not found in schedule")

        stats = schedule.completion_stats or {"completed": 0, "total": 0, "skipped": 0}
        stats["completed"] = stats.get("completed", 0) + 1
        stats["total"] = sum(len(d.get("tasks", [])) for d in days)

        schedule.days = days
        flag_modified(schedule, "days")
        schedule.completion_stats = stats
        schedule.updated_at = datetime.utcnow()

        if feedback:
            user_feedback = schedule.user_feedback or []
            user_feedback.append({
                "task_id": task_id,
                "feedback": feedback,
                "timestamp": datetime.utcnow().isoformat(),
            })
            schedule.user_feedback = user_feedback

        await db.commit()
        return {"status": "completed", "completion_stats": stats}

    def _fallback_adapt_changes_summary(
        self, old_days: list, new_days: list, feedback: str
    ) -> str:
        """Deterministic summary when the LLM omits changes_summary. Short, no fluff."""
        lines = []
        try:
            ot = (old_days or [{}])[0].get("tasks", []) if old_days else []
            nt = (new_days or [{}])[0].get("tasks", []) if new_days else []
            n = min(len(ot), len(nt), 4)
            shown = 0
            for i in range(n):
                t0, t1 = ot[i], nt[i]
                if t0.get("time") != t1.get("time") or t0.get("title") != t1.get("title"):
                    title = (t1.get("title") or "task").split("—")[0].strip()[:32]
                    lines.append(f"• {title} {t0.get('time', '?')} → {t1.get('time', '?')}")
                    shown += 1
                    if shown >= 3:
                        break
            if len(nt) != len(ot) and old_days and new_days and shown < 3:
                lines.append(f"• day 1 tasks: {len(ot)} → {len(nt)}")
        except Exception:
            pass

        fb = (feedback or "").strip()
        if not lines and fb:
            lines.append(f"• {fb[:90]}{'…' if len(fb) > 90 else ''}")
        lines.append("• reminders reset")
        return "\n".join(lines)

    async def adapt_schedule(self, user_id: str, schedule_id: str, db: AsyncSession, feedback: str) -> dict:
        schedule = await self._load_schedule(schedule_id, user_id, db)
        if not schedule:
            raise ValueError("Schedule not found")

        old_days_snapshot = copy.deepcopy(schedule.days or [])

        stats = schedule.completion_stats or {}
        total = stats.get("total", 1)
        completed = stats.get("completed", 0)
        completion_rate = round((completed / max(total, 1)) * 100)

        skipped_types = []
        for day in schedule.days or []:
            for task in day.get("tasks", []):
                if task.get("status") == "skipped":
                    skipped_types.append(task.get("task_type", "unknown"))

        prompt = SCHEDULE_ADAPTATION_PROMPT.format(
            current_schedule_json=json.dumps({"days": schedule.days}, indent=2),
            completed_count=completed,
            total_count=total,
            most_skipped=", ".join(set(skipped_types)) if skipped_types else "none",
            completion_rate=completion_rate,
            user_feedback=feedback,
        )

        try:
            import google.generativeai as genai
            model = genai.GenerativeModel(settings.gemini_model)
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(response_mime_type="application/json"),
            )
            adapted = json.loads(response.text)
        except Exception as e:
            logger.error(f"Schedule adaptation failed: {e}")
            raise ValueError(f"Failed to adapt schedule: {e}")

        adapted_days = adapted.get("days", schedule.days)
        changes_summary = (adapted.get("changes_summary") or "").strip()
        if changes_summary:
            # Keep concise: up to 4 lines, ~100 chars each, no rambling
            tight = [ln.strip()[:100] for ln in changes_summary.split("\n") if ln.strip()][:4]
            changes_summary = "\n".join(tight)
        if not changes_summary:
            changes_summary = self._fallback_adapt_changes_summary(
                old_days_snapshot, adapted_days, feedback
            )

        # Reset notification_sent so reminders fire for updated tasks
        for day in adapted_days:
            for task in day.get("tasks", []):
                task["notification_sent"] = False
                if not task.get("task_id"):
                    task["task_id"] = str(uuid.uuid4())

        schedule.days = adapted_days
        flag_modified(schedule, "days")
        schedule.updated_at = datetime.utcnow()
        schedule.adapted_count = (schedule.adapted_count or 0) + 1

        user_feedback = schedule.user_feedback or []
        user_feedback.append({
            "type": "adaptation",
            "feedback": feedback,
            "timestamp": datetime.utcnow().isoformat(),
        })
        schedule.user_feedback = user_feedback
        await db.commit()

        result = self._schedule_to_dict(schedule)
        result["changes_summary"] = changes_summary
        return result

    async def edit_task(
        self, user_id: str, schedule_id: str, task_id: str, db: AsyncSession, updates: dict
    ) -> dict:
        schedule = await self._load_schedule(schedule_id, user_id, db)
        if not schedule:
            raise ValueError("Schedule not found")

        updated = False
        updated_task = None
        days = schedule.days or []
        for day in days:
            for task in day.get("tasks", []):
                if task.get("task_id") == task_id:
                    if updates.get("time"):
                        task["time"] = updates["time"]
                        task["notification_sent"] = False
                    if updates.get("title"):
                        task["title"] = updates["title"]
                    if updates.get("description"):
                        task["description"] = updates["description"]
                    if updates.get("duration_minutes"):
                        task["duration_minutes"] = updates["duration_minutes"]
                    updated = True
                    updated_task = task
                    break
            if updated:
                break

        if not updated:
            raise ValueError("Task not found in schedule")

        schedule.days = days
        flag_modified(schedule, "days")
        schedule.updated_at = datetime.utcnow()
        await db.commit()
        return {"status": "updated", "task": updated_task}

    async def delete_task(
        self, user_id: str, schedule_id: str, task_id: str, db: AsyncSession
    ) -> dict:
        schedule = await self._load_schedule(schedule_id, user_id, db)
        if not schedule:
            raise ValueError("Schedule not found")

        deleted = False
        days = schedule.days or []
        for day in days:
            original_count = len(day.get("tasks", []))
            day["tasks"] = [t for t in day.get("tasks", []) if t.get("task_id") != task_id]
            if len(day["tasks"]) < original_count:
                deleted = True
                break

        if not deleted:
            raise ValueError("Task not found in schedule")

        schedule.days = days
        flag_modified(schedule, "days")
        schedule.updated_at = datetime.utcnow()
        await db.commit()
        return {"status": "deleted"}

    async def get_maxx_schedule(self, user_id: str, maxx_id: str, db: AsyncSession) -> Optional[dict]:
        """Get the user's active schedule for a specific maxx."""
        user_uuid = UUID(user_id)
        result = await db.execute(
            select(UserSchedule).where(
                (UserSchedule.user_id == user_uuid)
                & (UserSchedule.maxx_id == maxx_id)
                & (UserSchedule.is_active == True)
            ).order_by(UserSchedule.created_at.desc()).limit(1)
        )
        schedule = result.scalar_one_or_none()
        return self._schedule_to_dict(schedule) if schedule else None

    async def update_schedule_context(self, user_id: str, schedule_id: str, db: AsyncSession, context_updates: dict) -> dict:
        """Update learned context on a schedule (e.g. outside_today, actual wake time)."""
        schedule = await self._load_schedule(schedule_id, user_id, db)
        if not schedule:
            raise ValueError("Schedule not found")
        ctx = schedule.schedule_context or {}
        ctx.update(context_updates)

        # When outside_today is updated, set outside_today_date so we can refresh daily
        if "outside_today" in context_updates:
            user = await db.get(User, schedule.user_id)
            tz_name = (user.onboarding or {}).get("timezone", "UTC") if user else "UTC"
            try:
                user_tz = ZoneInfo(tz_name)
            except Exception:
                user_tz = ZoneInfo("UTC")
            ctx["outside_today_date"] = datetime.now(user_tz).date().isoformat()

        schedule.schedule_context = ctx
        flag_modified(schedule, "schedule_context")
        schedule.updated_at = datetime.utcnow()
        await db.commit()
        return {"status": "updated", "schedule_context": ctx}

    async def update_preferences(self, user_id: str, preferences: dict, db: AsyncSession) -> dict:
        """Update schedule preferences for a user (stored on active schedule)"""
        user_uuid = UUID(user_id)
        result = await db.execute(
            select(UserSchedule).where((UserSchedule.user_id == user_uuid) & (UserSchedule.is_active == True))
        )
        schedule = result.scalar_one_or_none()
        if schedule:
            schedule.preferences = preferences
            schedule.updated_at = datetime.utcnow()
            await db.commit()
        else:
            user = await db.get(User, user_uuid)
            if user:
                user.schedule_preferences = preferences
                user.updated_at = datetime.utcnow()
                await db.commit()
        return {"message": "Preferences updated"}

    # --- helpers ---

    async def _build_user_context(self, db: AsyncSession, user_id: str, course_id: str) -> str:
        lines: list[str] = []
        user_uuid = UUID(user_id)
        course_uuid = UUID(course_id)

        result = await db.execute(
            select(UserSchedule)
            .where(
                (UserSchedule.user_id == user_uuid) &
                (UserSchedule.course_id == course_uuid) &
                (UserSchedule.is_active == False)
            )
            .order_by(UserSchedule.created_at.desc())
            .limit(3)
        )
        past_schedules = result.scalars().all()

        past_feedback = []
        for sched in past_schedules:
            stats = sched.completion_stats or {}
            total = stats.get("total", 0)
            completed = stats.get("completed", 0)
            if total > 0:
                lines.append(f"Past schedule: {completed}/{total} tasks completed ({round(completed/total*100)}%)")
            for fb in (sched.user_feedback or []):
                past_feedback.append(fb.get("feedback", ""))

        if past_feedback:
            lines.append(f"Past feedback: {'; '.join(past_feedback[:5])}")

        latest_scan_result = await db.execute(
            select(Scan).where(Scan.user_id == user_uuid).order_by(Scan.created_at.desc()).limit(1)
        )
        latest_scan = latest_scan_result.scalar_one_or_none()
        if latest_scan and latest_scan.analysis:
            metrics = (latest_scan.analysis or {}).get("metrics", {})
            jawline = metrics.get("jawline", {})
            if jawline:
                lines.append(f"User jawline score: {jawline.get('definition_score', 'N/A')}/10")
            overall = metrics.get("overall_score")
            if overall:
                lines.append(f"User overall face score: {overall}/10")

        user = await db.get(User, user_uuid)
        onboarding = (user.onboarding if user else {}) or {}
        if onboarding:
            profile_parts = []
            if onboarding.get("gender"): profile_parts.append(f"Gender: {onboarding['gender']}")
            if onboarding.get("age"): profile_parts.append(f"Age: {onboarding['age']}")
            if onboarding.get("height"): profile_parts.append(f"Height: {onboarding['height']}cm")
            if onboarding.get("weight"): profile_parts.append(f"Weight: {onboarding['weight']}kg")
            if profile_parts:
                lines.append("## PHYSICAL PROFILE")
                lines.append(", ".join(profile_parts))

            if onboarding.get("activity_level"):
                lines.append(f"Activity Level: {onboarding['activity_level']}")
            if onboarding.get("equipment"):
                lines.append(f"Available Equipment: {', '.join(onboarding['equipment'])}")
            if onboarding.get("skin_type"):
                lines.append(f"Skin Type: {onboarding['skin_type']}")

        if lines:
            return "\n## USER CONTEXT & HISTORY\n" + "\n".join(lines)
        return "\nNo prior history available — this is the user's first schedule."

    def _generate_fallback_schedule(self, module: dict, num_days: int, wake_time: str) -> dict:
        guidelines = module.get("guidelines", {}) or {}
        exercises = guidelines.get("exercises", ["General exercise"])

        days = []
        for day_num in range(1, num_days + 1):
            tasks = []
            tasks.append({
                "task_id": str(uuid.uuid4()),
                "time": wake_time,
                "title": f"Morning {exercises[0] if exercises else 'Exercise'}",
                "description": f"Start your day with a {exercises[0].lower() if exercises else 'exercise'} session.",
                "task_type": "exercise",
                "duration_minutes": 15 + (day_num * 2),
            })
            tasks.append({
                "task_id": str(uuid.uuid4()),
                "time": "18:00",
                "title": f"Evening {exercises[-1] if exercises else 'Exercise'}",
                "description": f"End your day strong with {exercises[-1].lower() if exercises else 'exercise'}.",
                "task_type": "exercise",
                "duration_minutes": 15 + (day_num * 2),
            })
            days.append({
                "day_number": day_num,
                "tasks": tasks,
                "motivation_message": f"Day {day_num} — keep pushing!",
            })

        return {"days": days}

    async def _load_schedule(self, schedule_id: str, user_id: str, db: AsyncSession) -> Optional[UserSchedule]:
        try:
            schedule_uuid = UUID(schedule_id)
        except ValueError:
            return None
        schedule = await db.get(UserSchedule, schedule_uuid)
        if schedule and schedule.user_id == UUID(user_id):
            return schedule
        return None

    def _schedule_to_dict(self, schedule: UserSchedule) -> dict:
        d = {
            "id": str(schedule.id),
            "user_id": str(schedule.user_id),
            "schedule_type": schedule.schedule_type or "course",
            "course_id": str(schedule.course_id) if schedule.course_id else None,
            "course_title": schedule.course_title,
            "module_number": schedule.module_number,
            "maxx_id": schedule.maxx_id,
            "days": schedule.days or [],
            "preferences": schedule.preferences or {},
            "schedule_context": schedule.schedule_context or {},
            "is_active": schedule.is_active,
            "created_at": schedule.created_at,
            "adapted_count": schedule.adapted_count or 0,
        }
        return d


schedule_service = ScheduleService()
