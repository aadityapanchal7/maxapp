"""
HairMax notification engine — schedule generation + coaching reference.

Full reference: hairmax_notification_engine_reference.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_REF_FILE = Path(__file__).with_name("hairmax_notification_engine_reference.md")

try:
    HAIRMAX_NOTIFICATION_ENGINE_REFERENCE = _REF_FILE.read_text(encoding="utf-8")
except OSError:
    HAIRMAX_NOTIFICATION_ENGINE_REFERENCE = (
        "# HairMax notification reference missing. Restore hairmax_notification_engine_reference.md.\n"
    )

HAIRMAX_COACHING_REFERENCE = """## HAIRMAX NOTIFICATION ENGINE (condensed)

TIMING (wake + bed):
- Minoxidil AM = **wake + 15 min** | Minoxidil PM = **bed − 90 min**
- Finasteride (daily) = typical **wake + 30–45 min** (or user-picked once daily)
- Midday = midpoint(wake+15, bed−60) for **monthly check-in (1st)** and tips
- Ketoconazole = **2–3×/week** on wash days (not daily)
- Microneedling = **1×/week** user day (default Sunday), **not** same night as minox (24h); **never** same day as **face** microneedling if SkinMax — stagger
- Bloodwork = **3× year 1** (baseline ~3d after oral fin start, +180d, +365d) — not daily spam
- Bi-weekly **progress photos**; optional **shed** log on wash days
- Quiet hours: bed → wake

DOSE: 0.5mg fin ≈ 85–90% DHT suppression vs 1mg — respect user choice to stay on 0.5mg. Side ladder: 1st nocebo/wait → 2nd lower dose/EOD → 3rd topical or pause/restart 0.25mg. Sexual sides → stop resolves most; drop dose or change route.

RAMP: M1 fin+keto+tips+photos → M2–3 +minox 2× → M4+ +microneedling → M6/12 escalation per reference.

SKINMAX: merge AM/PM blocks (**scalp first**, face after wait); cap **10**/day total.

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


def format_hairmax_anchor_times(wake_time: str, sleep_time: str) -> str:
    wh, wm = _parse_hm(wake_time)
    sh, sm = _parse_hm(sleep_time)
    min_am_h, min_am_m = _add_minutes(wh, wm, 15)
    min_pm_h, min_pm_m = _add_minutes(sh, sm, -90)
    fin_h, fin_m = _add_minutes(wh, wm, 40)
    am15_h, am15_m = _add_minutes(wh, wm, 15)
    pm60_h, pm60_m = _add_minutes(sh, sm, -60)
    am_mins = am15_h * 60 + am15_m
    pm_mins = pm60_h * 60 + pm60_m
    if pm_mins < am_mins:
        pm_mins += 24 * 60
    mid_mins = (am_mins + pm_mins) // 2 % (24 * 60)
    mid_h, mid_m = mid_mins // 60, mid_mins % 60
    return f"""## COMPUTED ANCHOR TIMES — HAIRMAX
- Wake: {wake_time} | Bed: {sleep_time}
- **Minoxidil AM** → {_format_hm(min_am_h, min_am_m)} (wake + 15 min)
- **Minoxidil PM** → {_format_hm(min_pm_h, min_pm_m)} (bed − 90 min)
- **Finasteride (example daily slot)** → {_format_hm(fin_h, fin_m)} (wake + 40 min — adjust to user preference)
- **Midday (monthly 1st, tips)** → {_format_hm(mid_h, mid_m)} (midpoint wake+15 and bed−60)
"""


