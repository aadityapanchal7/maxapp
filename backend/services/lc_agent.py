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
import contextvars
import logging
import os
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Per-turn product sink. recommend_product appends catalog hits here so the
# chat API can return a STRUCTURED `products` array (name/brand/url/description/
# image) instead of relying on the LLM to emit well-formed inline markdown
# links. Reset at the start of each chat turn; read after the agent finishes.
# A ContextVar keeps it task-local (safe under concurrent requests).
_products_ctx: contextvars.ContextVar[Optional[list]] = contextvars.ContextVar(
    "recommended_products", default=None
)


def reset_recommended_products() -> list:
    """Start a fresh per-turn product sink and return it."""
    sink: list = []
    _products_ctx.set(sink)
    return sink


def get_recommended_products() -> list[dict]:
    """Return the products collected this turn (deduped by url, max 6)."""
    sink = _products_ctx.get()
    if not sink:
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for p in sink:
        url = (p or {}).get("url") or ""
        key = url or (p or {}).get("name") or ""
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(p)
        if len(out) >= 6:
            break
    return out


def _collect_recommended_products(hits: list) -> None:
    """Append catalog ProductHits to the per-turn sink as card dicts. Live
    (non-catalog) hits are skipped — they have no curated name/brand/image."""
    sink = _products_ctx.get()
    if sink is None:
        return
    for h in hits or []:
        try:
            if getattr(h, "source", "") != "catalog":
                continue
            sink.append({
                "name": getattr(h, "name", "") or "",
                "brand": getattr(h, "brand", "") or "",
                "url": getattr(h, "url", "") or "",
                "description": getattr(h, "snippet", "") or "",
                "image": getattr(h, "image", "") or "",
            })
        except Exception:
            continue


def record_catalog_products(products: list) -> None:
    """Append catalog Product objects (resolved from prose mentions by the
    link validator) to the per-turn sink as card dicts. Called from
    link_validator so the products we surface as cards are exactly the ones
    Max named in the message — authoritative name/brand/url + our-words blurb."""
    sink = _products_ctx.get()
    if sink is None:
        return
    for p in products or []:
        try:
            sink.append({
                "name": getattr(p, "name", "") or "",
                "brand": getattr(p, "brand", "") or "",
                "url": getattr(p, "display_url", None) or getattr(p, "url", "") or "",
                "description": getattr(p, "rationale", "") or "",
                "image": getattr(p, "image", "") or "",
            })
        except Exception:
            continue

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool

from config import settings
from services import fitmax_plan as fplan
from services.chat_telemetry import log_agent_run, log_prompt_budget
from services.lc_memory import history_dicts_to_lc_messages
from services.lc_providers import get_chat_llm_with_tools_and_fallback
from services.prompt_constants import MAX_CHAT_SYSTEM_PROMPT, CHAT_VISUAL_GRAMMAR
from services.fast_rag_answer import _TABLE_REQUEST_RE as _AGENT_TABLE_REQUEST_RE
from services.prompt_loader import PromptKey, resolve_prompt
from services.sms_reply_style import sms_chat_appendix
from services.token_budget import count_tokens, trim_context_blob, trim_text_block

logger = logging.getLogger(__name__)

# Map canonical MCQ chip values → (domain label, action verb) for chip-answer detection.
# When a user message exactly matches one of these (stripped, lowercased), it is a
# chip answer to the previous turn's clarifying question — the model must NOT ask
# another clarifying question; it should give actionable advice immediately.
_CHIP_ANSWER_MAP: dict[str, tuple[str, str]] = {
    # hair goal chips
    "less thinning":    ("hair thinning", "provide hair-thinning advice"),
    "more growth":      ("hair growth", "provide hair-growth advice"),
    "dandruff/scalp":   ("scalp / dandruff", "provide scalp and dandruff advice"),
    "styling":          ("hair styling", "provide hair-styling advice"),
    "general health":   ("general hair health", "provide general hair-health advice"),
    # skin goal chips
    "clearer skin":     ("skin clarity", "provide a clear-skin routine"),
    "less acne":        ("acne", "provide an acne-fighting routine"),
    "anti-aging":       ("anti-aging", "provide an anti-aging skincare routine"),
    "even texture":     ("skin texture", "provide a skin-texture routine"),
    "hydration":        ("skin hydration", "provide a hydration routine"),
    # workout goal chips
    "build muscle":     ("muscle building", "provide a muscle-building plan"),
    "lose fat":         ("fat loss", "provide a fat-loss plan"),
    "get stronger":     ("strength", "provide a strength training plan"),
    "general fitness":  ("general fitness", "provide a general fitness plan"),
    # nutrition goal chips
    "fat loss":         ("fat loss nutrition", "provide fat-loss nutrition advice"),
    "muscle gain":      ("muscle gain nutrition", "provide muscle-gain nutrition advice"),
    "more energy":      ("energy / nutrition", "provide energy-boosting nutrition advice"),
}

# Per-request surface for a schedule-change proposal created during this turn.
# api/chat.py calls reset_proposed_change() at turn start, then the
# propose_schedule_change tool MUTATES the shared dict (NOT a .set() — langchain
# runs the tool coroutine in a copied context, so a re-set would not propagate;
# mutating the same dict object does, exactly like the recommended-products sink).
# api/chat.py reads get_proposed_change() after the agent to attach Yes/No.
_proposed_change_ctx: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "proposed_schedule_change", default=None
)


def reset_proposed_change() -> dict:
    """Start a fresh per-turn proposal sink (a mutable dict) and return it."""
    sink: dict = {}
    _proposed_change_ctx.set(sink)
    return sink


def get_proposed_change() -> Optional[dict]:
    """Return {proposal_id, summary} if a proposal was made this turn, else None."""
    sink = _proposed_change_ctx.get()
    if sink and sink.get("proposal_id"):
        return {"proposal_id": sink["proposal_id"], "summary": sink.get("summary", "")}
    return None


