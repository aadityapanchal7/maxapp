# SKINMAX NOTIFICATION ENGINE — AI Reference (authoritative for schedule generation + SMS / task copy)

Use this document with **USER CONTEXT** from onboarding (wake, bed, skin type, primary/secondary concern, routine level, outdoor frequency, dietary restrictions). Do not invent intake questions the app does not collect; personalize **task titles, descriptions, and timing** from the fields you receive.

---

## USER INPUTS (collected at onboarding)

- Wake time (e.g. 7:00 AM)
- Bed time (e.g. 11:00 PM)
- Skin type: oily / dry / combo / normal
- Primary concern: acne / pigmentation / texture / redness / aging
- Secondary concern: optional, same options
- Routine level: none / basic / intermediate
- Outdoor frequency: always / sometimes / rarely
- Dietary restrictions opted in: dairy / sugar / seed oils (any combo or none)

Optional fields the backend may pass when known: `outside_today`, `skin_hydration_notifications`, `exfoliation_weekday`, retinoid start date / weeks on retinoid (for ramp and purge messaging).

---

## TIMING LOGIC — when notifications fire

All times are **computed from wake and bed**. Nothing is a generic “morning” or “night” without deriving from the user’s schedule.

- **AM Routine** — **15 minutes after wake** (time to get to the bathroom). Example: wake 7:00 → AM 7:15.
- **SPF Reapply** — **3 hours after AM Routine**. Only if outdoor setting is **always** or **sometimes**. If **always**, schedule every day. If **sometimes**, use “Going outside today?” logic and `outside_today` when known; only schedule reapply when appropriate. If **rarely**, **never** schedule SPF reapply.
- **Midday Tip** — **midpoint between AM Routine time and PM Routine time** (keeps the tip centered in the active day).
- **Hydration Check** — **2 hours after Midday Tip**. Omit entirely if user disabled hydration (`skin_hydration_notifications` false).
- **PM Routine** — **60 minutes before bed** (products absorb before pillow). Example: bed 11:00 PM → PM 10:00 PM.
- **Restriction Reminder** — **at most once per day**, at **one** estimated meal slot: **wake+1h**, **wake+5h**, or **wake+9h** (breakfast / lunch / dinner). Vary which slot day-to-day so it does not feel robotic. If multiple restrictions are opted in, **rotate which restriction** you mention — **never all three in one day**.
- **Weekly Exfoliation** — user’s chosen weekday (default **Wednesday**) at **PM Routine** time; that night **replaces** normal PM. **Never retinoid + exfoliant same night.** For acne/texture peels, avoid scheduling exfoliation the night **before or after** a retinoid night when possible.
- **Pillowcase Reminder** — every **Sunday** at **Midday Tip** time.
- **Monthly Progress Photo** — **1st of month** at **Midday Tip** time.
- **Monthly Routine Check-in** — **1st of month**, **30 minutes after PM Routine** time.
- **Quiet hours** — **no** notifications between **bed time and wake time** (handle midnight wrap in user timezone).

### Adherence (do not over-nag)

- User may **snooze 30 minutes** or **skip today** on any routine — **no follow-up nag** for that skipped task.
- If the user **does not log AM routine** by **AM slot + 2 hours**, **do not** send a chase reminder; they already know.

---

## AM ROUTINE — exact steps by concern (use in task `description`)

Apply **skin type modifiers** after the concern-specific steps.

**Acne:** (1) CeraVe Foaming Facial Cleanser (2) Paula's Choice 2% BHA Liquid Exfoliant — thin layer, let dry 2 min (3) Moisturizer per skin type (4) EltaMD UV Clear SPF 46

**Pigmentation:** (1) La Roche-Posay Toleriane Hydrating Cleanser (2) Vitamin C serum — SkinCeuticals CE Ferulic or The Ordinary Vitamin C 23% (budget) (3) The Ordinary Alpha Arbutin 2% — layer under moisturizer (4) Moisturizer (5) La Roche-Posay Anthelios SPF 50+

**Texture / Scarring:** (1) CeraVe Hydrating Cleanser (2) The Ordinary Niacinamide 10% + Zinc 1% (3) Moisturizer (4) La Roche-Posay Anthelios SPF 50+

**Redness / Sensitivity:** (1) La Roche-Posay Toleriane Gentle Cleanser — fragrance-free (2) The Ordinary Azelaic Acid 10% — skip this step if skin is flaring today (3) Dr. Jart+ Ceramidin Cream (**this is the moisturizer** — barrier-heavy) (4) EltaMD UV Physical SPF 41 — mineral only, no chemical filters

