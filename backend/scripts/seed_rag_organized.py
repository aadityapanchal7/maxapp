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


def _load_env() -> None:
    """Defer dotenv import so this module can be imported by tooling that
    only needs the DOCS constant (e.g. the offline retrieval benchmark)."""
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
# Training Split — pick one and stop program-hopping

For natural lifters, frequency-per-muscle (1.5–3x/week) and total weekly hard sets per muscle (10–20) drive growth. The split is a vehicle, not the cause. Pick what fits your schedule and stick to it for at least 8 weeks.

## Push / Pull / Legs (PPL) — 6 days

Best for intermediates with time. Each muscle hits 2x/week.

- Push: bench, OHP, incline DB press, lateral raise, triceps
- Pull: deadlift or row, pull-ups, barbell row, rear delt, biceps
- Legs: squat, RDL, leg press, hamstring curl, calves

Volume target: 12–16 hard sets per muscle per week. Reps mostly 5–12.

## Upper / Lower — 4 days

Best for working adults. Each muscle hits 2x/week, simpler to recover from.

- Upper A (heavy): bench 4x5, row 4x6, OHP 3x8, pull-up 3x8, curl 3x10
- Lower A (heavy): squat 4x5, RDL 3x6, leg press 3x10, calf raise 4x12
- Upper B (volume): incline DB 4x10, cable row 4x12, lateral raise 5x15, face pull 4x15, triceps 3x12
- Lower B (volume): front squat 3x8, hip thrust 4x8, leg curl 4x12, walking lunge 3x10

## Full Body — 3 days

Best for absolute beginners (first 6 months) or busy weeks. Each muscle 3x/week with low per-session volume.

- A: squat 3x5, bench 3x5, row 3x8, plank
- B: deadlift 3x3, OHP 3x5, pull-up 3xAMRAP, hanging knee raise
- C: front squat 3x6, incline DB press 3x8, lat pulldown 3x10

## What actually matters (and what doesn't)

- Progressive overload (more weight, more reps, or better technique each week) > fancy programming.
- Frequency 2x/week beats 1x/week for hypertrophy. Frequency 3x/week barely beats 2x — diminishing returns.
- "Bro splits" (chest day, back day) work — but only if total weekly volume is 12+ hard sets per muscle. Most people undershoot and stay small.
- Switching programs every 4 weeks is the fastest way to look the same in a year.""",
    },
    {
        "maxx_id": "fitmax",
        "doc_title": "Leaning Out & Macros",
        "content": """\
# Leaning Out — macros that actually move bodyfat

The framework is simple, the execution is what most people fail at. Track honestly for 7 days before declaring "the deficit isn't working."

## Caloric Deficit Strategy

- Maintenance ≈ bodyweight (lbs) × 14–16. Sedentary desk worker = 14, daily lifter = 15, lifter + 10k steps = 16.
- Cutting deficit: 300–500 below maintenance. Below that, you stall energy + lose muscle.
- Aggressive cut (rare, only for short windows): 500–750 deficit, accept some muscle loss.
- Re-weigh weekly average (morning, post-pee, no clothes). Daily scale fluctuations are 90% water.

## Protein Targets — non-negotiable on a cut

- 0.8–1.0 g per lb bodyweight, every day. This is the single biggest lever for keeping muscle.
- Spread across 3–5 meals, each with ≥0.3 g/kg per meal to maximize muscle protein synthesis.
- Whey post-workout is convenient, not magical. Real food works the same.

## Carbs and Fats

- Carbs: fuel training. 1.5–3 g/lb bodyweight on training days, lower on rest days if you want — but don't go zero-carb if you're lifting.
- Fats: 0.3–0.4 g/lb bodyweight floor. Below this, hormones (testosterone) tank.
- Fill the remaining calories with whichever you prefer. The carb-vs-fat religious war doesn't move bodyfat — total calories do.

## Carb Cycling

Optional. Useful for advanced cutters or competitors. Higher carbs (3 g/lb) on training days, lower (1 g/lb) on rest days, same weekly average. No magic — just helps recovery and hunger management.

## When Progress Stalls

- 2 weeks of no scale movement on a 7-day average → drop calories by 100–150 OR add 1k–2k steps daily.
- 6–8 weeks into a cut → take a 1-week diet break at maintenance. Hormonal + psychological reset, not a "cheat week."
- If you're losing more than 1.5% bodyweight per week, you're losing muscle. Slow down.

## What to Stop Believing

