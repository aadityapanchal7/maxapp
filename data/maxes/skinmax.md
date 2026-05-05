---
maxx_id: skinmax
display_name: Skin
short_description: Clear, even, healthy skin via barrier-first protocols.

schedule_design:
  cadence_days: 14
  am_window: ["wake+0:10", "wake+1:30"]
  pm_window: ["sleep-2:00", "sleep-0:15"]
  daily_task_budget: [3, 6]
  intensity_ramp:
    week_1: [0.0, 0.5]
    week_2: [0.3, 1.0]
  # Deterministic skeleton — schedule_skeleton.py expands this against the
  # user's required_field answers without an LLM call. Block order = render
  # order; each block is independently filtered by `if`. `replaces` lets a
  # phase override a default block (e.g. REPAIR replaces pm_active).
  skeleton:
    blocks:
      - id: am_foundation
        slot: am_open
        cadence: daily
        tasks: [skin.cleanse_am, skin.moisturize_am, skin.spf]
      - id: am_active
        slot: am_active
        cadence: daily
        # Picker walks `pick_from` and emits at most one task per day.
        # First eligible item with remaining quota wins.
        pick_from:
          - { id: skin.azelaic_am,  days_per_week: 7, requires: ["skin_concern in [acne, rosacea, pigmentation]", "barrier_state != damaged"] }
          - { id: skin.centella_am, days_per_week: 7, requires: ["skin_concern == rosacea or barrier_state == damaged"] }
      - id: midday_check
        slot: midday
        cadence: daily
        tasks: [skin.hydration_water]
      - id: midday_spf_reapply
        slot: midday
        cadence: daily
        if: "outdoor_exposure in [heavy, moderate]"
        tasks: [skin.spf_reapply]
      - id: pm_foundation
        slot: pm_close
        cadence: daily
        tasks: [skin.cleanse_pm, skin.moisturize_pm]
      - id: pm_active
        slot: pm_active
        cadence: dynamic
        pick_from:
          # Ordered by priority. Conflicts (`not_with`) are enforced day-by-day.
          - { id: skin.retinoid_pm,    days_per_week: 4, requires: ["skin_concern in [acne, pigmentation, texture, maintenance]", "barrier_state != damaged"], not_with: [skin.dermastamp_pm] }
          - { id: skin.dermastamp_pm,  days_per_week: 2, requires: ["skin_concern in [pigmentation, texture]", "barrier_state == stable", "dermastamp_owned == true"], not_with: [skin.retinoid_pm] }
      - id: pm_circulation
        slot: pm_close
        cadence: n_per_week=5
        tasks: [skin.facial_massage]
      - id: internal_zinc
        slot: am_open
        cadence: daily
        if: "skin_concern in [acne, pigmentation]"
        tasks: [skin.zinc_supp]
      - id: internal_diet
        slot: flexible
        cadence: n_per_week=5
        if: "skin_concern in [rosacea, acne, pigmentation] and diet_open in [yes_full, yes_some]"
        tasks: [skin.diet_anti_inflammatory]
      # Phase override: damaged barrier → strip all actives + force pause day.
      # `replaces` removes other blocks by id before placement.
      - id: phase_repair_lock
        slot: pm_active
        cadence: daily
        if: "barrier_state == damaged"
        replaces: [pm_active, am_active]
        tasks: [skin.barrier_pause]
      # --- Density layer: weekly + monthly habits a real protocol includes ---
      - id: pillowcase_change
        slot: midday
        cadence: n_per_week=1
        tasks: [skin.pillowcase_change]
      - id: weekly_exfoliation
        slot: pm_active
        cadence: n_per_week=1
        if: "barrier_state == stable and skin_concern in [acne, pigmentation, texture]"
        not_with_same_day: [skin.retinoid_pm, skin.dermastamp_pm]
        tasks: [skin.weekly_exfoliation]
      - id: hydration_mask
        slot: pm_active
        cadence: n_per_week=1
        if: "skin_concern in [rosacea, maintenance] or skin_type == dry"
        tasks: [skin.hydration_mask]
      - id: progress_photo_skin
        slot: am_open
        cadence: weekly_on=sunday
        tasks: [skin.progress_photo]
      - id: monthly_review_skin
        slot: midday
        cadence: monthly_on=1
        tasks: [skin.monthly_review]
      - id: derm_check
        slot: flexible
        cadence: monthly_on=1
        if: "skin_concern in [acne, rosacea, pigmentation]"
        tasks: [skin.derm_consult]

