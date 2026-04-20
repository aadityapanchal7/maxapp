"""Seed rag_documents with exactly 5 organized docs per maxx (25 total).

Clears the table first, then inserts fresh rows.  Real content is included
inline for docs that already have it; placeholders are inserted for the rest
so you can fill them in via the Supabase dashboard.

Usage (from backend/ directory):
    python scripts/seed_rag_organized.py
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(_BACKEND_DIR / ".env")


# ── All 25 documents organised by maxx ──────────────────────────────────

DOCS: list[dict] = [

    # ━━ FITMAX (5) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "maxx_id": "fitmax",
        "doc_title": "Cutting",
        "content": """\
# Leaning Out (Cutting)

Getting lean is 80% calorie deficit, 20% protein intake, and progressive resistance training to keep muscle while the fat comes off.

## The Math

- Maintenance calories ≈ bodyweight in lbs × 14–16. Less if sedentary.
- Cutting deficit: 300–500 below maintenance. More than that and you lose muscle fast.
- Expect 0.5–1% bodyweight fat loss per week. Anything faster is muscle.

## Protein

- 0.8–1g per lb of bodyweight daily. Non-negotiable for muscle retention.
- Distribute across 3–5 meals, each with at least 0.3g/kg to maximize MPS.
- Whey shake post-workout is convenient, not magic.

## Training

- Keep lifting heavy — don't switch to high-rep "toning." Heavy training signals the body to hold muscle.
- 3–4 strength sessions per week, compound lifts (squat, deadlift, bench, row, OHP).
- Add 8–15k steps daily. This is the secret weapon over cardio machines — sustainable and doesn't crush recovery.

## When Progress Stalls

- Re-weigh yourself morning, same conditions, 7-day average. The scale lies daily.
- Drop calories by 100–150 after 2 weeks of no trend movement.
- Take a diet break (maintenance for 1–2 weeks) every 6–8 weeks for hormonal and psychological recovery.""",
    },
    {
        "maxx_id": "fitmax",
        "doc_title": "Training Split",
        "content": """\
# Training Split

Add your training split content here.

## Example Sections
- Push/pull/legs
- Upper/lower split
- Full body
- Frequency recommendations""",
    },
    {
        "maxx_id": "fitmax",
        "doc_title": "Leaning Out & Macros",
        "content": """\
# Leaning Out & Diet Nutrition Macros

Add your leaning out and macro content here.

## Example Sections
- Caloric deficit strategy
- Protein targets
- Carb cycling
- Fat intake guidelines""",
    },
    {
        "maxx_id": "fitmax",
        "doc_title": "Supplements",
        "content": """\
# Fitmax Supplements Guide

Add your supplement content here.

## Example Sections
- Pre-workout
- Post-workout
- Daily essentials
- Sleep & recovery""",
    },
    {
        "maxx_id": "fitmax",
        "doc_title": "Bodily Dimensions",
        "content": """\
# Bodily Dimensions — Clavicles & Ideal Frame Ratios

Add your bodily dimensions content here.

## Example Sections
- Shoulder-to-waist ratio
- Clavicle width and bone structure
- Ideal frame proportions
- Measurement guide""",
    },

    # ━━ SKINMAX (5) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "maxx_id": "skinmax",
        "doc_title": "Acne",
        "content": """\
# Acne Fundamentals

Acne is inflammation driven by four things: excess oil (sebum), clogged pores (dead skin cells), bacteria (C. acnes), and inflammation. You fix acne by attacking all four, not just one.

## Core Stack (most cases)

- **AM**: gentle cleanser, niacinamide serum, moisturizer, SPF 50
- **PM**: gentle cleanser, active (retinoid or BHA), moisturizer
- Retinoid (adapalene 0.1% OTC) 3 nights a week, working up to nightly. This is the single most effective thing you can do.
- Salicylic acid (BHA) 1–2 nights on non-retinoid nights for clogged pores and blackheads.

## What Doesn't Help

- Scrubbing. Physical exfoliation inflames active acne.
- Drying it out with toothpaste, rubbing alcohol, or lemon juice.
- Over-washing. Twice a day max.

## Diet Levers