- "Eating after 8pm makes you fat." No, total calories make you fat.
- "Carbs at night ruin sleep." No, they often improve it.
- "Cardio kills gains." Only if cardio crushes your recovery. 2–4 30-min sessions/week is fine.
- "I have a slow metabolism." Almost always wrong. You're underreporting intake or overreporting activity.""",
    },
    {
        "maxx_id": "fitmax",
        "doc_title": "Supplements",
        "content": """\
# Supplements — what's worth buying and what's a scam

Supplements optimize at the margins. They cannot fix bad training, bad sleep, or a bad diet. If you're not nailing those first, you're wasting money.

## Tier 1 — buy these, real evidence

- **Creatine monohydrate**: 5g daily, any time, with or without food. ~5–10% strength increase, more reps in reserve, better cell hydration. Cheapest, best-studied supplement on earth. Skip "creatine HCL" — pure marketing.
- **Whey protein** (or casein): convenient way to hit protein targets. Not magic. Plant-based blend works fine if you don't tolerate dairy.
- **Vitamin D3** (2000–5000 IU daily): if you don't get 20+ min sun. Low D3 tanks testosterone and recovery.
- **Caffeine** (100–200 mg pre-training): improves performance ~3–5%. Tolerance builds — cycle off every 6 weeks for a week.

## Tier 2 — situational, modest gains

- **Beta-alanine** (3–5g daily): meaningful for high-rep work (12+ reps to failure). Causes harmless tingling. Skip if you only train 3–8 reps.
- **Citrulline malate** (6–8g pre-workout): pump + endurance. Niche but legit.
- **Fish oil** (2–3g EPA+DHA daily): if your diet has low omega-3. Anti-inflammatory.
- **Magnesium glycinate** (300–400mg before bed): improves sleep depth. Most lifters are mildly deficient.

## Tier 3 — skip

- Pre-workout blends with proprietary formulas — overpriced caffeine + beta-alanine.
- BCAAs — useless if your protein intake is adequate.
- Testosterone boosters (Tribulus, fenugreek, ZMA) — placebo at best.
- Fat burners — caffeine in a fancy bottle.
- Glutamine, HMB, "anabolic" protein blends — marketing.

## Stack Examples by Goal

- Cutting: creatine + whey + caffeine + magnesium.
- Bulking: creatine + whey + casein at night + vitamin D.
- Maintenance: creatine + multivitamin if your diet is narrow + magnesium for sleep.

## Timing

Most "timing" claims are exaggerated. Total daily intake matters far more than pre/post-workout windows. Take creatine whenever you'll remember it. Take protein when convenient. Don't engineer your life around a 30-minute "anabolic window" — it's 4–6 hours wide.""",
    },
    {
        "maxx_id": "fitmax",
        "doc_title": "Bodily Dimensions",
        "content": """\
# Body Proportions — the frame ratios that actually mog

Aesthetic mass is built around skeletal frame. You can't widen clavicles or narrow hips, but you CAN exploit the frame you have by lean mass placement and bodyfat.

## The Money Ratios

- **Shoulder-to-waist (V-taper)**: target 1.4–1.6:1 (golden ratio territory). Measure shoulders at deltoid widest point, waist at navel. Most untrained men are 1.2:1.
- **Waist-to-hip**: 0.85–0.9. Lower = more hourglass-feminine. Higher = blockier.
- **Bicep-to-flexed-forearm**: 1.0:1 looks balanced. Forearm <80% of bicep looks chicken-armed.
- **Calf-to-flexed-bicep**: 1.0:1. Big arms with chicken legs is the universal cope physique.

## What You Can Actually Change

- **Width illusion**: lateral delts (side raises, behind-the-neck high-pull, OHP) widen the shoulder line more than chest mass does. 3 lateral raise sessions/week minimum.
- **Waist tightness**: stop training obliques heavy. Don't do weighted side bends. Vacuum work + low bodyfat = small waist. Direct ab training is fine; obliques get hit indirectly anyway.
- **Lower-body asymmetry**: if your quads dominate your hams, your legs look "blocky from the side." Add 2x/week dedicated hamstring (RDL + leg curl) if you squat-bias.

## Measurement Protocol

- Same time of day (morning, fasted), same posture (relaxed, not flexed unless noted).
- Tape parallel to floor, snug but not compressing.
- Track every 4 weeks. Avoid daily measuring — you'll go crazy at noise.

## Frame Reality Check

- Clavicle width is set by 18–21 (growth plate fusion). Heavy overhead pressing in adolescence may add a small amount via bone remodeling — adults: nothing.
- Hip width is set the same way. Wider hips = blockier waist illusion regardless of muscle.
- If your wrist circumference is <6.5", you have a small frame; build for tightness + symmetry, not mass illusion. >7.5" wrists carry mass well.

## What Doesn't Matter

- "Ideal arm size" (16", 18", whatever) — it's relative to your shoulder width. A 17" arm on a narrow frame looks bigger than a 17" arm on a wide one.
- Specific lift numbers as aesthetic markers — a 405 squat doesn't make your legs look better than a 315 if your bodyfat is 18%.""",
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
# Skinmax Routines — AM, PM, weekly

The whole point of a routine is to compress decisions: same products, same order, same time. Improvisation is what kills consistency.

## AM Routine (5 minutes)

1. **Cleanser** — gentle, non-foaming if dry skin, gel/foaming if oily. Splash-rinse only if you didn't sweat overnight.
2. **Active serum** — niacinamide 5–10% (oil control + barrier) OR vitamin C 10–15% L-ascorbic acid (brightening, antioxidant). Pick one. Don't layer.
3. **Moisturizer** — non-comedogenic, ceramide-based. Cetaphil, CeraVe AM, La Roche-Posay Toleriane.
4. **Sunscreen SPF 30+** — non-negotiable. Mineral (zinc/titanium) for sensitive, chemical for cosmetic finish. Apply 2 finger-lengths to face + neck.

## PM Routine (5–10 minutes)

1. **First cleanse** (oil-based balm or micellar water) — only if you wore sunscreen or makeup.
2. **Second cleanse** (water-based) — sweep through, 30 seconds.
3. **Active** — pick one per night, do not layer:
   - Retinoid (adapalene 0.1% OTC, or tretinoin Rx) — 3 nights/week, work up to nightly. Pea-size for whole face.
   - BHA (salicylic 1–2%) — 1–2 nights on non-retinoid nights. For clogged pores, blackheads.
   - AHA (glycolic or lactic 5–10%) — 1 night/week max. For texture, dullness.
4. **Moisturizer** — same as AM, or richer (ceramide cream). Use the moisturizer "sandwich" if you're new to retinoids: moisturizer → wait 10 min → retinoid → moisturizer again.

## Weekly Treatments

- **Clay mask** (kaolin or bentonite): 1x/week if oily. Skip if dry/sensitive.
- **Hydrating mask** (hyaluronic + B5): 1x/week, restore barrier after actives.
- **Dermarolling** (0.25mm only at home): 1x/week, on a clean-bare-skin night. Anything deeper than 0.5mm = derm office only.

## Concern-Specific Add-Ons

- **Acne**: stack adapalene PM + benzoyl peroxide 2.5% spot-treat AM (separate, not layered).
- **Hyperpigmentation**: vitamin C AM + retinoid PM + religious SPF. Tretinoin for stubborn cases.
- **Rosacea / redness**: cut all actives for 4 weeks, only barrier repair (panthenol, centella). Add azelaic 10% slowly.
- **Aging concerns**: retinoid is the single biggest mover. Vitamin C and SPF are the supporting cast.

## Order Rules

- Thinnest to thickest.
- Water-based serums before oil-based.
- Do NOT layer actives in the same routine (no retinoid + BHA same night, no vitamin C + retinoid same morning).
- Wait 5–10 min between active and moisturizer if your skin tolerates it; otherwise apply moisturizer first as a buffer.""",
    },
    {
        "maxx_id": "skinmax",
        "doc_title": "Sun Protection",
        "content": """\
# Sun Protection — the single biggest anti-aging move you'll make

UV damage causes ~80% of visible skin aging. No retinoid, peel, or laser undoes what daily SPF would have prevented. If you do nothing else for your skin, do this.

## Why SPF Is Non-Negotiable

- UVA (long wavelength) penetrates deep, causes wrinkles + collagen breakdown + pigmentation. Comes through windows, clouds, and on cold days. Year-round.
- UVB (short wavelength) burns the surface. Triggers acute redness + DNA damage. Strongest 10am–4pm in summer.
- "I'm indoors all day" = you still need it. Window glass blocks UVB, not UVA. Driving = significant UVA exposure.

## Chemical vs Mineral

- **Chemical** (avobenzone, octinoxate, oxybenzone, octocrylene): cosmetically elegant, no white cast, works after ~15 min absorption. Best for daily wear under makeup.
- **Mineral** (zinc oxide, titanium dioxide): physical block, works on application, less irritating. Better for sensitive/rosacea/post-procedure. Modern formulas (e.g., Biore UV Aqua Rich, La Roche-Posay Anthelios Mineral) have minimal white cast.
- Hybrid (chemical + mineral) = practical for most people.

## Application Protocol

- **Amount**: 2 finger-lengths for face + neck. Most people apply ~25–50% of what's needed and effectively get SPF 7–15 from their "SPF 30."
- **Order**: very last step of AM skincare, BEFORE makeup.
- **Reapply every 2 hours** if outdoors. Indoors, once is enough unless you wash your face.
- **Reapplication tools**: SPF stick or powder (e.g., Supergoop! [Re]setting Powder) over makeup is fine — better than nothing.

## SPF Number — what it actually means

- SPF 30 = blocks 97% of UVB. SPF 50 = 98%. SPF 100 = 99%. Diminishing returns.
- The bigger gap is in PA rating (UVA). Look for **PA++++** or **broad spectrum**. SPF number alone tells you nothing about UVA protection.
- Best daily SPFs (US-friendly): EltaMD UV Clear, La Roche-Posay Anthelios, Supergoop! Unseen.

## Sun Damage Reversal

- Daily SPF + retinoid (adapalene or tretinoin) for 6+ months reverses some pigment + texture.
- Vitamin C 15% AM antioxidant boosts SPF performance and disrupts UV-induced free radicals.
- For deeper damage: in-office laser (Fraxel, BBL), 3–5 sessions, $$$.
- Tan = damage. There is no "healthy tan." Self-tanner if you want the look.

## What Won't Save You

- Diet "internal sunscreen" (lycopene, antioxidants) — 4% added protection at best. Not a substitute for topical SPF.
- A baseball cap blocks ~50% of UV reaching the face. Wide-brim hat = ~80%. Still need sunscreen on the chin/neck.
- "Higher SPF means I don't need to reapply" — wrong. Reapplication beats SPF number every time.""",
    },
    {
        "maxx_id": "skinmax",
        "doc_title": "Anti-Aging",
        "content": """\
# Anti-Aging — what actually works (in order of impact)

Anti-aging is a physics problem: UV damage and collagen loss accumulate. Marketing won't reverse them. These are the moves that actually slow the clock, ranked by effect size.

## Tier 1 — Mandatory

1. **Daily SPF 30+ broad-spectrum**. Single biggest move. Without this, every other anti-aging product is rearranging deck chairs.
2. **Retinoid nightly** (or near-nightly). Adapalene 0.1% OTC is the entry point. Tretinoin 0.025–0.1% Rx is the gold standard for collagen induction. 3–6 months for visible texture/wrinkle improvement, 12+ for deeper changes.
3. **7–9h sleep + low-stress lifestyle**. Cortisol breaks down collagen. Sleep deprivation shows up on the face within a week.

## Tier 2 — Significant Gains

- **Vitamin C serum AM** (15–20% L-ascorbic acid, OR ethyl ascorbic acid for sensitive). Antioxidant that limits UV-induced oxidative damage and brightens. Pair with SPF.
- **Niacinamide 5–10%**. Reduces redness, balances oil, supports barrier. Stacks with everything.
- **Peptides** (palmitoyl pentapeptide, copper peptides). Modest collagen-signaling. Worth it if your routine is already nailed.
- **Bakuchiol** as retinoid alternative for pregnancy/sensitive skin. ~70% of retinol's effect, no irritation.

## Tier 3 — Aesthetic Touch-Ups

- **Glycolic acid 5–10%** weekly. Smooths surface, fades pigment. Don't combine with retinoid the same night.
- **Hyaluronic acid serums**: hydration only, no anti-aging effect. Worth using for plumpness, not wrinkle prevention.
- **In-office** (when budget allows, every 2–5 years): one Fraxel/BBL session beats months of topicals for texture/pigment.

## What's a Scam

- "Stem cell" creams — molecules too large to penetrate; they're decoration.
- Collagen drinks/peptides — orally consumed collagen breaks into amino acids and never reaches the skin as collagen.
- Eye creams that aren't just moisturizer with a markup. Use the same retinoid you use elsewhere on the orbital area (avoid lash line).
- "Anti-blue-light" claims — no good evidence screen light meaningfully ages skin.

## Lifestyle That Actually Moves the Needle

- Don't smoke. Smoker's face is real — broken capillaries + accelerated wrinkles.
- Limit alcohol — dehydrates and inflames.
- 2L+ water/day is hygiene, not a magic bullet.
- Avoid yo-yo dieting — repeated big bodyfat swings stretch + sag skin permanently.
- Sleep on your back if possible — chronic side-sleeping causes sleep wrinkles by your 40s.

## Realistic Timelines

- Topicals (retinoid, vit C): 12 weeks for noticeable, 12 months for "wow."
- In-office laser: 4–6 weeks per session, 3–5 sessions for full result.
- Lifestyle (sleep, no smoking): months to show, but compounds permanently.""",
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
# Finasteride — the only proven DHT blocker for AGA

Androgenic alopecia is driven by DHT (dihydrotestosterone) miniaturizing follicles in genetically susceptible scalp areas. Finasteride blocks the conversion of testosterone to DHT and is the highest-impact intervention for stopping male pattern hair loss.

## How DHT Causes Hair Loss

- Testosterone converts to DHT via the 5-alpha-reductase enzyme.
- DHT binds to androgen receptors in scalp follicles (especially crown, vertex, hairline) and shrinks them over successive growth cycles.
- Result: thinner hair → vellus (peach fuzz) → no hair. Process is gradual, progressive, and irreversible without intervention.

## Oral Finasteride

- **Dose**: 1mg daily (Propecia / Proscar 5mg cut into quarters). FDA-approved for AGA.
- **Effect**: blocks ~70% of scalp DHT. Stops loss in ~85% of users; regrowth in ~30–50%.
- **Timeline**: stops shedding by month 3–6. Visible regrowth (where possible) by month 6–12. Full effect by 18–24 months.
- **Discontinuation**: stop, and you lose all gains within 6–12 months. This is forever, or it's nothing.

## Topical Finasteride

- **Dose**: 0.25% solution applied 1mL daily to scalp.
- **Effect**: similar regional DHT reduction with significantly less systemic absorption.
- **Use case**: people who can't tolerate oral, or want to minimize systemic side effect risk.
- **Drawback**: requires compounding pharmacy. Slightly less proven for diffuse loss.

## Dutasteride — the stronger option

- Blocks both 5-AR type 1 + type 2 (finasteride only blocks type 2).
- Reduces scalp DHT by ~90% vs finasteride's 70%.
- **Dose**: 0.5mg daily, OR 0.5mg 2–3x/week.
- Off-label for hair loss in the US (approved in some countries). Better for advanced/aggressive loss when finasteride isn't enough.

## Side Effects — be honest about the risk

- Sexual side effects (reduced libido, ED, ejaculation issues): occur in ~2–4% of users in trials. Most resolve on discontinuation.
- Post-finasteride syndrome (PFS): rare but real for a subset. Persistent symptoms after stopping. Genetic susceptibility likely.
- Mood changes: less common, watch for it.
- Bloodwork baseline before starting (PSA, testosterone, liver) and every 6–12 months on dut.
- If you experience side effects, lower the dose (e.g., 0.5mg every other day) before quitting outright.

## Stack For Maximum Effect

- Finasteride (or dutasteride) — root cause attack
- Minoxidil 5% topical 2x/day — vasodilator + growth signal
- Dermarolling 1.5mm 1x/week before minoxidil — improves absorption + stimulates growth factors
- Ketoconazole shampoo 2x/week — mild anti-androgen at scalp level

This 4-stack is the evidence-based ceiling for natural intervention.""",
    },
    {
        "maxx_id": "hairmax",
        "doc_title": "Hair Care Routine",
        "content": """\
# Hair Care Routine — what to do daily, weekly, never

Hair health = scalp health. The hair shaft itself is dead protein; you can't "repair" it, only prevent damage.

## Wash Frequency

- **Oily scalp**: every 1–2 days. Letting oil sit clogs follicles + breeds malassezia (the dandruff yeast).
- **Normal**: every 2–3 days.
- **Dry/curly**: 1–2x/week. Co-wash (conditioner only) on intermediate days.

Skip-day "training your scalp to produce less oil" is mostly myth — but going too short between washes does dry out the lengths.

## Shampoo Selection

- For most: gentle sulfate-free daily shampoo (SLES-free or low-foam). Sulfates strip natural oils too aggressively for daily use.
- Anti-DHT shampoos (saw palmetto, caffeine): mild adjuncts only. They don't replace finasteride or minoxidil.
- **Ketoconazole 2%** (Nizoral) 2x/week: clinically validated for AGA — mild anti-androgen at scalp level + treats malassezia. Lather, sit 3–5 min, rinse.
- **Tar-based** for stubborn dandruff/seborrheic dermatitis.

## Conditioner

- Only on lengths and ends — never the scalp (causes buildup + clogged follicles).
- Leave-in for dry/coarse hair, rinse-out for fine.
- Silicones: cosmetic only; can build up. Periodic clarifying wash (sulfate shampoo 1x/month) clears them out.

## Scalp Health & Exfoliation

- 1–2x/week scalp exfoliant (BHA-based, like The Ordinary Glycolic 7%) clears dead cells + sebum.
- Scalp massage 5 min daily: increases blood flow modestly. Cumulative effect over 6+ months. Free.
- Don't pick or scratch — micro-injuries scar follicles permanently.

## Styling Without Damage

- Heat styling: always heat protectant first; keep blow dryer 6+ inches away on medium heat.
- Tight hairstyles (man bun, slicked back): traction alopecia from chronic pulling. Vary your style.
- Wet hair is weakest — don't brush vigorously. Use a wide-tooth comb.
- Sun: UV damages hair shaft + scalp. Hat or hair-specific SPF spray when outdoors all day.

## Diet for Hair

- Iron + ferritin: hair-loss patients often have ferritin <70. Get bloodwork.
- Zinc 15–30mg daily if low.
- Protein 0.6+ g/lb bodyweight: hair is keratin (protein) — chronic underfeeding shows up as shedding.
- Biotin: only useful if you're actually deficient (rare). Mostly placebo + hype.""",
    },
    {
        "maxx_id": "hairmax",
        "doc_title": "Dermarolling",
        "content": """\
# Dermarolling for Hair Growth — protocol, depth, safety

Microneedling triggers a wound-healing response in the scalp: growth factors (VEGF, PDGF) get released, follicles get a regeneration signal, and topical absorption improves. Combined with minoxidil, it boosts regrowth meaningfully.

## Needle Depth — get this right or stop

- **0.25mm**: cosmetic only. Too shallow for follicle stimulation. Skip.
- **0.5mm**: light absorption boost. OK for sensitive scalps + first month of use.
- **1.0mm**: standard hair-growth depth. Good middle ground.
- **1.5mm**: most studies showing AGA regrowth used 1.5mm. This is the target depth for serious users.
- **2.0mm+**: derm office only. Risks scarring + permanent follicle damage at home.

## Frequency

- **1x/week** is the standard protocol. Studies showing ~24% improvement in count used weekly 1.5mm sessions.
- More than 1x/week → no benefit, more inflammation, recovery never completes.
- Skip a week if scalp is irritated or you've had recent shedding.

## Technique

1. Wash scalp, towel dry, NO product on first.
2. Roll each direction 8–10 times: vertically, horizontally, both diagonals. Light pressure — let the needles do the work.
3. Cover thinning + transition zones (hairline, vertex, crown).
4. Wait at least 24h before applying minoxidil. Apply to scalp ONLY in the next dose to avoid systemic absorption spike.
5. Expect mild redness for 12–24h. Pinpoint bleeding at 1.5mm is normal — heavy bleeding = too aggressive.

## Combining With Minoxidil

- Wait 24h before reapplying minoxidil after a roll session.
- Microneedling spikes minoxidil absorption — doing both same-day can cause systemic side effects (palpitations, swelling).
- Some advanced protocols apply minoxidil 24h pre-roll + skip the day-of post-roll. This is fine.

## Cleaning & Safety

- After each use: rinse roller in warm water, soak 10 min in 70% isopropyl alcohol, air-dry.
- Replace every 8–12 weeks. Needles dull and risk scarring + infection.
- Single-use is best for shared rollers (e.g., between partners): always replace.
- Never share a roller with someone else (bloodborne pathogen risk).
- If a needle breaks or bends: throw it out immediately.

## What Won't Work

- "Hair growth shampoos" applied right after rolling — surfactants irritate fresh micro-injuries.
- Daily rolling — overstimulates the scalp into chronic inflammation.
- Rolling on completely bald (NW6-7 crown) areas — no follicles left to stimulate. Restoration there requires transplant.""",
    },
    {
        "maxx_id": "hairmax",
        "doc_title": "Scalp Health",
        "content": """\
# Scalp Health — the foundation under every other hair protocol

You can stack minoxidil + finasteride + dermarolling perfectly, but if your scalp is inflamed, oily, or fungal-overloaded, those interventions plateau early. Treat the scalp as if it were facial skin — because it is.

## Ketoconazole Shampoo Protocol

- **Nizoral 2%** (OTC strength = 1% in US; 2% Rx). 1% works fine for AGA support.
- Frequency: 2x/week.
- Method: lather onto wet scalp, work in 60 seconds, then **leave on for 3–5 minutes** before rinsing. Letting it sit is what makes it work.
- On non-Nizoral days, use a gentle daily shampoo.
- Mechanism: anti-fungal (kills malassezia, the scalp yeast that drives most "dandruff") + mild anti-androgen at the scalp level.

## Dandruff & Seborrheic Dermatitis

- Both are malassezia-driven. Treatment ladder:
  1. Ketoconazole 2x/week (above).
  2. Selenium sulfide 2.5% (Selsun Blue Rx-strength) 2x/week if Nizoral plateaus.
  3. Pyrithione zinc daily as a maintenance shampoo.
  4. Stubborn cases: topical clobetasol from derm for inflammation, plus oral antifungal for severe seborrheic.
- Diet: high sugar + alcohol feeds malassezia. Cut both for 4 weeks if dandruff resists topicals.

## Scalp Circulation & Massage

- 5 minutes daily massage with fingertips (not nails — never break skin).
- Circular motions, full coverage, gentle pressure.
- ~24-week studies show modest hair density gains from massage alone — small but free, and stacks with everything else.
- Avoid massage rollers/handheld devices that pull on hair — traction risk.

## Nutrition for Hair Health

- **Iron + ferritin**: low ferritin (<70) is a major silent driver of shedding, especially in women + vegans. Bloodwork if shedding > 3 months. Iron supplement only if deficient.
- **Zinc** 15–30mg daily — important for keratin synthesis.
- **Vitamin D3** 2000–5000 IU — D receptors in follicles; deficiency correlates with telogen effluvium.
- **B12** — mainly relevant for vegans/vegetarians or people with absorption issues.
- **Biotin**: only fixes loss IF you're deficient (rare). Otherwise a placebo. Don't waste $20/month.
- **Protein**: 0.6+ g/lb bodyweight floor. Hair is keratin — chronic underfeeding causes diffuse shedding within ~3 months.

## Things That Actively Hurt Your Scalp

- Bleach + dye every 4 weeks → scalp burns + cumulative follicle damage.
- Tight hairstyles 24/7 (slick-back, tight bun, cornrows) → traction alopecia.
- Excessive heat styling → not technically follicle damage but breaks shaft → looks thinner.
- Sleeping in oils overnight without washing → oil oxidizes + clogs follicles.
- Cold air/wind → not the cause of hair loss but dries scalp + worsens dandruff.

## Signs Something Is Wrong (See a Derm)

- Sudden patchy loss → alopecia areata (autoimmune).
- Persistent itching with no improvement on Nizoral → fungal infection or psoriasis.
- Burning + redness + sores → contact dermatitis or infection.
- Scarring (smooth bald patches with no follicles visible) → cicatricial alopecia, time-sensitive.""",
    },
    # New: explicit Norwood reference doc — users search for "nw2/nw3"
    {
        "maxx_id": "hairmax",
        "doc_title": "Norwood Scale",
        "content": """\
# Norwood Scale — staging male pattern hair loss

The Norwood scale (Hamilton-Norwood) is the standard 1–7 staging for male AGA. Knowing your stage informs treatment urgency, realistic regrowth ceiling, and whether transplant is on the table.

## Stages

- **Norwood 1 (NW1)**: no visible recession. Juvenile hairline (low + flat across forehead).
- **Norwood 2 (NW2)**: slight temple recession ("mature hairline"). Most adult men over 25. NOT actively losing — this is normal maturation, not pattern loss.
- **Norwood 2A**: triangular forelock thinning emerges between temples.
- **Norwood 3**: clear M-shape recession at temples. This IS pattern loss starting. Intervene now — fin + minox starts paying off.
- **Norwood 3 Vertex**: NW3 temples + crown thinning visible from above.
- **Norwood 4**: deeper M + visible crown bald spot. Bridge of hair still connects front to back.
- **Norwood 5**: bridge thinning, M and crown approaching merger.
- **Norwood 6**: bridge gone, only horseshoe at sides + back.
- **Norwood 7**: mature horseshoe pattern, only thin/sparse hair on sides + back.

## NW2 vs NW3 — the most common confusion

- NW2 = mature hairline, no active loss. The temples have receded ~1–1.5cm from the juvenile line. Stable.
- NW3 = the temples have receded MORE (clear deep M) AND the recession is progressing year over year. If you're tracking photos and the line keeps moving back, you're NW3, not NW2.
- The test: photo from 2 years ago, photo today, side by side. No movement = NW2. Movement = NW3+.

## Action By Stage

- **NW1–NW2**: nothing to do. Don't start finasteride for cosmetic anxiety alone.
- **NW2A / early NW3**: this is the highest-leverage intervention window. Start finasteride + minoxidil 5%. Add dermarolling. Density and slowed progression are very achievable.
- **NW3–NW4**: still good response to fin + minox + derma roller. Existing miniaturized hairs can rethicken; lost ones rarely return without transplant.
- **NW5+**: maintain remaining native hair with fin/dut + minox. Hair transplant becomes the realistic option for restoring frontal density. Plan around limited donor supply.

## Family History Tells You The Ceiling

- Look at your maternal grandfather, paternal grandfather, father, and uncles in their 50s.
- If most are NW6+, your genetic ceiling is aggressive. Start treatment at the first sign.
- If most are NW2–3 lifelong, your loss may be environmental + reversible (stress, deficiency).

## What Norwood Doesn't Tell You

- Diffuse thinning across the scalp (no temple recession) is a separate pattern. AGA can present diffuse rather than M-pattern.
- Female pattern loss uses the Ludwig scale, not Norwood.
- Crown-only loss without front recession is also AGA — same treatments apply.""",
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
# Spinal Decompression — recover the height your discs lost today

Vertebral discs compress under daily gravity load — a sedentary adult is ~1cm shorter at night than morning. Decompression restores this acutely (and may protect long-term disc health), but it does NOT add bone past growth plate fusion.

## What Decompression Actually Does

- Reduces axial load → discs rehydrate → vertebrae separate slightly.
- Daily measurable: 0.5–1.5cm restoration with morning routine.
- Long-term: better posture + fewer back issues + slows age-related disc degeneration. Not "real" extra height past 21.

## Hanging Protocol

- **Equipment**: doorframe pull-up bar, $25.
- **Frequency**: 3–5x daily, 30–60 seconds passive hang.
- **Form**: shoulders relaxed, do NOT engage lats. Let bodyweight pull spine.
- **Build-up**: start 15s if you can't hang a full minute. Grip is the limiter early.
- **Advanced**: weighted hangs (5–10lb plate) for deeper traction. Don't exceed 60 seconds.

## Inversion Tables

- More aggressive than hanging — full bodyweight pulls in opposite direction.
- 5–15 minutes daily, start at 30° angle, work up to 60° over weeks.
- Contraindicated: glaucoma, hypertension, heart disease, retinal detachment.
- Don't expect more height gain than hanging — same physics, more comfortable for some.

## Yoga / Bodyweight Decompression

- **Cat-cow**: 10 reps, mobility + spine articulation.
- **Cobra → child's pose flow**: 5–10 reps, spinal extension/flexion.
- **Standing forward fold**: 60 sec, hamstrings + lower back release.
- **Bridge pose**: 3x 30 sec, opens thoracic + posterior chain.
- These help mobility and posture but the height-restoration effect is smaller than dead hangs.

## Sleep As Decompression

- 8 hours flat (or near-flat) is the longest decompression session you do daily.
- Firm mattress > soft (sagging mattress causes lateral spine compression).
- Pillow height: head should be neutral, not pushed forward.

## When To See A Specialist

- Persistent back pain >2 weeks despite mobility work.
- Numbness or tingling in legs/arms (potential disc impingement).
- Sudden loss of height (>1 inch in a year as an adult) — could indicate vertebral compression or osteoporosis.
- Considering medical-grade traction (DRX9000, etc.) — research provider, costs $$$, evidence base mixed.

## What Doesn't Work

- "Limb lengthening" promised online without surgery — physics impossible.
- Chiropractic "adjustments" for height gain — temporary realignment at best, no bone change.
- Stretching alone (no axial decompression) — improves mobility, doesn't significantly decompress.""",
    },
    {
        "maxx_id": "heightmax",
        "doc_title": "Sleep & Growth",
        "content": """\
# Sleep & Growth — when the body actually builds height

Growth hormone (GH) pulses ~70% during deep sleep (slow-wave sleep / SWS), specifically the first 90–120 minutes after sleep onset. If your growth plates are open (typically <18M / <16F), this is when bone lengthens. Past closure, sleep still optimizes recovery + spinal disc rehydration.

## Growth Hormone & Deep Sleep

- GH released in pulses during SWS, with the largest pulse in cycle 1 (the first 90 min).
- Disrupted sleep onset = killed first pulse = reduced cumulative GH for the night.
- Late-night eating, alcohol, blue light, and stress all suppress SWS depth.
- Caffeine after 2pm reduces SWS by ~10% even if you "fall asleep fine."

## Optimal Sleep Duration

- **Adolescents (10–17)**: 9–10 hours. Skipping sleep at this age literally truncates final height.
- **Young adults (18–25)**: 8–9 hours. Final height locks in around 18–21 (M) / 16–18 (F).
- **Adults (25+)**: 7–9 hours. No more bone lengthening, but sleep drives recovery, hormonal balance, and skin/face quality.

## Sleep Posture

- **On back, neutral pillow**: best for spinal alignment. Reduces facial wrinkles + neck strain.
- **Side**: OK if pillow keeps neck neutral (cervical curve preserved). Knee pillow helps hip alignment.
- **Stomach**: worst — twists neck 90°, compresses chest, causes facial asymmetry over years.
- Avoid arm-under-pillow positions — pinches nerves.

## Pre-Sleep Habits That Maximize SWS

- Last meal 2–3h before bed. Late insulin spike suppresses GH release.
- Cool room (65–68°F / 18–20°C). Body temp drop = sleep onset signal.
- Dark room — even small light kills melatonin. Blackout curtains or eye mask.
- No phone 30 min pre-sleep, OR night-shift mode + brightness <30%.
- Magnesium glycinate 300–400mg, 30 min before bed. Improves SWS depth.
- Hot shower 60–90 min before bed. Body cooldown after = sleep cue.

## Supplements

- **Magnesium glycinate** — improves SWS quality, mild anxiolytic. Best risk/reward.
- **Melatonin** 0.3–1mg (microdose) — only useful for jet lag or shifted schedules. Higher doses cause grogginess.
- **L-theanine** 200mg — mild relaxation, stacks with magnesium.
- **Zinc** — supports testosterone + sleep cycle indirectly.
- Avoid sleeping pills (Ambien, etc.) — fragment SWS, induce dependency. Last resort, not a habit.

## What Hurts Growth + Recovery

- Alcohol within 3h of bed: destroys SWS, even at low doses.
- Marijuana: reduces SWS over chronic use.
- Late-night training (intense, within 2h of bed): elevated cortisol delays sleep.
- Inconsistent schedule (varying bedtime ±2h): chronic mild jet lag.
- Phone in bed: even if not "looking at it," presence cues alertness.

## Reality Check For Adults

If you're past growth plate fusion, sleep won't add bone height. But it WILL: improve posture (apparent height +0.5–1 inch), boost facial recovery (skin, undereye, jaw definition), restore disc height each night, and protect the height you have for life.""",
    },
    {
        "maxx_id": "heightmax",
        "doc_title": "Nutrition for Height",
        "content": """\
# Nutrition for Height — what to feed bones (open growth plates only)

Caveat: nutrition matters MOST during active growth (childhood through ~18M / ~16F). Past growth plate fusion, no nutrient adds bone length. But adult nutrition still affects bone density (which preserves your existing height) + connective tissue / posture.

## Calcium

- **Daily target**: 1000mg (adults), 1300mg (teens/active growth).
- **Best sources**: dairy (yogurt, cheese, milk), sardines + canned salmon (with bones), tofu (calcium-set), leafy greens (kale, bok choy — NOT spinach, oxalates block absorption).
- **Supplement only if dietary intake is low**: calcium citrate 500mg with meals. Don't exceed 500mg per dose — absorption caps.
- **Without vitamin D and K2, calcium doesn't reach bone**.

## Vitamin D3 + K2 (the bone delivery system)

- **D3**: 2000–5000 IU daily. Below ~30 ng/mL serum, your body can't absorb calcium efficiently. Get bloodwork — most people are deficient.
- **K2 (MK-7)**: 100–200mcg daily. Directs calcium TO bone (and away from arteries). Synergizes with D3.
- Taking high-dose D3 without K2 long-term may calcify soft tissue. Always pair them.

## Protein for Growth Plates + Bone Matrix

- **Daily target**: 0.7–1.0 g per lb bodyweight.
- Bone is ~50% protein matrix (collagen) — undereating tanks growth + repair.
- **Best sources**: eggs, dairy, lean meat, fish, legumes.
- **Collagen 10–20g/day** (gelatin, bone broth, or supplement) — modest evidence for bone + connective tissue support.

## Micronutrients That Matter

- **Zinc** 15–25mg: critical for IGF-1 + growth hormone signaling.
- **Magnesium** 300–400mg: ~60% of bone mineral structure includes Mg.
- **Vitamin C** 200mg+: required for collagen synthesis. Citrus, peppers, kiwi.
- **Vitamin A** (retinol form) — supports osteoblast function. Liver, eggs, dairy. Don't megadose.
- **Boron** 3mg: small but real effect on bone metabolism.

## Foods To Avoid (Or Minimize)

- **Excess salt** (>2300mg sodium/day): pulls calcium from bones via urinary excretion.
- **Excess caffeine** (>400mg): reduces calcium absorption.
- **Phosphoric acid sodas** (Coke, Pepsi): chronic intake correlates with lower bone density in teens. Drink water or milk.
- **High-sugar / high-processed-carb diet**: drives chronic inflammation + insulin resistance, hurts bone metabolism.
- **Alcohol regularly**: reduces osteoblast activity + GH release.

## Adolescent-Specific Maximization (open plates)

If you're under 18 (M) or 16 (F) and still growing:
- Hit calcium 1300mg + protein 0.8g/lb daily, every day.
- Sleep 9–10h.
- Train (sprint, jump, lift) — mechanical load signals bone to grow.
- Don't smoke. Smoking truncates final height by ~1cm in adolescent users.
- See a pediatrician if growth velocity has stalled — could be hormonal.

## Adult Nutrition Reality

Past growth plate closure: nutrition is about **preserving** bone density + posture, not adding length. Same nutrients (calcium, D3, K2, protein, magnesium), same targets. The wins are: fewer fractures by 60, better posture, no apparent height loss into old age.""",
    },
    {
        "maxx_id": "heightmax",
        "doc_title": "Stretching",
        "content": """\
# Stretching & Flexibility — apparent height + posture (not bone)

Stretching does NOT make your bones longer. Period. It DOES open up posture, decompress soft tissue, restore lost spinal length from compression, and unlock the apparent height your slouch was costing you. That's typically 0.5–1.5 inches recoverable.

## Morning Stretch Routine (10 min)

Do this before checking your phone. Cumulative posture wins compound over months.

1. **Cat-cow** — 10 reps, slow. Articulates spine, primes mobility.
2. **Standing forward fold** — 60s. Hamstrings + lower back unload.
3. **Cobra** — 30s, 2 rounds. Reverses thoracic kyphosis from sleep.
4. **Hip flexor lunge stretch** — 60s per side. Counters anterior pelvic tilt from sitting.
5. **Doorway chest stretch** — 60s per side. Counters rounded shoulders.
6. **Wall angels** — 10 reps. Activates lower traps + scapular retractors.

## Hip Flexor + Hamstring Work (the apparent-height duo)

- **Tight hip flexors → anterior pelvic tilt** → lower back arches forward → spine compresses + you look shorter.
- **Tight hamstrings → posterior pelvic tilt** → flattens lumbar curve → looks slouched.
- Most desk workers have BOTH at the same time — fix is daily mobility, not just stretching once a week.

Hip flexor protocol:
- Kneeling lunge stretch, 60s per side, 2x/day.
- Pigeon pose (or 90/90 sit), 60s per side, 1x/day.
- Couch stretch (rear foot elevated on couch, lunge forward), 60s per side, 1x/day.

Hamstring protocol:
- Standing forward fold, 60s, 2x/day.
- Active straight-leg raises, 10 reps per side, daily.
- PNF stretching post-workout: contract-relax 3x10s holds.

## Thoracic Mobility (the upper back fix)

Forward head + rounded shoulders + tech neck = visible 1–2 inches of apparent height lost. Fix:

- **Foam roll thoracic spine**: 2 minutes daily. Lay on roller perpendicular to spine, hands behind head, gently extend over roller.
- **Wall slides** (back flat against wall, arms 90° overhead): 10 reps daily.
- **Band pull-aparts** with light band: 15 reps, 2x/day.
- **Prone Y-T-W raises** on floor: 10 reps each, 1x/day. Activates lower + middle traps.
- Pull-ups + rows in your training program (3+ sessions/week).

## Consistency + Tracking

- Mobility doesn't show in 1 week. Compounds over 8–12.
- Photo every 4 weeks: same position, same lighting, same clothes. Side profile reveals pelvic + thoracic changes you can't feel.
- Measure standing height once a month, morning, against a wall — most people gain 0.5–1.5cm of recovered height in 8–12 weeks of consistent work.

## What Doesn't Help

- Static stretching pre-lifting → actually reduces strength temporarily. Save it for evening or rest days.
- Aggressive stretching to "force" growth — chronic overstretching damages tendons, no height benefit.
- Yoga without postural emphasis (just sweating in poses) — moves mobility, but you need targeted thoracic + hip work for actual posture change.
- Stretching for height gain past growth plate fusion — apparent height only, no bone length.""",
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
# Jaw Exercises & Masseter Training — what builds the muscle, what breaks the joint

The visible jawline is mostly two things: bodyfat above the jaw and masseter muscle thickness behind it. Masseter responds to load like any other muscle — but the TMJ is unforgiving when you overload it.

## Mastic Gum Protocol (the standard)

- **Product**: Greek mastic gum (chios mastic) OR Falim Turkish gum (much cheaper, similar load).
- **Hardness**: ~3–5x harder than regular gum. Real masseter loading.
- **Dose**: 30–60 minutes per day, total. Split across 2–3 sessions.
- **Sides**: alternate sides every few minutes. NEVER chew chronically one-sided — creates asymmetry.
- **Timeline**: 4–6 weeks for visible width gain. 12 weeks for clear masseter hypertrophy. Plateau by ~6 months without progressive overload.

## Jawzrsize / Jawline Trainer Tools

- Silicone bite tools providing 20–40lb resistance per chew.
- More intense than mastic gum but harder to control TMJ load.
- **Use 2–3x/week max**, 5–10 min sessions. NOT daily.
- Stop immediately at any joint clicking or pain.
- Verdict: optional. Mastic gum + falim covers 90% of the gain at lower TMJ risk.

## Masseter Hypertrophy Timeline

- Week 1–4: subjective fatigue + soreness. No visible change.
- Week 4–8: faint width increase, more obvious in side mirror.
- Week 8–12: clear bilateral hypertrophy. Selfies show measurable change.
- Week 12+: plateau without progressive overload (harder gum, longer sessions, or weighted bite tools).
- Realistic ceiling: 2–4mm width gain per side. Bigger gains usually = TMJ inflammation or one-sided imbalance.

## Avoiding TMJ Issues

- **Pre-existing TMJ?** Cap at 15 min/day mastic, NEVER use bite tools, see a dentist before progression.
- **Clicking joint** = stop the session. Inflammation in the TMJ disc — rest 1 week + ice.
- **Pain in front of ear** during chewing = overload. Cut volume by half for 2 weeks.
- **Headache after sessions** = jaw clenching too hard. Lighten grip; you don't need to crush the gum, just chew rhythmically.
- **Bilateral discipline**: alternate sides religiously. Asymmetry from chronic one-sided chewing takes months to undo.

## Stack For Maximum Effect

- Mewing 24/7 (free baseline tongue-pressure work)
- Mastic / Falim 30–60 min daily, alternating sides
- Body fat <15% — single biggest mover for jawline visibility regardless of muscle
- Neck training (chin tucks, weighted neck work) — counters double-chin appearance""",
    },
    {
        "maxx_id": "bonemax",
        "doc_title": "Bone Density & Diet",
        "content": """\
# Bone Density & Diet — the substrate your jaw + skull are built from

Bone is living tissue: it remodels under mechanical load, hormonal signal, and nutrient supply. Adolescents add density during puberty (peak by ~25). Adults can maintain or rebuild density but cannot add new length to closed plates.

## The Trio: Calcium + Vitamin D3 + Vitamin K2

These work together. Missing any one and the others underperform.

- **Calcium** 1000mg/day adults, 1300mg/day teens. Best from dairy, sardines (with bones), tofu (calcium-set), leafy greens (kale, bok choy — not spinach).
- **Vitamin D3** 2000–5000 IU daily. Required for calcium absorption from gut. Get bloodwork — most adults are deficient (target 30–60 ng/mL).
- **Vitamin K2 (MK-7)** 100–200mcg daily. Directs calcium INTO bone (and away from arteries). The missing piece in most stacks.
- Take all three with the same fatty meal for absorption.

## Weight-Bearing Exercise For Bone Density

Bone responds to mechanical strain. Sedentary = bone loss; loaded = bone gain.

- **Compound lifts** (squat, deadlift, OHP, bench): #1 osteogenic stimulus. Heavy 5x5 work loads the spine + hips.
- **Jumping / plyometrics**: 50 jumps total, 3x/week. High-impact stimulus. Best for adolescents.
- **Sprinting**: similar bone-loading benefit. 10–20 sprints, 2x/week.
- **Walking is NOT enough** for bone density maintenance — the load is too low.

## Collagen + Connective Tissue

Bone matrix is ~50% collagen. Tendons + ligaments are pure collagen.

- **Collagen peptides 10–20g daily** with vitamin C (50mg+). Take pre-workout or with breakfast.
- **Bone broth**: same idea, gentler delivery.
- **Glycine** 5g pre-bed: stimulates collagen synthesis + improves sleep.
- Skin and joint benefits are bonuses; the bone effect is the headline for jaw training.

## Hormonal Factors

- **Testosterone**: drives bone density in men. Low T (<400 ng/dL) → progressive density loss. Sleep + lifting + adequate fat intake (0.3+ g/lb bodyweight) maintain natural production.
- **Estrogen**: protects bone in women. Post-menopausal women lose ~1% density/year without HRT.
- **Cortisol**: chronic stress = chronic high cortisol = bone catabolism. Manage stress, sleep deeply, don't overtrain.
- **GH / IGF-1**: pulses during deep sleep. Sleep deprivation tanks bone-supportive hormones.

## What Hurts Bone

- Sodas with phosphoric acid (Coke, Pepsi) — chronic intake drops bone density in teens.
- Smoking — directly inhibits osteoblasts.
- Alcohol >2 drinks/day — suppresses osteoblast function.
- Excess sodium — pulls calcium out via urine.
- Crash dieting — under-eating drops bone density measurably within months.

## Reality For Jaw Aesthetics

Mature mandible is shaped by genetics + adolescent growth. Adult bone density work won't reshape your jaw — but it WILL: maintain the structure you have, support masseter training, prevent age-related shrinkage of facial bone (real phenomenon by 60+), and provide the substrate for any cosmetic work later in life.""",
    },
    {
        "maxx_id": "bonemax",
        "doc_title": "Facial Structure",
        "content": """\
# Facial Structure & Forward Growth — the orthotropics framework

The Mew/orthotropics model: facial bone position is heavily influenced by tongue posture, breathing, and chewing load during development. The further forward the maxilla projects, the more defined the face. The further down/back, the longer + softer the face appears.

## Maxilla vs Mandible

- **Maxilla (upper jaw)**: drives midface projection. Forward growth = high cheekbones + supportive midface + short philtrum. Recessed = long face, dark undereye, weak cheekbones.
- **Mandible (lower jaw)**: jawline + chin. Forward = strong defined jaw. Recessed = weak chin, double-chin appearance even at low bodyfat.
- **Maxilla position dictates mandible position**. Recessed maxilla forces mandible to retreat (otherwise teeth wouldn't meet).

## Orthotropics Principles

The Mews (Mike + John) argue:
1. **Tongue on palate, lips sealed, teeth lightly touching** = correct resting posture. Drives forward maxillary growth in children.
2. **Mouth breathing** = tongue drops + maxilla descends + face elongates over years.
3. **Soft modern diet** = under-loaded jaw = narrower arch, smaller mandible than ancestors.
4. Adolescent intervention (proper tongue posture + hard chewing) can guide growth. Adult intervention is much smaller — bone is set.

Evidence base: orthotropics is mechanistically plausible for adolescents (sutures still pliable). Adult claims (palatal expansion via mewing) are largely anecdotal and contested by mainstream orthodontics.

## Breathing & Facial Development

- **Nasal breathing 24/7** (including sleep) is foundational. Teaches tongue to sit on palate by default.
- **Mouth breathing** during growth → adenoid facies (long face, weak chin, dental crowding).
- **Mouth tape at night** for adults: $5/month. Forces nasal breathing during sleep when tongue posture is involuntary.
- **Nasal strips** if you have a deviated septum or chronic congestion. Combine with seasonal allergy management.
- **Chronic sinus issues** → see ENT. Persistent obstruction long-term shapes the face.

## Adult Realistic Expectations

If your growth plates closed years ago:
- **Mewing 24/7**: marginal forward maxilla position improvement (mostly tongue muscle tone), better chin tuck appearance, reduced double-chin look. Visible only with discipline + months.
- **Hard chewing**: real masseter hypertrophy (visible jawline width). 4–12 weeks. The biggest non-surgical lever.
- **Body fat reduction** to <15% (M) / <22% (F): by far the biggest visible jaw improvement. Bone hasn't moved — fat just no longer hides it.
- **Posture work**: shifts head forward → backward = visible chin/jaw definition + 0.5–1 inch apparent height.

## Surgical vs Non-Surgical

Surgical (when natural is exhausted):
- **MARPE** (mini-screw assisted palatal expansion): adult expansion of maxilla via screws over 6 months. Real bone movement. Done at maxillofacial surgery clinics.
- **Le Fort / BSSO** (orthognathic surgery): moves maxilla and/or mandible forward. Massive aesthetic + functional change. Requires 1–2 years orthodontic prep + surgery + recovery. $30k–$80k.
- **Genioplasty**: chin advancement. Smaller scope, quicker recovery.
- **Filler / implants**: cosmetic illusion of structure. Cheaper, reversible (filler) or semi-permanent (implants). Doesn't change underlying bone.

Non-surgical first. Surgery is for people whose facial structure is causing functional issues (sleep apnea, bite problems) or for advanced lookmaxxing where natural ceiling is hit and budget allows.""",
    },
    {
        "maxx_id": "bonemax",
        "doc_title": "Chewing Protocol",
        "content": """\
# Chewing Protocol — the daily load that builds masseter

Chewing is the only training method that delivers consistent masseter load. The product matters less than the consistency.

## Hard Gum vs Mastic Gum vs Falim

Ranked by hardness + cost-effectiveness:

- **Falim Turkish gum** (~$0.05/piece): cheapest, ~3x harder than regular gum, comes in mint/cinnamon/sugar-free. The standard for daily volume.
- **Greek Mastic Gum** (~$0.50/piece): natural resin, ~5x harder, distinctive pine taste. Premium option, can be split with falim.
- **Regular sugar-free gum** (Trident, Extra): too soft for meaningful load. Won't move the needle past 4 weeks.
- **Jawzrsize / silicone bite tools**: harder than gum but high TMJ risk. Use sparingly.
- **Beef jerky / dense steaks**: real food, real load. Add to diet 2–3 meals/week if jaw size is a goal.

## Duration & Frequency

- **Total daily volume**: 30–60 minutes of active chewing.
- **Distribution**: split across 2–3 sessions. Don't chew 60 min straight (TMJ overload).
- **Days/week**: 6 days. One rest day allows masseter recovery.
- **Per-piece life**: Falim loses hardness after ~10 min. Replace it. Mastic stays harder ~20 min.
- **Sessions example**: 20 min morning + 20 min afternoon + 20 min while working/walking.

## Bilateral Chewing Technique — non-negotiable

- Switch sides every 2–3 minutes. Use a timer if you space out.
- Most people have a "dominant chewing side" → develops asymmetric jaw width.
- If you've been chewing one-sided for years: consciously favor the weak side 70/30 for 2–3 months until balance returns.
- Even pressure: don't crush down with full force. Rhythmic medium pressure builds endurance + size; max-effort crushing risks TMJ.

## Progress Tracking

- **Photos**: front + 3/4 + side, same lighting, every 4 weeks. Masseter changes are subtle in mirror; obvious in 3-month side-by-sides.
- **Tape measure**: across widest jaw point (gonial angle area), morning, mouth closed, teeth lightly touching. Track weekly average.
- **Soreness journal**: faint masseter DOMS first 2 weeks → adapts. Persistent soreness = overload, back off.
- **Visual checkpoints**: 4 weeks (subjective fatigue + soreness), 8 weeks (faint width gain in mirror), 12 weeks (clearly visible to others).

## When Progress Stalls (12+ Weeks In)

- Switch from Falim → Mastic for harder load.
- Add 5–10 min per session.
- Add a bite-tool session 1x/week (Jawzrsize style) for novel stimulus — if TMJ is healthy.
- Re-check body fat — masseter you can't see under 18% bodyfat is wasted effort.
- Cut session length back if soreness is persistent — recovery is part of growth.

## What Won't Work

- Chewing all day with regular soft gum.
- Doing 5-min sessions inconsistently.
- Crushing harder gum 1x/week (no progressive volume = no adaptation).
- Ignoring side-rotation discipline.
- Expecting bone-level jaw change from masseter alone — it's muscle hypertrophy, not bone widening.""",
    },
    # New: explicit Bonesmashing doc — users actually search for this term
    {
        "maxx_id": "bonemax",
        "doc_title": "Bonesmashing",
        "content": """\
# Bonesmashing — what it is, what it actually does, and what to do instead

Also called: bonesmash, bone smash, bone smashing, bonemashing, skull smashing, cheekbone smashing.

"Bonesmashing" is the practice of repeatedly striking the facial bones (cheekbones, zygomatic, jaw, chin) with a hard object — small hammer, smooth river rock, glass bottle — under the theory that bone responds to mechanical microtrauma by remodeling thicker (Wolff's Law applied to face). It's spread through TikTok, looksmax forums, looksmaxxing communities, and r/Lookism.

## The Theoretical Mechanism

- **Wolff's Law**: bone adapts to applied load by laying down new bone in stress lines.
- Proponents argue facial bone, like any bone, can be remodeled denser/wider via repeated low-impact percussion.
- Cited references: weightlifters with denser long bones, boxers with thickened nasal bones.

## What The Evidence Actually Shows

Be candid about this — the evidence does NOT support the practice as proponents claim:

- **No clinical studies on facial bonesmashing in humans**. Anecdotes only.
- Boxer + weightlifter bone changes happen over **years** of progressive load — not 5-minute home percussion sessions.
- Facial bone is thinner and more vascular than long bone — much higher fracture/microfracture risk per impact.
- "Wolff's Law adaptation" requires sub-fracture-threshold load. Most home practitioners massively overshoot.

## Real Risks

- **Periosteal damage** (the bone covering): bruising + chronic inflammation, can scar the surface.
- **Hairline fractures**: can heal misaligned, leaving permanent asymmetry.
- **Nerve damage**: trigeminal branches run close to surface bone (cheek, jaw line). Repeated trauma → numbness, hypersensitivity, chronic pain.
- **Soft tissue swelling**: can produce a temporary "fuller" look (mistaken for "gains") that's actually edema. Subsides in days, returns to baseline.
- **Long-term cumulative damage**: similar pathology to repeated head trauma in contact sports — facial bone can develop osteonecrosis or resorption from repeated injury.

## Why People Think It "Works"

- **Edema after sessions** = temporary swelling that distorts perception.
- **Confirmation bias** = combined with mewing, chewing, fat loss, posture work all happening simultaneously.
- **Photo angles** = 4 weeks of progress photos = different lighting + camera height.
- **Forum echo chambers** = success stories upvoted, regrets/injuries silenced.

## What To Do Instead (everything bonesmashing claims, without the risk)

For visible jaw + cheekbone change:

1. **Body fat <12–15% (M) / <22% (F)**: single biggest visible change to facial structure. Bone hasn't moved — fat just stops hiding it. Free, evidence-based.
2. **Mastic gum / Falim 30–60 min daily** (alternating sides): builds masseter muscle. Visible jaw width gain in 8–12 weeks.
3. **24/7 mewing + nasal breathing**: muscle tone of tongue + face over 6+ months. Marginal but cumulative.
4. **Neck training**: chin tucks + weighted neck flexion 3x/week. Eliminates double-chin appearance, sharpens jaw line.
5. **Posture / forward head correction**: pull head back to neutral spine. Visible chin/jaw definition gain immediately.
6. **Weight train compound lifts**: increases overall facial fullness via testosterone + general muscle/bone density.

That stack delivers 80%+ of the visible change real bonesmashers claim, in 12 weeks, with zero injury risk.

## If You're Still Going To Do It

Don't. But if you do despite this:
- Never strike directly with hard objects.
- Use only manual fingertip percussion with light pressure.
- Stop immediately at any pain, swelling, numbness, or asymmetry.
- See an oral surgeon or maxillofacial specialist if you've already done damage.
- Consider that the hours you'd spend on this could be on the legitimate stack above.

## Bottom Line

Bonesmashing is mostly cope wrapped in pseudoscientific Wolff's Law citations. Adult facial bone is set. The visible-change wins everyone wants come from masseter, body fat, and posture — none of which require hitting your face with a hammer.""",
    },
]


async def main() -> None:
    _load_env()
    from db.sqlalchemy import AsyncSessionLocal
    from sqlalchemy import text

    assert len(DOCS) >= 25, f"Expected at least 25 docs, got {len(DOCS)}"

    by_maxx: dict[str, int] = {}
    for d in DOCS:
        by_maxx[d["maxx_id"]] = by_maxx.get(d["maxx_id"], 0) + 1
    for mid, count in sorted(by_maxx.items()):
        assert count >= 5, f"{mid} has {count} docs, expected at least 5"

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
