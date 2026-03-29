"""
Maxx Schedule Guidelines — Protocol definitions for each maxx type.
Each maxx has a set of skin-concern (or goal-based) protocols the AI uses
to generate personalised daily/weekly schedules.

To add a new maxx, create a dict entry in MAXX_GUIDELINES with the same shape.
"""

from typing import Any, Optional

from services.prompt_loader import PromptKey, resolve_prompt

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

# Expandable module cards (Maxx detail UI) — same shape as HEIGHTMAX_MODULES
SKINMAX_MODULES = [
    {
        "title": "Acne / Congestion",
        "description": "Oil control, actives that work, and a barrier that doesn't bail on you.",
        "steps": [
            {"title": "AM routine", "content": SKINMAX_PROTOCOLS["acne"]["am"]},
            {"title": "PM routine", "content": SKINMAX_PROTOCOLS["acne"]["pm"]},
            {"title": "Weekly", "content": SKINMAX_PROTOCOLS["acne"]["weekly"]},
            {"title": "Sunscreen", "content": SKINMAX_PROTOCOLS["acne"]["sunscreen"]},
        ],
    },
    {
        "title": "Pigmentation / Uneven Tone",
        "description": "Brighten, fade spots, and block UV — SPF is non-negotiable.",
        "steps": [
            {"title": "AM routine", "content": SKINMAX_PROTOCOLS["pigmentation"]["am"]},
            {"title": "PM routine", "content": SKINMAX_PROTOCOLS["pigmentation"]["pm"]},
            {"title": "Weekly", "content": SKINMAX_PROTOCOLS["pigmentation"]["weekly"]},
            {"title": "Sunscreen", "content": SKINMAX_PROTOCOLS["pigmentation"]["sunscreen"]},
        ],
    },
    {
        "title": "Texture / Scarring",
        "description": "Smooth surface, support collagen, and protect healing skin from UV.",
        "steps": [
            {"title": "AM routine", "content": SKINMAX_PROTOCOLS["texture"]["am"]},
            {"title": "PM routine", "content": SKINMAX_PROTOCOLS["texture"]["pm"]},
            {"title": "Weekly", "content": SKINMAX_PROTOCOLS["texture"]["weekly"]},
            {"title": "Sunscreen", "content": SKINMAX_PROTOCOLS["texture"]["sunscreen"]},
        ],
    },
    {
        "title": "Redness / Sensitivity",
        "description": "Barrier first, gentle actives, no unnecessary irritation.",
        "steps": [
            {"title": "AM routine", "content": SKINMAX_PROTOCOLS["redness"]["am"]},
            {"title": "PM routine", "content": SKINMAX_PROTOCOLS["redness"]["pm"]},
            {"title": "Weekly", "content": SKINMAX_PROTOCOLS["redness"]["weekly"]},
            {"title": "Sunscreen", "content": SKINMAX_PROTOCOLS["redness"]["sunscreen"]},
        ],
    },
    {
        "title": "Aging / Skin Quality",
        "description": "Retinoids, antioxidants, daily SPF — aging is a long game.",
        "steps": [
            {"title": "AM routine", "content": SKINMAX_PROTOCOLS["aging"]["am"]},
            {"title": "PM routine", "content": SKINMAX_PROTOCOLS["aging"]["pm"]},
            {"title": "Weekly", "content": SKINMAX_PROTOCOLS["aging"]["weekly"]},
            {"title": "Sunscreen", "content": SKINMAX_PROTOCOLS["aging"]["sunscreen"]},
        ],
    },
]

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
        "how_to": "After a proper warm-up, do 6-10 sprints of 8-12 seconds with 60-90 seconds rest. Keep volume low and quality high.",
        "notification": "Sprint day. Short burst, full intent, long rest. Don't turn it into cardio.",
        "blackpill": "Sprinting is not a proven adult height hack; the value is that intense exercise can acutely raise GH/IGF-1 signaling and improves frame, leanness, and athletic posture. That helps you read taller, even if it does not lengthen bones.",
    },
    "deep_sleep_routine": {
        "label": "Deep Sleep Routine",
        "cadence": "Night routine, every day.",
        "how_to": "Keep a fixed sleep window, aim for 7-9 hours, cut caffeine several hours before bed, cut screens 30-60 minutes before bed, and do not let bedtime drift.",
        "notification": "Height is won or lost tonight. Get off screens. Same sleep time. Don't sabotage the GH window.",
        "blackpill": "Sleep is the only hormone-maxxing habit that actually deserves obsession here. Tissue repair and growth-related hormone release are strongly tied to sleep. If you sleep like trash, everything else is cope.",
    },
    "decompress_lengthen": {
        "label": "Decompress / Lengthen",
        "cadence": "Dead hangs on waking, plus a midday or evening decompression block daily if you sit a lot.",
        "how_to": "Dead hang 2 x 20-30 sec. Hip flexor stretch 2 x 30 sec/side. Hamstring stretch 2 x 30 sec/side. Thoracic extension over bench or foam roller for 5-8 slow reps.",
        "notification": "Decompress. Hang, open the hips, lengthen the hamstrings, and get your thoracic spine out of desk mode.",
        "blackpill": "This is for spinal decompression and posture height, not real bone growth. Very worth doing if you sit all day because compression posture makes you look shorter and weaker.",
    },
    "height_killers": {
        "label": "Height Killers",
        "cadence": "Daily anti-habit checks.",
        "how_to": "Avoid chronic slouching, all-day sitting folded over, under-eating, sleep debt, added sugars, and overtraining. If porn stays in the app, frame it as sleep sabotage or motivation drain, not bone growth science.",
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
        "cadence": "Behavior rules, every day.",
        "how_to": "Keep sleep tight, lift or sprint a few times weekly, avoid chronic stress spirals, and avoid big late-night sugar hits.",
        "notification": "Protect the hormone environment: train hard, recover harder, don't spike sugar before bed.",
        "blackpill": "Hormone maxxing is mostly code for not nuking sleep and recovery. Poor sleep, stress, and repeated insulin spikes make you look softer, flatter, and more compressed; they are not helping your growth profile.",
    },
}

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

# ---------------------------------------------------------------------------
# HairMax protocols keyed by concern
# ---------------------------------------------------------------------------
HAIR_TYPE_TO_CONCERN = {
    "straight": "wash_routine",
    "wavy": "wash_routine",
    "curly": "wash_routine",
    "thinning": "minoxidil",
    "normal": "wash_routine",
}

