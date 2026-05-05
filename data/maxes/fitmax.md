---
maxx_id: fitmax
display_name: Fit
short_description: Strength, body composition, and conditioning aligned to your goal.

required_fields:
  - id: goal
    question: "What's your main fitness goal right now?"
    type: enum
    options:
      fat_loss: "Fat loss / cut — drop body fat, get leaner"
      muscle_gain: "Muscle gain / lean bulk — add size"
      recomp: "Recomp — lean out and add muscle at the same time"
      maintenance: "Maintain — hold what I've got"
      performance: "Performance — strength, conditioning, athletic"
    required: true
    why: "Drives the calorie target, training split, and which phase the schedule starts in."

  - id: experience_level
    question: "What's your training experience level?"
    type: enum
    options:
      beginner: "Beginner — under 1 year of consistent lifting"
      intermediate: "Intermediate — 1-3 years, know the main lifts"
      advanced: "Advanced — 3+ years, intentional programming"
    required: true
    why: "Beginners get higher-frequency simpler programs with newbie-gain assumptions; advanced get periodization."

  - id: equipment
    question: "What can you train with?"
    type: enum
    options:
      full_gym: "Full gym — barbells, dumbbells, machines"
      home_dumbbells: "Home with dumbbells (and maybe bands / pull-up bar)"
      bodyweight_only: "Bodyweight only — no equipment"
    required: true
    why: "Schedule task selection (compound lifts vs DB substitutes vs bodyweight progressions) depends entirely on this."

  - id: days_per_week
    question: "How many days per week can you realistically train?"
    type: int
    min: 2
    max: 6
    step: 1
    default: 4
    unit: "days"
    required: true
    why: "Determines split (full-body for 2-3, upper/lower for 4, push/pull/legs for 5-6)."

  - id: session_minutes
    question: "How long can you commit to per session, on most days?"
    type: int
    min: 30
    max: 90
    step: 15
    default: 60
    unit: "min"
    required: true
    why: "Caps total volume per session — short sessions get higher-density circuits; long get traditional rest-pause."

  - id: daily_activity_level
    question: "Outside the gym, how active is your day?"
    type: enum
    options:
      sedentary: "Sedentary — desk job, mostly sitting"
      lightly_active: "Lightly active — walks, on feet some of the day"
      moderately_active: "Moderately active — physical job or daily activity"
      very_active: "Very active — manual work or hard training daily"
    required: true
    why: "TDEE multiplier — drives calorie target alongside goal."

optional_context:
  - id: age
    description: "User age (from onboarding) — gates training intensity, recovery cadence."
  - id: biological_sex
    description: "Biological sex (from onboarding) — drives baseline calorie + protein targets."
  - id: height_cm
    description: "Height in cm (from onboarding) — used for BMR calculation."
  - id: weight_kg
    description: "Current bodyweight in kg (from onboarding) — used for protein target and progress tracking."
  - id: estimated_body_fat
    description: "User-stated body-fat band (under 10 / 10-15 / 15-20 / 20-25 / 25-30 / 30+) — refines phase selection."
  - id: dietary_restrictions
    description: "vegan / vegetarian / gluten-free / lactose-free — biases food suggestions."
  - id: training_history
    description: "Sport / lifting background notes — informs accessory selection."
  - id: injury_history
    description: "Injuries to work around — substitutes contraindicated lifts."
  - id: cardio_preference
    description: "Steady-state vs HIIT preference — biases conditioning blocks."
  - id: home_equipment_extras
    description: "Pull-up bar, kettlebell, bands — unlocks specific movements at home."
  - id: tracking_capability
    description: "Whether the user is willing to log calories / weigh food — drives precise vs portion-based language."

