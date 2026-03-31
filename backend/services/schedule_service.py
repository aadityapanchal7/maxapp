"""
Schedule Service - AI-powered personalised schedule generation using Gemini
Generates, adapts, and manages user schedules for course modules.
"""

import asyncio
import copy
import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Optional, List
from zoneinfo import ZoneInfo
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from config import settings
from services.llm_sync import sync_llm_json_response
from services.prompt_loader import PromptKey, resolve_prompt
from services.guideline_service import (
    get_maxx_guideline_async,
    resolve_concern,
    build_protocol_prompt_section,
    build_heightmax_protocol_section,
)
from services.maxx_guidelines import (
    build_bonemax_prompt_section,
    build_fitmax_prompt_section,
    build_hairmax_prompt_section,
    build_heightmax_prompt_section,
    build_skinmax_prompt_section,
)
from models.sqlalchemy_models import User, UserSchedule, Scan
from services.schedule_streak import sync_master_schedule_streak
from models.rds_models import Course

logger = logging.getLogger(__name__)

MAX_ACTIVE_SCHEDULES = 2

# Default horizon for new schedules (~1 month). LLM + fallbacks must repeat weekly/biweekly
# checkpoints across all generated days, not only in week 1.
DEFAULT_MAXX_SCHEDULE_DAYS = 30
DEFAULT_COURSE_SCHEDULE_DAYS = 30


class ScheduleLimitError(Exception):
    """Raised when the user already has the maximum number of active schedules."""

    def __init__(self, active_labels: list[str]):
        self.active_labels = active_labels
        names = ", ".join(active_labels)
        super().__init__(
            f"You already have {len(active_labels)} active module{'s' if len(active_labels) != 1 else ''} ({names}). "
            f"Stop one before starting a new one."
        )


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
1. Create a schedule for {num_days} days (include every day 1…{num_days}). If {num_days} > 7, repeat **weekly** checkpoints (e.g. weigh-in, wash day, progress photo) on the same weekday each week, and **bi-weekly** items every 14 days — not only in the first week.
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
- If the user runs multiple active modules, avoid adding duplicate generic morning/midday wake-style tasks at the same clock time as before; stagger or merge intent into concrete tasks.
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
{height_track_footer}

## USER CONTEXT
Wake time: {wake_time}
Sleep time: {sleep_time}
Profile hint: {profile_hint}
Selected concern: {selected_concern}
Outside today: {outside_today}
{user_profile_context}

{multi_module_instruction}

## PERSONALIZATION (HeightMax)
When building a HeightMax schedule, USE the user's age, sex, and height from USER CONTEXT:
- Age: affects growth-plate status (adults vs teens), recovery needs, and intensity
- Sex: affects typical frame, hormone context, and protocol emphasis
- Height: affects baseline and goal framing
Personalize task types, timing, and messaging accordingly.

## PERSONALIZATION (BoneMax)
When building a BoneMax schedule, USE the BoneMax profile lines in USER CONTEXT (workout frequency, TMJ history, mastic gum experience, heavy screen time):
- TMJ / jaw issues → conservative masseter and neck intensity; avoid stacking hard jaw work
- Heavy screen time → extra midday oral-posture / neck resets
- Higher workout days/week → place neck training after training days where possible
- Gum beginners → shorter mastic sessions with same form rules

## MINIMUM TASKS PER DAY — MANDATORY (do NOT generate fewer)

**Skinmax:** minimum **3** tasks/day (AM routine, midday micro-tip, PM routine). Typical day has **4–5** tasks when including SPF reapply and/or hydration check. Weekly adds exfoliation (replaces PM on chosen day) + pillowcase (Sunday). Monthly: progress photo + check-in on the 1st.

**HairMax (thinning/minoxidil stack):** minimum **4** tasks/day (finasteride, minoxidil AM, minoxidil PM, daily scalp micro-tip). Typical day has **4–5** tasks. Weekly: ketoconazole 2–3x/week on wash days; microneedling 1×/week (after month 4). Bi-weekly: progress photos. Monthly: check-in on the 1st.

**HairMax (non-thinning):** minimum **3** tasks/day (wash routine reminder or oil/mask on treatment days, daily scalp micro-tip, PM hair care). Weekly: wash day tasks per hair type frequency.

**HeightMax:** minimum **4** tasks/day (morning decompression, midday posture, evening decompression, sleep GH protocol). Typical: **5–7** with sprint days, nutrition, measurements.

**BoneMax:** minimum **4** tasks/day (mewing morning, midday oral posture, masseter/chew, mewing night). Typical: **5–7** with fascia, neck, nutrition, symmetry.

**FitMax:** minimum **3** tasks on rest days (morning nutrition, midday tip, evening closeout). Workout days: **5–6** (add pre-workout, post-workout, supplements). Weekly: weigh-in. Monthly: body check.

CRITICAL: If the notification engine reference specifies particular tasks as MANDATORY DAILY (e.g. Skinmax AM + midday + PM, or HairMax minoxidil AM + PM), you MUST include them every single day. A schedule with only 1–2 tasks/day is WRONG — go back and re-read the notification engine reference and add all required tasks.

## MULTI-WEEK CADENCE (REQUIRED — you are generating **{num_days}** consecutive days)

