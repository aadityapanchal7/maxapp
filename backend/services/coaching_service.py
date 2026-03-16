"""
Coaching Service — State management, check-ins, AI memory, rules engine.
Handles the full coaching loop: context gathering, check-in parsing, memory
updates, tone detection, and proactive outbound messages.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from config import settings
from models.sqlalchemy_models import User, UserCoachingState, UserSchedule, ChatHistory, Scan

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config — only behavioral thresholds, no message/tone hardcoding
# ---------------------------------------------------------------------------
COACHING_CONFIG = {
    "check_in_cooldown_hours": 8,
}


class CoachingService:

    # ------------------------------------------------------------------
    # State CRUD
    # ------------------------------------------------------------------

    async def get_or_create_state(self, user_id: str, db: AsyncSession) -> UserCoachingState:
        user_uuid = UUID(user_id)
        result = await db.execute(
            select(UserCoachingState).where(UserCoachingState.user_id == user_uuid)
        )
        state = result.scalar_one_or_none()
        if not state:
            state = UserCoachingState(user_id=user_uuid)
            db.add(state)
            await db.commit()
            await db.refresh(state)
        return state

    async def update_state(self, user_id: str, db: AsyncSession, **kwargs) -> UserCoachingState:
        state = await self.get_or_create_state(user_id, db)
        for k, v in kwargs.items():
            if hasattr(state, k):
                setattr(state, k, v)
        state.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(state)
        return state

    # ------------------------------------------------------------------
    # Check-in processing
    # ------------------------------------------------------------------

    async def process_check_in(self, user_id: str, db: AsyncSession, data: dict) -> UserCoachingState:
        """
        Called after the AI parses a check-in response from the user.
        data keys: workout_done, sleep_hours, calories, mood, injury, notes
        """
        state = await self.get_or_create_state(user_id, db)

        if data.get("workout_done"):
            state.last_workout = datetime.utcnow()
            state.streak_days = (state.streak_days or 0) + 1
            state.missed_days = 0
        if data.get("missed"):
            state.missed_days = (state.missed_days or 0) + 1
            state.streak_days = 0
        if data.get("sleep_hours"):
            state.last_sleep_hours = float(data["sleep_hours"])
        if data.get("calories"):
            state.last_calories = int(data["calories"])
        if data.get("mood"):
            state.last_mood = str(data["mood"])
        if data.get("injury"):
            injuries = list(state.injuries or [])
            injuries.append({
                "area": data["injury"].get("area", "unknown"),
                "note": data["injury"].get("note", ""),
                "date": datetime.utcnow().isoformat(),
            })
            state.injuries = injuries
            flag_modified(state, "injuries")

        state.total_check_ins = (state.total_check_ins or 0) + 1
        state.last_check_in = datetime.utcnow()
        state.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(state)
        return state

    async def record_missed_day(self, user_id: str, db: AsyncSession) -> UserCoachingState:
        state = await self.get_or_create_state(user_id, db)
        state.missed_days = (state.missed_days or 0) + 1
        state.streak_days = 0
        state.updated_at = datetime.utcnow()
        await db.commit()
        return state

    # ------------------------------------------------------------------
    # AI Memory — summaries + persistent context
    # ------------------------------------------------------------------

    async def update_ai_memory(self, user_id: str, db: AsyncSession, conversation_summary: str):
        """
        After a conversation, store a compressed summary.
        Keep last 3 summaries in ai_summaries, rewrite ai_context with latest.
        """
        user_uuid = UUID(user_id)
        user = await db.get(User, user_uuid)
        if not user:
            return

        summaries = list(user.ai_summaries or [])
        summaries.append({
            "summary": conversation_summary,
            "date": datetime.utcnow().isoformat(),
        })
        # Keep only last 3
        if len(summaries) > 3:
            summaries = summaries[-3:]

        user.ai_summaries = summaries
        flag_modified(user, "ai_summaries")

        # Build a merged context from all 3 summaries
        merged = "\n---\n".join(s["summary"] for s in summaries)
        user.ai_context = merged
        user.updated_at = datetime.utcnow()
        await db.commit()

    async def generate_conversation_summary(self, messages: list[dict]) -> str:
        """
        Use Gemini to compress recent conversation into a brief summary.
        Returns the summary text.
        """
        if not messages:
            return ""
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in messages[-20:])
        prompt = f"""Compress this conversation into 2-3 sentences capturing key facts about the user
