"""Deterministic onboarding question driver.

Replaces free-form LLM questioning during max-schedule onboarding. Walks
required_fields from the max-doc one at a time, returning structured
question payloads (text + choices OR slider widget) that the mobile UI
renders via its existing quick-reply / new slider components.

State machine lives in `user_schedule_context._onboarding_pending`:
    {"max": "skinmax", "last_question": "skin_concern"}

Flow per chat turn:
1. peek_pending(user_state) → {max, last_question} | None
2. If pending and the user message is the answer to last_question:
     coerce_answer(field_spec, user_msg) → coerced value | None
     If coerced: persist to context under field_id, advance.
     If not:     re-ask the same question.
3. peek_next_question(maxx_id, merged_state) → next field spec or None
4. If next field exists: emit question payload (text + choices/slider).
5. If no next field: clear pending state, signal "ready to generate".

The driver is purely additive — it sits in front of the chat agent and
returns early when it has a question to ask. The agent never sees the
turn.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from services.task_catalog_service import get_doc, missing_required, warm_catalog, is_loaded

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Pending-state helpers                                                      #
# --------------------------------------------------------------------------- #

PENDING_KEY = "_onboarding_pending"


def get_pending(user_state: dict) -> Optional[dict]:
    """Return the current pending onboarding step, or None."""
    p = user_state.get(PENDING_KEY)
    if isinstance(p, dict) and p.get("max") and p.get("last_question"):
        return dict(p)
    return None


def make_pending(maxx_id: str, field_id: str) -> dict:
    return {"max": maxx_id, "last_question": field_id}


def clear_pending() -> dict:
    """Returns a context update that clears the pending state."""
    return {PENDING_KEY: None}


# --------------------------------------------------------------------------- #
#  Question building                                                          #
# --------------------------------------------------------------------------- #

def peek_next_question(maxx_id: str, user_state: dict) -> Optional[dict]:
    """Return the next missing required field as a structured spec, or None
    when all required fields are answered."""
    if not is_loaded():
        # Caller is async; we can't await here. Caller must warm before invoking.
        logger.warning("peek_next_question called before catalog warm; expect empty.")
    missing = missing_required(maxx_id, user_state)
    return missing[0] if missing else None


def field_to_question_payload(field_spec: dict) -> dict:
    """Convert a doc required_field spec into the wire format the mobile UI
    expects.  Always returns a dict with at minimum:
        {"text": "<question>", "field_id": "<id>"}
    Plus EITHER:
        "choices": ["Option A", ...]   for enum/yes_no
        "input_widget": {...}          for numeric / slider questions
    """
    fid = str(field_spec.get("id") or "")
    qtext = str(field_spec.get("question") or fid).strip()
    ftype = str(field_spec.get("type") or "str").strip().lower()

    payload: dict[str, Any] = {"text": qtext, "field_id": fid}

    if ftype == "enum":
        opts = field_spec.get("options") or {}
        # `options` is {value: label}. UI shows labels but answers map back.
        # We expose ordered labels as choices; coerce_answer maps label→value.
        labels = [str(v) for v in (opts.values() if isinstance(opts, dict) else opts)]
        payload["choices"] = labels
        # Stash the value→label map so coerce_answer can do the inverse lookup.
        payload["_value_map"] = (
            {str(k): str(v) for k, v in opts.items()} if isinstance(opts, dict) else None
        )

    elif ftype == "yes_no":
        payload["choices"] = ["Yes", "No"]

    elif ftype == "int":
        # Slider widget. Sensible defaults per field; can be overridden in doc.
        slider = {
            "type": "slider",
            "min": int(field_spec.get("min", 13)),
            "max": int(field_spec.get("max", 50)),
            "step": int(field_spec.get("step", 1)),
            "default": int(field_spec.get("default", 18)),
            "label": qtext,
            "unit": field_spec.get("unit") or "",
        }
        payload["input_widget"] = slider

    elif ftype in ("clock", "time"):
        # Common clock answers as quick replies.
        payload["choices"] = ["06:00", "06:30", "07:00", "07:30", "08:00", "22:00", "22:30", "23:00", "23:30"]

    else:
        # str — no constrained input; just emit the question. UI falls back to free text.
        pass

    return payload


# --------------------------------------------------------------------------- #
#  Answer coercion                                                            #
# --------------------------------------------------------------------------- #

def coerce_answer(field_spec: dict, raw: str) -> Optional[Any]:
    """Try to parse user message into the field's expected value.
    Returns the parsed value on success, None on failure (caller should re-ask).
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    ftype = str(field_spec.get("type") or "str").strip().lower()
    low = text.lower()

    if ftype == "enum":
        opts = field_spec.get("options") or {}
        if not isinstance(opts, dict):
            return None
        # 1) exact value match
        for k in opts:
            if low == str(k).lower():
                return str(k)
        # 2) exact label match
        for k, v in opts.items():
            if low == str(v).lower():
                return str(k)
        # 3) substring on label (user typed a fragment)
        best = None
        for k, v in opts.items():
            if low in str(v).lower() or str(v).lower() in low:
                best = str(k)
                break
        if best:
            return best
        # 4) keyword heuristic per common skinmax cases
        keywords = {
            "acne": ["acne", "pimple", "breakout", "zit"],
            "pigmentation": ["pigment", "dark spot", "scar", "uneven", "post-acne"],
            "rosacea": ["rosacea", "redness", "flush", "sensitive"],
            "texture": ["texture", "rough", "pore", "congest"],
            "maintenance": ["maintain", "fine", "preventive"],
            "stable": ["stable", "fine", "tolerate", "not really", "no", "no problem"],
            "sensitive": ["sometimes", "depends", "occasion"],
            "damaged": ["damaged", "irritate", "burn", "sting", "red"],
            "oily": ["oily", "shiny", "greasy"],
            "dry": ["dry", "tight", "flaky"],
            "combo": ["combo", "combination", "t-zone", "tzone"],
            "normal": ["normal", "balanced"],
            "straight": ["straight"],
            "wavy": ["wavy", "wave", "loose"],
            "curly": ["curly", "curl", "spiral"],
            "yes_active": ["yes", "yeah", "yep", "want to act", "definitely"],
            "yes_observing": ["maybe", "not sure", "thinking", "watching"],
            "no_but_family": ["family", "runs in", "father", "uncle"],
            "no": ["no", "nope", "none"],
            "yes_regular": ["3+", "regular", "every day", "5", "4", "lift"],
            "yes_some": ["sometimes", "1-2", "occasional", "now and then"],
            "posture": ["posture", "stand"],
            "retention": ["retention", "decompress", "loss"],
            "perceived": ["fashion", "look taller", "shoes", "perceived"],
            "growth": ["grow", "growth", "natural"],
            "all": ["all", "everything"],
        }
        for value, kws in keywords.items():
            if value in opts and any(k in low for k in kws):
                return value
        return None

    if ftype == "yes_no":
        if low in ("yes", "y", "yeah", "yep", "true", "1"):
            return True
        if low in ("no", "n", "nope", "nah", "false", "0"):
            return False
        return None

    if ftype == "int":
        # Tolerate "i'm 17" or "17 years old".
        import re
        m = re.search(r"\b(\d{1,3})\b", text)
        if not m:
            return None
        v = int(m.group(1))
        lo = int(field_spec.get("min", 0))
        hi = int(field_spec.get("max", 200))
        return max(lo, min(hi, v))

    if ftype in ("clock", "time"):
        import re
        m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*(am|pm)?\s*$", text, re.IGNORECASE)
        if not m:
            # Try "7am" / "11pm"
            m2 = re.match(r"^\s*(\d{1,2})\s*(am|pm)\s*$", text, re.IGNORECASE)
            if not m2:
                return None
            h = int(m2.group(1)) % 12
            if (m2.group(2) or "").lower() == "pm":
                h += 12
            return f"{h:02d}:00"
        h = int(m.group(1))
        mm = int(m.group(2))
        suf = (m.group(3) or "").lower()
        if suf == "pm" and h < 12:
            h += 12
        if suf == "am" and h == 12:
            h = 0
        return f"{h:02d}:{mm:02d}"

    # str — accept whatever they typed.
    return text


