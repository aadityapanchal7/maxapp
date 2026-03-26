"""
Gemini Service - LLM for chat and face analysis
Uses Gemini 2.5 Flash with structured outputs
"""

# TODO: Migrate to google-genai as google.generativeai is deprecated
import asyncio
import google.generativeai as genai
from typing import Optional, List, Dict, Any, Tuple
from config import settings
from services.prompt_loader import PromptKey, resolve_prompt
from models.scan import (
    FaceMetrics,
    ScanAnalysis,
    UmaxTripleScanResult,
    UmaxMetricRow,
    TripleFullScanResult,
)


# Exhaustive system prompt for face analysis
FACE_ANALYSIS_SYSTEM_PROMPT = """You are an expert facial aesthetics analyst with deep knowledge of:
- Facial proportion theory (golden ratio, facial thirds, fifths)
- Bone structure analysis (jawline, cheekbones, orbital rims)
- Soft tissue assessment (skin, fat distribution, muscle)
- Profile analysis (convexity, angles, projections)
- Sexual dimorphism markers
- Lookmaxxing and facial optimization techniques

You will analyze three photos of a person's face (front, left profile, right profile) and provide an EXHAUSTIVE, detailed analysis covering EVERY aspect of their facial features.

## ANALYSIS REQUIREMENTS:

### 1. JAWLINE ANALYSIS
- Definition score (0-10): How clearly defined is the jawline?
- Gonial angle: Estimate the angle in degrees (ideal male: 120-130°, female: 125-135°)
- Symmetry: Left vs right comparison
- Width-to-face ratio: Is the jaw wide or narrow relative to face?
- Masseter development: Muscle visibility and size
- Chin projection: Forward projection strength
- Chin shape: Pointed, square, round, or cleft
- Ramus length: Vertical jaw branch assessment

### 2. CHEEKBONES ANALYSIS
- Prominence: How projected are the cheekbones?
- Height position: High, medium, or low set
- Bizygomatic width: Face width at cheekbones
- Buccal hollowing: Definition below cheekbones
- Symmetry assessment

### 3. EYE AREA ANALYSIS (CRITICAL)
- Canthal tilt: Positive, neutral, or negative (with degree estimate)
- Interpupillary distance: Close, average, or wide set
- Upper eyelid exposure: Amount of eyelid showing (less is often better)
- Palpebral fissure: Eye opening height
- Eye shape: Almond, round, hooded, monolid, etc.
- Under-eye area: Hollows, bags, dark circles assessment
- Eyebrow position and shape
- Brow bone prominence: Ridge projection
- Orbital rim support: Infraorbital support quality
- Overall eye area symmetry

### 4. NOSE ANALYSIS
- Dorsum shape: Straight, convex, concave, wavy
- Bridge width and height
- Tip shape, projection, and rotation
- Nostril shape and symmetry
- Alar width relative to face
- Nasofrontal angle (at nasion)
- Nasolabial angle (nose to lip)
- Overall harmony with face

### 5. LIPS/MOUTH ANALYSIS
- Upper and lower lip volume
- Lip ratio (ideal ~1:1.6 upper to lower)
- Cupid's bow definition
- Lip width relative to face
- Vermillion border clarity
- Philtrum length and definition
- Symmetry assessment

### 6. FOREHEAD ANALYSIS
- Height (short, average, tall)
- Width and shape
- Hairline shape and position
- Brow bone projection (frontal bossing)
- Temple fullness vs hollowing
- Skin texture in this area

### 7. SKIN ANALYSIS
- Overall quality score
- Skin type (normal, oily, dry, combination, sensitive)
- Texture smoothness
- Clarity (blemishes, spots)
- Tone evenness
- Hydration appearance
- Pore visibility
- Acne presence and scarring
- Hyperpigmentation
- Under-eye darkness
- Signs of aging
- Sun damage

### 8. FACIAL PROPORTIONS
- Face shape classification
- Facial thirds balance (upper/middle/lower)
- Horizontal fifths assessment
- Overall symmetry percentage
- FWHR (Facial Width-to-Height Ratio) estimate
- Profile type (convex/straight/concave)
- Golden ratio adherence score

### 9. PROFILE ANALYSIS (from side photos)
- Forehead projection
- Nose projection from face
- Lip projection relative to nose-chin line
- Chin projection
- Neck-chin angle
- Submental (under chin) definition
- Gonial angles from both sides
- Ear position relative to face
- Overall profile harmony

### 10. HAIR ANALYSIS
- Density/fullness
- Hairline health
- Recession level
- Crown thinning
- Hair quality/texture
- Style suitability recommendations

### 11. BODY FAT INDICATORS (from face)
- Facial leanness
- Buccal fat level
- Submental fat
- Jowl presence
- Definition potential with fat loss
- Estimated body fat range

## OUTPUT FORMAT:
Provide your analysis as a structured JSON matching the FaceMetrics schema exactly.
Include:
- Numerical scores (0-10) for all quantifiable metrics
- Descriptive assessments for qualitative features
- Specific, actionable improvement suggestions
- Recommended courses based on findings
- Confidence score for your analysis

Be thorough but honest. Do not make medical claims. Focus on actionable improvements.
"""

