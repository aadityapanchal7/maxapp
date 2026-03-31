"""
FitMax notification engine — schedule generation + coaching reference.

Full reference: fitmax_notification_engine_reference.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_REF_FILE = Path(__file__).with_name("fitmax_notification_engine_reference.md")

try:
    FITMAX_NOTIFICATION_ENGINE_REFERENCE = _REF_FILE.read_text(encoding="utf-8")
except OSError:
    FITMAX_NOTIFICATION_ENGINE_REFERENCE = (
        "# FitMax notification reference missing. Restore fitmax_notification_engine_reference.md.\n"
    )

FITMAX_COACHING_REFERENCE = """## FITMAX NOTIFICATION ENGINE (condensed)

PHASES (route from BF band + goal): **Cut** (BF >~15% OR goal lean) | **Lean bulk** (10–15% + build) | **Recomp** (15–20% + beginner + both) | **Maintain** (10–15% + maintain).

TIMING: **Pre-workout** = workout −30m | **Post-workout** = workout_end +15m (estimate ~60–90m session) | **AM nutrition** = wake+30 | **Midday tip** = midpoint(wake+15, bed−60) | **PM nutrition** = bed−2h | **Weigh-in** = Mon wake+15 | **Monthly body** = 1st at midday | Quiet: bed→wake.

TRAINING: aesthetics split; **lateral raises** + **face pulls** every session pattern; **neck** 2–3×/wk **unless BoneMax** (then strip neck from FitMax). Progressive overload +2.5–5 lb when top of rep range hit.

NUTRITION: Cut −500 / bulk +250–300 / recomp+maint @ TDEE; protein ~1g/lb. **No-track** users → portion language only.

BUDGET: phase-in W1–2 lean; W3–4 +PM+supps; W5+ +posture+monthly. Cap **10**/day with other maxxes.

CROSS: **+BoneMax** dedupe posture; **+HeightMax** dead hang after axial leg day; **+Skinmax** merge AM nutrition+skin; **+HairMax** creatine/hair caveat when relevant.
"""


def _parse_hm(s: str) -> tuple[int, int]:
    parts = str(s).strip().split(":")
    h = int(parts[0])
    m = int(parts[1][:2]) if len(parts) > 1 else 0
    return h, m


def _add_minutes(h: int, m: int, delta: int) -> tuple[int, int]:
    total = h * 60 + m + delta
    total %= 24 * 60
    return total // 60, total % 60


def _format_hm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def _midpoint_wake15_bed60(wake_time: str, sleep_time: str) -> str:
    wh, wm = _parse_hm(wake_time)
    sh, sm = _parse_hm(sleep_time)
    am15_h, am15_m = _add_minutes(wh, wm, 15)
    pm60_h, pm60_m = _add_minutes(sh, sm, -60)
    am_mins = am15_h * 60 + am15_m
    pm_mins = pm60_h * 60 + pm60_m
    if pm_mins < am_mins:
        pm_mins += 24 * 60
    mid_mins = (am_mins + pm_mins) // 2 % (24 * 60)
    return _format_hm(mid_mins // 60, mid_mins % 60)


def resolve_fitmax_phase(onboarding: dict[str, Any] | None) -> str:
    """Map onboarding to protocol key: cut | lean_bulk | recomp | maintain."""
    ob = onboarding or {}
    bf = str(
        ob.get("fitmax_body_fat_band")
        or ob.get("estimated_body_fat")
        or ob.get("body_fat_band")
        or ""
    ).lower()
    goal = str(ob.get("fitmax_primary_goal") or ob.get("primary_goal") or ob.get("goal") or "").lower()
    exp = str(ob.get("fitmax_training_experience") or ob.get("training_experience") or "").lower()
    is_beginner = any(x in exp for x in ("never", "beginner", "<1", "0 year"))

    def _band10_15() -> bool:
        return any(x in bf for x in ("10-15", "10_15", "10–15", "10 to 15"))

    def _band15_20() -> bool:
        return any(x in bf for x in ("15-20", "15_20", "15–20"))

    def _over15() -> bool:
        return any(
            x in bf
            for x in (
                "15-20",
                "15_20",
                "20-25",
                "20_25",
                "25-30",
                "25_30",
                "30+",
                "30 +",
                "don't",
                "dont know",
                "unknown",
            )
        )

    if "maintain" in goal:
        if _band10_15() or "under 10" in bf or "under_10" in bf or bf.startswith("under"):
            return "maintain"
    if "lean" in goal or "face" in goal or "cut" in goal or "shred" in goal:
        return "cut"
    if ("both" in goal or "recomp" in goal) and is_beginner and _band15_20():
        return "recomp"
    if "muscle" in goal or "bulk" in goal or "build" in goal:
        if _band10_15() or "under 10" in bf or "under_10" in bf:
            return "lean_bulk"
    if _over15():
        return "cut"
    if is_beginner:
        return "recomp"
    return "lean_bulk"


def format_fitmax_anchor_times(
    wake_time: str,
    sleep_time: str,
    workout_time: str = "18:00",
    workout_duration_min: int = 75,
) -> str:
    wh, wm = _parse_hm(wake_time)
    sh, sm = _parse_hm(sleep_time)
    wo_h, wo_m = _parse_hm(workout_time)
    am_nut_h, am_nut_m = _add_minutes(wh, wm, 30)
    pm_nut_h, pm_nut_m = _add_minutes(sh, sm, -120)
    pre_h, pre_m = _add_minutes(wo_h, wo_m, -30)
    end_h, end_m = _add_minutes(wo_h, wo_m, workout_duration_min)
    post_h, post_m = _add_minutes(end_h, end_m, 15)
    mon_wi_h, mon_wi_m = _add_minutes(wh, wm, 15)
    midday = _midpoint_wake15_bed60(wake_time, sleep_time)
    return f"""## COMPUTED ANCHOR TIMES — FITMAX
