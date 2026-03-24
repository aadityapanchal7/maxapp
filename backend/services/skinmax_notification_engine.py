"""
SkinMax notification engine — authoritative reference for schedule generation and coaching.

Full reference: skinmax_notification_engine_reference.md (loaded at import).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_REF_FILE = Path(__file__).with_name("skinmax_notification_engine_reference.md")

try:
    SKINMAX_NOTIFICATION_ENGINE_REFERENCE = _REF_FILE.read_text(encoding="utf-8")
except OSError:
    SKINMAX_NOTIFICATION_ENGINE_REFERENCE = (
        "# SkinMax notification reference file missing. Restore skinmax_notification_engine_reference.md.\n"
    )

# Shorter block for chat/coaching context (still actionable).
SKINMAX_COACHING_REFERENCE = """## SKINMAX NOTIFICATION ENGINE (condensed)

TIMING (all derived from wake_time + sleep_time; never vague):
- AM routine = wake + 15 min | PM routine = bed − 60 min | Midday tip = midpoint(AM, PM) | Hydration = midday + 2h (skip if user disabled)
- SPF reapply = AM + 3h only if outdoor_frequency is always (daily) or sometimes (confirm going out / outside_today); never if rarely
- Quiet hours: nothing between bed and wake
- Restriction reminder: max 1/day at wake+1h OR +5h OR +9h; rotate if multiple restrictions
- Weekly exfoliation: default Wed at PM time (replaces PM); never same night as retinoid
- Pillowcase: Sunday at midday time | Monthly photo: 1st at midday | Monthly check-in: 1st at PM+30m

BUDGET: 3–5 notifications/day min/max; AM + midday + PM are mandatory daily tasks.

PM: alternate Retinoid night vs Rest night per ramp (weeks 1–2: Mon+Thu; 3–4: MWF; 5–8: EOD; 9+: nightly unless redness/unstarted rules). Exfoliation day = rest night.

COMBOS: primary concern drives retinoid; secondary adds AM active if safe. No BHA+retinoid same session; no AHA peel + retinoid same night; BP and retinoid different sessions.

For full AM/PM product steps, conflict matrix, and monthly check-in branches, follow the user's active schedule tasks and the long reference if needed.
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


def format_computed_anchor_times(wake_time: str, sleep_time: str) -> str:
    """
    Concrete example times for the LLM (grounding). Uses same-day assumption (PM after AM).
    """
    wh, wm = _parse_hm(wake_time)
    sh, sm = _parse_hm(sleep_time)
    am_h, am_m = _add_minutes(wh, wm, 15)
    pm_h, pm_m = _add_minutes(sh, sm, -60)
    am_mins = am_h * 60 + am_m
    pm_mins = pm_h * 60 + pm_m
    if pm_mins < am_mins:
        pm_mins += 24 * 60
    mid_mins = (am_mins + pm_mins) // 2
    mid_mins %= 24 * 60
    mid_h, mid_m = mid_mins // 60, mid_mins % 60
    hyd_h, hyd_m = _add_minutes(mid_h, mid_m, 120)
    spf_h, spf_m = _add_minutes(am_h, am_m, 180)
    return f"""## COMPUTED ANCHOR TIMES FOR THIS USER (examples — use these formulas, not guesses)
- Wake (from USER CONTEXT): {wake_time}
- Bed / sleep (from USER CONTEXT): {sleep_time}
- **AM Routine** → {_format_hm(am_h, am_m)} (wake + 15 minutes)
- **PM Routine** → {_format_hm(pm_h, pm_m)} (bed time − 60 minutes)
- **Midday Tip** → {_format_hm(mid_h, mid_m)} (midpoint between AM Routine and PM Routine)
- **Hydration Check** → {_format_hm(hyd_h, hyd_m)} (Midday + 2 hours) — omit entirely if user disabled hydration reminders
- **SPF Reapply** → {_format_hm(spf_h, spf_m)} (AM Routine + 3 hours) — only per outdoor_frequency + sometimes/outside_today rules
"""


