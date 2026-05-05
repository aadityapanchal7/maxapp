---
maxx_id: heightmax
display_name: Height
short_description: Posture, decompression, and perceived-height. No medical or hormone protocols.

schedule_design:
  cadence_days: 14
  am_window: ["wake+0:10", "wake+1:00"]
  pm_window: ["sleep-2:00", "sleep-0:15"]
  daily_task_budget: [2, 5]
  intensity_ramp:
    week_1: [0.0, 0.6]
    week_2: [0.4, 1.0]
  skeleton:
    blocks:
      # Daily mobility / decompression — universal.
      - id: am_mobility
        slot: am_open
        cadence: daily
        tasks: [height.am_mobility]
      - id: pm_decompression
        slot: pm_close
        cadence: daily
        tasks: [height.pm_decompression]
      - id: sleep_window
        slot: pm_close
        cadence: daily
        tasks: [height.sleep_extend]
      # Posture-specific (desk users).
      - id: wall_posture
        slot: am_open
        cadence: daily
        if: "posture_issues == true"
        tasks: [height.wall_posture]
      - id: desk_reset
        slot: midday
        cadence: daily
        if: "posture_issues == true"
        tasks: [height.desk_reset_midday]
      - id: chin_tucks
        slot: midday
        cadence: daily
        if: "posture_issues == true"
        tasks: [height.chin_tucks]
      # Decompression hang (skip if spine_pain).
      - id: dead_hang
        slot: pm_active
        cadence: n_per_week=4
        if: "!spine_pain"
        tasks: [height.dead_hang]
      # Strength / posture — only if user trains.
      - id: face_pulls
        slot: pm_active
        cadence: n_per_week=3
        if: "training_status in [yes_regular, yes_some]"
        tasks: [height.face_pulls]
      - id: glute_bridge
        slot: am_active
        cadence: n_per_week=4
        tasks: [height.glute_bridge]
      - id: foam_roll
        slot: pm_active
        cadence: n_per_week=3
        tasks: [height.foam_roll_back]
      # Teen-only growth foundations.
      - id: protein_check
        slot: midday
        cadence: daily
        if: "age < 22"
        tasks: [height.protein_check]
      - id: sunlight_am
        slot: am_open
        cadence: daily
        if: "age < 22"
        tasks: [height.sunlight_am]
      # Perceived-height track.
      - id: outfit_check
        slot: am_active
        cadence: n_per_week=3
        if: "heightmax_focus in [perceived, all]"
        tasks: [height.outfit_check]
      - id: shoe_audit
        slot: am_open
        cadence: n_per_week=3
        if: "heightmax_focus in [perceived, all]"
        tasks: [height.shoe_audit]
      - id: posing_practice
        slot: flexible
        cadence: n_per_week=2
        if: "heightmax_focus in [perceived, all]"
        tasks: [height.posing_practice]
      # --- Density layer ---
      - id: morning_height_log
        slot: am_open
        cadence: n_per_week=2
        tasks: [height.morning_log]
      - id: progress_photo_height
        slot: am_open
        cadence: weekly_on=sunday
        tasks: [height.progress_photo]
      - id: monthly_review_height
        slot: midday
        cadence: monthly_on=1
        tasks: [height.monthly_review]
      - id: inversion_session
        slot: pm_close
        cadence: n_per_week=4
        if: "equipment_access in [inversion_table, full_setup] and spine_health == none"
        tasks: [height.inversion]
      - id: calcium_check
        slot: midday
        cadence: daily
        if: "age < 22"
        tasks: [height.calcium_check]