**Aging:** (1) CeraVe Hydrating Cleanser (2) Vitamin C serum — SkinCeuticals CE Ferulic or The Ordinary Vitamin C 23% (3) The Ordinary Hyaluronic Acid 2% + B5 on damp skin (4) Moisturizer (5) La Roche-Posay Anthelios SPF 50+

### Skin type modifiers (AM + PM context)

- **Oily:** moisturizer = CeraVe Daily Moisturizing Lotion (lightweight). Skip oil/seal steps.
- **Dry:** moisturizer = CeraVe Moisturizing Cream. Optional The Ordinary Squalane Oil as final AM seal if very dry.
- **Combo:** CeraVe Daily Lotion on oily zones, CeraVe Cream on dry patches.
- **Normal:** CeraVe Daily Lotion.

---

## PM ROUTINE — Retinoid Night vs Rest Night (automatic)

Every PM is **either** Retinoid Night **or** Rest Night from the **retinoid ramp** below. The user does not pick; encode the correct variant in `title` and `description`.

### PM skin type modifiers (retinoid nights)

- **Dry:** always use buffer (moisturizer before retinoid) regardless of routine level.
- **Oily:** skip seal/oil; lighter moisturizer.
- **Combo:** buffer on dry zones only.

### Retinoid Night — by concern

**Acne:** (1) CeraVe Foaming Cleanser (2) If routine level is **none** OR skin type is **dry**: CeraVe PM Lotion buffer, wait 10 min (3) Differin adapalene 0.1% — pea-sized, thin layer (4) Wait 20 min (5) CeraVe PM Facial Moisturizing Lotion

**Pigmentation:** (1) CeraVe Hydrating Cleanser (2) Tretinoin 0.025% — thin on completely dry skin (3) Wait 20 min (4) CeraVe PM Lotion

**Texture / Scarring:** (1) CeraVe Hydrating Cleanser (2) Tretinoin 0.05% — thin on dry skin (3) Wait 20 min (4) CeraVe PM Lotion

**Redness / Sensitivity:** Only after **4+ weeks** barrier repair **and** manual opt-in: (1) La Roche-Posay Toleriane Cleanser (2) La Roche-Posay Cicaplast Baume B5 **first** as buffer (3) Tretinoin 0.025% pea-sized **over** the moisturizer (sandwich) (4) Wait 20 min (5) Cicaplast again to seal

**Aging:** (1) Oil cleanser — Emma Hardie Moringa Balm (2) CeraVe Hydrating second cleanse (3) Tretinoin 0.025–0.05% on dry skin (4) Wait 20 min (5) CeraVe PM Lotion (6) The Ordinary 100% Squalane Oil to seal

### Rest Night — by concern

**Acne:** (1) CeraVe Foaming Cleanser (2) Benzoyl peroxide 2.5% — **spot treat active breakouts only**, not full face (3) CeraVe PM Lotion

**Pigmentation:** (1) CeraVe Hydrating Cleanser (2) The Ordinary Azelaic Acid 10% (3) CeraVe PM Lotion

**Texture:** (1) CeraVe Hydrating Cleanser (2) The Ordinary Niacinamide 10% (3) CeraVe PM Lotion

**Redness:** (1) La Roche-Posay Toleriane Dermo-Cleanser (2) The Ordinary Azelaic Acid 10% — skip if flaring (3) La Roche-Posay Cicaplast Baume B5

**Aging:** (1) Oil cleanser then CeraVe Hydrating Cleanser (double cleanse) (2) The Ordinary Hyaluronic Acid 2% + B5 on damp skin (3) CeraVe PM Lotion (4) The Ordinary Squalane Oil

---

## RETINOID RAMP SCHEDULE — how to choose retinoid vs rest

Track from **retinoid start date** when available; otherwise assume “not started” until onboarding indicates otherwise.

- **Redness concern:** **No retinoid** until **4+ weeks** of barrier-only routine **and** user **opts in**. Until then, **every night = rest night**.
- **Not started retinoid:** **all rest nights**; you may **suggest** starting after **2+ weeks** on a stable basic routine.
- **Weeks 1–2:** retinoid **Mon + Thu** only (2×/week).
- **Weeks 3–4:** retinoid **Mon, Wed, Fri** (3×/week).
- **Weeks 5–8:** retinoid **every other night** (alternate automatically).
- **Week 9+:** retinoid **nightly** unless user pauses / irritation.
- **Override:** **Exfoliation day = always rest night** (never retinoid + exfoliant same night).

### Purge reassurance (~14 days after retinoid start)

Schedule **one** checkpoint-style reminder with copy along these lines: *“Purging is normal during weeks 2–6 on retinoids. Weak skin cells are pushing out faster — that often means it’s working. Don’t quit. If it’s severe, drop to every 3rd night and tell me in chat.”*

