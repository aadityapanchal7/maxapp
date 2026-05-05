---
maxx_id: bonemax
display_name: Bone
short_description: Mewing, jaw posture, masseter training, and bone-support nutrition for facial structure.

schedule_design:
  cadence_days: 14
  am_window: ["wake+0:00", "wake+1:00"]
  pm_window: ["sleep-1:30", "sleep-0:15"]
  daily_task_budget: [3, 7]
  intensity_ramp:
    week_1: [0.0, 0.5]
    week_2: [0.3, 1.0]
  skeleton:
    blocks:
      # --- Mewing — 3/day backbone, every day ---
      - id: mewing_am
        slot: am_open
        cadence: daily
        tasks: [bone.mewing_am]
      - id: mewing_midday
        slot: midday
        cadence: daily
        tasks: [bone.mewing_midday]
      - id: mewing_night
        slot: pm_close
        cadence: daily
        tasks: [bone.mewing_night]
      # --- Masseter — TMJ-safe ramp handled by prompt_modifiers ---
      - id: masseter_session
        slot: am_active
        cadence: daily
        if: "tmj_history != true"
        tasks: [bone.masseter]
      - id: masseter_ramp
        slot: am_active
        cadence: n_per_week=3
        if: "tmj_history == true"
        tasks: [bone.masseter_ramp]
      # --- Fascia / lymph ---
      - id: fascia_am
        slot: am_open
        cadence: daily
        tasks: [bone.fascia_am]
      - id: fascia_pm
        slot: pm_close
        cadence: n_per_week=4
        tasks: [bone.fascia_pm]
      # --- Nasal breathing ---
      - id: nasal_check
        slot: midday
        cadence: daily
        tasks: [bone.nasal_check]
      - id: nasal_check_extra
        slot: pm_active
        cadence: daily
        if: "heavy_screen_time == true or mouth_breather == true"
        tasks: [bone.nasal_check]
      # --- Neck training — workout-day-coupled ---
      - id: neck_workout_heavy
        slot: pm_active
        cadence: n_per_week=4
        if: "workout_frequency == heavy"
        tasks: [bone.neck_workout]
      - id: neck_workout_moderate
        slot: pm_active
        cadence: n_per_week=3
        if: "workout_frequency == moderate"
        tasks: [bone.neck_workout]
      - id: neck_light
        slot: pm_active
        cadence: n_per_week=2
        if: "workout_frequency == light"
        tasks: [bone.neck_workout]
      - id: neck_solo
        slot: pm_active
        cadence: n_per_week=1
        if: "workout_frequency == none"
        tasks: [bone.neck_solo]
      # --- Chin tucks bundle into midday on non-workout days; not_with_same_day prevents double-up ---
      - id: chin_tucks
        slot: midday
        cadence: n_per_week=4
        if: "workout_frequency in [none, light]"
        not_with_same_day: [bone.neck_workout, bone.neck_solo]
        tasks: [bone.chin_tucks]
      # --- Daily symmetry / posture micro-check ---
      - id: symmetry_check
        slot: flexible
        cadence: daily
        tasks: [bone.symmetry_check]
      # --- Bone-support nutrition (gated on opt-in) ---
      - id: nutrition_stack_am
        slot: am_open
        cadence: daily
        if: "nutrition_stack_open == true"
        tasks: [bone.vitd_k2]
      - id: nutrition_stack_pm
        slot: pm_close
        cadence: daily
        if: "nutrition_stack_open == true"
        tasks: [bone.magnesium_pm]

