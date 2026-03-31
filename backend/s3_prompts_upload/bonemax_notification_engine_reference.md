# BONEMAX NOTIFICATION ENGINE — Reference (authoritative for schedule + SMS copy)

## USER INPUTS (onboarding)

- Wake time, bed time  
- Age  
- Workout days and time (e.g. Mon/Wed/Fri at 6:00 PM)  
- Screen time hours per day (estimate)  
- Current habits: already mewing? / chewing gum? / training neck? / none  
- Jaw issues: TMJ clicking, jaw pain, or grinding history? yes / no  
- Sleep position: back / side / stomach / don't know  
- Optional toggles: meal chewing reminders, bone nutrition stack opt-in, hard mewing, mouth breather flag  

## TIMING LOGIC — when notifications fire

All times derive from **wake_time** and **sleep_time** (bed). No vague "morning" without a computed clock time.

| Slot | Rule |
|------|------|
| **Mewing Morning Reset** | **Wake time** — first thing, before anything else |
| **Mewing Midday Reset** | **Midpoint** of active day — same formula as Skinmax midday: midpoint between **(wake + 15 min)** and **(bed − 60 min)** |
| **Mewing Night Check** | **Bed − 30 minutes** — anchor for sleep optimization copy (Module 7) |
| **Masseter Session** | User-chosen time, or default **wake + 2 hours** — once daily |
| **Facial Exercises** | **Wake + 15 minutes** — stacks after morning mewing reset (5 min block) |
| **Nasal Breathing Check** | **Midday mewing reset + 2 hours** — once daily (twice if screen time 6+ h: midday + afternoon; max 2×/day) |
| **Neck Training** | **15 minutes after workout end** on workout days only. **Non–workout days:** chin tucks **bundled into midday mewing** notification (not separate). On workout days after full neck session, **omit** chin tucks from midday |
| **Fascia / Lymph — Morning** | **Wake + 20 minutes** (after mewing reset; after skin AM if they have Skinmax) |
| **Fascia / Lymph — Evening** | **Bed − 90 minutes** — **4–5×/week**, not nightly. If user has Skinmax: **skip** on retinoid nights or exfoliation nights. If no Skinmax: **5×/week** with **Wednesday + Sunday off** as rest pattern |
| **Symmetry Check** | **Once daily** at a **variable** time between midday and evening; **rotate** symmetry tips on a **weekly** cycle |
| **Quiet hours** | **No** notifications between **bed** and **wake** |

## MODULE 1 — MEWING (3/day backbone)

**Morning (wake):** 👅 Mewing — morning set — tongue on palate (back third), lips sealed, teeth light touch, chin slightly tucked, light suction hold, swallow and hold, nasal only, **60s** then passive. Every day, no ramp.

**Midday (midpoint):** 👅 Mewing — midday reset — tongue up? lips sealed? nasal? unclench jaw, stack head over neck, chin back, **30s** conscious then passive. If screen time **6+ h**, append screen-forward-head cue.

**Night (bed−30):** 👅 Mewing — night set — tongue up, lips closed, nasal; **bundle Module 7 sleep lines** here (no standalone sleep module notifications).

## MODULE 2 — MASSETER (1 session + optional recovery ping)

- **Weeks 1–2:** Falim 10–15 min, slow, switch sides q5min, premolar zone, stop if click/pain.  
- **Weeks 3–4:** Falim 20 min, same form.  
- **Week 5+:** Mastic or double Falim 20–30 min.  
- **Post-session check** ~**5 min after** expected end: recovery / clicking / pain / one-sided — adjust progression (drop level if 2× clicking/week; pause 3 days if pain with copy per spec).  
- **TMJ history at onboarding:** cap **15 min max**, **Falim only**, never progress past beginner stack; always include light jaw-history disclaimer.  
- **Meal chewing reminders (optional, toggle):** estimated meals **wake+1h / +5h / +9h** but **max 2×/day** (lunch + dinner only — skip breakfast). User can turn off.

## MODULE 3 — NECK

- **Workout day:** full routine **15 min after workout end**; progression weeks 1–4 → 5–8 → 9+ per reference; non-consecutive days.  
- **Daily chin tucks:** on **non-workout** days, **in midday mewing** text; **skip** in midday on days they already did full neck session.

## MODULE 4 — FACIAL EXERCISES (1/day)

**Wake+15:** 5 min — jaw push-outs, chin lifts, cheekbone presses, fish face — per rep counts in long-form spec. **No progression.** If user skips **5+ days** in a row, shorten to **2 min** (jaw push-outs + chin lifts only).

## MODULE 5 — FASCIA / LYMPH

**Wake+20:** ~90s tap + drain + optional contrast. **Bed−90:** 2–3 min evening routine; tool-optional. Skip evening on Skinmax retinoid/exfol nights when applicable.

## MODULE 6 — NASAL BREATHING

**Midday+2h:** daytime check. **Night:** bundled into mewing night (mouth tape note, congestion alt, mouth-breather week-1 copy).

## MODULE 7 — SLEEP OPTIMIZATION

**No standalone SMS.** Append to **mewing night check** by profile: side/stomach → back sleep nudge; back → rotating asymmetry tips (Wed–Sun style rotation in spec).

## BONE NUTRITION

**Not daily unless opted in.** One meal-time ping (**wake+1h or wake+5h**) with D3/K2/Mg/Zn/Boron/Collagen copy. **No nag** if not opted in.

## PROGRESSION SUMMARY

- Masseter / neck: week bands per spec; TMJ and pain rules override.  
- Mewing / nasal: **no** auto progression; hard mewing **only** if user toggles (adds holds to morning).  
- Facial: shorten after 5-day skip streak.

## MONTHLY CHECK-IN

**1st of month at midday** (same midpoint as mewing midday): photos + neck tape + jaw feel + TMJ month summary; branch responses per spec (stronger/same/weaker + TMJ).

## NOTIFICATION BUDGET & PHASES

**Problem:** Full stack = 9–11+/day — too many.

**Phase rollout (AI chooses starting phase from `weeks_on_routine` or default phase 1):**

- **Phase 1 (weeks 1–2):** Mewing 3 + Masseter 2 (session + recovery) + Symmetry 1 → **~6/day**  
- **Phase 2 (weeks 3–4):** Phase 1 + Facial 1 + Nasal 1 → **~8/day**  
- **Phase 3 (week 5+):** Phase 2 + Neck (workout days) + Fascia 2 (morning + evening 4–5×) + Nutrition if opted in → real average **~8–9** after evening skips  

**Skinmax + BoneMax:** merge **morning** (mewing reset + skin AM) and **evening** (mewing night + skin PM) into **combined** notifications when same window.

**Hard cap: 10 notifications/day** across all modules. If over, drop lowest priority first: hydration (Skinmax), meal chewing reminders, second drainage session, etc.

**Snooze / skip:** 30 min snooze; skip = no nag; **7 days** inactive on a module → one check-in message offering to turn module off.

---

## NOTIFICATION COUNT TABLE (planning)

| Module | Typical daily slots | Notes |
|--------|---------------------|--------|
| Mewing | 3 | Daily |
| Masseter | 2 | Session + recovery check |
| Facial | 1 | Daily |
| Fascia | 2 | PM 4–5×/week |
| Nasal | 1 (2 if high screen) | Daily |
| Neck | 1 | Workout days only |
| Symmetry | 1 | Daily |
| Bone nutrition | 1 | Only if opted in |
| Monthly | 1 | 1st only |

Use **phases** and **merges** to stay under caps.
