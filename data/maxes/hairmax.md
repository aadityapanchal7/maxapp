---
maxx_id: hairmax
display_name: Hair
short_description: Healthy scalp, right-cut hair, optional loss prevention.

schedule_design:
  cadence_days: 14
  am_window: ["wake+0:10", "wake+1:00"]
  pm_window: ["sleep-2:00", "sleep-0:15"]
  daily_task_budget: [1, 5]
  intensity_ramp:
    week_1: [0.0, 0.6]
    week_2: [0.4, 1.0]
  skeleton:
    blocks:
      # Wash cadence depends on hair_type: curly 1×/wk + co-wash, others 2×/wk.
      - id: wash_curly
        slot: am_active
        cadence: n_per_week=1
        if: "hair_type == curly"
        tasks: [hair.shampoo_wash]
      - id: cowash_curly
        slot: am_active
        cadence: n_per_week=1
        if: "hair_type == curly"
        tasks: [hair.cowash_curly]
      - id: wash_default
        slot: am_active
        cadence: n_per_week=2
        if: "hair_type in [straight, wavy]"
        tasks: [hair.shampoo_wash]
      # Hydration / leave-in only for wavy/curly or dry scalp.
      - id: leavein
        slot: am_active
        cadence: n_per_week=2
        if: "hair_type in [wavy, curly] or scalp_state == dry"
        tasks: [hair.leavein]
      # Daily styling track.
      - id: style_daily
        slot: am_active
        cadence: daily
        if: "daily_styling == true"
        tasks: [hair.style_product]
      - id: heat_protect
        slot: am_active
        cadence: daily
        if: "heat_styling == true"
        tasks: [hair.heat_protect]
      - id: product_rinse
        slot: pm_close
        cadence: n_per_week=2
        if: "daily_styling == true"
        tasks: [hair.product_rinse_pm]
      # Always-on circulation.
      - id: scalp_massage
        slot: am_open
        cadence: n_per_week=5
        tasks: [hair.scalp_massage]
      # Loss-prevention track. Active = both AM+PM minox; observing/family = none.
      - id: minox_am
        slot: am_open
        cadence: daily
        if: "hair_loss_signs in [yes_active, yes_observing] and minoxidil_using != false"
        tasks: [hair.minoxidil_am]
      - id: minox_pm
        slot: pm_close
        cadence: daily
        if: "hair_loss_signs == yes_active and minoxidil_using != false"
        tasks: [hair.minoxidil_pm]
      # Microneedle ONCE per week, on a day with no minox (handled by scheduler).
      - id: microneedle
        slot: pm_active
        cadence: n_per_week=1
        if: "hair_loss_signs in [yes_active, yes_observing] and dermaroller_owned == true and scalp_state != sensitive"
        not_with_same_day: [hair.minoxidil_am, hair.minoxidil_pm]
        tasks: [hair.microneedle_pm]
      - id: finasteride
        slot: flexible
        cadence: daily
        if: "finasteride_using == true"
        tasks: [hair.finasteride_reminder]
      - id: scalp_check
        slot: flexible
        cadence: weekly_on=sunday
        if: "hair_loss_signs in [yes_observing, no_but_family]"
        tasks: [hair.scalp_check]
      - id: beard_trim
        slot: am_active
        cadence: n_per_week=2
        if: "facial_hair_growing == true"
        tasks: [hair.beard_trim]
      - id: haircut_book
        slot: flexible
        cadence: monthly_on=1
        tasks: [hair.haircut_book]
      # --- Density layer: anti-fungal wash, deep condition, progress photo,
      # monthly check-in. These give the user a real protocol — not just
      # one minox reminder per day.
      - id: ketoconazole_wash
        slot: am_active
        cadence: n_per_week=2
        if: "scalp_state in [oily, dry]"
        tasks: [hair.ketoconazole_wash]
      - id: deep_condition_weekly
        slot: pm_active
        cadence: n_per_week=1
        if: "heat_styling in [sometimes, often] or hair_type in [wavy, curly]"
        tasks: [hair.deep_condition]
      - id: progress_photo_biweekly
        slot: am_open
        cadence: weekly_on=sunday
        if: "hair_loss_signs in [yes_active, yes_observing, no_but_family]"
        tasks: [hair.progress_photo]
      - id: monthly_review
        slot: midday
        cadence: monthly_on=1
        tasks: [hair.monthly_review]
      - id: bloodwork_quarterly
        slot: flexible
        cadence: monthly_on=1
        if: "current_treatment in [oral_topical, full_stack]"
        tasks: [hair.bloodwork_check]