HAIRMAX_PROTOCOLS = {
    "wash_routine": {
        "label": "Wash Routine",
        "shampoo": "Gentle, sulfate-free, paraben-free, scalp-focused (not harsh stripping)",
        "conditioner": "Always on hair strands, never on scalp unless specifically intended. Leave-in conditioner is safest broad recommendation.",
        "frequency_straight_wavy": "Shampoo 2–3x/week",
        "frequency_curly": "Shampoo less often, build fixed wash days; optional co-wash between",
        "frequency_product_heavy": "If product used daily, wash out buildup every couple days",
        "over_washed_signs": "Dry + small white flakes → reduce shampoo frequency",
        "under_washed_signs": "Greasy itchy scalp + buildup → increase wash frequency",
        "rule": "Never push 'no shampoo' as a recommendation",
    },
    "anti_dandruff": {
        "label": "Anti-Dandruff Protocol",
        "when_to_use": "Only if flakes are oily/yellow/persistent OR scalp stays itchy despite gentle products",
        "shampoo": "Anti-dandruff shampoo (ketoconazole, zinc pyrithione, or selenium sulfide based)",
        "frequency": "2–3x/week during flare, reduce to 1x/week maintenance once controlled",
        "conditioner": "Still use conditioner on strands after anti-dandruff shampoo",
        "rule": "Do not recommend anti-dandruff unless clear signs of fungal/seborrheic issue",
    },
    "oils_masks": {
        "label": "Oils & Hair Masks",
        "when_to_use": "For dry/damaged hair, pre-wash treatment, or scalp nourishment",
        "frequency": "1–2x/week",
        "how_to": "Apply oil to scalp and lengths 30 mins to overnight before washing. Massage into scalp.",
        "best_oils": "Castor oil, rosemary oil, argan oil, coconut oil (avoid if protein-sensitive)",
        "masks": "Deep conditioning mask 1x/week after shampooing, leave 5–10 mins",
        "notification": "Oil your scalp tonight. Massage in, leave overnight, wash tomorrow.",
    },
    "minoxidil": {
        "label": "Minoxidil Protocol",
        "who_needs_it": "Anyone with visible hair thinning, receding hairline, or crown thinning",
        "when_to_apply": "PM skincare time, before skincare routine. Optional morning secondary if user is advanced.",
        "frequency": "Daily (non-negotiable)",
        "how_to": "Apply to thinning areas only (hairline, crown, temples). Let dry before bed.",
        "notification_core": "Minoxidil. Thinning areas only.",
        "notification_pressure": "Miss days = lose gains.",
        "notification_identity": "You either maintain your hairline or watch it go.",
        "notification_skip_escalate": "Skipped yesterday. That's how hairlines die. Apply now.",
        "notification_consistent": "Minoxidil done? Good. Keep the streak.",
        "rule": "Daily application is non-negotiable for results. Consistency is everything.",
    },
    "dermastamp": {
        "label": "Dermastamp / Dermaroller",
        "who_needs_it": "Anyone with hair thinning, used alongside minoxidil for enhanced absorption and stimulation",
        "when_to_use": "Evening PM skincare time before bed. Ideally same day each week (habit lock).",
        "frequency": "1x/week default, max 2x/week (never more)",
        "how_to": "Use 0.5–1.5mm needles on hairline/crown only. Clean device before/after. Do not apply minoxidil immediately after (wait 24 hours).",
        "notification": "Dermastamp tonight. Hairline/crown only.",
        "rule": "Never exceed 2x/week. Always sterilize. Don't stack with minoxidil same night.",
    },
}

HAIRMAX_CONCERNS = [
    {"id": "wash_routine", "label": "Wash Routine Optimization"},
    {"id": "anti_dandruff", "label": "Anti-Dandruff Treatment"},
    {"id": "oils_masks", "label": "Oils & Hair Masks"},
    {"id": "minoxidil", "label": "Minoxidil (Hair Thinning)"},
    {"id": "dermastamp", "label": "Dermastamp / Dermaroller"},
]

