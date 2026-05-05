---
maxx_id: fitmax
display_name: Fit
short_description: Strength, body composition, and conditioning aligned to your goal.

schedule_design:
  cadence_days: 14
  am_window: ["wake+0:15", "wake+1:30"]
  pm_window: ["sleep-2:30", "sleep-0:30"]
  daily_task_budget: [3, 6]
  intensity_ramp:
    week_1: [0.0, 0.6]
    week_2: [0.4, 1.0]
  skeleton:
    blocks:
      # --- Daily nutrition rails ---
      - id: am_nutrition
        slot: am_open
        cadence: daily
        tasks: [fit.am_nutrition]
      - id: midday_tip
        slot: midday
        cadence: daily
        tasks: [fit.midday_tip]
      - id: pm_nutrition
        slot: pm_close
        cadence: daily
        tasks: [fit.pm_nutrition]
      # --- Workout window — N times/week, where N = days_per_week ---
      - id: preworkout
        slot: am_active
        cadence: n_per_week=days_per_week
        tasks: [fit.preworkout]
      - id: workout_session
        slot: pm_active
        cadence: n_per_week=days_per_week
        tasks: [fit.workout_session]
      - id: postworkout
        slot: pm_active
        cadence: n_per_week=days_per_week
        tasks: [fit.postworkout]
      # --- Steps target — required for cut / fat-loss; sedentary users always ---
      - id: daily_steps
        slot: flexible
        cadence: daily
        if: "goal == fat_loss or daily_activity_level == sedentary"
        tasks: [fit.daily_steps]
      # --- Conditioning by phase ---
      - id: cardio_liss
        slot: flexible
        cadence: n_per_week=2
        if: "goal == fat_loss"
        tasks: [fit.cardio_liss]
      - id: cardio_lean_bulk
        slot: flexible
        cadence: n_per_week=1
        if: "goal == muscle_gain"
        tasks: [fit.cardio_liss]
      # --- Recovery + tracking ---
      - id: weekly_weighin
        slot: am_open
        cadence: n_per_week=1
        tasks: [fit.weekly_weighin]
      - id: monthly_photo
        slot: midday
        cadence: every_n_days=30
        tasks: [fit.monthly_photo]
      - id: deload_check
        slot: flexible
        cadence: every_n_days=42
        if: "experience_level in [intermediate, advanced]"
        tasks: [fit.deload_check]
      # --- Hydration nudge — heavy training or hot conditions ---
      - id: hydration_check
        slot: midday
        cadence: daily
        if: "days_per_week >= 4 or daily_activity_level == very_active"
        tasks: [fit.hydration_check]

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

  - id: estimated_body_fat
    question: "Roughly what's your body-fat range right now?"
    type: enum
    options:
      under_10: "Under 10% — visible abs, vascularity"
      "10_15": "10–15% — lean, abs faintly visible"
      "15_20": "15–20% — soft but athletic"
      "20_25": "20–25% — noticeable softness"
      over_25: "25%+ — significant softness"
      unknown: "Honestly not sure"
    required: true
    why: "Refines phase selection. Over_25 → cut even if user wants 'recomp' (recomp at higher BF wastes time). Under_10 + bulk = lean bulk; under_10 + maintain = aggressive maintenance."

  - id: nutrition_tracking_pref
    question: "How precise do you want to get with nutrition?"
    type: enum
    options:
      full_track: "Full tracking — log calories + macros daily"
      portion_only: "Portion language — palms / fists, no numbers"
      no_tracking: "Don't track at all — just eat better intuitively"
    required: true
    why: "Decides whether the schedule shows calorie/macro tasks (full_track), portion reminders (portion_only), or only food-quality cues (no_tracking)."

  - id: sleep_hours
    question: "Average hours of sleep per night?"
    type: int
    min: 4
    max: 12
    step: 1
    default: 7
    unit: "hr"
    required: true
    why: "Under 7 hr → recovery is the limiter. Lower training volume on under-7 days, add sleep priority cue 60 min before bed. Over 8 hr → can push higher volume / intensity."

  - id: dietary_restrictions
    question: "Any dietary restrictions you're sticking to?"
    type: enum
    options:
      none: "No restrictions"
      vegetarian: "Vegetarian"
      vegan: "Vegan"
      gluten_free: "Gluten-free"
      lactose_free: "Lactose-free"
      keto: "Keto / very low carb"
    required: true
    why: "Drives meal-suggestion bias. Vegan/vegetarian → harder to hit protein, suggest tofu/tempeh/pea protein. Keto → low-carb meal templates. Gluten/lactose-free → exclude wheat/dairy from suggestions."

  - id: injury_history
    question: "Any injuries to work around?"
    type: enum
    options:
      none: "Nothing — full range of motion"
      knee: "Knees — careful with squats/lunges"
      shoulder: "Shoulder — careful with overhead pressing"
      back: "Lower back — careful with deadlifts / squats"
      multiple: "Multiple — I'll explain in chat"
    required: true
    why: "Substitutes contraindicated lifts. Knee → goblet squat / leg press / split squat. Shoulder → DB landmine press / chest-supported row. Back → trap bar / RDL only / box squat."

  - id: supplement_openness
    question: "How open are you to supplements?"
    type: enum
    options:
      none: "Just food — no supplements"
      basic: "Basics — protein powder + creatine"
      full_stack: "Full stack — pre-workout, BCAAs, vitamins, etc."
    required: true
    why: "Gates supplement reminders. None = no nudges. Basic = protein + creatine timing reminders. Full = pre-workout + EAA timing layered in."

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
  - id: bf_high_force_cut
    if: "estimated_body_fat in [over_25] and goal != maintenance"
    then: "OVERRIDE: regardless of stated goal, this user needs CUT phase. Recomp at >25% BF wastes time. Calorie target = TDEE − 500. Frame supportively: 'lean out first, then build — order matters'."
  - id: bf_low_lean_bulk_ok
    if: "estimated_body_fat == under_10 and goal == muscle_gain"
    then: "Aggressive lean bulk window. TDEE + 350 (vs +250 for higher BF). Less risk of fat gain at this body fat. Daily weigh-in reminder; pull back surplus to +200 if weekly gain >0.5 lb."
  - id: tracking_full_macros
    if: "nutrition_tracking_pref == full_track"
    then: "Schedule daily macro log reminders: protein at each meal, calorie total at PM. Add weekly macro review task on Sunday. Use exact gram numbers in copy."
  - id: tracking_portion_only
    if: "nutrition_tracking_pref == portion_only"
    then: "Use portion language exclusively. 'Palm of protein, fist of carbs, thumb of fat per meal'. Skip macro/calorie task copy. Weekly bodyweight review only."
  - id: tracking_none_food_quality
    if: "nutrition_tracking_pref == no_tracking"
    then: "Drop ALL calorie/macro/portion task copy. Replace with food-quality cues only ('add a vegetable', 'protein at every meal', 'limit liquid calories'). No numbers. Frame around habits, not measurements."
  - id: low_sleep_recovery
    if: "sleep_hours < 7"
    then: "RECOVERY-LIMITED. Lower training volume by 1 working set per exercise. Add bedtime cue 60 min before target sleep. Cut PM caffeine entirely. Frame: 'more sleep > more sets, every time'."
  - id: high_sleep_push_volume
    if: "sleep_hours >= 8"
    then: "RECOVERY-RICH. Can push higher volume / intensity. Add 1 extra working set per exercise on top of phase baseline. Maintain bedtime consistency though — drift wrecks the gain."
  - id: vegetarian_protein
    if: "dietary_restrictions == vegetarian"
    then: "Suggest eggs / dairy / Greek yogurt / cottage cheese / whey + plant protein blends. Easier than vegan to hit protein. Daily protein cue at one meal."
  - id: keto_macros
    if: "dietary_restrictions == keto"
    then: "MACRO INVERT: fat is primary fuel. Carbs <30g/day. Protein moderate (0.7g/lb to avoid gluconeogenesis). Schedule keto-friendly meal suggestions: meat + fat + green veg. Skip 'add a banana' style copy."
  - id: gluten_free_swap
    if: "dietary_restrictions == gluten_free"
    then: "Swap wheat suggestions to rice / oats (certified GF) / quinoa / GF pasta. Watch hidden gluten in protein bars / sauces — flag at weekly review."
  - id: knee_injury_sub
    if: "injury_history == knee"
    then: "EXCLUDE: barbell back squat, lunges, jump variations. SUBSTITUTE: goblet squat, leg press, Bulgarian split squat (controlled), step-ups (low height). Add quad activation warm-up before any leg session."
  - id: shoulder_injury_sub
    if: "injury_history == shoulder"
    then: "EXCLUDE: overhead barbell press, behind-neck pulldown, upright row, dips. SUBSTITUTE: DB landmine press, neutral-grip DB press, chest-supported DB row, machine pec deck. Add shoulder mobility warm-up."
  - id: back_injury_sub
    if: "injury_history == back"
    then: "EXCLUDE: conventional deadlift, heavy back squat, bent-over barbell row. SUBSTITUTE: trap bar deadlift, box squat, chest-supported row, cable row. Add deadbug + bird-dog core stability warm-up before any compound lift."
  - id: supplements_basic_timing
    if: "supplement_openness in [basic, full_stack]"
    then: "Add creatine 5g/day reminder (any time, but consistency matters). Whey shake post-workout reminder. Both build into the existing post-workout protein task — no new notification, just copy."
  - id: supplements_full_preworkout
    if: "supplement_openness == full_stack"
    then: "Add pre-workout caffeine reminder 30 min before training. EAA / BCAA during long sessions (>75 min). Multivitamin AM. Vitamin D3 daily if under 22 or northern climate."

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