required_fields:
  - id: age
    question: "How old are you?"
    type: int
    required: true
    why: "Under-18 → growth foundations matter more (sleep, calories, posture). Adult → posture + perceived-height focus."

  - id: heightmax_focus
    question: "Which of these is your main goal?"
    type: enum
    options:
      posture: "Fix posture / stand taller"
      retention: "Reduce daily height loss (decompression, mobility)"
      perceived: "Look taller (fashion, shoes, presence)"
      growth: "Maximize natural growth (under 22)"
      all: "All of the above"
    required: true
    why: "Selects which of the three tracks (posture, retention, perceived) get scheduled."

  - id: posture_issues
    question: "Do you sit at a desk / on a phone for most of the day?"
    type: yes_no
    required: true
    why: "Yes → adds desk-reset task and forward-head correction emphasis."

  - id: training_status
    question: "Do you currently strength train?"
    type: enum
    options:
      yes_regular: "Yes, 3+ times a week"
      yes_some: "Sometimes, 1–2 times a week"
      "no": "No"
    required: true
    why: "Strength training builds the frame that holds posture. Gates frame-building tasks."

  - id: desk_hours
    question: "How many hours a day do you spend at a desk or on your phone?"
    type: int
    min: 0
    max: 16
    step: 1
    default: 8
    unit: "hr"
    required: true
    why: "Desk-bound users need 2× midday posture resets + forward-head correction at AM and PM. Light desk users get 1 reset. None can skip the reset chain."

  - id: sleep_hours
    question: "Average hours of sleep per night?"
    type: int
    min: 4
    max: 12
    step: 1
    default: 7
    unit: "hr"
    required: true
    why: "For users under 22, sleep extension matters more than any decompression — growth hormone peaks in deep sleep. Under 7hr triggers nightly wind-down + screen cutoff cues."

  - id: spine_health
    question: "Any back, neck, or spine pain you live with?"
    type: enum
    options:
      none: "No issues"
      occasional: "Occasional stiffness or soreness"
      chronic: "Chronic — see a doctor regularly"
      diagnosed: "Diagnosed condition (herniated disc, scoliosis, etc.)"
    required: true
    why: "Chronic / diagnosed → ONLY gentle decompression + doctor consult reminder. Strip dead hangs, inversions, aggressive stretches. None → full protocol."

  - id: equipment_access
    question: "What do you have access to for decompression work?"
    type: enum
    options:
      none: "Nothing — bodyweight only"
      pullup_bar: "Pull-up bar / doorway bar"
      inversion_table: "Inversion table"
      full_setup: "Bar + inversion + foam roller / mobility tools"
    required: true
    why: "Decides which decompression tasks fire. None = lying decompression only. Inversion = full hang + inversion. Full = the works."

optional_context:
  - id: height_current
    description: "Current height — for perceived-height baseline (not promised growth)"
  - id: outfit_concerns
    description: "User open to fashion advice for proportions"
  - id: shoe_style_pref
    description: "Boots/sneakers/dress — biases shoe recommendations"
  - id: cardiovascular_concerns
    description: "Any heart/BP issues — gates inversion table tasks"
  - id: body_fat_high
    description: "User wants leanmaxx → adds body-comp tasks"
  - id: morning_loss_amt
    description: "How much height user loses through the day (cm) — drives decompression cadence"
  - id: nutrition_priority
    description: "Open to dietary tweaks for growth (protein, calcium, vitamin D)"