HAIRMAX_MODULES = [
    {
        "title": "Shampoo & Conditioner Basics",
        "description": "The foundation of healthy hair: choosing the right products and using them correctly.",
        "steps": [
            {"title": "Shampoo selection", "content": "Use a gentle, sulfate-free, paraben-free shampoo. Focus on scalp cleansing, not harsh stripping. Your shampoo should clean without leaving hair squeaky or dry."},
            {"title": "Conditioner rules", "content": "Always use conditioner on the hair strands (mid-length to ends). Do NOT put conditioner on your scalp unless it's specifically designed for scalp use. Leave-in conditioner is the safest broad recommendation for most users."},
            {"title": "Anti-dandruff trigger", "content": "Only use anti-dandruff shampoo if: flakes are oily/yellow/persistent, OR scalp stays itchy despite using gentle products. Don't jump to anti-dandruff for simple dry scalp."},
            {"title": "Blackpilled truth", "content": "Most hair problems come from using the wrong products or washing incorrectly. Get this foundation right before adding anything else."},
        ],
    },
    {
        "title": "When to Wash",
        "description": "Wash frequency based on your hair type. Over-washing and under-washing both cause problems.",
        "steps": [
            {"title": "Straight/wavy hair", "content": "Shampoo 2–3x/week. This balances oil control without stripping."},
            {"title": "Curly hair", "content": "Shampoo less often. Build fixed wash days (e.g., Sunday/Wednesday). Optional co-wash between shampoo days to refresh without stripping."},
            {"title": "Product users", "content": "If you use styling products daily, wash out buildup every couple of days. Product buildup suffocates follicles."},
            {"title": "Over-washed signs", "content": "Dry hair + small white flakes = you're washing too much. Reduce shampoo frequency."},
            {"title": "Under-washed signs", "content": "Greasy itchy scalp + visible buildup = you're not washing enough. Increase wash frequency."},
            {"title": "Golden rule", "content": "Never push 'no shampoo' lifestyle. Your scalp needs cleaning."},
        ],
    },
    {
        "title": "Oils & Hair Masks",
        "description": "Deep nourishment for scalp and hair health.",
        "steps": [
            {"title": "When to use", "content": "For dry/damaged hair, as a pre-wash treatment, or for scalp nourishment."},
            {"title": "Frequency", "content": "Oil treatment 1–2x/week. Deep conditioning mask 1x/week."},
            {"title": "How to oil", "content": "Apply oil to scalp and lengths 30 mins to overnight before washing. Massage into scalp for 5 minutes to stimulate blood flow. Wash out the next morning."},
            {"title": "Best oils", "content": "Castor oil (thickness), rosemary oil (growth stimulation), argan oil (shine/moisture), coconut oil (penetrates shaft—avoid if protein-sensitive)."},
            {"title": "Hair mask protocol", "content": "After shampooing, apply deep conditioning mask. Leave 5–10 mins. Rinse thoroughly. Do this 1x/week."},
            {"title": "Notification", "content": "Oil your scalp tonight. Massage in, leave overnight, wash tomorrow."},
        ],
    },
    {
        "title": "Minoxidil Protocol",
        "description": "The non-negotiable daily treatment for anyone with hair thinning. Miss days = lose gains.",
        "steps": [
            {"title": "Who needs it", "content": "Anyone with visible hair thinning, receding hairline, temple recession, or crown thinning. If you're losing hair, this is the intervention."},
            {"title": "When to apply", "content": "PM skincare time, before your skincare routine. Let it dry before bed. Optional: morning secondary application if you're advanced and committed."},
            {"title": "Frequency", "content": "Daily. Non-negotiable. This is not optional if you want results."},
            {"title": "How to apply", "content": "Apply to thinning areas only—hairline, crown, temples. Use dropper or foam. Massage in gently. Let dry completely before sleeping."},
            {"title": "Notification: Core", "content": "Minoxidil. Thinning areas only."},
            {"title": "Notification: Pressure", "content": "Miss days = lose gains."},
            {"title": "Notification: Identity", "content": "You either maintain your hairline or watch it go."},
            {"title": "If you skip", "content": "Escalate tone: 'Skipped yesterday. That's how hairlines die. Apply now.'"},
            {"title": "If you're consistent", "content": "Reduce to 1 clean reminder/day: 'Minoxidil done? Good. Keep the streak.'"},
            {"title": "Blackpilled truth", "content": "Minoxidil works. But only if you use it every single day. One week off can undo months of progress. This is a lifetime commitment if you want to keep your hair."},
        ],
    },
    {
        "title": "Dermastamp / Dermaroller",
        "description": "Weekly microneedling for enhanced minoxidil absorption and follicle stimulation. High friction, high reward.",
        "steps": [
            {"title": "Who needs it", "content": "Anyone with hair thinning. Used alongside minoxidil for enhanced absorption and direct follicle stimulation."},
            {"title": "When to use", "content": "Evening PM skincare time before bed. Pick the same day each week to lock in the habit (e.g., every Sunday night)."},
            {"title": "Frequency", "content": "1x/week default. Maximum 2x/week. Never more—you need scalp recovery time."},
            {"title": "How to do it", "content": "Use 0.5–1.5mm needle length. Target hairline and crown only. Roll/stamp in multiple directions. Clean and sterilize device before and after use."},
            {"title": "Minoxidil timing", "content": "Do NOT apply minoxidil immediately after dermastamping. Wait 24 hours. The micro-wounds need to heal first."},
            {"title": "Notification", "content": "Dermastamp tonight. Hairline/crown only."},
            {"title": "Blackpilled truth", "content": "Microneedling creates micro-injuries that trigger healing response and increase blood flow to follicles. Combined with minoxidil, it's one of the most effective non-surgical interventions. But overdoing it causes scarring. Stick to 1x/week."},
        ],
    },
]

# Expandable cards for Bonemax detail UI (same shape as SKINMAX_MODULES / HEIGHTMAX_MODULES)
BONEMAX_MODULES = [
    {
        "title": "Mewing & oral posture",
        "description": "All-day tongue posture, resets, and optional hard mewing caps — backend turns this into timed cues.",
        "steps": [
            {"title": "Baseline", "content": "Tongue up, lips sealed, nasal breathing, teeth light touch, jaw relaxed."},
            {"title": "Resets", "content": "Morning 30–60s; midday after screens; night 30s check before sleep."},
            {"title": "Hard mewing", "content": "1–2x/day max, short holds, stop if tension builds."},
        ],
    },
    {
        "title": "Chewing posture",
        "description": "Meal-time form: symmetrical load, premolar bias, no clench — reminders only; schedule has the cadence.",
        "steps": [
            {"title": "During meals", "content": "Head upright, lips sealed when possible, slow deliberate chews, alternate sides."},
            {"title": "Non-negotiables", "content": "No one-side-only chewing, no forward-head gnawing, no sloppy open-mouth chewing."},
        ],
    },
    {
        "title": "Fascia / lymph",
        "description": "Light drainage and optional contrast — timed in your schedule, not invented in chat.",
        "steps": [
            {"title": "AM", "content": "Short tapping + drainage paths after cleansing; feather-light pressure."},
            {"title": "PM", "content": "Evening sessions a few nights/week; skip on harsh actives nights."},
        ],
    },
    {
        "title": "Bone nutrition · neck · masseter",
        "description": "Stack with meals, neck work after training days, mastic gum volume with rest logic — all encoded as tasks.",
        "steps": [
            {"title": "Nutrition", "content": "Bone-support stack concept with meals (e.g. D3, K2, magnesium, zinc, boron) — follow your own products."},
            {"title": "Neck", "content": "Chin tucks + accessory work; scaled if TMJ-sensitive."},
            {"title": "Mastic gum", "content": "One main session/day max, form-first, stop if clicking or pain."},
        ],
    },
]

# ---------------------------------------------------------------------------
# FitMax — phase protocols (Cut / Lean bulk / Recomp / Maintain)
# ---------------------------------------------------------------------------
FITMAX_PROTOCOLS = {
    "cut": {
        "label": "Cut — deficit, preserve muscle, face gains",
        "cadence": "Train 3–6×/week per user availability; pre-workout −30m, post +15m after session",
        "how_to": "Caloric deficit (~TDEE−500), protein ≥1g/lb, train for hypertrophy with lateral raise + face pull volume every session pattern.",
        "notification": "Anchor protein early; remind session focus + progressive overload when logs show top-of-range reps.",
        "blackpill": "Face leanness is mostly kitchen + consistency; one perfect workout won't outrun a surplus.",
    },
    "lean_bulk": {
        "label": "Lean bulk — small surplus, keep facial definition",
        "cadence": "3–6×/week; monitor scale +0.5–1 lb/wk max",
        "how_to": "TDEE+250–300, protein ~1g/lb, bias shoulders/back volume; deload when stalls.",
        "notification": "Surplus discipline: if weight spikes >1 lb/wk, pull 200 kcal; hit protein every meal.",
        "blackpill": "Fast bulk = fat face; slow surplus keeps jawline in the game.",
    },
    "recomp": {
        "label": "Recomp — maintenance + high protein (beginner window)",
        "cadence": "3–5×/week full-body or split per equipment",
        "how_to": "Eat at maintenance, protein ~1g/lb, progressive overload on compounds + accessories.",
        "notification": "Protein is the lever; sleep and steps support recomp more than macro perfectionism.",
        "blackpill": "Recomp is real for novices — not for skipping protein or training like a tourist.",
    },
    "maintain": {
        "label": "Maintain — sweet spot physique",
        "cadence": "Keep training consistent; same notification anchors for habit glue",
        "how_to": "TDEE maintenance, protein ~0.8–1g/lb, keep face pulls + shoulder volume as identity habits.",
        "notification": "Consistency beats novelty; weekly weigh-in + monthly photos catch drift early.",
        "blackpill": "Maintenance still needs structure — drifting off plan is how people 'accidentally' bulk.",
    },
}