required_fields:
  - id: hair_type
    question: "Which best describes your hair?"
    type: enum
    options:
      straight: "Lies flat, gets oily fast"
      wavy: "Loose S-bends"
      curly: "Tight spirals"
    required: true
    why: "Wash cadence and product choice depend entirely on this."

  - id: hair_loss_signs
    question: "Have you noticed any temple recession, crown thinning, or excess shedding?"
    type: enum
    options:
      yes_active: "Yes — and I want to act on it"
      yes_observing: "Maybe — I'm not sure yet"
      "no": "No"
      no_but_family: "No, but it runs in my family"
    required: true
    why: "Determines whether the loss-prevention track activates (minoxidil/microneedle/finasteride reminders)."

  - id: scalp_state
    question: "How does your scalp usually feel?"
    type: enum
    options:
      oily: "Oily, gets greasy fast"
      dry: "Dry, sometimes flaky / itchy"
      normal: "Comfortable, no issues"
      sensitive: "Reactive — irritated by many products"
    required: true
    why: "Drives shampoo choice + wash frequency."

  - id: daily_styling
    question: "Do you style your hair daily with product (clay / pomade / cream)?"
    type: yes_no
    required: true
    why: "Adds wash-out reminders and a styling task."

  - id: current_treatment
    question: "Are you on any hair-loss treatments right now?"
    type: enum
    options:
      none: "Nothing yet"
      topical_only: "Topical minoxidil (Rogaine / generic)"
      oral_topical: "Oral finasteride + minoxidil"
      full_stack: "Fin + min + microneedle / dermastamp"
    required: true
    why: "Decides where to start the user — none = ramp from baseline, full_stack = maintain, drop redundant reminders."

  - id: heat_styling
    question: "Do you use heat styling tools (blow dryer, flat iron, curling iron)?"
    type: enum
    options:
      never: "Never"
      sometimes: "Once or twice a week"
      often: "Most days"
    required: true
    why: "Heat = need protectant task before each session + weekly deep-condition. Often = mandatory protectant; sometimes = lighter cadence."

  - id: dermaroller_owned
    question: "Do you own (or willing to buy) a 0.5mm dermaroller for scalp microneedling?"
    type: yes_no
    required: true
    why: "Gates the weekly microneedling task. If no, suggest hand massage as substitute (less effective but still circulation boost)."

  - id: routine_time_pref
    question: "How much time do you want to spend on hair / scalp care daily?"
    type: enum
    options:
      minimal: "Under 5 min — wash + go"
      standard: "5–15 min — basics + product"
      extensive: "15+ min — full routine, willing to invest"
    required: true
    why: "Drives task density. Minimal = strip to essentials (wash + minox if loss); extensive = layer scalp massage, pre-poo treatments, weekly masks."

optional_context:
  - id: face_shape
    description: "User-stated face shape — biases haircut suggestions"
  - id: current_haircut
    description: "What they have now — relevant for transition advice"
  - id: minoxidil_using
    description: "Already using minox? gates microneedle scheduling — superseded by current_treatment"
  - id: finasteride_using
    description: "On fin/dut already? skip those reminders — superseded by current_treatment"
  - id: facial_hair_growing
    description: "Adds beard care tasks"
  - id: product_preferences
    description: "Specific shampoos/conditioners they like"
  - id: previous_treatments_quit
    description: "Previously tried fin/min and quit — informs sensitivity / pace"
  - id: hair_density_goal
    description: "Maintain vs. regrow vs. transplant-prep — biases aggressiveness"