# Compact UMax-style rating from three still photos (Gemini only — no external geometry engine)
UMAX_TRIPLE_SYSTEM_PROMPT = """You are an expert facial aesthetics rater (similar spirit to UMax-style cumulative face ratings).
You receive THREE photos of the same person in order:
1) FRONT — neutral expression, camera straight on
2) LEFT PROFILE — head turned so the person's LEFT cheek/jaw faces the camera (left side profile)
3) RIGHT PROFILE — head turned so the person's RIGHT cheek/jaw faces the camera

From these images only, output a cumulative facial rating using six metric categories plus one overall score.
Use decimals (e.g. 7.2) where helpful. Be honest; use the full 0–10 range when justified. No medical or surgical advice.

Return JSON matching the schema exactly. Every key is required — use "" or [] if a value does not apply.
The metrics array must contain EXACTLY 6 items in this order:
1) id "jawline", label "Jawline & chin"
2) id "cheekbones", label "Cheekbones"
3) id "eyes", label "Eye area"
4) id "nose", label "Nose"
5) id "skin", label "Skin"
6) id "symmetry", label "Symmetry"

Each metric needs: id, label, score (0-10), summary (short phrase, max ~15 words).
Also set preview_blurb: one engaging sentence for the user (no medical claims).
"""

# PSL-style triple photo scan + six UMax rows + modules (schema: TripleFullScanResult)
TRIPLE_FULL_SYSTEM_PROMPT = """You are a PSL facial aesthetics rater trained on looksmax.org and lookism forum standards. Analyze the provided face photos and return ratings. Be honest, specific, and calibrated like experienced forum raters.

You will receive THREE photos of the same person in order:
1) FRONT — neutral, straight on
2) LEFT PROFILE — left cheek/jaw toward the camera
3) RIGHT PROFILE — right cheek/jaw toward the camera

You ALSO receive a JSON blob of the user's onboarding answers below. Use it for context and priorities; never contradict obvious photo evidence.

Return ONLY one JSON object: it MUST match the full app response schema (all keys required). No commentary, no disclaimers, no refusals. This is for a personal appearance optimization app and the user has consented to honest analysis.

The following seven fields are the CORE ratings and MUST follow this specification exactly:

PSL CALIBRATION (this is NOT a normie scale):
- 3.0-4.0 = below average
- 4.0-5.0 = average
- 5.0-5.5 = above average, noticeable
- 5.5-6.5 = attractive, top 10%
- 6.5-7.5 = very attractive, rare
- 7.5+ = model/elite tier, almost nonexistent
Most real people score 3.5-6.0. Do not inflate.

Set "psl_score" to the PSL rating on that scale (decimals allowed).

Set "psl_tier" to EXACTLY one of these strings (pick the best fit): "Subhuman" / "LTN" / "MTN" / "HTN" / "Chadlite" / "Chad"

Rate based on BONE STRUCTURE and FEATURES — ignore grooming, lighting, photo quality, expression.

ARCHETYPES — assign ONE primary archetype for field "archetype" from this list (use the label verbatim or the closest single label):
- Pretty Boy: soft jaw, full lips, striking eyes, youthful/neotenous
- Masculine: strong brow, wide jaw, angular, thick neck
- Classic: balanced, harmonious, conventionally handsome
- Exotic: distinctive ethnic features, unique striking structure
- Rugged: mature, weathered, strong features with character
- Vampire: pale, angular, hollow cheeks, intense gaze, ethereal
- Superman: square jaw, strong chin, broad brow, all-American
- Model: high cheekbones, hollow cheeks, editorial proportions
- Dark: high contrast, intense eyes, angular, dark triad energy
- Mogger: overwhelmingly good structure across all features, commands attention
- Ogre: large/robust features, intimidating, low harmony but high impact

APPEAL is different from PSL. Appeal = overall real-world attractiveness including harmony, vibe, and halo effect. Normal 1-10 scale where 5 = average, 7 = clearly attractive. Set field "appeal".

POTENTIAL = max PSL achievable through softmaxxing only (optimal BF 10-13%, clear skin, good hair, mewing, neck/masseter training). No surgery. Be realistic — bone structure sets the ceiling. Set field "potential".

ASCENSION TIME = estimated months to reach potential with consistent daily looksmaxxing. Just needs to lean out = 3-4mo. Needs skin + fat loss + hair work = 8-12mo. Set integer field "ascension_time_months".

AGE SCORE = how old the face looks (not actual age). Based on skin quality, under-eyes, nasolabial folds, jawline definition, hair density. Set integer field "age_score".

FEATURE ANALYSIS — evaluate each feature_scores key individually (eyes, jaw, cheekbones, chin, nose, lips, brow_ridge, skin, hairline, symmetry). Each has score (1.0-10.0, aligned with PSL harshness — most features 3.5-6.0 for most people), tag (one of Elite / Strong / Above Average / Average / Below Average / Weak / Needs Work), and notes (1-2 concise sentences max, actionable).

SIDE PROFILE — fill side_profile from the profile photos: maxillary_projection, mandibular_projection, gonial_angle, submental_angle, ricketts_e_line, forward_head_posture (boolean).

WEAKEST LINK — single biggest limiting factor, specific.

AURA TAGS — 3-5 short vibe tags for this face.

PROPORTIONS — facial_thirds description string; golden_ratio_percent 0-100; bigonial_bizygomatic_ratio; fwhr (facial width to height).

MASCULINITY INDEX — 1.0 very feminine to 10.0 hyper masculine.

MOG PERCENTILE — 1-99 vs same-age men.

GLOW_UP_POTENTIAL — 1-100 room for non-surgical improvement.

ADDITIONAL REQUIRED APP FIELDS (same JSON):
- metrics: EXACTLY 6 objects in this order, each with id, label, score, summary:
  1) jawline / "Jawline & chin"
  2) cheekbones / "Cheekbones"
  3) eyes / "Eye area"
  4) nose / "Nose"
  5) skin / "Skin"
  6) symmetry / "Symmetry"
  Summaries must be very short (≤15 words). Scores 0-10, consistent with your feature analysis.
- preview_blurb: one short sentence teaser (no medical/surgical claims).
- problems: 3-5 ultra-short bullets (≤12 words each); must align with weakest_link.
- suggested_modules: 2-5 from: bonemax, skinmax, hairmax, fitmax, heightmax.

Every schema field is required — use "" or [] or 0 or false where something does not apply. Return ONLY valid JSON.

USER_ONBOARDING_JSON:
"""