FITMAX_CONCERNS = [
    {"id": "cut", "label": "Cut / get lean"},
    {"id": "lean_bulk", "label": "Lean bulk"},
    {"id": "recomp", "label": "Recomp"},
    {"id": "maintain", "label": "Maintain"},
]

MAXX_GUIDELINES = {
    "skinmax": {
        "label": "skinmax",
        "description": "Skincare and gut health",
        "schedule_rules": {
            "engine": "skinmax_notification_engine_reference.md",
            "am_routine": "wake_time + 15 minutes (never generic 'morning' without deriving from wake)",
            "pm_routine": "bed_time - 60 minutes",
            "midday_tip": "midpoint between AM routine and PM routine",
            "hydration": "midday + 2 hours (toggle off via skin_hydration_notifications)",
            "spf_reapply": "AM routine + 3 hours; only if outdoor_frequency is always or sometimes (sometimes + outside_today); never if rarely",
            "quiet_hours": "No notifications between bed_time and wake_time",
            "daily_budget": "min 3 (AM + midday + PM), max 5 notifications",
            "weekly": "exfoliation on chosen weekday at PM time (replaces PM); pillowcase Sunday at midday time",
            "monthly": "progress photo 1st at midday; check-in 1st at PM+30m",
            "retinoid_ramp": "Automatic Mon/Thu → MWF → EOD → nightly per weeks since start; exfoliation day = rest night",
            "learn_patterns": True,
        },
          "intake_questions": [
        "What time do you usually wake up AND go to sleep? (e.g., 7am / 11pm)"
    ],
        "protocols": SKINMAX_PROTOCOLS,
        "concern_mapping": SKIN_TYPE_TO_CONCERN,
        "concern_question": "What's your ONE main skin concern? Pick one: Acne, Pigmentation, Texture, Redness, or Aging.",
        "concerns": SKINMAX_CONCERNS,
        "modules": SKINMAX_MODULES,
        "recurring": True,
        "daily_tasks": True,
        "weekly_tasks": True,
    },
    "heightmax": {
        "label": "Heightmax",
        "description": "Posture, recovery, and presentation rules that make your frame read taller.",
        "schedule_rules": {
            "engine": "heightmax_notification_engine_reference.md",
            "morning_decompression": "wake_time + 20 minutes",
            "midday_posture": "midpoint(wake+15min, bed−60min) — same as BoneMax midday",
            "afternoon_posture": "midday + 3 hours if 6+ hours screen/day at onboarding",
            "evening_decompression": "bed_time − 90 minutes",
            "sleep_gh_protocol": "bed_time − 45 minutes",
            "sprint_reminder": "30 minutes before workout on sprint days (2–3×/week, non-consecutive)",
            "height_nutrition": "wake+1h or wake+5h — only if user opted in",
            "weekly_measurement": "Sunday wake + 30 minutes",
            "monthly_checkin": "1st of month at midday posture time",
            "quiet_hours": "No notifications between bed and wake",
            "daily_cap": "Typically 6–7/day full stack; max 10/day with other modules",
            "sprint_spacing": "Sprint sessions 2–3×/week, never consecutive days",
            "presentation_focus": "Tier 3: no fake inch promises — posture/decompression reclamation only",
        },
        "modules": HEIGHTMAX_MODULES,
        "protocols": HEIGHTMAX_PROTOCOLS,
        "concern_mapping": {},
        "concern_question": "What's the main height lever you want to attack first? Pick one: Posturemaxxing, Sprintmaxxing, Deep Sleep Routine, Decompress / Lengthen, Height Killers, Look Taller Instantly, Height Fuel, or Hormones to Max.",
        "concerns": HEIGHTMAX_CONCERNS,
        "recurring": True,
        "daily_tasks": True,
        "weekly_tasks": True,
        "protocol_prompt_template": """## HEIGHT PROTOCOL — {label}
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

- Learn the user's patterns and adjust timing if they complete tasks early/late
- If the user repeatedly skips steps, reduce friction and simplify the routine

- All tasks MUST be anchored to the user's wake and sleep times
- Do NOT output vague times like "morning" or "night"
- Convert everything into exact clock times

""",
    },
    "fitmax": {
        "label": "FitMax",
        "description": "Aesthetic hypertrophy, phased nutrition, body comp tracking, and face-gains framing — not powerlifting-first.",
        "schedule_rules": {
            "engine": "fitmax_notification_engine_reference.md",
            "pre_workout": "preferred_workout_time − 30 minutes",
            "post_workout": "estimated_workout_end + 15 minutes",
            "morning_nutrition": "wake_time + 30 minutes",
            "midday_aesthetics": "midpoint(wake+15min, bed−60min)",
            "evening_nutrition": "bed_time − 2 hours",
            "weekly_weigh_in": "Monday wake + 15 minutes",
            "monthly_body_check": "1st of month at midday aesthetics time",
            "quiet_hours": "No notifications between bed and wake",
            "daily_cap": "5–6 workout days, 3–4 rest days; max 10/day with other modules",
            "phase_in": "W1–2 training+AM nutrition+weigh-in; W3–4 +PM+supplements; W5+ +midday tips+monthly",
            "learn_patterns": True,
        },
        "protocols": FITMAX_PROTOCOLS,
        "concern_mapping": {},
        "concern_question": "Body-composition phase is auto-routed from body fat + goal (Cut / Lean bulk / Recomp / Maintain).",
        "concerns": FITMAX_CONCERNS,
        "recurring": True,
        "daily_tasks": True,
        "weekly_tasks": True,
        "protocol_prompt_template": """## FITMAX PROTOCOL — {label}
Cadence: {cadence}
How to do it: {how_to}
Notification angle: {notification}
Blackpilled truth: {blackpill}

## SCHEDULE RULES
- **Workout days:** pre-workout (−30m) + post-workout (+15m after estimated session end) only on scheduled lift days
- **Daily:** morning nutrition (wake+30) + evening closeout (bed−2h); merge supplements at wake+30 if opted in
- **Monday:** weekly weigh-in at wake+15; **1st of month:** body check at midday anchor
- **Midday:** 10-day rotating aesthetics tip (omit posture overlap if BoneMax active — swap for training/nutrition tips)
- **Phase routing:** use engine reference (BF% + goal → Cut / Lean bulk / Recomp / Maintain)
- **No-track users:** portion-based guidance, no macro numbers in copy
- **TDEE:** Mifflin–St Jeor; tune from weigh-in trends monthly
- All tasks use **exact HH:MM** from wake, bed, and preferred workout time

""",
    },
    "hairmax": {
        "label": "HairMax",
        "description": "AI-personalised hair care schedule based on your hair type and concerns (thinning, wash routine, scalp health).",
        "schedule_rules": {
            "engine": "hairmax_notification_engine_reference.md",
            "minoxidil_am": "wake_time + 15 minutes",
            "minoxidil_pm": "bed_time − 90 minutes",
            "finasteride_daily": "typically wake + 30–45 min (user-adjustable); topical fin at night if oral skipped",
            "ketoconazole": "2–3×/week on wash days only",
            "microneedling": "1×/week; not same night as minoxidil (24h); stagger vs face microneedling if SkinMax active",
            "midday": "midpoint(wake+15, bed−60) for monthly check-in (1st) and rotating tips",
            "bloodwork": "Baseline ~3d after oral fin start, +180d, +365d — not daily",
            "treatment_ramp": "M1 fin+keto → M2–3 +minox 2× → M4+ microneedling",
            "quiet_hours": "No notifications between bed and wake",
            "daily_cap": "~4–5/day full stack; max 10/day with other modules",
            "learn_patterns": True,
        },
          "intake_questions": [
        "What time do you usually wake up AND go to sleep? (e.g., 7am / 11pm)"
    ],
        "modules": HAIRMAX_MODULES,
        "protocols": HAIRMAX_PROTOCOLS,
        "concern_mapping": HAIR_TYPE_TO_CONCERN,
        "concern_question": "What's your main hair concern? Pick one: Wash Routine, Anti-Dandruff, Oils & Masks, Minoxidil (for thinning), or Dermastamp.",
        "concerns": HAIRMAX_CONCERNS,
        "recurring": True,
        "daily_tasks": True,
        "weekly_tasks": True,
        "protocol_prompt_template": """## HAIR PROTOCOL — {label}

{protocol_details}

## SCHEDULE RULES
- Wash frequency depends on hair type: straight/wavy 2-3x/week, curly less often with optional co-wash
- Minoxidil is PM skincare time, daily, non-negotiable for thinning users
- Dermastamp is 1x/week max, same day each week, never same night as minoxidil (wait 24h)
- Oil treatments are 1-2x/week, evening before wash day as overnight treatment
- Anti-dandruff shampoo only when clear fungal/seborrheic signs, not for simple dry scalp
- Conditioner goes on strands only, never on scalp unless specifically designed for it
- Never push "no shampoo" as a lifestyle recommendation

## NOTIFICATION RULES FOR THINNING USERS
- Core reminder: "Minoxidil. Thinning areas only."
- Consistency pressure: "Miss days = lose gains."
- Identity framing: "You either maintain your hairline or watch it go."
- If user skips: escalate tone slightly
- If user is consistent: reduce to 1 clean reminder/day
- Prioritize highest ROI actions
- Do NOT spam repeated reminders for the same task
""",
    },
    "bonemax": {
        "label": "Bonemax",
        "description": "Facial bone / jawline stack: mewing, chewing form, fascia, bone nutrition, neck training, masseter gum.",
        "schedule_rules": {
            "engine": "bonemax_notification_engine_reference.md",
            "mewing_morning": "wake_time — first ping of the day",
            "mewing_midday": "midpoint(wake+15min, bed−60min) — same active-day logic as SkinMax midday",
            "mewing_night": "bed_time − 30 minutes — bundles sleep optimization + nasal night notes",
            "facial_exercises": "wake + 15 minutes",
            "fascia_morning": "wake + 20 minutes",
            "fascia_evening": "bed − 90 minutes, 4–5×/week; skip on SkinMax retinoid/exfol nights when applicable",
            "masseter_default": "user-chosen or wake + 2 hours",
            "nasal_check": "midday mewing + 2h (2× if screen 6+h, max 2/day)",
            "neck_training": "15 min after workout end on workout days; chin tucks in midday mewing on non-workout days",
            "symmetry": "1×/day between midday and evening, weekly rotating tips",
            "bone_nutrition": "1×/day at meal only if user opted in — no nag otherwise",
            "quiet_hours": "No notifications between bed and wake",
            "daily_cap": "Hard cap 10 notifications/day across all modules; use phased rollout 1→2→3",
            "learn_patterns": True,
        },
        "protocols": {
            "bonemax_stack": {
                "label": "BoneMax / jawline stack",
                "task_families": (
                    "Encode: oral posture/mewing resets; chewing-form meal cues; fascia/lymph blocks; "
                    "bone-support nutrition with meals; neck training (chin tucks + accessory work); "
                    "mastic gum / masseter sessions with recovery logic."
                ),
            },
        },
        "concern_mapping": {},
        "concern_question": None,
        "concerns": [],
        "recurring": True,
        "daily_tasks": True,
        "weekly_tasks": True,
        "protocol_prompt_template": """## BONEMAX PROTOCOL — {label}

{task_families}

## SCHEDULE RULES
- Anchor tasks to wake_time and sleep_time; use exact HH:MM.
- Spread mewing/oral posture cues across the day; add extra midday resets if user has heavy screen time.
- Schedule chewing-form reminders at meal windows (infer from wake/sleep or generic lunch/dinner bands).
- Fascia/lymph: morning block; optional midday; evening 4–5x/week not nightly.
- Bone nutrition reminders: with breakfast/lunch/dinner as appropriate.
- Neck training: 2–3x/week for most; daily chin tucks as short reminders; place after workout days if workout_frequency is high; reduce if tmj_history is yes.
- Masseter/mastic: 0–1 main session per day max; shorter duration if mastic_gum_regular is no or tmj_history is yes; never stack multiple hard jaw sessions same day.
- No sunscreen/outside-today-only tasks. No skin or hair protocols.

## USER BONEMAX CONTEXT (must personalize task text and intensity)
Use the profile line that lists: workout frequency, TMJ history, mastic gum experience, heavy screen time.

## OUTPUT
Return JSON schedule only; motivational lines short and on-brand (casual, direct).
""",
        "modules": BONEMAX_MODULES,
    },
}