- High-glycemic foods and skim dairy correlate with acne flares in RCTs. Cut both for 4 weeks and measure.
- Omega-3 (2g EPA+DHA daily) reduces inflammatory markers.

## When to See a Derm

If you have cystic acne (deep painful bumps) or nothing improves in 12 weeks of consistent OTC use, prescription options (tretinoin, oral antibiotics, spironolactone, isotretinoin) are step-changes better.""",
    },
    {
        "maxx_id": "skinmax",
        "doc_title": "Debloat",
        "content": """\
# Debloat Your Face

Facial bloat comes from water retention, mostly driven by sodium/potassium imbalance, poor sleep, and alcohol.

## Quick Wins (24h)

- Drink 3L of water through the day — dehydration *causes* retention, it doesn't fix it
- Cut sodium below 1500mg for a day: no canned food, no soy sauce, no salty snacks
- Eat potassium-rich foods: banana, avocado, spinach, potato, coconut water
- Cold exposure: 10 minutes ice roller or face in ice water for 30 seconds constricts vessels and flushes lymph

## Lymphatic Drainage

Gua sha or manual lymphatic drainage massage moves interstitial fluid out of the face. Work from center outward, then down the sides of the neck toward the collarbone. 5 minutes morning on clean skin.

## Sleep Position

Sleep with your head elevated one extra pillow. Side sleeping causes unilateral puffiness on the compressed side.

## What to Avoid

- Alcohol the night before (both dehydrating and inflammatory)
- Dairy if you're sensitive — often drives facial bloat within 12 hours
- Late-night salty food""",
    },
    {
        "maxx_id": "skinmax",
        "doc_title": "Routines",
        "content": """\
# Skinmax Routines

Add your skinmax routine content here.

## Example Sections
- AM routine
- PM routine
- Weekly treatments
- Concern-specific protocols""",
    },
    {
        "maxx_id": "skinmax",
        "doc_title": "Sun Protection",
        "content": """\
# Sun Protection & SPF

Add your sun protection content here.

## Example Sections
- Why SPF is non-negotiable
- Chemical vs mineral sunscreen
- Reapplication protocol
- Sun damage reversal""",
    },
    {
        "maxx_id": "skinmax",
        "doc_title": "Anti-Aging",
        "content": """\
# Anti-Aging Fundamentals

Add your anti-aging content here.

## Example Sections
- Retinoids for collagen
- Vitamin C serum
- Peptides and niacinamide
- Lifestyle factors (sleep, hydration, stress)""",
    },

    # ━━ HAIRMAX (5) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "maxx_id": "hairmax",
        "doc_title": "Minoxidil",
        "content": """\
# Minoxidil (Rogaine)

Minoxidil is a vasodilator that extends the anagen (growth) phase of hair follicles and thickens miniaturized hairs. It's the most evidence-backed topical for androgenic alopecia along with finasteride.

## Protocol

- **Strength**: 5% foam or liquid. 5% beats 2% for men; 5% also works for women despite the label.
- **Dose**: 1 mL twice daily on dry scalp. Leave on 4 hours minimum.
- **Timeline**: initial shed at weeks 2–8 (normal, existing weak hairs falling to make room for thicker regrowth). Visible improvement 3–6 months. Peak at 12 months.

## Real Talk

- You have to use it forever. Stop, and you lose the gains within 3–6 months.
- Foam has less propylene glycol so less scalp irritation.
- Oral minoxidil (prescription, 2.5–5mg) is often more effective and easier than topical for people with busy routines. Requires bloodwork.

## Stack With

- **Finasteride** 1mg oral or 0.25% topical — attacks the hormonal root cause (DHT). Combining with minoxidil is ~10x more effective than either alone.
- **Dermarolling** 1.5mm once a week before minoxidil — improves absorption and stimulates growth factors.
- **Ketoconazole shampoo** 2x/week — mild anti-androgen effect on scalp.""",
    },
    {
        "maxx_id": "hairmax",
        "doc_title": "Finasteride",
        "content": """\
# Finasteride & DHT Blockers

Add your finasteride content here.