required_fields:
  - id: skin_concern
    question: "What's the one thing you'd most like to change about your skin right now?"
    type: enum
    options:
      acne: "Active breakouts / pimples"
      pigmentation: "Dark spots, post-acne marks, uneven tone"
      rosacea: "Persistent redness, flushing, sensitivity"
      texture: "Rough texture, large pores, congestion"
      maintenance: "Skin looks fine — I want to keep it that way"
    required: true
    why: "Determines the protocol track (acne / pigment / rosacea / texture / maintain) and which actives are safe."

  - id: barrier_state
    question: "When you apply actives like acids or retinoids, does your skin sting, burn, or get red?"
    type: enum
    options:
      damaged: "Yes — even gentle products often irritate me"
      sensitive: "Sometimes, depends on the product"
      stable: "No — my skin tolerates things well"
    required: true
    why: "Damaged barriers must be repaired BEFORE actives. Skipping this is the #1 cause of skincare failure."

  - id: skin_type
    question: "A few hours after washing, how does your skin feel?"
    type: enum
    options:
      oily: "Shiny / oily across the whole face"
      dry: "Tight, sometimes flaky"
      combo: "Oily T-zone, normal or dry cheeks"
      normal: "Comfortable, balanced"
    required: true
    why: "Drives moisturizer choice and wash frequency."

  - id: routine_level
    question: "Where are you starting from with your skincare routine?"
    type: enum
    options:
      none: "Nothing right now — start me from scratch"
      basic: "Cleanser + moisturizer + SPF"
      intermediate: "I use 1–2 actives (vitamin C, BHA, etc.)"
      advanced: "Multiple actives + retinoid in rotation"
    required: true
    why: "Drives ramp speed. Beginners get a slower onboarding to actives; advanced users skip the foundation phase."

  - id: outdoor_exposure
    question: "How much time do you spend outside in direct sun, on a typical day?"
    type: enum
    options:
      heavy: "A lot — outdoor work, daily walks, frequent sun"
      moderate: "Some — commute, errands, weekend outdoors"
      minimal: "Barely — mostly indoors, drive everywhere"
    required: true
    why: "Drives SPF reapply cadence. Heavy = midday + afternoon reapply task. Minimal = AM SPF only."

  - id: tret_history
    question: "Have you ever used tretinoin or a prescription retinoid before?"
    type: enum
    options:
      never: "No, never tried it"
      tried_quit: "Tried it, but quit (irritation, side effects)"
      currently_on: "Currently using it"
      previously_used: "Used it in the past, comfortable with it"
    required: true
    why: "Drives retinoid ramp pace. Never → start at 0.025% 2×/wk and ramp slowly. Currently_on → maintain current cadence. Quit-due-to-irritation → use buffered/sandwich method or skip retinoid track entirely."

  - id: climate
    question: "What's your climate / weather like, mostly?"
    type: enum
    options:
      humid: "Humid — sticky, sweaty, high moisture"
      dry: "Dry — low humidity, arid, indoor heat"
      temperate: "Mild — neither extreme"
      cold: "Cold — winter most of the year"
    required: true
    why: "Drives moisturizer weight + hydration emphasis. Dry/cold = heavier moisturizer + occlusive layer at PM. Humid = lightweight gel-cream + extra cleanse cadence."

  - id: diet_open
    question: "Open to small diet tweaks (cutting dairy, sugar, or seed oils) if they'd clear your skin faster?"
    type: enum
    options:
      yes_full: "Yes — willing to cut anything if it helps"
      yes_some: "Maybe — open to one or two changes"
      no: "Not interested — keep food separate"
    required: true
    why: "Gates internal-support tasks (anti-inflammatory diet reminders, dairy/sugar cuts). Most acne and rosacea respond significantly to dietary changes."

