"""Mock creator archetypes for the creator-generation AI-quality eval harness.

Ten archetypes chosen to span the diversity of real creator-max content: rich
structured docs, sparse docs, a non-English doc, an abstract mental-skill
domain, a pathologically huge doc (tests the 4000-char truncation in
`creator_onboarding_service._read_doc_text`), bullet-only notes, and a messy
unstructured transcript. Nothing here touches the DB or network — pure data.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Archetype:
    key: str
    label: str
    maxx_id: str
    display_name: str
    tagline: str
    doc_filename: str
    doc_text: str
    language: str  # "en" | "es" — used to validate output-language matching
    typical_answers: dict  # test-drive style answers keyed by TEST_DRIVE_STEPS ids
    chat_question: str = "What should I do first?"
    notes: str = ""


# ── 1. Skincare guru — rich, structured, ~8k chars ──────────────────────────
def _skincare_doc() -> str:
    sections = [
        (
            "MODULE 1 — THE FOUNDATION ROUTINE (Weeks 1-2)",
            """Every subscriber starts here, no exceptions — even if you've "done skincare
before." The Foundation Routine is two steps, morning and night, for 14 days
straight before we add anything else.

Morning:
1. Gentle gel cleanser (30 seconds, lukewarm water — never hot, it strips
   the barrier and makes everything downstream worse).
2. Broad-spectrum SPF 30+, a full teaspoon for the face and neck. This is
   non-negotiable; every other product in this course is wasted money if you
   skip this step.

Night:
1. Double cleanse only if you wore SPF/makeup that day — oil cleanser first,
   then the gel cleanser.
2. A basic ceramide moisturizer. Nothing active yet. The goal of weeks 1-2 is
   a calm, non-reactive barrier — that's the soil everything else grows in.

