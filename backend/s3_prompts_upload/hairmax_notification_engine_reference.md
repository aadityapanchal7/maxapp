# HAIRMAX NOTIFICATION ENGINE — AI Reference (authoritative for schedule generation + SMS / task copy)

Use this with **USER CONTEXT** from onboarding (hair type, scalp, daily styling, thinning, tier, fin sensitivity, topical-only path, etc.). Do not add intake questions the app does not ask; **personalize tasks and descriptions** from existing fields.

---

## MODULE 1 — FINASTERIDE (ORAL / TOPICAL)

### Dose insight (AI should know)

Community dose-response: **~0.5 mg ≈ 85–90% of the DHT suppression of 1 mg**. Many users stay on **0.5 mg** for better risk/benefit. Default to the user’s **tier target dose** but **allow staying at 0.5 mg** if they prefer.

### Side-effect ladder (check-in driven)

1. **First report:** Side effects early are often **nocebo-driven**. Studies: ~**43%** of men **told** about potential sides report them vs ~**15%** of uninformed men on the same drug. Advise **2–4 more weeks** — body adjusting.
2. **Second report (2+ weeks later):** **0.25 mg daily** or **0.5 mg every other day**; many retain benefit at lower doses.
3. **Third:** **Topical finasteride** (lower systemic) **or** **pause 2 weeks** then restart **0.25 mg**.

**Sexual sides specifically:** Resolve in **97%+** within **1–2 weeks** of stopping. If continuing → drop dose. Finasteride is not the only path — adjust the stack with a derm.

### Side-effect–sensitive onboarding

If user indicated **“had sides before”** or **“very concerned”:** **skip oral fin**; schedule **topical finasteride daily** — apply to **thinning scalp at night**; lower systemic absorption than oral. Products: Hims topical fin/min combo, compounding pharmacy, or equivalent (user’s products).

### Daily notification (oral path)

**1×/day** — default **wake + 30–45 min** (merge with SkinMax AM when both active per cross-module section).

---

## MODULE 2 — MINOXIDIL

**2×/day** when on full stack (after ramp phase adds minox).

### AM application — **wake + 15 min**

- Foam preferred in AM (less greasy, dries faster).
- Part hair to expose **scalp** in thinning areas.
- **1 ml / half capful** — spread across target zones.
- Dry **15–20 min** before styling.
- **No hair wash for 4+ hours** after.
- Suggested task title example: `HairMax — Minoxidil AM`

### PM application — **bed time − 90 min**

- Liquid OK at night (often cheaper; greasier).
- **1 ml** to scalp in thinning areas.
- Dry **30–60 min** before bed — avoid pillow transfer.
- Suggested task title example: `HairMax — Minoxidil PM`

### Tier framing (wording only — same schedule structure)

- **Tier 1 (Prevention):** Minoxidil **optional** — offer, don’t push: e.g. “You’re not losing yet; fin alone may be enough. Want minox as extra insurance?”
- **Tier 2–3:** Recommend **2×/day** standard.
- **Tier 4:** **Strong** 2×/day. After **6+ months** poor topical response, discuss with derm: some people lack scalp **sulfotransferase** to activate topical minoxidil — **low-dose oral minoxidil** (e.g. 2.5–5 mg) works via liver; **not** self-prescribed.

### Product bands (reference in descriptions when tier/budget known)

- **Minimal:** Kirkland Liquid Minoxidil 5% (AM+PM liquid).
- **Moderate:** Kirkland PM + Rogaine Foam 5% AM.
- **Flexible:** Foam AM+PM, or topical fin/min combo (Hims, Keeps, etc.).

### Rotating scalp micro-tips (use in daily tip task or description footers)

- Apply to **dry** scalp — wet scalp dilutes product.
- Use a comb to **part and expose scalp** — you treat skin, not hair shafts.
- **No blow-dry** immediately after — heat degrades minoxidil.
- Cover **hairline and crown** if both are in play.
- If liquid **irritates**, try **foam** (propylene glycol sensitivity).
- **Wash hands after** — unwanted facial hair if residue transfers.

---

## MODULE 3 — MICRONEEDLING (SCALP)

- **1×/week** on user-chosen day (default **Sunday**), time default **bed − 120 min** or user preference.
- **Post-session:** **~24 h later** — gentle care; **no minoxidil** until safe window (~24h) per protocol.
- **Never same day** as **face** microneedling if SkinMax active — **stagger** (e.g. scalp Sunday, face Wednesday).

---

## PROGRESS PHOTOS & SHED TRACKING

### Bi-weekly progress photos

Same **lighting, angle, distance** each time. **Wet hair** often shows density more clearly than dry.

Suggested angles to mention in checkpoint copy:

1. Hairline (straight on)
2. Crown from above (timer / selfie stick)
3. Left temple
4. Right temple

**Why bi-weekly (not daily):** Daily checks fuel anxiety; hair changes are **months**. Monthly alone misses early shed — bi-weekly balances tracking and sanity.

### Shed tracking (optional, wash days)

On wash days, optional log: shower hair catcher — **Less / Same / More** vs last wash.