optional_context:
  - id: product_preferences
    description: "Specific cleansers/moisturizers/SPFs the user prefers"
  - id: product_dislikes
    description: "Products that have caused breakouts or irritation"
  - id: dermastamp_owned
    description: "Whether user owns a dermastamp (gates that task)"
  - id: hormonal_factors
    description: "On accutane/birth control/cycle issues — gates aggressive actives"
  - id: routine_complexity_pref
    description: "User prefers a minimalist routine vs. willing to layer many products"
  - id: budget_constraint
    description: "Drugstore-only vs. open to mid-tier vs. open to any price"
  - id: time_per_routine
    description: "How many minutes user wants to spend per AM/PM routine — drives layering depth"

prompt_modifiers:
  - id: phase_repair
    if: "barrier_state == damaged"
    then: "PHASE: REPAIR for first 2 weeks. NO retinoids, NO acids, NO vitamin C. Foundation only: cleanse, ceramides, panthenol, SPF. Rationale: barrier must heal before actives can work."
  - id: rosacea_calm
    if: "skin_concern == rosacea"
    then: "PHASE: REPAIR for week 1. Centella + azelaic only. NO retinoid in week 1. Avoid morning heat-exposure tasks. Add internal anti-inflammatory cue 1×/day."
  - id: pigment_resurface
    if: "skin_concern == pigmentation and barrier_state != damaged"
    then: "Week 1 = REPAIR. Week 2+ = RESURFACE: retinoid PM (0.05% start, pea-sized), dermastamp 2×/wk on non-retinoid nights only. SPF AM is non-negotiable."
  - id: acne_protocol
    if: "skin_concern == acne and barrier_state != damaged"
    then: "Azelaic AM (anti-inflammatory + antibacterial), retinoid PM after week 1. Single active per session. Add internal sugar/dairy reduction prompt 3×/wk."
  - id: maintenance_simple
    if: "skin_concern == maintenance"
    then: "PROTECT phase from day 1. Minimal routine: cleanse AM/PM, moisturizer, SPF, retinoid PM 3×/wk. No phase ramp needed."
  - id: routine_none_starter
    if: "routine_level == none"
    then: "ABSOLUTE BEGINNER. Week 1–2 = cleanser + moisturizer + SPF only, no exceptions. Build the habit first. Week 3+ introduce ONE active per fortnight. Skip all PM actives until week 4."
  - id: routine_advanced_skip_ramp
    if: "routine_level == advanced"
    then: "ADVANCED USER. Skip the foundation phase. Start full protocol week 1 at user's existing tolerance level. Lean on prompt_modifiers for concern; assume user knows ingredient interactions."
  - id: heavy_outdoor_spf
    if: "outdoor_exposure == heavy"
    then: "SPF REAPPLY: critical. Schedule midday SPF reapply (AM+3h) every day + afternoon (AM+6h) on weekdays. Use stick or powder format for over-makeup reapply. Add weekly UV-damage scan reminder."
  - id: minimal_outdoor_spf
    if: "outdoor_exposure == minimal"
    then: "SPF REAPPLY: skip — AM SPF + window-distance only. Save the notification slot for hydration check or evening routine cue."
  - id: tret_never_slow_ramp
    if: "tret_history == never and skin_concern in [acne, pigmentation, texture, aging]"
    then: "RETINOID RAMP: start at adapalene 0.1% (drugstore, gentle) or tretinoin 0.025%, 2×/wk weeks 1–2, 3×/wk weeks 3–4, every-other-night weeks 5–8, nightly week 9+. Add purge reassurance reminder week 2."
  - id: tret_quit_buffer
    if: "tret_history == tried_quit"
    then: "RETINOID SANDWICH METHOD: moisturizer first, retinoid 0.025% over the moisturizer (buffered), wait 20 min, moisturizer again. Start 1×/wk only. Slow reintroduction prevents the irritation that caused them to quit before."
  - id: tret_currently_maintain
    if: "tret_history == currently_on"
    then: "RETINOID: maintain current cadence — do NOT reset the ramp. Schedule retinoid PM at user's existing frequency (default 4×/wk). Skip purge reassurance — user is past that phase."
  - id: dry_climate_occlusive
    if: "climate in [dry, cold]"
    then: "MOISTURIZER: heavier ceramide cream PM + occlusive seal (squalane oil or petrolatum-based balm) on top. Add hydration check 2×/day during winter months. Skip foaming cleanser AM — too stripping in dry air."
  - id: humid_climate_lighter
    if: "climate == humid"
    then: "MOISTURIZER: lightweight gel-cream only. Skip oils. Add second cleanse cadence (PM double-cleanse always). Increase BHA frequency to clear sweat-driven congestion."
  - id: diet_full_open
    if: "diet_open == yes_full"
    then: "INTERNAL TRACK: enable all anti-inflammatory diet reminders. Daily anti-inflammatory cue at lunch. Weekly dairy/sugar/seed-oil cycling reminder. 30-day elimination challenge after week 4 if breakouts persist."
  - id: diet_partial
    if: "diet_open == yes_some"
    then: "INTERNAL TRACK: light. One diet reminder per week (rotate dairy/sugar/seed-oils). No elimination challenge. Frame as 'optional' so user doesn't feel forced."