- Wake: {wake_time} | Bed: {sleep_time} | Preferred workout start: {workout_time}
- **Morning nutrition** → {_format_hm(am_nut_h, am_nut_m)} (wake + 30 min)
- **Evening nutrition closeout** → {_format_hm(pm_nut_h, pm_nut_m)} (bed − 2 h)
- **Pre-workout** → {_format_hm(pre_h, pre_m)} (workout − 30 min)
- **Post-workout** → {_format_hm(post_h, post_m)} (~{workout_duration_min} min session + 15 min after)
- **Monday weigh-in** → {_format_hm(mon_wi_h, mon_wi_m)} (wake + 15 min)
- **Midday posture / aesthetics** → {midday} (midpoint wake+15 and bed−60)
- **Monthly body check (1st)** → {midday} (use midday slot)
"""


def summarize_fitmax_onboarding(
    onboarding: dict[str, Any],
    wake_time: str,
    sleep_time: str,
    phase: str,
) -> str:
    ob = onboarding or {}
    lines = [
        "## FITMAX USER PROFILE",
        f"- Routed phase / protocol key: **{phase}**",
        f"- Wake / bed from request: {wake_time} / {sleep_time}",
    ]
    for key, label in (
        ("fitmax_body_fat_band", "Body fat band"),
        ("estimated_body_fat", "Estimated body fat"),
        ("fitmax_primary_goal", "Primary goal"),
        ("primary_goal", "Primary goal (alt)"),
        ("fitmax_training_experience", "Training experience"),
        ("training_experience", "Training experience (alt)"),
        ("fitmax_equipment", "Equipment"),
        ("available_equipment", "Equipment (alt)"),
        ("fitmax_workout_days_per_week", "Workout days/week"),
        ("workout_days_per_week", "Workout days/week (alt)"),
        ("fitmax_preferred_workout_time", "Preferred workout time"),
        ("preferred_workout_time", "Preferred workout time (alt)"),
        ("fitmax_diet_approach", "Diet approach"),
        ("dietary_approach", "Diet approach (alt)"),
        ("fitmax_supplements_opt_in", "Supplements opt-in"),
        ("fitmax_weeks_on_program", "Weeks on program (phase-in)"),
        ("weight_kg", "Weight (kg)"),
        ("weight_lb", "Weight (lb)"),
        ("height_cm", "Height (cm)"),
    ):
        if ob.get(key) is not None and str(ob.get(key)).strip() != "":
            lines.append(f"- {label}: {ob.get(key)}")
    return "\n".join(lines)


def get_fitmax_slot_times(
    wake_time: str,
    sleep_time: str,
    workout_time: str = "18:00",
    workout_duration_min: int = 75,
) -> dict[str, str]:
    wh, wm = _parse_hm(wake_time)
    sh, sm = _parse_hm(sleep_time)
    wo_h, wo_m = _parse_hm(workout_time)
    am_nut_h, am_nut_m = _add_minutes(wh, wm, 30)
    pm_nut_h, pm_nut_m = _add_minutes(sh, sm, -120)
    pre_h, pre_m = _add_minutes(wo_h, wo_m, -30)
    end_h, end_m = _add_minutes(wo_h, wo_m, workout_duration_min)
    post_h, post_m = _add_minutes(end_h, end_m, 15)
    wi_h, wi_m = _add_minutes(wh, wm, 15)
    midday = _midpoint_wake15_bed60(wake_time, sleep_time)
    return {
        "morning_nutrition": _format_hm(am_nut_h, am_nut_m),
        "evening_nutrition": _format_hm(pm_nut_h, pm_nut_m),
        "pre_workout": _format_hm(pre_h, pre_m),
        "post_workout": _format_hm(post_h, post_m),
        "monday_weigh_in": _format_hm(wi_h, wi_m),
        "midday_posture": midday,
        "monthly_body_check": midday,
    }


FITMAX_JSON_DIRECTIVES = """## FITMAX — JSON SCHEDULE OUTPUT (MANDATORY)

