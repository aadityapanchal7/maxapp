"""Persistent user facts — long-term memory for whatever the user tells
the bot about themselves.

Differs from `user_schedule_context` (already exists) — that holds
schedule-influencing prefs (wake_time, dermastamp_owned, etc.). This
holds general identity / lifestyle / health facts that should bias EVERY
LLM call's answers — not just schedule generation.

Storage: `user_schedule_context.context.user_facts` (a JSON dict).
Already-merged into the user's persistent context blob, so cache + DB
hooks are reused — no new table.

Shape:
    user_facts = {
        "diet":        ["vegetarian"],          # list[str]
        "allergies":   ["fragrance", "tret"],   # list[str]
        "body":        {"height": "5'10\\"", "weight_lb": 165},   # dict
        "lifestyle":   ["dry climate", "night shift"],
        "preferences": ["minimalist routines"],
        "dislikes":    ["fades"],
        "equipment":   ["foam roller"],
        "_stated_at":  {<key>: ISO date},  # when each fact was first learned
    }

Two entry points:
  - extract_facts_from_message(text) → dict of new facts to merge
  - format_facts_for_prompt(facts)   → human-readable summary string

A small chat-layer hook calls the extractor on every user turn (no LLM
round-trip — pure regex), merges into the context blob, and the
formatter is included in EVERY LLM system prompt downstream so the
model is reminded of these facts on every turn.
"""

from __future__ import annotations

import logging
import re
from datetime import date as _date
from typing import Any

logger = logging.getLogger(__name__)


FACTS_KEY = "user_facts"


# --------------------------------------------------------------------------- #
#  Patterns                                                                   #
# --------------------------------------------------------------------------- #

# Diet — first-person assertions about what the user does/doesn't eat.
_DIET = [
    (re.compile(r"\bi'?m\s+(vegan|vegetarian|pescatarian|carnivore)\b", re.IGNORECASE),
     lambda m: ("diet", m.group(1).lower())),
    (re.compile(r"\bi\s+don'?t\s+eat\s+(meat|red meat|pork|beef|chicken|fish|dairy|gluten|eggs?)\b", re.IGNORECASE),
     lambda m: ("diet", f"no {m.group(1).lower()}")),
    (re.compile(r"\bi\s+(?:can'?t|cannot)\s+(?:have|eat|drink)\s+(dairy|gluten|lactose|nuts|peanuts|shellfish|eggs?|soy)\b", re.IGNORECASE),
     lambda m: ("allergies", m.group(1).lower())),
    (re.compile(r"\bi'?m\s+(lactose intolerant|gluten intolerant|gluten[- ]free|dairy[- ]free)\b", re.IGNORECASE),
     lambda m: ("diet", m.group(1).lower())),
]

# Allergies / sensitivities — generic.
_ALLERGY = [
    (re.compile(r"\bi'?m\s+allergic\s+to\s+([a-z][a-z\s\-/']{1,40})", re.IGNORECASE),
     lambda m: ("allergies", _trim_clause(m.group(1)))),
    (re.compile(r"\b([a-z][a-z\-]{2,30})\s+(?:makes me|gives me|caused?\s+me)\s+(?:break out|breakouts|a rash|hives)\b", re.IGNORECASE),
     lambda m: ("allergies", m.group(1).lower())),
]

# Body / measurements.
_BODY = [
    (re.compile(r"\bi'?m\s+(\d{1,2})['’]\s*(\d{1,2})(?:[\"”])?\s*(?:tall)?", re.IGNORECASE),
     lambda m: ("body.height", f"{m.group(1)}'{m.group(2)}\"")),
    (re.compile(r"\bi\s+weigh\s+(\d{2,3})\s*(lb|lbs|pounds|kg)\b", re.IGNORECASE),
     lambda m: ("body.weight", f"{m.group(1)}{m.group(2).lower()}")),
    (re.compile(r"\bi'?m\s+(\d{2,3})\s*(lb|lbs|pounds|kg)\b", re.IGNORECASE),
     lambda m: ("body.weight", f"{m.group(1)}{m.group(2).lower()}")),
    (re.compile(r"\bmy\s+(?:body\s*fat|bf)\s+is\s+(\d{1,2})\s*%?", re.IGNORECASE),
     lambda m: ("body.body_fat_pct", int(m.group(1)))),
]