required_fields:
  - id: workout_frequency
    question: "How many days per week do you usually work out?"
    type: enum
    options:
      none: "0 — I'm not training right now"
      light: "1-2 days a week"
      moderate: "3-4 days a week"
      heavy: "5+ days a week"
    required: true
    why: "Neck training piggybacks on workout days. Determines how often to schedule the full neck protocol vs chin-tuck-only days."

  - id: tmj_history
    question: "Have you ever had TMJ issues, jaw pain, or clicking?"
    type: yes_no
    required: true
    why: "If yes — strip masseter work from week 1, ramp slowly, watch for flares. If no — start the full protocol from day 1."

  - id: mastic_gum_regular
    question: "Do you already chew mastic gum (or another hard gum) regularly?"
    type: yes_no
    required: true
    why: "Decides masseter ramp pace. Already-conditioned jaws can start at the standard 1×/day; new jaws ramp from 5 min every other day."

  - id: heavy_screen_time
    question: "Do you spend most of your day on a computer or phone?"
    type: yes_no
    required: true
    why: "Heavy screen time means forward-head posture all day — schedule adds extra mid-day mewing reset + nasal-breathing checks."

  - id: mewing_experience
    question: "How familiar are you with mewing?"
    type: enum
    options:
      none: "Never tried it"
      heard_of: "Heard of it, never properly done it"
      occasional: "I do it sometimes"
      regular: "Daily practice for months+"
    required: true
    why: "Decides ramp pace + technique-emphasis copy. None → start with form check + basic morning hold; regular → skip basics, layer hard-mewing cues."

  - id: sleep_position
    question: "How do you sleep, mostly?"
    type: enum
    options:
      back: "Back — face up"
      side: "Side"
      stomach: "Stomach — face down"
      mixed: "Mixed / depends"
    required: true
    why: "Stomach sleeping wrecks tongue posture and pushes the jaw forward asymmetrically. Stomach → bedtime cue includes side-sleep transition. Back → ideal, no extra cue. Side → asymmetric load reminder weekly."

  - id: nasal_breather
    question: "Do you breathe through your nose during the day?"
    type: enum
    options:
      always: "Always — nose only"
      mostly: "Mostly — sometimes mouth"
      mouth: "Often through my mouth"
      unsure: "Honestly not sure"
    required: true
    why: "Mouth breathing is the #1 enemy of jaw posture. Mouth → nasal check 3×/day + lip-tape suggestion at bedtime. Mostly → 2×/day. Always → 1×/day form check."

  - id: jaw_priority
    question: "What matters most to you for your jaw?"
    type: enum
    options:
      definition: "Sharper definition / lower body fat at jawline"
      mass: "Bigger masseter / fuller lower face"
      structure: "Overall facial structure / posture"
      symmetry: "Even left/right balance"
    required: true
    why: "Drives masseter ramp aggressiveness + which symmetry-check tips rotate. Definition → cardio + chewing gum focus. Mass → harder masseter + creatine optional. Structure → mewing + posture priority. Symmetry → balanced-bite + asymmetric chewing avoidance."

  - id: nutrition_stack_open
    question: "Open to a bone-support supplement stack (vitamin D3 + K2 + magnesium)?"
    type: yes_no
    required: true
    why: "Gates the nutrition tasks. If yes → AM D3+K2 with food + PM magnesium. If no → skip those notification slots entirely."

optional_context:
  - id: age
    description: "User age (from onboarding) — under-22 has more growth-plate plasticity for jaw posture changes."
  - id: sleep_position
    description: "Back / side / stomach — biases the bedtime mewing reset and pillow advice."
  - id: mouth_breather
    description: "Self-reported mouth breathing during the day or while sleeping — adds nasal-breathing reminders."
  - id: jaw_appearance_goal
    description: "What the user wants to change (jawline definition, masseter size, chin projection) — biases reminder copy."
  - id: nutrition_stack_open
    description: "Whether the user is open to a bone-support supplement stack (vitamin D / K2 / magnesium) — gates the nutrition block."
  - id: current_habits
    description: "Already mewing? chewing gum? training neck? — informs ramp pace per module."
  - id: meal_chewing_reminders_opt_in
    description: "User opted into meal-time chewing posture cues — gates per-meal reminders."
  - id: hard_mewing_opt_in
    description: "User wants advanced mewing (active suction holds vs passive) — biases reminder cadence."

