"""
HeightMax notification engine — authoritative reference for schedule generation and coaching.

Full reference: heightmax_notification_engine_reference.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_REF_FILE = Path(__file__).with_name("heightmax_notification_engine_reference.md")

try:
    HEIGHTMAX_NOTIFICATION_ENGINE_REFERENCE = _REF_FILE.read_text(encoding="utf-8")
except OSError:
    HEIGHTMAX_NOTIFICATION_ENGINE_REFERENCE = (
        "# HeightMax notification reference missing. Restore heightmax_notification_engine_reference.md.\n"
    )

HEIGHTMAX_COACHING_REFERENCE = """## HEIGHTMAX NOTIFICATION ENGINE (condensed)

TIMING (wake + bed; exact HH:MM):
- Morning decompression = wake + 20 min
- Midday posture = midpoint(wake+15, bed−60) — same as BoneMax midday
- Afternoon posture = midday + 3h — only if screen ≥6h/day at onboarding
- Evening decompression = bed − 90 min
- Sleep / GH protocol = bed − 45 min
- Sprint reminder = 30 min before workout on sprint days (2–3×/week, non-consecutive)
- Post-sprint eat window ≈ 60 min after session ends
- Height nutrition = wake+1h or wake+5h — **only if opted in**
- Weekly measure = Sunday wake + 30 min
- Monthly review = 1st at midday (same as midday posture time)
- Quiet hours: bed → wake

TIERS: under 18 = Tier 1; 18–21 = Tier 2; 22+ = Tier 3 (posture/decomp reclaim only ~0.5–2 cm, no fake growth promises).

BUDGET: Phase 1 ~2–3/day → Phase 2 ~5–6 → Phase 3 ~6–7; **max 10/day** with other modules.

MERGES: + Bonemax = merge posture + sleep evening + supplements where overlap; + Fitmax = sprint counts as workout; decompress after heavy axial lifting days.

NEVER ask outside_today — HeightMax does not use it.
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


def height_tier_from_age(age: Any) -> int:
    """1 = under 18, 2 = 18–21, 3 = 22+ (plates closed framing)."""
    try:
        a = int(age)
    except (TypeError, ValueError):
        return 2
    if a < 18:
        return 1
    if a <= 21:
        return 2
    return 3


def format_heightmax_anchor_times(wake_time: str, sleep_time: str) -> str:
    wh, wm = _parse_hm(wake_time)
    sh, sm = _parse_hm(sleep_time)
    morn_dec_h, morn_dec_m = _add_minutes(wh, wm, 20)
    am_a_h, am_a_m = _add_minutes(wh, wm, 15)
    pm_skin_h, pm_skin_m = _add_minutes(sh, sm, -60)
    am_mins = am_a_h * 60 + am_a_m
    pm_mins = pm_skin_h * 60 + pm_skin_m
    if pm_mins < am_mins:
        pm_mins += 24 * 60
    mid_mins = (am_mins + pm_mins) // 2 % (24 * 60)
    mid_h, mid_m = mid_mins // 60, mid_mins % 60
    aft_h, aft_m = _add_minutes(mid_h, mid_m, 180)
    eve_st_h, eve_st_m = _add_minutes(sh, sm, -90)
    sleep_h, sleep_m = _add_minutes(sh, sm, -45)
    week_meas_h, week_meas_m = _add_minutes(wh, wm, 30)
    nutr_h, nutr_m = _add_minutes(wh, wm, 60)
    return f"""## COMPUTED ANCHOR TIMES — HEIGHTMAX (use formulas)
- Wake: {wake_time} | Bed: {sleep_time}
- **Morning decompression** → {_format_hm(morn_dec_h, morn_dec_m)} (wake + 20 min)
- **Midday posture** → {_format_hm(mid_h, mid_m)} (midpoint of wake+15 and bed−60)
- **Afternoon posture** → {_format_hm(aft_h, aft_m)} (midday + 3h) — only if 6+ h screen
- **Evening decompression** → {_format_hm(eve_st_h, eve_st_m)} (bed − 90 min)
- **Sleep / GH protocol** → {_format_hm(sleep_h, sleep_m)} (bed − 45 min)
- **Weekly measurement (Sunday)** → {_format_hm(week_meas_h, week_meas_m)} (Sunday wake + 30 min)
- **Height nutrition (if opted in)** → {_format_hm(nutr_h, nutr_m)} (example: wake + 1h; or use wake+5h alternate)
- **Sprint pre-workout** → 30 min before user's workout time on sprint days (from onboarding)
"""