# Lifestyle / location.
_LIFESTYLE = [
    (re.compile(r"\bi\s+live\s+in\s+([a-z][a-z\s,\-']{2,40})", re.IGNORECASE),
     lambda m: ("lifestyle", f"lives in {_trim_clause(m.group(1))}")),
    (re.compile(r"\bi\s+work\s+(?:the\s+)?night\s+shift\b", re.IGNORECASE),
     lambda m: ("lifestyle", "night shift")),
    (re.compile(r"\bi\s+work\s+from\s+home\b", re.IGNORECASE),
     lambda m: ("lifestyle", "wfh")),
    (re.compile(r"\bi'?m\s+a\s+student\b", re.IGNORECASE),
     lambda m: ("lifestyle", "student")),
    (re.compile(r"\bi\s+(?:work out|train)\s+(in the (?:morning|evening|afternoon)|at night|early|late)\b", re.IGNORECASE),
     lambda m: ("preferences", f"workout {m.group(1).lower()}")),
]

# Climate.
_CLIMATE = [
    (re.compile(r"\bit'?s\s+(?:very\s+)?(humid|dry|cold|hot)\s+(?:here|where i live)\b", re.IGNORECASE),
     lambda m: ("lifestyle", f"{m.group(1).lower()} climate")),
    (re.compile(r"\bi'?m\s+in\s+a\s+(humid|dry|cold|hot)\s+climate\b", re.IGNORECASE),
     lambda m: ("lifestyle", f"{m.group(1).lower()} climate")),
]

# Strong dislikes / hard avoidances.
_DISLIKE = [
    (re.compile(r"\bi\s+(?:hate|don'?t like|can'?t stand)\s+([a-z][a-z\-/' ]{2,40})", re.IGNORECASE),
     lambda m: ("dislikes", _trim_clause(m.group(1)))),
    (re.compile(r"\bplease\s+(?:no|don'?t)\s+([a-z][a-z\-/' ]{2,30})", re.IGNORECASE),
     lambda m: ("dislikes", _trim_clause(m.group(1)))),
]

# Health context.
_HEALTH = [
    (re.compile(r"\bi'?m\s+on\s+(accutane|tretinoin|finasteride|dutasteride|minoxidil)\b", re.IGNORECASE),
     lambda m: ("health", f"on {m.group(1).lower()}")),
    (re.compile(r"\bi\s+(?:smoke|vape)\b(?!\s*(?:no|never|don'?t))", re.IGNORECASE),
     lambda m: ("health", "smokes")),
    (re.compile(r"\bi\s+drink\s+(?:alcohol|beer|wine)\s+(?:every|daily|every day|a lot)\b", re.IGNORECASE),
     lambda m: ("health", "drinks frequently")),
    (re.compile(r"\bi\s+have\s+(eczema|psoriasis|rosacea|acne|melasma|seborrheic dermatitis)\b", re.IGNORECASE),
     lambda m: ("health", m.group(1).lower())),
]

ALL_PATTERNS = _DIET + _ALLERGY + _BODY + _LIFESTYLE + _CLIMATE + _DISLIKE + _HEALTH


# --------------------------------------------------------------------------- #
#  Extraction                                                                 #
# --------------------------------------------------------------------------- #

def extract_facts_from_message(text: str) -> dict[str, Any]:
    """Return a dict of NEW facts found in this message.

    Keys are dotted paths into the user_facts blob:
        - "diet"        → list[str], appended (deduped)
        - "allergies"   → list[str], appended
        - "body.height" → scalar, replaces existing
        - etc.

    Caller is responsible for merging this output into the persistent
    blob via the merger below.
    """
    if not text or not text.strip():
        return {}
    out: dict[str, Any] = {}
    for pat, mk in ALL_PATTERNS:
        for m in pat.finditer(text):
            try:
                key, value = mk(m)
            except Exception:
                continue
            if not value:
                continue
            if key in ("diet", "allergies", "lifestyle", "preferences", "dislikes", "equipment", "health"):
                bucket = out.setdefault(key, [])
                if isinstance(bucket, list) and value not in bucket:
                    bucket.append(value)
            else:
                out[key] = value
    return out


