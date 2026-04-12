"""
LangChain Tool-Calling Agent for Max Chat.

Replaces the manual two-pass (pass-1 tool-detect → dispatch in chat.py → pass-2 synthesise)
with a proper AgentExecutor loop:

  1. LLM receives system prompt + history + user message + tool schemas
  2. LLM decides whether/which tools to call
  3. AgentExecutor executes the tools (real async implementations — not stubs)
  4. LLM receives tool results and synthesises a final user-facing response
  5. Repeat until done or max_iterations reached

All tool business logic that previously lived in chat.py's for-tool dispatch block
is now here as real async functions using closure capture for DB/user context.
No direct google.generativeai / openai / mistralai SDK imports — everything through
LangChain providers (lc_providers.py).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool

from config import settings
from services.lc_memory import history_dicts_to_lc_messages
from services.lc_providers import get_chat_llm_with_tools_and_fallback
from services.prompt_constants import MAX_CHAT_SYSTEM_PROMPT
from services.prompt_loader import PromptKey, resolve_prompt
from services.sms_reply_style import sms_chat_appendix

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper functions (copied from api/chat.py to avoid circular import)
# ---------------------------------------------------------------------------

def _normalize_clock_hhmm(raw: Optional[str]) -> Optional[str]:
    """Normalise to HH:MM (24 h). Accepts 24 h clock or 12 h with am/pm."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    m12 = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?|am|pm)\s*$", s, re.I)
    if m12:
        h = int(m12.group(1))
        mn = int(m12.group(2) or 0)
        ap = m12.group(3).lower().replace(".", "")
        if mn > 59 or h < 1 or h > 12:
            return s[:32]
        if ap.startswith("a"):
            h = 0 if h == 12 else h
        else:
            h = 12 if h == 12 else h + 12
        return f"{h:02d}:{mn:02d}"
    m24 = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m24:
        h, mn = int(m24.group(1)), int(m24.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return f"{h:02d}:{mn:02d}"
    return s[:32]


def _safe_int_age(val) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, int) and 8 <= val <= 100:
        return val
    if isinstance(val, float) and not (val != val):
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


def _yes_no_answered(val) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return True
    s = str(val).strip().lower()
    return s in ("yes", "no", "y", "n", "true", "false", "1", "0")


def _normalize_hair_yes_no(val) -> Optional[str]:
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


def _infer_skin_concern_id_from_onboarding(ob: dict) -> Optional[str]:
    if not ob:
        return None
    primary = str(ob.get("primary_skin_concern") or "").strip().lower()
    secondary = str(ob.get("secondary_skin_concern") or "").strip().lower()
    keyword_to_id = [
        (("acne", "breakout", "blemish", "pimple", "blackhead"), "acne"),
        (("pigment", "dark spot", "melasma", "hyperpigmentation", "uneven tone"), "pigmentation"),
        (("texture", "scar", "scarring", "pores"), "texture"),
        (("red", "sensitive", "rosacea", "irritat"), "redness"),
        (("aging", "wrinkle", "fine line", "anti-aging"), "aging"),
    ]
    for text in (primary, secondary):
        if not text:
            continue
        for keywords, concern_id in keyword_to_id:
            if any(kw in text for kw in keywords):
                return concern_id
    return None


def _summarise_schedule(schedule: dict) -> str:
    days = schedule.get("days", [])
    if not days:
        return "schedule created. check your Schedule tab."
    first_day = days[0]
    tasks = first_day.get("tasks", [])
    title = (schedule.get("course_title") or schedule.get("maxx_id") or "schedule").strip()
    lines = [f"your {title} schedule is locked in.", "", "day 1:"]
    for t in tasks[:5]:
        lines.append(f"  {t.get('time', '??:??')} — {t.get('title', 'Task')}")
    if len(tasks) > 5:
        lines.append(f"  +{len(tasks) - 5} more")
    lines.append(f"\n{len(days)} days planned. check Schedule tab.")
    return "\n".join(lines)


async def _persist_user_wake_sleep(user, db, wake_time, sleep_time) -> None:
    from sqlalchemy.orm.attributes import flag_modified

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


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

