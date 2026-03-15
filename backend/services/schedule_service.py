"""
Schedule Service - AI-powered personalised schedule generation using Gemini
Generates, adapts, and manages user schedules for course modules.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from zoneinfo import ZoneInfo
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from services.gemini_service import GeminiService
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

Return ONLY valid JSON with the updated "days" array.
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

    async def adapt_schedule(self, user_id: str, schedule_id: str, db: AsyncSession, feedback: str) -> dict:
        schedule = await self._load_schedule(schedule_id, user_id, db)
        if not schedule:
            raise ValueError("Schedule not found")

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

        schedule.days = adapted.get("days", schedule.days)
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

        return self._schedule_to_dict(schedule)

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
        schedule.updated_at = datetime.utcnow()
        await db.commit()
        return {"status": "deleted"}

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
        return {
            "id": str(schedule.id),
            "user_id": str(schedule.user_id),
            "course_id": str(schedule.course_id),
            "course_title": schedule.course_title,
            "module_number": schedule.module_number,
            "days": schedule.days or [],
            "preferences": schedule.preferences or {},
            "is_active": schedule.is_active,
            "created_at": schedule.created_at,
            "adapted_count": schedule.adapted_count or 0,
        }


schedule_service = ScheduleService()