1. Use **HH:MM** 24h; follow COMPUTED ANCHOR TIMES + full reference (pre-workout **workout−30m**, post **session_end+15m**).
2. **Do NOT** use a generic wake-only check-in as the first FitMax ping — first daily anchor is **morning nutrition at wake+30** (merge with Skinmax AM when both active).
3. **Quiet hours:** no tasks between sleep_time and wake_time.
4. **Workout days only:** pre + post training tasks; **rest days:** omit pre/post.
5. **Monday:** weekly weigh-in at **wake+15** (checkpoint).
6. **1st of month:** monthly body check at **midday** anchor (checkpoint).
7. **Phase-in:** if `fitmax_weeks_on_program` is 1–2, omit evening nutrition + posture + monthly except weigh-in; weeks 3–4 add PM nutrition + supplements if opted in; week 5+ full module set per reference.
8. **BoneMax active:** remove neck work from lift descriptions; **replace** midday posture tips with training/nutrition tips (no posture duplication).
9. **HeightMax active:** after leg days with squats/deadlifts, optional **dead hang 2 min** copy in post-workout or evening task.
10. **Skinmax active:** merge morning nutrition + AM skincare into **one** notification when possible.
11. **HairMax active:** when scheduling creatine tip, add **DHT/hair caveat** for predisposed users.
12. **task_type:** `routine` for nutrition blocks; `reminder` for cues; `checkpoint` for weigh-in, monthly photos, progressive-overload reviews.
13. Cap **10** notifications/day **across all modules**; stagger with MULTI-ACTIVE-MODULES instructions.
"""


POSTURE_TIPS_10: list[str] = [
    "Shoulder check: pull shoulders back — rounded shoulders narrow your frame.",
    "Stomach vacuum: exhale, belly button to spine, 5×20s — trains TVA, narrower waist look.",
    "APT check: squeeze glutes, slight posterior pelvic tilt — saves waist measurement.",
    "Creatine: 5g daily monohydrate — strength + fullness (see HairMax caveat if thinning risk).",
    "Water: ~1 gal / 3.5L — dehydration flattens muscles and dulls skin.",
    "Sleep: 7–9h — muscle repair peaks in deep sleep.",
    "Shoulder-to-waist ratio drives the V-taper — wide shoulders + narrow waist.",
    "Neck thickness frames the jaw — 2–3×/wk if not in BoneMax.",
    "Face pulls every session: 3×15–20 — posture + rear delts.",
    "Alcohol: blunts protein synthesis, hurts sleep and face leanness — cut for face gains.",
]