Common mistake: subscribers who jump straight to acids or retinoids in week 1
because they're impatient. I will actively tell you to slow down in the chat
if I see this — a compromised barrier makes every active you add later burn,
and you'll blame the product instead of the sequencing.""",
        ),
        (
            "MODULE 2 — INTRODUCING ACTIVES (Weeks 3-6)",
            """Once your skin tolerates the Foundation Routine with zero redness or
tightness for 5 consecutive days, we introduce ONE active at a time, in this
order: niacinamide → azelaic acid → a retinoid → (only if oily/acne-prone)
a BHA.

Niacinamide (weeks 3-4): 5% serum, AM only, under SPF. Watch for pilling —
that means you're using too much or layering too fast; wait 60 seconds
between layers.

Azelaic acid (week 4-5, if tolerating niacinamide): 10% cream, can go AM or
PM. This is the ingredient I get asked about most — it's slower than people
expect. Give it the full 5 weeks before judging whether it's working on
post-inflammatory marks.

Retinoid (week 5-6): start at the lowest strength you can get, PM only,
every third night for the first two weeks (not nightly — that's the #1
reason people "can't tolerate retinoids," they go too hard too fast).
Buffer with your moisturizer if you feel any sting.""",
        ),
        (
            "MODULE 3 — TROUBLESHOOTING (ongoing)",
            """Purging vs. breaking out: purging is small, fast-cycling whiteheads in
areas you ALREADY tend to break out, and it resolves inside 4-6 weeks.
Breaking out is new territory (cheeks, jawline you never had issues with
before) or persists past 6 weeks — that means the product doesn't agree with
you, full stop, and we drop it.

Redness/stinging that doesn't fade in 20 minutes: stop the active, go back
to the Foundation Routine for 3 days, then reintroduce at half frequency.

Plateaus: if you've been consistent for 8+ weeks and progress has stalled,
the answer is almost never "add more products." It's usually one of: (a)
sun exposure creeping back in, (b) a new active fighting with an old one,
or (c) sleep/stress undoing what the routine is doing. I will ask about all
three before I recommend anything new.""",
        ),
        (
            "MODULE 4 — BUDGET & PRODUCT PHILOSOPHY",
            """You do not need expensive products for 90% of this to work. The
formulation matters more than the brand — a $12 niacinamide serum with a
sane pH and stable formulation beats a $60 one with fragrance and alcohol
high on the ingredient list.

What's worth spending more on: sunscreen you'll actually reapply (find one
you like the texture of, that's the real ROI), and a dermatologist visit
once a year for anything a routine can't fix (cystic acne, suspicious moles,
melasma that isn't responding after 3 months).

What's never worth it: 10-step routines, "detox" masks, anything claiming
to work in 3 days. If a subscriber asks about a viral TikTok product, my
answer is always: check the actual ingredient list against what we're
already doing before adding anything.""",
        ),
        (
            "MODULE 5 — SAFETY NOTES",
            """This course is not a substitute for a dermatologist. Anyone with
diagnosed eczema, rosacea, or cystic acne should loop in a dermatologist
before starting actives — I'll say this every time it's relevant, not just
here. Pregnant or breastfeeding subscribers should skip retinoids and
high-strength salicylic acid entirely; niacinamide and azelaic acid are
considered safe but I still tell people to confirm with their OB.

If anything on this routine ever causes swelling, blistering, or spreads
past the application site, that's a stop-and-see-a-doctor situation, not a
"wait it out" situation.""",
        ),
        (
            "MODULE 6 — SEASONAL ADJUSTMENTS",
            """Winter: swap the gel cleanser for a cream cleanser once humidity drops —
the same gel that felt fine in summer will strip a cold-weather barrier.
Bump the ceramide moisturizer to a richer formula and consider dropping
retinoid frequency to twice a week if you notice any flaking.

Summer: reapply SPF every 2 hours if you're outside for extended periods,
not just once in the morning — this is the single most common gap I see
even among subscribers who are otherwise doing everything right. Consider a
lighter gel-cream moisturizer if the cream formula feels heavy in humidity.

Travel: pack travel-size Foundation Routine products only, skip actives
entirely for trips under 5 days — the disruption to your routine plus new
water/climate is a recipe for reactive skin, and it's not worth troubleshooting
mid-trip. Resume actives at the frequency you left off at, not from scratch.""",
        ),
        (
            "MODULE 7 — SUBSCRIBER FAQ (most common questions, verbatim style)",
            """"Can I use vitamin C and niacinamide together?" — yes, despite the old
myth; use vitamin C in the morning under SPF, niacinamide can go AM or PM,
just don't layer them in the same exact minute if your skin is sensitive.

"Why did my skin get worse before it got better?" — see the purging section
above; if it's past 6 weeks it isn't purging anymore, it's something not
agreeing with you.

"Do I need a toner?" — no. Toners are almost always an unnecessary extra
step; the only exception is an exfoliating toner, which is just a delivery
method for an acid you could apply directly.

"What order do I apply things in?" — thinnest to thickest consistency,
water-based before oil-based, and always SPF last in the morning.

"Is it okay to mix retinoid and azelaic acid on the same night?" — generally
yes once your skin tolerates both individually, but introduce that
combination slowly, starting at twice a week rather than nightly.

"How long until I see results?" — barrier calm: 1-2 weeks. Texture/tone
improvements from actives: 6-8 weeks minimum. Post-inflammatory marks and
deeper texture: 3-4 months. I say this in almost every chat because
expectation-setting prevents people from quitting at week 3 out of
impatience.""",
        ),
        (
            "MODULE 8 — QUICK INGREDIENT GLOSSARY",
            """Niacinamide: barrier support, oil regulation, brightening. Gentle enough
for daily use once tolerated.

Azelaic acid: anti-inflammatory, helps post-inflammatory marks and mild
rosacea-adjacent redness. Slow but steady — judge it on a 5-week horizon.

Retinoids: the single best-evidenced anti-aging and acne-clearing category
we have, but also the most likely to cause irritation if introduced too
fast. Always PM, always with SPF discipline the next morning.

Salicylic acid (BHA): oil-soluble, good for clogged pores and blackheads.
Only added for oily/acne-prone subscribers per the Module 2 sequencing.

Ceramides: barrier-repair lipids, the backbone of the Foundation Routine
moisturizer. Not an "active," safe to use forever, every skin type.

Hyaluronic acid: humectant, hydration support — apply to damp skin, it pulls
moisture from wherever is wettest, including the air if your skin is drier
than the environment, so always seal it with a moisturizer on top.""",
        ),
    ]
    body = "\n\n".join(f"{h}\n{t}" for h, t in sections)
    header = (
        "THE CLEAR SKIN METHOD — Creator Knowledge Base\n"
        "Author: Mara (skincaremax)\n"
        "Purpose: This is the full protocol reference the AI coach should draw "
        "from when answering subscriber questions. Sequencing matters more than "
        "any single product.\n\n"
    )
    return header + body