def summarize_hairmax_onboarding(
    onboarding: dict[str, Any],
    wake_time: str,
    sleep_time: str,
    concern: str,
) -> str:
    ob = onboarding or {}
    lines = [
        "## HAIRMAX USER PROFILE",
        f"- Selected concern / track: {concern}",
        f"- Wake / bed from request: {wake_time} / {sleep_time}",
    ]
    if ob.get("hair_type"):
        lines.append(f"- Hair type: {ob.get('hair_type')}")
    if ob.get("scalp_state"):
        lines.append(f"- Scalp: {ob.get('scalp_state')}")
    tier = ob.get("hairmax_treatment_tier") or ob.get("hair_treatment_tier")
    if tier:
        lines.append(f"- Treatment tier (1–4): {tier}")
    if ob.get("hair_finasteride_sensitive") is not None or ob.get("hairmax_fin_sensitive") is not None:
        lines.append(
            f"- Finasteride sensitivity / concern: {ob.get('hair_finasteride_sensitive') or ob.get('hairmax_fin_sensitive')}"
        )
    if ob.get("hair_topical_fin_only") or ob.get("hairmax_topical_fin_only"):
        lines.append("- Path: topical finasteride (no oral)")
    if ob.get("hairmax_fin_dose_preference"):
        lines.append(f"- Fin dose preference: {ob.get('hairmax_fin_dose_preference')}")
    if ob.get("hairmax_budget_band"):
        lines.append(f"- Product budget band: {ob.get('hairmax_budget_band')}")
    if ob.get("hairmax_microneedling_weekday") is not None:
        lines.append(f"- Microneedling weekday: {ob.get('hairmax_microneedling_weekday')}")
    if ob.get("hairmax_microneedling_time"):
        lines.append(f"- Microneedling time: {ob.get('hairmax_microneedling_time')}")
    if ob.get("hair_shed_tracking_opt_in") is not None:
        lines.append(f"- Shed tracking (wash days): {ob.get('hair_shed_tracking_opt_in')}")
    if ob.get("hair_fin_start_date"):
        lines.append(f"- Finasteride start date (bloodwork math): {ob.get('hair_fin_start_date')}")
    if ob.get("hairmax_months_on_treatment") is not None:
        lines.append(f"- Months on treatment (ramp phase): {ob.get('hairmax_months_on_treatment')}")
    return "\n".join(lines)


def get_hairmax_slot_times(wake_time: str, sleep_time: str) -> dict[str, str]:
    wh, wm = _parse_hm(wake_time)
    sh, sm = _parse_hm(sleep_time)
    min_am_h, min_am_m = _add_minutes(wh, wm, 15)
    min_pm_h, min_pm_m = _add_minutes(sh, sm, -90)
    fin_h, fin_m = _add_minutes(wh, wm, 40)
    am15_h, am15_m = _add_minutes(wh, wm, 15)
    pm60_h, pm60_m = _add_minutes(sh, sm, -60)
    am_mins = am15_h * 60 + am15_m
    pm_mins = pm60_h * 60 + pm60_m
    if pm_mins < am_mins:
        pm_mins += 24 * 60
    mid_mins = (am_mins + pm_mins) // 2 % (24 * 60)
    mid_h, mid_m = mid_mins // 60, mid_mins % 60
    mn_h, mn_m = _add_minutes(sh, sm, -120)
    return {
        "minoxidil_am": _format_hm(min_am_h, min_am_m),
        "minoxidil_pm": _format_hm(min_pm_h, min_pm_m),
        "finasteride": _format_hm(fin_h, fin_m),
        "midday": _format_hm(mid_h, mid_m),
        "microneedling_default": _format_hm(mn_h, mn_m),
    }


HAIRMAX_JSON_DIRECTIVES = """## HAIRMAX — JSON SCHEDULE OUTPUT (MANDATORY)

1. Use **HH:MM** 24h from wake/sleep; follow COMPUTED ANCHOR TIMES + reference (minox AM **wake+15**, PM **bed−90**).
2. **Do NOT** add a generic wake check-in as the only HairMax ping — first actionable task is **fin** and/or **minox AM** per ramp phase (merge with SkinMax AM per HAIRMAX+SKINMAX when both active).
3. **Quiet hours:** no tasks between sleep_time and wake_time.
4. **Treatment ramp:** month 1 ≠ full stack; stagger fin → minox → microneedling per engine.
5. **Microneedling:** weekly; **not** same night as minoxidil (24h separation); if SkinMax face microneedling exists, **different day** from scalp.
6. **Ketoconazole:** 2–3×/week only, on wash days.
7. **Bloodwork:** schedule as **checkpoint** tasks on specific dates (baseline ~3d after fin start, +180d, +365d) — not daily.
8. **Bi-weekly photos** and **monthly check-in** (1st at midday) as **checkpoint** tasks.
9. **Side-effect ladder** and **0.5mg vs 1mg** preference — reflect in description copy when relevant.
10. **task_type:** `routine` for applications; `reminder` for tips; `checkpoint` for photos, bloodwork, monthly review, microneedling session.
11. Cap **10** notifications/day **across all modules**; merge with SkinMax when instructed.
"""