## Example Sections
- How DHT causes hair loss
- Oral vs topical finasteride
- Dosing protocols
- Side effects and risk management""",
    },
    {
        "maxx_id": "hairmax",
        "doc_title": "Hair Care Routine",
        "content": """\
# Hair Care Routine

Add your hair care routine content here.

## Example Sections
- Shampoo and conditioner selection
- Washing frequency
- Scalp health and exfoliation
- Styling without damage""",
    },
    {
        "maxx_id": "hairmax",
        "doc_title": "Dermarolling",
        "content": """\
# Dermarolling for Hair Growth

Add your dermarolling content here.

## Example Sections
- Needle depth (0.5mm vs 1.0mm vs 1.5mm)
- Frequency and technique
- Combining with minoxidil
- Cleaning and safety""",
    },
    {
        "maxx_id": "hairmax",
        "doc_title": "Scalp Health",
        "content": """\
# Scalp Health & Maintenance

Add your scalp health content here.

## Example Sections
- Ketoconazole shampoo protocol
- Dandruff and seborrheic dermatitis
- Scalp circulation and massage
- Nutrition for hair (biotin, zinc, iron)""",
    },

    # ━━ HEIGHTMAX (5) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "maxx_id": "heightmax",
        "doc_title": "Posture",
        "content": """\
# Posture for Apparent Height

You won't grow new bone after your growth plates close (usually 18–21 for men, 16–18 for women). But poor posture can cost you 1–3 inches of *apparent* height, and fixing it is free.

## The Common Losses

- **Forward head posture** (tech neck) — head hanging 2–3 inches forward of shoulders steals visual height and compresses cervical discs.
- **Thoracic kyphosis** — hunched upper back from desk work.
- **Anterior pelvic tilt** — weak glutes and tight hip flexors tilt the pelvis forward, pushing the lower back into hyperlordosis.

## Daily Drills (10 min)

- **Chin tucks** — 3 sets of 10, pulling the head straight back (double chin motion)
- **Thoracic extensions over foam roller** — 2 minutes, slow breathing
- **Dead bugs** — 3 sets of 10 per side, for core + pelvic control
- **Glute bridges** — 3 sets of 15, squeeze hard at the top
- **Hip flexor stretch** — 60 seconds per side

## Sleep + Decompression

- Sleep 7–9 hours. Spinal discs rehydrate overnight; you're ~0.5 inch taller in the morning.
- Hanging from a pull-up bar 60 seconds daily decompresses the spine mildly. Not magic but combined with posture work it helps.

## Heavy Lifting

Counterintuitive but true: deadlifts and squats done with good form build the erectors and glutes that hold you upright all day. People who lift correctly are measurably taller by the end of the year than sedentary people — purely from better structural posture.""",
    },
    {
        "maxx_id": "heightmax",
        "doc_title": "Spinal Decompression",
        "content": """\
# Spinal Decompression

Add your spinal decompression content here.

## Example Sections
- Hanging protocols
- Inversion table usage
- Yoga poses for spine lengthening
- When to see a specialist""",
    },
    {
        "maxx_id": "heightmax",
        "doc_title": "Sleep & Growth",
        "content": """\
# Sleep & Growth Optimization

Add your sleep and growth content here.

## Example Sections
- Growth hormone and deep sleep
- Optimal sleep duration by age
- Sleep posture for spinal health
- Supplements (melatonin, magnesium)""",
    },
    {
        "maxx_id": "heightmax",
        "doc_title": "Nutrition for Height",
        "content": """\
# Nutrition for Height

Add your nutrition for height content here.

## Example Sections
- Calcium and vitamin D
- Protein for growth plates
- Micronutrients (zinc, magnesium)
- Foods to avoid""",
    },
    {
        "maxx_id": "heightmax",
        "doc_title": "Stretching",
        "content": """\
# Stretching & Flexibility

Add your stretching content here.

## Example Sections
- Morning stretch routine
- Hip flexor and hamstring work
- Thoracic mobility drills
- Consistency and tracking progress""",
    },

    # ━━ BONEMAX (5) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "maxx_id": "bonemax",
        "doc_title": "Mewing",
        "content": """\
# Mewing