SKINCARE = Archetype(
    key="skincare_guru",
    label="Skincare guru — rich structured 8k-char doc",
    maxx_id="skincaremax",
    display_name="Mara",
    tagline="Dermatologist-approved routines without the 10-step nonsense",
    doc_filename="clear_skin_method.txt",
    doc_text=_skincare_doc(),
    language="en",
    typical_answers={
        "goal": "Fix bad habits I've picked up",
        "experience": "Tried it before, didn't stick",
        "time": "10 minutes",
        "schedule": "Morning before work/school",
        "blocker": "Not knowing if I'm doing it right",
    },
)


# ── 2. Fitness coach — week-by-week program doc ─────────────────────────────
FITNESS = Archetype(
    key="fitness_coach",
    label="Fitness coach — week-by-week program doc",
    maxx_id="strengthmax",
    display_name="Deion",
    tagline="Build real strength in 12 weeks — no fluff, no fads",
    doc_filename="twelve_week_strength_program.txt",
    doc_text="""TWELVE-WEEK STRENGTH FOUNDATIONS — Program Overview
Coach: Deion (strengthmax)

WEEK 1-2: MOVEMENT ASSESSMENT & TECHNIQUE
Three full-body sessions per week (Mon/Wed/Fri). Focus entirely on bodyweight
squat, hip hinge, push-up, and row patterns. No added load yet — I want
video-checkable technique before we load anything. 3 sets of 8-10 reps per
movement, 90 seconds rest.

WEEK 3-5: LOAD INTRODUCTION
Add a barbell or dumbbells at a weight where the LAST rep of each set is
still clean. Squat, Romanian deadlift, bench or push-up progression,
inverted row. 4 sets of 6-8. This is where most beginners either quit
(too sore, went too heavy) or plateau immediately (too light, no stimulus) —
the target is "hard but crisp" on every rep.

WEEK 6-8: PROGRESSIVE OVERLOAD BLOCK
Same four lifts, add 2.5-5lbs per session when you complete all sets at the
top of the rep range. Introduce a fifth day of conditioning (10-15 min,
zone 2 pace) for recovery capacity, not fat loss — that's a separate
conversation.

WEEK 9-10: DELOAD
Cut volume by 40%, keep intensity moderate. This is not optional and not a
sign you're behind — everyone deloads here regardless of how the last 8
weeks went. Skipping this is the #1 reason people get hurt in week 11-12.

WEEK 11-12: TESTING BLOCK
Re-test your 5-rep max on squat, deadlift, and bench/push-up equivalent.
Compare to week 1 baseline notes. This becomes the anchor for the next
12-week block.

NUTRITION BASICS (applies every week): protein target is roughly 0.7-1g per
lb bodyweight, spread across meals. I don't hand out calorie targets in this
program — that's a rabbit hole that derails people before they've built the
training habit. Sleep 7+ hours; strength adaptation happens there, not in
the gym.

INJURY / SAFETY NOTE: any sharp joint pain (not muscle soreness) is a stop
signal — deload that specific movement and check form on video before
resuming. This program assumes no pre-existing injuries; anyone with a
current injury should clear it with a physio first.""",
    language="en",
    typical_answers={
        "goal": "Build a foundation from scratch",
        "experience": "Complete beginner",
        "time": "30 minutes",
        "schedule": "Evening after dinner",
        "blocker": "Low motivation after a few days",
    },
)


