---
maxx_id: bonemax
display_name: Bone
short_description: Mewing, jaw posture, masseter training, and bone-support nutrition for facial structure.

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