```yaml task_catalog
- id: fit.am_nutrition
  title: "AM nutrition — protein-forward breakfast"
  description: "30-40g protein within an hour of waking. eggs, greek yogurt, whey, or a meat option. add fruit or oats for carbs."
  duration_min: 5
  default_window: am_open
  tags: [am, nutrition, protein]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Nutrition principles"
  frequency: { type: daily, n: 1 }

- id: fit.midday_tip
  title: "midday training tip"
  description: "rotating cue — progressive overload, technique check, recovery focus, or motivation. one specific actionable per day."
  duration_min: 1
  default_window: midday
  tags: [midday, tip, motivation]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "Training principles"
  frequency: { type: daily, n: 1 }

- id: fit.pm_nutrition
  title: "PM nutrition — last meal anchor"
  description: "protein + slow carb 2-3 hours before bed. caesar salad with chicken, salmon + rice, lean ground beef + sweet potato."
  duration_min: 5
  default_window: pm_close
  tags: [pm, nutrition, protein]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Nutrition principles"
  frequency: { type: daily, n: 1 }

- id: fit.preworkout
  title: "pre-workout fuel + hydration"
  description: "light carb + protein 60-90 min out (banana + whey, oats + egg whites). 16-24 oz water. caffeine 30 min pre-lift if you use it."
  duration_min: 5
  default_window: am_active
  tags: [preworkout, fuel]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Nutrition principles"
  frequency: { type: n_per_week, n: 4 }

- id: fit.workout_session
  title: "training session"
  description: "lift per your split — compounds first, accessories after. lateral raises + face pulls every session. progressive overload: hit top of rep range → add 2.5-5 lb next time."
  duration_min: 60
  default_window: pm_active
  tags: [workout, training, lift]
  applies_when: [always]
  intensity: 0.8
  evidence_section: "Training principles"
  frequency: { type: n_per_week, n: 4 }

- id: fit.postworkout
  title: "post-workout protein"
  description: "30-40g protein within 60 min of finishing — whey shake, chicken, greek yogurt. rehydrate fully before next meal."
  duration_min: 5
  default_window: pm_active
  tags: [postworkout, protein, recovery]
  applies_when: [always]
  intensity: 0.3
  evidence_section: "Nutrition principles"
  frequency: { type: n_per_week, n: 4 }

- id: fit.daily_steps
  title: "daily step target"
  description: "8000-10000 steps if cutting; 7000+ if sedentary. counts as conditioning quota when on a cut."
  duration_min: 1
  default_window: flexible
  tags: [steps, conditioning, neat]
  applies_when: ["goal == fat_loss or daily_activity_level == sedentary"]
  intensity: 0.3
  evidence_section: "Recovery"
  frequency: { type: daily, n: 1 }

- id: fit.cardio_liss
  title: "LISS cardio — 30 min"
  description: "low-intensity steady state — incline walk, easy bike, swim. heart rate 60-70% max. burns calories without eating into recovery."
  duration_min: 30
  default_window: flexible
  tags: [cardio, conditioning, liss]
  applies_when: ["goal in [fat_loss, muscle_gain]"]
  intensity: 0.4
  evidence_section: "Training principles"
  frequency: { type: n_per_week, n: 2 }

- id: fit.weekly_weighin
  title: "weekly weigh-in"
  description: "monday morning, fasted, after bathroom, before water. average over the week — daily fluctuation is noise. log it."
  duration_min: 2
  default_window: am_open
  tags: [tracking, weighin]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "Recovery"
  frequency: { type: n_per_week, n: 1 }

- id: fit.monthly_photo
  title: "monthly progress photo"
  description: "front + side + back. same lighting, same time of day, similar post-meal state. compare month-over-month, not day-to-day."
  duration_min: 5
  default_window: midday
  tags: [tracking, progress]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Recovery"
  frequency: { type: every_n_days, n: 30 }

- id: fit.deload_check
  title: "deload week check-in"
  description: "every 6-8 weeks, drop volume in half for one week. recovery overshoots — strength comes back higher. only intermediates+."
  duration_min: 2
  default_window: flexible
  tags: [recovery, deload]
  applies_when: ["experience_level in [intermediate, advanced]"]
  intensity: 0.2
  evidence_section: "Recovery"
  frequency: { type: every_n_days, n: 42 }

- id: fit.hydration_check
  title: "hydration check"
  description: "0.5-1 oz per lb bodyweight per day, more on training days. urine pale yellow = good; dark = drink up."
  duration_min: 1
  default_window: midday
  tags: [hydration, recovery]
  applies_when: ["days_per_week >= 4 or daily_activity_level == very_active"]
  intensity: 0.1
  evidence_section: "Nutrition principles"
  frequency: { type: daily, n: 1 }
```