# ── 3. Chess coach — abstract mental skill ──────────────────────────────────
CHESS = Archetype(
    key="chess_coach",
    label="Chess coach — abstract mental-skill domain",
    maxx_id="chessmax",
    display_name="Ilya",
    tagline="Think three moves ahead — in chess and everywhere else",
    doc_filename="chess_improvement_framework.txt",
    doc_text="""CHESS IMPROVEMENT FRAMEWORK — for 1000-1600 rated players
Coach: Ilya (chessmax)

THE THREE PILLARS
Most plateaued club players over-invest in openings and under-invest in the
other two pillars: tactics (pattern recognition under time pressure) and
endgames (technique with reduced material). My rough allocation for daily
practice time: 50% tactics puzzles, 30% endgame study, 20% opening prep —
inverted from what most players actually do.

DAILY HABIT: PUZZLE RUSH DISCIPLINE
15-20 minutes of tactics puzzles daily, but with a rule: if you get a puzzle
wrong, STOP and figure out why before moving to the next one. Speed-running
puzzles without post-mortem is just pattern exposure without pattern
retention — you'll recognize the puzzle next time, not the underlying motif.

CALCULATION TRAINING
Before moving a piece in a slow game, force yourself to write down (mentally
or literally) the top 2 candidate moves and calculate at least 3 ply deep on
each before comparing. This feels painfully slow at first — that's the
point. Blitz trains pattern recall; calculation training under no time
pressure builds the actual "seeing further" skill that transfers back to
blitz once internalized.

ENDGAME TECHNIQUE PRIORITY ORDER
1. King and pawn endgames (opposition, key squares) — the foundation
   everything else builds on.
2. Rook endgames (Lucena, Philidor positions) — these come up constantly;
   most club games that reach an endgame involve rooks.
3. Basic minor piece endgames (bishop vs knight trade-offs).
Do NOT spend serious study time on theoretical endgames you'll see once a
decade (queen vs. rook, etc.) until the above three are automatic.

OPENING PHILOSOPHY
Pick ONE opening repertoire per color and stick with it for at least 50
games before switching — most improvement at this level comes from
understanding the resulting middlegame structures deeply, not from knowing
more openings shallowly. I don't recommend memorizing more than 8-10 moves
deep for anyone under 1800.

MENTAL GAME
Tilt after a loss is the single biggest rating-killer I see. The rule I give
every subscriber: after any loss, you get ONE more game max, then you stop
for the day. Playing angry costs more rating points than the original loss
did.

TRANSFERABLE FRAMING
When subscribers ask how this applies outside chess, my answer: the
calculation discipline (generate candidates, evaluate before committing) and
the tilt-control rule are the two habits that generalize best to decisions
under pressure in general.""",
    language="en",
    typical_answers={
        "goal": "Level up — I'm not a beginner anymore",
        "experience": "Intermediate — doing some of it already",
        "time": "20 minutes",
        "schedule": "Flexible — varies day to day",
        "blocker": "Low motivation after a few days",
    },
)


# ── 4. Spanish-language creator — doc entirely in Spanish ───────────────────
SPANISH = Archetype(
    key="spanish_creator",
    label="Spanish-language creator — doc entirely in Spanish",
    maxx_id="disciplinamax",
    display_name="Renata",
    tagline="Disciplina diaria para una vida que realmente quieres",
    doc_filename="metodo_disciplina_diaria.txt",
    doc_text="""EL MÉTODO DE DISCIPLINA DIARIA — Base de Conocimiento
Creadora: Renata (disciplinamax)

FASE 1 — LA RUTINA MÍNIMA (Semana 1-2)
Todo empieza con tres hábitos innegociables, sin excepción: despertarse a la
misma hora todos los días (incluyendo fines de semana, con máximo 1 hora de
diferencia), diez minutos de planificación por la mañana escribiendo las tres
tareas más importantes del día, y una caminata de 15 minutos sin teléfono.
No agregamos nada más hasta que estos tres se sientan automáticos, usualmente
entre 10 y 14 días.

Error común: la gente quiere agregar meditación, ejercicio intenso, lectura y
dieta todo en la misma semana. Eso garantiza el fracaso. La disciplina se
construye con victorias pequeñas y consistentes, no con cambios drásticos
que no se sostienen después de la primera semana difícil.

FASE 2 — BLOQUES DE ENFOQUE (Semana 3-6)
Una vez que la rutina mínima es automática, introducimos bloques de trabajo
profundo: 90 minutos sin notificaciones, sin redes sociales, con UNA sola
tarea. Empezamos con un bloque al día y subimos a dos hacia la semana 6.

La resistencia que vas a sentir en los primeros 20 minutos de cada bloque es
normal — se llama "fricción de arranque" y desaparece con la repetición, no
esperando a sentir motivación antes de empezar.

FASE 3 — REVISIÓN SEMANAL (continuo)
Cada domingo, 20 minutos: ¿qué funcionó?, ¿qué no?, ¿qué ajusto para la
próxima semana? Esta revisión es más importante que cualquier hábito nuevo
que quieras agregar — sin ella, repites los mismos errores sin darte cuenta.

CUÁNDO PARAR Y DESCANSAR
Si llevas más de 5 días seguidos sin dormir al menos 7 horas, la prioridad
cambia: dormir, no productividad. La disciplina sin descanso se convierte en
agotamiento, y el agotamiento es lo que hace que la gente abandone el método
por completo en la semana 4 o 5.

NOTA DE SEGURIDAD
Este método no sustituye ayuda profesional. Si la falta de disciplina viene
acompañada de síntomas de depresión o ansiedad persistente, la recomendación
siempre es hablar con un profesional de salud mental antes de seguir con
cualquier rutina de productividad.""",
    language="es",
    typical_answers={
        "goal": "Fix bad habits I've picked up",
        "experience": "Tried it before, didn't stick",
        "time": "20 minutes",
        "schedule": "Morning before work/school",
        "blocker": "Forgetting / no routine",
    },
    chat_question="¿Qué debería hacer primero?",
    notes="Validates output-language matching against the source doc's language (Spanish).",
)