prompt_modifiers:
  - id: under_18_growth
    if: "age < 18"
    then: "Growth-foundations track is PRIMARY: sleep 8–10 hr emphasis, calorie/protein cue, sunlight exposure prompt, posture work. Frame all language as 'supports natural growth potential' — never promise height."
  - id: adult_posture_perceived
    if: "age >= 22"
    then: "Growth track INACTIVE (growth plates closed). Focus posture + retention + perceived. No claims about height growth. Reference 'supports posture / retention / perceived height'."
  - id: heavy_desk
    if: "posture_issues == true"
    then: "Add midday desk-reset task daily. Forward-head correction is week-1 priority. Wall posture drill 2×/day."
  - id: cardiovascular_caution
    if: "cardiovascular_concerns == true"
    then: "EXCLUDE inversion-table tasks. Substitute lying decompression. Add note: 'check with doctor before inversion exercises'."
  - id: spine_pain_caution
    if: "spine_pain == true"
    then: "Use ONLY gentle decompression (lying knee-to-chest, doorway hang ≤30s). Skip dead hangs and aggressive stretches. Recommend doctor consult."
  - id: chronic_spine_doctor_only
    if: "spine_health in [chronic, diagnosed]"
    then: "DOCTOR-ONLY DECOMPRESSION. Schedule lying knee-to-chest 2×/day max. Skip ALL hangs, inversions, aggressive stretches. Add weekly doctor / PT check-in reminder. Frame as 'support, not treatment'."
  - id: heavy_desk_double_reset
    if: "desk_hours >= 8"
    then: "TWO midday posture resets (mid-morning + mid-afternoon). Add forward-head correction every 90 min as standalone task. Wall posture drill 3×/day. Eye-line check (monitor at eye level) reminder weekly."
  - id: low_sleep_under_22_critical
    if: "sleep_hours < 7 and age < 22"
    then: "SLEEP-FIRST PROTOCOL. Bedtime cue 90 min before target sleep. Screen cutoff 60 min before bed. No caffeine after 2pm reminder. Frame: 'growth hormone peaks in first 2 hr of deep sleep — under 7 hr cuts that window in half'."
  - id: low_sleep_adult
    if: "sleep_hours < 7 and age >= 22"
    then: "Add bedtime wind-down cue. Frame around recovery + posture muscle repair, not growth. Skip the under-22 framing."
  - id: equipment_none_lying_only
    if: "equipment_access == none"
    then: "DECOMPRESSION TASKS: lying knee-to-chest, cat-cow, supine spinal twist, child's pose. ZERO standing hang or inversion tasks. Frame as 'gravity-neutral release'."
  - id: equipment_pullup_bar_hangs
    if: "equipment_access in [pullup_bar, full_setup] and spine_health == none"
    then: "Add dead hang 60s 2×/day (AM after wake, PM before bed). Progress to weighted hangs after week 4 if comfortable. NEVER same day as heavy axial leg work — at least 6 hr gap."
  - id: equipment_inversion_full
    if: "equipment_access in [inversion_table, full_setup] and spine_health == none and cardiovascular_concerns != true"
    then: "Inversion table 5 min PM, 4×/wk. Start at 30° angle week 1, progress to 60° by week 4. Always supervised first sessions. Skip if dizziness or BP issues."
---

# What heightmaxxing actually means

Heightmaxxing covers a few different goals that get conflated:

- **Natural growth potential** (teens only): supporting growth via sleep, nutrition, training.
- **Posture correction**: undoing forward head, rounded shoulders, anterior pelvic tilt that reduce visible height.
- **Daily height retention**: reducing the spinal disc compression that makes everyone shorter by evening.
- **Perceived height**: using clothing, shoes, body composition, and presence to look taller.
- **Cosmetic height boosts**: insoles, thicker socks, boot stacking.

This module covers all of the above. It does NOT cover medical interventions — hormones, peptides, aromatase inhibitors, growth hormone, limb lengthening surgery — those require licensed medical supervision and are out of scope.

## Real height vs perceived height

- **Real (skeletal) height**: mostly genetics + puberty. Cannot be increased after growth plate closure outside of surgery.
- **Measured height**: affected by posture and spinal compression — varies by 1–3 cm through the day.
- **Perceived height**: how tall you look. Affected by shoes, clothing, body fat, proportions, hair, confidence, posing, camera angle.

Most "height gains" in this module come from posture + retention + perceived height. Real growth claims belong in adolescence only and even then only through foundations (sleep, nutrition, training).

## Growth plates

Growth plates (epiphyseal plates) are cartilage areas at the ends of long bones where length growth happens. They close near the end of puberty (typically 14–18 in females, 16–21 in males, varies). After closure, length growth stops.

Most adult-height claims online are exaggerated. Self-directed hormone manipulation to "reopen plates" is dangerous and medical-only.

## Safe vs risky heightmaxxing

