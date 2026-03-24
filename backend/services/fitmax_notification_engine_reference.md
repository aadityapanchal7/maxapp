# FITMAX NOTIFICATION ENGINE — AI Reference

## USER INPUTS (onboarding)

- Wake time, bed time  
- Age, current height and weight  
- Estimated body fat %: under 10% / 10–15% / 15–20% / 20–25% / 25–30% / 30%+ / don't know (visual reference chart in UI)  
- Primary goal: get lean (face gains) / build muscle / both (recomp) / maintain  
- Training experience: never / beginner (&lt;1y) / intermediate (1–3y) / advanced (3+y)  
- Equipment: full gym / home (DB + bench + pull-up) / bodyweight only  
- Workout days: 3 / 4 / 5 / 6 per week  
- Preferred workout time  
- Dietary approach: flexible / tracking macros / don't want to track  
- Supplements stack: opt-in only  

## PHASE ROUTING (BF% + goal → phase)

Use **body fat band + primary goal** to assign one phase:

| Phase | Condition |
|-------|-----------|
| **Cut** | BF over ~15%, **or** any BF with goal **get lean** |
| **Lean bulk** | ~10–15% BF + goal **build muscle** |
| **Recomp** | ~15–20% BF + **beginner** + goal **both** — maintenance calories, high protein |
| **Maintain** | ~10–15% BF + goal **maintain** — sweet spot |

## TIMING — when notifications fire

- **Pre-workout:** 30 min before preferred workout time — today's training focus.  
- **Post-workout:** 15 min after **estimated** session end (session length from program tier, typically ~60–90 min).  
- **Morning nutrition:** wake + 30 min — macro / portion targets by phase.  
- **Midday posture / aesthetics tip:** midpoint of active day = midpoint(wake+15m, bed−60m). 10-day rotating tips.  
- **Evening nutrition closeout:** bed − 2 h — protein + calorie check.  
- **Weekly weigh-in:** every **Monday** at wake + 15 min (after bathroom, before food).  
- **Monthly body check:** **1st of month** at midday anchor.  
- **Quiet hours:** no notifications between bed and wake.  

## MODULE 1 — TRAINING PROGRAM

- **1 pre + 1 post per workout day only.** Aesthetics-first: V-taper, shoulders, neck, upper back, chest, arms, core; legs proportional but not powerlifting-priority.  
- **Lateral raises:** high volume on every push/shoulder day (niche “non-negotiable”).  
- **Face pulls:** every session — posture + rear delts.  
- **Neck work:** 2–3×/week in programs **unless BoneMax is active** (then neck lives in BoneMax; remove from FitMax to avoid duplication).  
- **Progressive overload:** when user hits top of rep range for all sets, next session suggest +2.5–5 lb with copy explaining rep fallout is OK.  

### Split sketches (adapt to equipment + days)

- **3-day:** A Push+Shoulders, B Pull+Neck, C Legs+Core  
- **4-day upper/lower:** Upper shoulder emphasis, Lower+Neck, Upper back emphasis, Lower+Abs  
- **5–6 day PPL:** Push / Pull / Legs (+ rest or repeat)  

## MODULE 2 — NUTRITION

- **2×/day:** morning (wake+30) + evening (bed−2h).  
- **TDEE:** Mifflin–St Jeor from height, weight, age, activity; adjust from weigh-in trends monthly.  
- Phase targets: Cut = TDEE−500; Lean bulk = TDEE+250–300; Recomp/Maintain = TDEE; protein ~1 g/lb (0.8–1 g on maintain).  
- If **“don't want to track”:** portion-based copy (palm protein, fist carbs, thumb fat), no numbers in notifications.  

## MODULE 3 — BODY COMP & FACE GAINS

- **Weekly weigh-in** (Monday wake+15). Interpret trends vs phase (cut 0.5–1 lb/wk, bulk same, maintain ±2 lb noise).  
- **Monthly body check** (1st, midday): photos + waist / shoulders / neck; shoulder÷waist ratio (Adonis index framing).  
- **Face gains copy:** fat loss shows in face first; periodic education, not spam.  
- **BF milestone nudges** (once per threshold): ~20%, ~15%, ~12%, ~10%, sub-10 warnings per spec.  

## MODULE 4 — POSTURE & PROPORTIONS

- **1×/day midday** — 10-day rotation (shoulders, vacuum, APT, creatine, water, sleep, shoulder-waist ratio, neck, face pulls, alcohol).  
- If **BoneMax active:** drop posture-overlap tips from FitMax; replace with extra training/nutrition tips (no duplication).  

## MODULE 5 — SUPPLEMENTS

- **Opt-in only.** Bundle with **morning nutrition** at wake+30 when enabled. Evidence-only: creatine 5 g, protein as food-first, etc.  

## NOTIFICATION BUDGET & PHASE-IN

| Module | Per day | When |
|--------|---------|------|
| Training | 2 | Workout days only |
| Nutrition AM | 1 | Daily |
| Nutrition PM | 1 | Daily |
| Posture tip | 1 | Daily (phase 3+) |
| Supplements | 1 | Daily if opted in |
| Weigh-in | 1 | Monday |
| Body check | 1 | Monthly |

- **Workout days:** ~5–6 tasks; **rest:** ~3–4. Hard cap **10/day** all modules.  
- **Phase-in:** W1–2 training + AM nutrition + weekly weigh-in; W3–4 + PM nutrition + supplements; W5+ + posture + monthly check. Use `fitmax_weeks_on_program` when present.  

## CROSS-MODULE

- **FitMax + BoneMax:** no neck in FitMax lifts; no duplicate posture tips in FitMax; face pulls stay.  
- **FitMax + HeightMax:** sprints = cardio, no extra cardio; after heavy squat/DL copy: optional 2 min dead hang; merge protein targets.  
- **FitMax + SkinMax:** merge **morning nutrition + AM skin** into one block when times align; midday add line: leanness helps skin (inflammation).  
- **FitMax + HairMax:** creatine ↔ hair note (DHT concern, mixed evidence) when creatine tip would fire.  

---

All task times MUST be **HH:MM** 24h, derived from user wake, bed, and preferred workout time. Respect quiet hours and multi-module merge rules.