# ── 5. Sparse creator — 2-sentence doc ──────────────────────────────────────
SPARSE = Archetype(
    key="sparse_creator",
    label="Sparse creator — 2-sentence doc",
    maxx_id="focusmax",
    display_name="Theo",
    tagline="One habit at a time",
    doc_filename="notes.txt",
    doc_text=(
        "I help people build one focus habit at a time instead of overhauling "
        "everything at once. Start with a single 10-minute daily block and don't "
        "add anything new until it's automatic."
    ),
    language="en",
    typical_answers={
        "goal": "Build a foundation from scratch",
        "experience": "Complete beginner",
        "time": "10 minutes",
        "schedule": "Flexible — varies day to day",
        "blocker": "Forgetting / no routine",
    },
    notes="Almost no source material — stress-tests hallucination under thin context.",
)


# ── 6. Mega-doc creator — ~60k chars (tests 4000-char truncation) ──────────
def _megadoc() -> str:
    topics = [
        ("Cash flow forecasting", "Build a rolling 13-week cash forecast so surprises never blindside you."),
        ("Zero-based budgeting", "Every dollar gets a job before the month starts, not after it's spent."),
        ("Debt avalanche vs. snowball", "Avalanche saves more interest; snowball keeps motivation — pick by temperament, not just math."),
        ("Emergency fund sizing", "3-6 months of essential expenses, held in a boring high-yield account, not invested."),
        ("Automating savings", "Move money the day it lands, before you see it in checking — willpower is not a savings strategy."),
        ("Investing basics", "Low-cost index funds first; individual stock picking is a hobby, not a plan."),
        ("Tax-advantaged accounts", "Max the employer match before anything else — it's an immediate 100% return."),
        ("Lifestyle creep", "Every raise, bank half of it before your spending adjusts upward to match it."),
        ("Time-blocking", "Calendar the deep work before the meetings fill every gap by default."),
        ("The two-minute rule", "If it takes less than two minutes, do it now instead of adding it to a list."),
        ("Weekly review ritual", "Sunday, 30 minutes: what shipped, what slipped, what's the one priority for next week."),
        ("Saying no", "A calendar full of other people's priorities means none of your own get done."),
        ("Energy management", "Match hard tasks to your natural peak-energy window instead of fighting your own rhythm."),
        ("Batch processing email", "Two or three fixed windows a day beats a constantly open inbox tab."),
        ("Systems over goals", "A goal without a system is a wish — the system is what you actually control daily."),
    ]
    case_studies = [
        "a subscriber juggling two jobs found this hardest to sustain on weekends",
        "someone with young kids had to move the block to nap time instead of mornings",
        "a subscriber who travels for work does a lightweight version from hotel rooms",
        "the most common failure mode here is skipping the review, not skipping the action",
        "subscribers who paired this with an accountability partner stuck with it 3x longer",
    ]
    faqs = [
        "\"What if I miss a day?\" — you don't restart from zero, you just resume the next day; missing one day never breaks a streak that matters, missing two in a row usually does.",
        "\"Should I track this in an app?\" — anything with a visible streak works; the tool matters far less than checking it daily.",
        "\"What if this week's habit doesn't fit my schedule?\" — shrink the habit before you skip it entirely; a 2-minute version done daily beats a 20-minute version done never.",
        "\"How do I know if I'm actually improving?\" — the weekly review answers this better than how you feel in the moment; feelings lag reality by about two weeks.",
        "\"Can I combine this week with next week early?\" — no, sequencing exists for a reason; rushing ahead is the most common way subscribers quietly drop the whole program by week 20.",
    ]
    weeks = []
    for i in range(1, 53):
        topic, blurb = topics[(i - 1) % len(topics)]
        case = case_studies[(i - 1) % len(case_studies)]
        faq = faqs[(i - 1) % len(faqs)]
        weeks.append(
            f"WEEK {i} — {topic.upper()}\n"
            f"{blurb} This week's assignment builds directly on week {max(1, i - 1)}: "
            f"revisit what you set up then, measure whether it held for the full 7 days, "
            f"and adjust ONE variable before adding anything new. The subscribers who skip "
            f"this measurement step and stack five new habits at once are the ones who quit "
            f"by week {min(52, i + 6)}.\n"
            f"Journal prompt: where did friction show up this week, and was it a system "
            f"problem or a discipline problem? Ninety percent of the time it's the former.\n"
            f"Field note: {case}. Adjust your own version of this week's habit accordingly "
            f"rather than copying the template rigidly — the principle matters more than the "
            f"exact implementation, and week {i} is a checkpoint, not a finish line.\n"
            f"FAQ: {faq}\n"
        )
    header = (
        "THE FULL FINANCIAL & PRODUCTIVITY MASTERY CURRICULUM\n"
        "Creator: Priya (moneymax)\n"
        "52-week program, uploaded as a single reference document — the AI coach\n"
        "should treat week 1 as the current onboarding priority for new subscribers.\n\n"
    )
    return header + "\n".join(weeks)