# --------------------------------------------------------------------------- #
#  Trigger detection                                                          #
# --------------------------------------------------------------------------- #

_START_INTENT_KEYWORDS = {
    "skinmax":   ["skinmax", "skin max", "skin schedule", "skin plan", "skin routine"],
    "hairmax":   ["hairmax", "hair max", "hair schedule", "hair plan", "hair routine"],
    "heightmax": ["heightmax", "height max", "height schedule", "height plan", "posture plan"],
    "fitmax":    ["fitmax", "fit max", "fit schedule", "fit plan", "fitness plan", "workout plan", "training plan", "lifting plan", "gym plan"],
    "bonemax":   ["bonemax", "bone max", "bone schedule", "bone plan", "jaw plan", "mewing plan"],
}


def detect_max_start_intent(message: str) -> Optional[str]:
    """If the user's message is asking to start a max schedule, return the
    maxx_id (only for maxes that have a doc). Otherwise None."""
    if not message:
        return None
    text = message.lower()
    # Require an action verb to avoid false positives on "what is skinmax"
    has_action = any(w in text for w in ["start", "begin", "create", "build", "make", "set up", "want", "i'd like", "id like", "let's do", "lets do"])
    if not has_action:
        return None
    for max_, kws in _START_INTENT_KEYWORDS.items():
        if any(kw in text for kw in kws):
            doc = get_doc(max_)
            if doc is not None:
                return max_
    return None
