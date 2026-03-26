"""
Coaching Service — State management, check-ins, AI memory, rules engine.
Handles the full coaching loop: context gathering, check-in parsing, memory
updates, tone detection, and proactive outbound messages.
"""

import asyncio
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
from db.sqlalchemy import AsyncSessionLocal
from services.prompt_loader import PromptKey, resolve_prompt

logger = logging.getLogger(__name__)


def _sync_gemini_plain_text(prompt: str) -> str:
    """Blocking Gemini call — run via asyncio.to_thread so the event loop is not frozen."""
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)
    resp = model.generate_content(prompt)
    return (resp.text or "").strip()


# ---------------------------------------------------------------------------
# Config — only behavioral thresholds, no message/tone hardcoding
# ---------------------------------------------------------------------------
COACHING_CONFIG = {
    "check_in_cooldown_hours": 8,
}

_COACHING_MEMORY_COMPRESS_FALLBACK = """Compress this conversation into 2-3 sentences capturing key facts about the user
(goals, concerns, injuries, progress, preferences, anything they mentioned about themselves).
Only include factual info, no fluff.

CONVERSATION:
{convo}

SUMMARY:"""

_COACHING_TONE_DETECT_FALLBACK = """Analyze this chat between a coaching AI and a user.
Based on the user's responses, which coaching tone works best for them?
Options: "direct", "aggressive", "chill"

- "direct" = they respond well to straightforward no-BS advice
- "aggressive" = they need tough love, accountability, being called out
- "chill" = they respond better to gentle encouragement, low pressure

Reply with ONLY one word: direct, aggressive, or chill

CONVERSATION:
{convo}"""

_COACHING_FITMAX_CHECK_IN_FALLBACK = """You are the Fitmax SMS coach. Write one SMS only.

Tone: direct, knowledgeable, personal. Never generic.
Max length: 3 sentences.
Exactly one actionable point.

User name: {name}
Check-in type: {check_in_type}
Missed tasks today: {missed_today}

Week state context:
{context_str}{multi_module_sms_hint}

If check_in_type is one of:
- morning_training_day: mention today's session focus and one execution cue.
- morning_rest_day: reinforce recovery + protein target.
- preworkout: remind session start and one cue.
- postworkout: reinforce protein + current calorie position.
- evening_nutrition: mention calories left and one practical food option.
- weekly_fitmax_summary: summarize week with one key priority for next week.
- milestone_pr: celebrate PR and compare to prior trend.

Return only the message text, no labels."""

_COACHING_CHECK_IN_GENERAL_FALLBACK = """You are Max, a lookmaxxing coach. Generate a short check-in message for {name}.

User context:
{context_str}{multi_module_sms_hint}

Check-in type: {check_in_type}{missed_line}

Generate ONE short message (1-2 sentences max). Be casual, direct, no fluff. Match your tone to their situation — if they're slacking, call it out; if they're on a streak, hype them. Sound like a real person texting, not GPT.

Message:"""