def get_maxx_guideline(maxx_id: str) -> Optional[dict]:
    return MAXX_GUIDELINES.get(maxx_id)


def resolve_skin_concern(skin_type: Optional[str], explicit_concern: Optional[str] = None) -> str:
    if explicit_concern and explicit_concern in SKINMAX_PROTOCOLS:
        return explicit_concern
    return SKIN_TYPE_TO_CONCERN.get(skin_type or "normal", "aging")


def build_skinmax_prompt_section(
    concern: str,
    *,
    onboarding: Optional[dict[str, Any]] = None,
    wake_time: str = "",
    sleep_time: str = "",
    outside_today: bool = False,
    for_coaching: bool = False,
) -> str:
    """
    Build SkinMax text for Gemini schedule generation or coaching context.
    When for_coaching=True, use a shorter notification-engine excerpt to save tokens.
    """
    from services.skinmax_notification_engine import (
        SKINMAX_COACHING_REFERENCE,
        SKINMAX_JSON_DIRECTIVES,
        SKINMAX_NOTIFICATION_ENGINE_REFERENCE,
        format_computed_anchor_times,
        summarize_skinmax_onboarding,
    )

    coaching_ref = resolve_prompt(PromptKey.SKINMAX_COACHING_REFERENCE, SKINMAX_COACHING_REFERENCE)
    full_ref = resolve_prompt(
        PromptKey.SKINMAX_NOTIFICATION_ENGINE_REFERENCE, SKINMAX_NOTIFICATION_ENGINE_REFERENCE
    )
    json_dirs = resolve_prompt(PromptKey.SKINMAX_JSON_DIRECTIVES, SKINMAX_JSON_DIRECTIVES)

    protocol = SKINMAX_PROTOCOLS.get(concern) or SKINMAX_PROTOCOLS["aging"]
    onboarding = onboarding or {}

    base = f"""## SKINCARE PROTOCOL — {protocol['label']}
AM Routine: {protocol['am']}
PM Routine: {protocol['pm']}
Weekly: {protocol['weekly']}
Sunscreen: {protocol['sunscreen']}
"""
    profile = summarize_skinmax_onboarding(onboarding, wake_time, sleep_time, outside_today)
    anchors = ""
    if wake_time and sleep_time:
        anchors = format_computed_anchor_times(wake_time, sleep_time)

    engine_body = coaching_ref if for_coaching else full_ref

    if for_coaching:
        return f"{base}\n{profile}\n{engine_body}\n"

    return f"""{base}
{profile}

{anchors}

## SKINMAX NOTIFICATION ENGINE — FULL REFERENCE (follow exactly)
{engine_body}

{json_dirs}
"""