MEGADOC_TEXT = _megadoc()

MEGADOC = Archetype(
    key="megadoc_creator",
    label="Mega-doc creator — 60k+ chars (tests 4000-char truncation)",
    maxx_id="moneymax",
    display_name="Priya",
    tagline="Money and momentum — one week at a time",
    doc_filename="full_52_week_curriculum.txt",
    doc_text=MEGADOC_TEXT,
    language="en",
    typical_answers={
        "goal": "Build a foundation from scratch",
        "experience": "Complete beginner",
        "time": "20 minutes",
        "schedule": "Morning before work/school",
        "blocker": "Too busy / unpredictable schedule",
    },
    notes=(
        f"doc is {len(MEGADOC_TEXT)} chars; _read_doc_text truncates to 4000, so only "
        "Week 1 content (cash flow forecasting) should ever reach the model — validation "
        "checks the model doesn't hallucinate content from later weeks it never saw."
    ),
)


# ── 7. Bullet-point-only notes ──────────────────────────────────────────────
BULLETS = Archetype(
    key="bullet_notes",
    label="Bullet-point-only notes creator",
    maxx_id="postureMax".lower(),
    display_name="Sam",
    tagline="Fix your desk posture in 6 weeks",
    doc_filename="posture_notes.txt",
    doc_text="""- Goal: fix forward head posture + rounded shoulders from desk work
- Week 1-2: chin tucks, 3x10 daily, doorway pec stretch 3x30sec
- Week 1-2: set hourly stand-up reminder, minimum 2 min walk
- Week 3-4: add band pull-aparts 3x15, wall angels 3x10
- Week 3-4: monitor should be at eye level, no looking down
- Week 5-6: add face pulls if have access to cable/band, 3x12
- Week 5-6: sleep on back or side only, no stomach sleeping
- Red flag: numbness/tingling down arm = stop, see a doctor, not a posture issue
- Progress check: profile photo every 2 weeks, same spot/lighting
- Common mistake: people only do exercises, ignore the hourly movement break
- Common mistake: doing chin tucks wrong (jutting chin down instead of back)
- Non-negotiable: standing desk or sit-stand alternation if available
- Motivation note: posture change is slow, 6-8 weeks minimum before it's visible
  in photos, don't judge by day 3""",
    language="en",
    typical_answers={
        "goal": "Fix bad habits I've picked up",
        "experience": "Complete beginner",
        "time": "10 minutes",
        "schedule": "Midday breaks",
        "blocker": "Forgetting / no routine",
    },
    notes="Tests whether generation can structure habits from terse bullets rather than prose.",
)