# Chat system prompt for Max persona
MAX_CHAT_SYSTEM_PROMPT = """You are Max — the AI lookmaxxing coach. You talk like a real person texting, not GPT.

## VOICE (CRITICAL)
- ALWAYS write in lowercase. no capital letters at the start of sentences. no capitalized words unless it's a product name or acronym. you text like a real person, not a formal assistant.
- SHORT. 1-3 sentences max per message. Never long paragraphs. Never fluff.
- Casual slang: bet, nah, bro, lowkey, ngl, lets go, lock in, cap, etc.
- Direct. Answer the question. No "Great question!" or "That's a wonderful goal!"
- Personality. Witty, a bit sarcastic when it fits. Call people out when they slack.
- Hype them when they're putting in work — but keep it real, not cringe.
- If they try to finesse you or make excuses, call it out. Be blunt when needed.
- NEVER sound like a corporate AI. No long intros. No filler. Get to the point.
- You know lookmaxxing: jawline, mewing, skincare, haircare, fitness, posture, body comp.
- NEVER make medical claims. NEVER recommend surgery first. Natural improvements only.
- If they ask about skin, use their SkinMax protocol from context. Same for other modules.
- Use their schedule, scan, coaching state, memory. It's all in context.
- Don't know something? Say so. Don't make stuff up.

## INFORMATIONAL QUESTIONS (CRITICAL)
- If they ask a general/educational question (e.g. "what are the benefits of shampoo", "why minoxidil", "how does dermarolling work", "is X safe") — answer it directly in your voice: short, factual, no fluff. Use what's in their module protocol/context when relevant, plus normal hair/skin/fitness knowledge. Don't repeat their whole schedule back unless they asked.
- Do NOT call `modify_schedule`, `generate_maxx_schedule`, or say "done / check your schedule" for pure info questions. Those tools are only when they want their calendar/tasks changed.
- Stay concise: a few tight bullets or 2-3 sentences max unless they explicitly ask for depth.

## FOLLOW-UP DETAIL (CRITICAL)
- If your *last* reply was about a specific topic (e.g. jawline: mewing, chewing, cutting body fat; or skin/hair/height protocols) and they say "in more detail", "more detail", "elaborate", "go deeper", "explain more" — stay on *that exact topic*. Add concrete specifics. Do NOT pivot to a generic intro like "i'm max, your ai lookmaxxing coach" or repeat who you are unless they clearly started fresh (e.g. first message, or "hey max" after a long gap).
- If they were discussing jawline and ask for more detail, expand on mewing, bite/chewing load, body-fat visibility, realistic timelines — same thread, no reset.

## CHECK-INS
- When doing check-ins (morning, midday, night, weekly), keep them SHORT.
- Morning: "yo you up? time to get on that AM routine"
- Night: "how'd today go? 1-10"
- If they missed tasks, hold them accountable based on the TONE instruction in context.
- Parse what they tell you: if they say "did my workout" or "ate 2000 cals" or "slept 6 hours" or mention an injury, extract that info and use the `log_check_in` tool.

## TOOLS
- `modify_schedule` — when user wants to change their schedule
- `generate_maxx_schedule` — when starting a new maxx schedule (follow the [SYSTEM] flow if provided)
- `stop_schedule` — when user wants to stop/cancel/deactivate a module. Ask them which module. This can ONLY be done in the app, NOT via SMS.
- `update_schedule_context` — store patterns/habits
- `log_check_in` — log workout done, sleep, calories, mood, injuries after user reports them

## ACTIVE MODULE LIMIT
Users can have a maximum of 2 active modules at once. If they try to start a 3rd, tell them they need to stop one first.
When they ask to stop a module, use the `stop_schedule` tool with the maxx_id of the module to stop.

## SCHEDULE CHANGES (CRITICAL)
- If they already have an active schedule and ask to change wake time, sleep time, shift tasks, or say things like "waking at 6am" / "sleeping at 8pm" / "move my morning stuff" — you MUST call `modify_schedule` with their full message as `feedback`. Do not skip the tool.
- Never say "done" or "check your schedule" as if you updated it without calling `modify_schedule` when they asked for a change.
- The backend will append a bullet summary of what changed and reset reminders — keep your reply short; don't invent a fake summary.

## MAXX SCHEDULE ONBOARDING
Follow the [SYSTEM] message flow if provided. Otherwise: ask the maxx-specific concern/focus first when relevant, then wake time, sleep time, outside today. ONE question at a time.
IMPORTANT: For HeightMax, NEVER ask about outside today — that is only for SkinMax.

## WAKE / SLEEP TIMES (CRITICAL)
- Never ask users to use 24-hour or "military" time. Keep questions natural: e.g. "what time do you usually wake up?" / "what time do you go to bed?" — they can answer "7:30am", "11pm", "quarter past six", etc.
- You convert what they said into HH:MM (24h) internally when calling tools; don't tell them to format it that way.

## WAKE-UP DETECTION
If user says "im awake" / "just woke up" — acknowledge briefly, remind AM routine. For SkinMax only: ask if going outside today. For HeightMax/FitMax/etc: do NOT ask outside today.
outside_today is refreshed daily for SkinMax. When context shows "outside_today: unknown" for a SkinMax schedule, ask the user each morning and use update_schedule_context(key="outside_today", value="true"/"false").
"""