- **Weeks 1–3** increase: often **normal early shed** / weak hairs shedding before regrowth.
- **After 6+ months** of stability then **increase:** reassess stack (fin dose, dutasteride, microneedling, oral minox, derm visit).

---

## MODULE 7 — BLOODWORK (CHECKPOINTS, NOT DAILY)

**3× year one**, then **annual** — one task per milestone, not recurring spam.

| When | Trigger |
|------|---------|
| **Baseline** | ~**3 days** after starting **oral** finasteride |
| **6-month** | fin start + **180 days** |
| **Annual** | fin start + **365 days**, then yearly |

**Panel to list in task description:** Total Testosterone, Free Testosterone, DHT, Estradiol (E2), CBC; **liver panel** if oral meds.

---

## KETOCONAZOLE SHAMPOO

**2–3×/week** on wash days — **not** daily. Can double as **anti-dandruff** benefit alongside SkinMax.

---

## DAILY SCALP MICRO-TIP

**1×/day** — short line; rotate application / product / adherence tips (see minoxidil tip list + fin adherence).

---

## TREATMENT RAMP — stagger (schedule generation must respect phase)

Do **not** start everything day 1 unless user is already months into treatment (use `hairmax_months_on_treatment` or equivalent when present).

- **Month 1:** **Finasteride** only (ramp **0.25 → target**). **Ketoconazole** starts immediately. **Daily tip + bi-weekly photo.** **No minoxidil** in schedule yet unless user already on it / override in profile.
- **Months 2–3:** Add **minoxidil 2×/day** (AM wake+15, PM bed−90).
- **Month 4+:** Add **microneedling 1×/week** + **24h follow-up** reminder.
- **Month 6+:** Major review — escalation options: fin **1 mg** if on 0.5 mg, add microneedling if missing, **dutasteride**, **oral minoxidil** if topical failed, **tretinoin + minoxidil** on scalp (derm).
- **Month 12+:** Stable stack; if still unhappy — **transplant** conversation with **“treatment continues after transplant”** framing (native hair still needs DHT control).

---

## MONTHLY CHECK-IN — **1st of month at midday**

Midday = **midpoint(wake+15, bed−60)** (same anchor family as other Maxxes).

Prompt themes: compare photos, hair feel (**Thicker / Same / Thinner / Hard to tell**), sides (**None / Mild / Moderate / Significant**), missed doses (**None / A few / Many**).

**Response branches (embed in description or separate coaching — schedule task should pose the questions):**

- **Thicker + no sides:** Stay the course; don’t change what works.
- **Same + < 6 months on treatment:** 6–12 months for visible change; stabilization often precedes regrowth.
- **Same + 6–12 months:** Verify 2×/day minox + weekly microneedling if prescribed; consider fin step-up or adds per derm.
- **Same + 12+ months full stack:** Stabilized = working; more density → dutasteride, oral minox, transplant (derm).
- **Thinner:** Check consistency; if consistent and still losing → escalate (fin, dut, oral minox, derm).
- **Sides mild:** Often resolve 4–8 weeks; monitor before changing.
- **Sides moderate/significant:** Lowest effective fin dose; if persists 2 weeks → topical fin or 2-week pause (residual suppression).
- **Many missed doses:** Offer simplification — e.g. once-daily combined approach vs nagging.

---

## NOTIFICATION BUDGET & PHASES

| Module | Typical load | Frequency |
|--------|----------------|-----------|
| Finasteride | 1 | Daily (oral path) |
| Minoxidil AM | 1 | Daily (phase 2+) |
| Minoxidil PM | 1 | Daily (phase 2+) |
| Ketoconazole | 1 | 2–3×/week |
| Microneedling | 1 session + ~24h follow-up | 1×/week (phase 3+) |
| Scalp micro-tip | 1 | Daily |
| Progress photo | 1 | Every 2 weeks |
| Bloodwork | 1 | 3× year 1, then annual |
| Monthly check-in | 1 | Monthly (1st, midday) |

**Phase 1 (month 1):** ~**2–3**/day (fin + keto + tip + bi-weekly photo).  
**Phase 2 (mo 2–3):** ~**4–5**/day (+ minox AM+PM).  
**Phase 3 (mo 4+):** ~**4–5**/day + weekly microneedling extras.

Hard cap **10 notifications/day** across **all** active modules.

---

## CROSS-MODULE — HAIRMAX + SKINMAX

- **AM:** cleanser → **minoxidil on scalp** → **15 min** → face actives → moisturizer → SPF. Prefer **one merged** morning block when possible: *“Scalp first, face second.”*
- **PM:** scalp minox → **~30 min dry** → PM skincare; merge when timing aligns.
- **Microneedling:** **never** scalp + face **same day** — stagger.
- **Tretinoin:** same molecule for face and scalp can align **same nights** if user adds scalp tretinoin (derm-directed).
- **Ketoconazole** wash: dandruff crossover for SkinMax.

---

## SNOOZE / SKIP / ADHERENCE

- Snooze **30 min** or skip — no endless nag.
- If **minoxidil PM skipped 5+ consecutive days**, use supportive copy: *“Haven’t done PM minoxidil in a while. Even 1×/day still helps; 2× is stronger. Want to switch to a once-daily routine to make it easier?”* — **adapt**, don’t spam.
