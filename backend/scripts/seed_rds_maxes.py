"""
Seed RDS maxes table with schedule guidelines (protocols, schedule_rules, concerns).
Run after migrations. Safe to run repeatedly — upserts by maxx id.

Usage:
    cd backend
    .\venv\Scripts\python.exe scripts/seed_rds_maxes.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from models.rds_models import Maxx
from db.rds import init_rds_db, close_rds_db, RDSSessionLocal


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

SKIN_TYPE_TO_CONCERN = {
    "oily": "acne",
    "dry": "aging",
    "combination": "acne",
    "sensitive": "redness",
    "normal": "aging",
}

SKINMAX_SCHEDULE_RULES = {
    "am_timing": "After waking up, when user usually does skincare",
    "pm_timing": "1 hour before going to sleep so no substances rub off on pillow",
    "sunscreen_reapply": "Every 3 hours while user is outside",
    "learn_patterns": True,
    "wake_check": "Ask user to confirm they are awake each morning; if they say 'im awake' earlier or later, adjust",
}

SKINMAX_PROTOCOL_PROMPT_TEMPLATE = """## SKINCARE PROTOCOL — {label}
AM Routine: {am}
PM Routine: {pm}
Weekly: {weekly}
Sunscreen: {sunscreen}

## SCHEDULE RULES
- AM routine time = shortly after user wakes up
- PM routine time = 1 hour before user goes to sleep (so nothing rubs off on pillow)
- Sunscreen reapply reminders every 3 hours IF user will be outside that day
- Weekly tasks (masks, exfoliants, peels) should be spread across the week
- Learn the user's patterns and adapt over time
"""

SKINMAX_CONCERNS = [
    {"id": "acne", "label": "Acne / Congestion"},
    {"id": "pigmentation", "label": "Pigmentation / Uneven Tone"},
    {"id": "texture", "label": "Texture / Scarring"},
    {"id": "redness", "label": "Redness / Sensitivity"},
    {"id": "aging", "label": "Aging / Skin Quality"},
]

MAXX_SEEDS = [
    {
        "id": "skinmax",
        "label": "SkinMax",
        "description": "AI-personalised skincare schedule based on your skin type and concerns.",
        "icon": "sparkles-outline",
        "color": "#8B5CF6",
        "modules": [],
        "protocols": SKINMAX_PROTOCOLS,
        "schedule_rules": SKINMAX_SCHEDULE_RULES,
        "concern_mapping": SKIN_TYPE_TO_CONCERN,
        "concern_question": "What's your ONE main skin concern? Pick one: Acne, Pigmentation, Texture, Redness, or Aging.",
        "concerns": SKINMAX_CONCERNS,
        "protocol_prompt_template": SKINMAX_PROTOCOL_PROMPT_TEMPLATE,
    },
    # Placeholder maxxes — add protocols, concerns, etc. when you have rules
    {"id": "hairmax", "label": "Hairmax", "description": "Hair growth and scalp health.", "icon": "cut-outline", "color": "#3B82F6", "modules": [], "protocols": {}, "schedule_rules": {}, "concern_mapping": {}, "concern_question": None, "concerns": [], "protocol_prompt_template": None},
    {"id": "fitmax", "label": "Fitmax", "description": "Training and physique.", "icon": "fitness-outline", "color": "#10B981", "modules": [], "protocols": {}, "schedule_rules": {}, "concern_mapping": {}, "concern_question": None, "concerns": [], "protocol_prompt_template": None},
    {"id": "bonemax", "label": "Bonemax", "description": "Facial structure optimization.", "icon": "body-outline", "color": "#F59E0B", "modules": [], "protocols": {}, "schedule_rules": {}, "concern_mapping": {}, "concern_question": None, "concerns": [], "protocol_prompt_template": None},
    {"id": "heightmax", "label": "Heightmax", "description": "Posture and height optimization.", "icon": "resize-outline", "color": "#6366F1", "modules": [], "protocols": {}, "schedule_rules": {}, "concern_mapping": {}, "concern_question": None, "concerns": [], "protocol_prompt_template": None},
]


async def seed():
    await init_rds_db()
    async with RDSSessionLocal() as session:
        for data in MAXX_SEEDS:
            result = await session.execute(select(Maxx).where(Maxx.id == data["id"]))
            existing = result.scalar_one_or_none()
            if existing:
                # Update with guidelines (merge, don't overwrite id/label if we want to preserve)
                for k, v in data.items():
                    if hasattr(existing, k):
                        setattr(existing, k, v)
                print(f"✅ Updated {data['id']}")
            else:
                row = Maxx(**{k: v for k, v in data.items() if k in [c.key for c in Maxx.__table__.columns]})
                session.add(row)
                print(f"✅ Created {data['id']}")
        await session.commit()
    await close_rds_db()


if __name__ == "__main__":
    asyncio.run(seed())
