# SKINMAX NOTIFICATION ENGINE — Reference (authoritative for schedule + SMS copy)

## USER INPUTS (collected at onboarding)

- Wake time (e.g. 7:00 AM)
- Bed time (e.g. 11:00 PM)
- Skin type: oily / dry / combo / normal
- Primary concern: acne / pigmentation / texture / redness / aging
- Secondary concern: optional, same options
- Routine level: none / basic / intermediate
- Outdoor frequency: always / sometimes / rarely
- Dietary restrictions opted in: dairy / sugar / seed oils (any combo or none)

## TIMING LOGIC — when notifications fire

All notification times are computed from the user's wake and bed times. Nothing is hardcoded to generic "morning" or "night" without deriving from wake/sleep.

- **AM Routine** — 15 minutes after wake time (time to get to the bathroom). Example: wake 7:00 → AM at 7:15.
- **SPF Reapply** — 3 hours after AM Routine. Only if outdoor setting is **always** or **sometimes**. If **always**, fire every day. If **sometimes**, ask "Going outside today?" and only fire reapply if they confirm yes (or use `outside_today` when known). If **rarely**, never schedule SPF reapply.
- **Midday Tip** — midpoint between AM Routine time and PM Routine time. Keeps the tip centered in their active day.
- **Hydration Check** — 2 hours after Midday Tip. User can disable in settings (`skin_hydration_notifications` false).
- **PM Routine** — 60 minutes before bed. Example: bed 11:00 PM → PM at 10:00 PM (products absorb before pillow).
- **Restriction Reminder** — at most once per day, at one estimated mealtime: wake+1h, wake+5h, or wake+9h (breakfast / lunch / dinner). Pick one slot per day; rotate. If multiple restrictions opted in, rotate which restriction you mention — never all three in one day.
- **Weekly Exfoliation** — user's chosen day (default Wednesday) at **PM Routine** time. That night the PM task is the exfoliation routine (replaces normal PM). Never retinoid + exfoliant same night.
- **Pillowcase Reminder** — every Sunday at **Midday Tip** time.
- **Monthly Progress Photo** — 1st of month at **Midday Tip** time.
- **Monthly Routine Check-in** — 1st of month, 30 minutes after PM Routine time.
- **Quiet hours** — no notifications between bed time and wake time (wrap across midnight correctly in the user's timezone).

## AM ROUTINE — notification content, by concern

Show exact morning steps in order. Apply **skin type modifiers** below to the moisturizer (and seal if dry).

**Acne:** (1) CeraVe Foaming Facial Cleanser (2) Paula's Choice 2% BHA Liquid — thin layer, dry 2 min (3) Moisturizer per skin type (4) EltaMD UV Clear SPF 46

**Pigmentation:** (1) La Roche-Posay Toleriane Hydrating Cleanser (2) Vitamin C — SkinCeuticals CE Ferulic or The Ordinary Vitamin C 23% (budget) (3) The Ordinary Alpha Arbutin 2% under moisturizer (4) Moisturizer (5) La Roche-Posay Anthelios SPF 50+

**Texture / Scarring:** (1) CeraVe Hydrating Cleanser (2) The Ordinary Niacinamide 10% + Zinc 1% (3) Moisturizer (4) La Roche-Posay Anthelios SPF 50+

**Redness / Sensitivity:** (1) La Roche-Posay Toleriane Gentle Cleanser — fragrance-free (2) The Ordinary Azelaic Acid 10% — skip if flaring (3) Dr. Jart+ Ceramidin Cream as moisturizer (4) EltaMD UV Physical SPF 41 — mineral only

**Aging:** (1) CeraVe Hydrating Cleanser (2) Vitamin C — CE Ferulic or TO 23% (3) The Ordinary Hyaluronic Acid 2% + B5 on damp skin (4) Moisturizer (5) La Roche-Posay Anthelios SPF 50+

**Skin type modifiers:** Oily — CeraVe Daily Moisturizing Lotion; skip oils. Dry — CeraVe Moisturizing Cream; optional TO Squalane seal if very dry. Combo — lotion on oily zones, cream on dry patches. Normal — CeraVe Daily Lotion.

## PM ROUTINE — Retinoid Night vs Rest Night (alternate automatically)

The schedule should encode **either** a retinoid night **or** a rest night per the retinoid ramp (below). User does not manually pick; reflect the correct variant in `title`/`description`.

**Retinoid Night** (by concern) — follow reference for acne (Differin + buffer rules for none/basic or dry), pigmentation/texture/aging (tretinoin strengths), redness (only after 4+ weeks barrier + opt-in; sandwich method).

**Rest Night** (by concern) — acne: BP spot treat; pigmentation: azelaic acid; texture: niacinamide; redness: gentle cleanse + azelaic (skip if flaring) + Cicaplast; aging: double cleanse + HA + PM lotion + squalane.

## RETINOID RAMP SCHEDULE

- **Redness:** no retinoid until 4+ weeks barrier-only + manual opt-in; until then all PMs are rest nights.
- **Not started retinoid:** all rest nights; AI may suggest starting after 2+ weeks on basic routine.
- **Weeks 1–2:** retinoid Mon + Thu only (2×/week).
- **Weeks 3–4:** retinoid Mon, Wed, Fri (3×/week).
- **Weeks 5–8:** every other night.
- **Week 9+:** nightly retinoid unless user pauses.
- **Override:** exfoliation day = always rest night (no retinoid same night).
- **Purge reassurance:** one message ~14 days after retinoid start (copy per reference).

## WEEKLY EXFOLIATION (replaces PM that night)

- **Acne / Texture:** The Ordinary AHA 30% + BHA 2% — max 10 min, rinse, moisturizer only; not inflamed; not adjacent to retinoid night.
- **Pigmentation / Aging:** The Ordinary Glycolic Acid 7% — swipe, leave, moisturize; not retinoid night.
- **Redness:** The Inkey List PHA Toner only if 4+ weeks stable barrier; if flare in last week, rest night instead.

## MIDDAY MICRO-TIPS — rotating 7-day cycle

Mon: hands off face · Tue: water ~3L · Wed: pillowcase · Thu: wipe phone · Fri: stress/cortisol · Sat: sunglasses UV · Sun: diet / inflammation

## RESTRICTION REMINDERS

Max 1/day if opted in. Rotate copy: Dairy (IGF-1) · Sugar (inflammation 48h) · Seed oils (pro-inflammatory).

## COMBO CONCERNS (primary + secondary)

Primary sets retinoid/PM structure; secondary adds AM active if no conflict. Never: BHA + retinoid same session; AHA peel + retinoid same night; BP + retinoid same session. Vitamin C + niacinamide OK (VC first). Azelaic with retinoid OK (AM or rest nights).

## MONTHLY CHECK-IN (1st, PM+30m)

Ask: Better / Same / Worse. Branch per reference (continue, wait 8–12 weeks, upgrade, purge vs simplify to barrier-only 14 days).

## NOTIFICATION BUDGET

- Daily **max** 5 notifications; **min** 3 (AM routine + midday tip + PM routine — always).
- Weekly adds: exfoliation + pillowcase (1–2).
- Monthly adds: photo + check-in (2 on the 1st).
- Restriction: +1/day max if opted in.
- Quiet hours enforced.
- User may snooze 30 min; "skip today" = no nag; do not send follow-up if AM not logged by AM+2h.

---

## AM ROUTINE — full step copy by concern (for task descriptions)

Use these ordered steps in notification text. Apply **skin type modifiers** after.

**Acne:** (1) CeraVe Foaming Facial Cleanser (2) Paula's Choice 2% BHA Liquid Exfoliant — thin layer, let dry 2 min (3) Moisturizer (see skin type) (4) EltaMD UV Clear SPF 46

**Pigmentation:** (1) La Roche-Posay Toleriane Hydrating Cleanser (2) Vitamin C serum — SkinCeuticals CE Ferulic or The Ordinary Vitamin C 23% (budget) (3) The Ordinary Alpha Arbutin 2% — layer under moisturizer (4) Moisturizer (5) La Roche-Posay Anthelios SPF 50+

**Texture / Scarring:** (1) CeraVe Hydrating Cleanser (2) The Ordinary Niacinamide 10% + Zinc 1% (3) Moisturizer (4) La Roche-Posay Anthelios SPF 50+

**Redness / Sensitivity:** (1) La Roche-Posay Toleriane Gentle Cleanser — fragrance-free (2) The Ordinary Azelaic Acid 10% — skip if flaring (3) Dr. Jart+ Ceramidin Cream (this IS the moisturizer) (4) EltaMD UV Physical SPF 41 — mineral only

**Aging:** (1) CeraVe Hydrating Cleanser (2) Vitamin C — CE Ferulic or TO 23% (3) The Ordinary Hyaluronic Acid 2% + B5 on damp skin (4) Moisturizer (5) La Roche-Posay Anthelios SPF 50+

**Skin type modifiers:** Oily — CeraVe Daily Moisturizing Lotion; skip oil/seal. Dry — CeraVe Moisturizing Cream; optional TO Squalane AM seal if very dry. Combo — Daily Lotion on oily zones, Cream on dry patches. Normal — CeraVe Daily Lotion.

## PM — RETINOID NIGHT (by concern)

**Acne:** (1) CeraVe Foaming Cleanser (2) If routine level is none OR skin is dry: CeraVe PM Lotion buffer, wait 10 min (3) Differin adapalene 0.1% — pea-sized, thin layer (4) Wait 20 min (5) CeraVe PM Facial Moisturizing Lotion

**Pigmentation:** (1) CeraVe Hydrating Cleanser (2) Tretinoin 0.025% — thin on completely dry skin (3) Wait 20 min (4) CeraVe PM Lotion

**Texture / Scarring:** (1) CeraVe Hydrating Cleanser (2) Tretinoin 0.05% — thin on dry skin (3) Wait 20 min (4) CeraVe PM Lotion

**Redness / Sensitivity:** Only after 4+ weeks barrier repair + opt-in: (1) LRP Toleriane Cleanser (2) LRP Cicaplast Baume B5 buffer first (3) Tretinoin 0.025% pea-sized over moisturizer — sandwich (4) Wait 20 min (5) Cicaplast again to seal

**Aging:** (1) Oil cleanser — Emma Hardie Moringa Balm (2) CeraVe Hydrating second cleanse (3) Tretinoin 0.025–0.05% on dry skin (4) Wait 20 min (5) CeraVe PM Lotion (6) TO 100% Squalane to seal

**PM skin type:** Dry — always buffer before retinoid. Oily — skip seal/oil. Combo — buffer dry zones only.

## PM — REST NIGHT (by concern)

**Acne:** (1) CeraVe Foaming (2) Benzoyl peroxide 2.5% spot only (3) CeraVe PM Lotion

**Pigmentation:** (1) CeraVe Hydrating (2) The Ordinary Azelaic Acid 10% (3) CeraVe PM Lotion

**Texture:** (1) CeraVe Hydrating (2) TO Niacinamide 10% (3) CeraVe PM Lotion

**Redness:** (1) LRP Toleriane Dermo-Cleanser (2) TO Azelaic 10% — skip if flaring (3) LRP Cicaplast Baume B5

**Aging:** (1) Oil cleanser → CeraVe Hydrating double cleanse (2) TO HA 2% + B5 on damp (3) CeraVe PM (4) TO Squalane

## RETINOID RAMP (decision rules)

Redness: no retinoid until 4 weeks barrier + opt-in — all rest until then. Not started: all rest; may suggest start after 2+ weeks basic routine. Weeks 1–2: Mon+Thu retinoid. Weeks 3–4: Mon Wed Fri. Weeks 5–8: every other night. Week 9+: nightly unless paused. Exfoliation day = always rest. Purge reassurance ~day 14 after start.

## WEEKLY EXFOLIATION (replaces PM that night)

**Acne:** TO AHA 30% + BHA 2% — 10 min max, rinse, moisturizer only; skip if inflamed; not night before/after retinoid.

**Pigmentation:** TO Glycolic 7% — cotton pad, leave on, moisturize; not retinoid night.

**Texture:** Same as acne peel; not same week as microneedling session.

**Redness:** Inkey PHA only if 4+ weeks stable; flare in last week → rest night.

**Aging:** TO Glycolic 7%; not retinoid night.

## MIDDAY TIPS (Mon–Sun)

Mon hands off face · Tue 3L water · Wed pillowcase · Thu phone screen · Fri stress/breaths · Sat sunglasses · Sun diet inflammation

## RESTRICTION COPY

Dairy — IGF-1 / breakouts. Sugar — inflammation 48h. Seed oils — pro-inflammatory cooking.

## COMBO CONCERNS (merge rules)

Primary drives retinoid + PM structure; secondary adds AM active if safe. Conflicts: no BHA + retinoid same session; no AHA peel + retinoid same night; VC + niacinamide OK (VC first); azelaic with retinoid OK (AM or rest); BP + retinoid never same session.

**Examples:** Acne+Pig: AM BHA then Alpha Arbutin; PM retinoid tretinoin; rest night azelaic. Acne+Texture: AM BHA + niacinamide; PM tretinoid; rest BP spot. Pig+Aging: AM VC + Arbutin + HA; PM tretinoin; rest HA + squalane. Redness+Acne: 4 weeks barrier first; then AM azelaic, PM adapalene slow ramp. Redness+Aging: 4 weeks barrier; AM VC if tolerated; PM tretinoin 0.025% sandwich from 1×/week. Texture+Pig: AM VC + Arbutin; PM 0.05% tretinoin; rest azelaic; microneedling when no active acne.

## MONTHLY CHECK-IN RESPONSES

Better → keep plan. Same and under 8 weeks on routine → wait on actives. Same and 8+ weeks → suggest one upgrade (retinoid step, AM active, exfoliation, VC). Worse within 6 weeks of retinoid start → likely purge; drop to 1×/week retinoid. Worse otherwise → 2 weeks cleanser + moisturizer + SPF only; then re-layer actives.