def summarize_skinmax_onboarding(
    onboarding: dict[str, Any],
    wake_time: str,
    sleep_time: str,
    outside_today: bool,
) -> str:
    """Human-readable lines for the schedule prompt."""
    ob = onboarding or {}
    lines = [
        "## SKINMAX USER PROFILE (onboarding)",
        f"- Wake / bed from request: {wake_time} / {sleep_time}",
        f"- outside_today (for this generation): {'Yes' if outside_today else 'No'}",
    ]
    st = ob.get("skin_type")
    if st:
        lines.append(f"- Skin type: {st}")
    pc = ob.get("skin_concern") or ob.get("primary_skin_concern")
    if pc:
        lines.append(f"- Primary concern: {pc}")
    sc = ob.get("secondary_skin_concern")
    if sc:
        lines.append(f"- Secondary concern: {sc}")
    rl = ob.get("routine_level")
    if rl:
        lines.append(f"- Routine level: {rl}")
    outdoor = ob.get("outdoor_frequency")
    if outdoor:
        lines.append(f"- Outdoor frequency: {outdoor}")
    dr = ob.get("dietary_restrictions")
    if dr:
        lines.append(f"- Dietary restrictions (reminders): {dr}")
    hyd = ob.get("skin_hydration_notifications")
    if hyd is not None:
        lines.append(f"- Hydration notifications enabled: {hyd}")
    exf = ob.get("exfoliation_weekday")
    if exf is not None:
        lines.append(f"- Exfoliation weekday (0=Mon … 6=Sun, or name): {exf}")
    if ob.get("retinoid_start_date"):
        lines.append(f"- Retinoid start date: {ob.get('retinoid_start_date')}")
    if ob.get("barrier_repair_weeks"):
        lines.append(f"- Barrier repair tracking: {ob.get('barrier_repair_weeks')}")
    return "\n".join(lines)


SKINMAX_JSON_DIRECTIVES = """## SKINMAX — JSON SCHEDULE OUTPUT (MANDATORY)

1. Use **exact HH:MM** (24h) for every task. Derive all times from wake_time and sleep_time using the reference + COMPUTED ANCHOR TIMES above.
2. **Do NOT** add a generic "morning check-in / let me know you're awake" at wake time for SkinMax — start the day with **AM Routine** at wake+15 (or stagger per MULTI-ACTIVE-MODULES if another module already owns wake).
3. Respect **quiet hours**: no tasks scheduled between sleep_time and wake_time.
4. Keep **3–5 tasks per calendar day**. Minimum daily: AM routine, Midday tip, PM routine. Add SPF reapply / hydration / restriction only when rules say so.
5. **Title + description** must reflect the correct concern protocol (AM steps, PM retinoid vs rest, exfoliation night copy when applicable).
6. On **weekly exfoliation day** (default Wednesday if not in onboarding), PM task = exfoliation routine from reference (not standard PM).
7. **Sunday**: add pillowcase reminder at midday time.
8. **1st of month**: progress photo at midday; routine check-in 30 min after PM time.
9. For `sometimes` outdoor: if outside_today is No, you may still schedule a short "Going outside today?" reminder near AM+3h window or fold into AM description — do **not** schedule SPF reapply unless they would be going out.
10. Use `task_type`: `routine` for AM/PM/exfoliation blocks, `reminder` for SPF/hydration/restriction/pillowcase/photo/check-in style pings.
"""


def get_skinmax_slot_times(wake_time: str, sleep_time: str) -> dict[str, str]:
    """Canonical slot labels → HH:MM for deterministic fallbacks and tests."""
    wh, wm = _parse_hm(wake_time)
    sh, sm = _parse_hm(sleep_time)
    am_h, am_m = _add_minutes(wh, wm, 15)
    pm_h, pm_m = _add_minutes(sh, sm, -60)
    am_mins = am_h * 60 + am_m
    pm_mins = pm_h * 60 + pm_m
    if pm_mins < am_mins:
        pm_mins += 24 * 60
    mid_mins = (am_mins + pm_mins) // 2
    mid_mins %= 24 * 60
    mid_h, mid_m = mid_mins // 60, mid_mins % 60
    hyd_h, hyd_m = _add_minutes(mid_h, mid_m, 120)
    spf_h, spf_m = _add_minutes(am_h, am_m, 180)
    return {
        "am_routine": _format_hm(am_h, am_m),
        "pm_routine": _format_hm(pm_h, pm_m),
        "midday_tip": _format_hm(mid_h, mid_m),
        "hydration": _format_hm(hyd_h, hyd_m),
        "spf_reapply": _format_hm(spf_h, spf_m),
    }