prompt_modifiers:
  - id: cut_phase
    if: "goal == fat_loss or estimated_body_fat in [20-25, 25-30, 30+]"
    then: "PHASE: CUT. Calorie target = TDEE − 500. Protein ~1g/lb bodyweight. Add daily step target (8-10k). Conditioning 2×/wk (LISS or low-intensity). Lifts focus on retaining muscle: 4-8 reps, hard sets, do not reduce volume aggressively."
  - id: lean_bulk_phase
    if: "goal == muscle_gain and estimated_body_fat in [under_10, 10-15]"
    then: "PHASE: LEAN BULK. Calorie target = TDEE + 250-300. Protein ~1g/lb. Surplus is small — track weight weekly, target +0.25-0.5 lb/wk. Conditioning 1×/wk to maintain cardio without eating into recovery."
  - id: recomp_phase
    if: "goal == recomp and experience_level == beginner"
    then: "PHASE: RECOMP. Calorie target = TDEE (maintenance). Protein elevated to ~1g/lb. Beginner-gains window — strict program adherence, progressive overload every session. Re-evaluate every 8 weeks."
  - id: maintenance_phase
    if: "goal == maintenance"
    then: "PHASE: MAINTAIN. Calorie target = TDEE. Protein 0.7-0.8g/lb. 3-4 sessions/wk is enough. Track only weekly bodyweight; no calorie counting required."
  - id: performance_phase
    if: "goal == performance"
    then: "PHASE: PERFORMANCE. Calorie target = TDEE +100-200. Periodize: 4-week strength block (3-5 reps), 4-week hypertrophy block (8-12 reps), 1-week deload. Conditioning 2×/wk."
  - id: bodyweight_track
    if: "equipment == bodyweight_only"
    then: "Substitute compound lifts with progressive bodyweight movements: pull-ups → archer / one-arm progression; push-ups → archer / one-arm / planche progression; squats → pistol progression; hinges → single-leg RDL / glute bridge. Volume runs higher (3-5 sets at higher reps)."
  - id: dumbbell_only_track
    if: "equipment == home_dumbbells"
    then: "Substitute barbell lifts with DB equivalents: bench → DB bench, squat → goblet/DB Bulgarian split squat, deadlift → DB RDL, OHP → DB shoulder press. Add bands for pull patterns if no pull-up bar. Reduce target weight expectations — DBs cap intensity vs barbell."
  - id: low_frequency_full_body
    if: "days_per_week <= 3"
    then: "Use full-body sessions. Compound lifts every session (squat / hinge / press / row / accessory). 8-12 working sets per session."
  - id: mid_frequency_upper_lower
    if: "days_per_week == 4"
    then: "Upper / lower split (alternating). 8-10 working sets per session, ~6 working sets per body part across the week."
  - id: high_frequency_split
    if: "days_per_week >= 5"
    then: "Push / pull / legs (or PPL with arm day). Volume 12-16 working sets per body part per week. Add 1-2 dedicated arm/shoulder accessory days if 6/wk."
  - id: short_sessions_density
    if: "session_minutes <= 45"
    then: "Use density circuits / supersets for accessories. 2-3 main lifts at 3-4 working sets, rest 1.5 min between. No isolation chaos — keep movement count low."
  - id: long_sessions_volume
    if: "session_minutes >= 75"
    then: "Traditional split: 4-5 working sets on main lifts, 3-4 sets on accessories, 2-3 min rest on compounds. Add a 10-15 min cardio finisher 1-2× per week."
  - id: sedentary_steps
    if: "daily_activity_level == sedentary"
    then: "Add daily 7000-step target. If goal == fat_loss, raise to 8000-10000. Counts as the conditioning quota for cut phases."
  - id: very_active_recovery
    if: "daily_activity_level == very_active"
    then: "Outside-gym activity already provides cardiovascular stimulus. Skip dedicated steady-state cardio. Prioritize protein and sleep — recovery, not more activity, is the limiter."
  - id: vegan_protein_bias
    if: "dietary_restrictions == vegan"
    then: "Protein targets harder to hit. Suggest tofu / tempeh / seitan / pea-protein isolate. Add 1 daily reminder for protein quota at lunch."
  - id: tmj_neck_caveat
    if: "injury_history contains 'tmj' or injury_history contains 'jaw' or injury_history contains 'neck'"
    then: "EXCLUDE neck training. Substitute with banded face pulls + cuffed reverse fly. Avoid heavy front-loaded movements (front squat, Zercher) until cleared."

---

# Why FitMax matters

Body composition is the foundation looksmaxxing rests on. Lean mass under thin skin reads as health, status, and discipline — every other module compounds on top of this. Fat distribution reshapes the face independently of skin or jawline work; gaining muscle changes posture and proportions in ways no haircut or skincare routine can.

The schedule is built from goal + experience + equipment + frequency. Everything else (training split, calorie target, conditioning load) derives from those four answers. Body-fat band and activity level refine the calorie math; injury history gates risky lifts.

# Core protocol

## Training principles

- Progressive overload is non-negotiable: when you hit the top of the prescribed rep range with good form, add 2.5-5 lb the next session.
- Stay close to failure on the last set of compound lifts (RIR 0-2). Earlier sets at RIR 2-3.
- Lateral raises and face pulls every session, regardless of split — small posterior delts and rear delts are aesthetics multipliers.
- Train neck 2-3×/wk via plate-loaded harness or banded resistance — UNLESS the user is also running BoneMax (in which case BoneMax owns neck and we omit it from FitMax).
- Compounds before isolation. Big rocks first.

## Nutrition principles

- Protein targets ~1g/lb bodyweight, regardless of goal.
- Calories adjust by phase: cut −500, lean bulk +250-300, recomp / maintenance @ TDEE, performance +100-200.
- No-track users get portion-based language: palm of protein, fist of carbs, thumb of fat per meal.
- Hydration: 0.5-1 oz per lb bodyweight per day, more on training days.
- Pre-workout: light meal 60-90 min out (protein + carb). Post-workout: protein within 60 min of finishing.

## Recovery

- Sleep 7-9 hr nightly. Schedule should include a wind-down cue at bed − 60 min on training days.
- Deload every 6-8 weeks (week of half-volume) for intermediates and advanced.
- One full rest day per week minimum, even on 5-6 day splits.

# Notification cadence

- **Pre-workout** at workout − 30m: hydration + light fuel reminder.
- **Workout window**: deterministic, user-set training time.
- **Post-workout** at workout end + 15m: protein reminder.
- **AM nutrition** at wake + 30m: protein-forward breakfast cue.
- **Midday tip** at midpoint(wake+15, bed−60): rotating motivational + technique cue.
- **PM nutrition** at bed − 2h: last meal anchor; protein + slow carb suggestion.
- **Weekly weigh-in** Monday at wake + 15m.
- **Monthly progress photo** 1st of month at midday.

Quiet hours: nothing between bed and wake.

# Cross-module rules

- **+ BoneMax**: BoneMax owns neck training; strip neck from FitMax sessions.
- **+ HeightMax**: After axial leg day, prepend a 60-90s dead hang to the post-workout block.
- **+ SkinMax**: Merge AM nutrition and AM skincare cues into a single block (cleanse → SPF → eat).
- **+ HairMax**: If on creatine, add the standard "creatine doesn't cause hair loss in users without genetic baldness predisposition" caveat once per cycle.
