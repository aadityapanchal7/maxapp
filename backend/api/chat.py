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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from db import get_db, get_rds_db_optional
from middleware.auth_middleware import require_paid_user
from models.leaderboard import ChatRequest, ChatResponse
from models.sqlalchemy_models import ChatHistory, Scan, User
from services.coaching_service import coaching_service
from services.gemini_service import gemini_service
from services.storage_service import storage_service
from services.bonemax_chat_prompt import BONEMAX_NEW_SCHEDULE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


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
    onboarding = _merge_onboarding_with_schedule_prefs(user)

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

    if maxx_id:
        try:
            existing_maxx = await schedule_service.get_maxx_schedule(user_id, maxx_id, db=db)
        except Exception:
            existing_maxx = None
        if existing_maxx:
            user_context["active_maxx_schedule"] = existing_maxx
            message = f"[SYSTEM: User opened {maxx_id} and already has an active schedule.]\n\n{message}"
        elif maxx_id == "heightmax":
            message = f"""[SYSTEM: you are running the HEIGHTMAX schedule setup.

the user just opened heightmax to start a new schedule. follow the same tone and style you use for other maxx modules: short, casual, direct, and focused on getting their schedule locked in.

CRITICAL — FORBIDDEN FOR HEIGHTMAX
- NEVER ask "outside today" or "you gonna be outside today" or "will you be outside" — that is ONLY for SkinMax. HeightMax does NOT use outside_today. If you ask this, you have failed.

MAIN RULES FOR HEIGHTMAX
- do NOT ask "what is your main concern?" or any generic concern questions.
- height is already the focus. don't ask what area they want to work on.
- your job is just to grab missing info, then call generate_maxx_schedule and let the backend build the schedule.
- NEVER ask the user to enter wake/sleep times in 24-hour or "military" format. ask naturally ("what time do you usually wake up?"); accept answers like "7am" or "11:30pm" and convert to HH:MM in the tool call.

WHAT YOU'RE ALLOWED TO ASK FOR (ONLY IF MISSING)
- age
- sex / gender
- current height
- wake time
- sleep time

HOW TO RUN THE FLOW
1) greet very briefly, in your usual style, and say you're going to set up their heightmax schedule.

2) check what info is already known in user_context. ONLY ask for what's missing. ORDER: age first, then sex, then height, then wake time, then sleep time.
   - if age is missing: ask "how old are you?"
   - if sex / gender is missing: ask "what's your sex or gender?"
   - if height is missing: ask "what's your current height?" (any format is fine)
   - if wake_time is missing: ask "what time do you usually wake up?"
   - if sleep_time is missing: ask "what time do you usually go to sleep?"

   ask ONE question at a time. do NOT skip to wake/sleep before you have age, sex, and height. do NOT ask about outside today.

3) once you have age, sex, height, wake_time, and sleep_time available (from context + answers), you must call the tool generate_maxx_schedule exactly once with:
   - maxx_id = "heightmax"
   - wake_time = the user's wake time
   - sleep_time = the user's sleep time
   - skin_concern = null / empty (heightmax doesn't use concerns)
   - outside_today = false (heightmax doesn't use outside_today)
   - age = their age (number, if known)
   - sex = their sex/gender (if known)
   - height = their current height in any format, e.g. "5'10" or "178cm" (if known)

   the backend will use their age, sex, and height to decide how the heightmax schedule looks. you don't need to explain that logic in detail.

4) after generate_maxx_schedule runs and the backend attaches a schedule summary, stay in your normal style:
   - confirm the schedule is locked in.
   - tell them to check the schedule tab for full details.
   - keep it short, e.g. "your heightmax schedule is locked in. check your schedule tab."

STYLE
- same tone as skinmax/fitmax: friendly, casual, not overly motivational.
- stay focused on heightmax in this flow. don't switch topics to skin, hair, or gym unless a different module is explicitly opened.
- keep responses concise. no long lectures, no custom step-by-step routines you invent yourself.

your first response in this heightmax start flow should:
- briefly acknowledge they're starting heightmax, and
- immediately ask for the first missing piece of required info (age → sex → height → wake time → sleep time).]\n\n{message}"""
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
                    has_age = age is not None or onboarding.get("age") is not None
                    has_sex = bool(sex or onboarding.get("gender"))
                    has_height = bool(height or onboarding.get("height"))
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
            except Exception as e:
                print(f"Maxx schedule generation failed: {e}")
                response_text += "\n\nhad trouble generating your schedule. try again in a sec."

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