prompt_modifiers:
  - id: loss_prevention_active
    if: "hair_loss_signs in [yes_active, yes_observing]"
    then: "ACTIVATE loss-prevention track: topical minoxidil 1× or 2×/day, scalp microneedle 1×/wk (NEVER same night as minox, 24hr gap). If finasteride mentioned, daily reminder. Document any irritation."
  - id: family_balding_watchful
    if: "hair_loss_signs == no_but_family"
    then: "Maintenance + scalp-health priority. No minoxidil yet (no current loss). Add monthly photo-check task for early detection."
  - id: curly_low_wash
    if: "hair_type == curly"
    then: "Wash 1–2×/week max. Co-wash midweek. Curl cream + leave-in daily. NO sea salt spray (drying). Minimal brushing."
  - id: oily_scalp_more_wash
    if: "scalp_state == oily and hair_type != curly"
    then: "Wash 3×/week. Sulfate-free or gentle clarifying weekly. Avoid heavy oil-based products."
  - id: dry_sensitive_scalp
    if: "scalp_state in [dry, sensitive]"
    then: "Reduce wash frequency by 1/week from baseline. Conditioner every wash. Avoid sulfates entirely."
  - id: styling_routine
    if: "daily_styling == true"
    then: "Add: pre-style routine (small product, on damp hair), evening rinse if heavy product use 3+ days in a row."
  - id: treatment_none_starter
    if: "current_treatment == none and hair_loss_signs in [yes_active, yes_observing]"
    then: "RAMP TREATMENT: month 1 = topical minoxidil 1×/day (foam, AM only). Month 2 = bump to 2×/day (AM foam + PM liquid). Add finasteride consultation reminder month 2. Month 3+ = consider microneedle if scalp not sensitive."
  - id: treatment_topical_only_advance
    if: "current_treatment == topical_only and hair_loss_signs == yes_active"
    then: "Suggest oral finasteride consultation in month 2 if regrowth plateaus. Continue minoxidil 2×/day. Add microneedle 1×/wk after week 4."
  - id: treatment_full_stack_maintain
    if: "current_treatment == full_stack"
    then: "MAINTENANCE MODE: minox AM + PM, fin daily, microneedle 1×/wk. Skip ramp reminders, skip 'consider treatment' nudges. Focus reminders on consistency + monthly progress photo."
  - id: heat_protectant_required
    if: "heat_styling == often"
    then: "Add heat protectant spray task BEFORE every styling session. Add weekly deep-condition mask (hydrating, not protein — protein on damaged hair makes it brittle). Recommend 2-month break from heat 1×/yr."
  - id: heat_occasional
    if: "heat_styling == sometimes"
    then: "Heat protectant on heat days only. Bi-weekly deep-condition. Lower priority than treatment / wash routine."
  - id: dermaroller_microneedle
    if: "dermaroller_owned == true and hair_loss_signs in [yes_active, yes_observing] and scalp_state != sensitive"
    then: "Schedule microneedle 1×/week PM (NEVER same night as minoxidil — 24hr gap). Pre-clean scalp with alcohol wipe. Apply minox 24hr later. Replace dermaroller every 3 months."
  - id: routine_minimal_strip
    if: "routine_time_pref == minimal"
    then: "STRIP to essentials: wash + condition + (minox if loss-prevention). Skip scalp massage task, skip pre-poo, skip weekly mask. Frame everything as 'this is the floor — anything beyond it is bonus'."
  - id: routine_extensive_layer
    if: "routine_time_pref == extensive"
    then: "FULL ROUTINE: layer scalp massage AM (5 min, fingertip circles), pre-poo oil treatment 1×/wk, weekly hydration mask, monthly clarifying wash. Add daily scalp tonic if oily."
---

# Why hair matters for attractiveness

Hair is one of the highest-leverage aesthetic variables for men. It sits directly on the frame of the face — small changes in cut, length, or texture noticeably change how facial structure is perceived. The difference between average and put-together is often just the right haircut and a maintenance routine, not better genetics.

Most men who think they have "bad hair" actually have one of three problems: wrong cut for their face shape, poor side fullness, or no maintenance routine. The right haircut balances proportions, enhances bone structure, and makes daily styling easier.

## How hair frames the face

- Tighter sides → slimmer, more structured face
- Fuller sides → wider, softer
- More volume on top → vertical height, elongates face
- Fringes / curtains → shorten perceived face length

Same haircut looks great on one person, terrible on another. Goal: choose a style that balances your face shape, not chase trends.

## How hair affects perceived bone structure

Haircuts don't change bone — they change how it's perceived.

- Tighter sides → sharper jawline
- Texture on top → cheekbone definition
- Softer, fuller styles → reduce harshness on very angular faces
- Fringes → draw attention away from longer midface or forehead

# Common hair mistakes

**Wrong haircut for face shape.** Copying popular styles without considering proportions exaggerates flaws.