# ── 8. Cooking / nutrition ───────────────────────────────────────────────────
COOKING = Archetype(
    key="cooking_nutrition",
    label="Cooking / nutrition creator",
    maxx_id="mealprepmax",
    display_name="Andre",
    tagline="30-minute meals that actually hit your macros",
    doc_filename="meal_prep_system.txt",
    doc_text="""THE SUNDAY MEAL PREP SYSTEM
Creator: Andre (mealprepmax)

CORE PHILOSOPHY
Meal prep fails when it's boring — people quit rice-and-chicken by week 3.
This system rotates THREE base proteins, THREE base carbs, and FIVE sauces
across the week so every meal is a different combination, same prep time.

SUNDAY PREP BLOCK (90 minutes total)
1. Proteins (30 min): grill or bake chicken thighs, sear a batch of tofu,
   and hard-boil a dozen eggs — three proteins, one session.
2. Carbs (20 min, overlaps with protein cook time): rice cooker for jasmine
   rice, roast a tray of potatoes, cook a batch of farro.
3. Vegetables (20 min): roast two sheet pans of whatever's in season —
   broccoli, peppers, zucchini — high heat, minimal oil.
4. Sauces (20 min): five small jars — chimichurri, tahini-lemon, spicy
   peanut, garlic-yogurt, and a basic vinaigrette. This is what actually
   prevents boredom, not the protein/carb rotation.

DAILY ASSEMBLY (5 minutes)
Pick one protein + one carb + one vegetable + one sauce. That's it — 81
possible combinations from one prep session.

MACRO GUIDANCE (not calorie counting)
Palm of protein, fist of carb, two fists of vegetables, thumb of sauce/fat —
per meal, adjust portions up or down by activity level rather than tracking
grams. I only recommend actual macro tracking for subscribers training for
a specific physique or performance goal, not for general health.

FOOD SAFETY NOTES
Cooked proteins are good in the fridge for 4 days max, freeze what you won't
eat by day 4. Never leave cooked rice at room temp more than 2 hours — it's
one of the highest-risk foods for bacterial regrowth.

BUDGET VERSION
Swap tofu/chicken thighs for a bigger batch of eggs and canned beans; swap
farro for regular rice. Same system, roughly 40% cheaper.

DIETARY ADAPTATIONS
Gluten-free: farro out, quinoa or rice in — no other changes needed.
Vegan: swap chicken for a second tofu prep or tempeh; egg swap is trickier,
I usually recommend marinated chickpeas as the third "protein."
Anyone with diagnosed food allergies should treat this as a starting
template and substitute around their allergen — I'm not a dietitian and
this isn't medical nutrition advice for allergy management.""",
    language="en",
    typical_answers={
        "goal": "Build a foundation from scratch",
        "experience": "Tried it before, didn't stick",
        "time": "45+ minutes",
        "schedule": "Evening after dinner",
        "blocker": "Too busy / unpredictable schedule",
    },
)


