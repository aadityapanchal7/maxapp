"""
Maxx Schedule Guidelines — Protocol definitions for each maxx type.
Each maxx has a set of skin-concern (or goal-based) protocols the AI uses
to generate personalised daily/weekly schedules.

To add a new maxx, create a dict entry in MAXX_GUIDELINES with the same shape.
"""

from typing import Optional

# ---------------------------------------------------------------------------
# Skin-type → primary concern mapping (used when user hasn't picked a concern)
# ---------------------------------------------------------------------------
SKIN_TYPE_TO_CONCERN = {
    "oily": "acne",
    "dry": "aging",
    "combination": "acne",
    "sensitive": "redness",
    "normal": "aging",
}

# ---------------------------------------------------------------------------
# SkinMax protocols keyed by concern
# ---------------------------------------------------------------------------
SKINMAX_PROTOCOLS = {
    "acne": {
        "label": "Acne / Congestion",
        "am": "Gentle cleanser → benzoyl peroxide or salicylic acid → lightweight moisturizer → sunscreen",
        "pm": "Cleanser → adapalene/retinoid → moisturizer",
        "weekly": "Clay mask 1–2x, BHA exfoliant 1–3x, no strong peels if inflamed",
        "sunscreen": "Oil-free, non-comedogenic SPF 30+ every morning",
    },
    "pigmentation": {
        "label": "Pigmentation / Uneven Tone",
        "am": "Gentle cleanser → vitamin C or azelaic acid → moisturizer → sunscreen",
        "pm": "Cleanser → retinoid or azelaic acid → moisturizer",
        "weekly": "Gentle exfoliant 1–2x, brightening mask 1x, mild peel occasionally",
        "sunscreen": "SPF 30–50 daily or dark spots will keep getting worse",
    },
    "texture": {
        "label": "Texture / Scarring",
        "am": "Gentle cleanser → niacinamide or salicylic acid → moisturizer → sunscreen",
        "pm": "Cleanser → retinoid → moisturizer",
        "weekly": "AHA/BHA exfoliant 1–2x, smoothing mask 1x, mild peel occasionally",
        "sunscreen": "SPF 30+ daily to protect collagen and prevent scar darkening",
    },
    "redness": {
        "label": "Redness / Sensitivity",
        "am": "Gentle cleanser → azelaic acid or calming serum → barrier moisturizer → sunscreen",
        "pm": "Gentle cleanser → azelaic acid → barrier moisturizer",
        "weekly": "Hydrating mask 1–2x, very mild exfoliation or none, avoid aggressive peels",
        "sunscreen": "Mineral SPF 30+ daily, especially if skin gets red easily",
    },
    "aging": {
        "label": "Aging / Skin Quality",
        "am": "Gentle cleanser → vitamin C → moisturizer → sunscreen",
        "pm": "Cleanser → retinoid/retinol → moisturizer",
        "weekly": "Hydrating mask 1x, gentle exfoliant 1x, peel occasionally if tolerated",
        "sunscreen": "SPF 30–50 every day since UV ages your face faster than anything",
    },
}

# ---------------------------------------------------------------------------
# Generic guidelines dict (future maxxes plug in here)
# ---------------------------------------------------------------------------
SKINMAX_CONCERNS = [
    {"id": "acne", "label": "Acne / Congestion"},
    {"id": "pigmentation", "label": "Pigmentation / Uneven Tone"},
    {"id": "texture", "label": "Texture / Scarring"},
    {"id": "redness", "label": "Redness / Sensitivity"},
    {"id": "aging", "label": "Aging / Skin Quality"},
]

MAXX_GUIDELINES = {
    "skinmax": {
        "label": "SkinMax",
        "description": "AI-personalised skincare schedule based on your skin type and concerns.",
        "schedule_rules": {
            "am_timing": "After waking up, when user usually does skincare",
            "pm_timing": "1 hour before going to sleep so no substances rub off on pillow",
            "sunscreen_reapply": "Every 3 hours while user is outside",
            "learn_patterns": True,
            "wake_check": "Ask user to confirm they are awake each morning; if they say 'im awake' earlier or later, adjust",
        },
        "protocols": SKINMAX_PROTOCOLS,
        "concern_mapping": SKIN_TYPE_TO_CONCERN,
        "concern_question": "What's your ONE main skin concern? Pick one: Acne, Pigmentation, Texture, Redness, or Aging.",
        "concerns": SKINMAX_CONCERNS,
        "recurring": True,
        "daily_tasks": True,
        "weekly_tasks": True,
    },
}


def get_maxx_guideline(maxx_id: str) -> Optional[dict]:
    return MAXX_GUIDELINES.get(maxx_id)


def resolve_skin_concern(skin_type: Optional[str], explicit_concern: Optional[str] = None) -> str:
    if explicit_concern and explicit_concern in SKINMAX_PROTOCOLS:
        return explicit_concern
    return SKIN_TYPE_TO_CONCERN.get(skin_type or "normal", "aging")


def build_skinmax_prompt_section(concern: str) -> str:
    """Build protocol text for the Gemini prompt."""
    protocol = SKINMAX_PROTOCOLS.get(concern)
    if not protocol:
        protocol = SKINMAX_PROTOCOLS["aging"]

    return f"""## SKINCARE PROTOCOL — {protocol['label']}
AM Routine: {protocol['am']}
PM Routine: {protocol['pm']}
Weekly: {protocol['weekly']}
Sunscreen: {protocol['sunscreen']}

## SCHEDULE RULES
- AM routine time = shortly after user wakes up
- PM routine time = 1 hour before user goes to sleep (so nothing rubs off on pillow)
- Sunscreen reapply reminders every 3 hours IF user will be outside that day
- Weekly tasks (masks, exfoliants, peels) should be spread across the week
- Learn the user's patterns and adapt over time
"""