- **Safe**: sleep, nutrition, posture, exercise, fashion, shoes.
- **Caution**: supplements (most are unnecessary unless deficient).
- **Medical-only**: growth hormone, peptides, aromatase inhibitors, limb lengthening.
- **Never in app protocols**: dosages, injection instructions, drug sourcing, hormone stacks.

# Natural growth foundations

## Sleep

Growth and recovery happen during sleep. Poor sleep hurts recovery, posture, hormones, and energy.

- Consistent bedtime, dark room, no phone before bed, morning sunlight.
- 8–10 hours for teens, 7–9 for adults.
- Avoid: 4–6 hr sleep, irregular schedule, late caffeine, doomscrolling in bed.

## Nutrition

Eating to reach your genetic potential means enough calories, enough protein, calcium-rich foods, vitamin D, omega-3 / fish, fruits and vegetables.

Many skinny teens under-eat without realizing. Add meals, milk, eggs, rice, meat, fish, yogurt, nuts. Goal: support growth and muscle, not just gain fat.

Bone-support foods: dairy, fish, eggs, leafy greens, meat, beans, fortified foods.

Don't claim milk "makes you taller" — say it supports growth potential when diet is lacking. Avoid raw milk recommendations (safety/legal).

## Training

Strength training builds posture, frame, confidence. Strengthens back, glutes, legs, core. Helps avoid slouched posture.

Sports (basketball, swimming, sprinting, lifting) don't magically lengthen bones. They improve posture, body composition, and perceived height.

Frame building targets: shoulders, upper back, neck, core, glutes, legs.

# Posture as "free height"

Bad posture makes you look shorter. Forward head posture, rounded shoulders, anterior pelvic tilt all reduce visible height. Fixing posture can improve both measured and perceived height.

## Forward head fix

Signs: head sticks forward, neck tightness, hunched at computer.
Fixes: chin tucks, wall posture drill, upper back strengthening, screen at eye level.

## Rounded shoulder fix

Signs: shoulders roll forward, chest looks collapsed.
Fixes: face pulls, band pull-aparts, rows, chest stretching.

## Anterior pelvic tilt fix

Signs: lower back arch, belly sticks out even when lean, tight hip flexors.
Fixes: hip flexor stretches, glute bridges, planks, dead bugs, hamstring work.

## Daily posture routine

5 min morning mobility, 5 min desk reset, 5 min night stretching. Total 15 min — anything more rarely gets done.

# Spinal decompression and height retention

People are usually taller in the morning. Spinal discs compress through the day. Goal: reduce excessive compression, improve posture.

## Hanging

Temporarily decompresses the spine. Helps tightness and posture. Does NOT permanently lengthen bones. Frame as "height retention," "posture support," "temporary decompression."

## Stretching

Best targets: hip flexors, hamstrings, chest, lats, upper back, calves.

Stack: cat-cow, cobra, child's pose, hip flexor, hamstring, lat stretch.

## Inversion tables

Temporary decompression. More useful for back tightness than actual height. **Caution**: blood pressure, eye pressure, spine issues — check with doctor first.

## Joint support supplements

Glucosamine, chondroitin, MSM. Frame as "joint and disc support" — never promise height growth. "May support joint comfort and height retention."

# Fraudmaxxing — cosmetic height boosts

Cosmetic ways to appear taller. Not real skeletal growth. Best used subtly — goal is to look natural.

## Insoles

- 0.5–1 cm: most natural. Works in sneakers and casual shoes.
- 1–2 cm: noticeable boost. Needs deeper shoes.
- 2–4 cm: risk of looking unnatural. Changes walking mechanics. Best only with boots or high-tops.

Mistakes: going too high, wearing in low-profile shoes, limping, taking shoes off and instantly losing several cm.

## Sock-in-shoe / heel padding

Thick socks: small boost, more comfortable than huge lifts. Double socks: slight extra height; sweating risk. Heel padding: small heel elevation; must keep shoe stable.

## Bootmaxxing

- Chelsea boots: natural lift, stylish, can hide insoles.
- Combat boots: strong lift, masculine, casual/streetwear.
- Workwear boots: rugged, natural thick sole, less suspicious than obvious lifts.
- Boot + insole stack: most powerful combo. Stay natural; don't overstack.