**Over-fading.** Tight fades sharpen structure but don't suit every face. Some shapes need medium/fuller sides for balance.

**Bad product use.** Wrong product or too much → flat, greasy, dull. Stacking products without washing builds buildup.

**Ignoring scalp.** Hair quality starts at the scalp. Dryness, dandruff, buildup → frizz, itch, poor texture.

**Aggressive towel drying.** Rubbing damages cuticle → frizz, breakage. Scrunch or pat instead.

**Letting cuts grow out too long.** Short cuts need trimming every few weeks; long needs shaping too.

**Describing instead of showing.** Stylists work visually. Bring 2–3 reference photos with similar hair type.

# Hair types, products, and routine

## Hair texture

**Straight** — lies flat, reflects light, can look shiny but flat. Oils travel down strands fast → gets oily quickly. Best with texture powder, clay, pomade. Layered cuts add volume.

**Wavy** — loose S-bends. Frizzy if dried wrong, loses definition if over-brushed. Best with sea salt spray, clay, pomade, leave-in.

**Curly** — tight spirals, naturally voluminous. Prone to dryness and frizz without hydration. Best with curl cream, leave-in, minimal brushing.

## Products

**Texture powder** — volume + matte finish. For short, fine, or flat hair wanting lift. Avoid on very dry or curly hair.

**Clay** — natural hold, matte. Medium-length, structured styles, most hair types. Avoid very dry or extremely curly.

**Pomade** — hold + slight shine. Slick-back, controlled styles, medium-thick hair. Avoid fine hair or matte goals.

**Sea salt spray** — enhances waves, adds texture. Wavy hair, medium length, beachy looks. Avoid very dry hair (drying).

**Curl cream** — defines curls, reduces frizz. Curly + thick wavy hair. Avoid very fine hair.

**Leave-in conditioner** — hydration + texture. Almost everyone, especially dry / curly / long. Avoid overuse on very oily hair. Most versatile product.

## Daily styling routine

1. Start with clean or slightly damp hair.
2. Apply small amount of product (less is more).
3. Style with hands or comb.
4. Air dry or low heat.

Using too much product is the most common mistake.

## Wash frequency by hair type

- Straight: 2–3×/week (oils travel fast)
- Wavy: 2–3×/week
- Curly: 1–2×/week, midweek co-wash, weekend rinse

## Product rules

- Use small amounts.
- Wash out styling products every few days.
- Don't layer multiple products without washing.

Buildup → flat, flakey, greasy hair.

## Hydration

- Conditioner after every shampoo.
- Leave-in for ongoing hydration.
- Avoid excessive heat styling.

## Shampoo, conditioner, scalp health

Hair health begins at the scalp. Most "hair problems" are actually scalp problems — frizz, flatness, itch.

Sulfates can strip natural oils if too harsh — many benefit from gentler sulfate-free formulas. Parabens are preservatives; modern formulations often skip them.

Wash too often → dry scalp. Wash too little → buildup, dandruff. Most people do best with **2 washes per week** (adjusted by hair type and scalp state).

# Face shapes and haircuts

The right cut enhances your structure; the wrong one exaggerates imbalance.

Identify face shape from forehead width, cheekbone width, jawline width, overall length.

## Oval

Balanced proportions, slightly wider forehead than chin. Most versatile face shape. Best: textured crop, medium flow, slick back, quiff, taper fades. Medium side fullness. Avoid ultra-aggressive fades that distort balance.

## Round

Similar width and height, soft jaw, full cheeks. Goal: add vertical structure, reduce width. Best: quiff, pompadour, faux hawk, high-volume textured top, short sides. Tight sides reduce facial width. Avoid full sides, bowl cuts, straight fringe.

## Square

Strong jaw, wide forehead, angular structure. Already strong — add texture, don't exaggerate angles. Best: textured crop, side part with movement, short fades, crew cuts. Medium sides. Avoid extremely sharp fades.

## Rectangular / Oblong

Long face, straight cheeks, strong vertical length. Goal: reduce vertical, add horizontal. Best: curtains, textured crop, medium-length layered, natural flow. Fuller sides shorten the face. Avoid tall pompadours, high-volume tops, extremely tight sides.

## Diamond

Wide cheekbones, narrow forehead and jaw. Goal: balance upper face, soften cheekbones. Best: layered medium cuts, textured crops, side-swept fringe, flow styles. Medium-to-full sides. Avoid very tight fades.