async def build_agent_system_prompt(
    user_context: Optional[dict],
    delivery_channel: str,
) -> str:
    """Build the full system prompt for the agent (same logic as _lc_chat in llm_router)."""
    chat_prompt = await asyncio.to_thread(
        resolve_prompt, PromptKey.MAX_CHAT_SYSTEM, MAX_CHAT_SYSTEM_PROMPT
    )

    context_str = user_context.get("coaching_context", "") if user_context else ""
    if not context_str and user_context:
        if user_context.get("latest_scan"):
            scan = user_context["latest_scan"]
            context_str += f"\nLATEST SCAN: score={scan.get('overall_score', '?')}/10"
            if scan.get("focus_areas"):
                context_str += f", focus={scan['focus_areas']}"
        if user_context.get("onboarding"):
            ob = user_context["onboarding"]
            bits = [
                f"{k}: {', '.join(v) if isinstance(v, list) else v}"
                for k, v in ob.items()
                if v and k in ("skin_type", "goals", "gender", "age")
            ]
            if bits:
                context_str += f"\nPROFILE: {' | '.join(bits)}"
        if user_context.get("active_schedule"):
            schedule = user_context["active_schedule"]
            label = schedule.get("course_title") or schedule.get("maxx_id") or "?"
            context_str += f"\nSCHEDULE: {label}"
        if user_context.get("active_maxx_schedule"):
            ms = user_context["active_maxx_schedule"]
            context_str += f"\nActive {ms.get('maxx_id')} schedule exists."

    if context_str:
        chat_prompt += f"\n\n## USER CONTEXT:\n{context_str}"

    sms_extra = sms_chat_appendix(delivery_channel)
    if sms_extra:
        chat_prompt += "\n\n" + sms_extra

    return chat_prompt


# ---------------------------------------------------------------------------
# Real tool implementations — closures capturing DB session and user context
# ---------------------------------------------------------------------------

