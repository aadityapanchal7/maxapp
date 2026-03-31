# HEIGHTMAX NOTIFICATION ENGINE — Reference (authoritative for schedule + SMS copy)

## USER INPUTS (onboarding)

- Wake time, bed time  
- Age, current height (self-reported)  
- Growth plate status: open / closed / don't know  
- Workout days and time  
- Currently doing stretching or decompression: yes / no  
- Sleep quality self-assessment: good / average / poor  
- Goal: maximize remaining growth / recover compressed height / both  
- Optional: height nutrition stack opt-in, screen hours estimate, `heightmax_weeks_on_routine` for phase  

## AGE TIERS (routing)

- **Tier 1 (under 18):** Plates likely open — all modules; natural optimization can help.  
- **Tier 2 (18–21):** Plates closing — posture + decompression + sleep/nutrition; realistic expectations.  
- **Tier 3 (22+):** Plates closed — posture + decompression only; **never** promise skeletal growth beyond **~0.5–2 cm** reclamation; frame as presentation / recovery, not new bone length.  

If growth plates **don't know** and age **under 20:** suggest wrist X-ray once at onboarding only — **not** a recurring notification.

## TIMING LOGIC

All times from **wake_time** and **sleep_time**. Quiet hours: **no** notifications between bed and wake.

| Slot | Rule |
|------|------|
| **Morning stretch / decompression** | **Wake + 20 minutes** |
| **Midday posture check** | **Midpoint** of active day — same as BoneMax/Skinmax midday: midpoint between **(wake + 15 min)** and **(bed − 60 min)** |
| **Afternoon posture check** | **Midday + 3 hours** — only if user reported **6+ hours** daily screen time |
| **Sprint / HIIT** | **30 minutes before** scheduled workout time on **sprint days** (2–3×/week, non-consecutive) |
| **Evening stretch / decompression** | **Bed − 90 minutes** |
| **Sleep protocol (GH)** | **Bed − 45 minutes** |
| **Height nutrition** | Once at meal: **wake + 1 h** or **wake + 5 h** — **only if opted in** |
| **Weekly measurement** | **Every Sunday** at **wake + 30 minutes** |
| **Monthly check-in** | **1st of month** at **midday** (same midpoint as posture midday) |

## MODULE 1 — SPINAL DECOMPRESSION & STRETCHING (2×/day)

**Morning (wake+20):** Dead hang 60–90s total, cobra 30s×3, cat-cow 10 slow, tadasana 30s×2 — total ~5–7 min. Tier 1: add disc-development framing. Tier 3: reclaim natural height / stop being shorter than you should be — not “growing.”

**Evening (bed−90):** Dead hang, lying twist, inversion or legs-up-wall, child’s pose — ~5–8 min. No progressive overload; consistency only. Optional inversion table note ~week 4.

## MODULE 2 — POSTURE (1–2×/day)

**Midday:** Wall test, chin tucks ×10, shoulder squeezes ×10, glute bridges 2×15 — ~3–4 min. Communicate **1–3 cm** recovery from posture is the proven adult heightmax.

**Afternoon (midday+3h, screen 6+):** Quick slip check — head, shoulders, screen height.

After **4+ weeks** consistent: may suggest wall slides.

## MODULE 3 — SLEEP (GH) (1×/day)

**Bed−45:** Blue light off, cool room, no food &lt;2h before bed; at bed: dark room, back sleep, thin pillow. Tier-specific GH copy per spec. Supplement suggestions **once** at onboarding (magnesium, low-dose melatonin) — not repeated daily SMS.

## MODULE 4 — SPRINT / HIIT (2–3×/week)

**30 min pre–workout** on sprint days: warm-up, 6–8×30s sprints, 60–90s rest, cool-down — ~20 min. **No food 1h after** sprint (insulin blunts GH spike).

**~60 min after session:** “eating window open” + high protein within 30 min.

Non-consecutive sprint days; if workouts Mon/Wed/Fri, sprints e.g. Tue/Thu or Mon/Fri.

## MODULE 5 — HEIGHT NUTRITION (opt-in, 1×/day)

**Tier 1:** Growth-focused stack framing — protein ~1 g/lb, D3, K2, zinc, magnesium, calcium from food, collagen, slight surplus.

**Tier 2 (18–21):** Same nutrients; frame as squeezing residual potential + recovery.

**Tier 3 (21+):** Bone density / recovery / presentation support — not linear growth.

Only if user **opted in** — otherwise **no** nutrition notification.

## MODULE 6 — HEIGHT TRACKING (weekly)

**Sunday wake+30:** Standardized **morning** measure after decompression routine — same wall/mark method, mm precision. Evening height is **not** comparable.

Expectation copy by tier at onboarding (not daily).

## MODULE 7 — APPEARANCE (softmax)

**No daily SMS.** Onboarding education once; **1×/week** optional line **merged into midday posture** notification — rotate tips (monochrome, fit, V-neck, vertical stripes, shoes, hair volume, etc.).

## PHASE-IN

- **Phase 1 (weeks 1–2):** Posture (1–2/day) + sleep protocol + weekly measure → ~2–3/day  
- **Phase 2 (weeks 3–4):** + decompression 2/day + nutrition if opted in → ~5–6/day  
- **Phase 3 (week 5+):** + sprint 2–3×/week + appearance in posture → ~6–7/day  

Stay under **10/day** with other modules.

## MONTHLY CHECK-IN (1st, midday)

Compare Sunday measurements, posture feel, back pain from stretching. Branch per spec (+0.5 cm / flat / down / pain → deload or doctor).

## CROSS-MODULE

- **Heightmax + Bonemax:** merge posture cues; merge sleep protocol with mewing night check; merge overlapping supplement reminders into **one** meal-time block.  
- **Heightmax + Fitmax:** sprint day = workout day; dead hangs can live at gym; after heavy squat/deadlift days note **temporary** spinal compression → decompression after leg day.  

**Hard cap: 10 notifications/day** combined.