---

# Why skin matters for appearance

Skin is the foundation of facial attractiveness. Before someone notices your jawline, eyes, or symmetry, they subconsciously register skin clarity, tone, and texture. Good skin acts like a filter — it enhances everything underneath. Bad skin overrides even strong features.

Most people think skincare is about products. In reality it's about controlling inflammation, protecting the barrier, and maintaining internal balance. When those align, good skin is almost automatic.

## The three categories of skin issues

Almost every skin issue falls into one of three buckets. Understanding which one prevents random product use.

**Texture** — surface quality. Rough, bumpy, enlarged pores, acne scars, congestion. Caused by slow turnover, clogged pores, collagen breakdown. Fixed with retinoids, controlled exfoliation, collagen stimulation.

**Pigmentation** — color issues. Post-acne marks (PIH), sun spots, uneven tone. Pigmentation is usually a downstream effect of inflammation: treat pigment without calming inflammation and it returns. Fixed with SPF, retinoids, azelaic acid, anti-inflammatory routine.

**Inflammation** — the root cause. Redness, active acne, rosacea, irritation. Driven internally by gut imbalance, insulin spikes (IGF-1 → oil), stress/cortisol, dietary triggers (sugar, seed oils, dairy). Driven externally by over-exfoliation, harsh products, barrier damage, UV exposure.

Most people try to fix texture or pigment while still inflamed. That's why nothing works long-term.

## How skin quality affects perceived age

Healthy skin: collagen keeps skin tight, light reflection enhances cheekbones and jawline, even tone makes features stand out.

Damaged skin: collagen breakdown causes sagging and dullness, uneven tone makes the face look tired, texture blurs facial definition.

# The biggest skincare mistakes

Most people don't lack products — they have bad system design.

**Over-exfoliating.** Trying to scrub problems away. Result: damaged barrier, more redness, worse acne, sensitivity. Exfoliating inflamed skin makes everything worse.

**Ignoring the barrier.** The barrier controls hydration, irritation, and inflammation. When damaged: products stop working, skin becomes reactive, breakouts increase. Fix with ceramides, panthenol, and pausing actives temporarily.

**Treating symptoms instead of causes.** Treating acne without fixing diet/hormones, treating pigmentation without reducing inflammation, using actives without repairing the barrier.

**Product overload.** Stacking acids + retinoids + vitamin C + exfoliants. Overwhelms skin, reduces absorption. Rule: one active at a time.

**Skipping SPF.** UV worsens pigmentation, breaks down collagen, increases inflammation. SPF is the #1 non-negotiable.

**Ignoring internal health.** Skin is affected by gut health, insulin, inflammation, sleep quality. External products can't outrun internal chaos.

# The skin barrier — most important concept

The skin barrier is the outermost layer (stratum corneum). Skin cells are the bricks; lipids (fats) are the mortar. It controls water retention, protection from bacteria/irritants, regulation of inflammation, and absorption of skincare products.

When intact: skin stays hydrated, irritation is minimal, products absorb correctly, inflammation stays low.

When damaged: water escapes (dry, irritated), irritants enter (inflammation rises), oil dysregulates, skin becomes reactive. This kicks off cycles like: acne → harsh treatment → barrier damage → more acne.

## Signs of barrier damage

- Persistent redness
- Burning or stinging when applying products
- Dryness even after moisturizing
- Flaky or rough texture
- Increased breakouts
- Skin feels tight after washing
- Products suddenly "stop working"