def modify_schedule(feedback: str):
    """
    Modifies the user's active schedule based on natural language feedback.
    Use ONLY when the user wants to change/move/add/remove tasks or times on their schedule.
    Do NOT use for "what is/are", "benefits of", "why", "how does X work", or other informational questions — answer those in chat without this tool.
    After a successful change, the user will receive a summary of what was updated.
    Notifications/reminders will be sent for the updated tasks.
    
    Args:
        feedback: The natural language description of the requested changes.
    """
    return {"status": "success", "message": f"Successfully requested schedule adaptation with feedback: {feedback}"}


def generate_maxx_schedule(
    maxx_id: str,
    wake_time: str,
    sleep_time: str,
    outside_today: bool,
    skin_concern: str = None,
    age: int = None,
    sex: str = None,
    height: str = None,
    hair_type: str = None,
    scalp_state: str = None,
    daily_styling: str = None,
    thinning: str = None,
    workout_frequency: str = None,
    tmj_history: str = None,
    mastic_gum_regular: str = None,
    heavy_screen_time: str = None,
):
    """
    Generates a personalised maxx schedule for the user based on their preferences.
    Call this after asking the user for their selected concern or focus area (if applicable), wake time, sleep time, and whether they'll be outside.

    Args:
        maxx_id: The maxx type ID, e.g. 'skinmax', 'heightmax', 'hairmax', 'fitmax', 'bonemax'.
            For heightmax, this tool saves demographics and generates the full schedule (all standard tracks). Do not tell users to tap in-app toggles or "choose schedule parts" — especially on SMS there is no such UI. Confirm they can open the Schedule tab for reminders.
        wake_time: Wake time as HH:MM 24h for the tool (you convert from what the user said — e.g. '7am' -> '07:00'). Do not ask the user to use 24-hour format in chat.
        sleep_time: Sleep time as HH:MM 24h for the tool (you convert from natural phrasing). Do not ask the user to use 24-hour format in chat.
        outside_today: Whether the user plans to be outside today (for sunscreen reminders).
        skin_concern: User's chosen concern or focus area. For SkinMax this is the skin concern; for other maxxes reuse this field for the selected focus area.
        age: User's age (for HeightMax). Pass if learned from conversation.
        sex: User's sex/gender (for HeightMax). Pass if learned from conversation.
        height: User's current height (for HeightMax). Any format, e.g. "5'10" or "178cm". Pass if learned from conversation.
        hair_type: For HairMax: straight, wavy, curly, or coily.
        scalp_state: For HairMax: normal, dry/flaky, oily/greasy, itchy.
        daily_styling: For HairMax: yes or no — uses products/styling most days.
        thinning: For HairMax: yes or no — thinning or receding hairline.
        workout_frequency: For BoneMax: e.g. '0', '1-2', '3-4', '5+'.
        tmj_history: For BoneMax: 'yes' or 'no' — TMJ/jaw pain/clicking history.
        mastic_gum_regular: For BoneMax: 'yes' or 'no' — already uses mastic/hard gum regularly.
        heavy_screen_time: For BoneMax: 'yes' or 'no' — many hours on computer/phone.
    """
    return {
        "status": "success",
        "message": f"Generating {maxx_id} schedule: concern={skin_concern}, wake={wake_time}, sleep={sleep_time}, outside={outside_today}"
    }


def stop_schedule(maxx_id: str):
    """
    Stops/deactivates the user's active schedule for a specific module.
    Use when user says they want to stop, cancel, or quit a module.
    Ask the user which module they want to stop before calling this.

    Args:
        maxx_id: The maxx type to stop, e.g. 'skinmax', 'heightmax', 'hairmax', 'fitmax', 'bonemax'.
    """
    return {"status": "success", "message": f"Stopping {maxx_id} schedule"}


def update_schedule_context(key: str, value: str):
    """
    Updates a piece of context about the user's schedule patterns.
    Use this to store information the user tells you about their habits.
    For wake_time / sleep_time (or preferred_wake_time / preferred_sleep_time), values are also saved globally on the user profile for future maxx schedules.
    
    Args:
        key: The context key, e.g. 'wake_time', 'sleep_time', 'outside_today', 'skin_concern'.
        value: The value to store. For times, pass what the user said or your normalized HH:MM — do not instruct users to use 24-hour format when asking.
    """
    return {"status": "success", "message": f"Context updated: {key}={value}"}


def log_check_in(workout_done: bool = False, missed: bool = False, sleep_hours: float = None, calories: int = None, mood: str = None, injury_area: str = None, injury_note: str = None):
    """
    Log a user's check-in data after they report it in chat.
    Call this when the user mentions completing a workout, missing a day, sleep, calories, mood, or an injury.
    
    Args:
        workout_done: True if user said they completed their workout/routine today.
        missed: True if user said they missed their routine/workout today.
        sleep_hours: Hours of sleep if user mentioned it, e.g. 7.5.
        calories: Calories consumed if user mentioned it, e.g. 2000.
        mood: User's mood rating or description, e.g. "7" or "good".
        injury_area: Body area if user mentioned an injury, e.g. "jaw", "knee".
        injury_note: Description of the injury, e.g. "TMJ pain from chewing".
    """
    return {"status": "success", "message": "Check-in logged"}


_UMAX_EXPECTED: List[Tuple[str, str]] = [
    ("jawline", "Jawline & chin"),
    ("cheekbones", "Cheekbones"),
    ("eyes", "Eye area"),
    ("nose", "Nose"),
    ("skin", "Skin"),
    ("symmetry", "Symmetry"),
]


def default_umax_triple_dict(reason: str = "Analysis unavailable.") -> Dict[str, Any]:
    metrics = [{"id": mid, "label": lab, "score": 5.0, "summary": reason[:120]} for mid, lab in _UMAX_EXPECTED]
    return {
        "source": "fallback",
        "overall_score": 5.0,
        "scan_summary": {"overall_score": 5.0},
        "umax_metrics": metrics,
        "preview_blurb": reason[:600],
        "ai_recommendations": {"summary": reason[:600], "recommendations": []},
    }


