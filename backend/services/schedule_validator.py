"""Deterministic schedule validator.

Runs after every generation/adapt and before anything is saved. Catches
hallucinated tasks, invalid task IDs, time collisions, sleep-window
violations, duplicate titles, oversized tasks/days. Returns either:
  - (True, [], days_normalized)            — clean
  - (False, [errors_list], days_normalized) — caller can surface to LLM
                                              for one retry pass

The validator also AUTOMATICALLY FIXES soft issues (push 5min separation
between same-window tasks, truncate over-long titles) so the LLM doesn't
have to bother with them. Hard errors (unknown task ID, bad day count,
catastrophic structure) require regeneration.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import time as dtime
from typing import Any

from services.schedule_dsl import (
    from_minutes,
    parse_clock,
    resolve_window,
    to_minutes,
)
from services.task_catalog_service import all_tasks, get_task

logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 28
# 15-min minimum so a routine that fans into 4 sub-tasks doesn't fire 4
# notifications inside 20 minutes (was 5; produced morning storms).
MIN_TASK_GAP_MIN = 15
# Per-module daily cap. Single skinmax user needs 7-8 (AM cleanse +
# moisturize + SPF = 3 just for the morning foundation, before any
# active or PM routine). Cross-module total is capped separately at 6
# in multi_module_collision so 3 active maxxes don't aggregate to 24.
HARD_DAILY_TASK_CAP = 8


# Tokens that should keep their original casing in task titles even when
# the rest of the title is lowercased. These are common abbreviations
# users recognize visually; rendering them lowercase ("am nutrition",
# "spf 50", "liss cardio") looks wrong and reduces scan-ability.
_PRESERVE_CASE_TOKENS = (
    "AM", "PM", "SPF", "UV", "BHA", "AHA", "PHA", "LISS", "HIIT",
    "TDEE", "RIR", "DB", "BB", "OHP", "RDL", "PPL", "TMJ",
    "K2", "D3", "B5", "B12", "C", "EAA", "BCAA", "MMA",
)


def _normalize_title_case(raw: str) -> str:
    """Lowercase a task title but preserve common ALL-CAPS abbreviations
    (AM, PM, SPF, LISS, etc). Without this, the validator's earlier
    blanket .lower() turned "AM nutrition" into "am nutrition", which
    reads wrong for a scannable reminder list.
    """
    if not raw:
        return ""
    lo = raw.strip().lower()
    out = lo
    for tok in _PRESERVE_CASE_TOKENS:
        # Word-boundary, case-insensitive replace back to canonical casing.
        out = re.sub(rf"\b{tok.lower()}\b", tok, out)
    return out


# Title humanization — converts catalog-style technical titles into
# reminder-style friendly phrases. Called once per task in the validator;
# every catalog gets the same human pass without needing to maintain
# parallel display strings in each .md doc.
#
# Patterns are tried in order. First match wins. Each entry:
#   (regex,  replacement_template,  flags)
# Replacement may use \\1 \\2 capture refs.
_HUMANIZE_PATTERNS: list[tuple[str, str]] = [
    # Skin / hair / face routines — reframe as ACTION the user takes
    (r"^cleanse face \(am\)$",          "wash your face"),
    (r"^cleanse face \(pm\)$",          "wash your face before bed"),
    (r"^moisturize \(am\)$",            "moisturize your face"),
    (r"^moisturize \(pm\)$",            "moisturize before bed"),
    (r"^apply spf 50$",                 "put on SPF — last step"),
    (r"^reapply spf$",                  "reapply your SPF"),
    (r"^apply azelaic acid$",           "apply azelaic acid serum"),
    (r"^apply centella serum$",         "apply your calming serum"),
    (r"^apply retinoid \(pea\)$",       "retinoid — pea-sized, dry skin"),
    (r"^dermastamp face$",              "dermastamp face (1 pass)"),
    (r"^facial massage \((\d+)s\)$",    r"face massage — \1 seconds"),
    (r"^drink water — 1l target$",      "hydration check — water break"),
    (r"^skip seed oils \+ sugar$",      "diet check — skip seed oils, sugar"),
    (r"^take zinc \+ collagen$",        "zinc + collagen supplement"),
    (r"^skip actives — barrier rest$",  "barrier rest — skip actives tonight"),
    (r"^pillowcase change$",            "fresh pillowcase tonight"),
    (r"^weekly exfoliation \(.+?\)$",   "weekly exfoliation — PHA / AHA"),
    (r"^hydration mask \(15 min\)$",    "hydration mask before bed"),
    (r"^photo: face front \+ sides$",   "skin progress photo"),
    (r"^monthly skin review$",          "monthly skin check-in"),
    (r"^schedule derm check \(6mo\)$",  "book a dermatologist visit"),

    # Hair
    (r"^wash \+ condition$",            "shampoo + condition"),
    (r"^co-wash curls$",                "midweek co-wash"),
    (r"^apply leave-in$",               "apply leave-in conditioner"),
    (r"^style with product$",           "style your hair"),
    (r"^rinse out product \(pm\)$",     "rinse hair before bed"),
    (r"^massage scalp \(60s\)$",        "scalp massage — 60 seconds"),
    (r"^apply minoxidil \(am, 1ml\)$",  "morning minoxidil — 1ml to scalp"),
    (r"^apply minoxidil \(pm, 1ml\)$",  "evening minoxidil — 1ml to scalp"),
    (r"^microneedle scalp 0\.5mm$",     "scalp microneedle (0.5mm)"),
    (r"^take finasteride$",             "take finasteride"),
    (r"^photo: scalp \+ hairline$",     "hair progress photo"),
    (r"^trim beard / neckline$",        "beard / neckline trim"),
    (r"^apply heat protectant$",        "heat protectant before styling"),
    (r"^book next haircut$",            "book your next haircut"),
    (r"^ketoconazole shampoo wash$",    "ketoconazole wash (anti-fungal)"),
    (r"^deep-condition mask$",          "deep-conditioning mask"),
    (r"^monthly hair review$",          "monthly hair check-in"),
    (r"^bloodwork check \(quarterly\)$", "bloodwork check (every 3 months)"),

    # Bone / mewing
    (r"^mewing \(am set, (\d+)s\)$",    r"morning mewing — \1 second hold"),
    (r"^mewing reset \(midday, (\d+)s\)$", r"midday mewing reset (\1s)"),
    (r"^mewing \(night set\)$",         "night mewing set"),
    (r"^chew mastic gum \((\d+) min\)$", r"mastic gum — \1 min, alternate sides"),
    (r"^chew mastic gum \(ramp\)$",     "mastic gum — ramp set"),
    (r"^facial massage \(am\)$",        "AM facial massage / lymph"),
    (r"^facial fascia release \(pm\)$", "PM fascia release"),
    (r"^nasal-breathing check$",        "nasal-breathing check"),
    (r"^neck training \(full set\)$",   "neck training — full set"),
    (r"^neck training \(solo day\)$",   "neck training — solo day"),
    (r"^chin tucks ×(\d+)$",            r"chin tucks — \1 reps"),
    (r"^symmetry / posture check$",     "posture / symmetry check"),
    (r"^take d3 \+ k2 \(with food\)$",  "vitamin D3 + K2 with food"),
    (r"^take magnesium \(pm\)$",        "magnesium before bed"),
    (r"^photo: jaw \+ side profile$",   "jaw progress photo"),
    (r"^monthly jaw review$",           "monthly jaw check-in"),
    (r"^hard mewing \(60s suction hold\)$", "hard mewing — 60s suction hold"),
    (r"^lip tape \(bedtime\)$",         "lip tape (medical paper) before bed"),
    (r"^alternate chewing sides$",      "alternate chewing sides"),

    # Height
    (r"^am mobility \(5 min\)$",        "AM mobility — 5 min"),
    (r"^desk reset \(5 min\)$",         "desk reset — 5 min posture break"),
    (r"^pm decompression \(5 min\)$",   "spinal decompression — 5 min"),
    (r"^dead hang \(60s\)$",            "dead hang — 60 seconds"),
    (r"^wall posture drill$",           "wall posture drill"),
    (r"^face pulls 3×12$",              "face pulls — 3 sets of 12"),
    (r"^glute bridge 3×15$",            "glute bridge — 3 sets of 15"),
    (r"^check sleep window$",           "wind down — sleep is coming"),
    (r"^hit protein \(~1g/lb\)$",       "protein check — about 1g per lb"),
    (r"^10 min am sunlight$",           "10 min sunlight (AM)"),
    (r"^outfit proportions check$",     "outfit proportions check"),
    (r"^rotate shoes \(weekly\)$",      "rotate your shoes (weekly)"),
    (r"^mirror posture check$",         "mirror posture check"),
    (r"^chin tucks ×15$",               "chin tucks — 15 reps"),
    (r"^foam-roll upper back$",         "foam-roll upper back"),
    (r"^log am height$",                "log your morning height"),
    (r"^photo: full-body posture$",     "posture / height photo"),
    (r"^monthly height review$",        "monthly height check-in"),
    (r"^inversion table \(5 min\)$",    "inversion — 5 min"),
    (r"^calcium-rich meal$",            "calcium-rich meal (one today)"),

    # Fit
    (r"^eat am protein meal$",          "eat AM protein meal"),
    (r"^midday training cue$",          "midday training cue"),
    (r"^eat pm meal \(protein \+ carb\)$", "PM meal — protein + carb"),
    (r"^pre-workout fuel$",             "pre-workout fuel + caffeine"),
    (r"^lift session$",                 "lift session"),
    (r"^post-workout protein$",         "post-workout protein (40g)"),
    (r"^hit step target$",              "hit your step target"),
    (r"^liss cardio \(30 min\)$",       "LISS cardio — 30 min"),
    (r"^weekly weigh-in$",              "weekly weigh-in (fasted)"),
    (r"^take progress photo$",          "monthly progress photo"),
    (r"^deload week — drop volume$",    "deload week — half volume"),
    (r"^hydration check$",              "hydration check"),
    (r"^mobility warm-up \(10 min\)$",  "mobility warm-up — 10 min"),
    (r"^wind down — bed in 60 min$",    "wind down — bed in 60 min"),
    (r"^lunch protein hit$",            "lunch protein hit (30-40g)"),
    (r"^pm stretch \(8 min\)$",         "PM stretch — 8 min"),
    (r"^weekly progress review$",       "weekly progress review"),
    (r"^monthly check-in$",             "monthly progress check-in"),
    (r"^form-check video$",             "film a form-check video"),
    (r"^take creatine \(5g\)$",         "take creatine — 5g"),
    (r"^full body a$",                  "lift session — Full Body A"),
    (r"^full body b$",                  "lift session — Full Body B"),
    (r"^full body c$",                  "lift session — Full Body C"),
    (r"^upper a — push focus$",         "lift — Upper A (push focus)"),
    (r"^lower a — squat focus$",        "lift — Lower A (squat focus)"),
    (r"^upper b — pull focus$",         "lift — Upper B (pull focus)"),
    (r"^lower b — deadlift focus$",     "lift — Lower B (deadlift focus)"),
    (r"^push day a$",                   "lift — Push A"),
    (r"^pull day a$",                   "lift — Pull A"),
    (r"^legs day a$",                   "lift — Legs A"),
    (r"^push day b$",                   "lift — Push B"),
    (r"^pull day b$",                   "lift — Pull B"),
    (r"^legs day b$",                   "lift — Legs B"),
]


def _format_description(raw: str) -> str:
    """Break a long single-paragraph description into scannable lines.

    Real coach-style notification body: each step on its own line, prefixed
    with a bullet. Mobile renders the description verbatim, so adding `\n`
    + bullet markers yields a multi-line card the user can skim.

    Heuristics:
    - If the description is already multi-line OR short (≤80 chars), leave as-is.
    - Split on sentence boundaries (. ! ?) AND comma-separated step lists
      that look like "X 4×6, Y 3×8, Z 3×10" (workout/skincare instructions).
    - Wrap each step in "• " bullet marker.
    - Cap at 6 bullets — past that the body becomes a wall again.
    """
    if not raw:
        return ""
    raw = raw.strip()
    if "\n" in raw or len(raw) <= 80:
        return raw

    # Identify a leading prefix like "warm-up: ..." that wraps the whole
    # description; surface it as the first bullet.
    pieces: list[str] = []

    # First pass: split on sentence ends.
    sentence_split = re.split(r"(?<=[.!?])\s+(?=[a-z0-9A-Z])", raw)
    for s in sentence_split:
        s = s.strip()
        if not s:
            continue
        # If a sentence contains a "x 4×6, y 3×8, z 3×10" exercise list
        # (or comma-separated multi-step list), break it on commas too.
        if re.search(r"\d×\d", s) or s.count(", ") >= 3:
            sub_pieces = [p.strip() for p in s.split(",") if p.strip()]
            pieces.extend(sub_pieces)
        else:
            pieces.append(s)

    # Drop the trailing period from each piece for cleaner bullets.
    cleaned = []
    for p in pieces:
        p = p.rstrip(". ")
        if p:
            cleaned.append(p)

    if len(cleaned) <= 1:
        # Nothing meaningful to split on — return original.
        return raw
    if len(cleaned) > 6:
        # Cap to 6 bullets so the body doesn't become its own wall.
        # Merge the tail into the last bullet so we don't lose info.
        cleaned = cleaned[:5] + [", ".join(cleaned[5:])]

    return "\n".join(f"• {p}" for p in cleaned)


def _humanize_title(catalog_title: str) -> str:
    """Convert a catalog-style title to a reminder-style friendly phrase.

    Falls through to the original title (lowercased + abbrev-cased) when
    no pattern matches. Adding a new task doesn't require a humanize
    entry — it just stays as-is. Adding an entry overrides the default.
    """
    if not catalog_title:
        return ""
    base = _normalize_title_case(catalog_title)
    for pat, repl in _HUMANIZE_PATTERNS:
        m = re.match(pat, base, re.IGNORECASE)
        if m:
            new = re.sub(pat, repl, base, flags=re.IGNORECASE)
            return _normalize_title_case(new)
    return base


@dataclass
class ValidationError:
    severity: str  # "hard" | "soft"
    code: str
    message: str
    day_index: int | None = None
    task_id: str | None = None


def validate_and_fix(
    *,
    maxx_id: str,
    days: list[dict],
    wake_time: str,
    sleep_time: str,
    user_ctx: dict[str, Any],
    expected_day_count: int | None = None,
    daily_task_budget: tuple[int, int] | None = None,
) -> tuple[bool, list[ValidationError], list[dict]]:
    """Validate + fix-where-safe. Returns (clean, errors, fixed_days).

    `clean` is False ONLY when there are HARD errors. Soft fixes don't
    flip clean to False — they're applied silently.
    """
    errors: list[ValidationError] = []
    if not isinstance(days, list):
        errors.append(ValidationError("hard", "structure", "days must be a list"))
        return False, errors, []

    wake = parse_clock(wake_time, "07:00")
    sleep = parse_clock(sleep_time, "23:00")
    sleep_min = _sleep_minutes_normalized(wake, sleep)

    valid_ids = {t.id for t in all_tasks(maxx_id)}
    if expected_day_count and len(days) != expected_day_count:
        errors.append(ValidationError(
            "soft", "day_count_mismatch",
            f"expected {expected_day_count} days, got {len(days)}",
        ))

    fixed_days: list[dict] = []
    for di, day in enumerate(days):
        tasks = day.get("tasks") or []
        if not isinstance(tasks, list):
            errors.append(ValidationError("hard", "day_tasks_type", "day.tasks must be a list", day_index=di))
            continue

        clean_tasks: list[dict] = []
        for task in tasks:
            err, fixed = _validate_task(
                task=task, day_index=di, valid_ids=valid_ids, maxx_id=maxx_id,
                wake=wake, sleep_min=sleep_min,
            )
            errors.extend(err)
            if fixed is not None:
                clean_tasks.append(fixed)

        clean_tasks = _enforce_separation(clean_tasks, day_index=di, errors=errors)

        # Daily task budget
        if daily_task_budget:
            mn, mx = daily_task_budget
            if len(clean_tasks) < mn:
                errors.append(ValidationError(
                    "soft", "below_min_tasks",
                    f"day {di+1}: {len(clean_tasks)} tasks < min {mn}",
                    day_index=di,
                ))
            if len(clean_tasks) > mx:
                # Drop lowest-intensity (cosmetic) tasks beyond cap.
                clean_tasks = _truncate_by_intensity(clean_tasks, maxx_id, mx)
                errors.append(ValidationError(
                    "soft", "above_max_tasks",
                    f"day {di+1}: trimmed to budget max {mx}",
                    day_index=di,
                ))

        # Hard cap regardless of per-max budget
        if len(clean_tasks) > HARD_DAILY_TASK_CAP:
            clean_tasks = _truncate_by_intensity(clean_tasks, maxx_id, HARD_DAILY_TASK_CAP)
            errors.append(ValidationError(
                "soft", "hard_cap",
                f"day {di+1}: trimmed to hard cap {HARD_DAILY_TASK_CAP}",
                day_index=di,
            ))

        fixed_days.append({**day, "tasks": clean_tasks})

    # Cross-day antagonism: retinoid + dermastamp on same day
    _detect_antagonism(fixed_days, maxx_id, errors)

    has_hard = any(e.severity == "hard" for e in errors)
    return (not has_hard), errors, fixed_days


def _validate_task(
    *,
    task: dict,
    day_index: int,
    valid_ids: set[str],
    maxx_id: str,
    wake: dtime,
    sleep_min: int,
) -> tuple[list[ValidationError], dict | None]:
    errs: list[ValidationError] = []
    if not isinstance(task, dict):
        return [ValidationError("hard", "task_type", "task must be object", day_index=day_index)], None

    cat_id = task.get("catalog_id") or task.get("task_catalog_id")
    if not cat_id:
        return [ValidationError("hard", "missing_catalog_id",
                                "task missing catalog_id", day_index=day_index)], None
    if cat_id not in valid_ids:
        return [ValidationError("hard", "unknown_catalog_id",
                                f"catalog_id {cat_id!r} not in {maxx_id} catalog",
                                day_index=day_index, task_id=cat_id)], None

    catalog_task = get_task(maxx_id, cat_id)
    raw_title = (task.get("title") or catalog_task.title or "").strip()
    # Run through the humanizer first so reminder-friendly phrasing wins
    # over the technical catalog title. _humanize_title falls through to
    # the original (lowercased) title if no pattern matches, so adding a
    # task without a humanize entry is safe.
    title = _humanize_title(raw_title)
    # Bump the cap so the friendlier rephrasings (often a few chars
    # longer) don't get truncated mid-word.
    soft_cap = max(MAX_TITLE_CHARS, 36)
    if len(title) > soft_cap:
        title = title[: soft_cap - 1].rstrip() + "…"
    elif not title:
        title = catalog_task.title

    description = (task.get("description") or catalog_task.description or "").strip()
    if len(description) > 380:  # bumped from 220 — bullets give us extra char budget
        description = description[:377].rstrip() + "..."
    description = _format_description(description)

    # Time
    raw_time = task.get("time") or ""
    minute = _parse_time_field(raw_time)
    if minute is None:
        # Fallback to mid-window of catalog default_window.
        try:
            sleep_t = from_minutes(sleep_min if sleep_min < 24*60 else sleep_min - 24*60)
            ws, we = resolve_window(catalog_task.default_window, wake=wake, sleep=sleep_t)
            minute = (ws + we) // 2
        except Exception:
            minute = to_minutes(wake) + 60

    # Sleep window violation: anything between sleep and wake (next morning) is invalid.
    if _is_during_sleep(minute, wake_min=to_minutes(wake), sleep_min=sleep_min):
        errs.append(ValidationError(
            "soft", "sleep_window",
            f"task at {raw_time or minute} falls inside sleep window — moved",
            day_index=day_index, task_id=cat_id,
        ))
        # Push to wake+1hr (am_open default).
        minute = to_minutes(wake) + 60

    fixed = {
        "task_id": task.get("task_id") or _stable_uid(),
        "catalog_id": cat_id,
        "title": title,
        "description": description,
        "time": from_minutes(minute).strftime("%H:%M"),
        "duration_min": int(task.get("duration_min", catalog_task.duration_min)),
        "tags": list(task.get("tags") or catalog_task.tags),
        "status": task.get("status") or "pending",
        "intensity": float(catalog_task.intensity),
    }
    return errs, fixed


# Routine-step priority — lower = earlier in the routine. Lookup by tag.
# A real coach orders these strictly: no one moisturizes BEFORE cleansing,
# no one applies SPF AFTER scalp minoxidil (causes facial migration of
# minox), no one takes a supplement before hydrating their face. The
# validator re-orders within each ~30-min window using these priorities
# before stamping gap-separated times.
_ROUTINE_PRIORITY: dict[str, int] = {
    # AM face routine (must run in this order)
    "cleanse":          10,
    "wash":             10,
    "active":           20,  # serums, treatments — vit C, BHA, niacinamide
    "anti-inflammatory": 25,
    "hydration":        28,  # leave-ins, hyaluronic
    "barrier":          30,  # ceramides, panthenol
    "moisturize":       35,
    "moisturizer":      35,
    "spf":              40,  # ALWAYS last face step in AM
    "protect":          40,
    # Hair / scalp tasks (after face fully done so SPF dries first)
    "scalp-care":       55,
    "scalp":            55,
    "loss-prevention":  60,  # minoxidil
    "treatment":        60,
    "styling":          70,
    "post-wash":        70,
    "grooming":         70,
    # Mewing / posture (passive — slot anywhere after the active stuff)
    "mewing":           80,
    "posture":          80,
    "fascia":           85,
    "lymph":            85,
    # Internal / nutrition (eat after applying topicals; gum after AM stack)
    "supplement":       90,
    "nutrition":        90,
    "protein":          90,
    "masseter":         95,  # chew gum after morning routine
    "jaw":              95,
    # Decompression / mobility / cardio (own time, but rank low so they
    # don't insert mid-skincare if same slot)
    "mobility":         100,
    "decompression":    100,
    "stretch":          100,
    "cardio":           105,
    "steps":            105,
    "neat":             105,
    # Workout window — pre/lift/post sequence enforced by their distinct slots,
    # but if collisions happen these priorities back them up.
    "preworkout":       110,
    "warmup":           115,
    "workout":          120,
    "lift":             120,
    "training":         120,
    "postworkout":      125,
    "recovery":         130,
    # PM bedtime stack
    "pm":               140,
    "sleep":            150,
    "wind-down":        155,
}


def _routine_score(t: dict) -> int:
    """Lower = earlier in the routine. Picks the lowest-priority tag the
    task carries; defaults to 200 (slot-end) if none of its tags are in
    the priority map."""
    tags = t.get("tags") or []
    if not tags:
        return 200
    scores = [_ROUTINE_PRIORITY[g] for g in tags if g in _ROUTINE_PRIORITY]
    return min(scores) if scores else 200


def _enforce_separation(tasks: list[dict], *, day_index: int, errors: list[ValidationError]) -> list[dict]:
    """Sort tasks by (slot bucket, routine priority, original time); push
    later tasks forward to enforce min gap.

    Routine priority means: within the same ~30-min window, cleanse fires
    before serum before moisturizer before SPF before minoxidil before
    supplements — regardless of which block emitted them. Without this,
    cross-block emission order followed declaration order in the .md doc,
    so a hairmax minox AM block declared above a skinmax SPF block could
    fire MINOX FIRST then SPF, causing minox migration to face skin.
    """
    if not tasks:
        return tasks
    # Bucket size: tasks landing within 45 min of each other are treated
    # as the "same routine block" and re-ordered by priority. Beyond
    # that, the original time wins (lunch should not get pulled into the
    # morning routine because it has the lowest score).
    BUCKET_MIN = 45

    timed = [(t, _parse_time_field(t["time"]) or 0) for t in tasks]
    timed.sort(key=lambda x: x[1])

    # Bucketize: contiguous tasks within BUCKET_MIN of the bucket's first
    # task share a bucket.
    buckets: list[list[tuple[dict, int]]] = []
    for t, start in timed:
        if buckets and start - buckets[-1][0][1] <= BUCKET_MIN:
            buckets[-1].append((t, start))
        else:
            buckets.append([(t, start)])

    # Within each bucket, sort by routine priority then by original time.
    reordered: list[tuple[dict, int]] = []
    for b in buckets:
        b.sort(key=lambda pair: (_routine_score(pair[0]), pair[1]))
        # Anchor the bucket to the EARLIEST original time in the bucket
        # so reordering doesn't shift the whole block earlier or later.
        anchor = min(p[1] for p in b)
        reordered.extend((t, anchor) for (t, _) in b)

    # Stamp times sequentially with MIN_TASK_GAP_MIN spacing.
    last_end = -1
    out = []
    for t, anchor in reordered:
        start = max(anchor, last_end + MIN_TASK_GAP_MIN if last_end >= 0 else anchor)
        original_start = _parse_time_field(t["time"]) or 0
        if start != original_start:
            errors.append(ValidationError(
                "soft", "time_collision",
                f"day {day_index+1}: re-stamped {t['title']!r} to {from_minutes(start)}",
                day_index=day_index, task_id=t.get("catalog_id"),
            ))
            t = {**t, "time": from_minutes(start).strftime("%H:%M")}
        last_end = start + max(1, int(t.get("duration_min", 1)))
        out.append(t)
    return out


# Tags that mark a task as ESSENTIAL — never drop these even if the day
# blows past the cap. SPF, cleanse, and the workout sessions are non-
# negotiable; dropping them would leave the user with a broken protocol.
_ESSENTIAL_TAGS = frozenset({
    "foundation",  # cleanse / moisturize / SPF / barrier — the daily floor
    "spf",
    "cleanse",
    "wash",
    "workout",     # the lift session itself
    "training",
    "lift",
})


def _truncate_by_intensity(tasks: list[dict], maxx_id: str, cap: int) -> list[dict]:
    """Drop the most-skippable tasks until we're under the cap.

    Three-tier priority (kept in this order):
      1. Tasks tagged essential (cleanse, spf, foundation, workout) —
         these are the floor of any real protocol; never drop them.
      2. Among non-essentials, keep highest-intensity first.
      3. Tie-break by earliest time.

    Without (1), an over-cap day would drop SPF (intensity 0.1) before
    the daily symmetry-check (intensity 0.1, but tied) — leaving the
    user with a skin protocol that's missing sun protection. Real
    coaches never make that trade.
    """
    def _is_essential(t: dict) -> bool:
        tags = set(t.get("tags") or [])
        return bool(tags & _ESSENTIAL_TAGS)

    essentials = [t for t in tasks if _is_essential(t)]
    optional = [t for t in tasks if not _is_essential(t)]

    # If essentials alone exceed the cap, keep the highest-intensity
    # essentials. (Extreme edge case — a maxx with > cap foundation
    # tasks. Real docs don't hit this.)
    if len(essentials) > cap:
        essentials.sort(
            key=lambda t: (-(t.get("intensity") or 0.0), _parse_time_field(t["time"]) or 0),
        )
        kept = essentials[:cap]
    else:
        slots_left = cap - len(essentials)
        optional.sort(
            key=lambda t: (-(t.get("intensity") or 0.0), _parse_time_field(t["time"]) or 0),
        )
        kept = essentials + optional[:slots_left]

    return sorted(kept, key=lambda t: _parse_time_field(t["time"]) or 0)


# Pairs of catalog_ids that must NOT appear on the same day.
_ANTAGONISTIC = {
    frozenset({"skin.retinoid_pm", "skin.dermastamp_pm"}),
    frozenset({"hair.minoxidil_am", "hair.microneedle_pm"}),
    frozenset({"hair.minoxidil_pm", "hair.microneedle_pm"}),
}


def _detect_antagonism(days: list[dict], maxx_id: str, errors: list[ValidationError]) -> None:
    for di, day in enumerate(days):
        ids = {t.get("catalog_id") for t in (day.get("tasks") or [])}
        for pair in _ANTAGONISTIC:
            if pair.issubset(ids):
                errors.append(ValidationError(
                    "hard", "antagonistic_pair",
                    f"day {di+1}: {sorted(pair)} must not coexist on same day",
                    day_index=di,
                ))


def _parse_time_field(s: Any) -> int | None:
    if isinstance(s, int):
        return s
    if not isinstance(s, str):
        return None
    s = s.strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def _is_during_sleep(minute: int, *, wake_min: int, sleep_min: int) -> bool:
    """sleep_min is normalized so sleep_min > wake_min always."""
    minute_norm = minute if minute >= wake_min else minute + 24 * 60
    return minute_norm < wake_min or minute_norm >= sleep_min


def _sleep_minutes_normalized(wake: dtime, sleep: dtime) -> int:
    s = to_minutes(sleep)
    w = to_minutes(wake)
    if s < w:
        s += 24 * 60
    return s


def _stable_uid() -> str:
    from uuid import uuid4
    return str(uuid4())