def make_chat_tools(
    db,
    rds_db,
    user_id: str,
    user,
    onboarding: dict,
    active_schedule: Optional[dict],
    channel: str,
) -> list:
    """
    Create real async tool implementations as closures that capture the
    DB session, user model, and per-request context.

    Each tool executes the same business logic that previously lived in
    chat.py's manual tool dispatch block.
    """
    from services.schedule_service import schedule_service, ScheduleLimitError
    from services.coaching_service import coaching_service
    from services.maxx_guidelines import SKINMAX_PROTOCOLS, resolve_skin_concern

    # ------------------------------------------------------------------ #
    #  modify_schedule                                                     #
    # ------------------------------------------------------------------ #
    @tool
    async def modify_schedule(feedback: str) -> str:
        """
        Modify the user's active schedule from natural language feedback.
        Only call when the user explicitly requests calendar or task changes.
        """
        if not active_schedule:
            return "no active schedule to modify"
        try:
            result = await schedule_service.adapt_schedule(
                user_id=user_id,
                schedule_id=active_schedule["id"],
                db=db,
                feedback=feedback,
            )
            return result.get("changes_summary", "schedule updated")
        except Exception as e:
            logger.exception("modify_schedule tool failed: %s", e)
            return f"could not update schedule: {e}"

    # ------------------------------------------------------------------ #
    #  generate_maxx_schedule                                              #
    # ------------------------------------------------------------------ #
    @tool
    async def generate_maxx_schedule(
        maxx_id: str,
        wake_time: str = "07:00",
        sleep_time: str = "23:00",
        outside_today: bool = False,
        skin_concern: Optional[str] = None,
        age: Optional[int] = None,
        sex: Optional[str] = None,
        gender: Optional[str] = None,
        height: Optional[str] = None,
        hair_type: Optional[str] = None,
        scalp_state: Optional[str] = None,
        daily_styling: Optional[str] = None,
        thinning: Optional[str] = None,
        hair_thinning: Optional[str] = None,
        workout_frequency: Optional[str] = None,
        tmj_history: Optional[str] = None,
        mastic_gum_regular: Optional[str] = None,
        heavy_screen_time: Optional[str] = None,
    ) -> str:
        """
        Generate a personalised maxx schedule after required onboarding fields are collected.
        maxx_id must be one of: skinmax, heightmax, hairmax, fitmax, bonemax.
        Returns a summary of day 1 tasks or an error message listing what is missing.
        """
        try:
            req_maxx = str(maxx_id or "skinmax").strip().lower()
            _age = _safe_int_age(age)
            _sex = sex or gender
            final_wake = (
                _normalize_clock_hhmm(wake_time)
                or _normalize_clock_hhmm(onboarding.get("wake_time"))
                or "07:00"
            )
            final_sleep = (
                _normalize_clock_hhmm(sleep_time)
                or _normalize_clock_hhmm(onboarding.get("sleep_time"))
                or "23:00"
            )

            # Resolve skin concern for skinmax
            if req_maxx == "skinmax":
                sc_str = str(skin_concern or "").strip().lower()
                resolved_concern = (
                    sc_str if sc_str in SKINMAX_PROTOCOLS
                    else (
                        _infer_skin_concern_id_from_onboarding(onboarding)
                        or resolve_skin_concern(
                            str(onboarding.get("skin_type") or "").strip() or None, None
                        )
                    )
                )
            else:
                resolved_concern = skin_concern or onboarding.get("skin_type")

            # HeightMax: validate demographics
            if req_maxx == "heightmax":
                has_age = _age is not None or _safe_int_age(onboarding.get("age")) is not None
                ob_sex = str(onboarding.get("gender") or onboarding.get("sex") or "").strip()
                has_sex = bool((_sex and str(_sex).strip()) or ob_sex)
                ob_h = onboarding.get("height")
                has_height = bool(
                    (height and str(height).strip())
                    or (ob_h and str(ob_h).strip())
                )
                missing = []
                if not has_age:
                    missing.append("age")
                if not has_sex:
                    missing.append("sex/gender")
                if not has_height:
                    missing.append("height")
                if missing:
                    return f"missing required fields for heightmax: {', '.join(missing)}"

            # HairMax: validate hair fields
            if req_maxx == "hairmax":
                _ht = hair_type or onboarding.get("hair_type")
                _ss = scalp_state or onboarding.get("scalp_state")
                _ds = daily_styling if daily_styling is not None else onboarding.get("daily_styling")
                _th = (
                    thinning or hair_thinning
                    or onboarding.get("hair_thinning")
                    or onboarding.get("thinning")
                )
                if not _yes_no_answered(_th):
                    hcl = str(onboarding.get("hair_current_loss") or "").lower()
                    if any(w in hcl for w in ("yes", "yeah", "yep", "reced", "thin", "losing", "balding", "some")):
                        _th = "yes"
                    elif any(w in hcl for w in ("no", "nope", "none", "not really", "minimal", "little")):
                        _th = "no"
                missing = []
                if not str(_ht or "").strip():
                    missing.append("hair_type")
                if not str(_ss or "").strip():
                    missing.append("scalp_state")
                if not _yes_no_answered(_ds):
                    missing.append("daily_styling (yes/no)")
                if not _yes_no_answered(_th):
                    missing.append("thinning (yes/no)")
                if missing:
                    return f"missing required fields for hairmax: {', '.join(missing)}"

            # BoneMax: validate bone fields
            wf = tmj_raw = gum_raw = scr_raw = None
            if req_maxx == "bonemax":
                wf = (workout_frequency or onboarding.get("bonemax_workout_frequency") or "").strip()
                tmj_raw = tmj_history if tmj_history is not None else onboarding.get("bonemax_tmj_history")
                gum_raw = mastic_gum_regular if mastic_gum_regular is not None else onboarding.get("bonemax_mastic_gum_regular")
                scr_raw = heavy_screen_time if heavy_screen_time is not None else onboarding.get("bonemax_heavy_screen_time")
                missing = []
                if not wf:
                    missing.append("workout_frequency (0, 1-2, 3-4, or 5+)")
                if not _yes_no_answered(tmj_raw):
                    missing.append("tmj_history (yes/no)")
                if not _yes_no_answered(gum_raw):
                    missing.append("mastic_gum_regular (yes/no)")
                if not _yes_no_answered(scr_raw):
                    missing.append("heavy_screen_time (yes/no)")
                if missing:
                    return f"missing required fields for bonemax: {', '.join(missing)}"

            # For HeightMax: persist age/sex/height to onboarding so future API calls see them
            if req_maxx == "heightmax" and user:
                from sqlalchemy.orm.attributes import flag_modified as _flag_modified
                ra = _age or _safe_int_age(onboarding.get("age"))
                rs = (str(_sex).strip() if _sex else "") or str(onboarding.get("gender") or "").strip()
                rh = (str(height).strip() if height and str(height).strip() else "") or str(onboarding.get("height") or "").strip()
                ob = dict(user.onboarding or {})
                if ra is not None:
                    ob["age"] = ra
                if rs:
                    ob["gender"] = rs
                if rh:
                    ob["height"] = rh
                user.onboarding = ob
                _flag_modified(user, "onboarding")
                await db.flush()

            schedule = await schedule_service.generate_maxx_schedule(
                user_id=user_id,
                maxx_id=req_maxx,
                db=db,
                rds_db=rds_db,
                wake_time=final_wake,
                sleep_time=final_sleep,
                skin_concern=resolved_concern,
                outside_today=False if req_maxx in ("fitmax", "hairmax") else bool(outside_today),
                override_age=_age,
                override_sex=_sex,
                override_height=str(height).strip() if height and str(height).strip() else None,
                override_hair_type=(hair_type or onboarding.get("hair_type") or "").strip() or None,
                override_scalp_state=(scalp_state or onboarding.get("scalp_state") or "").strip() or None,
                override_daily_styling=_normalize_hair_yes_no(
                    daily_styling if daily_styling is not None else onboarding.get("daily_styling")
                ),
                override_thinning=_normalize_hair_yes_no(
                    thinning or hair_thinning
                    or onboarding.get("hair_thinning")
                    or onboarding.get("thinning")
                ),
                override_workout_frequency=wf,
                override_tmj_history=_normalize_hair_yes_no(tmj_raw),
                override_mastic_gum_regular=_normalize_hair_yes_no(gum_raw),
                override_heavy_screen_time=_normalize_hair_yes_no(scr_raw),
            )
            await _persist_user_wake_sleep(user, db, final_wake, final_sleep)
            return _summarise_schedule(schedule)

        except ScheduleLimitError as e:
            names = ", ".join(e.active_labels)
            return (
                f"schedule limit reached: you already have 2 active modules ({names}). "
                "stop one first."
            )
        except Exception as e:
            logger.exception("generate_maxx_schedule tool failed: %s", e)
            return f"schedule generation failed — try again in a moment"

    # ------------------------------------------------------------------ #
    #  stop_schedule                                                       #
    # ------------------------------------------------------------------ #
    @tool
    async def stop_schedule(maxx_id: str) -> str:
        """
        Deactivate a module schedule when the user wants to stop it.
        maxx_id must be one of: skinmax, heightmax, hairmax, fitmax, bonemax.
        """
        if channel == "sms":
            return "stopping modules can only be done in the app"
        try:
            result = await schedule_service.deactivate_schedule_by_maxx(
                user_id, maxx_id.strip().lower(), db
            )
            if result:
                return f"{maxx_id} schedule stopped"
            return f"no active {maxx_id} schedule found"
        except Exception as e:
            logger.exception("stop_schedule tool failed: %s", e)
            return f"could not stop {maxx_id}: {e}"

    # ------------------------------------------------------------------ #
    #  update_schedule_context                                             #
    # ------------------------------------------------------------------ #
    @tool
    async def update_schedule_context(key: str, value: str) -> str:
        """
        Store a schedule habit context value, e.g. outside_today, wake_time, sleep_time.
        """
        try:
            lk = key.lower().replace("-", "_")
            if lk in ("wake_time", "sleep_time", "preferred_wake_time", "preferred_sleep_time"):
                wk = value if "wake" in lk else None
                sk = value if "sleep" in lk else None
                await _persist_user_wake_sleep(user, db, wk, sk)
            if active_schedule and key:
                await schedule_service.update_schedule_context(
                    user_id=user_id,
                    schedule_id=active_schedule["id"],
                    db=db,
                    context_updates={key: value},
                )
            return f"{key}={value} saved"
        except Exception as e:
            logger.exception("update_schedule_context tool failed: %s", e)
            return f"context update failed: {e}"

    # ------------------------------------------------------------------ #
    #  log_check_in                                                        #
    # ------------------------------------------------------------------ #
    @tool
    async def log_check_in(
        workout_done: Optional[bool] = None,
        missed: Optional[bool] = None,
        sleep_hours: Optional[float] = None,
        calories: Optional[int] = None,
        mood: Optional[str] = None,
        injury_area: Optional[str] = None,
        injury_note: Optional[str] = None,
    ) -> str:
        """
        Log check-in data ONLY when user explicitly reports their day —
        e.g. 'i did my workout', 'slept 7 hours', 'ate 1800 cals', 'missed today'.
        Do NOT call for questions or casual chat.
        """
        try:
            check_in_data: dict = {}
            parts: list[str] = []
            if workout_done:
                check_in_data["workout_done"] = True
                parts.append("workout=done")
            if missed:
                check_in_data["missed"] = True
                parts.append("missed=true")
            if sleep_hours is not None:
                check_in_data["sleep_hours"] = sleep_hours
                parts.append(f"sleep={sleep_hours}h")
            if calories is not None:
                check_in_data["calories"] = calories
                parts.append(f"calories={calories}")
            if mood:
                check_in_data["mood"] = mood
                parts.append(f"mood={mood}")
            if injury_area:
                check_in_data["injury"] = {
                    "area": injury_area,
                    "note": injury_note or "",
                }
                parts.append(f"injury={injury_area}")
            if check_in_data:
                await coaching_service.process_check_in(user_id, db, check_in_data)
            return "check-in logged: " + (", ".join(parts) or "data saved")
        except Exception as e:
            logger.exception("log_check_in tool failed: %s", e)
            return f"check-in failed: {e}"

    # ------------------------------------------------------------------ #
    #  set_coaching_mode                                                   #
    # ------------------------------------------------------------------ #
    @tool
    async def set_coaching_mode(mode: str) -> str:
        """
        Set coaching intensity. Call when user says 'be harder on me', 'go easy',
        'tough love', 'be more chill', 'back to normal'.
        mode must be: hardcore, gentle, or default.
        """
        try:
            from sqlalchemy.orm.attributes import flag_modified as _flag_modified

            mode_clean = str(mode).lower().strip()
            if mode_clean not in ("hardcore", "gentle", "default"):
                mode_clean = "default"
            if user:
                prof = dict(user.profile or {})
                prof["coaching_mode"] = mode_clean
                user.profile = prof
                _flag_modified(user, "profile")
                user.updated_at = datetime.utcnow()
                await db.commit()
                coaching_service.invalidate_context_cache(user_id)
            return f"coaching mode set to {mode_clean}"
        except Exception as e:
            logger.exception("set_coaching_mode tool failed: %s", e)
            return f"could not set coaching mode: {e}"

    # ------------------------------------------------------------------ #
    #  get_today_tasks                                                     #
    # ------------------------------------------------------------------ #
    @tool
    async def get_today_tasks() -> str:
        """
        Return today's task list from all active schedules.
        ONLY call when user explicitly asks what tasks or schedule they have today.
        Do NOT call for greetings or general questions.
        """
        try:
            tz_name = (onboarding or {}).get("timezone") or "UTC"
            try:
                user_tz = ZoneInfo(tz_name)
            except Exception:
                user_tz = ZoneInfo("UTC")
            today_iso = datetime.now(user_tz).date().isoformat()
            all_scheds = await schedule_service.get_all_active_schedules(user_id, db)
            tasks_out: list[str] = []
            for s in all_scheds:
                mod = s.get("maxx_id") or s.get("course_title") or "program"
                for day in s.get("days") or []:
                    if day.get("date") != today_iso:
                        continue
                    for t in day.get("tasks") or []:
                        tasks_out.append(
                            f"{t.get('time', '?')} {t.get('title', '?')} "
                            f"[{t.get('status', 'pending')}] ({mod})"
                        )
            brief = "; ".join(tasks_out[:12])
            if len(tasks_out) > 12:
                brief += f" +{len(tasks_out) - 12} more"
            return brief or "no tasks scheduled today"
        except Exception as e:
            logger.exception("get_today_tasks tool failed: %s", e)
            return "could not load today's tasks"

    # ------------------------------------------------------------------ #
    #  get_module_info                                                     #
    # ------------------------------------------------------------------ #
    @tool
    async def get_module_info(module: str, topic: Optional[str] = None) -> str:
        """
        Fetch protocol/coaching reference for a module.
        Use when user asks a detailed how-to or protocol question about a specific module.
        module must be one of: skinmax, hairmax, fitmax, bonemax, heightmax.
        """
        try:
            mod = str(module).lower().strip()
            tp = str(topic or "").lower().strip()
            ref_path = os.path.normpath(
                os.path.join(
                    os.path.dirname(__file__),
                    f"{mod}_notification_engine_reference.md",
                )
            )
            if not mod or not os.path.exists(ref_path):
                return f"no reference found for {mod}"
            with open(ref_path, "r", encoding="utf-8") as f:
                content = f.read()
            if tp:
                lines = content.split("\n")
                result_lines: list[str] = []
                in_section = False
                for line in lines:
                    if tp in line.lower():
                        in_section = True
                    if in_section:
                        result_lines.append(line)
                        if len(result_lines) >= 30:
                            break
                excerpt = "\n".join(result_lines).strip() or content[:1500]
            else:
                excerpt = content[:1500]
            return f"[{mod} reference]\n{excerpt[:1200]}"
        except Exception as e:
            logger.exception("get_module_info tool failed: %s", e)
            return "could not load module info"

    # ------------------------------------------------------------------ #
    #  recommend_product                                                   #
    # ------------------------------------------------------------------ #
    @tool
    async def recommend_product(module: str, concern: str) -> str:
        """
        Get product/ingredient recommendations for a module and concern.
        Use when user asks what to buy or what products to use.
        module: skinmax, hairmax, fitmax, bonemax, heightmax.
        """
        try:
            mod = str(module).lower().strip()
            con = str(concern).lower().strip()
            ref_path = os.path.normpath(
                os.path.join(
                    os.path.dirname(__file__),
                    f"{mod}_notification_engine_reference.md",
                )
            )
            if not mod or not os.path.exists(ref_path):
                return f"no product reference found for {mod}"
            with open(ref_path, "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n")
            prod_lines: list[str] = []
            in_section = not bool(con)
            for line in lines:
                if con and con in line.lower():
                    in_section = True
                if in_section:
                    stripped = line.strip()
                    if stripped and any(
                        kw in line.lower()
                        for kw in (
                            "cerave", "paula", "nizoral", "minoxidil", "finasteride",
                            "retinol", "retinoid", "niacinamide", "vitamin", "spf",
                            "sunscreen", "serum", "moisturizer", "cleanser", "shampoo",
                            "conditioner", "dermastamp", "dermaroller", "falim",
                            "mastic", "protein", "creatine", "zinc", "magnesium",
                            "omega", "collagen", "biotin", "caffeine",
                        )
                    ):
                        prod_lines.append(stripped)
                    if len(prod_lines) >= 8:
                        break
            result = "; ".join(prod_lines[:5])[:300] if prod_lines else content[:300]
            return f"[{mod}/{con} products]\n{result}"
        except Exception as e:
            logger.exception("recommend_product tool failed: %s", e)
            return "could not load product recommendations"

    return [
        modify_schedule,
        generate_maxx_schedule,
        stop_schedule,
        update_schedule_context,
        log_check_in,
        set_coaching_mode,
        get_today_tasks,
        get_module_info,
        recommend_product,
    ]


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