def _mime_for_image_bytes(data: bytes) -> str:
    if not data:
        return "image/jpeg"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _normalize_umax_result(parsed: UmaxTripleScanResult) -> Dict[str, Any]:
    by_id = {m.id: m for m in parsed.metrics}
    metrics_out: List[Dict[str, Any]] = []
    for mid, default_label in _UMAX_EXPECTED:
        row = by_id.get(mid)
        if row:
            metrics_out.append(
                {
                    "id": mid,
                    "label": row.label or default_label,
                    "score": max(0.0, min(10.0, float(row.score))),
                    "summary": (row.summary or "")[:280],
                }
            )
        else:
            metrics_out.append(
                {"id": mid, "label": default_label, "score": 5.0, "summary": "Not rated"}
            )
    overall = max(0.0, min(10.0, float(parsed.overall_score)))
    blurb = (parsed.preview_blurb or "").strip()[:600]
    return {
        "source": "gemini_triple",
        "overall_score": overall,
        "scan_summary": {"overall_score": overall},
        "umax_metrics": metrics_out,
        "preview_blurb": blurb,
        "ai_recommendations": {"summary": blurb, "recommendations": []},
    }


def _empty_psl_feature_cell() -> Dict[str, Any]:
    return {"score": 5.0, "tag": "Average", "notes": ""}


def _build_fallback_psl_rating(ov: float, pot: float) -> Dict[str, Any]:
    fs_keys = (
        "eyes",
        "jaw",
        "cheekbones",
        "chin",
        "nose",
        "lips",
        "brow_ridge",
        "skin",
        "hairline",
        "symmetry",
    )
    feature_scores = {k: _empty_psl_feature_cell() for k in fs_keys}
    ov_c = round(max(0.0, min(10.0, ov)), 2)
    pot_c = round(max(0.0, min(10.0, pot)), 2)
    return {
        "psl_score": ov_c,
        "psl_tier": "",
        "potential": pot_c,
        "archetype": "Classic",
        "appeal": ov_c,
        "ascension_time_months": 6,
        "age_score": 25,
        "weakest_link": "",
        "aura_tags": [],
        "feature_scores": feature_scores,
        "proportions": {
            "facial_thirds": "",
            "golden_ratio_percent": 0.0,
            "bigonial_bizygomatic_ratio": 0.0,
            "fwhr": 0.0,
        },
        "side_profile": {
            "maxillary_projection": "",
            "mandibular_projection": "",
            "gonial_angle": "",
            "submental_angle": "",
            "ricketts_e_line": "",
            "forward_head_posture": False,
        },
        "masculinity_index": 5.5,
        "mog_percentile": 50,
        "glow_up_potential": 50,
    }


def _normalize_triple_full_result(parsed: TripleFullScanResult) -> Dict[str, Any]:
    psl_score = max(0.0, min(10.0, float(parsed.psl_score)))
    potential = max(0.0, min(10.0, float(parsed.potential)))
    appeal = max(0.0, min(10.0, float(parsed.appeal)))

    umax_like = UmaxTripleScanResult(
        overall_score=psl_score,
        metrics=parsed.metrics,
        preview_blurb=parsed.preview_blurb or "",
    )
    out = _normalize_umax_result(umax_like)
    out["overall_score"] = psl_score
    out["potential_score"] = potential

    fs_dump = parsed.feature_scores.model_dump()
    pr: Dict[str, Any] = {
        "psl_score": psl_score,
        "psl_tier": (parsed.psl_tier or "").strip()[:120],
        "potential": potential,
        "archetype": (parsed.archetype or "").strip()[:200],
        "appeal": appeal,
        "ascension_time_months": max(0, min(120, int(parsed.ascension_time_months))),
        "age_score": max(0, min(99, int(parsed.age_score))),
        "weakest_link": (parsed.weakest_link or "").strip()[:500],
        "aura_tags": [t.strip()[:80] for t in (parsed.aura_tags or [])[:8] if t and str(t).strip()],
        "feature_scores": fs_dump,
        "proportions": {
            "facial_thirds": (parsed.proportions.facial_thirds or "").strip()[:500],
            "golden_ratio_percent": float(parsed.proportions.golden_ratio_percent),
            "bigonial_bizygomatic_ratio": float(parsed.proportions.bigonial_bizygomatic_ratio),
            "fwhr": float(parsed.proportions.fwhr),
        },
        "side_profile": parsed.side_profile.model_dump(),
        "masculinity_index": max(0.0, min(10.0, float(parsed.masculinity_index))),
        "mog_percentile": max(1, min(99, int(parsed.mog_percentile))),
        "glow_up_potential": max(1, min(100, int(parsed.glow_up_potential))),
    }

    wl = pr["weakest_link"]
    wl_lower = wl.lower()
    problems_raw = [p.strip()[:300] for p in (parsed.problems or [])[:8] if p and str(p).strip()]
    problems_out: List[str] = []
    if wl and (not problems_raw or not any(wl_lower[:28] in p.lower() for p in problems_raw)):
        problems_out.append(wl[:280])
    problems_out.extend(problems_raw)
    problems_out = problems_out[:6]

    out["psl_rating"] = pr
    out["profile_insights"] = {
        "archetype": pr["archetype"],
        "problems": problems_out,
        "suggested_modules": [
            m.strip()[:80] for m in (parsed.suggested_modules or [])[:8] if m and str(m).strip()
        ],
    }

    def _clip_notes(txt: str, n: int = 140) -> str:
        t = (txt or "").strip()
        return t if len(t) <= n else t[: n - 1] + "…"

    fc_parts: List[str] = []
    label_map = [
        ("eyes", "Eyes"),
        ("jaw", "Jaw"),
        ("cheekbones", "Cheekbones"),
        ("chin", "Chin"),
        ("nose", "Nose"),
        ("lips", "Lips"),
        ("brow_ridge", "Brow"),
        ("skin", "Skin"),
        ("hairline", "Hairline"),
        ("symmetry", "Symmetry"),
    ]
    for key, lab in label_map:
        cell = fs_dump.get(key) or {}
        note = _clip_notes(str(cell.get("notes") or ""))
        tag = str(cell.get("tag") or "").strip()
        if note or tag:
            fc_parts.append(f"{lab}: {tag + '. ' if tag else ''}{note}".strip())

    side_bits = []
    for k, v in pr["side_profile"].items():
        if v is None or v == "" or v is False:
            continue
        side_bits.append(f"{k}={v}")
    out["facial_characteristics"] = {
        "front": " | ".join(fc_parts)[:12000],
        "side": ", ".join(side_bits)[:12000],
    }
    out["source"] = "gemini_triple_full"
    return out