prompt_modifiers:
  - id: tmj_caution
    if: "tmj_history == true"
    then: "PHASE: TMJ-SAFE RAMP. NO masseter / mastic gum in week 1. Week 2: introduce 5 min every other day. Week 3+: standard cadence only if no flare. Add 'jaw check-in' midday: any clicking, pain, fatigue? — log and back off if yes."
  - id: workout_neck_train
    if: "workout_frequency in [moderate, heavy]"
    then: "Append neck training (4-way harness or banded) for 5-8 min, 15 min after workout end on training days. On non-training days bundle chin tucks into the midday mewing reset (not a separate notification)."
  - id: light_workout_neck
    if: "workout_frequency == light"
    then: "Neck training 2× per week regardless of training days — pick fixed weekdays at PM time. Chin tucks bundled into midday mewing on the other 5 days."
  - id: no_workout_neck
    if: "workout_frequency == none"
    then: "Neck protocol = chin tucks bundled into midday mewing daily, plus 1 dedicated banded neck session per week at user-set time. No harness recommended (no anchor)."
  - id: mastic_advanced
    if: "mastic_gum_regular == true and tmj_history == false"
    then: "Start at standard cadence: mastic 1× daily at user-chosen time (default wake + 2h). Single piece, 10-15 min chew, balanced left-right. Rest 1 day per week."
  - id: mastic_beginner
    if: "mastic_gum_regular == false and tmj_history == false"
    then: "RAMP. Week 1: half-piece, every other day, 5 min max. Week 2: full piece, every other day, 8-10 min. Week 3+: 1×/day at standard cadence. Rotate sides each session."
  - id: heavy_screen_extra_resets
    if: "heavy_screen_time == true"
    then: "Add a second mid-afternoon mewing + nasal-breathing reset at midday + 2h. Append screen-forward-head cue to the standard midday reset copy. Cap nasal-breathing reminders at 2/day."
  - id: mouth_breather_focus
    if: "mouth_breather == true"
    then: "Nasal-breathing checks 2×/day (midday + bed − 60 min). Bedtime: explicit lip-tape suggestion if user opted in; otherwise 'lips sealed, nasal only' nightly cue. Add a weekly check on snoring / mouth-dry mornings."
  - id: under_22_oral_posture_priority
    if: "age < 22"
    then: "Frame mewing as 'oral posture for facial development' — bone is still adapting. Mewing morning + midday + night every day, no skip days. Hard-mewing cue once a week to reinforce active form."
  - id: adult_maintenance_framing
    if: "age >= 25"
    then: "Frame mewing as 'maintenance + drainage / posture' — fully-fused bone, gains are slower. Same daily cadence but mention realistic timeline (6-12 months for visible jaw posture change). No claims about bone remodeling."
  - id: mewing_none_form_check
    if: "mewing_experience == none"
    then: "WEEK 1: form-check focus. Daily 30s morning hold + mirror check (back third of tongue on palate, lips sealed, teeth touching). No midday or night cue yet. Week 2 add midday. Week 3 add night. Build the habit before stacking."
  - id: mewing_regular_advanced
    if: "mewing_experience == regular"
    then: "Skip basic form copy. Add hard-mewing cue (active suction holds 60s) 1×/day in addition to the standard 3-set. Add weekly self-progress photo (jawline angle, side profile)."
  - id: stomach_sleep_correction
    if: "sleep_position == stomach"
    then: "STOMACH SLEEPING: counterproductive. Add bedtime cue 'try side or back tonight' + pillow setup tips (body pillow to anchor side position). After 2 weeks if still stomach, add weekly transition reminder. Frame: 'face plants in pillow undo your daily mewing'."
  - id: side_sleep_alternation
    if: "sleep_position == side"
    then: "SIDE SLEEPING: asymmetric pressure. Add weekly reminder to alternate sides (note which side you woke up on). Recommend high-loft pillow for shoulder support so jaw doesn't compress."
  - id: mouth_breather_lip_tape
    if: "nasal_breather == mouth"
    then: "MOUTH BREATHING: critical fix. 3×/day nasal-only practice (5 min each: AM, midday, PM). At bedtime, suggest lip tape (medical paper tape, vertical strip, NOT across full mouth). Add weekly snore / dry-mouth check-in. Refer to ENT if persistent."
  - id: nasal_mostly_check
    if: "nasal_breather == mostly"
    then: "Nasal breathing 2×/day check. Frame: 'when you catch yourself mouth-breathing, close lips, push tongue up, breathe slow through nose 3x'. No lip-tape suggestion yet."
  - id: jaw_definition_priority
    if: "jaw_priority == definition"
    then: "DEFINITION FOCUS: emphasize body-fat reduction (link to FitMax if active). Add daily 'jawline reveal' check — front-camera photo at consistent angle / lighting. Lower masseter intensity (avoid bulking the muscle); skip creatine for jaw."
  - id: jaw_mass_priority
    if: "jaw_priority == mass"
    then: "MASS FOCUS: aggressive masseter ramp. Mastic 2× daily (AM + PM) once past TMJ check. Add jaw-specific creatine cue (5g/day). Weekly progress photo at chin / side angle."
  - id: jaw_symmetry_priority
    if: "jaw_priority == symmetry"
    then: "SYMMETRY FOCUS: alternate chewing sides at every meal (cue: AM brush reminder + meal-time mid-chew prompt). Avoid sleeping always on same side. Add monthly self-photo at perfectly square angle to track shifts."