async def run_chat_agent(
    message: str,
    lc_history: List[BaseMessage],
    user_context: Optional[dict],
    image_data: Optional[bytes],
    delivery_channel: str,
    tools: list,
) -> tuple[str, bool]:
    """
    Run the tool-calling AgentExecutor and return (response_text, schedule_mutated).

    schedule_mutated=True when any schedule-modifying tool (generate, modify, stop)
    fired — used by chat.py for cache invalidation.

    The agent handles the full reasoning → tool call → observe → respond loop.
    max_iterations=4 allows: tool call → observe → (optional second tool) → final answer.
    """
    system_prompt = await build_agent_system_prompt(user_context, delivery_channel)

    # Image: inject as multimodal content part in the human message
    if image_data:
        import base64
        b64 = base64.b64encode(image_data).decode()
        input_content: str | list = [
            {"type": "text", "text": message or ""},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]
    else:
        input_content = message or ""

    prompt = ChatPromptTemplate.from_messages([
        ("system", "{system_prompt}"),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    llm = get_chat_llm_with_tools_and_fallback(tools, max_tokens=768)
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=4,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
        verbose=False,
    )

    # Budget: pass 1 + tool execution(s) + pass 2 — generous for schedule gen
    call_timeout = float(settings.llm_timeout_seconds) * 4

    logger.info("[AGENT] user channel=%s msg=%.80s", delivery_channel, message or "")

    result = await asyncio.wait_for(
        executor.ainvoke({
            "input": input_content,
            "chat_history": lc_history,
            "system_prompt": system_prompt,
        }),
        timeout=call_timeout,
    )

    response_text = (result.get("output") or "").strip()

    # Track which tools fired
    tool_names_fired: set[str] = set()
    for step in result.get("intermediate_steps") or []:
        action = step[0]
        if hasattr(action, "tool"):
            tool_names_fired.add(action.tool)

    if tool_names_fired:
        logger.info("[AGENT] tools fired: %s", ", ".join(sorted(tool_names_fired)))
    else:
        logger.info("[AGENT] no tools — response: %.150s", response_text[:150])

    schedule_mutated = bool(
        tool_names_fired & {"generate_maxx_schedule", "modify_schedule", "stop_schedule"}
    )

    return response_text, schedule_mutated