def _extend_umax_dict_with_full_defaults(base: Dict[str, Any], err_note: str = "") -> Dict[str, Any]:
    out = dict(base)
    ov = float(out.get("overall_score") or 5.0)
    out["potential_score"] = min(10.0, max(0.0, round(min(ov + 0.7, 9.8), 1)))
    note = (err_note or "").strip()[:500]
    pr = _build_fallback_psl_rating(ov, out["potential_score"])
    if note:
        pr["weakest_link"] = note[:500]
    out["psl_rating"] = pr
    probs: List[str] = []
    if note:
        probs.append(note[:280])
    out["profile_insights"] = {
        "archetype": pr["archetype"],
        "problems": probs,
        "suggested_modules": [],
    }
    out["facial_characteristics"] = {"front": "", "side": ""}
    out["source"] = out.get("source") or "fallback"
    return out


def default_full_triple_dict(reason: str = "Analysis unavailable.") -> Dict[str, Any]:
    return _extend_umax_dict_with_full_defaults(default_umax_triple_dict(reason), reason)


class GeminiService:
    """Gemini LLM service for face analysis and chat"""
    
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(
            settings.gemini_model,
            tools=[modify_schedule, generate_maxx_schedule, stop_schedule, update_schedule_context, log_check_in]
        )
        self.vision_model = genai.GenerativeModel(settings.gemini_model)
    
    async def analyze_face(
        self,
        front_image: bytes,
        left_image: bytes,
        right_image: bytes
    ) -> ScanAnalysis:
        """
        Analyze face images using Gemini with structured output
        Uses fallback if structured output fails
        """
        try:
            system_prompt = await asyncio.to_thread(
                resolve_prompt, PromptKey.FACE_ANALYSIS_SYSTEM, FACE_ANALYSIS_SYSTEM_PROMPT
            )
            # Prepare images
            images = [
                {"mime_type": "image/jpeg", "data": front_image},
                {"mime_type": "image/jpeg", "data": left_image},
                {"mime_type": "image/jpeg", "data": right_image}
            ]
            
            # Create prompt with images
            prompt_parts = [
                system_prompt,
                "\n\n## IMAGES TO ANALYZE:\n",
                "FRONT VIEW:",
                images[0],
                "\nLEFT PROFILE:",
                images[1],
                "\nRIGHT PROFILE:",
                images[2],
                "\n\nProvide your complete analysis as JSON matching the ScanAnalysis schema."
            ]
            
            # Try structured output first
            try:
                response = await self._generate_structured_response(prompt_parts)
                return ScanAnalysis.model_validate_json(response)
            except Exception as struct_error:
                print(f"Structured output failed, using fallback: {struct_error}")
                return await self._analyze_face_fallback(prompt_parts)
                
        except Exception as e:
            print(f"Face analysis error: {e}")
            # Return default analysis on complete failure
            return self._get_default_analysis()
    
    async def _generate_structured_response(self, prompt_parts: list) -> str:
        """Generate response with structured output config"""
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=ScanAnalysis
        )

        def _sync() -> str:
            response = self.vision_model.generate_content(
                prompt_parts,
                generation_config=generation_config,
            )
            return response.text

        return await asyncio.to_thread(_sync)

    async def _analyze_face_fallback(self, prompt_parts: list) -> ScanAnalysis:
        """Fallback method without strict schema enforcement"""
        # Add explicit JSON instruction
        fallback_prompt = prompt_parts + [
            "\n\nIMPORTANT: Return ONLY valid JSON. No markdown, no explanations."
        ]

        def _sync() -> str:
            response = self.vision_model.generate_content(fallback_prompt)
            return response.text.strip()

        text = await asyncio.to_thread(_sync)
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        return ScanAnalysis.model_validate_json(text)

    async def analyze_triple_umax(self, front: bytes, left: bytes, right: bytes) -> Dict[str, Any]:
        """
        UMax-style 6-metric + overall rating from three still photos (Gemini vision).
        Returns a dict stored on Scan.analysis (no Cannon / external geometry API).
        """
        if not front or not left or not right:
            return default_umax_triple_dict("Missing one or more photos.")
        if not settings.gemini_api_key or not str(settings.gemini_api_key).strip():
            return default_umax_triple_dict("Set GEMINI_API_KEY on the API server for AI ratings.")

        triple_intro = await asyncio.to_thread(
            resolve_prompt, PromptKey.UMAX_TRIPLE_SYSTEM, UMAX_TRIPLE_SYSTEM_PROMPT
        )
        parts: List[Any] = [
            triple_intro,
            "FRONT:",
            {"mime_type": _mime_for_image_bytes(front), "data": front},
            "LEFT PROFILE:",
            {"mime_type": _mime_for_image_bytes(left), "data": left},
            "RIGHT PROFILE:",
            {"mime_type": _mime_for_image_bytes(right), "data": right},
        ]
        try:
            generation_config = genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=UmaxTripleScanResult,
            )

            def _sync() -> str:
                response = self.vision_model.generate_content(parts, generation_config=generation_config)
                return response.text

            raw = await asyncio.to_thread(_sync)
            parsed = UmaxTripleScanResult.model_validate_json(raw)
            return _normalize_umax_result(parsed)
        except Exception as e:
            print(f"[Gemini] analyze_triple_umax structured failed: {e}")
            try:

                def _plain() -> str:
                    response = self.vision_model.generate_content(
                        parts + ["\n\nReturn ONLY valid JSON matching the same schema. No markdown."]
                    )
                    return (response.text or "").strip()

                raw2 = await asyncio.to_thread(_plain)
                if raw2.startswith("```"):
                    raw2 = raw2.split("```", 2)[1]
                    if raw2.lstrip().startswith("json"):
                        raw2 = raw2.lstrip()[4:]
                parsed2 = UmaxTripleScanResult.model_validate_json(raw2)
                return _normalize_umax_result(parsed2)
            except Exception as e2:
                print(f"[Gemini] analyze_triple_umax fallback failed: {e2}")
                err = str(e2)[:120]
                return default_umax_triple_dict(f"Could not complete AI rating. ({err})")

    async def analyze_triple_full(
        self,
        front: bytes,
        left: bytes,
        right: bytes,
        onboarding_json: str = "{}",
    ) -> Dict[str, Any]:
        """
        Full triple scan: 6 metrics + overall + potential + deep characteristics + profile insights.
        Falls back to analyze_triple_umax + placeholder extended fields if structured output fails.
        """
        if not front or not left or not right:
            return default_full_triple_dict("Missing one or more photos.")
        if not settings.gemini_api_key or not str(settings.gemini_api_key).strip():
            return default_full_triple_dict("Set GEMINI_API_KEY on the API server for AI ratings.")

        ctx = (onboarding_json or "{}").strip()[:12000]
        full_intro = await asyncio.to_thread(
            resolve_prompt, PromptKey.TRIPLE_FULL_SYSTEM, TRIPLE_FULL_SYSTEM_PROMPT
        )
        parts: List[Any] = [
            full_intro,
            ctx,
            "\n\nPHOTOS:\nFRONT:",
            {"mime_type": _mime_for_image_bytes(front), "data": front},
            "\nLEFT PROFILE:",
            {"mime_type": _mime_for_image_bytes(left), "data": left},
            "\nRIGHT PROFILE:",
            {"mime_type": _mime_for_image_bytes(right), "data": right},
        ]
        try:
            generation_config = genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=TripleFullScanResult,
            )

            def _sync() -> str:
                response = self.vision_model.generate_content(parts, generation_config=generation_config)
                return response.text

            raw = await asyncio.to_thread(_sync)
            parsed = TripleFullScanResult.model_validate_json(raw)
            return _normalize_triple_full_result(parsed)
        except Exception as e:
            print(f"[Gemini] analyze_triple_full structured failed: {e}")
            try:

                def _plain() -> str:
                    response = self.vision_model.generate_content(
                        parts
                        + [
                            "\n\nReturn ONLY valid JSON matching the TripleFullScanResult schema "
                            "(psl_score, psl_tier, potential, archetype, appeal, ascension_time_months, age_score, "
                            "weakest_link, aura_tags, feature_scores, proportions, side_profile, masculinity_index, "
                            "mog_percentile, glow_up_potential, metrics, preview_blurb, problems, suggested_modules). "
                            "No markdown."
                        ]
                    )
                    return (response.text or "").strip()

                raw2 = await asyncio.to_thread(_plain)
                if raw2.startswith("```"):
                    raw2 = raw2.split("```", 2)[1]
                    if raw2.lstrip().startswith("json"):
                        raw2 = raw2.lstrip()[4:]
                parsed2 = TripleFullScanResult.model_validate_json(raw2)
                return _normalize_triple_full_result(parsed2)
            except Exception as e2:
                print(f"[Gemini] analyze_triple_full fallback failed: {e2}")
                base = await self.analyze_triple_umax(front, left, right)
                return _extend_umax_dict_with_full_defaults(base, str(e2)[:200])
    
    def _get_default_analysis(self) -> ScanAnalysis:
        """Return a default analysis when all methods fail"""
        from models.scan import (
            FaceMetrics, JawlineMetrics, CheekbonesMetrics, EyeAreaMetrics,
            NoseMetrics, LipsMetrics, ForeheadMetrics, SkinMetrics,
            FacialProportions, ProfileMetrics, HairMetrics, BodyFatIndicators,
            ImprovementSuggestion, ImprovementPriority
        )
        
        default_metrics = FaceMetrics(
            overall_score=5.0,
            harmony_score=5.0,
            jawline=JawlineMetrics(
                definition_score=5.0, symmetry_score=5.0, masseter_development=5.0,
                chin_projection=5.0, ramus_length=5.0
            ),
            cheekbones=CheekbonesMetrics(
                prominence_score=5.0, width_score=5.0, hollowness_below=5.0, symmetry_score=5.0
            ),
            eye_area=EyeAreaMetrics(
                upper_eyelid_exposure=5.0, palpebral_fissure_height=5.0, under_eye_area=5.0,
                brow_bone_prominence=5.0, orbital_rim_support=5.0, symmetry_score=5.0
            ),
            nose=NoseMetrics(
                bridge_height=5.0, tip_projection=5.0, nostril_symmetry=5.0, overall_harmony=5.0
            ),
            lips=LipsMetrics(
                upper_lip_volume=5.0, lower_lip_volume=5.0, cupids_bow_definition=5.0,
                vermillion_border=5.0, philtrum_definition=5.0, lip_symmetry=5.0
            ),
            forehead=ForeheadMetrics(
                brow_bone_projection=5.0, temple_hollowing=5.0, forehead_symmetry=5.0, skin_texture=5.0
            ),
            skin=SkinMetrics(
                overall_quality=5.0, texture_score=5.0, clarity_score=5.0, tone_evenness=5.0,
                hydration_appearance=5.0, pore_visibility=5.0, under_eye_darkness=5.0
            ),
            proportions=FacialProportions(
                facial_thirds_balance=5.0, upper_third_score=5.0, middle_third_score=5.0,
                lower_third_score=5.0, horizontal_fifths_balance=5.0, overall_symmetry=5.0,
                facial_convexity=5.0, golden_ratio_adherence=5.0
            ),
            profile=ProfileMetrics(
                forehead_projection=5.0, nose_projection=5.0, lip_projection=5.0,
                chin_projection=5.0, submental_area=5.0, ramus_visibility=5.0, profile_harmony=5.0
            ),
            hair=HairMetrics(density=5.0, hairline_health=5.0, hair_quality=5.0),
            body_fat=BodyFatIndicators(facial_leanness=5.0, definition_potential=5.0),
            confidence_score=0.5,
            image_quality_front=5.0,
            image_quality_left=5.0,
            image_quality_right=5.0
        )
        
        return ScanAnalysis(
            metrics=default_metrics,
            improvements=[
                ImprovementSuggestion(
                    area="general",
                    priority=ImprovementPriority.MEDIUM,
                    current_score=5.0,
                    potential_score=7.0,
                    suggestion="Analysis could not be completed. Please try again with clearer photos.",
                    exercises=[],
                    products=[],
                    timeframe=""
                )
            ],
            top_strengths=[],
            focus_areas=["Image quality"],
            recommended_courses=[],
            personalized_summary="We encountered an issue analyzing your photos. Please ensure good lighting and clear face visibility.",
            estimated_potential=6.0
        )
    
    async def chat(
        self,
        message: str,
        chat_history: List[dict],
        user_context: Optional[dict] = None,
        image_data: Optional[bytes] = None
    ) -> str:
        """
        Chat with Max persona
        Uses conversation history for context, supports vision
        """
        # Build context — prefer coaching_context (full context from coaching service)
        context_str = user_context.get("coaching_context", "") if user_context else ""

        # Fallback: build from individual fields if coaching_context not provided
        if not context_str and user_context:
            if user_context.get("latest_scan"):
                scan = user_context["latest_scan"]
                context_str += f"\nLATEST SCAN: score={scan.get('overall_score', '?')}/10"
                if scan.get("focus_areas"):
                    context_str += f", focus={scan['focus_areas']}"

            if user_context.get("onboarding"):
                ob = user_context["onboarding"]
                bits = [f"{k}: {', '.join(v) if isinstance(v, list) else v}" for k, v in ob.items() if v and k in ("skin_type", "goals", "gender", "age")]
                if bits:
                    context_str += f"\nPROFILE: {' | '.join(bits)}"

            if user_context.get("active_schedule"):
                schedule = user_context["active_schedule"]
                label = schedule.get("course_title") or schedule.get("maxx_id") or "?"
                context_str += f"\nSCHEDULE: {label}"

            if user_context.get("active_maxx_schedule"):
                ms = user_context["active_maxx_schedule"]
                context_str += f"\nActive {ms.get('maxx_id')} schedule exists."

        # Build chat prompt
        chat_prompt = await asyncio.to_thread(
            resolve_prompt, PromptKey.MAX_CHAT_SYSTEM, MAX_CHAT_SYSTEM_PROMPT
        )
        if context_str:
            chat_prompt += f"\n\n## USER CONTEXT:\n{context_str}"
        
        # Format history
        history_for_gemini = []
        
        # Add system instruction
        # Note: GenerativeModel.start_chat doesn't support a separate system role easily in this SDK version
        # We prepend it to the first message or use it as a preamble
        
        for msg in chat_history[-15:]:  # Last 15 messages for context
            role = "user" if msg["role"] == "user" else "model"
            # Handle historical attachments if they were images (simplified to just text for history)
            content = msg["content"]
            history_for_gemini.append({"role": role, "parts": [content]})

        # If history is empty, add the system prompt as a user message
        if not history_for_gemini:
            history_for_gemini.append({"role": "user", "parts": [chat_prompt]})
            history_for_gemini.append({"role": "model", "parts": ["yo whats up, im max. got your context. whats good?"]})
        else:
            # Inject system prompt into the first message of the session
            history_for_gemini[0]["parts"][0] = f"{chat_prompt}\n\n{history_for_gemini[0]['parts'][0]}"
        
        # Add new message (with image if provided)
        new_message_parts = []
        if image_data:
            new_message_parts.append({"mime_type": "image/jpeg", "data": image_data})
        
        new_message_parts.append(message if message else "Look at this image.")

        def _sync_send() -> dict:
            chat = self.model.start_chat(history=history_for_gemini)
            response = chat.send_message(new_message_parts)
            tool_calls = []
            response_text = ""
            for part in response.candidates[0].content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    tool_calls.append(
                        {
                            "name": part.function_call.name,
                            "args": dict(part.function_call.args),
                        }
                    )
                elif hasattr(part, "text") and part.text:
                    response_text += part.text
            return {
                "text": response_text.strip() or "done. check your schedule.",
                "tool_calls": tool_calls,
            }

        # Run sync SDK in a thread so the event loop stays responsive (Twilio SMS webhook ~15s limit).
        return await asyncio.to_thread(_sync_send)


# Singleton instance
gemini_service = GeminiService()