If skin reacts to basic products, the barrier is compromised.

## Repair ingredients

**Ceramides** are the main lipids in the barrier. They lock in moisture, strengthen the barrier, prevent water loss, protect against irritation. Safe for almost all skin types.

**Panthenol (Vitamin B5)** is both hydrator and anti-inflammatory. Soothes irritation, speeds barrier repair, reduces redness. Great paired with retinoids.

**Lipid repair** restores ceramides, fatty acids, and cholesterol together — the skin's natural structure.

## What to STOP during barrier damage

Pause: exfoliating acids (AHA/BHA), scrubs, retinoids if irritation is high, vitamin C if it stings, over-washing.

## The "Repair Before Treating" principle

Most people try to treat acne, remove pigmentation, and smooth texture while inflamed and damaged. This causes worse breakouts, darker pigmentation, chronic irritation.

Correct sequence: repair the barrier → reduce inflammation → introduce actives.

# Layering and absorption

Skin is designed to block things from entering. Products work only if the barrier is prepped, layering is correct, and actives are used strategically.

## The absorption ladder (correct order)

1. **Cleanser** — removes oil, dirt, sunscreen, buildup so actives reach skin.
2. **Toner / hydrating mist** (optional) — light hydration; expanded skin cells absorb next layers better. Apply on damp skin — the "golden window."
3. **Active (one at a time)** — azelaic, niacinamide, retinoid (PM only), exfoliating acids (separate nights).
4. **Treatment serum** — vitamin C (AM) or centella/panthenol (PM). Supports skin after the active.
5. **Hydrating serum** — hyaluronic acid, beta-glucan, peptides. Pulls water in; improves plumpness.
6. **Moisturizer** — locks in hydration; ceramides + lipids repair barrier.
7. **Occlusive (PM, optional)** — Cicaplast or light petrolatum. Seals in. Use only when dry/damaged.
8. **SPF (AM only)** — blocks UV damage and pigmentation.

## Active timing

AM: azelaic acid, niacinamide, vitamin C — reduce inflammation, protect from environmental stress.

PM: retinoids (tretinoin), repair-focused ingredients — collagen production, skin remodeling.

## What destroys absorption

- Over-exfoliating (destroys barrier)
- Alcohol-based toners (break lipid structure)
- Stacking multiple acids (burns receptors)
- Applying on dry, unprepped skin (poor penetration)
- Occlusives in AM (traps heat → redness)

# Collagen activation and rebuilding

## Retinoids — the foundation

Retinoids are the primary drivers of collagen production. They stimulate fibroblasts, increase turnover, improve texture and pigmentation. Not "anti-aging products" — cellular architects.

Protocol: start 0.05% tretinoin, apply on dry skin, pea-sized amount, gradually increase frequency.

## Dermastamping

Creates controlled micro-injury → stimulates collagen → improves product absorption.

Protocol: depth 0.25mm, 2× per week. Never on the same night as retinoids. Reduces scarring, fades pigment faster, smooths texture.

## Facial massage

30–60 seconds daily, upward strokes (jaw → temples → forehead), drain downward behind ears. Improves circulation, healing, nutrient delivery. Reduces puffiness. Avoid on retinoid nights.

# Hyperpigmentation repair

Pigmentation is not the root problem — it's a symptom of inflammation. Trying to "bleach" it away usually makes it worse.

## Phase 1 — Repair (2–4 weeks)

Goal: reduce inflammation, rebuild barrier.

Use: centella asiatica (cica) for redness/micro-damage, azelaic acid 10–20% for inflammation + bacteria + gentle brightening, ceramides + panthenol for barrier.

Internal: L-glutamine 5g AM (gut lining), probiotics 20B CFU, zinc + collagen, hydration ~3L/day. Diet reset 2–3 weeks: avoid high sugar, seed oils, excess dairy, processed foods.

Stop: exfoliating acids, scrubs, vitamin C if irritating, retinoids in first 1–2 weeks.

## Phase 2 — Resurface (4–8 weeks)

Goal: increase turnover so pigmented cells shed.

Retinoid (core driver): 0.05% tretinoin, pea-sized on dry skin, gradually increase. Real retinoids — retinol is weak.