# Canonical-form aliases. Different extraction paths (regex, async LLM,
# onboarding) produce different phrasings for the same concept; we
# normalize to one stored value so the validator and prompt-formatter
# don't have to know about every synonym.
_DIET_ALIASES: dict[str, str] = {
    "no meat":            "vegetarian",
    "doesn't eat meat":   "vegetarian",
    "doesnt eat meat":    "vegetarian",
    "dont eat meat":      "vegetarian",
    "don't eat meat":     "vegetarian",
    "plant based":        "vegetarian",
    "plant-based":        "vegetarian",
    "no animal products": "vegan",
    "dairy free":         "no dairy",
    "dairy-free":         "no dairy",
    "lactose intolerant": "no dairy",
    "gluten free":        "no gluten",
    "gluten-free":        "no gluten",
    "gluten intolerant":  "no gluten",
    "celiac":             "no gluten",
}

_ALLERGY_ALIASES: dict[str, str] = {
    "tree nuts":  "tree nut",
    "peanuts":    "peanut",
    "shellfish":  "shellfish",  # already canonical
    "lactose":    "dairy",
    "perfume":    "fragrance",
    "scent":      "fragrance",
    "scented":    "fragrance",
    "sulfates":   "sulfate",
    "sls":        "sulfate",
}


def _canonicalize(category: str, value: str) -> str:
    """Map a raw fact value to its canonical form. Idempotent."""
    v = (value or "").strip().lower()
    if not v:
        return v
    table = {
        "diet": _DIET_ALIASES,
        "allergies": _ALLERGY_ALIASES,
    }.get(category)
    if not table:
        return v
    return table.get(v, v)