def _detect_image_mime(image_data: bytes) -> str:
    """Infer data: URL MIME type from image magic bytes (defaults to image/jpeg)."""
    if not image_data:
        return "image/jpeg"
    h = image_data[:16]
    if len(h) >= 3 and h[0:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(h) >= 8 and h[0:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(h) >= 6 and h[0:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(h) >= 12 and h[0:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "image/webp"
    if len(h) >= 2 and h[0:2] == b"BM":
        return "image/bmp"
    return "image/jpeg"


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


def _extract_wake_sleep_from_feedback(feedback: str) -> dict[str, Optional[str]]:
    """Extract likely wake/sleep times from natural-language schedule feedback."""
    result: dict[str, Optional[str]] = {"wake": None, "sleep": None}
    text = str(feedback or "").strip().lower()
    if not text:
        return result

    wake_patterns = (
        r"(?:wake|waking|wake up|wakeup)(?:\s+(?:at|around|by|to))?\s*(\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|am|pm)?)",
        r"(\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|am|pm)?)\s*(?:wake|wakeup)",
    )
    sleep_patterns = (
        r"(?:sleep|sleeping|bedtime|go to bed|bed)(?:\s+(?:at|around|by|to))?\s*(\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|am|pm)?)",
        r"(\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|am|pm)?)\s*(?:sleep|bedtime|bed)",
    )

    for pattern in wake_patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            result["wake"] = _normalize_clock_hhmm(m.group(1))
            break

    for pattern in sleep_patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            result["sleep"] = _normalize_clock_hhmm(m.group(1))
            break

    return result


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


_BONEMAX_WF_ALLOWED = frozenset({"0", "1-2", "3-4", "5+"})


def _normalize_bonemax_workout_frequency(raw: Optional[str]) -> Optional[str]:
    """Map user/LLM strings to canonical bonemax workout_frequency or None if invalid."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", "", s)
    if s in _BONEMAX_WF_ALLOWED:
        return s
    if s in ("5plus", "5ormore", "6+", "7+", "daily", "everyday"):
        return "5+"
    if s in ("3to4", "3_4"):
        return "3-4"
    if s in ("1to2", "1_2"):
        return "1-2"
    if s in ("0", "none", "sedentary", "inactive"):
        return "0"
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
        lines.append(f"  {t.get('time', '??:??')}, {t.get('title', 'Task')}")
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

    # Re-expand every active doc-driven schedule so AM/PM task times shift
    # to the new wake/sleep. Skeleton expand is <1ms — cheap to do eagerly.
    # Skipped silently for users with no active doc-driven schedules.
    try:
        from services.schedule_runtime import regenerate_active_schedules
        await regenerate_active_schedules(
            user_id=str(user.id), db=db, reason="wake_sleep_change",
        )
    except Exception as _e:
        logger.warning("regen after wake/sleep change failed (non-fatal): %s", _e)


# Map the timing-anchor keys the bot may pass to their canonical onboarding
# field. These are the precise times that re-anchor whole windows across every
# active maxx (see schedule_dsl.build_anchor_overrides).
_TIMING_ANCHOR_KEYS: dict[str, str] = {
    "preferred_workout_time": "preferred_workout_time",
    "workout_time": "preferred_workout_time",
    "get_ready_time": "get_ready_time",
    "shower_time": "get_ready_time",
}


async def _persist_onboarding_clock(user, db, key: str, value) -> bool:
    """Persist one HH:MM timing anchor onto user.onboarding — the canonical
    store the Edit-Lifestyle UI also reads/writes. Returns True if changed.
    Caller is responsible for triggering schedule regen afterwards."""
    from sqlalchemy.orm.attributes import flag_modified

    if not user:
        return False
    norm = _normalize_clock_hhmm(value) if value and str(value).strip() else None
    if not norm:
        return False
    ob = dict(user.onboarding or {})
    if ob.get(key) == norm:
        return False
    ob[key] = norm
    user.onboarding = ob
    flag_modified(user, "onboarding")
    await db.flush()
    return True


async def _persist_get_ready_minutes(user, db, value) -> bool:
    """Persist the morning get-ready DURATION (minutes) onto user.onboarding —
    same canonical store the Edit-Lifestyle UI reads/writes, so the chatbot and
    the UI never diverge. Clamped to [10, 90]. Returns True if changed; caller
    triggers regen."""
    from sqlalchemy.orm.attributes import flag_modified

    if not user:
        return False
    try:
        mins = int(round(float(str(value).strip())))
    except (TypeError, ValueError):
        return False
    mins = max(10, min(90, mins))
    ob = dict(user.onboarding or {})
    if ob.get("get_ready_minutes") == mins:
        return False
    ob["get_ready_minutes"] = mins
    user.onboarding = ob
    flag_modified(user, "onboarding")
    await db.flush()
    return True


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

async def build_agent_system_prompt(
    user_context: Optional[dict],
    delivery_channel: str,
) -> str:
    """Build the full system prompt for the agent (same logic as _lc_chat in llm_router)."""
    chat_prompt = resolve_prompt(PromptKey.MAX_CHAT_SYSTEM, MAX_CHAT_SYSTEM_PROMPT)

    context_str = user_context.get("coaching_context", "") if user_context else ""
    # Unified per-user brief injection: what Max already knows (so it never
    # re-asks) + facts it's UNCERTAIN about (so it confirms rather than silently
    # acting on stale info). Populated by the chat handler from assemble_user_brief.
    if user_context:
        _known = (user_context.get("known_summary") or "").strip()
        if _known:
            context_str += f"\nKNOWN ABOUT THIS USER (do not re-ask): {_known}"
        _confirm = user_context.get("confirm_facts") or []
        if _confirm:
            _cf = "; ".join(str(c) for c in _confirm[:4])
            context_str += ("\nUNCERTAIN — briefly confirm with the user before relying on these "
                            "(e.g. \"still true that …?\"), don't assume: " + _cf)
        _recall = user_context.get("recall") or []
        if _recall:
            _rc = " | ".join(str(r) for r in _recall[:3])
            context_str += ("\nFROM EARLIER CHATS (recall naturally, don't make them repeat): " + _rc)
    if not context_str and user_context:
        if user_context.get("latest_scan"):
            scan = user_context["latest_scan"]
            # Only surface the scan line when there's a real score — a truthy-but
            # -empty scan dict otherwise leaks "LATEST SCAN: score=?/10".
            scan_score = scan.get("overall_score")
            if scan_score not in (None, "", "?"):
                context_str += f"\nLATEST SCAN: score={scan_score}/10"
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
            # Daily availability — chatbot uses this to plan around work
            # hours and respect the user's wake/sleep window. Without it
            # the bot suggests routines at times the user is unavailable
            # (e.g. "morning skincare at 8am" when they're commuting).
            wake = (ob.get("wake_time") or "").strip()
            sleep = (ob.get("sleep_time") or "").strip()
            work_sched = (ob.get("work_schedule") or "").strip().lower()
            work_start = (ob.get("work_start") or "").strip()
            work_end = (ob.get("work_end") or "").strip()
            avail_bits: list[str] = []
            if wake:
                avail_bits.append(f"wakes {wake}")
            if sleep:
                avail_bits.append(f"sleeps {sleep}")
            if work_sched == "fixed" and work_start and work_end:
                avail_bits.append(f"busy {work_start}–{work_end} (work/school)")
            elif work_sched == "flexible":
                avail_bits.append("flexible work/school hours")
            # Custom recurring obligations the user set in the Day Planner
            # (gym class, school pickup, commute, etc.). Same treatment as
            # work hours — the bot must never plan a routine on top of them.
            obligations = ob.get("obligations")
            if isinstance(obligations, list):
                for item in obligations:
                    if not isinstance(item, dict):
                        continue
                    o_start = (item.get("start") or "").strip()
                    o_end = (item.get("end") or "").strip()
                    o_label = (item.get("label") or "obligation").strip()
                    if o_start and o_end:
                        avail_bits.append(f"busy {o_start}–{o_end} ({o_label})")
            # When the user usually showers — skincare and other shower-dependent
            # routines (cleanser, body care, minoxidil on dry hair, etc.) should
            # land right after a shower, not at an arbitrary time.
            shower = (ob.get("shower_time") or "").strip().lower()
            shower_phrase = {
                "morning": "showers in the morning (right after waking)",
                "night": "showers at night (before bed)",
                "both": "showers both morning and night",
            }.get(shower)
            if shower_phrase:
                avail_bits.append(shower_phrase)
            if avail_bits:
                context_str += (
                    f"\nDAILY AVAILABILITY: {' | '.join(avail_bits)}"
                    f"\n(plan routines around the busy window; AM tasks before "
                    f"the busy block, PM tasks after; never schedule during it)"
                )
                if shower_phrase:
                    _anchor_when = {
                        "morning": "the morning get-ready window",
                        "night": "the wind-down window before bed",
                        "both": "either the morning or the evening shower",
                    }[shower]
                    context_str += (
                        f"\n(anchor skincare and shower-dependent routines to "
                        f"{_anchor_when} so they happen right after a shower)"
                    )
            # Per-weekday overrides from the Planner tab — only days that
            # differ from the default rhythm. The bot must honor the right
            # day's window/obligations (e.g. a later weekend wake, MWF class).
            weekly = ob.get("weekly_timings")
            if isinstance(weekly, dict):
                _wk_order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                _wk_abbr = {
                    "monday": "Mon", "tuesday": "Tue", "wednesday": "Wed", "thursday": "Thu",
                    "friday": "Fri", "saturday": "Sat", "sunday": "Sun",
                }
                wk_lines: list[str] = []
                for d in _wk_order:
                    ov = weekly.get(d)
                    if not isinstance(ov, dict) or not ov:
                        continue
                    db: list[str] = []
                    if ov.get("wake_time"):
                        db.append(f"wakes {ov['wake_time']}")
                    if ov.get("sleep_time"):
                        db.append(f"sleeps {ov['sleep_time']}")
                    if ov.get("preferred_workout_time"):
                        db.append(f"workout {ov['preferred_workout_time']}")
                    if ov.get("work_schedule") == "fixed" and ov.get("work_start") and ov.get("work_end"):
                        db.append(f"busy {ov['work_start']}–{ov['work_end']} (work/school)")
                    obs = ov.get("obligations")
                    if isinstance(obs, list):
                        for it in obs:
                            if isinstance(it, dict) and it.get("start") and it.get("end"):
                                db.append(f"busy {it['start']}–{it['end']} ({(it.get('label') or 'obligation').strip()})")
                    if db:
                        wk_lines.append(f"{_wk_abbr[d]}: {', '.join(db)}")
                if wk_lines:
                    context_str += "\nWEEKLY OVERRIDES (per day): " + " | ".join(wk_lines)
        if user_context.get("active_schedule"):
            schedule = user_context["active_schedule"]
            # Skip the line entirely when there's no real label, rather than
            # leaking a dangling "SCHEDULE: ?".
            label = schedule.get("course_title") or schedule.get("maxx_id")
            if label:
                context_str += f"\nSCHEDULE: {label}"
        if user_context.get("active_maxx_schedule"):
            ms = user_context["active_maxx_schedule"]
            context_str += f"\nActive {ms.get('maxx_id')} schedule exists."

    # Unified hyper-personalization brief — the assembled "what Max knows about
    # this user" across identity, culture, diet, work, rhythm, personality and
    # communication style, merged from onboarding + things they've told the chat
    # + Onairos inference (services.personalization). Injected so every reply is
    # tailored to the real person. Placed BELOW the diet absolute-rules block
    # (which prepends after this) so allergy/diet safety stays the top directive.
    try:
        if user_context:
            brief = (user_context.get("personalization_brief")
                     or (user_context.get("persistent_context") or {}).get("personalization_brief"))
            if brief:
                chat_prompt = f"{brief}\n\n---\n\n" + chat_prompt
    except Exception:
        pass

    # Long-term user facts (vegetarian, allergic-to, eczema, lives-in, etc.)
    # come from user_schedule_context.user_facts — extracted from chat passively
    # by services.user_facts_service. Inject NEAR THE TOP of the system prompt
    # with a forceful directive so RAG-retrieved content gets filtered through
    # them, not regurgitated verbatim.
    try:
        if user_context:
            facts_blob = (user_context.get("user_facts")
                          or (user_context.get("persistent_context") or {}).get("user_facts")) or {}
            # Fold in durable onboarding profile facts (wake/sleep, skin/hair
            # type, equipment, ...) so a fact captured in ANY maxx's setup is
            # part of KNOWN PROFILE and never re-asked. user_facts wins on
            # conflict (it reflects the most recent thing the user told chat).
            from services.user_facts_service import format_facts_for_prompt, facts_from_onboarding
            ob_facts = facts_from_onboarding((user_context or {}).get("onboarding"))
            merged_facts = {**ob_facts, **(facts_blob or {})} if (ob_facts or facts_blob) else {}
            if merged_facts:
                facts_str = format_facts_for_prompt(merged_facts)
                if facts_str:
                    # Placement matters for instruction-following. Anchor at top.
                    from services.user_facts_service import DIET_SUBSTITUTIONS
                    chat_prompt = (
                        "## ABSOLUTE RULES (override anything below)\n"
                        "When you make ANY recommendation (foods, products, "
                        "supplements, exercises, routines), you MUST filter "
                        "through KNOWN USER FACTS below. NEVER suggest, name, "
                        "reference, or compare against items the user said "
                        "they avoid, are allergic to, or that conflict with "
                        "their diet — even if a retrieved doc lists them, and "
                        "even in headers, titles, or educational explanations. "
                        "Do not write the forbidden ingredient's name anywhere "
                        "in your response. Rewrite forbidden items as "
                        "substitutions from the SUBSTITUTION GUIDE.\n\n"
                        "EXAMPLE: User is vegetarian. Doc says 'eat meat, "
                        "fish, eggs, beans'. Your answer: 'eat eggs, beans, "
                        "lentils, tofu, tempeh', NOT 'eat meat, fish, eggs, "
                        "beans'.\n\n"
                        f"{facts_str}\n\n"
                        f"{DIET_SUBSTITUTIONS}\n"
                        "---\n\n"
                    ) + chat_prompt
    except Exception:
        pass

    # Web-search fallback policy — appended to whichever prompt we ended
    # up with. Tells the agent when to escalate beyond the doc layer.
    chat_prompt += (
        # ── HUMAN VOICE — non-negotiable formatting rules ────────────
        # The base prompt above (max_chat_system) tries to set voice,
        # but the model still leaks AI-template tells under load. These
        # rules are appended AFTER the base prompt for higher recency
        # weight. Server-side post-processor (api/chat.py
        # _finalize_assistant_message) hard-strips violations as a
        # belt-and-suspenders enforcement — break these rules and the
        # user never sees the violation.
        "\n\n## VOICE: SOUND LIKE A REAL PERSON, NOT AN AI\n"
        # The em-dash ban lives once in the shared VOICE rules (persona_prompts
        # _GLOBAL_VOICE, injected via USER CONTEXT) and is enforced in
        # post-processing; it is intentionally NOT repeated here.
        "Hard rules (auto-stripped if violated, so just follow them):\n"
        "1. NEVER open with: 'Certainly', 'Of course', 'Absolutely', "
        "'Great question', 'Awesome question', 'I'd be happy to', "
        "'Let me break this down', 'It's important to note', 'As an "
        "AI', 'As your coach'. These are AI tells. Open with the "
        "answer.\n"
        "2. NEVER close with: 'I hope this helps', 'Hope that helps', "
        "'Feel free to ask', 'Let me know if you have any questions'. "
        "End on the last useful sentence. No sign-off.\n"
        "3. STRUCTURE multi-point answers. If your answer is 3+ tips / "
        "steps / points / reasons, OR describes a routine / regimen / "
        "protocol / how-to with multiple actions, you MUST output a "
        "NUMBERED markdown list (`1. ...` `2. ...` each on its own line), "
        "and the lead phrase of each item MUST be in **bold**. NEVER write "
        "a multi-step routine as a flowing paragraph. For example a skincare "
        "routine MUST look like:\n"
        "1. **cleanser**: wash with a gentle cleanser morning and night.\n"
        "2. **moisturizer**: lock in hydration to repair the barrier.\n"
        "3. **sunscreen**: spf 30+ every morning, no exceptions.\n"
        "A dense paragraph for a listy/routine answer does NOT pass review. "
        "A single-fact or 1-2 sentence answer stays short prose, do NOT "
        "force a list onto it.\n"
        "4. Each line / bullet under ~140 chars. Phone bubble is "
        "narrow; long lines wrap weirdly.\n"
        "5. Lowercase. Direct. No hype words ('amazing', 'incredible', "
        "'fantastic'). Real coach voice.\n"
        "## SOUND HUMAN — DO THIS (not just avoid the tells)\n"
        "Avoiding AI tells isn't enough; a person has warmth, takes, and a "
        "pulse. So:\n"
        "- React before you inform. Clock their mood from the message (hyped, "
        "frustrated, insecure, joking) and meet it in the FIRST line, then "
        "help. A person answers a person before answering a question.\n"
        "- Have takes. Pick a side and say it plain ('honestly, skip that one'). "
        "Confidence reads human; hedging and both-sides-ing read like a bot.\n"
        "- Vary the rhythm. Mix a 1-3 word line with a longer one. Fragments are "
        "fine when they land harder. Never the same paragraph shape twice.\n"
        "- Use what you know about them like a friend who was listening: call "
        "back a real detail from USER CONTEXT ('you said fragrance wrecks your "
        "skin, so skip this'). Never re-introduce yourself or restate who you "
        "are.\n"
        "- Dry humor and the occasional 'honestly' / 'lol' / 'ngl' when it's "
        "real, never forced. Emoji almost never.\n"
        "- You can think out loud and self-correct ('actually, scratch that, do "
        "X instead'). That's how people text.\n"
        "## NEVER RE-ASK KNOWN FACTS\n"
        "USER CONTEXT has a `KNOWN PROFILE` block with every fact the user "
        "already gave (age, sex, height, wake/sleep, work hours, concerns, "
        "history, experience, equipment, diet). Treat it as ground truth: never "
        "re-ask any of those, even when starting a new module, use them "
        "silently. Only ask for the new fields specific to the new maxx (e.g. "
        "user has wake=07:00 from hairmax -> don't re-ask it for skinmax).\n"
        "## PRODUCT LINKS: SURFACE PROACTIVELY\n"
        "EXCEPTION FIRST: if it's a BROAD personal-rec question and you don't yet "
        "know the fact that decides the pick (skin type, hair type, main concern, "
        "goal), ASK the clarifying MCQ first (see CLARIFY section) -- do NOT dump a "
        "covers-everyone routine or recommend products yet. Only surface products "
        "once you know enough.\n"
        "Be eager, the user shouldn't have to ask. Call "
        "`recommend_product(module, concern)` when: "
        "(a) they ask for a product/brand/link or 'what should i buy/use/get'; "
        "(b) you name any specific brand/product/supplement (cerave, the "
        "ordinary, niacinamide, creatine, minoxidil) even unasked; (c) your "
        "reply describes a routine with a product category (cleanser, "
        "moisturizer, spf, shampoo, protein, multivitamin), surface 1 pick.\n"
        "HOW THE LINKS SHOW UP: the app renders the recommended products as "
        "tappable preview CARDS under your message automatically -- you do NOT "
        "paste links. Just mention the product conversationally BY NAME in your "
        "prose (e.g. 'grab the cerave hydrating cleanser') and let the card carry "
        "the link.\n"
        "RULES:\n"
        "1. NEVER paste a URL or markdown link in your reply. No "
        "`[Name](https://...)`, no naked amazon.com links, no `(url)`/`(#)`/"
        "`(...)`. The cards handle all links; a link in your prose is WRONG.\n"
        "2. Still call recommend_product so the cards populate -- naming the "
        "product without calling it means no card shows.\n"
        "3. If `recommend_product` returns nothing (rare), give the protocol "
        "with plain ingredient names, no apology.\n"
        "4. Dietary/sensitivity facts already filtered the catalog, trust it.\n"
    )
    chat_prompt += (
        "\n\n## CLARIFY VAGUE QUESTIONS WITH MCQ\n"
        "For a BROAD personal-rec question -- 'what should i use/do/take/eat', "
        "'build me a routine/workout', 'help with my <skin/hair/diet>', 'where do "
        "i start' -- whose right answer DEPENDS on a fact you don't already have "
        "from KNOWN PROFILE, do NOT dump a generic protocol. LEAD with ONE focused "
        "clarifying question + 2-6 short (1-5 word) tappable options via a marker "
        "at the END of your reply. This takes PRECEDENCE over surfacing products: "
        "ask first, recommend after they answer. A clarifying question written as "
        "plain prose with no marker is WRONG -- it MUST be a marker so chips "
        "render.\n"
        "  Single-pick (one answer fits, e.g. skin type, experience level): "
        "[CHOICES]option a|option b|option c[/CHOICES]\n"
        "  Multi-pick (several apply, e.g. concerns, symptoms, equipment, "
        "allergies): [CHOICES_MULTI]option a|option b[/CHOICES_MULTI]\n"
        "CUSTOM ANSWER: add `Something else` as the LAST option ONLY when a real "
        "answer could fall outside your list (open-ended 'what's bothering you', "
        "goals, preferences, symptoms) -- the app turns it into a type-your-own "
        "box. Do NOT add it to closed questions with a fixed set (skin type, "
        "experience level, biological sex, yes/no, equipment).\n"
        "Examples: 'help with skin' -> 'what's bothering you?' [CHOICES_MULTI]"
        "acne|dryness|oily|sensitive|redness|Something else[/CHOICES_MULTI]  /  "
        "'what skincare should i use' -> 'what's your skin type?' [CHOICES]oily|dry|"
        "combo|sensitive|not sure[/CHOICES]  /  'start working out' -> 'what do you "
        "have access to?' [CHOICES]full gym|home dumbbells|bodyweight[/CHOICES]\n"
        "HARD RULE: if your reply asks the user for a fact (skin type, hair type, "
        "goal, main concern, equipment, days/week, experience) you MUST attach a "
        "CHOICES/CHOICES_MULTI marker for THAT question. Asking a fact-question in "
        "prose with no marker is a failure. 'what skincare should i use' and 'help "
        "with my hair' are NOT answerable without skin/hair type -- ASK with a "
        "marker, never give an everyone-routine.\n"
        "ASK only when you're actually missing the fact you'd need. If KNOWN "
        "PROFILE already answers it, or it's a SPECIFIC or general-knowledge "
        "question ('what % niacinamide', 'is creatine safe', 'how much protein per "
        "day'), answer directly -- NO marker.\n"
        "EXCEPTION — TABLE REQUESTS: if the user mentions 'table' or asks to put "
        "values in a table, this is NOT a broad question requiring clarification. "
        "See the TABLE BLOCK RULE in STRUCTURED VISUALS: build the table NOW with "
        "a reasonable default topic (e.g. AM/PM skincare routine). Never ask "
        "'what should the table show?'.\n"
    )
    chat_prompt += (
        "\n\n## WEB SEARCH FALLBACK\n"
        "If the user asks a factual/how-to/current-info question your docs (or "
        "search_knowledge) don't cover, call `web_search` with a short 3-8 word "
        "query before saying you don't have it (ingredient lookups, exercise "
        "form, product comparisons, brand info, dosing). Ground the answer in "
        "the snippets, don't invent details, cite at most one URL inline. Don't "
        "web_search for: this user's data, schedule ops, small talk, or "
        "restating yourself.\n"
    )
    chat_prompt += (
        # ── PLANNER SYNC — single source of truth ────────────────────
        # The Planner / schedule tab renders the EXACT same UserSchedule
        # store these tools read and write (master_schedule.build_master_view).
        # There is no separate "reminders" store. So anything time-bound the
        # user sees must go through a schedule tool, and the bot must never
        # claim a change it didn't actually persist (the planner would not
        # show it, and the user would catch the lie).
        "\n\n## PLANNER SYNC — REMINDERS/TASKS LIVE IN THE SCHEDULE\n"
        "The Planner tab and your schedule tools are the SAME thing. Every "
        "task, reminder, and time-block the user sees in the planner comes "
        "from the one schedule your tools read and write. There is no separate "
        "reminder list.\n"
        "1. Any reminder, task, time, or routine change you agree to, you MUST "
        "make it real by calling a schedule tool (generate_maxx_schedule, "
        "modify_schedule, edit_schedule_task, delete_schedule_task, "
        "complete_schedule_task, update_schedule_preferences). That tool write "
        "is the ONLY thing the planner shows.\n"
        "2. NEVER say something is set, added, moved, reminded, scheduled, or "
        "done unless you actually called the tool this turn and it succeeded. "
        "Saying 'got it, i'll remind you at 8' without a tool call is a lie, "
        "the planner stays empty. No phantom reminders.\n"
        "3. When you DO call a tool, the planner updates automatically, you "
        "don't paste times back as if that's the record. Make your words match "
        "exactly what you persisted (same task, same time).\n"
        "4. A 'reminder' is just a task in their routine schedule. To add or "
        "change one, edit/generate the schedule, don't invent a side channel. "
        "If you genuinely can't persist what they asked, say so plainly instead "
        "of pretending it's scheduled.\n"
        "\n## CHANGING A PLAN — PROPOSE FIRST, NEVER SILENTLY EDIT\n"
        "When the user wants to CHANGE part of their plan — 'i don't like this "
        "workout plan', 'change my diet', 'swap the heightmax tasks', 'make it "
        "easier', 'move it later', 'fewer days', or anything similar — you MUST "
        "call `propose_schedule_change` and let them confirm with Yes/No. Do NOT "
        "call modify_schedule / edit_schedule_task / delete_schedule_task / "
        "generate_maxx_schedule / update_schedule_context directly for these "
        "change-my-plan requests — those apply instantly with no confirmation. "
        "The only schedule mutation allowed without an explicit Yes is the user's "
        "own first-time setup of a brand-new max.\n"
        "1. Ground the proposal: pull the alternative from the coaching docs "
        "first (search_knowledge); if the docs don't cover it, use web_search. "
        "Never invent a protocol.\n"
        "2. Honor the ABSOLUTE RULES at the top: never propose a food/ingredient "
        "the user is allergic to or avoids; respect their diet pattern.\n"
        "3. Make ONE concrete proposal (not a menu), summarized in one sentence, "
        "then stop and let them tap Yes (apply) or No (you'll re-ask what they'd "
        "prefer). If they say No or type a tweak, propose again. Loop until Yes.\n"
        "4. Don't info-dump and don't apply silently — propose → Yes → apply.\n"
    )

    if context_str:
        bounded_context = trim_context_blob(
            context_str,
            max_tokens=int(getattr(settings, "chat_max_coaching_context_tokens", 1800) or 1800),
        )
        chat_prompt += f"\n\n## USER CONTEXT:\n{bounded_context}"

    sms_extra = sms_chat_appendix(delivery_channel)
    if sms_extra:
        chat_prompt += "\n\n" + sms_extra

    # Response-length preference — OVERRIDES any sentence-count rule in the base prompt.
    onboarding = (user_context or {}).get("onboarding") or {}
    length_pref = str(onboarding.get("response_length") or "").strip().lower()
    if length_pref == "concise":
        chat_prompt += (
            "\n\n## USER RESPONSE LENGTH PREFERENCE: CONCISE  (overrides all other length rules)\n"
            "- Hard cap: 1 sentence. 2 only if the question literally has two parts.\n"
            "- No bullets, no headers, no lists, no lead-ins (\"so basically…\", \"here's the thing…\").\n"
            "- Cut every word that isn't load-bearing. If you can't answer in one line, pick the single most useful thing and say it.\n"
            "- Never end with a question unless required to proceed (onboarding step)."
        )
    elif length_pref == "detailed":
        chat_prompt += (
            "\n\n## USER RESPONSE LENGTH PREFERENCE: DETAILED  (overrides all other length rules)\n"
            "- Up to ~8 sentences, or a tight bulleted structure. Still lowercase, still Max's voice, length is not license to pad.\n"
            "- Every expansion must add real info: mechanisms, exact protocols, numbers, evidence. If you catch yourself restating, stop.\n"
            "- Structure: direct answer → specifics (ingredient + %, time, reps, macros) → one sentence on why. No intros, no end-summaries.\n"
            "- Precedence: length sets how MUCH you say; your coach voice sets HOW. "
            "Even a terse persona (e.g. the hardcore coach) STILL delivers the full "
            "detail the user asked for here, do NOT go short on them. Give all the "
            "specifics, just in your own cadence: more concrete steps and short "
            "percussive hits rather than long flowing sentences."
        )
    else:
        chat_prompt += (
            "\n\n## USER RESPONSE LENGTH PREFERENCE: MEDIUM  (default)\n"
            "- 2-3 sentences. Or up to 4 short bullets if a list genuinely helps.\n"
            "- Answer first, then one concrete specific (product, dose, timing, or timeframe). No background, no throat-clearing."
        )

    system_budget = int(getattr(settings, "chat_max_system_prompt_tokens", 4096) or 4096)
    if count_tokens(chat_prompt) > system_budget:
        # Safety net only (the budget now fits a fully-loaded real-user prompt).
        # Size the preserved head/tail to the budget itself — the old fixed
        # 2200/900 chars slashed any over-budget prompt to ~780 tokens, dropping
        # the VOICE block + persona from the middle. Head pins the diet ABSOLUTE
        # RULES (top of prompt); tail pins the persona + length pref (end), so
        # both safety and voice survive even when the middle is trimmed.
        preserve_head = system_budget * 3                # ~diet rules + base + voice
        preserve_tail = max(1500, system_budget)         # ~persona + length pref
        chat_prompt = trim_text_block(
            chat_prompt,
            max_tokens=system_budget,
            preserve_head_chars=preserve_head,
            preserve_tail_chars=preserve_tail,
        )
    # Appended AFTER the token trim so the visual/confidence grammar always
    # survives (it's small + must reach the model intact to be usable).
    return chat_prompt + CHAT_VISUAL_GRAMMAR


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
    user_context: Optional[dict] = None,
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

    # Mutable: updated when generate_maxx_schedule creates a schedule so later
    # tools in the same agent turn see the new active schedule (not stale closure).
    schedule_state: dict = {"active": active_schedule}
    # Agent tool calls can arrive in quick succession (and some providers can emit
    # multiple tool calls in one turn). Serialize DB mutations so one AsyncSession
    # never commits concurrently.
    db_mutation_lock = asyncio.Lock()

    async def _safe_rollback() -> None:
        try:
            await db.rollback()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  modify_schedule                                                     #
    # ------------------------------------------------------------------ #
    @tool
    async def modify_schedule(feedback: str) -> str:
        """
        Modify the user's active schedule from natural language feedback.
        Call when user asks to change wake/sleep, task times, or schedule tasks.
        """
        cur = schedule_state.get("active")
        if not cur:
            return "no active schedule to modify"
        try:
            from services.schedule_runtime import adapt_and_persist
            async with db_mutation_lock:
                extracted = _extract_wake_sleep_from_feedback(feedback)
                if extracted["wake"] or extracted["sleep"]:
                    await _persist_user_wake_sleep(
                        user,
                        db,
                        extracted["wake"],
                        extracted["sleep"],
                    )
                result = await adapt_and_persist(
                    user_id=user_id,
                    schedule_id=cur["id"],
                    db=db,
                    feedback=feedback,
                )
            schedule_state["active"] = result
            coaching_service.invalidate_context_cache(user_id)
            return result.get("changes_summary", "schedule updated")
        except Exception as e:
            await _safe_rollback()
            logger.exception("modify_schedule tool failed: %s", e)
            err = str(e).lower()
            if "timeout" in err or "timed out" in err:
                return (
                    "schedule update timed out while adapting your plan. "
                    "try a shorter single change (for example: move workout to 18:30), "
                    "or retry in a moment."
                )
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
        body_weight_kg: Optional[float] = None,
        training_days_per_week: Optional[int] = None,
        training_experience: Optional[str] = None,
        fitmax_equipment: Optional[str] = None,
        session_minutes: Optional[int] = None,
        daily_activity_level: Optional[str] = None,
        dietary_restrictions: Optional[str] = None,
    ) -> str:
        """
        Generate a personalised maxx schedule after required onboarding fields are collected.
        maxx_id must be one of: skinmax, heightmax, hairmax, fitmax, bonemax.
        Returns a summary of day 1 tasks or an error message listing what is missing.
        """
        # ---- New doc-driven path -------------------------------------------------
        # If a max-doc exists for this maxx_id, route to the new generator.
        # All required-field validation, prompt assembly, task picking, validation
        # and persistence live there. No more per-max hardcoded logic here.
        try:
            from services.task_catalog_service import get_doc as _doc_get
            from services.schedule_runtime import generate_and_persist, ScheduleLimitError
        except Exception:
            _doc_get = None  # type: ignore
        req_maxx_early = str(maxx_id or "").strip().lower()
        if _doc_get is not None and _doc_get(req_maxx_early) is not None:
            try:
                # Merge tool args into onboarding overlay so required-field
                # validation in the generator sees them. Only set keys that were
                # actually provided by the model (skip the defaults).
                ob_overlay = dict(onboarding or {})
                _sex_local = sex or gender
                for k, v in (
                    ("skin_concern", skin_concern),
                    ("age", _safe_int_age(age)),
                    ("sex", _sex_local),
                    ("gender", gender),
                    ("height", height),
                    ("hair_type", hair_type),
                    ("scalp_state", scalp_state),
                    ("daily_styling", daily_styling),
                    ("hair_thinning", hair_thinning if hair_thinning is not None else thinning),
                    ("workout_frequency", workout_frequency),
                    ("tmj_history", tmj_history),
                    ("mastic_gum_regular", mastic_gum_regular),
                    ("heavy_screen_time", heavy_screen_time),
                ):
                    if v is not None and str(v).strip() != "":
                        ob_overlay[k] = v
                final_wake_n = _normalize_clock_hhmm(wake_time) or _normalize_clock_hhmm(onboarding.get("wake_time")) or "07:00"
                final_sleep_n = _normalize_clock_hhmm(sleep_time) or _normalize_clock_hhmm(onboarding.get("sleep_time")) or "23:00"
                async with db_mutation_lock:
                    await _persist_user_wake_sleep(user, db, final_wake_n, final_sleep_n)
                    result = await generate_and_persist(
                        user_id=user_id,
                        maxx_id=req_maxx_early,
                        db=db,
                        onboarding=ob_overlay,
                        wake_time=final_wake_n,
                        sleep_time=final_sleep_n,
                        subscription_tier=(getattr(user, "subscription_tier", None) if user else None),
                    )
                schedule_state["active"] = {
                    "id": result.get("id"),
                    "maxx_id": result.get("maxx_id"),
                    "course_title": result.get("course_title"),
                    "days": result.get("days") or [],
                }
                coaching_service.invalidate_context_cache(user_id)
                return result.get("summary") or _summarise_schedule(result)
            except ScheduleLimitError as e:
                names = ", ".join(e.active_labels)
                return (
                    f"schedule limit reached: you already have {len(e.active_labels)} active modules ({names}). "
                    "stop one first."
                )
            except ValueError as e:
                msg = str(e)
                if "missing required fields" in msg.lower() or "missing required" in msg.lower():
                    return msg
                logger.exception("new generator failed for %s: %s", req_maxx_early, e)
                return f"schedule generation failed: {msg}"
            except Exception as e:
                await _safe_rollback()
                logger.exception("new generator unexpected error for %s: %s", req_maxx_early, e)
                return "schedule generation failed, try again in a moment"

        # ---- Legacy path (no max-doc available — kept for migration window) -----
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
            elif req_maxx == "fitmax":
                resolved_concern = str(skin_concern or "").strip() or None
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
                wf_raw = (workout_frequency or onboarding.get("bonemax_workout_frequency") or "").strip()
                tmj_raw = tmj_history if tmj_history is not None else onboarding.get("bonemax_tmj_history")
                gum_raw = mastic_gum_regular if mastic_gum_regular is not None else onboarding.get("bonemax_mastic_gum_regular")
                scr_raw = heavy_screen_time if heavy_screen_time is not None else onboarding.get("bonemax_heavy_screen_time")
                missing = []
                if not wf_raw:
                    missing.append("workout_frequency (0, 1-2, 3-4, or 5+)")
                else:
                    wf_norm = _normalize_bonemax_workout_frequency(wf_raw)
                    if wf_norm is None:
                        return (
                            "bonemax workout_frequency must be one of: 0, 1-2, 3-4, 5+ "
                            f"(got: {wf_raw[:40]!r})"
                        )
                    wf = wf_norm
                if not _yes_no_answered(tmj_raw):
                    missing.append("tmj_history (yes/no)")
                if not (gum_raw is not None and str(gum_raw).strip()):
                    missing.append("mastic_gum_regular (jaw chew tolerance: strong/average/weak/painful)")
                if not _yes_no_answered(scr_raw):
                    missing.append("heavy_screen_time (yes/no)")
                if missing:
                    return f"missing required fields for bonemax: {', '.join(missing)}"

            # FitMax: merge tool + onboarding + profile, validate, persist, set schedule skin_concern label
            if req_maxx == "fitmax":
                if not user:
                    return "cannot generate fitmax schedule without a user context"
                from sqlalchemy.orm.attributes import flag_modified as _flag_modified_fm
                prof0 = dict((user.profile or {}).get("fitmax_profile") or {})
                merged_fm = fplan.seed_fitmax_profile_from_onboarding(dict(prof0), dict(onboarding or {}))
                fplan.merge_fitmax_tool_into_profile(
                    merged_fm,
                    age=_age,
                    sex=_sex,
                    gender=gender,
                    height_str=height,
                    skin_concern=skin_concern,
                    body_weight_kg=body_weight_kg,
                    training_days_per_week=training_days_per_week,
                    training_experience=training_experience,
                    fitmax_equipment=fitmax_equipment,
                    session_minutes=session_minutes,
                    daily_activity_level=daily_activity_level,
                    dietary_restrictions=dietary_restrictions,
                )
                miss_fm = fplan.fitmax_validate_required(merged_fm)
                if miss_fm:
                    return f"missing required fields for fitmax: {', '.join(miss_fm)}"
                fplan.persist_fitmax_to_user_onboarding(user, merged_fm)
                prof_m = dict((user.profile or {}).get("fitmax_profile") or {})
                prof_m.update(merged_fm)
                user.profile = {**(user.profile or {}), "fitmax_profile": prof_m}
                _flag_modified_fm(user, "profile")
                _flag_modified_fm(user, "onboarding")
                plan_prev = fplan.fitmax_build_plan(merged_fm)
                resolved_concern = (str(skin_concern or "").strip() or plan_prev["goal_label"])

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
            async with db_mutation_lock:
                if req_maxx == "fitmax":
                    await db.flush()
                if req_maxx == "heightmax" and user:
                    await db.flush()
                await _persist_user_wake_sleep(user, db, final_wake, final_sleep)

            yesno_overrides: dict = {}
            if req_maxx == "hairmax":
                _ds_src = daily_styling if daily_styling is not None else onboarding.get("daily_styling")
                _ds_n = _normalize_hair_yes_no(_ds_src)
                if _ds_n is not None:
                    yesno_overrides["override_daily_styling"] = _ds_n
                _th_src = thinning if thinning is not None else hair_thinning
                if _th_src is None:
                    _th_src = onboarding.get("hair_thinning")
                    if _th_src is None:
                        _th_src = onboarding.get("thinning")
                _th_n = _normalize_hair_yes_no(_th_src)
                if _th_n is not None:
                    yesno_overrides["override_thinning"] = _th_n
            elif req_maxx == "bonemax":
                _tmj_n = _normalize_hair_yes_no(tmj_raw)
                if _tmj_n is not None:
                    yesno_overrides["override_tmj_history"] = _tmj_n
                _gum_v = str(gum_raw).strip() if gum_raw is not None else ""
                if _gum_v:
                    yesno_overrides["override_mastic_gum_regular"] = _gum_v
                _scr_n = _normalize_hair_yes_no(scr_raw)
                if _scr_n is not None:
                    yesno_overrides["override_heavy_screen_time"] = _scr_n

            async with db_mutation_lock:
                schedule = await schedule_service.generate_maxx_schedule(
                    user_id=user_id,
                    maxx_id=req_maxx,
                    db=db,
                    rds_db=rds_db,
                    subscription_tier=(getattr(user, "subscription_tier", None) if user else None),
                    wake_time=final_wake,
                    sleep_time=final_sleep,
                    skin_concern=resolved_concern,
                    outside_today=False
                    if req_maxx in ("fitmax", "hairmax", "heightmax", "bonemax")
                    else bool(outside_today),
                    override_age=_age,
                    override_sex=_sex,
                    override_height=str(height).strip() if height and str(height).strip() else None,
                    override_hair_type=(hair_type or onboarding.get("hair_type") or "").strip() or None,
                    override_scalp_state=(scalp_state or onboarding.get("scalp_state") or "").strip() or None,
                    override_workout_frequency=wf,
                    **yesno_overrides,
                )
            if req_maxx == "fitmax" and user:
                from sqlalchemy.orm.attributes import flag_modified as _flag_plan
                await db.refresh(user)
                prof_fp = dict((user.profile or {}).get("fitmax_profile") or {})
                # Fold the user's diet signals in so the macro plan recommends
                # food they actually eat (vegetarian protein sources, allergy
                # swaps, familiar cuisines). Best-effort, fills only diet keys.
                try:
                    from services.personalization import state_signals as _pers_sig
                    _dsig = await _pers_sig(db, user_id)
                    for _dk in ("dietary_pattern", "dietary_restrictions",
                                "food_allergies", "food_cuisines", "foods_liked"):
                        if _dsig.get(_dk) and not prof_fp.get(_dk):
                            prof_fp[_dk] = _dsig[_dk]
                except Exception:
                    pass
                prof_fp["fitmax_plan"] = fplan.fitmax_build_plan(prof_fp)
                user.profile = {**(user.profile or {}), "fitmax_profile": prof_fp}
                _flag_plan(user, "profile")
                await db.flush()
            schedule_state["active"] = {
                "id": schedule.get("id"),
                "maxx_id": schedule.get("maxx_id"),
                "course_title": schedule.get("course_title"),
                "days": schedule.get("days") or [],
            }
            coaching_service.invalidate_context_cache(user_id)
            return _summarise_schedule(schedule)

        except ScheduleLimitError as e:
            names = ", ".join(e.active_labels)
            return (
                f"schedule limit reached: you already have {len(e.active_labels)} active modules ({names}). "
                "stop one first."
            )
        except Exception as e:
            await _safe_rollback()
            logger.exception("generate_maxx_schedule tool failed: %s", e)
            return f"schedule generation failed, try again in a moment"

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
            mid = maxx_id.strip().lower()
            async with db_mutation_lock:
                result = await schedule_service.deactivate_schedule_by_maxx(user_id, mid, db)
            if result:
                coaching_service.invalidate_context_cache(user_id)
                cur = schedule_state.get("active")
                if cur and str(cur.get("maxx_id") or "").lower() == mid:
                    try:
                        schedule_state["active"] = await schedule_service.get_current_schedule(
                            user_id, db=db
                        )
                    except Exception as refresh_err:
                        logger.warning("stop_schedule: refresh current schedule failed: %s", refresh_err)
                        schedule_state["active"] = None
                return f"{maxx_id} schedule stopped"
            return f"no active {maxx_id} schedule found"
        except Exception as e:
            await _safe_rollback()
            logger.exception("stop_schedule tool failed: %s", e)
            return f"could not stop {maxx_id}: {e}"

    # ------------------------------------------------------------------ #
    #  schedule CRUD / status tools                                       #
    # ------------------------------------------------------------------ #
    @tool
    async def get_current_schedule(
        course_id: Optional[str] = None,
        module_number: Optional[int] = None,
    ) -> str:
        """Fetch the user's current active schedule, optionally filtered by course/module."""
        try:
            sch = await schedule_service.get_current_schedule(
                user_id,
                db=db,
                course_id=course_id,
                module_number=module_number,
            )
            if not sch:
                return "no active schedule found"
            schedule_state["active"] = sch
            return _summarise_schedule(sch)
        except Exception as e:
            logger.exception("get_current_schedule tool failed: %s", e)
            return "could not load current schedule"

    @tool
    async def get_schedule_by_id(schedule_id: str) -> str:
        """Fetch one schedule by schedule_id."""
        try:
            sch = await schedule_service.get_schedule_by_id(schedule_id, user_id, db=db)
            if not sch:
                return "schedule not found"
            return _summarise_schedule(sch)
        except Exception as e:
            logger.exception("get_schedule_by_id tool failed: %s", e)
            return "could not load schedule"

    @tool
    async def get_maxx_schedule(maxx_id: str) -> str:
        """Fetch active schedule for a specific module (skinmax/hairmax/fitmax/bonemax/heightmax)."""
        try:
            mid = str(maxx_id or "").strip().lower()
            sch = await schedule_service.get_maxx_schedule(user_id, mid, db=db)
            if not sch:
                return f"no active {mid} schedule found"
            schedule_state["active"] = sch
            return _summarise_schedule(sch)
        except Exception as e:
            logger.exception("get_maxx_schedule tool failed: %s", e)
            return "could not load module schedule"

    @tool
    async def deactivate_schedule_by_id(schedule_id: str) -> str:
        """Deactivate a schedule by its schedule_id."""
        if channel == "sms":
            return "stopping schedules can only be done in the app"
        try:
            async with db_mutation_lock:
                result = await schedule_service.deactivate_schedule(user_id, schedule_id, db)
            coaching_service.invalidate_context_cache(user_id)
            cur = schedule_state.get("active")
            if cur and str(cur.get("id")) == str(schedule_id):
                schedule_state["active"] = None
            return str(result.get("message") or "schedule stopped")
        except Exception as e:
            await _safe_rollback()
            logger.exception("deactivate_schedule_by_id tool failed: %s", e)
            return f"could not deactivate schedule: {e}"

    async def _today_task_candidates(
        *,
        schedule_id: Optional[str] = None,
        maxx_id: Optional[str] = None,
    ) -> list[dict]:
        """Return today's tasks with ids across active schedules."""
        tz_name = (onboarding or {}).get("timezone") or "UTC"
        try:
            user_tz = ZoneInfo(tz_name)
        except Exception:
            user_tz = ZoneInfo("UTC")
        today_iso = datetime.now(user_tz).date().isoformat()

        out: list[dict] = []
        target_sid = str(schedule_id or "").strip()
        target_maxx = str(maxx_id or "").strip().lower()
        schedules = await schedule_service.get_all_active_schedules(user_id, db)
        for sch in schedules:
            sid = str(sch.get("id") or "")
            sm = str(sch.get("maxx_id") or "").strip().lower()
            if target_sid and sid != target_sid:
                continue
            if target_maxx and sm != target_maxx:
                continue
            for day in sch.get("days") or []:
                if day.get("date") != today_iso:
                    continue
                for task in day.get("tasks") or []:
                    tid = str(task.get("task_id") or "").strip()
                    if not tid:
                        continue
                    out.append({
                        "schedule_id": sid,
                        "task_id": tid,
                        "maxx_id": sm,
                        "time": str(task.get("time") or ""),
                        "title": str(task.get("title") or ""),
                        "description": str(task.get("description") or ""),
                        "status": str(task.get("status") or "pending").lower(),
                    })
        return out

    async def _resolve_today_task_target(
        *,
        action: str,
        schedule_id: Optional[str] = None,
        task_id: Optional[str] = None,
        task_hint: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str], str]:
        """
        Resolve (schedule_id, task_id) from explicit ids or today's tasks using a hint.
        Returns (sid, tid, message_if_unresolved).
        """
        candidates = await _today_task_candidates(schedule_id=schedule_id)
        if not candidates:
            return None, None, "no tasks found for today"

        # If task_id provided, trust it and infer schedule_id from today's candidates when omitted.
        if task_id:
            tid = str(task_id).strip()
            sid = str(schedule_id or "").strip()
            if sid:
                return sid, tid, ""
            for c in candidates:
                if c["task_id"] == tid:
                    return c["schedule_id"], tid, ""
            return None, None, "task id not found in today's tasks"

        # Action-aware status filtering.
        if action == "complete":
            candidates = [c for c in candidates if c["status"] != "completed"]
        elif action == "uncomplete":
            candidates = [c for c in candidates if c["status"] == "completed"]
        if not candidates:
            return None, None, "no matching tasks for this action today"

        hint = str(task_hint or "").strip().lower()
        if not hint:
            if len(candidates) == 1:
                c = candidates[0]
                return c["schedule_id"], c["task_id"], ""
            preview = "; ".join(f"{c['time']} {c['title']}" for c in candidates[:3])
            return None, None, f"multiple tasks matched today. specify task_hint (e.g. time/title). examples: {preview}"

        # Lightweight keyword+time matching.
        module_hits = {"skinmax", "hairmax", "fitmax", "bonemax", "heightmax"}
        hinted_maxx = next((m for m in module_hits if m in hint), "")
        time_hits = set(re.findall(r"\b\d{1,2}:\d{2}\b", hint))
        words = [w for w in re.findall(r"[a-z0-9]+", hint) if len(w) > 2]

        scored: list[tuple[int, dict]] = []
        for c in candidates:
            hay = f"{c['title']} {c['description']} {c['time']} {c['maxx_id']}".lower()
            score = 0
            if hinted_maxx and c["maxx_id"] == hinted_maxx:
                score += 4
            if c["time"] in time_hits:
                score += 4
            for w in words:
                if w in hay:
                    score += 1
            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]
        if best_score <= 0:
            return None, None, "could not map task_hint to today's tasks. include time or task title keywords"
        if len(scored) > 1 and scored[1][0] == best_score and best_score > 0:
            tied = [c for s, c in scored if s == best_score][:3]
            preview = "; ".join(f"{c['time']} {c['title']}" for c in tied)
            return None, None, f"task_hint is ambiguous. be more specific. candidates: {preview}"
        return best["schedule_id"], best["task_id"], ""

    @tool
    async def complete_schedule_task(
        schedule_id: Optional[str] = None,
        task_id: Optional[str] = None,
        task_hint: Optional[str] = None,
        feedback: Optional[str] = None,
    ) -> str:
        """
        Mark one task completed.
        ONLY call when user explicitly asks to mark/check off/complete a task.
        Do NOT call for "help/explain this task" questions.
        If task_id is missing, auto-resolve from today's tasks via task_hint.
        """
        try:
            sid, tid, err = await _resolve_today_task_target(
                action="complete",
                schedule_id=schedule_id,
                task_id=task_id,
                task_hint=task_hint,
            )
            if not sid or not tid:
                return err or "could not resolve task to complete"
            async with db_mutation_lock:
                result = await schedule_service.complete_task(
                    user_id=user_id,
                    schedule_id=sid,
                    task_id=tid,
                    db=db,
                    feedback=feedback,
                )
            coaching_service.invalidate_context_cache(user_id)
            return f"task marked complete ({result.get('status', 'ok')})"
        except Exception as e:
            await _safe_rollback()
            logger.exception("complete_schedule_task tool failed: %s", e)
            return f"could not complete task: {e}"

    @tool
    async def complete_today_tasks(maxx_id: Optional[str] = None) -> str:
        """
        Mark all of today's pending tasks as completed.
        ONLY call on explicit commands like "mark all complete".
        Do NOT call for help/explanation requests.
        Optionally limit to one module via maxx_id (skinmax/hairmax/fitmax/bonemax/heightmax).
        """
        try:
            tz_name = (onboarding or {}).get("timezone") or "UTC"
            try:
                user_tz = ZoneInfo(tz_name)
            except Exception:
                user_tz = ZoneInfo("UTC")
            today_iso = datetime.now(user_tz).date().isoformat()

            target_maxx = str(maxx_id or "").strip().lower()
            schedules = await schedule_service.get_all_active_schedules(user_id, db)
            total = 0
            done: list[str] = []

            for sch in schedules:
                sm = str(sch.get("maxx_id") or "").strip().lower()
                if target_maxx and sm != target_maxx:
                    continue
                sid = str(sch.get("id") or "")
                if not sid:
                    continue
                for day in sch.get("days") or []:
                    if day.get("date") != today_iso:
                        continue
                    for task in day.get("tasks") or []:
                        if str(task.get("status") or "").lower() == "completed":
                            continue
                        tid = str(task.get("task_id") or "")
                        if not tid:
                            continue
                        try:
                            async with db_mutation_lock:
                                await schedule_service.complete_task(
                                    user_id=user_id,
                                    schedule_id=sid,
                                    task_id=tid,
                                    db=db,
                                    feedback=None,
                                )
                            total += 1
                            done.append(f"{task.get('time', '?')} {task.get('title', 'task')}")
                        except Exception as one_err:
                            logger.warning("complete_today_tasks skipped task sid=%s tid=%s err=%s", sid, tid, one_err)

            if total:
                coaching_service.invalidate_context_cache(user_id)
                preview = "; ".join(done[:5])
                more = f" (+{total - 5} more)" if total > 5 else ""
                return f"marked {total} task(s) complete for today: {preview}{more}"
            if target_maxx:
                return f"no pending tasks found today for {target_maxx}"
            return "no pending tasks found today"
        except Exception as e:
            await _safe_rollback()
            logger.exception("complete_today_tasks tool failed: %s", e)
            return f"could not complete today's tasks: {e}"

    @tool
    async def uncomplete_schedule_task(
        schedule_id: Optional[str] = None,
        task_id: Optional[str] = None,
        task_hint: Optional[str] = None,
    ) -> str:
        """
        Mark a completed task back to pending.
        ONLY call when user explicitly asks to undo/uncomplete/revert completion.
        Auto-resolves from today's tasks when needed.
        """
        try:
            sid, tid, err = await _resolve_today_task_target(
                action="uncomplete",
                schedule_id=schedule_id,
                task_id=task_id,
                task_hint=task_hint,
            )
            if not sid or not tid:
                return err or "could not resolve task to uncomplete"
            async with db_mutation_lock:
                result = await schedule_service.uncomplete_task(
                    user_id=user_id,
                    schedule_id=sid,
                    task_id=tid,
                    db=db,
                )
            coaching_service.invalidate_context_cache(user_id)
            return f"task set to pending ({result.get('status', 'ok')})"
        except Exception as e:
            await _safe_rollback()
            logger.exception("uncomplete_schedule_task tool failed: %s", e)
            return f"could not uncomplete task: {e}"

    @tool
    async def edit_schedule_task(
        schedule_id: Optional[str] = None,
        task_id: Optional[str] = None,
        task_hint: Optional[str] = None,
        time: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        duration_minutes: Optional[int] = None,
    ) -> str:
        """
        Edit a schedule task.
        ONLY call when user explicitly asks to change task fields (time/title/description/duration).
        If task_id is missing, auto-resolve from today's tasks via task_hint.
        """
        try:
            updates: dict = {}
            if time is not None:
                updates["time"] = time
            if title is not None:
                updates["title"] = title
            if description is not None:
                updates["description"] = description
            if duration_minutes is not None:
                updates["duration_minutes"] = duration_minutes
            if not updates:
                return "no task updates provided"
            sid, tid, err = await _resolve_today_task_target(
                action="edit",
                schedule_id=schedule_id,
                task_id=task_id,
                task_hint=task_hint,
            )
            if not sid or not tid:
                return err or "could not resolve task to edit"
            async with db_mutation_lock:
                await schedule_service.edit_task(
                    user_id=user_id,
                    schedule_id=sid,
                    task_id=tid,
                    db=db,
                    updates=updates,
                )
            coaching_service.invalidate_context_cache(user_id)
            return "task updated"
        except Exception as e:
            await _safe_rollback()
            logger.exception("edit_schedule_task tool failed: %s", e)
            return f"could not edit task: {e}"

    @tool
    async def delete_schedule_task(
        schedule_id: Optional[str] = None,
        task_id: Optional[str] = None,
        task_hint: Optional[str] = None,
    ) -> str:
        """
        Delete a task.
        ONLY call when user explicitly asks to remove/delete a task.
        If task_id is missing, auto-resolve from today's tasks via task_hint.
        """
        try:
            sid, tid, err = await _resolve_today_task_target(
                action="delete",
                schedule_id=schedule_id,
                task_id=task_id,
                task_hint=task_hint,
            )
            if not sid or not tid:
                return err or "could not resolve task to delete"
            async with db_mutation_lock:
                await schedule_service.delete_task(
                    user_id=user_id,
                    schedule_id=sid,
                    task_id=tid,
                    db=db,
                )
            coaching_service.invalidate_context_cache(user_id)
            return "task deleted"
        except Exception as e:
            await _safe_rollback()
            logger.exception("delete_schedule_task tool failed: %s", e)
            return f"could not delete task: {e}"

    @tool
    async def update_schedule_preferences(
        wake_time: Optional[str] = None,
        sleep_time: Optional[str] = None,
        notifications_enabled: Optional[bool] = None,
        notification_minutes_before: Optional[int] = None,
    ) -> str:
        """Update user schedule preferences used by schedule generation/reminders."""
        try:
            prefs = dict(getattr(user, "schedule_preferences", {}) or {})
            if wake_time is not None:
                prefs["wake_time"] = wake_time
            if sleep_time is not None:
                prefs["sleep_time"] = sleep_time
            if notifications_enabled is not None:
                prefs["notifications_enabled"] = bool(notifications_enabled)
            if notification_minutes_before is not None:
                prefs["notification_minutes_before"] = int(notification_minutes_before)
            if not prefs:
                return "no preferences provided"
            async with db_mutation_lock:
                await schedule_service.update_preferences(user_id, prefs, db)
            return "preferences updated"
        except Exception as e:
            await _safe_rollback()
            logger.exception("update_schedule_preferences tool failed: %s", e)
            return f"could not update preferences: {e}"

    @tool
    async def generate_course_schedule(
        course_id: str,
        module_number: int,
        num_days: int = 30,
    ) -> str:
        """Generate a generic course/module schedule (non-maxx path)."""
        try:
            async with db_mutation_lock:
                schedule = await schedule_service.generate_schedule(
                    user_id=user_id,
                    course_id=course_id,
                    module_number=int(module_number),
                    db=db,
                    rds_db=rds_db,
                    preferences=None,
                    num_days=int(num_days),
                    subscription_tier=(getattr(user, "subscription_tier", None) if user else None),
                )
            schedule_state["active"] = {
                "id": schedule.get("id"),
                "maxx_id": schedule.get("maxx_id"),
                "course_title": schedule.get("course_title"),
                "days": schedule.get("days") or [],
            }
            coaching_service.invalidate_context_cache(user_id)
            return _summarise_schedule(schedule)
        except ScheduleLimitError as e:
            names = ", ".join(e.active_labels)
            return (
                f"schedule limit reached: you already have {len(e.active_labels)} active modules ({names}). "
                "stop one first."
            )
        except Exception as e:
            await _safe_rollback()
            logger.exception("generate_course_schedule tool failed: %s", e)
            return "schedule generation failed, try again in a moment"

    # ------------------------------------------------------------------ #
    #  update_schedule_context                                             #
    # ------------------------------------------------------------------ #
    @tool
    async def update_schedule_context(key: str, value: str) -> str:
        """
        Save persistent context the bot learned from chat that should influence
        future schedule generations and tweaks. Examples of keys:
          - product_preferences (object), product_dislikes (list)
          - morning_friction ("high"|"low"), explicit_avoidances (list)
          - equipment_owned (list), timing_preferences (object)
          - wake_time, sleep_time (also persisted to user profile)
          - preferred_workout_time (HH:MM), re-anchors the workout window for
            FitMax/HeightMax and every other maxx at once
          - get_ready_time (HH:MM), when they shower/get ready; re-anchors the
            morning skin/hair/mewing routine across maxes
          - get_ready_minutes (int 10-90), HOW LONG they take to get ready;
            sizes the morning routine block and pushes the rest of the AM later,
            so someone who needs longer gets a roomier morning. Use this when the
            user says things like "I take 45 min to get ready in the morning".
        Pass a clock time like "18:00" or "6:30 pm" for the clock keys, and a
        plain number of minutes (e.g. "45") for get_ready_minutes.
        """
        try:
            from services.user_context_service import merge_context, append_to_list
            lk = (key or "").lower().replace("-", "_")
            if lk in ("wake_time", "sleep_time", "preferred_wake_time", "preferred_sleep_time"):
                wk = value if "wake" in lk else None
                sk = value if "sleep" in lk else None
                async with db_mutation_lock:
                    await _persist_user_wake_sleep(user, db, wk, sk)
            elif lk in ("get_ready_minutes", "get_ready_duration", "get_ready_mins"):
                # Morning get-ready DURATION (minutes) — persist to the canonical
                # onboarding field so the UI and future generations agree, then
                # fall through to the regen below.
                async with db_mutation_lock:
                    await _persist_get_ready_minutes(user, db, value)
                lk = "get_ready_minutes"
            elif lk in _TIMING_ANCHOR_KEYS:
                # Precise day anchors (workout / get-ready) — persist to the
                # canonical onboarding field so the UI and future generations
                # agree, then fall through to the regen below.
                canonical = _TIMING_ANCHOR_KEYS[lk]
                async with db_mutation_lock:
                    await _persist_onboarding_clock(user, db, canonical, value)
                lk = canonical
            # Coerce value: if it looks like a JSON literal, parse; else store raw.
            parsed_val: Any = value
            try:
                import json as _json
                stripped = (value or "").strip()
                if stripped.startswith(("{", "[", '"')) or stripped in ("true", "false", "null"):
                    parsed_val = _json.loads(stripped)
            except Exception:
                pass
            list_keys = {"product_dislikes", "explicit_avoidances", "equipment_owned",
                         "skipped_repeatedly", "reported_issues"}
            async with db_mutation_lock:
                if lk in list_keys and not isinstance(parsed_val, list):
                    await append_to_list(user_id, lk, parsed_val, db)
                else:
                    await merge_context(user_id, {lk: parsed_val}, db)
            # If the saved key is one the skeleton consults (required field
            # answers, optional context like dermastamp_owned / training_status
            # / heat_styling, etc.), re-expand active schedules so the user
            # sees task changes immediately. We use a permissive whitelist —
            # bookkeeping keys (_onboarding_pending) are skipped via the
            # `_` prefix check.
            try:
                if lk and not lk.startswith("_") and lk not in ("wake_time", "sleep_time"):
                    # wake/sleep already triggered via _persist_user_wake_sleep above.
                    from services.schedule_runtime import regenerate_active_schedules
                    async with db_mutation_lock:
                        await regenerate_active_schedules(
                            user_id=user_id, db=db, reason=f"context:{lk}",
                        )
            except Exception as _e:
                logger.warning("regen after context update failed (non-fatal): %s", _e)
            return f"{lk}={parsed_val} saved"
        except Exception as e:
            await _safe_rollback()
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
        Log check-in data ONLY when user explicitly reports their day,
        e.g. 'i did my workout', 'slept 7 hours', 'ate 1800 cals', 'missed today'.
        Do NOT call for questions or casual chat.
        """
        try:
            check_in_data: dict = {}
            parts: list[str] = []
            if workout_done is not None:
                check_in_data["workout_done"] = workout_done
                parts.append(f"workout={'done' if workout_done else 'skipped'}")
            if missed is not None:
                check_in_data["missed"] = missed
                parts.append(f"missed={missed}")
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
                async with db_mutation_lock:
                    await coaching_service.process_check_in(user_id, db, check_in_data)
            return "check-in logged: " + (", ".join(parts) or "data saved")
        except Exception as e:
            await _safe_rollback()
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
                async with db_mutation_lock:
                    await db.flush()
                coaching_service.invalidate_context_cache(user_id)
            return f"coaching mode set to {mode_clean}"
        except Exception as e:
            await _safe_rollback()
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
                            f"[{t.get('status', 'pending')}] ({mod}) id={t.get('task_id', 'n/a')}"
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
            query = str(topic or module).strip()

            # --- RAG retrieval (primary path) ---
            try:
                from services.rag_service import hybrid_retrieve

                chunks = await hybrid_retrieve(db=db, maxx_id=mod, query=query, k=4)
                if chunks:
                    parts = [
                        f"[{c['doc_title']}, section {c['chunk_index'] + 1}]\n{c['content']}"
                        for c in chunks
                    ]
                    return "\n\n---\n\n".join(parts)
            except Exception as rag_err:
                logger.warning("get_module_info RAG failed (maxx=%s): %s", mod, rag_err)

            # --- Fallback: read local .md reference file ---
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
            tp = query.lower()
            if tp and tp != mod:
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

    @tool
    async def search_knowledge(query: str) -> str:
        """
        Search the knowledge base for factual answers when the user asks educational questions.
        Use for broad info questions where module is unclear.
        """
        try:
            q = str(query or "").strip()
            if not q:
                return "no query provided"
            from services.intent_classifier import classify_turn
            from services.rag_service import hybrid_retrieve

            intent = classify_turn(q, active_maxx=None)
            hints = [h for h in (intent.get("maxx_hints") or []) if h]
            if not hints:
                hints = ["general"]

            # Retrieve the hinted modules concurrently (was serial ~3x latency).
            # Safe: hybrid_retrieve doesn't use the passed db (vector_search opens
            # its own session, BM25 is in-memory), so concurrent calls don't
            # collide; and embed_text now caches, so the shared query embeds once.
            sel_hints = hints[:3]
            got_lists = await asyncio.gather(
                *[hybrid_retrieve(db=db, maxx_id=h, query=q, k=3) for h in sel_hints]
            )
            rows: list[dict] = []
            for hint, got in zip(sel_hints, got_lists):
                rows.extend([{**r, "_maxx": hint} for r in got])
            if not rows:
                return "no relevant knowledge found"
            rows.sort(key=lambda c: float(c.get("rrf_score", c.get("similarity", 0.0)) or 0.0), reverse=True)
            parts = [
                f"[{r.get('_maxx','general')}/{r.get('doc_title','reference')}, section {int(r.get('chunk_index', 0)) + 1}]\n{r.get('content','')}"
                for r in rows[:5]
            ]
            return "\n\n---\n\n".join(parts)
        except Exception as e:
            logger.exception("search_knowledge tool failed: %s", e)
            return "could not search knowledge base"

    # ------------------------------------------------------------------ #
    #  recommend_product                                                   #
    # ------------------------------------------------------------------ #
    @tool
    async def recommend_product(module: str, concern: str) -> str:
        """
        Get product/ingredient recommendations for a module and concern.
        Use when user asks what to buy or what products to use.
        module: skinmax, hairmax, fitmax, bonemax, heightmax.

        Returns BOTH:
          1. CATALOG-VETTED PRODUCTS, direct product links filtered
             through the user's facts (vegan, allergies, etc.). Quote
             the URLs verbatim. DO NOT invent or modify them.
          2. Coaching reference, protocol notes from the doc layer.
        """
        try:
            mod = str(module).lower().strip()
            con = str(concern).lower().strip()

            # ---- 1. Catalog-then-live lookup ------------------------- #
            # `find_or_search` is curated-catalog first (fact-filtered,
            # rationale-rich). If catalog returns 0 hits — rare but
            # possible for novel concerns — it falls back to a
            # constrained DDG search that returns real Amazon /dp/<ASIN>
            # product URLs scraped from search results. Live URLs are
            # auto-added to the link_validator allow-list so the agent
            # can cite them without being stripped as 'not catalog'.
            catalog_block = ""
            try:
                from services.product_search import find_or_search, format_for_prompt
                facts_blob = (
                    (user_context or {}).get("user_facts")
                    or ((user_context or {}).get("persistent_context") or {}).get("user_facts")
                    or {}
                )
                concern_tokens = [c for c in re.split(r"[,/&\s]+", con) if c]
                hits = await find_or_search(
                    module=mod,
                    concerns=concern_tokens or None,
                    user_facts=facts_blob,
                    limit=3,
                )
                catalog_block = format_for_prompt(hits)
                # Stash catalog hits as structured cards for the chat API to
                # return (authoritative name/brand/url/image + our-words blurb).
                _collect_recommended_products(hits)
                source = "catalog" if hits and hits[0].source == "catalog" else (
                    "live" if hits else "none"
                )
                logger.info(
                    "[recommend_product] %d hits for %s/%s (source=%s)",
                    len(hits), mod, con, source,
                )
            except Exception as e:
                logger.warning("[recommend_product] product lookup failed: %s", e)
                catalog_block = ""

            # ---- 2. Doc-derived coaching notes ------------------------ #
            ref_block = ""
            ref_path = os.path.normpath(
                os.path.join(
                    os.path.dirname(__file__),
                    f"{mod}_notification_engine_reference.md",
                )
            )
            if mod and os.path.exists(ref_path):
                try:
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
                            if not stripped or stripped.startswith("---"):
                                continue
                            if stripped.startswith("#") and len(stripped) < 80:
                                continue
                            is_bullet = bool(
                                re.match(r"^[-*•]\s+", stripped) or re.match(r"^\d+[\).]\s+", stripped)
                            )
                            if stripped and (is_bullet or ":" in stripped or len(stripped) > 40):
                                prod_lines.append(stripped)
                            if len(prod_lines) >= 8:
                                break
                    joined = "\n".join(prod_lines[:8])
                    ref_block = (joined[:300] if joined else content[:300])
                except Exception as e:
                    logger.warning("[recommend_product] ref read failed: %s", e)

            # ---- 3. Compose ------------------------------------------ #
            sections: list[str] = []
            if catalog_block:
                sections.append(catalog_block)
            if ref_block:
                sections.append(f"## COACHING NOTES ({mod}/{con})\n{ref_block}")
            if not sections:
                return f"no product recommendations available for {mod}/{con}"
            return "\n\n".join(sections)
        except Exception as e:
            logger.exception("recommend_product tool failed: %s", e)
            return "could not load product recommendations"

    # Web search fallback. Only call when the doc-grounded retrieval
    # (search_knowledge) returns nothing useful — see system prompt
    # directive in build_agent_system_prompt.
    @tool
    async def web_search(query: str) -> str:
        """Search the public web for an answer.

        Use ONLY when:
          1. search_knowledge / RAG didn't find what the user asked, AND
          2. the question is factual / how-to / current-events.
        Don't use for: schedule operations, anything personal about THIS
        user, or tasks better handled by other tools.

        Pass a tight 3-8 word query, not the user's full message.
        Returns a numbered block of up to 3 results: title · snippet · url.
        """
        try:
            from services.web_search import search as _ws
            return await _ws(query, max_results=3)
        except Exception as e:
            logger.info("web_search tool failed: %s", e)
            return f"(web search unavailable: {e.__class__.__name__})"

    # ------------------------------------------------------------------ #
    #  remember_about_user                                                 #
    # ------------------------------------------------------------------ #
    @tool
    async def remember_about_user(dimension: str, fact: str, key: str = "") -> str:
        """
        Save a durable, PERSONAL fact the user just revealed so Max remembers it
        forever and tailors everything (tone, food, culture, timing) to them.
        Call this whenever the user shares something lasting about WHO THEY ARE.
        Do NOT use it for one-off schedule tweaks (use update_schedule_context).

        `dimension` is one of: identity, culture, diet, work, lifestyle,
        personality, comms_style, goals, interests, constraints.
        `fact` is a short natural phrasing, e.g. "vegetarian", "family is Tamil",
        "works night shifts downtown", "wants blunt, no-fluff coaching".
        `key` (optional) is a canonical slot when this fact REPLACES the prior
        value for that slot, e.g. "diet.pattern", "comms_style.tone",
        "work.location_type". Omit key for additive facts (hobbies, foods, anecdotes).

        Examples:
          - "i'm vegetarian" -> remember_about_user("diet", "vegetarian", "diet.pattern")
          - "my mom's Tamil, we eat south indian" ->
              remember_about_user("culture", "Tamil family", "culture.culture") and
              remember_about_user("diet", "loves South Indian food")
          - "just talk to me straight, skip the pep talk" ->
              remember_about_user("comms_style", "blunt, no pep talk", "comms_style.tone")
          - "i climb on weekends" -> remember_about_user("interests", "rock climbing")
        """
        try:
            from services.personalization import remember_fact
            async with db_mutation_lock:
                mem = await remember_fact(
                    db, user_id, dimension=dimension, text=fact,
                    key=(key or None), source="chat",
                )
            if mem is None:
                return "nothing to remember"
            return f"remembered ({mem.dimension}): {mem.text}"
        except Exception as e:
            await _safe_rollback()
            logger.exception("remember_about_user tool failed: %s", e)
            return f"could not remember that: {e}"

    @tool
    async def propose_schedule_change(
        kind: str,
        summary: str,
        apply_tool: str,
        maxx_id: Optional[str] = None,
        task_hint: Optional[str] = None,
        time: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        duration_minutes: Optional[int] = None,
        context_key: Optional[str] = None,
        context_value: Optional[str] = None,
        source: str = "docs",
    ) -> str:
        """
        PROPOSE a concrete schedule change and ask the user Yes/No — DO NOT mutate
        the schedule yourself. Call this whenever the user wants to CHANGE their
        plan ("I don't like this workout plan", "change my diet", "swap the
        Heightmax tasks", "make it easier", "move it later", "fewer days", etc.)
        instead of calling modify_schedule / edit_schedule_task / generate_maxx_schedule
        directly. The change is only applied after the user taps Yes.

        Ground the suggestion in the docs first (use search_knowledge) and the web
        as fallback (web_search); honor the user's ABSOLUTE RULES (allergies / diet)
        — never propose a food they avoid. Never invent a protocol.

        Args:
          kind: one of switch_workout | switch_diet | edit_maxx_tasks | adjust | other
          summary: ONE short sentence describing exactly what will change, shown in
            the bubble (e.g. "Swap your Friday workout to a push/pull/legs split").
          apply_tool: the deterministic action to run on Yes — one of:
            - "edit_task"   : change a task's time/title/description/duration
                              (provide task_hint + the fields to change)
            - "delete_task" : remove a task (provide task_hint)
            - "update_preferences": change wake/sleep/notification prefs
                              (pass via context_key/context_value as JSON is NOT
                              needed — use set_context for plan switches instead)
            - "set_context" : switch a workout/diet plan or any durable preference
                              that regenerates tasks (provide context_key +
                              context_value, e.g. key="diet_pattern",
                              value="high-protein mediterranean")
          maxx_id: the affected maxx (fitmax, skinmax, hairmax, heightmax, bonemax) if any.
          task_hint/time/title/description/duration_minutes: for edit_task/delete_task.
          context_key/context_value: for set_context (and update_preferences pref keys).
          source: "docs" if grounded in the coaching docs, else "web".
        """
        try:
            from services.schedule_change_service import create_proposal
            from models.sqlalchemy_models import active_conversation_id as _conv_cv

            apply_tool = (apply_tool or "").strip()
            action: dict
            if apply_tool in ("edit_task", "delete_task"):
                sid, tid, err = await _resolve_today_task_target(
                    action=("edit" if apply_tool == "edit_task" else "delete"),
                    schedule_id=None,
                    task_id=None,
                    task_hint=task_hint,
                )
                if not sid or not tid:
                    return err or "could not find that task to change — ask the user which one."
                if apply_tool == "edit_task":
                    updates: dict = {}
                    if time is not None:
                        updates["time"] = time
                    if title is not None:
                        updates["title"] = title
                    if description is not None:
                        updates["description"] = description
                    if duration_minutes is not None:
                        updates["duration_minutes"] = duration_minutes
                    if not updates:
                        return "no changes specified for that task."
                    action = {"tool": "edit_task", "args": {"schedule_id": sid, "task_id": tid, "updates": updates}}
                else:
                    action = {"tool": "delete_task", "args": {"schedule_id": sid, "task_id": tid}}
            elif apply_tool == "set_context":
                if not context_key:
                    return "set_context needs a context_key (e.g. diet_pattern)."
                action = {"tool": "set_context", "args": {
                    "key": context_key, "value": context_value,
                    "only_max": maxx_id, "regenerate": True,
                }}
            elif apply_tool == "update_preferences":
                if not context_key:
                    return "update_preferences needs a preference key."
                action = {"tool": "update_preferences", "args": {"preferences": {context_key: context_value}}}
            else:
                return ("apply_tool must be one of edit_task, delete_task, set_context, "
                        "update_preferences.")

            conv_id = _conv_cv.get()
            async with db_mutation_lock:
                proposal = await create_proposal(
                    db,
                    user_id=user_id,
                    conversation_id=str(conv_id) if conv_id else None,
                    kind=kind,
                    maxx_id=maxx_id,
                    summary=summary,
                    action=action,
                    source=source,
                )
                await db.commit()
            # Surface to api/chat.py so it renders Yes/No (no second LLM call).
            # MUTATE the per-turn sink (set by reset_proposed_change in chat.py) —
            # langchain runs this coroutine in a copied context, so a .set() here
            # would not propagate, but mutating the shared dict does.
            sink = _proposed_change_ctx.get()
            if sink is not None:
                sink["proposal_id"] = str(proposal.id)
                sink["summary"] = proposal.summary
            return (
                f"PROPOSED (awaiting the user's Yes/No — not yet applied): {proposal.summary}. "
                "Briefly tell the user what you'll change and that they can tap Yes to apply or No to tweak it."
            )
        except Exception as e:
            await _safe_rollback()
            logger.exception("propose_schedule_change tool failed: %s", e)
            return f"could not prepare that change: {e}"

    return [
        propose_schedule_change,
        modify_schedule,
        generate_maxx_schedule,
        stop_schedule,
        get_current_schedule,
        get_schedule_by_id,
        get_maxx_schedule,
        deactivate_schedule_by_id,
        complete_schedule_task,
        complete_today_tasks,
        uncomplete_schedule_task,
        edit_schedule_task,
        delete_schedule_task,
        update_schedule_preferences,
        # generate_course_schedule INTENTIONALLY removed from agent tools.
        # It's the legacy course/module path (pre-doc-driven architecture);
        # all real user flows go through generate_maxx_schedule. Keeping
        # it as a callable function so any direct API caller can still hit
        # it, but pulling it out of the agent saves ~120 prompt tokens per
        # request and stops the LLM occasionally picking the wrong one
        # when the user says "make me a schedule" without naming a maxx.
        update_schedule_context,
        remember_about_user,
        log_check_in,
        set_coaching_mode,
        get_today_tasks,
        get_module_info,
        search_knowledge,
        recommend_product,
        web_search,
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
    db: Optional["AsyncSession"] = None,
    maxx_id: Optional[str] = None,
) -> tuple[str, bool]:
    """
    Run the tool-calling AgentExecutor and return (response_text, context_cache_invalidated).

    context_cache_invalidated=True when mutating/check-in tools fire, so chat.py
    can invalidate cached coaching context.

    The agent handles the full reasoning → tool call → observe → respond loop.
    max_iterations=6 allows deeper multi-tool turns before failing closed.
    """
    system_prompt = await build_agent_system_prompt(user_context, delivery_channel)

    # Per-turn hard-rules reminder. Even with the system prompt directive
    # near the top, gpt-4o-mini occasionally regurgitates RAG content
    # verbatim and slips a meat/fish into a vegetarian's answer. Appending
    # the rules to the user message at request time forces the model to
    # re-read them right next to the question — much harder to ignore.
    rules_reminder = ""
    try:
        if user_context:
            facts_blob = (user_context.get("user_facts")
                          or (user_context.get("persistent_context") or {}).get("user_facts"))
            if facts_blob:
                from services.user_facts_service import hard_constraints_reminder
                rules_reminder = hard_constraints_reminder(facts_blob)
    except Exception:
        pass

    # Table-block reminder: when the user asks for a table, append a terse
    # directive RIGHT AFTER their message so the model reads it immediately
    # before generating its response.
    _table_reminder = ""
    if _AGENT_TABLE_REQUEST_RE.search(message or ""):
        _table_reminder = (
            " [REQUIRED: output a table [VISUAL_BLOCK] NOW in this very response. "
            "Do not write 'I will build' or any future-tense. Do not ask any questions. "
            "The block must appear in your reply text — not promised for later.]"
        )

    # Chip-answer reminder: when the user sends a bare chip value from the previous
    # turn's clarifying MCQ, the model must not cascade into another clarifier.
    # Inject a terse directive immediately after the message so the model knows to
    # give actionable advice right now.
    _chip_reminder = ""
    _msg_stripped = (message or "").strip().lower()
    if _msg_stripped in _CHIP_ANSWER_MAP and not _table_reminder:
        _domain, _action = _CHIP_ANSWER_MAP[_msg_stripped]
        _chip_reminder = (
            f" [USER CHIP ANSWER: the user just picked '{_msg_stripped}' from a menu to "
            f"state their {_domain} goal. {_action.capitalize()} right now — "
            f"DO NOT ask another clarifying question. Give concrete, actionable content.]"
        )

    # Image: inject as multimodal content part in the human message
    if image_data:
        import base64

        mime = _detect_image_mime(image_data)
        b64 = base64.b64encode(image_data).decode()
        _msg_with_reminder = (message or "") + _table_reminder + _chip_reminder
        _prefix = (rules_reminder + " " if rules_reminder else "")
        input_content: str | list = [
            {"type": "text", "text": (_prefix + _msg_with_reminder)},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]
    else:
        _msg_with_reminder = (message or "") + _table_reminder + _chip_reminder
        input_content = (rules_reminder + " " if rules_reminder else "") + _msg_with_reminder

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
        max_iterations=6,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
        verbose=False,
    )

    # Budget: pass 1 + tool execution(s) + pass 2 — generous for schedule gen
    call_timeout = float(settings.llm_timeout_seconds) * 4

    logger.info("[AGENT] user channel=%s msg=%.80s", delivery_channel, message or "")
    history_tokens = sum(count_tokens(getattr(m, "content", "") or "") for m in lc_history)
    coaching_context_tokens = count_tokens((user_context or {}).get("coaching_context", ""))
    user_tokens = count_tokens(message or "")
    system_tokens = count_tokens(system_prompt)
    log_prompt_budget(
        path="agent",
        system_tokens=system_tokens,
        coaching_context_tokens=coaching_context_tokens,
        history_tokens=history_tokens,
        chunk_tokens=0,
        user_tokens=user_tokens,
        total_tokens=system_tokens + coaching_context_tokens + history_tokens + user_tokens,
    )

    try:
        result = await asyncio.wait_for(
            executor.ainvoke({
                "input": input_content,
                "chat_history": lc_history,
                "system_prompt": system_prompt,
            }),
            timeout=call_timeout,
        )
    except asyncio.TimeoutError:
        logger.error("[AGENT] timeout after %.1fs", call_timeout)
        if db is not None:
            try:
                await db.rollback()
            except Exception as rb_err:
                logger.warning("[AGENT] rollback after timeout failed: %s", rb_err)
        raise TimeoutError(
            "The assistant took too long. Please try again. Your message was saved."
        ) from None

    # Agent output is usually a string, but some providers / tool-calling paths
    # return it as a list of content blocks (str or {"text"|"content": ...}).
    # Coerce to text before stripping so a list never crashes the whole turn.
    _raw_out = result.get("output")
    if isinstance(_raw_out, list):
        _parts = []
        for _p in _raw_out:
            if isinstance(_p, str):
                _parts.append(_p)
            elif isinstance(_p, dict):
                _parts.append(str(_p.get("text") or _p.get("content") or ""))
        _raw_out = " ".join(p for p in _parts if p)
    response_text = (str(_raw_out) if _raw_out else "").strip()

    # When the tool-calling executor issues tool calls but produces no final
    # text (empty output), fire a plain single-shot call so the turn never
    # returns a blank. This happens for statement-type messages ("quick heads
    # up: i'm vegetarian") where the agent calls remember_about_user but
    # forgets to emit a closing response.
    if not response_text:
        try:
            from services.lc_providers import get_chat_llm_with_fallback as _gcllm
            from langchain_core.messages import HumanMessage, SystemMessage
            _ack_llm = _gcllm(max_tokens=80)
            _ack_resp = await _ack_llm.ainvoke([
                SystemMessage(content=(
                    "You are Max, a concise looksmaxxing coach. "
                    "The user just shared a personal detail or heads-up. "
                    "Acknowledge it briefly (1-2 sentences, no lists, no headings). "
                    "Keep Max's lowercase, direct voice."
                )),
                HumanMessage(content=message or ""),
            ])
            _ack_text = (getattr(_ack_resp, "content", None) or "").strip()
            if _ack_text:
                response_text = _ack_text
                logger.info("[AGENT] empty output recovered via ack call for msg=%.60s", message)
        except Exception as _ack_err:
            logger.warning("[AGENT] ack recovery failed: %s", _ack_err)

    # Hard-constraint validator: post-check the agent's final answer
    # against user_facts. If the agent recommended chicken to a
    # vegetarian (or any other constraint violation), regen ONCE with a
    # corrective directive routed back through the same LLM. This is the
    # last line of defense after prompt-time injection + per-turn rules
    # reminder — instruction-following can still drift, especially when
    # tool output (RAG, web_search) is loaded with forbidden terms.
    try:
        facts_blob = (
            (user_context or {}).get("user_facts")
            or ((user_context or {}).get("persistent_context") or {}).get("user_facts")
        )
        if facts_blob and response_text:
            from services.user_facts_validator import (
                enforce_against_facts, find_violations,
            )
            initial_violations = find_violations(response_text, facts_blob)
            if initial_violations:
                logger.info(
                    "[AGENT] facts-validator caught violations=%s; regenerating",
                    [t for t, _ in initial_violations],
                )
                from langchain_core.messages import HumanMessage, SystemMessage
                from services.lc_providers import get_chat_llm_with_fallback as _gcllm

                async def _regen(directive: str) -> str:
                    # Re-issue the answer through a plain LLM call (no
                    # tools). The directive names the violated terms and
                    # demands a clean rewrite.
                    sys_msg = (
                        "You are rewriting a previous answer. The user has "
                        "long-term constraints that the prior draft "
                        "violated. Produce ONLY the corrected answer, "
                        "no apologies, no meta-commentary."
                    )
                    facts_str = ""
                    try:
                        from services.user_facts_service import (
                            format_facts_for_prompt, DIET_SUBSTITUTIONS,
                        )
                        facts_str = (
                            f"{format_facts_for_prompt(facts_blob)}\n\n"
                            f"{DIET_SUBSTITUTIONS}\n"
                        )
                    except Exception:
                        pass
                    human = (
                        f"USER QUESTION:\n{message}\n\n"
                        f"PREVIOUS ANSWER (do not repeat verbatim):\n{response_text}\n\n"
                        f"{facts_str}"
                        f"{directive}"
                    )
                    rl = _gcllm(max_tokens=700, temperature=0.15)
                    resp = await rl.ainvoke([
                        SystemMessage(content=sys_msg),
                        HumanMessage(content=human),
                    ])
                    out = getattr(resp, "content", resp)
                    if isinstance(out, list):
                        out = "\n".join(str(x) for x in out)
                    return str(out or "").strip()

                response_text = await enforce_against_facts(
                    facts=facts_blob,
                    initial_answer=response_text,
                    regen=_regen,
                    max_attempts=1,
                )
    except Exception as e:
        logger.info("[AGENT] facts validator skipped: %s", e)

    # Link validator — same as fast_rag. Last line of defense against
    # search-URL leaks and hallucinated product pages.
    try:
        from services.link_validator import validate_and_rewrite_links
        response_text = validate_and_rewrite_links(response_text)
    except Exception as e:
        logger.info("[AGENT] link validator skipped: %s", e)

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

    log_agent_run(
        iterations=len(result.get("intermediate_steps") or []),
        tool_calls=len(tool_names_fired),
        response_len=len(response_text),
    )

    context_cache_invalidated = bool(tool_names_fired & {
        "generate_maxx_schedule",
        "modify_schedule",
        "stop_schedule",
        "deactivate_schedule_by_id",
        "complete_schedule_task",
        "complete_today_tasks",
        "uncomplete_schedule_task",
        "edit_schedule_task",
        "delete_schedule_task",
        "generate_course_schedule",
        "update_schedule_preferences",
        "update_schedule_context",
        "log_check_in",
        "set_coaching_mode",
    })

    return response_text, context_cache_invalidated