def build_bonemax_prompt_section(
    guideline: dict,
    *,
    onboarding: Optional[dict[str, Any]] = None,
    wake_time: str = "",
    sleep_time: str = "",
    other_active_maxx_ids: Optional[list[str]] = None,
    for_coaching: bool = False,
) -> str:
    """
    BoneMax schedule or coaching context: protocol stub + full notification engine reference.
    """
    from services.bonemax_notification_engine import (
        BONEMAX_COACHING_REFERENCE,
        BONEMAX_JSON_DIRECTIVES,
        BONEMAX_NOTIFICATION_ENGINE_REFERENCE,
        format_bonemax_anchor_times,
        summarize_bonemax_onboarding,
    )

    coaching_ref = resolve_prompt(PromptKey.BONEMAX_COACHING_REFERENCE, BONEMAX_COACHING_REFERENCE)
    full_ref = resolve_prompt(
        PromptKey.BONEMAX_NOTIFICATION_ENGINE_REFERENCE, BONEMAX_NOTIFICATION_ENGINE_REFERENCE
    )
    json_dirs = resolve_prompt(PromptKey.BONEMAX_JSON_DIRECTIVES, BONEMAX_JSON_DIRECTIVES)

    protos = guideline.get("protocols") or {}
    template = guideline.get("protocol_prompt_template") or ""
    protocol = protos.get("bonemax_stack") or {}
    base = ""
    if template and isinstance(protocol, dict):
        try:
            base = template.format(**protocol).strip() + "\n\n"
        except KeyError:
            base = f"## BONEMAX — {protocol.get('label', 'Bonemax')}\n{protocol.get('task_families', '')}\n\n"

    profile = summarize_bonemax_onboarding(onboarding or {}, wake_time, sleep_time)
    anchors = format_bonemax_anchor_times(wake_time, sleep_time) if wake_time and sleep_time else ""

    oids = [x for x in (other_active_maxx_ids or []) if x]
    combo = ""
    if "skinmax" in oids:
        combo = (
            "\n## ACTIVE MODULE: SKINMAX\n"
            "Merge overlapping windows per engine: **one** morning notification combining mewing morning reset + SkinMax AM when timing aligns; "
            "**one** evening block combining mewing night check (bed−30) + SkinMax PM when appropriate. "
            "Hard cap **10** total notifications/day — drop lowest-priority items first.\n"
        )
    if "fitmax" in oids:
        combo += (
            "\n## ACTIVE MODULE: FITMAX\n"
            "BoneMax owns **neck training** — FitMax programs must **not** prescribe separate neck volume. "
            "FitMax midday **posture** tips should be disabled or swapped for training/nutrition (no duplicate posture coaching). Cap **10**/day.\n"
        )

    engine_body = coaching_ref if for_coaching else full_ref

    if for_coaching:
        return f"{base}{profile}\n{anchors}\n{engine_body}{combo}\n"

    return f"""{base}{profile}

{anchors}
{combo}
## BONEMAX NOTIFICATION ENGINE — FULL REFERENCE (follow exactly)
{engine_body}

{json_dirs}
"""