Dermastamping: 0.25mm, 2×/week, never same night as retinoid.

Continue azelaic + barrier support. Avoid high-strength retinoid overdosing and over-exfoliation.

## Phase 3 — Protect (lifelong)

SPF every single day — non-negotiable. UV is the #1 cause of dark spots, uneven tone, collagen breakdown.

Antioxidants: vitamin E, green tea extract — reduce free radical damage.

Sleep & hormone rhythm: deep sleep is when collagen repairs, inflammation resets, pigmentation fades. Poor sleep = high cortisol = slow healing.

# Rosacea and chronic inflammation

Rosacea isn't a texture problem — it's an inflammation problem. Don't attack the skin; calm it, then rebuild.

## What rosacea is

Chronic inflammatory state. Signs: persistent redness, flushing, small bumps or acne-like texture, sensitive reactive skin.

## Internal triggers

Most rosacea starts internally. Drivers: blood sugar / insulin spikes, gut imbalance, stress / cortisol.

Diet triggers: seed oils (inflammatory cytokines), refined sugar (insulin spike), alcohol (vasodilation → flushing), excess dairy (some people).

Even one week of removing these can noticeably reduce redness.

## External triggers

Damaged or sensitive barrier. Triggered by over-exfoliation, harsh cleansers, alcohol-based toners, too many actives, heat, friction.

## Solutions

**Centella asiatica** — strong anti-inflammatory, repairs barrier, reduces redness. Well tolerated.

**Azelaic acid** — reduces redness, fights bacteria, helps pigment. Start 2–3×/week, increase gradually. Avoid if skin severely irritated until barrier stabilizes.

**Anti-inflammatory diet** — remove seed oils / sugar / alcohol / processed for 1–3 weeks. Add protein (stable blood sugar), whole foods, hydration.

**Reduced exfoliation** — avoid physical scrubs, frequent acid use, retinoid overuse. Rosacea gets worse when treated like a texture issue.

## Avoid completely during flares

Exfoliating acids, vitamin C if irritating, over-layering, hot water / heat exposure, aggressive treatments.

## Correct rosacea routine

AM: gentle cleanser → centella or azelaic → moisturizer (ceramides + panthenol) → SPF.

PM: cleanser → centella / calming serum → moisturizer. Delay retinoids until skin stabilizes.

# Routine templates by skin type

**Oily / acne-prone:** cleanse daily, azelaic AM, retinoid PM, consistent but not aggressive washing.

**Dry / sensitive:** cleanse once daily or gentle, focus on hydration + barrier repair, minimal actives at first.

**Combination:** mix; T-zone gets oily-skin treatment, cheeks get dry-skin treatment.

# Hydration and internal support

External: moisturizers, humectants (HA, etc.).

Internal: ~3L water daily, collagen, zinc, anti-inflammatory diet.

# Product usage rules

1. Don't stack actives. Retinoid + acids + vitamin C together → irritation, barrier damage. One active at a time.
2. Wash off product buildup. Leaving products on for days clogs pores, dulls skin, causes flakes.
3. Don't over-wash. Over-washing → dry, barrier-damaged, oilier skin (rebound).