## Shoe selection

Best for height: boots, Air Max-style sneakers, platform sneakers, chunky soles, high-tops.

Worst for height: flat Converse, thin-soled Vans, barefoot shoes, slides, thin-soled dress shoes.

Sneaky height: thicker midsoles, darker colors, high-top designs, pants covering shoe opening.

# Fashion heightmaxxing

Looking taller is about proportions. Longer leg line = taller appearance. Shorter visual torso = taller silhouette.

## Pants

- High-waisted: makes legs look longer. Best with tucked or cropped tops.
- Slim/straight fit: cleaner vertical line, no stacking/bunching.
- Avoid baggy breaks at the ankle (shortens leg visually).

## Shirts

- Cropped/shorter tops: shorter torso, longer legs.
- Tucked shirts: higher waistline, smart casual.
- Avoid long oversized shirts (shrinks frame, shortens leg line).

## Colors

- Monochrome fits: one color family creates a longer visual line.
- Low contrast shoes/pants: matching colors elongate legs.

## Outerwear

Cropped jackets, bomber jackets, short leather jackets. Avoid long coats that swallow your frame.

# Body composition

## Leanness

Lower body fat → smaller waist → shoulders look wider → leaner frame looks taller. Avoid the "compressed" look (high body fat, bad posture, baggy clothes, flat shoes, weak upper back).

## Shoulder-to-waist ratio

Train shoulders and back. Keep waist lean. Athletic V-taper looks taller.

# Hair and grooming

Hair can add perceived height — must still fit the face. Don't make hair absurdly tall just for height.

Best: textured fringe with volume, quiff, messy volume, medium textured top, taper/fade sides to elongate face.

Avoid: flat hair, bowl cuts, extremely wide hair, cuts that round the head.

Sharp grooming + facial hair balance + slim face = taller appearance.

# Social and photo heightmaxxing

## Camera angles

Low angle → look taller. Wide-angle distortion hurts proportions. Full-body photos should show longer leg line.

## Posing

Stand straight. One foot slightly forward. Shoulders back. Don't slouch next to people.

## Group photos

Stand slightly closer to the camera. Avoid being placed next to much taller people. Wear darker, cleaner vertical fits.

## Walking and presence

Upright posture, long relaxed stride, don't look down constantly. Confidence changes perceived height.

# Supplements (safe baseline)

- Vitamin D if deficient
- Calcium if diet is low
- Magnesium
- Zinc if deficient
- Omega-3
- Basic multivitamin if diet is poor

Joint support: glucosamine, chondroitin, collagen — frame as joint/posture support, not guaranteed height.

## Claims to avoid

NEVER say:
- "This will make you taller"
- "Guaranteed height increase"
- "Open your growth plates"
- "Reopen closed plates"
- "Replace medical care"
- "Use this hormone stack"

Say instead:
- "May support posture"
- "May help with height retention"
- "Can improve perceived height"
- "Supports general growth foundations during adolescence"
- "Talk to a licensed doctor for medical concerns"

# Medical boundary

This module does NOT include protocols for: growth hormone, peptides (CJC-1295, GHRP-2, GHRP-6, hexarelin, IGF-1, MK-677), aromatase inhibitors (Aromasin, Arimidex, Letrozole), DHT compounds, insulin manipulation, NSAIDs for bone growth, or limb lengthening surgery.

These are medical-only and require licensed supervision. Self-administration can cause permanent harm to growth, puberty, fertility, mood, bones, heart, and metabolism. The app discusses these only as education in a separate module — never as recommendations.

When to see a doctor: very delayed puberty, sudden growth stopping early, severe short stature concern, hormonal disorder suspicion, spine/posture pain, eating disorder signs.