def summarize_heightmax_onboarding(
    onboarding: dict[str, Any],
    wake_time: str,
    sleep_time: str,
    age_val: Any,
) -> str:
    ob = onboarding or {}
    tier = height_tier_from_age(age_val if age_val is not None else ob.get("age"))
    lines = [
        "## HEIGHTMAX USER PROFILE",
        f"- Wake / bed from request: {wake_time} / {sleep_time}",
        f"- Inferred tier from age: Tier {tier} (1=under 18, 2=18–21, 3=22+)",
    ]
    if ob.get("height"):
        lines.append(f"- Reported height: {ob.get('height')}")
    gp = ob.get("growth_plate_status") or ob.get("heightmax_growth_plate_status")
    if gp:
        lines.append(f"- Growth plate status: {gp}")
    goal = ob.get("heightmax_goal") or ob.get("height_goal")
    if goal:
        lines.append(f"- Height goal: {goal}")
    wst = ob.get("heightmax_workout_schedule") or ob.get("workout_days_time")
    if wst:
        lines.append(f"- Workout days / time: {wst}")
    if ob.get("heightmax_stretching_decompression") is not None:
        lines.append(f"- Already stretching/decompression: {ob.get('heightmax_stretching_decompression')}")
    sq = ob.get("heightmax_sleep_quality") or ob.get("sleep_quality")
    if sq:
        lines.append(f"- Sleep quality (self): {sq}")
    scr = ob.get("heightmax_screen_hours") or ob.get("bonemax_heavy_screen_time")
    if scr:
        lines.append(f"- Screen time (hours): {scr}")
    if ob.get("heightmax_height_nutrition_opt_in") is not None:
        lines.append(f"- Height nutrition opt-in: {ob.get('heightmax_height_nutrition_opt_in')}")
    if ob.get("heightmax_weeks_on_routine") is not None:
        lines.append(f"- Weeks on routine (phase hint): {ob.get('heightmax_weeks_on_routine')}")
    return "\n".join(lines)


def get_heightmax_slot_times(wake_time: str, sleep_time: str) -> dict[str, str]:
    wh, wm = _parse_hm(wake_time)
    sh, sm = _parse_hm(sleep_time)
    morn_dec_h, morn_dec_m = _add_minutes(wh, wm, 20)
    am_a_h, am_a_m = _add_minutes(wh, wm, 15)
    pm_skin_h, pm_skin_m = _add_minutes(sh, sm, -60)
    am_mins = am_a_h * 60 + am_a_m
    pm_mins = pm_skin_h * 60 + pm_skin_m
    if pm_mins < am_mins:
        pm_mins += 24 * 60
    mid_mins = (am_mins + pm_mins) // 2 % (24 * 60)
    mid_h, mid_m = mid_mins // 60, mid_mins % 60
    aft_h, aft_m = _add_minutes(mid_h, mid_m, 180)
    eve_st_h, eve_st_m = _add_minutes(sh, sm, -90)
    sleep_h, sleep_m = _add_minutes(sh, sm, -45)
    week_meas_h, week_meas_m = _add_minutes(wh, wm, 30)
    nutr_h, nutr_m = _add_minutes(wh, wm, 60)
    return {
        "morning_decompression": _format_hm(morn_dec_h, morn_dec_m),
        "midday_posture": _format_hm(mid_h, mid_m),
        "afternoon_posture": _format_hm(aft_h, aft_m),
        "evening_decompression": _format_hm(eve_st_h, eve_st_m),
        "sleep_protocol": _format_hm(sleep_h, sleep_m),
        "weekly_measurement": _format_hm(week_meas_h, week_meas_m),
        "height_nutrition": _format_hm(nutr_h, nutr_m),
        "monthly_checkin": _format_hm(mid_h, mid_m),
    }


HEIGHTMAX_JSON_DIRECTIVES = """## HEIGHTMAX — JSON SCHEDULE OUTPUT (MANDATORY)

1. Every task uses **HH:MM** 24h from wake_time/sleep_time and COMPUTED ANCHOR TIMES.
2. **Do NOT** use a generic "morning check-in at wake" as the first HeightMax ping — **morning decompression is wake+20** (unless MULTI-ACTIVE-MODULES requires stagger with another module's wake ping).
3. **Never** schedule `outside_today` or sunscreen tasks for HeightMax.
4. **Tier 3 (21+):** copy must not promise skeletal growth beyond posture/decompression reclamation (~0.5–2 cm realistic).
5. **Quiet hours:** nothing between sleep_time and wake_time.
6. Respect **enabled HeightMax tracks** in HEIGHTMAX — ENABLED TRACKS ONLY; do not invent tasks for disabled tracks.
7. **Phase-in:** weeks 1–2 lighter; ramp decompression, nutrition, sprints per engine.
8. **Sprint days:** 2–3×/week, not consecutive; 30 min pre workout + post-sprint eat ~60 min after session.
9. **task_type:** `routine` for stretch/decomp/sleep blocks; `reminder` for posture nudges; `checkpoint` for sprint, weekly measure, monthly review.
10. If **Bonemax** or **Fitmax** also active, merge overlapping posture/sleep/workout messaging per engine; cap **10** notifications/day total.
"""