def build_heightmax_prompt_section(
    *,
    tracks_protocol_text: str,
    height_track_footer: str,
    onboarding: Optional[dict[str, Any]] = None,
    wake_time: str = "",
    sleep_time: str = "",
    age_val: Any = None,
    other_active_maxx_ids: Optional[list[str]] = None,
    for_coaching: bool = False,
) -> str:
    """
    HeightMax: enabled-track protocol blocks + notification engine reference.
    `tracks_protocol_text` comes from `build_heightmax_protocol_section` in guideline_service.
    """
    from services.heightmax_notification_engine import (
        HEIGHTMAX_COACHING_REFERENCE,
        HEIGHTMAX_JSON_DIRECTIVES,
        HEIGHTMAX_NOTIFICATION_ENGINE_REFERENCE,
        format_heightmax_anchor_times,
        summarize_heightmax_onboarding,
    )

    coaching_ref = resolve_prompt(PromptKey.HEIGHTMAX_COACHING_REFERENCE, HEIGHTMAX_COACHING_REFERENCE)
    full_ref = resolve_prompt(
        PromptKey.HEIGHTMAX_NOTIFICATION_ENGINE_REFERENCE, HEIGHTMAX_NOTIFICATION_ENGINE_REFERENCE
    )
    json_dirs = resolve_prompt(PromptKey.HEIGHTMAX_JSON_DIRECTIVES, HEIGHTMAX_JSON_DIRECTIVES)

    ob = onboarding or {}
    age_use = age_val if age_val is not None else ob.get("age")
    profile = summarize_heightmax_onboarding(ob, wake_time, sleep_time, age_use)
    anchors = format_heightmax_anchor_times(wake_time, sleep_time) if wake_time and sleep_time else ""

    oids = [x for x in (other_active_maxx_ids or []) if x]
    combo = ""
    if "bonemax" in oids:
        combo += (
            "\n## ACTIVE MODULE: BONEMAX\n"
            "Merge overlapping **posture** notifications; merge **sleep** evening block (Height sleep GH at bed−45 with Bone mewing night at bed−30) into **one** pre-bed notification when timing allows; "
            "merge **supplement** reminders into one meal-time ping when stacks overlap. Cap **10** pings/day.\n"
        )
    if "fitmax" in oids:
        combo += (
            "\n## ACTIVE MODULE: FITMAX\n"
            "**Sprint day** can double as a workout day; dead hangs can be scheduled at the gym. "
            "After heavy **squat/deadlift** days, add or keep **evening decompression** copy (temporary spinal compression). Cap **10** pings/day.\n"
        )

    tracks = (tracks_protocol_text or "").strip()
    footer = height_track_footer or ""
    head = f"{tracks}\n{footer}\n" if tracks or footer else ""

    engine_body = HEIGHTMAX_COACHING_REFERENCE if for_coaching else HEIGHTMAX_NOTIFICATION_ENGINE_REFERENCE

    if for_coaching:
        return f"{head}{profile}\n{anchors}\n{engine_body}{combo}\n"

    return f"""{head}{profile}

{anchors}
{combo}
## HEIGHTMAX NOTIFICATION ENGINE — FULL REFERENCE (follow exactly)
{engine_body}

{HEIGHTMAX_JSON_DIRECTIVES}
"""


def build_fitmax_prompt_section(
    concern: str,
    guideline: dict[str, Any],
    *,
    onboarding: Optional[dict[str, Any]] = None,
    wake_time: str = "",
    sleep_time: str = "",
    other_active_maxx_ids: Optional[list[str]] = None,
    for_coaching: bool = False,
) -> str:
    """FitMax phase protocol + notification engine reference (schedule or coaching)."""
    from services.guideline_service import build_protocol_prompt_section
    from services.fitmax_notification_engine import (
        FITMAX_COACHING_REFERENCE,
        FITMAX_JSON_DIRECTIVES,
        FITMAX_NOTIFICATION_ENGINE_REFERENCE,
        format_fitmax_anchor_times,
        summarize_fitmax_onboarding,
    )

    coaching_ref = resolve_prompt(PromptKey.FITMAX_COACHING_REFERENCE, FITMAX_COACHING_REFERENCE)
    full_ref = resolve_prompt(
        PromptKey.FITMAX_NOTIFICATION_ENGINE_REFERENCE, FITMAX_NOTIFICATION_ENGINE_REFERENCE
    )
    json_dirs = resolve_prompt(PromptKey.FITMAX_JSON_DIRECTIVES, FITMAX_JSON_DIRECTIVES)

    tracks = build_protocol_prompt_section(guideline, concern)
    ob = onboarding or {}
    wo = str(
        ob.get("fitmax_preferred_workout_time")
        or ob.get("preferred_workout_time")
        or "18:00"
    ).strip()[:5]
    if ":" not in wo:
        wo = "18:00"
    profile = summarize_fitmax_onboarding(ob, wake_time, sleep_time, concern)
    anchors = (
        format_fitmax_anchor_times(wake_time, sleep_time, workout_time=wo)
        if wake_time and sleep_time
        else ""
    )

    oids = [x for x in (other_active_maxx_ids or []) if x]
    combo = ""
    if "bonemax" in oids:
        combo += (
            "\n## ACTIVE MODULE: BONEMAX\n"
            "Remove **neck training** from FitMax workout copy (BoneMax owns neck). "
            "Replace FitMax **midday posture** tips with **training/nutrition** tips — no duplicate posture coaching. "
            "**Face pulls** stay in FitMax. Cap **10** pings/day.\n"
        )
    if "heightmax" in oids:
        combo += (
            "\n## ACTIVE MODULE: HEIGHTMAX\n"
            "HeightMax **sprint** sessions count as cardio — do not add redundant cardio. "
            "After heavy **squat/deadlift** days, post-workout or evening copy may include **2 min dead hang** for spinal decompression. "
            "Align **protein** messaging with Height nutrition if both apply.\n"
        )
    if "skinmax" in oids:
        combo += (
            "\n## ACTIVE MODULE: SKINMAX\n"
            "Merge **morning nutrition** with **SkinMax AM** into **one** notification when windows align. "
            "Midday FitMax tip may add: leanness lowers systemic inflammation — helps skin clarity. Cap **10**/day.\n"
        )
    if "hairmax" in oids:
        combo += (
            "\n## ACTIVE MODULE: HAIRMAX\n"
            "When scheduling **creatine** reminders, add caveat: mixed evidence on DHT/hair — if hair priority > performance, skip creatine. "
            "Cap **10**/day total.\n"
        )

    engine_body = coaching_ref if for_coaching else full_ref

    if for_coaching:
        return f"{tracks}\n{profile}\n{anchors}\n{engine_body}{combo}\n"

    return f"""{tracks}
{profile}

{anchors}
{combo}
## FITMAX NOTIFICATION ENGINE — FULL REFERENCE (follow exactly)
{engine_body}

{json_dirs}
"""