# ── 9. Finance / productivity guru ──────────────────────────────────────────
FINANCE = Archetype(
    key="finance_productivity",
    label="Finance / productivity guru",
    maxx_id="wealthbuildmax",
    display_name="Karim",
    tagline="Build wealth on a normal salary — the boring way that works",
    doc_filename="wealth_building_framework.txt",
    doc_text="""THE BORING WEALTH FRAMEWORK
Creator: Karim (wealthbuildmax)

STEP 1 — THE FOUR-ACCOUNT SYSTEM
Checking (bills only), high-yield savings (emergency fund, 3-6 months
expenses), a separate "goals" savings account (vacation, car, etc — anything
under 3 years away), and a brokerage/retirement account for anything 3+
years out. Money flows checking → the other three, automatically, on payday.

STEP 2 — THE PRIORITY ORDER (do these in order, not all at once)
1. Employer 401k match — free money, do this before anything else.
2. High-interest debt (anything above ~7%) — pay this down aggressively,
   it's a guaranteed "return."
3. Emergency fund to 3-6 months.
4. Max tax-advantaged accounts (401k/IRA equivalents).
5. Taxable brokerage — low-cost index funds, not stock picking.

STEP 3 — THE 30-MINUTE MONTHLY REVIEW
First Sunday of the month: check net worth (assets minus debts, one number,
tracked over time — this is the only metric that matters long-term),
confirm automations still fired correctly, and adjust ONE thing if needed.
This is not a budgeting session — that's a weekly, 10-minute habit, separate
from this monthly review.

COMMON MISTAKES I SEE CONSTANTLY
Trying to time the market instead of automating consistent investing.
Keeping too much in checking "just in case" instead of a high-yield account
earning actual interest. Paying down low-interest debt (student loans under
5%) aggressively while ignoring the 401k match — that's leaving money on
the table for a smaller guaranteed win.

ON LIFESTYLE CREEP
Every raise: automatically increase the automated transfer to savings by
half the raise amount BEFORE you see the extra in checking. This is the
single highest-leverage habit in this entire framework.

WHAT THIS FRAMEWORK IS NOT
This isn't personalized financial advice, and I'm not a licensed advisor —
if you have complex situations (business ownership, significant inheritance,
major debt beyond typical consumer debt), talk to a fee-only fiduciary
advisor. This framework is the boring 80% that applies to almost everyone
on a normal salary.""",
    language="en",
    typical_answers={
        "goal": "Build a foundation from scratch",
        "experience": "Complete beginner",
        "time": "20 minutes",
        "schedule": "Morning before work/school",
        "blocker": "Not knowing if I'm doing it right",
    },
)


# ── 10. Messy transcript-style doc ──────────────────────────────────────────
MESSY = Archetype(
    key="messy_transcript",
    label="Messy transcript-style doc — filler words, no structure",
    maxx_id="mindsetmax",
    display_name="Jordan",
    tagline="Mental toughness for regular people",
    doc_filename="raw_transcript.txt",
    doc_text="""okay so um, like, the thing I always tell people right off the bat is that
like motivation is kind of a trap, you know? like everyone's waiting to
"feel motivated" before they start something and that's just, that's
backwards basically. um so what I actually have people do, and this is like
the core of everything I teach, is you pick literally the smallest version
of the habit you can imagine, like embarrassingly small, and you do THAT
every day no matter what, even on the bad days, especially on the bad days
honestly. so like if someone wants to start running they're not gonna run a
5k day one, they're gonna put their shoes on and walk outside for like 60
seconds, that's it, that's the whole habit for like the first two weeks.

and then, um, the other big thing, and I say this to basically every single
subscriber who messages me, is you gotta track it somehow, doesn't matter
how, could be an app, could be literally an X on a calendar, whatever, but
if you're not tracking you're gonna lie to yourself about how consistent
you're being, everyone does, I did it for years before I started tracking
stuff.

so yeah week one is just, small habit, do it daily, track it. week two
same thing but now you can bump the habit up slightly, like maybe the walk
becomes 3 minutes instead of 60 seconds, still tiny though, resist the urge
to go big too fast, that's like the number one way people quit by week
three, they get excited, they 3x the habit, then it feels like a chore again
and they stop entirely.

oh and I should say, like, if someone's dealing with actual depression or
something clinical, this isn't a replacement for that, like this is a
motivation/consistency framework not a mental health treatment, I always
tell people to see an actual professional if what they're describing sounds
like more than just "I lack discipline."

um what else... oh yeah the accountability thing, I think having literally
one other person who knows your daily habit and checks in even just once a
week makes a massive difference, way bigger than people expect, like it's
almost cheating how much that helps versus doing it totally solo.""",
    language="en",
    typical_answers={
        "goal": "Get back on track after falling off",
        "experience": "Tried it before, didn't stick",
        "time": "10 minutes",
        "schedule": "Flexible — varies day to day",
        "blocker": "Low motivation after a few days",
    },
    notes="Unstructured, filler-heavy, first-person spoken style — tests extraction from noise.",
)


ARCHETYPES: list[Archetype] = [
    SKINCARE,
    FITNESS,
    CHESS,
    SPANISH,
    SPARSE,
    MEGADOC,
    BULLETS,
    COOKING,
    FINANCE,
    MESSY,
]