```yaml task_catalog
- id: skin.cleanse_am
  title: "Cleanse face (AM)"
  description: "wash face with a gentle, non-stripping cleanser. lukewarm water only. 30 seconds, no scrubbing."
  duration_min: 3
  default_window: am_open
  tags: [am, cleanse, foundation]
  applies_when: [always]
  contraindicated_when: []
  intensity: 0.1
  evidence_section: "The skin barrier — most important concept"
  cooldown_hours: 0
  frequency: { type: daily, n: 1 }

- id: skin.cleanse_pm
  title: "Cleanse face (PM)"
  description: "wash off SPF + buildup with the same gentle cleanser. don't double-cleanse unless heavy SPF/makeup."
  duration_min: 3
  default_window: pm_active
  tags: [pm, cleanse, foundation]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "The skin barrier"
  frequency: { type: daily, n: 1 }

- id: skin.moisturize_am
  title: "Moisturize (AM)"
  description: "ceramide + panthenol moisturizer on damp skin within 60 seconds of cleansing. dime-sized."
  duration_min: 2
  default_window: am_open
  tags: [am, barrier, foundation]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "Repair ingredients"
  frequency: { type: daily, n: 1 }

- id: skin.moisturize_pm
  title: "Moisturize (PM)"
  description: "ceramide moisturizer to lock in PM routine. wait 5 min after retinoid if used."
  duration_min: 2
  default_window: pm_close
  tags: [pm, barrier, foundation]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "Repair ingredients"
  frequency: { type: daily, n: 1 }

- id: skin.spf
  title: "Apply SPF 50"
  description: "broad spectrum SPF 50, last step of AM routine, 2-finger-length. non-negotiable, every day."
  duration_min: 2
  default_window: am_open
  tags: [am, protect, foundation]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "Phase 3 — Protect"
  frequency: { type: daily, n: 1 }

- id: skin.spf_reapply
  title: "Reapply SPF"
  description: "reapply SPF if you've been outside or near windows. powder or stick is easiest."
  duration_min: 2
  default_window: midday
  tags: [midday, protect]
  applies_when: ["outdoor_exposure in [heavy, moderate]"]
  intensity: 0.2
  evidence_section: "Phase 3 — Protect"
  frequency: { type: daily, n: 1 }

- id: skin.azelaic_am
  title: "Apply azelaic acid"
  description: "thin layer azelaic 10–20% on damp skin AFTER cleanser, BEFORE moisturizer. anti-inflammatory + brightening."
  duration_min: 2
  default_window: am_active
  tags: [am, active, anti-inflammatory]
  applies_when: ["skin_concern in [acne, rosacea, pigmentation]"]
  contraindicated_when: ["barrier_state == damaged"]
  intensity: 0.4
  evidence_section: "Rosacea and chronic inflammation"
  frequency: { type: daily, n: 1 }

- id: skin.centella_am
  title: "Apply centella serum"
  description: "centella asiatica serum for redness/micro-damage. apply on damp skin, before moisturizer."
  duration_min: 2
  default_window: am_active
  tags: [am, calming, anti-inflammatory]
  applies_when: ["skin_concern == rosacea or barrier_state == damaged"]
  intensity: 0.2
  evidence_section: "Solutions"
  frequency: { type: daily, n: 1 }

- id: skin.retinoid_pm
  title: "Apply retinoid (pea)"
  description: "pea-sized tretinoin 0.05% on DRY skin (wait 15 min after cleanse). avoid eye/lip area. follow with moisturizer after 5 min."
  duration_min: 5
  default_window: pm_active
  tags: [pm, active, retinoid]
  applies_when: ["skin_concern in [acne, pigmentation, texture, maintenance] and barrier_state != damaged"]
  contraindicated_when: ["barrier_state == damaged", "skin_concern == rosacea"]
  intensity: 0.7
  evidence_section: "Retinoids — the foundation"
  cooldown_hours: 24
  frequency: { type: n_per_week, n: 4 }

- id: skin.dermastamp_pm
  title: "Dermastamp face"
  description: "dermastamp 0.25mm depth, 4 passes per zone, on clean dry skin. follow with hyaluronic + moisturizer. NEVER same night as retinoid."
  duration_min: 10
  default_window: pm_active
  tags: [pm, treatment, collagen]
  applies_when: ["skin_concern in [pigmentation, texture] and barrier_state == stable", "dermastamp_owned == true"]
  contraindicated_when: ["barrier_state == damaged", "skin_concern == rosacea"]
  intensity: 0.8
  evidence_section: "Dermastamping"
  cooldown_hours: 72
  frequency: { type: n_per_week, n: 2 }

- id: skin.facial_massage
  title: "Facial massage (30s)"
  description: "upward strokes jaw → temples → forehead. drain downward behind ears. circulation boost. skip on retinoid nights."
  duration_min: 1
  default_window: pm_close
  tags: [pm, circulation]
  applies_when: [always]
  contraindicated_when: []
  intensity: 0.2
  evidence_section: "Facial massage"
  frequency: { type: n_per_week, n: 5 }

- id: skin.hydration_water
  title: "Drink water — 1L target"
  description: "drink 1L water by midday. internal hydration → barrier function."
  duration_min: 1
  default_window: midday
  tags: [internal, hydration]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "Hydration and internal support"
  frequency: { type: daily, n: 1 }

- id: skin.diet_anti_inflammatory
  title: "Skip seed oils + sugar"
  description: "today: avoid seed oils, refined sugar, excess dairy. reduces inflammation that drives flares + pigment."
  duration_min: 1
  default_window: flexible
  tags: [internal, diet, anti-inflammatory]
  applies_when: ["skin_concern in [rosacea, acne, pigmentation]", "diet_open in [yes_full, yes_some]"]
  intensity: 0.3
  evidence_section: "Internal triggers"
  frequency: { type: n_per_week, n: 5 }

- id: skin.zinc_supp
  title: "Take zinc + collagen"
  description: "zinc 15mg + collagen peptides with breakfast. skin repair + tissue support."
  duration_min: 1
  default_window: am_open
  tags: [internal, supplement]
  applies_when: ["skin_concern in [acne, pigmentation]"]
  intensity: 0.1
  evidence_section: "Phase 1 — Repair"
  frequency: { type: daily, n: 1 }

- id: skin.barrier_pause
  title: "Skip actives — barrier rest"
  description: "skip ALL actives today. only cleanse, ceramides, SPF. let barrier recover. critical during repair."
  duration_min: 1
  default_window: flexible
  tags: [pm, barrier, repair]
  applies_when: ["barrier_state == damaged"]
  intensity: 0.0
  evidence_section: "What to STOP during barrier damage"
  frequency: { type: n_per_week, n: 7 }

- id: skin.pillowcase_change
  title: "Change pillowcase"
  description: "fresh pillowcase = no overnight bacteria + oil transfer onto cheeks. silk or freshly-laundered cotton. weekly minimum."
  duration_min: 2
  default_window: midday
  tags: [hygiene, weekly, environment]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "Skin barrier basics"
  frequency: { type: n_per_week, n: 1 }

- id: skin.weekly_exfoliation
  title: "Weekly exfoliation (PHA/AHA)"
  description: "swap PM cleanse for: cleanse → 1 layer mandelic acid 5% (or PHA toner) → moisturize. resurfaces dead cells. NEVER same night as retinoid."
  duration_min: 8
  default_window: pm_active
  tags: [exfoliation, weekly, active]
  applies_when: ["barrier_state == stable", "skin_concern in [acne, pigmentation, texture]"]
  contraindicated_when: ["barrier_state == damaged"]
  intensity: 0.5
  evidence_section: "Active strategy"
  cooldown_hours: 168
  frequency: { type: n_per_week, n: 1 }

- id: skin.hydration_mask
  title: "Hydration mask (15 min)"
  description: "hyaluronic + ceramide overnight mask, OR sheet mask 15 min before bed. weekly barrier reset for dry / irritated skin."
  duration_min: 15
  default_window: pm_active
  tags: [hydration, mask, weekly, repair]
  applies_when: ["skin_concern in [rosacea, maintenance] or skin_type == dry"]
  intensity: 0.2
  evidence_section: "Repair ingredients"
  frequency: { type: n_per_week, n: 1 }

- id: skin.progress_photo
  title: "Photo: face front + sides"
  description: "natural light, no makeup, same angle (front + 45° both sides). compare in 30 days, not daily — skin changes are slow."
  duration_min: 5
  default_window: am_open
  tags: [tracking, progress, biweekly]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Tracking progress"
  frequency: { type: every_n_days, n: 14 }

- id: skin.monthly_review
  title: "Monthly skin review"
  description: "compare photos. better / same / worse? new texture? stubborn spots? if 8+ weeks no change, escalate one variable (active strength, retinoid frequency, derm visit)."
  duration_min: 5
  default_window: midday
  tags: [review, monthly, checkpoint]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Treatment timelines"
  frequency: { type: every_n_days, n: 30 }

- id: skin.derm_consult
  title: "Schedule derm check (6mo)"
  description: "twice a year for active concerns. moles, persistent redness, severe acne all benefit from professional eyes. log Q's beforehand."
  duration_min: 5
  default_window: flexible
  tags: [medical, dermatology, biannual]
  applies_when: ["skin_concern in [acne, rosacea, pigmentation]"]
  intensity: 0.3
  evidence_section: "When to see a derm"
  frequency: { type: every_n_days, n: 180 }
```
