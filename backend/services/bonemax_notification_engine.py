"""
BoneMax notification engine — authoritative reference for schedule generation and coaching.

Full reference: bonemax_notification_engine_reference.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_REF_FILE = Path(__file__).with_name("bonemax_notification_engine_reference.md")

try:
    BONEMAX_NOTIFICATION_ENGINE_REFERENCE = _REF_FILE.read_text(encoding="utf-8")
except OSError:
    BONEMAX_NOTIFICATION_ENGINE_REFERENCE = (
        "# BoneMax notification reference missing. Restore bonemax_notification_engine_reference.md.\n"
    )

BONEMAX_COACHING_REFERENCE = """## BONEMAX NOTIFICATION ENGINE (condensed)

TIMING (wake_time + sleep_time; exact HH:MM):
- Mewing morning = wake | Facial = wake+15 | Fascia AM = wake+20 | Masseter default = wake+2h (or user time)
- Mewing midday = midpoint(wake+15, bed−60) — same active-day logic as Skinmax midday
- Nasal check = midday mewing +2h (2× if screen 6+h, max 2/day)
- Mewing night = bed−30 (bundle sleep optimization + nasal night notes here — no standalone sleep SMS)
- Fascia evening = bed−90, 4–5×/week; skip if Skinmax retinoid/exfol that night; if no Skinmax use 5× with Wed+Sun off pattern
- Neck = 15min after workout END on workout days only; non-workout: chin tucks IN midday mewing; skip chin tucks in midday if full neck done that day
- Symmetry = 1×/day between midday and evening, weekly rotating tips
- Quiet hours: nothing between bed and wake

BUDGET: Phase 1 ~6/day, Phase 2 ~8, Phase 3 ~8–9 effective. **Hard cap 10/day** all modules — merge with Skinmax morning/evening when both active; drop lowest-priority first.

TMJ onboarding: masseter cap 15min Falim-only, no progression past safe stack, always disclaimer.

Progression: masseter + neck by week bands; mewing/nasal no auto-escalation; hard mewing only if toggled; facial → 2min version after 5-day skip streak.

Monthly: 1st at midday — photos + neck measure + jaw feel + TMJ month.
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


def format_bonemax_anchor_times(wake_time: str, sleep_time: str) -> str:
    """Ground the LLM with computed examples (BoneMax + shared midday formula)."""
    wh, wm = _parse_hm(wake_time)
    sh, sm = _parse_hm(sleep_time)
    facial_h, facial_m = _add_minutes(wh, wm, 15)
    fascia_am_h, fascia_am_m = _add_minutes(wh, wm, 20)
    masseter_h, masseter_m = _add_minutes(wh, wm, 120)
    am_anchor_h, am_anchor_m = _add_minutes(wh, wm, 15)
    pm_skin_h, pm_skin_m = _add_minutes(sh, sm, -60)
    am_mins = am_anchor_h * 60 + am_anchor_m
    pm_mins = pm_skin_h * 60 + pm_skin_m
    if pm_mins < am_mins:
        pm_mins += 24 * 60
    mid_mins = (am_mins + pm_mins) // 2 % (24 * 60)
    mid_h, mid_m = mid_mins // 60, mid_mins % 60
    nasal_h, nasal_m = _add_minutes(mid_h, mid_m, 120)
    mew_night_h, mew_night_m = _add_minutes(sh, sm, -30)
    fascia_eve_h, fascia_eve_m = _add_minutes(sh, sm, -90)
    return f"""## COMPUTED ANCHOR TIMES FOR THIS USER (BoneMax — use formulas, not guesses)
- Wake: {wake_time} | Bed: {sleep_time}
- **Mewing morning reset** → {_format_hm(wh, wm)}
- **Facial exercises** → {_format_hm(facial_h, facial_m)} (wake + 15 min)
- **Fascia / lymph morning** → {_format_hm(fascia_am_h, fascia_am_m)} (wake + 20 min)
- **Masseter default slot** → {_format_hm(masseter_h, masseter_m)} (wake + 2h unless user chose another time)
- **Mewing midday reset** → {_format_hm(mid_h, mid_m)} (midpoint of wake+15 and bed−60)
- **Nasal breathing check** → {_format_hm(nasal_h, nasal_m)} (midday mewing + 2h; second slot in afternoon if screen 6+ h)
- **Mewing night check (+ sleep bundle)** → {_format_hm(mew_night_h, mew_night_m)} (bed − 30 min)
- **Fascia / lymph evening** → {_format_hm(fascia_eve_h, fascia_eve_m)} (bed − 90 min; 4–5×/week not daily)
"""