_COACHING_BEDTIME_FALLBACK = """You are Max — the user's lookmaxxing coach. Send ONE SMS before their bedtime.

User first name or handle: {name}

Context (trim mentally — stay brief):
{context_snippet}

Rules:
- 1–3 short sentences max. Casual, direct, lowercase ok — like other Max check-ins. No corporate tone.
- Say it's almost bedtime / wind-down in a natural way.
- You MUST clearly tell them they can reply to THIS SAME TEXT THREAD with a selfie or progress picture to log today's progress (MMS). Do not say "only in the app" — SMS photo reply is the main CTA.
- Do not analyze or judge their face; you're just collecting for their private archive.
- Under 300 characters if you can.

Output ONLY the SMS body, no quotes."""


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
        tmpl = await asyncio.to_thread(
            resolve_prompt,
            PromptKey.COACHING_MEMORY_COMPRESS,
            _COACHING_MEMORY_COMPRESS_FALLBACK,
        )
        prompt = tmpl.format(convo=convo)
        try:
            return await asyncio.to_thread(_sync_gemini_plain_text, prompt)
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
        tmpl = await asyncio.to_thread(
            resolve_prompt, PromptKey.COACHING_TONE_DETECT, _COACHING_TONE_DETECT_FALLBACK
        )
        prompt = tmpl.format(convo=convo)
        try:
            text = await asyncio.to_thread(_sync_gemini_plain_text, prompt)
            tone = text.lower()
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

        # --- Account (address naturally in replies) ---
        account_bits = []
        if user.first_name:
            account_bits.append(f"first_name={user.first_name}")
        if user.last_name:
            account_bits.append(f"last_name={user.last_name}")
        if user.username:
            account_bits.append(f"username=@{user.username}")
        if account_bits:
            parts.append(
                "ACCOUNT — use first name when greeting if present; username is social handle: "
                + " | ".join(account_bits)
            )

        # --- User profile (signup / global onboarding — always surface for schedule + chat flows) ---
        profile_bits = []
        global_bits = []
        for k in [
            "age",
            "gender",
            "sex",
            "height",
            "weight",
            "waist_cm",
            "skin_type",
            "goals",
            "experience_level",
            "activity_level",
            "equipment",
            "priority_order",
            "appearance_concerns",
            "primary_skin_concern",
            "secondary_skin_concern",
            "skincare_routine_level",
            "hair_family_history",
            "hair_current_loss",
            "hair_treatments_current",
            "hair_side_effect_sensitivity",
            "fitmax_primary_goal",
            "fitmax_training_experience",
            "fitmax_equipment",
            "fitmax_workout_days_per_week",
            "preferred_workout_time",
            "fitmax_preferred_workout_time",
            "screen_hours_daily",
            "questionnaire_v2_completed",
            "bonemax_workout_frequency",
            "bonemax_tmj_history",
            "bonemax_mastic_gum_regular",
            "bonemax_heavy_screen_time",
            "hair_type",
            "scalp_state",
            "daily_styling",
            "thinning",
            "hair_thinning",
        ]:
            v = onboarding.get(k)
            if v is not None and v != "" and v != []:
                val = ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
                global_bits.append(f"{k}={val}")
        if global_bits:
            parts.append(
                "GLOBAL ONBOARDING (from app signup — use as source of truth; do not re-ask unless user wants to change): "
                + " | ".join(global_bits)
            )
        wt = onboarding.get("wake_time")
        st = onboarding.get("sleep_time")
        sp = user.schedule_preferences or {}
        if not wt and sp.get("wake_time"):
            wt = sp.get("wake_time")
        if not st and sp.get("sleep_time"):
            st = sp.get("sleep_time")
        if wt or st:
            profile_bits.append(
                f"saved wake/sleep (reuse for new schedules — do not re-ask unless user wants to change; "
                f"never prompt for 24-hour format): "
                f"wake_time={wt or 'unknown'}, sleep_time={st or 'unknown'}"
            )
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
        bonemax_protocol_added = False
        heightmax_protocol_added = False
        hairmax_protocol_added = False
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
            if s.maxx_id == "bonemax":
                sched_str = f"SCHEDULE ({label}): bonemax"
            elif s.maxx_id == "heightmax":
                sched_str = f"SCHEDULE ({label}): heightmax"
            elif s.maxx_id == "fitmax":
                sched_str = f"SCHEDULE ({label}): fitmax phase={ctx.get('selected_concern', ctx.get('skin_concern', '?'))}"
            else:
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

            # --- SkinMax notification engine + protocol (for skin Q&A & SMS alignment) ---
            if s.maxx_id == "skinmax" and not skinmax_protocol_added:
                concern = ctx.get("skin_concern", "aging")
                wt = ctx.get("wake_time") or onboarding.get("wake_time") or "07:00"
                st = ctx.get("sleep_time") or onboarding.get("sleep_time") or "23:00"
                outside_val = False
                if ctx.get("outside_today_date") == today_iso and ctx.get("outside_today") is not None:
                    outside_val = bool(ctx.get("outside_today"))
                from services.maxx_guidelines import build_skinmax_prompt_section

                protocol_section = build_skinmax_prompt_section(
                    concern,
                    onboarding=onboarding,
                    wake_time=str(wt),
                    sleep_time=str(st),
                    outside_today=outside_val,
                    for_coaching=True,
                )
                parts.append(
                    f"SKINMAX NOTIFICATION ENGINE (reference for skin + routine):\n{protocol_section}"
                )
                skinmax_protocol_added = True

            # --- BoneMax notification engine (jaw / posture / SMS alignment) ---
            if s.maxx_id == "bonemax" and not bonemax_protocol_added:
                from services.guideline_service import get_maxx_guideline_async
                from services.maxx_guidelines import MAXX_GUIDELINES, build_bonemax_prompt_section

                guideline_b = await get_maxx_guideline_async("bonemax", rds_db)
                if not guideline_b:
                    guideline_b = MAXX_GUIDELINES.get("bonemax") or {}
                wt = ctx.get("wake_time") or onboarding.get("wake_time") or "07:00"
                st = ctx.get("sleep_time") or onboarding.get("sleep_time") or "23:00"
                other_ids = [
                    str(x.maxx_id) for x in schedules if x is not s and x.maxx_id
                ]
                bonemax_block = build_bonemax_prompt_section(
                    guideline_b,
                    onboarding=onboarding,
                    wake_time=str(wt),
                    sleep_time=str(st),
                    other_active_maxx_ids=other_ids,
                    for_coaching=True,
                )
                parts.append(
                    f"BONEMAX NOTIFICATION ENGINE (reference for jaw + posture + routine):\n{bonemax_block}"
                )
                bonemax_protocol_added = True

            if s.maxx_id == "heightmax" and not heightmax_protocol_added:
                from services.guideline_service import (
                    build_heightmax_protocol_section,
                    get_maxx_guideline_async,
                )
                from services.maxx_guidelines import MAXX_GUIDELINES, build_heightmax_prompt_section

                guideline_h = await get_maxx_guideline_async("heightmax", rds_db)
                if not guideline_h:
                    guideline_h = MAXX_GUIDELINES.get("heightmax") or {}
                hcomp = ctx.get("height_components")
                if isinstance(hcomp, dict):
                    height_components = {str(k): bool(v) for k, v in hcomp.items()}
                else:
                    height_components = None
                tracks_body = build_heightmax_protocol_section(guideline_h, height_components)
                active_labels: list[str] = []
                protos = guideline_h.get("protocols") or {}
                if height_components:
                    for k, p in protos.items():
                        if height_components.get(k, True) and isinstance(p, dict):
                            active_labels.append(str(p.get("label", k)))
                else:
                    for k, p in protos.items():
                        if isinstance(p, dict):
                            active_labels.append(str(p.get("label", k)))
                htf = ""
                if active_labels:
                    htf = (
                        "\n## HEIGHTMAX — ENABLED TRACKS ONLY\n"
                        f"Enabled tracks: {', '.join(active_labels)}.\n"
                    )
                wt = ctx.get("wake_time") or onboarding.get("wake_time") or "07:00"
                st = ctx.get("sleep_time") or onboarding.get("sleep_time") or "23:00"
                others = [str(x.maxx_id) for x in schedules if x is not s and x.maxx_id]
                age_v = onboarding.get("age")
                hm_block = build_heightmax_prompt_section(
                    tracks_protocol_text=tracks_body,
                    height_track_footer=htf,
                    onboarding=onboarding,
                    wake_time=str(wt),
                    sleep_time=str(st),
                    age_val=age_v,
                    other_active_maxx_ids=others,
                    for_coaching=True,
                )
                parts.append(
                    f"HEIGHTMAX NOTIFICATION ENGINE (reference for posture + sleep + sprints):\n{hm_block}"
                )
                heightmax_protocol_added = True

            if s.maxx_id == "hairmax" and not hairmax_protocol_added:
                from services.maxx_guidelines import (
                    HAIRMAX_PROTOCOLS,
                    build_hairmax_prompt_section,
                    resolve_hair_concern,
                )

                concern_h = ctx.get("skin_concern")
                if not concern_h or concern_h not in HAIRMAX_PROTOCOLS:
                    concern_h = resolve_hair_concern(
                        onboarding.get("hair_type"),
                        explicit_concern=ctx.get("skin_concern"),
                        has_thinning=bool(
                            onboarding.get("hair_thinning") or onboarding.get("thinning")
                        ),
                    )
                wt = ctx.get("wake_time") or onboarding.get("wake_time") or "07:00"
                st = ctx.get("sleep_time") or onboarding.get("sleep_time") or "23:00"
                others = [str(x.maxx_id) for x in schedules if x is not s and x.maxx_id]
                hair_block = build_hairmax_prompt_section(
                    concern_h,
                    onboarding=onboarding,
                    wake_time=str(wt),
                    sleep_time=str(st),
                    other_active_maxx_ids=others,
                    for_coaching=True,
                )
                parts.append(
                    f"HAIRMAX NOTIFICATION ENGINE (reference for hair loss stack + routine):\n{hair_block}"
                )
                hairmax_protocol_added = True

            if s.maxx_id == "fitmax" and not fitmax_protocol_added:
                from services.guideline_service import get_maxx_guideline_async
                from services.maxx_guidelines import MAXX_GUIDELINES, build_fitmax_prompt_section

                guideline_f = await get_maxx_guideline_async("fitmax", rds_db)
                if not guideline_f:
                    guideline_f = MAXX_GUIDELINES.get("fitmax") or {}
                concern_f = ctx.get("selected_concern") or ctx.get("skin_concern")
                protos_fm = guideline_f.get("protocols") or {}
                if not concern_f or concern_f not in protos_fm:
                    from services.fitmax_notification_engine import resolve_fitmax_phase

                    concern_f = resolve_fitmax_phase(onboarding)
                wt = ctx.get("wake_time") or onboarding.get("wake_time") or "07:00"
                st = ctx.get("sleep_time") or onboarding.get("sleep_time") or "23:00"
                others = [str(x.maxx_id) for x in schedules if x is not s and x.maxx_id]
                fm_block = build_fitmax_prompt_section(
                    concern_f,
                    guideline_f,
                    onboarding=onboarding,
                    wake_time=str(wt),
                    sleep_time=str(st),
                    other_active_maxx_ids=others,
                    for_coaching=True,
                )
                parts.append(
                    f"FITMAX NOTIFICATION ENGINE (reference for training + nutrition + body-comp SMS):\n{fm_block}"
                )
                fitmax_protocol_added = True

        # --- AI memory ---
        if user.ai_context:
            parts.append(f"MEMORY (from past convos):\n{user.ai_context}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Check-in message generation — fully AI-driven, no hardcoded tone
    # ------------------------------------------------------------------

    async def _prepare_check_in_prompts(
        self,
        user_id: str,
        db: AsyncSession,
        rds_db,
        check_in_type: str,
        missed_today: int,
    ) -> tuple[str | None, str]:
        """DB-only: Fitmax-specific prompt if applicable, plus general fallback prompt."""
        context_str = await self.build_full_context(user_id, db, rds_db)
        if not context_str:
            context_str = "No context yet."

        user = await db.get(User, UUID(user_id))
        name = (user.first_name or user.email.split("@")[0]) if user else "there"

        fitmax_result = await db.execute(
            select(UserSchedule).where(
                (UserSchedule.user_id == UUID(user_id))
                & (UserSchedule.maxx_id == "fitmax")
                & (UserSchedule.is_active == True)
            ).order_by(UserSchedule.created_at.desc()).limit(1)
        )
        fitmax_schedule = fitmax_result.scalar_one_or_none()

        n_active_result = await db.execute(
            select(UserSchedule).where(
                (UserSchedule.user_id == UUID(user_id)) & (UserSchedule.is_active == True)
            )
        )
        n_active_schedules = len(list(n_active_result.scalars().all()))
        multi_module_sms_hint = ""
        if n_active_schedules > 1:
            multi_module_sms_hint = (
                "\n\nThey have multiple active modules and get schedule task SMS. "
                "Do not duplicate generic good-morning or vague check-in copy — one specific, additive angle only."
            )

        fitmax_prompt = None
        if fitmax_schedule:
            fit_tmpl = await asyncio.to_thread(
                resolve_prompt,
                PromptKey.COACHING_FITMAX_CHECK_IN,
                _COACHING_FITMAX_CHECK_IN_FALLBACK,
            )
            fitmax_prompt = fit_tmpl.format(
                name=name,
                check_in_type=check_in_type,
                missed_today=missed_today,
                context_str=context_str,
                multi_module_sms_hint=multi_module_sms_hint,
            )

        missed_line = (
            f"\nThey missed {missed_today} task(s) today." if missed_today > 0 else ""
        )
        gen_tmpl = await asyncio.to_thread(
            resolve_prompt,
            PromptKey.COACHING_CHECK_IN_GENERAL,
            _COACHING_CHECK_IN_GENERAL_FALLBACK,
        )
        prompt = gen_tmpl.format(
            name=name,
            context_str=context_str,
            multi_module_sms_hint=multi_module_sms_hint,
            check_in_type=check_in_type,
            missed_line=missed_line,
        )

        return fitmax_prompt, prompt

    async def generate_check_in_message(
        self,
        user_id: str,
        db: Optional[AsyncSession] = None,
        rds_db=None,
        check_in_type: str = "midday",
        missed_today: int = 0,
    ) -> str:
        """
        Generate a check-in message using AI. Passes full context; AI decides tone and content.
        check_in_type: morning, midday, night, missed_task, weekly

        Pass db=None from background jobs so the DB connection is released before Gemini runs
        (avoids exhausting Supabase Session pooler slots).
        """
        if db is not None:
            fitmax_prompt, general_prompt = await self._prepare_check_in_prompts(
                user_id, db, rds_db, check_in_type, missed_today
            )
        else:
            async with AsyncSessionLocal() as inner:
                fitmax_prompt, general_prompt = await self._prepare_check_in_prompts(
                    user_id, inner, rds_db, check_in_type, missed_today
                )

        if fitmax_prompt:
            try:
                return await asyncio.to_thread(_sync_gemini_plain_text, fitmax_prompt)
            except Exception as e:
                logger.error(f"Fitmax check-in generation failed: {e}")

        try:
            return await asyncio.to_thread(_sync_gemini_plain_text, general_prompt)
        except Exception as e:
            logger.error(f"Check-in generation failed: {e}")
            return "yo, checking in — how you doing today?"

    async def _prepare_bedtime_prompt(
        self, user_id: str, db: AsyncSession, rds_db
    ) -> tuple[str, str]:
        """Returns (gemini_prompt, fallback_sms_with_name_placeholder filled)."""
        context_str = await self.build_full_context(user_id, db, rds_db)
        if not context_str:
            context_str = "No context yet."
        user = await db.get(User, UUID(user_id))
        name = (user.first_name or user.email.split("@")[0]) if user else "there"

        bed_tmpl = await asyncio.to_thread(
            resolve_prompt, PromptKey.COACHING_BEDTIME, _COACHING_BEDTIME_FALLBACK
        )
        prompt = bed_tmpl.format(name=name, context_snippet=context_str[:2500])

        fallback = (
            f"hey {name} — almost bedtime. if you want to log today's progress, just reply to this text "
            "with a selfie or progress pic and i'll drop it in your archive."
        )
        return prompt, fallback

    async def generate_bedtime_progress_picture_prompt(
        self,
        user_id: str,
        db: Optional[AsyncSession] = None,
        rds_db=None,
    ) -> str:
        """
        Short SMS before bedtime: casual Max voice + explicit instruction to reply with a photo via MMS.
        Use db=None from the scheduler so connections are not held during Gemini.
        """
        if db is not None:
            prompt, fallback = await self._prepare_bedtime_prompt(user_id, db, rds_db)
        else:
            async with AsyncSessionLocal() as inner:
                prompt, fallback = await self._prepare_bedtime_prompt(user_id, inner, rds_db)

        try:
            text = await asyncio.to_thread(_sync_gemini_plain_text, prompt)
            if text:
                return text
        except Exception as e:
            logger.error("Bedtime progress prompt generation failed: %s", e)

        return fallback


coaching_service = CoachingService()