Mewing is keeping your whole tongue (not just the tip) pressed against the roof of your mouth — palate — at rest, with teeth lightly touching and lips sealed. The goal is to let forward/upward tongue pressure reshape the maxilla over time for a more defined jawline and stronger midface.

## How to Do It

- Tip of tongue behind upper front teeth, not touching them
- Whole tongue suctioned flat to the roof of the mouth
- Teeth together but not clenched, lips sealed, breathe through your nose
- Swallow with your tongue pressed to the palate, not pushing off the teeth

## Timeline

Mewing works best in adolescents whose sutures are still malleable. Adults get smaller but real changes: better posture, reduced double chin from tongue tone, slightly firmer submental area over 12+ months of consistent posture.

## What It Won't Do

- Give you Brad Pitt's jawline in 3 months. Most dramatic before/after mewing videos involve angle changes, lighting, and weight loss.
- Move bone on adults the way orthognathic surgery does.
- Fix a recessed chin — that's a skeletal issue needing genioplasty or fillers.

## Works Well With

- **Chewing load**: hard gum, mastic gum, jerky. Hypertrophies masseter and temporalis.
- **Body fat reduction**: a jaw under 15% body fat looks dramatically sharper regardless of bone structure.
- **Nose breathing during sleep**: mouth breathers lose tongue posture every night. Mouth tape or nasal strips fix this.""",
    },
    {
        "maxx_id": "bonemax",
        "doc_title": "Jaw Exercises",
        "content": """\
# Jaw Exercises & Masseter Training

Add your jaw exercise content here.

## Example Sections
- Mastic gum protocol
- Jawzrsize and similar tools
- Masseter hypertrophy timeline
- Avoiding TMJ issues""",
    },
    {
        "maxx_id": "bonemax",
        "doc_title": "Bone Density & Diet",
        "content": """\
# Bone Density & Diet

Add your bone density content here.

## Example Sections
- Calcium, vitamin D, vitamin K2
- Weight-bearing exercise for bone density
- Collagen and connective tissue
- Hormonal factors""",
    },
    {
        "maxx_id": "bonemax",
        "doc_title": "Facial Structure",
        "content": """\
# Facial Structure & Forward Growth

Add your facial structure content here.

## Example Sections
- Maxilla vs mandible development
- Orthotropics principles
- Breathing and facial development
- Surgical vs non-surgical options""",
    },
    {
        "maxx_id": "bonemax",
        "doc_title": "Chewing Protocol",
        "content": """\
# Chewing Protocol

Add your chewing protocol content here.

## Example Sections
- Hard gum vs mastic gum vs falim
- Duration and frequency
- Bilateral chewing technique
- Progress tracking""",
    },
]


async def main() -> None:
    from db.sqlalchemy import AsyncSessionLocal
    from sqlalchemy import text

    assert len(DOCS) == 25, f"Expected 25 docs, got {len(DOCS)}"

    by_maxx: dict[str, int] = {}
    for d in DOCS:
        by_maxx[d["maxx_id"]] = by_maxx.get(d["maxx_id"], 0) + 1
    for mid, count in sorted(by_maxx.items()):
        assert count == 5, f"{mid} has {count} docs, expected 5"

    async with AsyncSessionLocal() as session:
        # Clear existing rows
        result = await session.execute(text("DELETE FROM rag_documents"))
        deleted = result.rowcount
        print(f"Cleared {deleted} existing row(s) from rag_documents\n")

        # Insert all 25
        for doc in DOCS:
            await session.execute(
                text(
                    "INSERT INTO rag_documents (maxx_id, doc_title, chunk_index, content) "
                    "VALUES (:maxx_id, :doc_title, 0, :content)"
                ),
                doc,
            )
            tag = "  [real]" if len(doc["content"]) > 500 else "  [stub]"
            print(f"{tag}  {doc['maxx_id']:12s}  {doc['doc_title']}")

        await session.commit()

    print(f"\nDone: inserted {len(DOCS)} docs (5 per maxx)")
    print("Edit content in Supabase dashboard -> Table Editor -> rag_documents")


if __name__ == "__main__":
    asyncio.run(main())