def resolve_hair_concern(hair_type: Optional[str], explicit_concern: Optional[str] = None, has_thinning: bool = False) -> str:
    """Resolve hair concern based on hair type and thinning status."""
    if explicit_concern and explicit_concern in HAIRMAX_PROTOCOLS:
        return explicit_concern
    if has_thinning:
        return "minoxidil"
    return HAIR_TYPE_TO_CONCERN.get(hair_type or "normal", "wash_routine")


def _hairmax_protocol_details_block(concern: str) -> tuple[str, dict]:
    """Return (details markdown, protocol dict) for the selected hair concern."""
    protocol = HAIRMAX_PROTOCOLS.get(concern) or HAIRMAX_PROTOCOLS["wash_routine"]

    if concern == "wash_routine":
        details = f"""Shampoo: {protocol['shampoo']}
Conditioner: {protocol['conditioner']}
Straight/Wavy frequency: {protocol['frequency_straight_wavy']}
Curly frequency: {protocol['frequency_curly']}
Product users: {protocol['frequency_product_heavy']}
Over-washed signs: {protocol['over_washed_signs']}
Under-washed signs: {protocol['under_washed_signs']}
Rule: {protocol['rule']}"""
    elif concern == "minoxidil":
        details = f"""Who needs it: {protocol['who_needs_it']}
When to apply: {protocol['when_to_apply']}
Frequency: {protocol['frequency']}
How to apply: {protocol['how_to']}
Notification (core): {protocol['notification_core']}
Notification (pressure): {protocol['notification_pressure']}
Notification (identity): {protocol['notification_identity']}
If skipped: {protocol['notification_skip_escalate']}
If consistent: {protocol['notification_consistent']}
Rule: {protocol['rule']}"""
    elif concern == "dermastamp":
        details = f"""Who needs it: {protocol['who_needs_it']}
When to use: {protocol['when_to_use']}
Frequency: {protocol['frequency']}
How to do it: {protocol['how_to']}
Notification: {protocol['notification']}
Rule: {protocol['rule']}"""
    elif concern == "oils_masks":
        details = f"""When to use: {protocol['when_to_use']}
Frequency: {protocol['frequency']}
How to apply: {protocol['how_to']}
Best oils: {protocol['best_oils']}
Masks: {protocol['masks']}
Notification: {protocol['notification']}"""
    elif concern == "anti_dandruff":
        details = f"""When to use: {protocol['when_to_use']}
Shampoo: {protocol['shampoo']}
Frequency: {protocol['frequency']}
Conditioner: {protocol['conditioner']}
Rule: {protocol['rule']}"""
    else:
        details = str(protocol)

    return details, protocol


def build_hairmax_prompt_section(
    concern: str,
    *,
    onboarding: Optional[dict[str, Any]] = None,
    wake_time: str = "",
    sleep_time: str = "",
    other_active_maxx_ids: Optional[list[str]] = None,
    for_coaching: bool = False,
) -> str:
    """Hair concern protocol + HairMax notification engine reference."""
    from services.hairmax_notification_engine import (
        HAIRMAX_COACHING_REFERENCE,
        HAIRMAX_JSON_DIRECTIVES,
        HAIRMAX_NOTIFICATION_ENGINE_REFERENCE,
        format_hairmax_anchor_times,
        summarize_hairmax_onboarding,
    )

    coaching_ref = resolve_prompt(PromptKey.HAIRMAX_COACHING_REFERENCE, HAIRMAX_COACHING_REFERENCE)
    full_ref = resolve_prompt(
        PromptKey.HAIRMAX_NOTIFICATION_ENGINE_REFERENCE, HAIRMAX_NOTIFICATION_ENGINE_REFERENCE
    )
    json_dirs = resolve_prompt(PromptKey.HAIRMAX_JSON_DIRECTIVES, HAIRMAX_JSON_DIRECTIVES)

    details, protocol = _hairmax_protocol_details_block(concern)
    base = f"""## HAIR PROTOCOL — {protocol['label']}
{details}

## SCHEDULE RULES (concern-specific baseline)
- Wash frequency depends on hair type: straight/wavy 2-3x/week, curly less often with optional co-wash
- Minoxidil: **AM wake+15**, **PM bed−90** per HairMax engine (not vague "night skincare")
- Microneedling / dermastamp: 1×/week max; never same night as minoxidil (24h gap); stagger vs SkinMax face microneedling
- Oil treatments: 1-2x/week, evening before wash day as overnight treatment
- Anti-dandruff / keto: 2-3x/week when indicated — can align with ketoconazole hair protocol
- Conditioner on strands only unless designed for scalp
- All tasks MUST use exact HH:MM from wake and sleep times

## NOTIFICATION RULES FOR THINNING USERS
- Core: "Minoxidil. Thinning areas only."
- Pressure: "Miss days = lose gains."
- If skip 5+ PM in a row: offer 1×/day simplification (per engine) vs nagging
- Prioritize highest ROI; fin dose 0.5mg vs 1mg — respect user preference (0.5mg ≈ 85-90% suppression of 1mg)
"""

    profile = summarize_hairmax_onboarding(onboarding or {}, wake_time, sleep_time, concern)
    anchors = format_hairmax_anchor_times(wake_time, sleep_time) if wake_time and sleep_time else ""

    oids = [x for x in (other_active_maxx_ids or []) if x]
    combo = ""
    if "skinmax" in oids:
        combo = (
            "\n## ACTIVE MODULE: SKINMAX\n"
            "Merge **AM**: cleanser → **minoxidil on scalp** → **15 min** → skin actives → moisturizer → SPF in **one** notification when windows align. "
            "Merge **PM**: minox → **30 min dry** → PM skincare. "
            "**Do not** schedule scalp microneedling same day as **face** microneedling — stagger (e.g. scalp Sunday, face Wednesday). "
            "Ketoconazole wash can double as dandruff control. **Max 10** notifications/day total.\n"
        )

    engine_body = coaching_ref if for_coaching else full_ref

    if for_coaching:
        return f"{base}\n{profile}\n{anchors}\n{engine_body}{combo}\n"

    return f"""{base}
{profile}

{anchors}
{combo}
## HAIRMAX NOTIFICATION ENGINE — FULL REFERENCE (follow exactly)
{engine_body}

{json_dirs}
"""
