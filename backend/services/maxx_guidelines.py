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
            "morning_decompression": "Schedule dead hangs and decompression work shortly after waking.",
            "sleep_wind_down": "Push wind-down reminders 3 hours before bed for caffeine cutoff and 45 minutes before bed for screen cutoff.",
            "posture_resets": "Add 1-2 posture reset reminders during the day rather than spamming notifications.",
            "sprint_spacing": "Sprint sessions should be spaced with recovery days and not scheduled daily.",
            "presentation_focus": "Favor posture, recovery, decompression, and visual presentation over fake bone-growth claims.",
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
    "hairmax": {
        "label": "HairMax",
        "description": "AI-personalised hair care schedule based on your hair type and concerns (thinning, wash routine, scalp health).",
        "schedule_rules": {
            "wash_timing": "Based on hair type: straight/wavy 2-3x/week, curly less often with co-wash days",
            "minoxidil_timing": "PM skincare time, before skincare routine. Daily non-negotiable.",
            "dermastamp_timing": "Same day each week (habit lock), evening before bed. Never same night as minoxidil.",
            "oil_timing": "1-2x/week, evening before wash day (overnight treatment)",
            "learn_patterns": True,
            "thinning_escalation": "If user skips minoxidil, escalate notification tone",
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
            "mewing_cues": "All-day soft oral posture reminders; morning/midday/night resets; optional hard mewing caps.",
            "chewing_form": "Meal-time chewing posture cues; symmetrical, premolar-biased, closed mouth.",
            "fascia_lymph": "Morning drainage; midday if puffy; evening sessions 4–5x/week.",
            "bone_nutrition": "Stack with meals daily (concept: D3, K2, magnesium, zinc, boron).",
            "neck_training": "After workouts / posture days; scale down if TMJ issues.",
            "masseter_gum": "One main session/day max, volume caps; rest if jaw pain or clicking.",
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

- All tasks MUST be anchored to the user's wake and sleep times
- Do NOT output vague times like "morning" or "night"
- Convert everything into exact clock times

- Learn the user's patterns and adjust timing if they complete tasks early/late
- If the user repeatedly skips steps, reduce friction and simplify the routine
"""


def resolve_hair_concern(hair_type: Optional[str], explicit_concern: Optional[str] = None, has_thinning: bool = False) -> str:
    """Resolve hair concern based on hair type and thinning status."""
    if explicit_concern and explicit_concern in HAIRMAX_PROTOCOLS:
        return explicit_concern
    if has_thinning:
        return "minoxidil"
    return HAIR_TYPE_TO_CONCERN.get(hair_type or "normal", "wash_routine")


def build_hairmax_prompt_section(concern: str) -> str:
    """Build protocol text for the Gemini prompt."""
    protocol = HAIRMAX_PROTOCOLS.get(concern)
    if not protocol:
        protocol = HAIRMAX_PROTOCOLS["wash_routine"]

    # Build protocol details based on the concern type
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

    return f"""## HAIR PROTOCOL — {protocol['label']}
{details}

## SCHEDULE RULES
- Wash frequency depends on hair type: straight/wavy 2-3x/week, curly less often with optional co-wash
- Minoxidil is PM skincare time, daily, non-negotiable for thinning users
- Dermastamp is 1x/week max, same day each week, never same night as minoxidil (wait 24h)
- Oil treatments are 1-2x/week, evening before wash day as overnight treatment
- Anti-dandruff shampoo only when clear fungal/seborrheic signs
- Conditioner goes on strands only, never on scalp
- Never push "no shampoo" as a lifestyle recommendation
- Adjust schedule timing based on user behavior (early/late completion)
- Reduce volume if user skips consistently
- All tasks MUST be anchored to the user's wake and sleep times
- Do NOT output vague times like "morning" or "night"
- Convert everything into exact clock times


## NOTIFICATION RULES FOR THINNING USERS
- Core: "Minoxidil. Thinning areas only."
- Pressure: "Miss days = lose gains."
- Identity: "You either maintain your hairline or watch it go."
- If skip: escalate tone
- If consistent: 1 clean reminder/day
- Prioritize highest ROI actions
"""
