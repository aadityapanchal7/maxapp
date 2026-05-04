"""Deterministic detector for schedule-update intents in free chat.

Replaces "let the agent decide whether to call update_schedule_context"
with regex pattern-matching that runs BEFORE the agent. Same pattern as
the onboarding questioner — chat layer owns the turn when it can apply
the user's intent reliably.

What it catches (in priority order):
  - Specific wake/sleep time: "wake up at 9am", "going to bed at 11"
  - Vague timing change: "im going to wake up later", "sleeping in more"
                         → emits a slider so the user picks the hour
  - Training status: "started lifting", "stopped going to the gym"
  - Posture: "i have a desk job", "i sit all day"
  - Outdoor: "i'm outside a lot now"
  - Equipment: "i bought a dermastamp", "i got a dermaroller"

Each detected intent either:
  - APPLIES IMMEDIATELY (specific + safe, e.g. wake_time 9:00)
  - or ASKS FOR INPUT via a slider/choices (vague intent)

When applied, regenerate_active_schedules() fires automatically (via the
hooks in lc_agent._persist_user_wake_sleep and update_schedule_context).
The intent is stored in user_schedule_context._pending_intent so the
follow-up answer can be routed back through this detector.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Pending state                                                              #
# --------------------------------------------------------------------------- #

PENDING_KEY = "_pending_intent"


def get_pending_intent(state: dict) -> Optional[dict]:
    p = state.get(PENDING_KEY)
    if isinstance(p, dict) and p.get("kind"):
        return dict(p)
    return None


# --------------------------------------------------------------------------- #
#  Detector                                                                   #
# --------------------------------------------------------------------------- #

# Specific time: "wake up at 9", "wake at 9:30am", etc.
_WAKE_SPECIFIC = re.compile(
    r"\b(?:i(?:'?ll| will)?\s+)?(?:wake|waking|get up|getting up)(?:\s+up)?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
    re.IGNORECASE,
)
_SLEEP_SPECIFIC = re.compile(
    r"\b(?:i(?:'?ll| will)?\s+)?(?:go to bed|sleep|going to bed|going to sleep|hit the sack|in bed|crash)(?:\s+at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
    re.IGNORECASE,
)

# Vague timing changes — no number given.
_WAKE_VAGUE = re.compile(
    r"\b(wake up later|waking up later|sleeping in|sleep in|gonna sleep more|sleep more|wake up earlier|waking up earlier|wake earlier|get up earlier|get up later)\b",
    re.IGNORECASE,
)
_SLEEP_VAGUE = re.compile(
    r"\b(stay up later|going to bed later|sleeping later|going to bed earlier|sleep earlier|crash earlier|hitting the bed earlier)\b",
    re.IGNORECASE,
)

# Training status.
_TRAIN_START = re.compile(
    r"\b(started lifting|started training|going to the gym|started the gym|i lift now|i'?m lifting|i train (?:now|again))\b",
    re.IGNORECASE,
)
_TRAIN_STOP = re.compile(
    r"\b(stopped lifting|stopped training|don'?t lift anymore|quit (?:lifting|training|the gym)|not training anymore)\b",
    re.IGNORECASE,
)

# Posture / desk.
_DESK_JOB = re.compile(
    r"\b(desk job|i sit all day|on my computer all day|on a screen all day|on my phone a lot|i'?m at a screen)\b",
    re.IGNORECASE,
)

# Outdoor.
_OUTDOOR = re.compile(
    r"\b(i'?m outside a lot|i go outside a lot|i work outside|in the sun a lot|always outside)\b",
    re.IGNORECASE,
)

# Equipment owned.
_DERMASTAMP = re.compile(r"\b(got a dermastamp|bought a dermastamp|i have a dermastamp|own a dermastamp)\b", re.IGNORECASE)
_DERMAROLLER = re.compile(r"\b(got a dermaroller|bought a dermaroller|i have a dermaroller|own a dermaroller)\b", re.IGNORECASE)


def detect_intent(message: str, state: dict) -> Optional[dict]:
    """Return an intent dict or None.

    Intent shape:
        {kind, vague?: bool, value?: any, slider?: dict, hint?: str}
    Caller is responsible for applying it (deterministically, then
    regenerating) or storing it as pending and returning a slider.
    """
    if not message or not message.strip():
        return None
    text = message.strip()

    # Specific wake time first (more confident than vague).
    m = _WAKE_SPECIFIC.search(text)
    if m and not _looks_like_topic_question(text):
        v = _hhmm_from_match(m)
        if v:
            return {"kind": "wake_time", "value": v}

    m = _SLEEP_SPECIFIC.search(text)
    if m and not _looks_like_topic_question(text):
        v = _hhmm_from_match(m)
        if v:
            return {"kind": "sleep_time", "value": v}

    # Vague — emit slider.
    if _WAKE_VAGUE.search(text):
        cur = state.get("wake_time") or "07:00"
        cur_h = _safe_hour(cur, fallback=7)
        return {
            "kind": "wake_time",
            "vague": True,
            "slider": {
                "type": "slider", "min": 5, "max": 12, "step": 1, "default": cur_h,
                "label": "new wake time (hour)", "unit": ":00",
            },
            "hint": "what time?",
        }

    if _SLEEP_VAGUE.search(text):
        cur = state.get("sleep_time") or "23:00"
        cur_h = _safe_hour(cur, fallback=23)
        # Sleep slider: 21-26 (where 24-26 = midnight to 2am).
        return {
            "kind": "sleep_time",
            "vague": True,
            "slider": {
                "type": "slider", "min": 21, "max": 26, "step": 1, "default": cur_h if cur_h >= 21 else 23,
                "label": "new bedtime (hour)", "unit": "",
            },
            "hint": "what time?",
        }

    # Training.
    if _TRAIN_START.search(text):
        return {"kind": "training_status", "value": "yes_some"}
    if _TRAIN_STOP.search(text):
        return {"kind": "training_status", "value": "no"}

    # Desk job.
    if _DESK_JOB.search(text):
        return {"kind": "posture_issues", "value": True}

    # Outdoor.
    if _OUTDOOR.search(text):
        return {"kind": "outdoor_lifestyle", "value": True}

    # Equipment.
    if _DERMASTAMP.search(text):
        return {"kind": "dermastamp_owned", "value": True}
    if _DERMAROLLER.search(text):
        return {"kind": "dermaroller_owned", "value": True}

    return None


# --------------------------------------------------------------------------- #
#  Helpers                                                                    #
# --------------------------------------------------------------------------- #

def _looks_like_topic_question(text: str) -> bool:
    """Avoid false-positives like 'what time should I wake up at?' — that's
    a question asking ABOUT wake time, not declaring a new one."""
    low = text.lower().strip()
    # Starts with question word AND contains '?'
    if low.startswith(("what", "when", "how", "should", "do you", "is it ok", "can i")) and "?" in low:
        return True
    return False


def _hhmm_from_match(m: re.Match) -> Optional[str]:
    try:
        h = int(m.group(1))
    except (TypeError, ValueError):
        return None
    mm = int(m.group(2)) if m.group(2) else 0
    suf = (m.group(3) or "").lower()
    if suf == "pm" and h < 12:
        h += 12
    elif suf == "am" and h == 12:
        h = 0
    elif not suf:
        # Heuristic: bare numbers with no am/pm → assume the user means
        # the natural reading. Wake 5-11 = AM, 1-4 = PM, sleep 9-11 = PM.
        # Without context this is fragile; only apply when reasonable.
        if h <= 11:
            pass  # assume as-given (likely AM for wake)
    if h < 0 or h > 23 or mm < 0 or mm > 59:
        return None
    return f"{h:02d}:{mm:02d}"


def _safe_hour(s: str, *, fallback: int) -> int:
    try:
        h = int(str(s).split(":")[0])
        return max(0, min(23, h))
    except (TypeError, ValueError):
        return fallback


def hour_to_hhmm(h: int) -> str:
    """Map a slider hour value back to HH:MM (handle 24/25/26 = past midnight)."""
    h = max(0, min(26, int(h)))
    if h >= 24:
        h -= 24
    return f"{h:02d}:00"