```yaml task_catalog
- id: height.am_mobility
  title: "AM mobility (5 min)"
  description: "cat-cow x10, cobra x5, doorway lat stretch 30s/side. wakes the spine without aggressive stretch."
  duration_min: 5
  default_window: am_open
  tags: [posture, mobility, am]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Daily posture routine"
  frequency: { type: daily, n: 1 }

- id: height.desk_reset_midday
  title: "Desk reset (5 min)"
  description: "stand up, chin tucks x10, chest opener at door 30s, shoulder rolls. resets posture from sitting."
  duration_min: 5
  default_window: midday
  tags: [posture, desk, midday]
  applies_when: ["posture_issues == true"]
  intensity: 0.2
  evidence_section: "Forward head fix"
  frequency: { type: daily, n: 1 }

- id: height.pm_decompression
  title: "PM decompression (5 min)"
  description: "child's pose 60s, hip flexor stretch 30s/side, hamstring stretch 30s/side, lying knee-to-chest 30s."
  duration_min: 5
  default_window: pm_close
  tags: [posture, decompression, pm]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Stretching"
  frequency: { type: daily, n: 1 }

- id: height.dead_hang
  title: "Dead hang (60s)"
  description: "hang from a bar (assisted ok), arms straight, relaxed grip. temporary spinal decompression."
  duration_min: 2
  default_window: pm_active
  tags: [decompression]
  applies_when: [always]
  contraindicated_when: ["spine_pain == true"]
  intensity: 0.4
  evidence_section: "Hanging"
  frequency: { type: n_per_week, n: 4 }

- id: height.wall_posture
  title: "Wall posture drill"
  description: "back against wall: heels, butt, shoulders, head all touching. chin tucked. 60 seconds."
  duration_min: 1
  default_window: am_open
  tags: [posture]
  applies_when: ["posture_issues == true"]
  intensity: 0.1
  evidence_section: "Forward head fix"
  frequency: { type: daily, n: 1 }

- id: height.face_pulls
  title: "Face pulls 3×12"
  description: "band or cable face pulls, 3 sets x 12. fixes rounded shoulders. light weight, controlled."
  duration_min: 5
  default_window: pm_active
  tags: [posture, strength]
  applies_when: ["training_status in [yes_regular, yes_some]"]
  intensity: 0.4
  evidence_section: "Rounded shoulder fix"
  frequency: { type: n_per_week, n: 3 }

- id: height.glute_bridge
  title: "Glute bridge 3×15"
  description: "lying glute bridge, 3 sets x 15, 1-second pause at top. fixes anterior pelvic tilt."
  duration_min: 5
  default_window: am_active
  tags: [posture, strength]
  applies_when: [always]
  intensity: 0.3
  evidence_section: "Anterior pelvic tilt fix"
  frequency: { type: n_per_week, n: 4 }

- id: height.sleep_extend
  title: "Check sleep window"
  description: "lights out by [sleep time]. teens: 8–10 hr target. adults: 7–9. consistency > duration."
  duration_min: 1
  default_window: pm_close
  tags: [growth, foundation]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "Sleep"
  frequency: { type: daily, n: 1 }

- id: height.protein_check
  title: "Hit protein (~1g/lb)"
  description: "today: aim 1g protein per lb bodyweight. eggs, meat, fish, dairy, beans. supports growth + frame."
  duration_min: 1
  default_window: midday
  tags: [growth, nutrition]
  applies_when: ["age < 22"]
  intensity: 0.2
  evidence_section: "Nutrition"
  frequency: { type: daily, n: 1 }

- id: height.sunlight_am
  title: "10 min AM sunlight"
  description: "10 min of morning sunlight, eyes open (no sunglasses), no window. circadian + vitamin D."
  duration_min: 10
  default_window: am_open
  tags: [growth, foundation]
  applies_when: ["age < 22"]
  intensity: 0.1
  evidence_section: "Sleep"
  frequency: { type: daily, n: 1 }

- id: height.outfit_check
  title: "Outfit proportions check"
  description: "high-waist or tucked, slim/straight pants, low-contrast shoes/pants, no baggy ankle break. monochrome bonus."
  duration_min: 3
  default_window: am_active
  tags: [perceived, fashion]
  applies_when: ["heightmax_focus in [perceived, all]"]
  intensity: 0.1
  evidence_section: "Fashion heightmaxxing"
  frequency: { type: n_per_week, n: 3 }

- id: height.shoe_audit
  title: "Rotate shoes (weekly)"
  description: "wear thicker-soled shoe today (boot, air max, platform sneaker). avoid flat slides/converse."
  duration_min: 1
  default_window: am_open
  tags: [perceived, fashion]
  applies_when: ["heightmax_focus in [perceived, all]"]
  intensity: 0.1
  evidence_section: "Shoe selection"
  frequency: { type: n_per_week, n: 3 }

- id: height.posing_practice
  title: "Mirror posture check"
  description: "shoulders back, chin slightly down, one foot forward. confident upright stance for 30s."
  duration_min: 1
  default_window: flexible
  tags: [perceived, presence]
  applies_when: ["heightmax_focus in [perceived, all]"]
  intensity: 0.1
  evidence_section: "Posing"
  frequency: { type: n_per_week, n: 2 }

- id: height.chin_tucks
  title: "Chin tucks ×15"
  description: "sit/stand straight, retract chin (double-chin posture) x 15. fixes forward head."
  duration_min: 1
  default_window: midday
  tags: [posture]
  applies_when: ["posture_issues == true"]
  intensity: 0.1
  evidence_section: "Forward head fix"
  frequency: { type: daily, n: 2 }

- id: height.foam_roll_back
  title: "Foam-roll upper back"
  description: "foam roller across upper back, 60s. opens chest, fixes rounded shoulders."
  duration_min: 3
  default_window: pm_active
  tags: [mobility, posture]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Rounded shoulder fix"
  frequency: { type: n_per_week, n: 3 }

- id: height.morning_log
  title: "Log AM height"
  description: "measure first thing AM (no shoes, against wall, marker on top of head). morning is your TRUE height — gravity hasn't compressed yet. log + compare bi-weekly."
  duration_min: 3
  default_window: am_open
  tags: [tracking, measurement, biweekly]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "Measuring height"
  frequency: { type: n_per_week, n: 2 }

- id: height.progress_photo
  title: "Photo: full-body posture"
  description: "front + side, neutral standing. compare in 30 days for posture changes (head over shoulders, chest open). under 22 → also tracks growth."
  duration_min: 5
  default_window: am_open
  tags: [tracking, progress, biweekly]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Tracking progress"
  frequency: { type: every_n_days, n: 14 }

- id: height.monthly_review
  title: "Monthly height review"
  description: "compare AM measurements + photos. 0.5cm taller (under 22 = real growth, adult = decompression win). posture clearly better? if no change in 90 days, audit consistency."
  duration_min: 5
  default_window: midday
  tags: [review, monthly, checkpoint]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Treatment timelines"
  frequency: { type: every_n_days, n: 30 }

- id: height.inversion
  title: "Inversion table (5 min)"
  description: "5 min on inversion table at 30° (week 1) → 60° (week 4). decompresses spine, reverses daily compression. NEVER if dizzy or BP issues."
  duration_min: 5
  default_window: pm_close
  tags: [decompression, equipment, evening]
  applies_when: ["equipment_access in [inversion_table, full_setup]"]
  contraindicated_when: ["spine_health in [chronic, diagnosed]", "cardiovascular_concerns == true"]
  intensity: 0.5
  evidence_section: "Decompression"
  cooldown_hours: 18
  frequency: { type: n_per_week, n: 4 }

- id: height.calcium_check
  title: "Calcium-rich meal"
  description: "Greek yogurt, sardines, leafy greens, fortified milk. for under-22 — building bones now. one calcium-loaded meal/day."
  duration_min: 5
  default_window: midday
  tags: [nutrition, calcium, growth]
  applies_when: ["age < 22"]
  intensity: 0.2
  evidence_section: "Bone health"
  frequency: { type: daily, n: 1 }
```
