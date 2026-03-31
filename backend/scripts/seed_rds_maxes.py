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
from services.maxx_guidelines import BONEMAX_MODULES, SKINMAX_MODULES


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

HEIGHTMAX_PROTOCOLS = {
    "posturemaxxing": {
        "label": "Posturemaxxing",
        "cadence": "All day posture rule with 1-2 reminder pushes per day.",
        "how_to": "Every 2-3 hours, stand up, pull chin straight back for 10 reps, squeeze shoulder blades down and back for 10 seconds, then walk for 1 minute without slouching.",
        "notification": "You're leaking inches. Chin back x 10. Stack ribs over pelvis. Walk tall for 60 sec.",
        "blackpill": "If your posture is cooked, you can look 1-2+ inches shorter than your frame reads. This is the highest-ROI height lever for adults because spinal posture changes presentation even when bone length does not.",
    },
    "sprintmaxxing": {
        "label": "Sprintmaxxing",
        "cadence": "2-3x per week, never daily.",
        "how_to": "After warm-up, do 6-10 sprints of 8-12 seconds with 60-90 seconds rest. Keep volume low and quality high.",
        "notification": "Sprint day. Short burst, full intent, long rest. Don't turn it into cardio.",
        "blackpill": "Sprinting is not a proven adult height hack; the value is that intense exercise can acutely raise GH/IGF-1 signaling and improves frame, leanness, and athletic posture. That helps you read taller, even if it does not lengthen bones.",
    },
    "deep_sleep_routine": {
        "label": "Deep Sleep Routine",
        "cadence": "Night routine, daily.",
        "how_to": "Keep a fixed sleep window, aim 7-9 hours, cut caffeine several hours before bed, cut screens 30-60 minutes before bed, and don't let bedtime drift.",
        "notification": "Height is won or lost tonight. Get off screens. Same sleep time. Don't sabotage the GH window.",
        "blackpill": "Sleep is the only hormone-maxxing habit that actually deserves obsession here. Tissue repair and growth-related hormone release are strongly tied to sleep. If you sleep like trash, everything else is cope.",
    },
    "decompress_lengthen": {
        "label": "Decompress / Lengthen",
        "cadence": "Dead hangs on waking plus a midday or evening decompression block daily if you sit a lot.",
        "how_to": "Dead hang 2 x 20-30 sec. Hip flexor stretch 2 x 30 sec/side. Hamstring stretch 2 x 30 sec/side. Thoracic extension over bench or foam roller for 5-8 slow reps.",
        "notification": "Decompress. Hang, open the hips, lengthen the hamstrings, and get your thoracic spine out of desk mode.",
        "blackpill": "This is for spinal decompression and posture height, not real bone growth. Very worth doing if you sit all day because compression posture makes you look shorter and weaker.",
    },
    "height_killers": {
        "label": "Height Killers",
        "cadence": "Daily anti-habit pushes.",
        "how_to": "Avoid chronic slouching, all-day sitting folded over, under-eating, sleep debt, added sugars, and overtraining. Do not sell porn or masturbation as a height lever; at most treat it as sleep sabotage or motivation drain.",
        "notification": "Stop doing the stuff that makes you look compressed, inflamed, under-recovered, and shorter.",
        "blackpill": "Most heightmaxxing online is fantasy. The real killers are boring: bad sleep, bad posture, bad recovery.",
    },
    "look_taller_instantly": {
        "label": "Look Taller Instantly",
        "cadence": "Immediate ROI presentation layer.",
        "how_to": "Prioritize posture, stay lean enough for a longer frame to show, use straighter-fitting clothes, avoid proportions that visually shorten the legs or torso, and use lifts only if you want the instant cheat code.",
        "notification": "If bones aren't changing, presentation has to. Stop dressing like you want to look compressed.",
        "blackpill": "For most adults, looking taller is more realistic than getting taller. That is not defeatist; it is just the highest-IQ route once growth plates are closed.",
    },
    "height_fuel": {
        "label": "Height Fuel",
        "cadence": "Daily with meals.",
        "how_to": "Hit 1.6-2.0 g/kg protein, keep calories adequate, and if supplementing, use a simple stack: vitamin D3, K2, magnesium, zinc, boron.",
        "notification": "Protein first. Growth-support stack with food. Don't under-eat and expect to grow or recover.",
        "blackpill": "Nutrition matters most before plates close and for recovery at any age. In adults, this supports posture, muscle, bone density, and frame, not miracle leg-bone lengthening.",
    },
    "hormones_to_max": {
        "label": "Hormones to Max",
        "cadence": "Behavior rules, daily.",
        "how_to": "Keep sleep tight, lift or sprint a few times weekly, avoid chronic stress spirals, and avoid big late-night sugar hits.",
        "notification": "Protect the hormone environment: train hard, recover harder, don't spike sugar before bed.",
        "blackpill": "Hormone maxxing is mostly code for don't nuke sleep and recovery. Repeated insulin spikes, poor sleep, and stress make you look softer, flatter, and more compressed; they are not helping your growth profile.",
    },
}