---

# Why BoneMax matters

Facial structure reads instantly — jawline angle, midface support, chin projection. Most adults can't change bone, but they CAN change posture, fascia tension, and muscle development around the jaw and neck, which shifts perceived structure significantly. Mewing trains tongue posture; masseter training thickens the jaw musculature; neck training holds the head up and back so the jawline stays sharp instead of soft.

The schedule is built from workout pattern + TMJ history + chewing experience + screen-time exposure. Those four answers decide how aggressive the masseter ramp is, where neck training plugs in, and how many midday posture resets are needed.

# Core protocol

## Mewing (3 sessions/day backbone)

- **Morning** at wake: tongue on palate (back third), lips sealed, teeth light touch, chin tucked. 60s active hold, then passive all day.
- **Midday** at midpoint(wake+15, bed−60): conscious 30s reset — tongue up, lips sealed, jaw unclenched, head over neck.
- **Night** at bed − 30min: night-set hold + sleep posture cues.

## Masseter / mastic

- 1× daily at user-set time (default wake + 2h). Single piece, 10-15 min, alternating sides.
- TMJ history → skip week 1, ramp from week 2.
- Rest 1 day/week.

## Neck training

- Workout days only: 5-8 min after workout (harness or banded 4-way).
- Non-workout days: chin tucks bundled into midday mewing.
- If user runs FitMax, BoneMax owns neck — FitMax should strip it from its session.

## Fascia / lymph

- Morning at wake + 20min: gua sha or facial massage 3-5 min. Stack after AM mewing.
- Evening at bed − 90min, 4-5×/wk: deeper fascia release. If on SkinMax, skip on retinoid or exfoliation nights.

## Bone-support nutrition (optional)

- Vitamin D3 (4000 IU) + K2 (100 mcg) with first fat-containing meal.
- Magnesium glycinate (300-400 mg) at bed − 60min.
- Calcium from food (greek yogurt, sardines, leafy greens) — supplement only if dietary gaps.

# Notification cadence

- **Mewing morning reset** at wake.
- **Mewing midday reset** at midpoint(wake+15, bed−60).
- **Mewing night check** at bed − 30min.
- **Masseter session** at user-chosen time (default wake + 2h).
- **Facial fascia AM** at wake + 20min.
- **Nasal breathing check** at midday + 2h (twice/day if heavy screen time).
- **Neck training** at workout end + 15m on training days.
- **Fascia / lymph PM** at bed − 90min, 4-5×/wk.
- **Symmetry check** once daily, variable midday-evening time, rotating tip.

Quiet hours: nothing between bed and wake.

# Cross-module rules

- **+ FitMax**: BoneMax owns neck training. FitMax sessions strip neck.
- **+ SkinMax**: Skip evening fascia / lymph on retinoid or exfoliation nights.
- **+ HairMax**: Morning fascia / lymph stacks AFTER scalp minoxidil dries (15-20 min).
- **+ HeightMax**: Morning mewing + posture cues coordinate with height posture-reset task — render as one compound notification, not two.

