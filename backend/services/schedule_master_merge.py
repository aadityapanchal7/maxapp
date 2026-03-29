"""
Master-schedule merge + dedupe — mirrors mobile/utils/scheduleAggregation.ts
so streak completion matches what users see on Master Schedule / Home.
"""

from __future__ import annotations

import re
from typing import Any

_SKIN_TASK_RE = re.compile(
    r"\b(skinmax|skincare|skin care|spf\b|sunscreen|retinoid|retinol|\bam\s+skincare|\bpm\s+skincare|"
    r"cleanser?\b|niacinamide|exfoliat|your skinmax|moisturiz\w*|moisturis\w*|evening routine:\s*cleanse)\b",
    re.I,
)
_HAIR_TASK_RE = re.compile(
    r"\b(hairmax|minoxidil|finasteride|dutasteride|hair loss|ketoconazole\s+shampoo|"
    r"microneedl(?:e|ing)\s+(?:for\s+)?hair|dermaroll(?:er)?\s+(?:for\s+)?(?:hair|scalp))\b",
    re.I,
)

_DEFAULT_MAXX_LABELS: dict[str, str] = {
    "skinmax": "skinmax",
    "hairmax": "Hairmax",
    "fitmax": "Fitmax",
    "bonemax": "Bonemax",
    "heightmax": "Heightmax",
}


def normalize_maxx_id(raw: Any) -> str:
    if raw is None:
        return ""
    s = re.sub(r"\s+", "", str(raw).strip().lower())
    if not s:
        return ""
    aliases = {
        "skin-max": "skinmax",
        "hair-max": "hairmax",
        "fit-max": "fitmax",
        "bone-max": "bonemax",
        "height-max": "heightmax",
    }
    return aliases.get(s, s)


def _normalize_routine_title(title: str) -> str:
    s = re.sub(r"\s+", " ", (title or "").lower().strip())
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:56]


def _skincare_routine_fingerprint(title: str, desc: str) -> str:
    blob = f"{title or ''} {desc or ''}"
    if not _SKIN_TASK_RE.search(blob):
        return ""
    core = re.sub(
        r"\b(pm|am|p\.?m\.?|a\.?m\.?|evening|night|morning|bedtime|skincare|skin care|routine|daily)\b",
        " ",
        (title or "").lower(),
        flags=re.I,
    )
    core = re.sub(r"\s+", " ", core).strip()
    if len(core) < 2:
        core = "skincare_routine"
    return core[:48]


def _skincare_am_pm_bucket(title: str, desc: str, time_s: str) -> str:
    blob = f"{title or ''} {desc or ''}"
    if re.search(r"\b(pm|evening|night|bedtime|before bed)\b", blob, re.I):
        return "pm"
    if re.search(r"\b(am|morning)\b", blob, re.I):
        return "am"
    t = (time_s or "").strip()
    if ":" in t:
        try:
            h = int(t.split(":")[0])
            return "am" if h < 12 else "pm"
        except ValueError:
            pass
    return "x"


def _dedupe_key_for_task(
    module_label: str,
    title: str,
    desc: str,
    time_s: str,
) -> str:
    fp = _skincare_routine_fingerprint(title, desc)
    if fp:
        bucket = _skincare_am_pm_bucket(title, desc, time_s)
        return f"{module_label}|SC|{bucket}|{fp}"
    rk = _normalize_routine_title(title)
    return f"{module_label}|{(time_s or '').strip()}|{rk}"


def _display_module_label(
    task: dict[str, Any],
    schedule_mid: str,
    base_label: str,
    active_maxx_ids: set[str],
) -> str:
    blob = f"{task.get('title') or ''} {task.get('description') or ''}"
    skinish = bool(_SKIN_TASK_RE.search(blob))
    hairish = bool(_HAIR_TASK_RE.search(blob))
    if schedule_mid == "skinmax" and hairish and not skinish and "hairmax" in active_maxx_ids:
        return _DEFAULT_MAXX_LABELS.get("hairmax", "Hairmax")
    return base_label


def _dedupe_master_tasks(tasks: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for t in tasks:
        key = _dedupe_key_for_task(
            t["_mod_label"],
            t.get("title") or "",
            t.get("description") or "",
            t.get("time") or "",
        )
        prev = best.get(key)
        if not prev:
            best[key] = t
            continue
        next_len = len(t.get("description") or "")
        prev_len = len(prev.get("description") or "")
        best[key] = t if next_len >= prev_len else prev
    out = list(best.values())
    out.sort(key=lambda x: (x.get("time") or ""))
    for row in out:
        row.pop("_mod_label", None)
    return out


def collect_merged_tasks_for_date(schedules: list[dict], target_date: str) -> list[dict]:
    """
    Deduped logical tasks for target_date (YYYY-MM-DD), matching the app master view.
    Each item: schedule_id, task_id, status, time, title, description.
    """
    active_maxx_ids: set[str] = set()
    for s in schedules or []:
        m = normalize_maxx_id(s.get("maxx_id"))
        if m:
            active_maxx_ids.add(m)

    rows: list[dict] = []
    for s in schedules or []:
        sid = str(s.get("id") or "")
        mid = normalize_maxx_id(s.get("maxx_id"))
        if mid in _DEFAULT_MAXX_LABELS:
            base_label = _DEFAULT_MAXX_LABELS[mid]
        else:
            base_label = str(s.get("course_title") or s.get("maxx_id") or "Program")

        for day in s.get("days") or []:
            d = day.get("date")
            if not d or d != target_date:
                continue
            for t in day.get("tasks") or []:
                blob_early = f"{t.get('title') or ''} {t.get('description') or ''}"
                skin_early = bool(_SKIN_TASK_RE.search(blob_early))
                hair_early = bool(_HAIR_TASK_RE.search(blob_early))
                if mid == "hairmax" and skin_early and not hair_early:
                    continue

                mod_label = _display_module_label(t, mid, base_label, active_maxx_ids)
                rows.append(
                    {
                        "schedule_id": sid,
                        "task_id": t.get("task_id"),
                        "status": str(t.get("status") or "pending").lower(),
                        "time": t.get("time") or "",
                        "title": t.get("title") or "",
                        "description": t.get("description") or "",
                        "_mod_label": mod_label,
                    }
                )

    return _dedupe_master_tasks(rows)


def merged_day_all_completed(schedules: list[dict], target_date: str) -> bool:
    tasks = collect_merged_tasks_for_date(schedules, target_date)
    if not tasks:
        return False
    return all(t.get("status") == "completed" for t in tasks)