`day_number` 1 = first calendar day (today in the user's timezone). **Do not** pack weekly/biweekly/monthly items only into days 1–7; repeat them on the correct **weekdays and calendar dates** through day {num_days}.

- **Skinmax:** Exfoliation PM on the user's exfoliation weekday **every week** in range. Sunday midday: pillowcase line (or merge into Sunday tip). **Every calendar 1st** in range: progress photo (midday) + routine check-in (PM + 30 min).
- **HairMax (thinning stack):** Ketoconazole **2–3×/week** on fixed wash weekdays throughout. Microneedling **once per week** on the user's microneedling weekday (not same night as minoxidil); omit until month 4+ if ramp says so. **Bi-weekly progress photos** (e.g. every 14 days from day 1). **Every 1st:** monthly check-in (midday).
- **HairMax (non-thinning):** Wash / treatment days on a repeating weekly pattern matching hair-type frequency.
- **HeightMax:** Sprint pattern and **weekly height measure** on the same weekday each week (e.g. Sunday). **Every 1st:** monthly review when in range.
- **BoneMax:** **Weekly** checkpoint (e.g. Monday): front/side progress snap or symmetry review. **Every 1st:** monthly bone check when in range.
- **FitMax:** **Weekly weigh-in** on the same weekday each week. **Every 1st:** monthly body check when phase allows.

Use `task_type` **`checkpoint`** for weekly/biweekly/monthly items. Keep descriptions short if needed so JSON stays valid for long horizons.

## INSTRUCTIONS
1. Create a schedule for {num_days} days (include **every** day from 1 through {num_days} in the `days` array).
2. Use the protocol and schedule rules for this maxx, not skincare assumptions unless the protocol explicitly says so.
3. Schedule morning tasks shortly after wake time and evening tasks with enough runway before sleep to actually get done.
4. Spread weekly or higher-intensity tasks across different days, and **repeat** them each week (or every 14 days for bi-weekly) across the full {num_days}-day window.
5. If the protocol involves outside exposure reminders, only add them when outside_today is true (Skinmax: follow outdoor_frequency rules in the Skinmax notification engine — not the same as this bullet for other maxxes).
6. Morning entry: follow MULTI-ACTIVE-MODULES above. If none, include one short morning check-in at wake time; if multi-module rules apply, do NOT duplicate a generic wake/good-morning SMS—stagger or use the first concrete task only. **Exception — Skinmax:** do NOT add a generic wake check-in; the AM routine at wake+15 is the first ping (unless another active module already owns wake — then stagger per MULTI-ACTIVE-MODULES). **Exception — BoneMax:** mewing morning reset at **wake** is the first ping. **Exception — HeightMax:** morning decompression at **wake+20** is the first HeightMax ping (merge with other modules per cross-module instructions when needed). **Exception — HairMax (thinning stack):** do NOT use a generic wake-only check-in; first pings are **finasteride (if oral path)** and/or **minoxidil at wake+15** per ramp phase (merge AM with Skinmax per HAIRMAX+SKINMAX when both active). **Exception — FitMax:** do NOT use a generic wake-only check-in; first daily FitMax anchor is **morning nutrition at wake+30** (merge with Skinmax AM when both active); on workout days add **pre-workout at workout−30m** (not a duplicate wake ping).
7. Each task must have: task_id (uuid), time (HH:MM in 24h), title, description, task_type (routine/reminder/checkpoint), duration_minutes.
8. task_type "routine" = core habit block, "reminder" = cue or anti-habit push, "checkpoint" = weekly treatment, harder session, or review.
9. Keep daily routines consistent but vary weekly treatments, sprint sessions, and review tasks across days.
10. Avoid stacking duplicate notification intent at the same clock time as generic pings the user may already get from another module (the system dedupes SMS, but schedules should still be sensible).
11. Include brief motivational messages for each day.
12. **IMPORTANT:** Every day MUST have at least the minimum number of tasks specified above. Read the NOTIFICATION ENGINE reference and include ALL mandatory daily tasks it lists. Short schedules with 1–2 tasks/day are wrong.
13. Task descriptions should include specific product names, step-by-step instructions, or actionable copy from the notification engine reference — not vague one-liners.
14. **SMS / push tone:** Titles and descriptions are used as the basis for text reminders. Write like a casual text from Max — not a dashboard. **Do not** use stiff patterns like `Category: Name — 2:22pm` or `Midday Tip: Hydration Goal` in titles. Prefer short titles (e.g. `water check`, `PM routine`, `sprint warm-up`) and put the real detail in **description** as plain, conversational sentences (lowercase ok). The app shows exact times; SMS will prefix something like `around 2:22pm — …`.

## OUTPUT FORMAT
Return ONLY valid JSON matching this structure (no markdown fences).
Each day should have **at least 3–5 tasks** (more for full-stack modules). The example below is abbreviated — your actual output must include ALL mandatory daily tasks per the notification engine reference.

{{
  "days": [
    {{
      "day_number": 1,
      "tasks": [
        {{
          "task_id": "uuid-string",
          "time": "07:15",
          "title": "AM Skincare Routine",
          "description": "(1) CeraVe Foaming Cleanser (2) Paula's Choice 2% BHA — thin layer, dry 2 min (3) CeraVe Daily Lotion (4) EltaMD UV Clear SPF 46",
          "task_type": "routine",
          "duration_minutes": 12
        }},
        {{
          "task_id": "uuid-string",
          "time": "10:15",
          "title": "SPF Reapply",
          "description": "Reapply SPF — 3h since AM. Especially important if outdoors.",
          "task_type": "reminder",
          "duration_minutes": 3
        }},
        {{
          "task_id": "uuid-string",
          "time": "14:37",
          "title": "Midday Micro-Tip",
          "description": "Hands off face. Every touch transfers bacteria and oils.",
          "task_type": "reminder",
          "duration_minutes": 1
        }},
        {{
          "task_id": "uuid-string",
          "time": "16:37",
          "title": "Hydration Check",
          "description": "Water check — ~3L target today. Hydration supports skin barrier.",
          "task_type": "reminder",
          "duration_minutes": 1
        }},
        {{
          "task_id": "uuid-string",
          "time": "22:00",
          "title": "PM Skincare — Retinoid Night",
          "description": "(1) CeraVe Foaming Cleanser (2) Differin 0.1% — pea-sized, thin layer (3) Wait 20 min (4) CeraVe PM Lotion",
          "task_type": "routine",
          "duration_minutes": 25
        }}
      ],
      "motivation_message": "Day 1 — consistency compounds. every AM + PM you don't skip is another day closer."
    }}
  ]
}}
"""


class ScheduleService:
    """AI-powered schedule generation and management"""

    def __init__(self):
        pass

    async def get_active_schedule_count(self, user_id: str, db: AsyncSession) -> tuple[int, list[str]]:
        """Return (count, list_of_labels) of all currently active schedules."""
        user_uuid = UUID(user_id)
        result = await db.execute(
            select(UserSchedule).where(
                (UserSchedule.user_id == user_uuid) & (UserSchedule.is_active == True)
            )
        )
        schedules = result.scalars().all()
        labels = []
        for s in schedules:
            label = getattr(s, "maxx_id", None) or getattr(s, "course_title", None) or "unknown"
            labels.append(label)
        return len(schedules), labels

    async def get_all_active_schedules(self, user_id: str, db: AsyncSession) -> list[dict]:
        """Return full schedule payloads for every active schedule (e.g. master week view)."""
        user_uuid = UUID(user_id)
        result = await db.execute(
            select(UserSchedule)
            .where((UserSchedule.user_id == user_uuid) & (UserSchedule.is_active == True))
            .order_by(UserSchedule.created_at.asc())
        )
        schedules = result.scalars().all()
        return [self._schedule_to_dict(s) for s in schedules]

    async def _enforce_schedule_limit(self, user_id: str, db: AsyncSession, replacing_maxx_id: str | None = None, replacing_course_module: tuple | None = None):
        """
        Raise ScheduleLimitError if adding a new schedule would exceed MAX_ACTIVE_SCHEDULES.
        Doesn't count the schedule being *replaced* (same maxx_id or same course+module).
        """
        user_uuid = UUID(user_id)
        result = await db.execute(
            select(UserSchedule).where(
                (UserSchedule.user_id == user_uuid) & (UserSchedule.is_active == True)
            )
        )
        active = result.scalars().all()
        filtered = []
        for s in active:
            if replacing_maxx_id and getattr(s, "maxx_id", None) == replacing_maxx_id:
                continue
            if replacing_course_module:
                cid, mnum = replacing_course_module
                if str(getattr(s, "course_id", "")) == cid and getattr(s, "module_number", None) == mnum:
                    continue
            filtered.append(s)
        if len(filtered) >= MAX_ACTIVE_SCHEDULES:
            labels = []
            for s in filtered:
                labels.append(getattr(s, "maxx_id", None) or getattr(s, "course_title", None) or "module")
            raise ScheduleLimitError(labels)

    async def deactivate_schedule(self, user_id: str, schedule_id: str, db: AsyncSession) -> dict:
        """Deactivate a specific schedule by ID."""
        user_uuid = UUID(user_id)
        sched_uuid = UUID(schedule_id)
        result = await db.execute(
            select(UserSchedule).where(
                (UserSchedule.id == sched_uuid) & (UserSchedule.user_id == user_uuid)
            )
        )
        schedule = result.scalar_one_or_none()
        if not schedule:
            raise ValueError("Schedule not found")
        schedule.is_active = False
        schedule.updated_at = datetime.utcnow()
        await db.commit()
        label = getattr(schedule, "maxx_id", None) or getattr(schedule, "course_title", None) or "schedule"
        return {"status": "stopped", "label": label}

    async def deactivate_schedule_by_maxx(self, user_id: str, maxx_id: str, db: AsyncSession) -> dict | None:
        """Deactivate the active schedule for a given maxx_id. Returns info dict or None."""
        user_uuid = UUID(user_id)
        result = await db.execute(
            select(UserSchedule).where(
                (UserSchedule.user_id == user_uuid) & (UserSchedule.maxx_id == maxx_id) & (UserSchedule.is_active == True)
            )
        )
        schedule = result.scalar_one_or_none()
        if not schedule:
            return None
        schedule.is_active = False
        schedule.updated_at = datetime.utcnow()
        await db.commit()
        return {"status": "stopped", "maxx_id": maxx_id}

    async def generate_schedule(
        self,
        user_id: str,
        course_id: str,
        module_number: int,
        db: AsyncSession,
        rds_db: AsyncSession,
        preferences: Optional[dict] = None,
        num_days: int = DEFAULT_COURSE_SCHEDULE_DAYS,
    ) -> dict:
        """Generate a personalised schedule for a user's course module."""
        await self._enforce_schedule_limit(
            user_id, db, replacing_course_module=(course_id, module_number)
        )
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
        if num_days == DEFAULT_COURSE_SCHEDULE_DAYS and guidelines.get("recommended_days"):
            num_days = guidelines["recommended_days"]

        gen_tmpl = await asyncio.to_thread(
            resolve_prompt, PromptKey.SCHEDULE_GENERATION, SCHEDULE_GENERATION_PROMPT
        )
        prompt = gen_tmpl.format(
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
            raw = await asyncio.to_thread(sync_llm_json_response, prompt)
            schedule_data = json.loads(raw)
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
        num_days: int = DEFAULT_MAXX_SCHEDULE_DAYS,
        override_age: Optional[int] = None,
        override_sex: Optional[str] = None,
        override_height: Optional[str] = None,
        override_hair_type: Optional[str] = None,
        override_scalp_state: Optional[str] = None,
        override_daily_styling: Optional[str] = None,
        override_thinning: Optional[str] = None,
        override_workout_frequency: Optional[str] = None,
        override_tmj_history: Optional[str] = None,
        override_mastic_gum_regular: Optional[str] = None,
        override_heavy_screen_time: Optional[str] = None,
        height_components: Optional[dict] = None,
    ) -> dict:
        """Generate a personalised recurring schedule for a maxx module."""
        await self._enforce_schedule_limit(user_id, db, replacing_maxx_id=maxx_id)
        if maxx_id == "heightmax" and height_components is not None and len(height_components) > 0:
            if not any(bool(v) for v in height_components.values()):
                raise ValueError("Select at least one height schedule component")

        guideline = await get_maxx_guideline_async(maxx_id, rds_db)
        if not guideline:
            raise ValueError(f"Unknown maxx: {maxx_id}")

        user_uuid = UUID(user_id)
        user = await db.get(User, user_uuid)
        onboarding = (user.onboarding if user else {}) or {}

        skin_type = onboarding.get("skin_type", "normal")
        protos = guideline.get("protocols") or {}
        if maxx_id == "bonemax":
            concern = "bonemax_stack"
        elif maxx_id == "heightmax":
            concern = "heightmax_multi"
        elif maxx_id == "fitmax":
            protos_fm = guideline.get("protocols") or {}
            if skin_concern and skin_concern in protos_fm:
                concern = skin_concern
            else:
                from services.fitmax_notification_engine import resolve_fitmax_phase

                concern = resolve_fitmax_phase(onboarding)
        else:
            concern = resolve_concern(guideline, skin_type, skin_concern)

        profile_hint = ""
        if maxx_id == "skinmax":
            profile_hint = skin_type
        elif maxx_id == "bonemax":
            profile_hint = "bonemax"
        elif maxx_id == "heightmax":
            profile_hint = "heightmax"
        elif maxx_id == "hairmax":
            profile_hint = concern or "hairmax"
        elif maxx_id == "fitmax":
            profile_hint = concern or "fitmax"
        else:
            profile_hint = onboarding.get("goal", "none")

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
        if maxx_id == "bonemax":
            wf = (override_workout_frequency or onboarding.get("bonemax_workout_frequency") or "").strip()
            tmj = (override_tmj_history or onboarding.get("bonemax_tmj_history") or "").strip()
            gum = (override_mastic_gum_regular or onboarding.get("bonemax_mastic_gum_regular") or "").strip()
            scr = (override_heavy_screen_time or onboarding.get("bonemax_heavy_screen_time") or "").strip()
            if wf:
                profile_parts.append(f"Workout days/week (band): {wf}")
            if tmj:
                profile_parts.append(f"TMJ / jaw pain / clicking history: {tmj}")
            if gum:
                profile_parts.append(f"Mastic or hard gum regularly: {gum}")
            if scr:
                profile_parts.append(f"Heavy computer/phone screen time: {scr}")
        if maxx_id == "heightmax":
            gp = onboarding.get("growth_plate_status") or onboarding.get("heightmax_growth_plate_status")
            if gp:
                profile_parts.append(f"Growth plate status: {gp}")
            hg = onboarding.get("heightmax_goal") or onboarding.get("height_goal")
            if hg:
                profile_parts.append(f"Height goal: {hg}")
            wds = onboarding.get("heightmax_workout_schedule") or onboarding.get("workout_days_time")
            if wds:
                profile_parts.append(f"Workout schedule: {wds}")
            if onboarding.get("heightmax_stretching_decompression") is not None:
                profile_parts.append(f"Already stretching/decompression: {onboarding.get('heightmax_stretching_decompression')}")
            sq = onboarding.get("heightmax_sleep_quality") or onboarding.get("sleep_quality")
            if sq:
                profile_parts.append(f"Sleep quality (self): {sq}")
            sh = onboarding.get("heightmax_screen_hours")
            if sh:
                profile_parts.append(f"Screen hours/day: {sh}")
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
            tier_h = onboarding.get("hairmax_treatment_tier") or onboarding.get("hair_treatment_tier")
            if tier_h is not None:
                profile_parts.append(f"Hair treatment tier: {tier_h}")
            if onboarding.get("hair_finasteride_sensitive") or onboarding.get("hairmax_fin_sensitive"):
                profile_parts.append("Finasteride: side-effect sensitive / concerned")
            if onboarding.get("hair_topical_fin_only") or onboarding.get("hairmax_topical_fin_only"):
                profile_parts.append("Hair stack: topical finasteride path (no oral)")
        if maxx_id == "fitmax":
            for key, lbl in (
                ("fitmax_body_fat_band", "Body fat band"),
                ("estimated_body_fat", "Estimated body fat"),
                ("fitmax_primary_goal", "Primary goal"),
                ("fitmax_training_experience", "Training experience"),
                ("fitmax_equipment", "Equipment"),
                ("available_equipment", "Equipment (alt)"),
                ("fitmax_workout_days_per_week", "Workout days/week"),
                ("workout_days_per_week", "Workout days/week (alt)"),
                ("fitmax_preferred_workout_time", "Preferred workout time"),
                ("preferred_workout_time", "Preferred workout time (alt)"),
                ("fitmax_diet_approach", "Diet approach"),
                ("dietary_approach", "Diet approach (alt)"),
            ):
                v = onboarding.get(key)
                if v is not None and str(v).strip() != "":
                    profile_parts.append(f"{lbl}: {v}")
            if onboarding.get("fitmax_supplements_opt_in") is not None:
                profile_parts.append(f"Supplements opt-in: {onboarding.get('fitmax_supplements_opt_in')}")
            if onboarding.get("fitmax_weeks_on_program") is not None:
                profile_parts.append(f"Weeks on program (phase-in): {onboarding.get('fitmax_weeks_on_program')}")
        user_profile_context = ", ".join(profile_parts) if profile_parts else "No profile data yet."

        other_active_result = await db.execute(
            select(UserSchedule).where(
                (UserSchedule.user_id == user_uuid)
                & (UserSchedule.is_active == True)
                & (UserSchedule.maxx_id != maxx_id)
            )
        )
        other_active = list(other_active_result.scalars().all())
        other_maxx_ids = [str(o.maxx_id) for o in other_active if o.maxx_id]
        if other_active:
            labels = [str(o.maxx_id or o.course_title or "module") for o in other_active]
            multi_module_instruction = (
                "## MULTI-ACTIVE-MODULES\n"
                f"The user already has other active module(s): {', '.join(labels)}.\n"
                "- Do NOT add another generic \"morning check-in\", \"good morning\", or \"let me know you're awake\" SMS in the same wake-time window — omit it or stagger at least 45 minutes from wake.\n"
                "- Prefer starting with this module's first concrete actionable habit so the user does not get redundant wake pings from two modules.\n"
                "- Avoid duplicate generic midday or evening check-in reminders; use task-specific copy instead.\n"
            )
        else:
            multi_module_instruction = ""
        if maxx_id == "bonemax" and "skinmax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## BONEMAX + SKINMAX\n"
                "Merge morning mewing reset + Skinmax AM into **one** notification when both would land near wake; "
                "merge mewing night check (bed−30) + Skinmax PM when both land in the pre-bed window. "
                "**Max 10 notifications/day** across modules — drop lowest-priority tasks first per BoneMax engine.\n"
            )
        elif maxx_id == "skinmax" and "bonemax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## SKINMAX + BONEMAX\n"
                "Prefer **one** merged morning block (mewing at wake + AM skincare) and **one** merged evening block when schedules overlap. "
                "Stay under **10** total daily notifications.\n"
            )
        if maxx_id == "heightmax" and "bonemax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## HEIGHTMAX + BONEMAX\n"
                "Merge **posture** notifications where exercises overlap; merge **evening sleep/posture** windows (bed−45 / bed−30) into one pre-bed block when possible; "
                "one combined **supplement** reminder if both stacks apply. **Max 10** notifications/day.\n"
            )
        elif maxx_id == "bonemax" and "heightmax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## BONEMAX + HEIGHTMAX\n"
                "Merge posture and pre-bed blocks per HeightMax + BoneMax engine; dedupe supplement meal pings.\n"
            )
        if maxx_id == "heightmax" and "fitmax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## HEIGHTMAX + FITMAX\n"
                "Sprint days can align with workout days; schedule **decompression** after heavy axial lifting days; **max 10** notifications/day.\n"
            )
        elif maxx_id == "fitmax" and "heightmax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## FITMAX + HEIGHTMAX\n"
                "Respect HeightMax sprint + decompression timing around logged workouts; cap total daily notifications at **10**.\n"
            )
        if maxx_id == "hairmax" and "skinmax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## HAIRMAX + SKINMAX\n"
                "Merge AM/PM routines: **scalp (minoxidil) first**, then skin steps with required wait times (15 min AM after minox; 30 min PM). "
                "**Never** scalp + face microneedling same day — stagger. **Max 10** notifications/day.\n"
            )
        elif maxx_id == "skinmax" and "hairmax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## SKINMAX + HAIRMAX\n"
                "Coordinate timing with minoxidil; one merged morning/evening block when possible. Stagger microneedling days. Cap **10**/day.\n"
            )
        if maxx_id == "fitmax" and "bonemax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## FITMAX + BONEMAX\n"
                "Neck work lives in **BoneMax** — remove neck prescriptions from FitMax workouts. "
                "Replace FitMax **midday posture** tips with **training/nutrition** tips (BoneMax owns posture). **Face pulls** stay in FitMax. Cap **10**/day.\n"
            )
        elif maxx_id == "bonemax" and "fitmax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## BONEMAX + FITMAX\n"
                "User lifts with FitMax — coordinate neck training with workout days; FitMax must not duplicate neck volume. Cap **10**/day.\n"
            )
        if maxx_id == "fitmax" and "skinmax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## FITMAX + SKINMAX\n"
                "Merge **wake+30** FitMax morning nutrition with Skinmax AM into **one** notification when possible.\n"
            )
        elif maxx_id == "skinmax" and "fitmax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## SKINMAX + FITMAX\n"
                "Merge morning blocks when times align; midday may note leanness → lower inflammation → clearer skin. Cap **10**/day.\n"
            )
        if maxx_id == "fitmax" and "hairmax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## FITMAX + HAIRMAX\n"
                "**Creatine** reminders: add hair/DHT caveat for users predisposed to loss. Cap **10**/day.\n"
            )
        elif maxx_id == "hairmax" and "fitmax" in other_maxx_ids:
            multi_module_instruction += (
                "\n## HAIRMAX + FITMAX\n"
                "If creatine is mentioned in FitMax stack, respect hair-priority user choice. Cap **10**/day.\n"
            )

        if maxx_id == "heightmax":
            tracks_body = build_heightmax_protocol_section(guideline, height_components)
            active_labels: List[str] = []
            if height_components:
                for k, p in protos.items():
                    if height_components.get(k, True) and isinstance(p, dict):
                        active_labels.append(p.get("label", k))
            else:
                for k, p in protos.items():
                    if isinstance(p, dict):
                        active_labels.append(p.get("label", k))
            if active_labels:
                height_track_footer = (
                    "\n## HEIGHTMAX — ENABLED TRACKS ONLY\n"
                    "Only schedule tasks, reminders, and checkpoints that belong to these user-selected tracks. "
                    "Do not add tasks for tracks the user did not select.\n"
                    f"Enabled tracks: {', '.join(active_labels)}.\n"
                )
            else:
                height_track_footer = ""
            protocol_section = build_heightmax_prompt_section(
                tracks_protocol_text=tracks_body,
                height_track_footer=height_track_footer,
                onboarding=onboarding,
                wake_time=wake_time,
                sleep_time=sleep_time,
                age_val=age_val if override_age is not None else onboarding.get("age"),
                other_active_maxx_ids=other_maxx_ids,
            )
            height_track_footer = ""
        elif maxx_id == "skinmax":
            protocol_section = build_skinmax_prompt_section(
                concern,
                onboarding=onboarding,
                wake_time=wake_time,
                sleep_time=sleep_time,
                outside_today=outside_today,
            )
            height_track_footer = ""
        elif maxx_id == "bonemax":
            protocol_section = build_bonemax_prompt_section(
                guideline,
                onboarding=onboarding,
                wake_time=wake_time,
                sleep_time=sleep_time,
                other_active_maxx_ids=other_maxx_ids,
            )
            height_track_footer = ""
        elif maxx_id == "hairmax":
            protocol_section = build_hairmax_prompt_section(
                concern,
                onboarding=onboarding,
                wake_time=wake_time,
                sleep_time=sleep_time,
                other_active_maxx_ids=other_maxx_ids,
            )
            height_track_footer = ""
        elif maxx_id == "fitmax":
            protocol_section = build_fitmax_prompt_section(
                concern,
                guideline,
                onboarding=onboarding,
                wake_time=wake_time,
                sleep_time=sleep_time,
                other_active_maxx_ids=other_maxx_ids,
            )
            height_track_footer = ""
        else:
            protocol_section = build_protocol_prompt_section(guideline, concern)
            height_track_footer = ""

        maxx_tmpl = await asyncio.to_thread(
            resolve_prompt, PromptKey.MAXX_SCHEDULE, MAXX_SCHEDULE_PROMPT
        )
        prompt = maxx_tmpl.format(
            maxx_label=guideline["label"],
            protocol_section=protocol_section,
            height_track_footer=height_track_footer,
            wake_time=wake_time,
            sleep_time=sleep_time,
            profile_hint=profile_hint,
            selected_concern=concern,
            outside_today="Yes" if outside_today else "No",
            user_profile_context=user_profile_context,
            num_days=num_days,
            multi_module_instruction=multi_module_instruction,
        )

        tz_name = onboarding.get("timezone", "UTC")
        try:
            user_tz = ZoneInfo(tz_name)
        except Exception:
            user_tz = ZoneInfo("UTC")
        start_date = datetime.now(user_tz).date()

        try:
            raw = await asyncio.to_thread(sync_llm_json_response, prompt)
            schedule_data = json.loads(raw)
        except Exception as e:
            logger.error(f"Gemini maxx schedule generation failed: {e}")
            schedule_data = self._generate_maxx_fallback(
                maxx_id,
                num_days,
                wake_time,
                sleep_time,
                height_components,
                outside_today=outside_today,
                onboarding=onboarding,
                start_date=start_date,
                hair_concern=concern if maxx_id == "hairmax" else None,
                other_maxx_ids=other_maxx_ids,
            )
        else:
            if maxx_id == "skinmax":
                self._augment_skinmax_llm_schedule(
                    schedule_data,
                    onboarding=onboarding or {},
                    wake_time=wake_time,
                    sleep_time=sleep_time,
                    outside_today=outside_today,
                    start_date=start_date,
                )
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

        start_date_iso = start_date.isoformat()
        sched_ctx = {
            "selected_concern": concern,
            "skin_concern": concern,
            "skin_type": skin_type,
            "outside_today": outside_today,
            "outside_today_date": start_date_iso,
            "wake_time": wake_time,
            "sleep_time": sleep_time,
        }
        if maxx_id == "skinmax":
            for key in (
                "outdoor_frequency",
                "routine_level",
                "secondary_skin_concern",
                "dietary_restrictions",
                "skin_hydration_notifications",
                "exfoliation_weekday",
                "retinoid_start_date",
                "barrier_repair_started_at",
            ):
                if onboarding.get(key) is not None:
                    sched_ctx[key] = onboarding[key]
        if maxx_id == "bonemax":
            sched_ctx.update(
                {
                    "bonemax_workout_frequency": (override_workout_frequency or onboarding.get("bonemax_workout_frequency") or ""),
                    "bonemax_tmj_history": (override_tmj_history or onboarding.get("bonemax_tmj_history") or ""),
                    "bonemax_mastic_gum_regular": (override_mastic_gum_regular or onboarding.get("bonemax_mastic_gum_regular") or ""),
                    "bonemax_heavy_screen_time": (override_heavy_screen_time or onboarding.get("bonemax_heavy_screen_time") or ""),
                }
            )
            for key in (
                "bonemax_workout_schedule",
                "bonemax_screen_hours",
                "bonemax_sleep_position",
                "bonemax_current_habits",
                "bonemax_meal_chewing_reminders",
                "bonemax_bone_nutrition_opt_in",
                "bonemax_hard_mewing",
                "bonemax_mouth_breather",
                "bonemax_weeks_on_routine",
                "bonemax_masseter_time",
            ):
                if onboarding.get(key) is not None:
                    sched_ctx[key] = onboarding[key]
        if maxx_id == "heightmax":
            if height_components is not None:
                sched_ctx["height_components"] = {str(k): bool(v) for k, v in height_components.items()}
            for key in (
                "growth_plate_status",
                "heightmax_growth_plate_status",
                "heightmax_goal",
                "height_goal",
                "heightmax_workout_schedule",
                "heightmax_workout_time",
                "heightmax_stretching_decompression",
                "heightmax_sleep_quality",
                "heightmax_screen_hours",
                "heightmax_height_nutrition_opt_in",
                "heightmax_weeks_on_routine",
            ):
                if onboarding.get(key) is not None:
                    sched_ctx[key] = onboarding[key]
        if maxx_id == "hairmax":
            for key in (
                "hairmax_treatment_tier",
                "hair_treatment_tier",
                "hair_finasteride_sensitive",
                "hairmax_fin_sensitive",
                "hair_topical_fin_only",
                "hairmax_topical_fin_only",
                "hairmax_fin_dose_preference",
                "hairmax_budget_band",
                "hairmax_microneedling_weekday",
                "hairmax_microneedling_time",
                "hair_shed_tracking_opt_in",
                "hair_fin_start_date",
                "hairmax_months_on_treatment",
            ):
                if onboarding.get(key) is not None:
                    sched_ctx[key] = onboarding[key]
        if maxx_id == "fitmax":
            for key in (
                "fitmax_body_fat_band",
                "fitmax_primary_goal",
                "fitmax_training_experience",
                "fitmax_equipment",
                "fitmax_workout_days_per_week",
                "fitmax_preferred_workout_time",
                "fitmax_diet_approach",
                "fitmax_supplements_opt_in",
                "fitmax_weeks_on_program",
            ):
                if onboarding.get(key) is not None:
                    sched_ctx[key] = onboarding[key]

        schedule_row = UserSchedule(
            user_id=user_uuid,
            schedule_type="maxx",
            maxx_id=maxx_id,
            course_title=guideline["label"],
            days=schedule_data.get("days", []),
            preferences=prefs,
            schedule_context=sched_ctx,
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

    def _augment_skinmax_llm_schedule(
        self,
        schedule_data: dict,
        *,
        onboarding: dict,
        wake_time: str,
        sleep_time: str,
        outside_today: bool,
        start_date: date,
    ) -> None:
        """
        Skinmax LLM output often returns only AM / midday / PM. Enrich with engine slots
        (hydration, SPF / outdoor prompt, dietary nudge, monthly checkpoints) when missing.
        """
        from services.skinmax_notification_engine import (
            add_minutes_to_clock,
            add_minutes_to_wake_clock,
            get_skinmax_slot_times,
            skinmax_dietary_restriction_keys,
            skinmax_midday_tip_for_weekday,
            skinmax_restriction_reminder_body,
        )

        days = schedule_data.get("days")
        if not isinstance(days, list):
            return

        ob = onboarding or {}
        slots = get_skinmax_slot_times(wake_time, sleep_time)
        freq = str(ob.get("outdoor_frequency", "sometimes")).lower()
        hydration_on = ob.get("skin_hydration_notifications", True)
        if hydration_on is None:
            hydration_on = True
        restriction_keys = skinmax_dietary_restriction_keys(ob)

        def tmin(t: str) -> int:
            p = str(t).strip().split(":")
            return int(p[0]) * 60 + int(p[1][:2])

        def near_slot(task_time: str, slot: str, win: int = 50) -> bool:
            return abs(tmin(task_time) - tmin(slot)) <= win

        def day_blob(ts: list) -> str:
            parts = []
            for x in ts:
                if not isinstance(x, dict):
                    continue
                parts.append(str(x.get("title", "")))
                parts.append(str(x.get("description", "")))
            return " ".join(parts).lower()

        for day in days:
            if not isinstance(day, dict):
                continue
            tasks = day.get("tasks")
            if not isinstance(tasks, list):
                day["tasks"] = []
                tasks = day["tasks"]

            try:
                dn = int(day.get("day_number") or 1)
            except (TypeError, ValueError):
                dn = 1
            d = start_date + timedelta(days=dn - 1)
            wd = d.weekday()
            blob = day_blob(tasks)

            # 1) Midday: engine tip + Sunday pillowcase line
            mid_slot = slots["midday_tip"]
            mid_idx = -1
            best = 9999
            for i, x in enumerate(tasks):
                if not isinstance(x, dict):
                    continue
                tt = x.get("time") or "12:00"
                gap = abs(tmin(tt) - tmin(mid_slot))
                if gap < best:
                    best = gap
                    mid_idx = i
            if mid_idx >= 0 and best <= 90:
                tip = skinmax_midday_tip_for_weekday(wd)
                if wd == 6:
                    tip += (
                        " Also: change your pillowcase today if you haven't this week — "
                        "keeps oil and bacteria off your face."
                    )
                t0 = tasks[mid_idx]
                desc = str(t0.get("description") or "").strip()
                generic = len(desc) < 55 or "tip of the day" in desc.lower()
                if generic:
                    t0["description"] = tip

            # 2) Hydration
            hyd = slots["hydration"]

            def _task_blob(x: dict) -> str:
                return f"{x.get('title', '')} {x.get('description', '')}".lower()

            has_hyd = any(
                k in blob for k in ("hydration", "water check", "~3l", "3l")
            ) or any(
                near_slot(x.get("time") or "", hyd)
                and any(w in _task_blob(x) for w in ("water", "hydrat", "3l", "drink"))
                for x in tasks
                if isinstance(x, dict)
            )
            if hydration_on and not has_hyd:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": hyd,
                        "title": "Skinmax — hydration check",
                        "description": "Water check — aim for ~3L today for barrier and glow.",
                        "task_type": "reminder",
                        "duration_minutes": 2,
                    }
                )
                blob = day_blob(tasks)

            # 3) SPF or "going outside" prompt
            spf_slot = slots["spf_reapply"]
            has_spf = any(k in blob for k in ("spf", "sunscreen", "reapply", "uv")) or any(
                near_slot(x.get("time") or "", spf_slot, 60)
                and any(k in _task_blob(x) for k in ("spf", "sun", "reapply", "uv"))
                for x in tasks
                if isinstance(x, dict)
            )
            has_outdoor_ask = "going outside" in blob or "outside today" in blob
            if freq == "rarely":
                pass
            elif freq == "always" or (freq == "sometimes" and outside_today):
                if not has_spf:
                    tasks.append(
                        {
                            "task_id": str(uuid.uuid4()),
                            "time": spf_slot,
                            "title": "Skinmax — SPF reapply",
                            "description": "Reapply SPF ~3h after your AM routine (per your outdoor plan).",
                            "task_type": "reminder",
                            "duration_minutes": 5,
                        }
                    )
                    blob = day_blob(tasks)
            elif freq == "sometimes" and not outside_today:
                if not has_spf and not has_outdoor_ask:
                    tasks.append(
                        {
                            "task_id": str(uuid.uuid4()),
                            "time": spf_slot,
                            "title": "Skinmax — going outside today?",
                            "description": (
                                "If yes, plan SPF reapply ~3h after AM. If not, you can skip an extra reapply."
                            ),
                            "task_type": "reminder",
                            "duration_minutes": 2,
                        }
                    )
                    blob = day_blob(tasks)

            # 4) Dietary restriction nudge (max 1/day)
            if restriction_keys:
                has_rest = any(
                    k in blob
                    for k in (
                        "nutrition nudge",
                        "igf-1",
                        "seed oil",
                        "dairy",
                        "added sugar",
                        "inflammatory",
                        "dietary restriction",
                    )
                )
                if not has_rest:
                    rk = restriction_keys[(dn - 1) % len(restriction_keys)]
                    meal_slots = [
                        add_minutes_to_wake_clock(wake_time, 60),
                        add_minutes_to_wake_clock(wake_time, 300),
                        add_minutes_to_wake_clock(wake_time, 540),
                    ]
                    st = meal_slots[(dn - 1) % 3]
                    tasks.append(
                        {
                            "task_id": str(uuid.uuid4()),
                            "time": st,
                            "title": "Skinmax — nutrition nudge",
                            "description": skinmax_restriction_reminder_body(rk),
                            "task_type": "reminder",
                            "duration_minutes": 2,
                        }
                    )
                    blob = day_blob(tasks)

            # 5) 1st of month: photo + check-in
            if d.day == 1:
                if "progress photo" not in blob and "monthly photo" not in blob:
                    photo_time = mid_slot
                    for x in tasks:
                        if not isinstance(x, dict):
                            continue
                        if near_slot(x.get("time") or "", mid_slot, 20) and (
                            "midday" in str(x.get("title", "")).lower()
                            or "tip" in str(x.get("title", "")).lower()
                        ):
                            photo_time = add_minutes_to_clock(mid_slot, 20)
                            break
                    tasks.append(
                        {
                            "task_id": str(uuid.uuid4()),
                            "time": photo_time,
                            "title": "Skinmax — monthly progress photo",
                            "description": "Same lighting/angle as last month — quick progress snapshot.",
                            "task_type": "reminder",
                            "duration_minutes": 3,
                        }
                    )
                    blob = day_blob(tasks)
                pm_slot = slots["pm_routine"]
                chk_time = add_minutes_to_clock(pm_slot, 30)
                if not any(
                    k in blob
                    for k in ("monthly check", "30-day", "30 day", "routine check-in", "how's your skin")
                ):
                    tasks.append(
                        {
                            "task_id": str(uuid.uuid4()),
                            "time": chk_time,
                            "title": "Skinmax — monthly check-in",
                            "description": "How's your skin vs last month? Note texture, breakouts, and barrier — adjust routine if needed.",
                            "task_type": "reminder",
                            "duration_minutes": 5,
                        }
                    )

            tasks.sort(key=lambda t: (t.get("time") or "00:00", t.get("title") or ""))

    def _generate_maxx_fallback(
        self,
        maxx_id: str,
        num_days: int,
        wake_time: str,
        sleep_time: str,
        height_components: Optional[dict] = None,
        *,
        outside_today: bool = False,
        onboarding: Optional[dict] = None,
        start_date: Optional[date] = None,
        hair_concern: Optional[str] = None,
        other_maxx_ids: Optional[list[str]] = None,
    ) -> dict:
        """Fallback schedule when Gemini fails for maxx schedules."""
        if maxx_id == "hairmax":
            sd = start_date if start_date is not None else datetime.now(ZoneInfo("UTC")).date()
            return self._generate_hairmax_fallback(
                num_days,
                wake_time,
                sleep_time,
                concern=hair_concern or "minoxidil",
                onboarding=onboarding or {},
                start_date=sd,
            )
        if maxx_id == "heightmax":
            sd = start_date if start_date is not None else datetime.now(ZoneInfo("UTC")).date()
            return self._generate_heightmax_fallback(
                num_days,
                wake_time,
                sleep_time,
                height_components,
                onboarding=onboarding or {},
                start_date=sd,
            )
        if maxx_id == "bonemax":
            sd = start_date if start_date is not None else datetime.now(ZoneInfo("UTC")).date()
            return self._generate_bonemax_fallback(
                num_days,
                wake_time,
                sleep_time,
                onboarding=onboarding or {},
                start_date=sd,
            )
        if maxx_id == "fitmax":
            sd = start_date if start_date is not None else datetime.now(ZoneInfo("UTC")).date()
            return self._generate_fitmax_fallback(
                num_days,
                wake_time,
                sleep_time,
                onboarding=onboarding or {},
                start_date=sd,
                other_maxx_ids=other_maxx_ids or [],
            )
        if maxx_id == "skinmax":
            from services.skinmax_notification_engine import get_skinmax_slot_times

            sd = start_date if start_date is not None else datetime.now(ZoneInfo("UTC")).date()
            return self._generate_skinmax_fallback(
                num_days,
                get_skinmax_slot_times(wake_time, sleep_time),
                outside_today=outside_today,
                onboarding=onboarding or {},
                start_date=sd,
            )

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

    def _generate_skinmax_fallback(
        self,
        num_days: int,
        slots: dict,
        *,
        outside_today: bool,
        onboarding: dict,
        start_date: date,
    ) -> dict:
        """Deterministic Skinmax-shaped days when Gemini fails (engine-aligned slot times)."""
        from services.skinmax_notification_engine import add_minutes_to_clock

        ob = onboarding or {}
        freq = str(ob.get("outdoor_frequency", "sometimes")).lower()
        hydration_on = ob.get("skin_hydration_notifications", True)
        exfol_raw = ob.get("exfoliation_weekday", 2)
        if isinstance(exfol_raw, str):
            key = exfol_raw.strip().lower()[:3]
            dow_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
            exfol_dow = dow_map.get(key, 2)
        else:
            try:
                exfol_dow = int(exfol_raw) % 7
            except (TypeError, ValueError):
                exfol_dow = 2

        days: list = []
        for day_num in range(1, num_days + 1):
            d = start_date + timedelta(days=day_num - 1)
            wd = d.weekday()
            tasks: list = [
                {
                    "task_id": str(uuid.uuid4()),
                    "time": slots["am_routine"],
                    "title": "Skinmax — AM routine",
                    "description": "AM steps per your concern: cleanser → actives → moisturizer → SPF (see Skinmax protocol).",
                    "task_type": "routine",
                    "duration_minutes": 12,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": slots["midday_tip"],
                    "title": "Skinmax — midday micro-tip",
                    "description": "7-day rotation tip (hands off face, water, pillowcase, phone, stress, sunglasses, diet).",
                    "task_type": "reminder",
                    "duration_minutes": 2,
                },
            ]
            include_spf = freq == "always" or (freq == "sometimes" and outside_today)
            if include_spf:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["spf_reapply"],
                        "title": "Skinmax — SPF reapply",
                        "description": "Reapply SPF ~3h after AM routine (per outdoor plan).",
                        "task_type": "reminder",
                        "duration_minutes": 5,
                    }
                )
            if hydration_on:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["hydration"],
                        "title": "Skinmax — hydration check",
                        "description": "Water check — steady hydration supports skin barrier.",
                        "task_type": "reminder",
                        "duration_minutes": 1,
                    }
                )

            is_exfol = wd == exfol_dow
            tasks.append(
                {
                    "task_id": str(uuid.uuid4()),
                    "time": slots["pm_routine"],
                    "title": (
                        "Skinmax — weekly exfoliation (PM)"
                        if is_exfol
                        else "Skinmax — PM routine"
                    ),
                    "description": (
                        "Exfoliation night per your concern — no retinoid. Limit time, rinse, moisturize."
                        if is_exfol
                        else "PM: retinoid night OR rest night per ramp (cleanser → treatment → moisturizer)."
                    ),
                    "task_type": "routine",
                    "duration_minutes": 25 if is_exfol else 20,
                }
            )

            if d.day == 1:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["midday_tip"],
                        "title": "Skinmax — monthly progress photo",
                        "description": "Same lighting/angle as last month — quick snapshot.",
                        "task_type": "checkpoint",
                        "duration_minutes": 3,
                    }
                )
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": add_minutes_to_clock(slots["pm_routine"], 30),
                        "title": "Skinmax — monthly check-in",
                        "description": "Texture, breakouts, barrier — vs last month; tweak routine if needed.",
                        "task_type": "checkpoint",
                        "duration_minutes": 5,
                    }
                )

            tasks.sort(key=lambda t: t.get("time") or "00:00")
            days.append(
                {
                    "day_number": day_num,
                    "tasks": tasks,
                    "motivation_message": f"Day {day_num} — Skinmax fallback: engine times; weekly exfoliation + monthly 1st checkpoints when applicable.",
                }
            )

        return {"days": days}

    def _generate_fitmax_fallback(
        self,
        num_days: int,
        wake_time: str,
        sleep_time: str,
        *,
        onboarding: Optional[dict] = None,
        start_date: date,
        other_maxx_ids: Optional[list[str]] = None,
    ) -> dict:
        """Fallback FitMax — engine anchors, phase-in, workout pattern."""
        from services.fitmax_notification_engine import (
            POSTURE_TIPS_10,
            get_fitmax_slot_times,
            resolve_fitmax_phase,
        )

        def _parse_days_per_week(ob: dict) -> int:
            raw = ob.get("fitmax_workout_days_per_week") or ob.get("workout_days_per_week") or 4
            try:
                n = int(float(str(raw).strip().split()[0]))
            except (ValueError, IndexError):
                n = 4
            return max(3, min(6, n))

        def _workout_weekdays(n: int) -> set[int]:
            if n <= 3:
                return {0, 2, 4}
            if n == 4:
                return {0, 1, 3, 4}
            if n == 5:
                return {0, 1, 2, 3, 4}
            return {0, 1, 2, 3, 4, 5}

        def _split_labels(n: int, bonemax: bool) -> list[str]:
            if n <= 3:
                seq = ["Push + Shoulders", "Pull + Neck", "Legs + Core"]
                if bonemax:
                    seq[1] = "Pull + Upper back (neck in BoneMax)"
                return seq
            if n == 4:
                return [
                    "Upper (shoulder focus)",
                    "Lower + posterior",
                    "Upper (back focus)",
                    "Lower + core",
                ]
            return ["Push (delts + face pulls)", "Pull (lats + rear delts)", "Legs + core"]

        ob = onboarding or {}
        oids = other_maxx_ids or []
        bonemax = "bonemax" in oids
        heightmax = "heightmax" in oids

        wo = str(ob.get("fitmax_preferred_workout_time") or ob.get("preferred_workout_time") or "18:00").strip()[:5]
        if ":" not in wo or len(wo) < 4:
            wo = "18:00"

        dpw = _parse_days_per_week(ob)
        wdays = _workout_weekdays(dpw)
        labels = _split_labels(dpw, bonemax)

        raw_w = ob.get("fitmax_weeks_on_program")
        if raw_w is None or str(raw_w).strip() == "":
            weeks = 99
        else:
            try:
                weeks = max(1, int(raw_w))
            except (TypeError, ValueError):
                weeks = 99
        full_pm = weeks >= 3
        full_posture = weeks >= 5
        monthly_on = weeks >= 5

        supp = bool(ob.get("fitmax_supplements_opt_in"))
        duration = 75 if dpw >= 4 else 60
        slots = get_fitmax_slot_times(wake_time, sleep_time, wo, duration)
        phase = resolve_fitmax_phase(ob)
        phase_blurb = {
            "cut": "deficit + high protein",
            "lean_bulk": "small surplus, slow weight gain",
            "recomp": "maintenance calories, protein priority",
            "maintain": "hold composition, stay consistent",
        }.get(phase, "train + protein")

        diet = str(ob.get("fitmax_diet_approach") or ob.get("dietary_approach") or "").lower()
        no_track = any(x in diet for x in ("don't", "dont", "no track", "flex", "portion"))

        workout_idx = 0
        days: List[dict] = []
        for day_num in range(1, num_days + 1):
            d = start_date + timedelta(days=day_num - 1)
            wd = d.weekday()
            is_lift_day = wd in wdays
            tasks: List[dict] = []

            am_title = "FitMax — Morning nutrition"
            if supp and full_pm:
                am_title = "FitMax — Morning nutrition + supplements"
            if no_track:
                am_desc = (
                    "Portion method: palm protein, fist carbs, thumb fat each meal — 3–4 meals, lean protein every time."
                )
            else:
                am_desc = f"Phase **{phase}**: {phase_blurb}. Anchor protein at breakfast."
            if supp and full_pm:
                am_desc += " Creatine 5g (skip if hair-priority + HairMax — your call)."

            tasks.append(
                {
                    "task_id": str(uuid.uuid4()),
                    "time": slots["morning_nutrition"],
                    "title": am_title,
                    "description": am_desc,
                    "task_type": "routine",
                    "duration_minutes": 5,
                }
            )

            if full_pm:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["evening_nutrition"],
                        "title": "FitMax — Evening nutrition closeout",
                        "description": "Protein target met? Calories over/under? Quick log in chat.",
                        "task_type": "reminder",
                        "duration_minutes": 3,
                    }
                )

            if full_posture and not bonemax:
                tip = POSTURE_TIPS_10[(d.toordinal() + day_num) % len(POSTURE_TIPS_10)]
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["midday_posture"],
                        "title": "FitMax — Midday aesthetics tip",
                        "description": tip,
                        "task_type": "reminder",
                        "duration_minutes": 2,
                    }
                )
            elif full_posture and bonemax:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["midday_posture"],
                        "title": "FitMax — Training cue (BoneMax covers posture)",
                        "description": "Hit top of rep range? Next session add 2.5–5 lb on lateral raises / isolations.",
                        "task_type": "reminder",
                        "duration_minutes": 2,
                    }
                )

            if wd == 0:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["monday_weigh_in"],
                        "title": "FitMax — Weekly weigh-in",
                        "description": "After bathroom, before food, same clothes. Log to 0.1.",
                        "task_type": "checkpoint",
                        "duration_minutes": 5,
                    }
                )

            if d.day == 1 and monthly_on:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["monthly_body_check"],
                        "title": "FitMax — Monthly body check",
                        "description": "Photos (front/side/back + face front) + waist / shoulders / neck tape.",
                        "task_type": "checkpoint",
                        "duration_minutes": 15,
                    }
                )

            if is_lift_day:
                label = labels[workout_idx % len(labels)]
                workout_idx += 1
                pre_desc = (
                    f"Today: **{label}**. Face pulls every session; lateral raises — light, controlled, high reps."
                )
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["pre_workout"],
                        "title": f"FitMax — Pre-workout ({label})",
                        "description": pre_desc,
                        "task_type": "reminder",
                        "duration_minutes": 3,
                    }
                )
                post_desc = "Protein 30–50g within 2h. Log sets/reps if you haven't."
                if heightmax:
                    post_desc += " After squats/deadlifts: optional 2 min dead hang."
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["post_workout"],
                        "title": "FitMax — Post-workout",
                        "description": post_desc,
                        "task_type": "checkpoint",
                        "duration_minutes": 5,
                    }
                )

            tasks.sort(key=lambda t: t.get("time") or "00:00")
            days.append(
                {
                    "day_number": day_num,
                    "tasks": tasks,
                    "motivation_message": f"Day {day_num} — FitMax fallback ({phase}); engine timings + phase-in rules.",
                }
            )

        return {"days": days}

    def _generate_heightmax_fallback(
        self,
        num_days: int,
        wake_time: str,
        sleep_time: str,
        height_components: Optional[dict] = None,
        *,
        onboarding: Optional[dict] = None,
        start_date: date,
    ) -> dict:
        """Fallback HeightMax — heightmax_notification_engine slot math + track toggles."""

        from services.heightmax_notification_engine import get_heightmax_slot_times

        def _on(key: str) -> bool:
            if not height_components:
                return True
            return bool(height_components.get(key, True))

        def _sub_time(tstr: str, minutes: int) -> str:
            h, m = map(int, tstr.split(":"))
            total = h * 60 + m - minutes
            total %= 24 * 60
            return f"{total // 60:02d}:{total % 60:02d}"

        def _add_time(tstr: str, minutes: int) -> str:
            h, m = map(int, tstr.split(":"))
            total = h * 60 + m + minutes
            total %= 24 * 60
            return f"{total // 60:02d}:{total % 60:02d}"

        ob = onboarding or {}
        slots = get_heightmax_slot_times(wake_time, sleep_time)
        workout_t = (ob.get("heightmax_workout_time") or "18:00").strip()[:5]
        if ":" not in workout_t:
            workout_t = "18:00"
        sprint_pre = _sub_time(workout_t, 30)
        sprint_post = _add_time(workout_t, 60)
        high_screen = False
        scr = str(ob.get("heightmax_screen_hours") or ob.get("bonemax_heavy_screen_time") or "")
        m_scr = re.search(r"(\d+)", scr)
        if m_scr and int(m_scr.group(1)) >= 6:
            high_screen = True
        nutrition_on = bool(ob.get("heightmax_height_nutrition_opt_in"))

        sprint_days = {1, 4, 6}

        days: list = []
        for day_num in range(1, num_days + 1):
            d = start_date + timedelta(days=day_num - 1)
            wd = d.weekday()
            tasks: List[dict] = []

            if _on("decompress_lengthen"):
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["morning_decompression"],
                        "title": "HeightMax — Morning decompression",
                        "description": "Dead hang, cobra, cat-cow, tadasana — 5–7 min. Spine is tallest in the morning.",
                        "task_type": "routine",
                        "duration_minutes": 7,
                    }
                )
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["evening_decompression"],
                        "title": "HeightMax — Evening decompression",
                        "description": "Undo daily compression: hang, twist, legs-up-wall or inversion, child's pose.",
                        "task_type": "routine",
                        "duration_minutes": 8,
                    }
                )

            if _on("posturemaxxing"):
                desc = "Wall test, chin tucks, shoulder squeezes, glute bridges — 3–4 min."
                if _on("look_taller_instantly") and wd == 0:
                    desc += " Softmax tip: fitted silhouette / vertical lines this week."
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["midday_posture"],
                        "title": "HeightMax — Midday posture reset",
                        "description": desc,
                        "task_type": "routine",
                        "duration_minutes": 4,
                    }
                )
                if high_screen:
                    tasks.append(
                        {
                            "task_id": str(uuid.uuid4()),
                            "time": slots["afternoon_posture"],
                            "title": "HeightMax — Afternoon posture slip check",
                            "description": "Screen-heavy day: head back, shoulders open, phone at eye level.",
                            "task_type": "reminder",
                            "duration_minutes": 1,
                        }
                    )

            if _on("deep_sleep_routine"):
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["sleep_protocol"],
                        "title": "HeightMax — Sleep / GH protocol",
                        "description": "Blue light off, cool room, no food <2h; blackout + back sleep + thin pillow.",
                        "task_type": "routine",
                        "duration_minutes": 5,
                    }
                )

            if _on("sprintmaxxing") and day_num in sprint_days:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": sprint_pre,
                        "title": "HeightMax — Sprint session soon",
                        "description": "Warm-up then 6–8×30s sprints, full rest. No food 1h after.",
                        "task_type": "checkpoint",
                        "duration_minutes": 25,
                    }
                )
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": sprint_post,
                        "title": "HeightMax — Post-sprint — eat window",
                        "description": "High-protein meal within 30 min.",
                        "task_type": "reminder",
                        "duration_minutes": 2,
                    }
                )

            if _on("height_killers"):
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": _add_time(slots["midday_posture"], 45),
                        "title": "HeightMax — Height killer audit",
                        "description": "Slouch, sitting load, sleep debt, under-eating — quick check.",
                        "task_type": "reminder",
                        "duration_minutes": 2,
                    }
                )

            if nutrition_on:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["height_nutrition"],
                        "title": "HeightMax — Height nutrition (meal)",
                        "description": "Protein + D3/K2/zinc/mag/collagen concept with a fat-containing meal — your stack.",
                        "task_type": "reminder",
                        "duration_minutes": 2,
                    }
                )

            if wd == 6 and _on("decompress_lengthen"):
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["weekly_measurement"],
                        "title": "HeightMax — Weekly height measure",
                        "description": "Sunday AM after routine: same wall/mark, mm precision.",
                        "task_type": "checkpoint",
                        "duration_minutes": 5,
                    }
                )

            if d.day == 1:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["monthly_checkin"],
                        "title": "HeightMax — Monthly review",
                        "description": "Compare Sundays, posture feel, any stretch-related pain.",
                        "task_type": "checkpoint",
                        "duration_minutes": 5,
                    }
                )

            tasks.sort(key=lambda t: t.get("time") or "00:00")
            days.append(
                {
                    "day_number": day_num,
                    "tasks": tasks,
                    "motivation_message": f"Day {day_num} — HeightMax fallback uses engine timing; Tier 3 = reclaim only, no inch promises.",
                }
            )

        return {"days": days}

    def _generate_hairmax_fallback(
        self,
        num_days: int,
        wake_time: str,
        sleep_time: str,
        *,
        concern: str,
        onboarding: dict,
        start_date: date,
    ) -> dict:
        """Fallback HairMax when Gemini fails — engine slot times + concern-aware tasks."""
        from services.hairmax_notification_engine import get_hairmax_slot_times

        def _bed_minus_mins(bed: str, delta: int) -> str:
            h, m = map(int, bed.split(":"))
            t = h * 60 + m - delta
            t %= 24 * 60
            return f"{t // 60:02d}:{t % 60:02d}"

        def _add_to_time(tstr: str, delta: int) -> str:
            h, m = map(int, tstr.split(":"))
            t = h * 60 + m + delta
            t %= 24 * 60
            return f"{t // 60:02d}:{t % 60:02d}"

        slots = get_hairmax_slot_times(wake_time, sleep_time)
        ob = onboarding or {}
        topical_only = bool(ob.get("hair_topical_fin_only") or ob.get("hairmax_topical_fin_only"))
        thinning_stack = concern in ("minoxidil", "dermastamp")
        topical_pm_slot = _bed_minus_mins(sleep_time, 120)

        mn_raw = ob.get("hairmax_microneedling_weekday", 6)
        if isinstance(mn_raw, str):
            _k = mn_raw.strip().lower()[:3]
            _dow_mn = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
            mn_dow = _dow_mn.get(_k, 6)
        else:
            try:
                mn_dow = int(mn_raw) % 7
            except (TypeError, ValueError):
                mn_dow = 6
        mnt = (ob.get("hairmax_microneedling_time") or "").strip()
        if mnt and ":" in mnt:
            mn_slot = mnt[:5]
        else:
            mn_slot = slots["microneedling_default"]
        mo_raw = ob.get("hairmax_months_on_treatment")
        if mo_raw is None or str(mo_raw).strip() == "":
            def _microneedling_ok(dn: int) -> bool:
                return dn >= 8

        else:
            try:
                _mo = int(mo_raw)

                def _microneedling_ok(dn: int) -> bool:
                    return _mo >= 4

            except (TypeError, ValueError):

                def _microneedling_ok(dn: int) -> bool:
                    return dn >= 8

        days: list = []
        for day_num in range(1, num_days + 1):
            d = start_date + timedelta(days=day_num - 1)
            wd = d.weekday()
            tasks: List[dict] = []

            if thinning_stack:
                if topical_only:
                    tasks.append(
                        {
                            "task_id": str(uuid.uuid4()),
                            "time": topical_pm_slot,
                            "title": "HairMax — Topical finasteride",
                            "description": "Apply to thinning scalp at night — lower systemic load. Pair timing with minoxidil PM per your routine.",
                            "task_type": "routine",
                            "duration_minutes": 3,
                        }
                    )
                else:
                    tasks.append(
                        {
                            "task_id": str(uuid.uuid4()),
                            "time": slots["finasteride"],
                            "title": "HairMax — Finasteride",
                            "description": "Daily dose per tier. 0.5mg ≈ 85–90% DHT suppression vs 1mg — staying on 0.5mg is valid if you prefer.",
                            "task_type": "routine",
                            "duration_minutes": 1,
                        }
                    )
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["minoxidil_am"],
                        "title": "HairMax — Minoxidil AM",
                        "description": "Foam preferred; 1ml to scalp; part hair; dry 15–20 min; no wash 4h; wash hands after.",
                        "task_type": "routine",
                        "duration_minutes": 5,
                    }
                )
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["minoxidil_pm"],
                        "title": "HairMax — Minoxidil PM",
                        "description": "Liquid OK; dry 30–60 min before bed; keep off pillow.",
                        "task_type": "routine",
                        "duration_minutes": 5,
                    }
                )
            else:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["midday"],
                        "title": f"HairMax — {concern.replace('_', ' ').title()} check-in",
                        "description": "Follow your hair protocol for this concern (wash, oils, anti-dandruff, etc.).",
                        "task_type": "reminder",
                        "duration_minutes": 3,
                    }
                )

            tasks.append(
                {
                    "task_id": str(uuid.uuid4()),
                    "time": slots["midday"],
                    "title": "HairMax — Scalp micro-tip",
                    "description": "Rotate tips: dry scalp, part to skin, no blow-dry right after minox, coverage includes crown.",
                    "task_type": "reminder",
                    "duration_minutes": 1,
                }
            )

            if thinning_stack and wd in (0, 2, 4):
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": _add_to_time(slots["finasteride"], 120),
                        "title": "HairMax — Ketoconazole wash",
                        "description": "2–3×/week medicated shampoo on scalp.",
                        "task_type": "routine",
                        "duration_minutes": 8,
                    }
                )

            if thinning_stack and wd == mn_dow and _microneedling_ok(day_num):
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": mn_slot,
                        "title": "HairMax — Microneedling session",
                        "description": "Weekly scalp session — not same night as minoxidil (shift if conflict); stagger vs face microneedling. Resume minox after ~24h safe window.",
                        "task_type": "checkpoint",
                        "duration_minutes": 20,
                    }
                )

            if thinning_stack and day_num % 14 == 1:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": _add_to_time(slots["minoxidil_am"], 45),
                        "title": "HairMax — Bi-weekly progress photos",
                        "description": "Same angles/lighting; wet hair OK for density.",
                        "task_type": "checkpoint",
                        "duration_minutes": 8,
                    }
                )

            if d.day == 1:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["midday"],
                        "title": "HairMax — Monthly check-in",
                        "description": "Compare photos, hair feel, sides, missed doses — per notification engine.",
                        "task_type": "checkpoint",
                        "duration_minutes": 5,
                    }
                )

            tasks.sort(key=lambda t: t.get("time") or "00:00")
            days.append(
                {
                    "day_number": day_num,
                    "tasks": tasks,
                    "motivation_message": f"Day {day_num} — HairMax fallback: ramp phases + Skinmax merge rules apply when stacked.",
                }
            )

        return {"days": days}

    def _generate_bonemax_fallback(
        self,
        num_days: int,
        wake_time: str,
        sleep_time: str,
        *,
        onboarding: dict,
        start_date: date,
    ) -> dict:
        """Fallback BoneMax when Gemini fails — aligned to bonemax_notification_engine slot math."""
        from services.bonemax_notification_engine import get_bonemax_slot_times

        def _add_minutes_to_str(tstr: str, delta: int) -> str:
            h, m = map(int, tstr.split(":"))
            total = h * 60 + m + delta
            total %= 24 * 60
            return f"{total // 60:02d}:{total % 60:02d}"

        slots = get_bonemax_slot_times(wake_time, sleep_time)
        ob = onboarding or {}
        masseter_time = (ob.get("bonemax_masseter_time") or "").strip()
        if masseter_time and ":" in masseter_time:
            slots = {**slots, "masseter": masseter_time[:5]}
        tmj_yes = str(ob.get("bonemax_tmj_history", "")).lower() in ("yes", "y", "true", "1")
        bone_stack = bool(ob.get("bonemax_bone_nutrition_opt_in"))
        high_screen = False
        scr = str(ob.get("bonemax_heavy_screen_time") or ob.get("bonemax_screen_hours") or "")
        m_scr = re.search(r"(\d+)", scr)
        if m_scr and int(m_scr.group(1)) >= 6:
            high_screen = True

        days: list = []
        for day_num in range(1, num_days + 1):
            d = start_date + timedelta(days=day_num - 1)
            wd = d.weekday()
            tasks: list = [
                {
                    "task_id": str(uuid.uuid4()),
                    "time": slots["mewing_morning"],
                    "title": "BoneMax — Mewing morning reset",
                    "description": "👅 Tongue on palate, lips sealed, teeth light, chin tucked, 60s hold then passive. Nasal only.",
                    "task_type": "routine",
                    "duration_minutes": 2,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": slots["facial"],
                    "title": "BoneMax — Facial exercises (5 min)",
                    "description": "Jaw push-outs, chin lifts, cheekbone presses, fish face — quick block after mewing set.",
                    "task_type": "routine",
                    "duration_minutes": 5,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": slots["fascia_am"],
                    "title": "BoneMax — Morning fascia / lymph",
                    "description": "90s tap + drain paths; feather-light pressure.",
                    "task_type": "routine",
                    "duration_minutes": 2,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": slots["masseter"],
                    "title": "BoneMax — Masseter session",
                    "description": (
                        "Falim 10–15 min, premolar zone, switch sides q5min, stop if click/pain. TMJ history: keep ≤15 min Falim only."
                        if tmj_yes
                        else "Falim/mastic per your week band — slow reps, lips sealed, premolar zone, stop if click/pain."
                    ),
                    "task_type": "checkpoint",
                    "duration_minutes": 15 if tmj_yes else 20,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": _add_minutes_to_str(slots["masseter"], 20),
                    "title": "BoneMax — Masseter recovery check",
                    "description": "Jaw worked but calm? Any clicking or one-sided soreness? Adjust next session per engine.",
                    "task_type": "checkpoint",
                    "duration_minutes": 1,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": slots["mewing_midday"],
                    "title": "BoneMax — Mewing midday reset (+ chin tucks if rest day)",
                    "description": "30s tongue/lips/nose; stack head; unclench."
                    + (" Add chin tucks 2×15 — no gym neck today." if day_num % 2 == 1 else " Gym day: you may skip chin tucks here if you hit neck post-workout."),
                    "task_type": "routine",
                    "duration_minutes": 3,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": slots["nasal"],
                    "title": "BoneMax — Nasal breathing check",
                    "description": "Mouth closed? 5 slow nasal breaths if not. Congestion: saline / light movement before forcing nasal only.",
                    "task_type": "reminder",
                    "duration_minutes": 1,
                },
                {
                    "task_id": str(uuid.uuid4()),
                    "time": slots["symmetry"],
                    "title": "BoneMax — Symmetry habit check",
                    "description": "Rotate weekly: shoulders, bag strap, chin on hand, jaw relaxed at rest, etc.",
                    "task_type": "reminder",
                    "duration_minutes": 1,
                },
            ]
            if high_screen:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": _add_minutes_to_str(slots["nasal"], 120),
                        "title": "BoneMax — Nasal / posture (screen day)",
                        "description": "Second check: screens pull head forward — reset nasal + chin back.",
                        "task_type": "reminder",
                        "duration_minutes": 1,
                    }
                )
            if wd not in (2, 6):
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["fascia_evening"],
                        "title": "BoneMax — Evening fascia / lymph",
                        "description": "2–3 min; jawline/cheeks/neck; finish downward to collarbone. Skip if Skinmax retinoid/exfol same night.",
                        "task_type": "routine",
                        "duration_minutes": 4,
                    }
                )
            tasks.append(
                {
                    "task_id": str(uuid.uuid4()),
                    "time": slots["mewing_night"],
                    "title": "BoneMax — Mewing night check (+ sleep cues)",
                    "description": "Tongue up, lips sealed, nasal. Bundle sleep position tip + optional mouth-tape note per onboarding.",
                    "task_type": "routine",
                    "duration_minutes": 2,
                }
            )
            if bone_stack:
                wh, wm = map(int, wake_time.split(":"))
                bh = (wh + 1) % 24
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": f"{bh:02d}:{wm:02d}",
                        "title": "BoneMax — Bone stack (with meal)",
                        "description": "D3/K2/Mg/Zn/Boron/collagen concept — take with a fat-containing meal.",
                        "task_type": "reminder",
                        "duration_minutes": 1,
                    }
                )
            if d.day == 1:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": slots["mewing_midday"],
                        "title": "BoneMax — Monthly bone check",
                        "description": "Front + side photos, neck tape, jaw feel, TMJ month review.",
                        "task_type": "checkpoint",
                        "duration_minutes": 8,
                    }
                )
            if wd == 0:
                tasks.append(
                    {
                        "task_id": str(uuid.uuid4()),
                        "time": _add_minutes_to_str(slots["mewing_morning"], 180),
                        "title": "BoneMax — Weekly checkpoint",
                        "description": "Front + side snap; note jaw tension, symmetry, and masseter recovery vs last week.",
                        "task_type": "checkpoint",
                        "duration_minutes": 5,
                    }
                )
            tasks.sort(key=lambda t: t.get("time") or "00:00")
            days.append(
                {
                    "day_number": day_num,
                    "tasks": tasks,
                    "motivation_message": f"Day {day_num} — BoneMax fallback: engine slot times, cap notifications when stacking modules.",
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

        user_uuid = UUID(user_id)
        user_row = await db.get(User, user_uuid)
        all_schedules = await self.get_all_active_schedules(user_id, db)
        streak = await sync_master_schedule_streak(user_row, all_schedules, db)

        return {"status": "completed", "completion_stats": stats, "schedule_streak": streak}

    def _recalc_completion_stats_from_days(self, days: list) -> dict:
        """Derive completion_stats from task statuses (keeps totals accurate when uncompleting)."""
        total = 0
        completed = 0
        skipped = 0
        for day in days or []:
            for task in day.get("tasks", []):
                total += 1
                st = task.get("status") or "pending"
                if st == "completed":
                    completed += 1
                elif st == "skipped":
                    skipped += 1
        return {"completed": completed, "total": total, "skipped": skipped}

    async def uncomplete_task(self, user_id: str, schedule_id: str, task_id: str, db: AsyncSession) -> dict:
        """Mark a completed task as pending again (master schedule toggle)."""
        schedule = await self._load_schedule(schedule_id, user_id, db)
        if not schedule:
            raise ValueError("Schedule not found")

        updated = False
        days = schedule.days or []
        for day in days:
            for task in day.get("tasks", []):
                if task.get("task_id") == task_id:
                    if task.get("status") != "completed":
                        raise ValueError("Task is not completed")
                    task["status"] = "pending"
                    task.pop("completed_at", None)
                    updated = True
                    break
            if updated:
                break

        if not updated:
            raise ValueError("Task not found in schedule")

        stats = self._recalc_completion_stats_from_days(days)
        schedule.days = days
        flag_modified(schedule, "days")
        schedule.completion_stats = stats
        schedule.updated_at = datetime.utcnow()

        await db.commit()

        user_uuid = UUID(user_id)
        user_row = await db.get(User, user_uuid)
        all_schedules = await self.get_all_active_schedules(user_id, db)
        streak = await sync_master_schedule_streak(user_row, all_schedules, db)

        return {"status": "pending", "completion_stats": stats, "schedule_streak": streak}

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

        adapt_tmpl = await asyncio.to_thread(
            resolve_prompt, PromptKey.SCHEDULE_ADAPTATION, SCHEDULE_ADAPTATION_PROMPT
        )
        prompt = adapt_tmpl.format(
            current_schedule_json=json.dumps({"days": schedule.days}, indent=2),
            completed_count=completed,
            total_count=total,
            most_skipped=", ".join(set(skipped_types)) if skipped_types else "none",
            completion_rate=completion_rate,
            user_feedback=feedback,
        )

        try:
            raw = await asyncio.to_thread(sync_llm_json_response, prompt)
            adapted = json.loads(raw)
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
            # Prefer canonical metric fields when present; fall back to legacy onboarding keys.
            unit = str(onboarding.get("unit_system") or "imperial").strip().lower()
            h_cm = onboarding.get("height_cm")
            w_kg = onboarding.get("weight_kg")
            if h_cm is None:
                h_raw = onboarding.get("height")
                if h_raw is not None:
                    h_cm = float(h_raw) if unit == "metric" else float(h_raw) * 2.54
            if w_kg is None:
                w_raw = onboarding.get("weight")
                if w_raw is not None:
                    w_kg = float(w_raw) if unit == "metric" else float(w_raw) * 0.453592
            if h_cm is not None:
                profile_parts.append(f"Height: {round(float(h_cm), 1)}cm")
            if w_kg is not None:
                profile_parts.append(f"Weight: {round(float(w_kg), 1)}kg")
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