---

## WEEKLY EXFOLIATION (replaces PM that night)

At **PM Routine** time on the chosen weekday.

- **Acne:** The Ordinary AHA 30% + BHA 2% Peeling Solution — **10 min max**, rinse, moisturizer only. Skip if inflamed. Not night before/after retinoid.
- **Pigmentation / Aging:** The Ordinary Glycolic Acid 7% Toning Solution — cotton pad, leave on, moisturize. Not a retinoid night.
- **Texture:** Same peel as acne; **not** same week as microneedling session if user does face microneedling.
- **Redness:** The Inkey List PHA Toner — only if **4+ weeks** stable barrier; if flare in last week, use **rest night** instead.

---

## MIDDAY MICRO-TIPS — rotating 7-day cycle (one per day)

Use as **Midday Tip** task body; same rotation for all concerns.

- **Monday:** Hands off your face — bacteria transfer causes breakouts.
- **Tuesday:** Water check — aim for ~3L today. Dehydrated skin looks dull and textured.
- **Wednesday:** Change your pillowcase this week? Dirty fabric causes breakouts and irritation.
- **Thursday:** Wipe your phone screen — it touches your face more than you think.
- **Friday:** Stressed today? Cortisol spikes can flare skin. Take 5 deep breaths.
- **Saturday:** Wearing sunglasses? They protect the thinnest skin on your face from UV.
- **Sunday:** Check your diet today — inflammatory foods often show on skin within 24–48 hours.

---

## RESTRICTION REMINDERS (max 1/day if opted in)

Rotate copy if multiple restrictions:

- **Dairy:** Dairy can spike IGF-1 and trigger breakouts — check what’s in your meal.
- **Sugar:** Added sugar drives inflammation — often shows on skin within ~48 hours.
- **Seed oils:** Many seed oils are pro-inflammatory in excess — check what you’re cooking with or ordering.

---

## COMBO CONCERNS (primary + secondary)

**Primary** drives retinoid choice and overall PM structure. **Secondary** adds an AM active only if **no conflict**.

**Conflict rules**

- BHA and retinoid: **never same session** — BHA AM, retinoid PM.
- AHA peel and retinoid: **never same night** — exfoliation day = rest night.
- Vitamin C and niacinamide: **OK** — layer **vitamin C first**.
- Azelaic acid and retinoid: **OK** — AM or rest nights.
- Benzoyl peroxide and retinoid: **never same session** — BP on rest nights or AM only.
- Microneedling over **active acne:** **never** — only clear, scarred areas.

**Examples**

- **Acne + Pigmentation:** AM BHA then Alpha Arbutin; PM retinoid night tretinoin; rest night azelaic.
- **Acne + Texture:** AM BHA + niacinamide; PM tretinoin; rest BP spot.
- **Pigmentation + Aging:** AM vitamin C + Alpha Arbutin + HA; PM tretinoin; rest HA + squalane.
- **Redness + Acne:** First 4 weeks barrier (redness protocol); then AM azelaic, PM adapalene **slow** ramp from 1×/week.
- **Redness + Aging:** 4 weeks barrier; then AM vitamin C if tolerated; PM tretinoin 0.025% sandwich from 1×/week.
- **Texture + Pigmentation:** AM vitamin C + Alpha Arbutin; PM 0.05% tretinoin; rest azelaic; microneedling when no active acne.

---

## MONTHLY CHECK-IN (1st of month, PM + 30 min)

Ask: **“Been ~30 days — how’s your skin? Better / Same / Worse”**

- **Better:** Keep the current plan. If still on retinoid ramp, advance to the next stage when appropriate. Next check in ~30 days.
- **Same + on routine < 8 weeks:** Most actives need **8–12 weeks** — too early to overhaul; stay consistent.
- **Same + 8+ weeks on routine:** Suggest **one** upgrade: retinoid step/frequency, missing AM active, weekly exfoliation if not doing it, or vitamin C if missing.
- **Worse + within ~6 weeks of retinoid start:** Likely **purge** — normal weeks 2–6; drop retinoid to **1×/week**; if not better in 2 weeks, pause retinoid and simplify.
- **Worse + past 6 weeks on retinoid OR not on retinoid:** **Barrier reset:** 2 weeks **cleanser + moisturizer + SPF only**; then re-introduce actives one at a time.

---

## NOTIFICATION BUDGET

- **Daily max:** 5 notifications | **Daily min:** 3 (**AM + midday + PM** always).
- **Weekly adds:** exfoliation + pillowcase (1–2).
- **Monthly adds:** progress photo + check-in (2 on the 1st).
- **Restriction:** +1/day max when opted in.
- **Quiet hours** always enforced.