```yaml task_catalog
- id: bone.mewing_am
  title: "mewing — morning set"
  description: "tongue on palate (back third), lips sealed, teeth light touch, chin tucked. 60s active hold, then passive all day. nasal only."
  duration_min: 2
  default_window: am_open
  tags: [mewing, am, foundation]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Mewing"
  frequency: { type: daily, n: 1 }

- id: bone.mewing_midday
  title: "mewing — midday reset"
  description: "tongue up? lips sealed? nasal? unclench jaw, head over neck, chin back. 30s conscious then passive."
  duration_min: 1
  default_window: midday
  tags: [mewing, midday, posture]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Mewing"
  frequency: { type: daily, n: 1 }

- id: bone.mewing_night
  title: "mewing — night set"
  description: "tongue up, lips closed, nasal. light suction. settle into sleep posture — tongue stays on palate as you drift off."
  duration_min: 2
  default_window: pm_close
  tags: [mewing, pm, sleep]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Mewing"
  frequency: { type: daily, n: 1 }

- id: bone.masseter
  title: "mastic gum session"
  description: "1 piece mastic gum, 10-15 min, alternate left/right sides every minute. balanced bite force. rest 1 day per week."
  duration_min: 12
  default_window: am_active
  tags: [masseter, jaw]
  applies_when: ["tmj_history != true"]
  intensity: 0.5
  evidence_section: "Masseter"
  cooldown_hours: 18
  frequency: { type: daily, n: 1 }

- id: bone.masseter_ramp
  title: "mastic gum — ramp set"
  description: "TMJ-safe ramp: half-piece, 5 min max, alternating sides. log any clicking, fatigue, or pain. back off if symptoms appear."
  duration_min: 6
  default_window: am_active
  tags: [masseter, jaw, ramp]
  applies_when: ["tmj_history == true"]
  contraindicated_when: []
  intensity: 0.3
  evidence_section: "Masseter"
  cooldown_hours: 36
  frequency: { type: n_per_week, n: 3 }

- id: bone.fascia_am
  title: "facial fascia / lymph — AM"
  description: "3-5 min: gua sha or hand massage, neck → jawline → cheek → temple. always upward / outward strokes. drains overnight puffiness."
  duration_min: 4
  default_window: am_open
  tags: [fascia, lymph, am]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Fascia / lymph"
  frequency: { type: daily, n: 1 }

- id: bone.fascia_pm
  title: "facial fascia / lymph — PM"
  description: "5-8 min deeper release. cheek hollows, masseter belly, behind ears. use oil if available. skip on retinoid / exfoliation nights if on SkinMax."
  duration_min: 6
  default_window: pm_close
  tags: [fascia, lymph, pm]
  applies_when: [always]
  intensity: 0.4
  evidence_section: "Fascia / lymph"
  frequency: { type: n_per_week, n: 4 }

- id: bone.nasal_check
  title: "nasal-breathing check"
  description: "are you breathing through your nose? lips sealed, jaw relaxed? screen forward-head check — chin back, head over shoulders."
  duration_min: 1
  default_window: midday
  tags: [nasal, posture, breathing]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "Mewing"
  frequency: { type: daily, n: 1 }

- id: bone.neck_workout
  title: "neck training — full session"
  description: "5-8 min: 4-way harness or banded. front, back, left, right — 15 reps each direction, 2 sets. progress only after no soreness."
  duration_min: 7
  default_window: pm_active
  tags: [neck, training]
  applies_when: ["workout_frequency in [light, moderate, heavy]"]
  intensity: 0.7
  evidence_section: "Neck training"
  frequency: { type: n_per_week, n: 3 }

- id: bone.neck_solo
  title: "neck training — solo day"
  description: "no workout today, but neck still gets work. 5 min banded 4-way. lighter intensity, same movement pattern."
  duration_min: 5
  default_window: pm_active
  tags: [neck, training, solo]
  applies_when: ["workout_frequency == none"]
  intensity: 0.5
  evidence_section: "Neck training"
  frequency: { type: n_per_week, n: 1 }

- id: bone.chin_tucks
  title: "chin tucks bundle"
  description: "10 chin tucks, 2-second hold each. emphasizes long-term forward-head correction. bundles into midday on non-workout days."
  duration_min: 2
  default_window: midday
  tags: [neck, posture, chin-tucks]
  applies_when: ["workout_frequency in [none, light]"]
  intensity: 0.2
  evidence_section: "Neck training"
  frequency: { type: n_per_week, n: 4 }

- id: bone.symmetry_check
  title: "symmetry / posture check"
  description: "rotating: even bite pressure / shoulders relaxed / chin back / tongue posture / nasal only. one focus per day."
  duration_min: 1
  default_window: flexible
  tags: [symmetry, posture, micro]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "Why BoneMax matters"
  frequency: { type: daily, n: 1 }

- id: bone.vitd_k2
  title: "vitamin D3 + K2 with food"
  description: "4000 IU vitamin D3 + 100 mcg K2 (MK-7) with first fat-containing meal. supports bone density and calcium routing."
  duration_min: 1
  default_window: am_open
  tags: [nutrition, supplement, am]
  applies_when: ["nutrition_stack_open == true"]
  intensity: 0.1
  evidence_section: "Bone-support nutrition (optional)"
  frequency: { type: daily, n: 1 }

- id: bone.magnesium_pm
  title: "magnesium glycinate PM"
  description: "300-400 mg magnesium glycinate 60 min before bed. supports sleep depth and overnight muscle relaxation."
  duration_min: 1
  default_window: pm_close
  tags: [nutrition, supplement, pm, sleep]
  applies_when: ["nutrition_stack_open == true"]
  intensity: 0.1
  evidence_section: "Bone-support nutrition (optional)"
  frequency: { type: daily, n: 1 }
```