def summarize_bonemax_onboarding(
    onboarding: dict[str, Any],
    wake_time: str,
    sleep_time: str,
) -> str:
    ob = onboarding or {}
    lines = [
        "## BONEMAX USER PROFILE (onboarding + request)",
        f"- Wake / bed from request: {wake_time} / {sleep_time}",
    ]
    if ob.get("age") is not None:
        lines.append(f"- Age: {ob.get('age')}")
    wst = ob.get("bonemax_workout_schedule") or ob.get("workout_days_time")
    if wst:
        lines.append(f"- Workout days / time: {wst}")
    wf = ob.get("bonemax_workout_frequency")
    if wf:
        lines.append(f"- Workout frequency (band): {wf}")
    scr = ob.get("bonemax_heavy_screen_time") or ob.get("bonemax_screen_hours")
    if scr:
        lines.append(f"- Screen time (hours / heavy): {scr}")
    habits = ob.get("bonemax_current_habits") or ob.get("bonemax_habits")
    if habits:
        lines.append(f"- Current habits (mewing/gum/neck): {habits}")
    tmj = ob.get("bonemax_tmj_history")
    if tmj:
        lines.append(f"- TMJ / jaw issues: {tmj}")
    gum = ob.get("bonemax_mastic_gum_regular")
    if gum:
        lines.append(f"- Mastic / hard gum experience: {gum}")
    sp = ob.get("bonemax_sleep_position") or ob.get("sleep_position")
    if sp:
        lines.append(f"- Sleep position: {sp}")
    if ob.get("bonemax_mouth_breather") is not None:
        lines.append(f"- Mouth breather flag: {ob.get('bonemax_mouth_breather')}")
    if ob.get("bonemax_meal_chewing_reminders") is not None:
        lines.append(f"- Meal chewing reminders enabled: {ob.get('bonemax_meal_chewing_reminders')}")
    if ob.get("bonemax_bone_nutrition_opt_in") is not None:
        lines.append(f"- Bone nutrition stack opt-in: {ob.get('bonemax_bone_nutrition_opt_in')}")
    if ob.get("bonemax_hard_mewing") is not None:
        lines.append(f"- Hard mewing toggle: {ob.get('bonemax_hard_mewing')}")
    if ob.get("bonemax_weeks_on_routine") is not None:
        lines.append(f"- Weeks on routine (phase hint): {ob.get('bonemax_weeks_on_routine')}")
    if ob.get("bonemax_masseter_time"):
        lines.append(f"- Masseter preferred time: {ob.get('bonemax_masseter_time')}")
    return "\n".join(lines)


def get_bonemax_slot_times(wake_time: str, sleep_time: str) -> dict[str, str]:
    """Deterministic slots for JSON fallback."""
    wh, wm = _parse_hm(wake_time)
    sh, sm = _parse_hm(sleep_time)
    facial_h, facial_m = _add_minutes(wh, wm, 15)
    fascia_am_h, fascia_am_m = _add_minutes(wh, wm, 20)
    masseter_h, masseter_m = _add_minutes(wh, wm, 120)
    am_anchor_h, am_anchor_m = _add_minutes(wh, wm, 15)
    pm_skin_h, pm_skin_m = _add_minutes(sh, sm, -60)
    am_mins = am_anchor_h * 60 + am_anchor_m
    pm_mins = pm_skin_h * 60 + pm_skin_m
    if pm_mins < am_mins:
        pm_mins += 24 * 60
    mid_mins = (am_mins + pm_mins) // 2 % (24 * 60)
    mid_h, mid_m = mid_mins // 60, mid_mins % 60
    nasal_h, nasal_m = _add_minutes(mid_h, mid_m, 120)
    mew_night_h, mew_night_m = _add_minutes(sh, sm, -30)
    fascia_eve_h, fascia_eve_m = _add_minutes(sh, sm, -90)
    sym_h, sym_m = _add_minutes(mid_h, mid_m, 90)
    return {
        "mewing_morning": _format_hm(wh, wm),
        "facial": _format_hm(facial_h, facial_m),
        "fascia_am": _format_hm(fascia_am_h, fascia_am_m),
        "masseter": _format_hm(masseter_h, masseter_m),
        "mewing_midday": _format_hm(mid_h, mid_m),
        "nasal": _format_hm(nasal_h, nasal_m),
        "symmetry": _format_hm(sym_h, sym_m),
        "mewing_night": _format_hm(mew_night_h, mew_night_m),
        "fascia_evening": _format_hm(fascia_eve_h, fascia_eve_m),
    }


BONEMAX_JSON_DIRECTIVES = """## BONEMAX — JSON SCHEDULE OUTPUT (MANDATORY)

1. Every task **time** is **HH:MM** 24h, computed from wake_time and sleep_time using the reference + COMPUTED ANCHOR TIMES.
2. **Do NOT** add a generic "morning check-in / let me know you're awake" at wake for BoneMax — **Mewing morning reset AT wake** is the first ping (unless MULTI-ACTIVE-MODULES forces stagger; if Skinmax is also active, **merge** morning mewing + skin AM into one notification when same window).
3. **Quiet hours:** no tasks between sleep_time and wake_time.
4. Respect **phase budget** (1→2→3) and **hard cap 10 notifications/day** across modules; if Skinmax active, merge evening mewing night + skin PM when appropriate.
5. **task_type:** `routine` for timed blocks (mewing sets, facial, fascia, masseter session, neck); `reminder` for symmetry / meal chewing / nutrition ping; `checkpoint` for masseter recovery check, monthly bone check.
6. Encode **workout-day-only** neck tasks using user's workout schedule from context; on non-workout days, put **chin tuck copy inside midday mewing** description (not a duplicate midday task).
7. **Fascia evening:** not every day — mark fewer evenings or omit tasks on rest pattern / Skinmax conflict nights per reference.
8. **TMJ yes:** masseter tasks must reflect 15min cap, Falim-only, permanent disclaimer in description.
9. **High screen (6+ h):** add screen-forward-head line to midday mewing; optionally second nasal check in afternoon (max 2 nasal/day).
10. **Monthly bone check:** 1st of month at **mewing midday** time.
"""