(goals, concerns, injuries, progress, preferences, anything they mentioned about themselves).
Only include factual info, no fluff.

CONVERSATION:
{convo}

SUMMARY:"""
        try:
            import google.generativeai as genai
            model = genai.GenerativeModel(settings.gemini_model)
            resp = model.generate_content(prompt)
            return resp.text.strip()
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return ""

    # ------------------------------------------------------------------
    # Tone detection — adapt over time
    # ------------------------------------------------------------------

    async def detect_tone_preference(self, user_id: str, db: AsyncSession, messages: list[dict]):
        """
        Analyze recent messages to detect if user responds better to
        aggressive accountability vs chill support. Updates coaching state.
        """
        if len(messages) < 10:
            return
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in messages[-30:])
        prompt = f"""Analyze this chat between a coaching AI and a user.
Based on the user's responses, which coaching tone works best for them?
Options: "direct", "aggressive", "chill"

- "direct" = they respond well to straightforward no-BS advice
- "aggressive" = they need tough love, accountability, being called out
- "chill" = they respond better to gentle encouragement, low pressure

Reply with ONLY one word: direct, aggressive, or chill

CONVERSATION:
{convo}"""
        try:
            import google.generativeai as genai
            model = genai.GenerativeModel(settings.gemini_model)
            resp = model.generate_content(prompt)
            tone = resp.text.strip().lower()
            if tone in ("direct", "aggressive", "chill"):
                await self.update_state(user_id, db, preferred_tone=tone)
        except Exception as e:
            logger.error(f"Tone detection failed: {e}")

    # ------------------------------------------------------------------
    # Context builder — pulls everything for the AI prompt
    # ------------------------------------------------------------------

    async def build_full_context(self, user_id: str, db: AsyncSession, rds_db=None) -> str:
        """
        Build the complete user context string for the AI prompt.
        Pulls: onboarding, coaching state, schedule, scans, AI memory, maxx guidelines.
        """
        user_uuid = UUID(user_id)
        user = await db.get(User, user_uuid)
        if not user:
            return ""

        parts = []
        onboarding = user.onboarding or {}
        state = await self.get_or_create_state(user_id, db)

        # --- User profile ---
        profile_bits = []
        for k in ["gender", "age", "skin_type", "goals"]:
            v = onboarding.get(k)
            if v:
                val = ", ".join(v) if isinstance(v, list) else str(v)
                profile_bits.append(f"{k}: {val}")
        if profile_bits:
            parts.append(f"PROFILE: {' | '.join(profile_bits)}")

        # --- Coaching state ---
        coaching_bits = []
        if state.streak_days:
            coaching_bits.append(f"streak: {state.streak_days}d")
        if state.missed_days:
            coaching_bits.append(f"missed: {state.missed_days}d")
        if state.primary_goal:
            coaching_bits.append(f"goal: {state.primary_goal}")
        if state.weight:
            coaching_bits.append(f"weight: {state.weight}")
        if state.last_sleep_hours:
            coaching_bits.append(f"last sleep: {state.last_sleep_hours}h")
        if state.last_calories:
            coaching_bits.append(f"last cals: {state.last_calories}")
        if state.last_mood:
            coaching_bits.append(f"mood: {state.last_mood}")
        if state.injuries:
            inj_str = ", ".join(i.get("area", "?") for i in state.injuries[-3:])
            coaching_bits.append(f"injuries: {inj_str}")
        if coaching_bits:
            parts.append(f"COACHING STATE: {' | '.join(coaching_bits)}")

        # --- Tone (user preference; AI decides how to adapt) ---
        if state.preferred_tone:
            parts.append(f"User responds better to: {state.preferred_tone} tone")

        # --- Latest scan ---
        scan_result = await db.execute(
            select(Scan).where(Scan.user_id == user_uuid).order_by(Scan.created_at.desc()).limit(1)
        )
        scan = scan_result.scalar_one_or_none()
        if scan and scan.analysis:
            a = scan.analysis
            parts.append(f"LATEST SCAN: score={a.get('overall_score', '?')}/10, focus={a.get('focus_areas', [])}")

        # --- Active schedules ---
        sched_result = await db.execute(
            select(UserSchedule).where(
                (UserSchedule.user_id == user_uuid) & (UserSchedule.is_active == True)
            ).order_by(UserSchedule.created_at.desc()).limit(3)
        )
        schedules = sched_result.scalars().all()
        skinmax_protocol_added = False
        tz_name = onboarding.get("timezone", "UTC")
        try:
            user_tz = ZoneInfo(tz_name)
        except Exception:
            user_tz = ZoneInfo("UTC")
        today_iso = datetime.now(user_tz).date().isoformat()
        for s in schedules:
            label = s.course_title or s.maxx_id or "schedule"
            ctx = s.schedule_context or {}
            today_tasks = []
            for day in (s.days or []):
                if day.get("date") == today_iso:
                    for t in day.get("tasks", []):
                        status = t.get("status", "pending")
                        today_tasks.append(f"{t.get('time','?')} {t.get('title','?')} [{status}]")
            sched_str = f"SCHEDULE ({label}): concern={ctx.get('skin_concern', '?')}"
            if today_tasks:
                sched_str += f" | today: {', '.join(today_tasks[:6])}"
            # outside_today: refreshed daily; if stale, AI should ask
            if s.maxx_id == "skinmax":
                outside_date = ctx.get("outside_today_date")
                if outside_date == today_iso:
                    outside_val = ctx.get("outside_today")
                    sched_str += f" | outside_today: {outside_val}"
                else:
                    sched_str += " | outside_today: unknown — ask user each morning"
            parts.append(sched_str)

            # --- SkinMax protocol (for skin Q&A) ---
            if s.maxx_id == "skinmax" and not skinmax_protocol_added:
                concern = ctx.get("skin_concern", "aging")
                try:
                    from services.guideline_service import get_maxx_guideline_async, build_protocol_prompt_section
                    guideline = await get_maxx_guideline_async("skinmax", rds_db)
                    if guideline:
                        protocol_section = build_protocol_prompt_section(guideline, concern)
                        if protocol_section:
                            parts.append(f"SKINMAX PROTOCOL (for skin questions):\n{protocol_section[:800]}")
                            skinmax_protocol_added = True
                except Exception:
                    from services.maxx_guidelines import build_skinmax_prompt_section
                    protocol_section = build_skinmax_prompt_section(concern)
                    parts.append(f"SKINMAX PROTOCOL (for skin questions):\n{protocol_section[:800]}")
                    skinmax_protocol_added = True

        # --- AI memory ---
        if user.ai_context:
            parts.append(f"MEMORY (from past convos):\n{user.ai_context}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Check-in message generation — fully AI-driven, no hardcoded tone
    # ------------------------------------------------------------------

    async def generate_check_in_message(
        self,
        user_id: str,
        db: AsyncSession,
        rds_db=None,
        check_in_type: str = "midday",
        missed_today: int = 0,
    ) -> str:
        """
        Generate a check-in message using AI. Passes full context; AI decides tone and content.
        check_in_type: morning, midday, night, missed_task, weekly
        """
        context_str = await self.build_full_context(user_id, db, rds_db)
        if not context_str:
            context_str = "No context yet."

        user = await db.get(User, UUID(user_id))
        name = (user.first_name or user.email.split("@")[0]) if user else "there"

        prompt = f"""You are Max, a lookmaxxing coach. Generate a short check-in message for {name}.

User context:
{context_str}

Check-in type: {check_in_type}
"""
        if missed_today > 0:
            prompt += f"\nThey missed {missed_today} task(s) today."

        prompt += """

Generate ONE short message (1-2 sentences max). Be casual, direct, no fluff. Match your tone to their situation — if they're slacking, call it out; if they're on a streak, hype them. Sound like a real person texting, not GPT.

Message:"""

        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel(settings.gemini_model)
            resp = model.generate_content(prompt)
            return resp.text.strip()
        except Exception as e:
            logger.error(f"Check-in generation failed: {e}")
            return "yo, checking in — how you doing today?"


coaching_service = CoachingService()