## Heart

Wide forehead, narrow chin. Goal: balance the wider top with the narrower bottom. Best: medium textured, fringe styles, side-swept. Medium sides. Avoid extremely short sides (makes forehead look wider).

## Triangle

Wide jaw, narrower forehead. Goal: add volume to upper face. Best: medium-length textured, side-swept, volume on top. Medium sides. Avoid buzz cuts (emphasizes jaw).

The best haircut isn't the trendiest — it balances your face shape, works with your texture, and is easy to maintain.

# Hair loss and prevention

Hair loss is much easier to slow early than to reverse later. Many men ignore early signs and only act once significant recession or thinning has occurred.

## Early signs

- Receding temples (slow backward movement near temples)
- Thinning at the crown
- Miniaturization (thinner, weaker strands before disappearing)
- More visible scalp under bright light
- Excess shedding combined with thinning

When hairline shape or density changes, it's usually androgenetic (male pattern) hair loss.

## Recession patterns

- Temple recession (M-shape)
- Mature hairline (slight, stabilizes)
- Diffuse thinning across the whole scalp
- Crown thinning

Early identification → preventative treatments work much better.

## Treatments

Two categories: growth stimulators and DHT blockers. Most effective protocols combine both.

**Minoxidil** — improves blood flow to follicles, stimulates growth, increases thickness, slows loss. Topical (liquid/foam) or oral (low-dose Rx). For early thinning or recession. Caution if cardiovascular conditions or scalp irritation. Results take several months of consistency.

**Finasteride** — blocks testosterone → DHT conversion (the hormone shrinking follicles). Slows loss, preserves hair, improves thickness. Requires medical supervision. Some users report side effects — consult a doctor.

**Dutasteride** — similar but stronger. Blocks multiple forms of the conversion enzyme. For non-responders to finasteride. Always under medical supervision.

**Microneedling** — small needles stimulate scalp, improve circulation, increase topical absorption (especially minoxidil). Use with topicals for synergistic effect. Improper technique irritates — careful use required.

## Safety

Hair loss treatments affect biology — consult a healthcare professional before starting finasteride, dutasteride, or oral minoxidil. Individual responses vary.

# Facial hair and grooming

Used right, facial hair adds contrast, emphasizes strong features, balances the face. Used poorly, it highlights flaws.

## How facial hair changes structure

- Emphasizes jawline
- Adds contrast to lower face
- Draws attention to chin/mouth
- Reduces appearance of skin imperfections
- Balances proportions

Short beard → defined jaw. Goatee → projects a weak chin, adds contrast for poor zygomatic projection. Stubble → sharper features.

Poor maintenance does the opposite — looks unclean, immature.

## Shave vs grow

Density matters more than coverage. If facial hair doesn't grow evenly within 2–3 weeks, it'll look patchy. Sparse moustaches and incomplete beards make the face look younger. Clean-shaven or light stubble usually beats patchy.

## Beard styles by face shape

- Round: goatee, stubble with tight sides, short boxed beard. Avoid full cheek beards (widens face).
- Long/rectangular: light stubble, fuller cheeks, short beards. Avoid long chin-heavy beards.
- Square: short stubble, short boxed, natural shapes. Avoid extremely sharp lines.
- Weak jaw / soft lower face: goatee, goatee + stubble, short beard emphasizing chin.

## Goatee strategies

Goatees work for weak jaws, longer philtrums, weak chin projection. Shifts attention to the center of the lower face. Must be clean and intentional, not uneven.

## Shaving technique

1. Prep skin (warm water / post-shower) — softens hair, opens pores.
2. Shaving cream or gel — reduces friction.
3. Shave **with the grain**.
4. Light pressure, short strokes.
5. Rinse with cool water.

## Tools

- Razor — closest shave, for clean-shaven looks. Irritation risk if misused.
- Electric trimmer — most versatile. Stubble maintenance, beard shaping, adjustable guards.
- Foil shaver — close shave with less irritation. Great for sensitive skin / razor bump prone.

## Preventing irritation

Causes: shaving against grain too aggressively, dull blades, too much pressure. Fixes: prep, clean blades, soothing post-shave products. Antibacterial or calming sprays help some.

## Neckline placement