HEIGHTMAX_SCHEDULE_RULES = {
    "morning_decompression": "Schedule dead hangs and decompression work shortly after waking",
    "sleep_wind_down": "Push reminders 3 hours before bed for caffeine cutoff and 45 minutes before bed for screen cutoff",
    "posture_resets": "Send only 1-2 posture resets per day so the reminders stay high-value",
    "sprint_spacing": "Sprint sessions should be 2-3x per week with recovery days between them",
    "presentation_focus": "Prioritize posture, recovery, decompression, and presentation over fake height-growth claims",
}

HEIGHTMAX_PROTOCOL_PROMPT_TEMPLATE = """## HEIGHT PROTOCOL — {label}
Cadence: {cadence}
How to do it: {how_to}
Notification angle: {notification}
Blackpilled truth: {blackpill}

## SCHEDULE RULES
- Prioritize posture, recovery, decompression, and presentation, not fake bone-growth promises
- Morning decompression work should happen shortly after wake time
- Sleep routine reminders should start hours before bed so the user actually cuts caffeine and screens
- Posture reminders should be sparse but strict: 1-2 well-timed pushes beats notification spam
- Sprint sessions belong 2-3x per week with full recovery, never daily
- Include anti-habit reminders for slouching, under-recovery, and under-eating
"""

HEIGHTMAX_CONCERNS = [
    {"id": "posturemaxxing", "label": "Posturemaxxing"},
    {"id": "sprintmaxxing", "label": "Sprintmaxxing"},
    {"id": "deep_sleep_routine", "label": "Deep Sleep Routine"},
    {"id": "decompress_lengthen", "label": "Decompress / Lengthen"},
    {"id": "height_killers", "label": "Height Killers"},
    {"id": "look_taller_instantly", "label": "Look Taller Instantly"},
    {"id": "height_fuel", "label": "Height Fuel"},
    {"id": "hormones_to_max", "label": "Hormones to Max"},
]