def merge_facts(existing: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
    """Merge `new` into `existing` user_facts blob. Lists union (dedup);
    scalars and dotted-path body.* fields replace."""
    out: dict[str, Any] = dict(existing or {})
    today = _date.today().isoformat()
    stated_at = dict(out.get("_stated_at") or {})

    for key, value in new.items():
        if "." in key:
            # Dotted path — write into a nested sub-dict.
            parent, child = key.split(".", 1)
            sub = dict(out.get(parent) or {})
            sub[child] = value
            out[parent] = sub
            stated_at[key] = today
        elif isinstance(value, list):
            existing_list = list(out.get(key) or [])
            for v in value:
                # Canonicalize at merge time so storage stays clean —
                # any future stored fact is in canonical form regardless
                # of which extractor produced it.
                cv = _canonicalize(key, str(v)) if isinstance(v, str) else v
                if cv not in existing_list:
                    existing_list.append(cv)
                    stated_at[f"{key}:{cv}"] = today
            out[key] = existing_list
        else:
            cv = _canonicalize(key, str(value)) if isinstance(value, str) else value
            out[key] = cv
            stated_at[key] = today

    if stated_at:
        out["_stated_at"] = stated_at
    return out


# --------------------------------------------------------------------------- #
#  Prompt formatting                                                          #
# --------------------------------------------------------------------------- #

def format_facts_for_prompt(facts: dict[str, Any] | None, max_items: int = 24) -> str:
    """Render the user_facts blob as a compact prompt block.

    Returns "" when there's nothing worth showing — caller can `if`-guard
    and skip the section entirely. Order of keys is stable (most-likely-
    relevant first) so the prompt is consistent across turns.
    """
    if not facts:
        return ""
    lines: list[str] = []
    order = ("diet", "allergies", "health", "body", "lifestyle", "preferences", "dislikes", "equipment")
    count = 0
    for key in order:
        v = facts.get(key)
        if not v:
            continue
        if isinstance(v, dict):
            sub = ", ".join(f"{k}={vv}" for k, vv in v.items() if vv not in (None, "", []))
            if not sub:
                continue
            lines.append(f"- {_label(key)}: {sub}")
        elif isinstance(v, list):
            joined = ", ".join(str(x) for x in v[: max_items])
            if not joined:
                continue
            lines.append(f"- {_label(key)}: {joined}")
        else:
            lines.append(f"- {_label(key)}: {v}")
        count += 1
    if not lines:
        return ""
    return "## KNOWN USER FACTS (don't contradict; use to personalize)\n" + "\n".join(lines)


def hard_constraints_reminder(facts: dict[str, Any] | None) -> str:
    """Compact one-liner stating the user's hard constraints. Designed to
    be PREPENDED to the user's message so instruction-following models
    can't miss it. Example output:
        "[hard rules: vegetarian; lactose intolerant; allergic to fragrance]"
    Returns "" if there are no constraints worth reminding."""
    if not facts:
        return ""
    bits: list[str] = []
    diet = facts.get("diet") or []
    allergies = facts.get("allergies") or []
    health = facts.get("health") or []
    dislikes = facts.get("dislikes") or []
    for v in diet:
        s = str(v).lower().strip()
        # Expand short tags into explicit "no X / no Y" reminders so the
        # model can't shrug them off as ambiguous.
        if s in ("vegetarian", "no meat", "doesn't eat meat", "plant based", "plant-based"):
            bits.append("vegetarian — NEVER suggest chicken, fish, beef, pork, seafood, or any meat")
        elif s == "vegan":
            bits.append("vegan — NEVER suggest meat, fish, eggs, dairy, whey, honey")
        else:
            bits.append(s)
    for v in allergies:
        bits.append(f"allergic to {v}")
    for v in health:
        if v in ("eczema", "psoriasis", "rosacea", "acne", "melasma", "seborrheic dermatitis"):
            bits.append(f"has {v}")
        elif v.startswith("on "):
            bits.append(v)
    for v in dislikes:
        bits.append(f"avoid {v}")
    if not bits:
        return ""
    return f"[hard rules — never violate: {'; '.join(bits)}]"


# Quick substitutions table the system prompt references so the model
# has concrete alternatives ready when a doc cites a forbidden item.
DIET_SUBSTITUTIONS = """## SUBSTITUTION GUIDE (apply automatically when filtering)
  vegetarian / no meat / doesn't eat meat / plant-based
               → NEVER suggest: chicken, beef, pork, turkey, fish, salmon, tuna,
                 shrimp, seafood, bacon, ham, sausage, jerky, lamb, duck, anchovy
               → DO suggest: tofu, tempeh, seitan, lentils, black beans, chickpeas,
                 edamame, eggs (allowed), greek yogurt (if dairy ok), cottage cheese,
                 quinoa, nuts, nut butter, seeds, hemp, protein powder (whey/pea/soy)
  vegan        → above + drop eggs/yogurt/cheese/whey; add seitan, nutritional yeast, hemp,
                 pea protein, soy protein
  no dairy     → swap milk/yogurt/cheese for: oat milk, coconut yogurt, almond milk
  no gluten    → swap wheat/bread/pasta for: rice, oats, quinoa, gluten-free oats
  lactose intolerant → same as no dairy
"""


def _label(key: str) -> str:
    return {
        "diet": "Diet",
        "allergies": "Allergies / sensitivities",
        "health": "Health",
        "body": "Body",
        "lifestyle": "Lifestyle",
        "preferences": "Preferences",
        "dislikes": "Dislikes / avoid",
        "equipment": "Equipment owned",
    }.get(key, key.title())


# --------------------------------------------------------------------------- #
#  Helpers                                                                    #
# --------------------------------------------------------------------------- #

_TAIL_STOPWORDS = re.compile(
    r"\s+(?:please|but|and|because|since|though|so|when|while|even|now|today|anymore|though|either|too|though).*$",
    re.IGNORECASE,
)


def _trim_clause(s: str) -> str:
    s = s.strip().rstrip(".,;:!?")
    s = _TAIL_STOPWORDS.sub("", s).strip()
    # Cap length so a runaway match doesn't store a paragraph.
    return s.lower()[:60]