Neckline sits about 1–2 fingers above the Adam's apple. Everything below gets shaved. A proper neckline prevents the beard from looking messy.

```yaml task_catalog
- id: hair.shampoo_wash
  title: "Wash + condition"
  description: "shampoo (sulfate-free if scalp is sensitive), condition mid-lengths to ends. don't apply conditioner to scalp."
  duration_min: 5
  default_window: am_active
  tags: [wash, foundation]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Wash frequency by hair type"
  frequency: { type: n_per_week, n: 2 }

- id: hair.cowash_curly
  title: "Co-wash curls"
  description: "conditioner-only wash to refresh curls without stripping. work through with fingers, rinse cool."
  duration_min: 5
  default_window: am_active
  tags: [wash, curly]
  applies_when: ["hair_type == curly"]
  intensity: 0.2
  evidence_section: "Wash frequency by hair type"
  frequency: { type: n_per_week, n: 1 }

- id: hair.leavein
  title: "Apply leave-in"
  description: "small amount of leave-in on damp hair after wash. focuses on mid-lengths and ends."
  duration_min: 1
  default_window: am_active
  tags: [post-wash, hydration]
  applies_when: ["hair_type in [wavy, curly] or scalp_state == dry"]
  intensity: 0.1
  evidence_section: "Hydration"
  frequency: { type: n_per_week, n: 2 }

- id: hair.style_product
  title: "Style with product"
  description: "small amount of clay/pomade/curl cream on damp hair. shape with hands. less is more."
  duration_min: 4
  default_window: am_active
  tags: [styling, am]
  applies_when: ["daily_styling == true"]
  intensity: 0.1
  evidence_section: "Daily styling routine"
  frequency: { type: daily, n: 1 }

- id: hair.product_rinse_pm
  title: "Rinse out product (PM)"
  description: "quick rinse with water before bed if you've worn product 3+ days straight. prevents buildup."
  duration_min: 3
  default_window: pm_close
  tags: [pm, scalp-care]
  applies_when: ["daily_styling == true"]
  intensity: 0.1
  evidence_section: "Product rules"
  frequency: { type: n_per_week, n: 2 }

- id: hair.scalp_massage
  title: "Massage scalp (60s)"
  description: "fingertip massage in circles for 60s. boosts circulation. do dry or with leave-in."
  duration_min: 1
  default_window: am_open
  tags: [scalp, circulation]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "Microneedling"
  frequency: { type: n_per_week, n: 5 }

- id: hair.minoxidil_am
  title: "Apply minoxidil (AM, 1ml)"
  description: "1ml topical minoxidil to thinning areas on dry scalp. wait 2–4 hr before getting hair wet."
  duration_min: 3
  default_window: am_open
  tags: [loss-prevention, active]
  applies_when: ["hair_loss_signs in [yes_active, yes_observing]", "minoxidil_using != false"]
  intensity: 0.6
  evidence_section: "Treatments"
  cooldown_hours: 12
  frequency: { type: daily, n: 1 }

- id: hair.minoxidil_pm
  title: "Apply minoxidil (PM, 1ml)"
  description: "1ml topical minoxidil to thinning areas. wait 30+ min before pillow contact."
  duration_min: 3
  default_window: pm_close
  tags: [loss-prevention, active]
  applies_when: ["hair_loss_signs == yes_active", "minoxidil_using != false"]
  intensity: 0.6
  evidence_section: "Treatments"
  cooldown_hours: 12
  frequency: { type: daily, n: 1 }

- id: hair.microneedle_pm
  title: "Microneedle scalp 0.5mm"
  description: "0.5mm dermaroller across thinning areas, 4 passes per zone. NEVER within 24hr of minoxidil. no products for 4hr after."
  duration_min: 8
  default_window: pm_active
  tags: [loss-prevention, treatment]
  applies_when: ["hair_loss_signs in [yes_active, yes_observing]", "dermaroller_owned == true"]
  contraindicated_when: ["scalp_state == sensitive"]
  intensity: 0.7
  evidence_section: "Microneedling"
  cooldown_hours: 168
  frequency: { type: n_per_week, n: 1 }

- id: hair.finasteride_reminder
  title: "Take finasteride"
  description: "take prescribed finasteride. consistency matters more than timing."
  duration_min: 1
  default_window: flexible
  tags: [loss-prevention, supplement]
  applies_when: ["finasteride_using == true"]
  intensity: 0.1
  evidence_section: "Treatments"
  frequency: { type: daily, n: 1 }

- id: hair.scalp_check
  title: "Photo: scalp + hairline"
  description: "front + crown photos in same lighting. compare monthly. catches loss early."
  duration_min: 2
  default_window: flexible
  tags: [tracking]
  applies_when: ["hair_loss_signs in [yes_observing, no_but_family]"]
  intensity: 0.1
  evidence_section: "Early signs"
  frequency: { type: every_n_days, n: 14 }

- id: hair.beard_trim
  title: "Trim beard / neckline"
  description: "trim with guard. clean neckline 1–2 fingers above adam's apple. with the grain only."
  duration_min: 5
  default_window: am_active
  tags: [grooming, facial-hair]
  applies_when: ["facial_hair_growing == true"]
  intensity: 0.1
  evidence_section: "Neckline placement"
  frequency: { type: n_per_week, n: 2 }

- id: hair.heat_protect
  title: "Apply heat protectant"
  description: "spray on damp hair before blow dryer / iron. prevents cuticle damage."
  duration_min: 1
  default_window: am_active
  tags: [heat, protection]
  applies_when: ["heat_styling == true"]
  intensity: 0.1
  evidence_section: "Hydration"
  frequency: { type: daily, n: 1 }

- id: hair.haircut_book
  title: "Book next haircut"
  description: "short cuts: 3–4 weeks. medium: 5–6 weeks. bring 2–3 reference photos with similar hair type."
  duration_min: 5
  default_window: flexible
  tags: [grooming, planning]
  applies_when: [always]
  intensity: 0.1
  evidence_section: "Common hair mistakes"
  frequency: { type: every_n_days, n: 28 }

- id: hair.ketoconazole_wash
  title: "Ketoconazole shampoo wash"
  description: "lather Nizoral 1% (or 2% Rx) on scalp, leave 5 min, rinse. anti-fungal + DHT-blocker action — supports the loss-prevention stack on top of minoxidil."
  duration_min: 8
  default_window: am_active
  tags: [wash, scalp-health, anti-dandruff]
  applies_when: ["scalp_state in [oily, dry]"]
  intensity: 0.3
  evidence_section: "Scalp health"
  frequency: { type: n_per_week, n: 2 }

- id: hair.deep_condition
  title: "Deep-condition mask"
  description: "leave-in mask (hydrating, NOT protein) on mid-lengths to ends, 10–15 min under shower steam, rinse cool. weekly recovery for heat or curly hair."
  duration_min: 15
  default_window: pm_active
  tags: [conditioning, recovery, weekly]
  applies_when: ["heat_styling in [sometimes, often] or hair_type in [wavy, curly]"]
  intensity: 0.2
  evidence_section: "Hair care basics"
  frequency: { type: n_per_week, n: 1 }

- id: hair.progress_photo
  title: "Photo: hairline + crown"
  description: "wet hair shows density better than dry. same lighting, same angle (front, crown from above, both temples). compare in 30 days, not daily."
  duration_min: 5
  default_window: am_open
  tags: [tracking, progress, biweekly]
  applies_when: ["hair_loss_signs in [yes_active, yes_observing, no_but_family]"]
  intensity: 0.2
  evidence_section: "Hair loss tracking"
  frequency: { type: every_n_days, n: 14 }

- id: hair.monthly_review
  title: "Monthly hair review"
  description: "review this month's photos vs last. thicker / same / thinner? sides showing up? if same after 6+ months, escalate stack with derm. if better, hold the line."
  duration_min: 5
  default_window: midday
  tags: [review, monthly, checkpoint]
  applies_when: [always]
  intensity: 0.2
  evidence_section: "Treatment timelines"
  frequency: { type: every_n_days, n: 30 }

- id: hair.bloodwork_check
  title: "Bloodwork check (quarterly)"
  description: "if on oral fin or dut: total + free T, DHT, estradiol, CBC, LFT. monitors side-effect risk. talk to your prescribing doctor about timing."
  duration_min: 30
  default_window: flexible
  tags: [medical, bloodwork, quarterly]
  applies_when: ["current_treatment in [oral_topical, full_stack]"]
  intensity: 0.5
  evidence_section: "Medication safety"
  frequency: { type: every_n_days, n: 90 }
```