HEIGHTMAX_MODULES = [
    {
        "title": "Posturemaxxing",
        "description": "Highest-ROI adult height lever because posture changes how your frame reads immediately.",
        "steps": [
            {"title": "All day rule", "content": "Ears over shoulders, ribcage stacked over pelvis, slight chin tuck, no phone-neck. Use occasional reminders only, around 1-2x a day."},
            {"title": "How to do it", "content": "Every 2-3 hours, stand up, pull chin straight back for 10 reps, squeeze shoulder blades down and back for 10 seconds, then walk for 1 minute without slouching."},
            {"title": "Notification", "content": "You're leaking inches. Chin back x 10. Stack ribs over pelvis. Walk tall for 60 sec."},
            {"title": "Blackpilled truth", "content": "If your posture is cooked, you can look 1-2+ inches shorter than your frame reads. This is the highest-ROI height lever for adults because spinal posture changes presentation even when bone length does not."},
        ],
    },
    {
        "title": "Sprintmaxxing",
        "description": "Frame, leanness, and posture play. Useful, but not bone-length science.",
        "steps": [
            {"title": "Cadence", "content": "Do it 2-3x per week, not daily."},
            {"title": "How to do it", "content": "After warm-up, do 6-10 sprints of 8-12 seconds with 60-90 seconds rest. Keep volume low and quality high."},
            {"title": "Best time", "content": "Afternoon or early evening, not right before bed."},
            {"title": "Notification", "content": "Sprint day. Short burst, full intent, long rest. Don't turn it into cardio."},
            {"title": "Blackpilled truth", "content": "Sprinting is not a proven adult height hack; the value is that intense exercise can acutely raise GH/IGF-1 signaling and improves frame, leanness, and athletic posture. That helps you read taller, even if it does not lengthen bones."},
        ],
    },
    {
        "title": "Deep Sleep Routine",
        "description": "The actual hormone-support habit worth obsessing over.",
        "steps": [
            {"title": "Cadence", "content": "Night routine, daily."},
            {"title": "How to do it", "content": "Keep a fixed sleep window, aim 7-9 hours, cut screens 30-60 minutes before bed, cut caffeine several hours before bed, and don't let bedtime drift."},
            {"title": "Notification", "content": "Height is won or lost tonight. Get off screens. Same sleep time. Don't sabotage the GH window."},
            {"title": "Blackpilled truth", "content": "Sleep is the only hormone-maxxing habit that actually deserves obsession here. Tissue repair and growth-related hormone release are strongly tied to sleep. If you sleep like trash, everything else is cope."},
        ],
    },
    {
        "title": "Decompress / Lengthen",
        "description": "Spinal decompression and posture height, not fake bone growth.",
        "steps": [
            {"title": "Cadence", "content": "Morning dead hangs on wake-up, plus a midday or evening decompression block daily if you sit a lot."},
            {"title": "How to do it", "content": "Dead hang: 2 x 20-30 sec. Hip flexor stretch: 2 x 30 sec/side. Hamstring stretch: 2 x 30 sec/side. Thoracic extension over bench or foam roller: 5-8 slow reps."},
            {"title": "Blackpilled truth", "content": "This is for spinal decompression and posture height, not real bone growth. Very worth doing if you sit all day because compression posture makes you look shorter and weaker."},
        ],
    },
    {
        "title": "Height Killers",
        "description": "Anti-habit module for the boring stuff that actually wrecks your presentation and recovery.",
        "steps": [
            {"title": "What to avoid", "content": "Chronic slouching, all-day sitting folded over, under-eating, sleep debt, added sugars, and overtraining."},
            {"title": "About no-gooning", "content": "There is no good evidence that porn or masturbation changes adult height, so don't frame it as a real height lever. If it stays in-app, frame it as sleep sabotage or motivation drain, not bone growth science."},
            {"title": "Notification", "content": "Stop doing the stuff that makes you look compressed, inflamed, under-recovered, and shorter."},
            {"title": "Blackpilled truth", "content": "Most heightmaxxing online is fantasy. The real killers are boring: bad sleep, bad posture, bad recovery."},
        ],
    },
    {
        "title": "Look Taller Instantly",
        "description": "Immediate ROI presentation module.",
        "steps": [
            {"title": "What to do", "content": "Prioritize posture, stay lean enough for a longer frame to show, use straighter-fitting clothes, avoid proportions that visually shorten the legs or torso, and use lifts only if you want the instant cheat code."},
            {"title": "Notification", "content": "If bones aren't changing, presentation has to. Stop dressing like you want to look compressed."},
            {"title": "Blackpilled truth", "content": "For most adults, looking taller is more realistic than getting taller. That is not defeatist; it is just the highest-IQ route once growth plates are closed."},
        ],
    },
    {
        "title": "Height Fuel",
        "description": "Recovery and frame support through food and a simple supplement stack.",
        "steps": [
            {"title": "Cadence", "content": "Daily with meals."},
            {"title": "How to do it", "content": "Hit 1.6-2.0 g/kg protein, keep calories adequate, and if supplementing, use a simple stack: vitamin D3, K2, magnesium, zinc, boron."},
            {"title": "Notification", "content": "Protein first. Growth-support stack with food. Don't under-eat and expect to grow or recover."},
            {"title": "Blackpilled truth", "content": "Nutrition matters most before plates close and for recovery at any age. In adults, this supports posture, muscle, bone density, and frame, not miracle leg-bone lengthening. Overweight or overnutrition can also speed skeletal maturation in youth, which can hurt final height."},
        ],
    },
    {
        "title": "Hormones to Max",
        "description": "Behavior rules for a better recovery environment.",
        "steps": [
            {"title": "Cadence", "content": "Behavior rules, daily."},
            {"title": "How to do it", "content": "Keep sleep tight, lift or sprint a few times weekly, avoid chronic stress spirals, and avoid big late-night sugar hits."},
            {"title": "Notification", "content": "Protect the hormone environment: train hard, recover harder, don't spike sugar before bed."},
            {"title": "Blackpilled truth", "content": "Hormone maxxing is mostly code for don't nuke sleep and recovery. Repeated insulin spikes, poor sleep, and stress make you look softer, flatter, and more compressed; they are not helping your growth profile. Exercise can stimulate GH acutely, but the basics still dominate."},
        ],
    },
]

MAXX_SEEDS = [
    {
        "id": "skinmax",
        "label": "Skinmax",
        "description": "skincare and your inner glow",
        "icon": "sparkles-outline",
        "color": "#8B5CF6",
        "modules": SKINMAX_MODULES,
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
    {"id": "bonemax", "label": "Bonemax", "description": "Facial bone / jawline stack — mewing, chewing form, fascia, nutrition, neck, masseter.", "icon": "body-outline", "color": "#F59E0B", "modules": BONEMAX_MODULES, "protocols": {}, "schedule_rules": {}, "concern_mapping": {}, "concern_question": None, "concerns": [], "protocol_prompt_template": None},
    {
        "id": "heightmax",
        "label": "Heightmax",
        "description": "Posture, recovery, decompression, and presentation rules that make your frame read taller.",
        "icon": "resize-outline",
        "color": "#6366F1",
        "modules": HEIGHTMAX_MODULES,
        "protocols": HEIGHTMAX_PROTOCOLS,
        "schedule_rules": HEIGHTMAX_SCHEDULE_RULES,
        "concern_mapping": {},
        "concern_question": "What's the main height lever you want to attack first? Pick one: Posturemaxxing, Sprintmaxxing, Deep Sleep Routine, Decompress / Lengthen, Height Killers, Look Taller Instantly, Height Fuel, or Hormones to Max.",
        "concerns": HEIGHTMAX_CONCERNS,
        "protocol_prompt_template": HEIGHTMAX_PROTOCOL_PROMPT_TEMPLATE,
    },
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
