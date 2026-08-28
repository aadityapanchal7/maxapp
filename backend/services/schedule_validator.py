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
from datetime import date as _date, time as dtime, timedelta as _timedelta
from typing import Any

from services.schedule_dsl import (
    crosses_midnight,
    from_minutes,
    order_minutes,
    parse_clock,
    resolve_window,
    schedulable_anchors,
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


# Em-dash (U+2014) is the single biggest "a bot wrote this" tell in task
# copy. Strip it from every title/description/motivation that reaches the
# user (calendar grid AND the SMS reminder path, which reads stored task
# text directly). En-dashes (U+2013) inside numeric ranges like "30-40g"
# or "8-12 weeks" are intentionally LEFT ALONE. Rule: if a number follows
# the dash it's a measure ("dead hang - 60s") so join with a space; every
# other case is a clause ("rest your barrier - no actives") so use a comma.
_EM_DASH = "—"


def _strip_em_dashes(text: str) -> str:
    if not text or _EM_DASH not in text:
        return text
    out = re.sub(r"\s*" + _EM_DASH + r"\s*(?=\d)", " ", text)   # measure follows
    out = re.sub(r"\s*" + _EM_DASH + r"\s*", ", ", out)          # clause follows
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()


# Title humanization — converts catalog-style technical titles into
# reminder-style friendly phrases. Called once per task in the validator;
# every catalog gets the same human pass without needing to maintain
# parallel display strings in each .md doc.
#
# Patterns are tried in order. First match wins. Each entry:
#   (regex,  replacement_template,  flags)
# Replacement may use \\1 \\2 capture refs.
_HUMANIZE_PATTERNS: list[tuple[str, str]] = [
    # Voice/style guide for these titles:
    #   - Speak TO the user — imperative, second-person, action-first.
    #   - Drop technical scaffolding ("session", "set", "drill") when a
    #     plain verb gets there faster ("lift", "stretch", "mew").
    #   - Keep doses/durations only when they're non-obvious cues the user
    #     needs at glance time ("60s", "1g/lb", "3×12").
    #   - Lowercase prevails; abbreviations preserved by _PRESERVE_CASE_TOKENS.
    #
    # ────────────────────────── SKIN ──────────────────────────────────
    (r"^cleanse face \(am\)$",          "wash your face"),
    (r"^cleanse face \(pm\)$",          "wash your face before bed"),
    (r"^moisturize \(am\)$",            "moisturize"),
    (r"^moisturize \(pm\)$",            "moisturize before bed"),
    (r"^apply spf 50$",                 "put on SPF"),
    (r"^reapply spf$",                  "reapply your SPF"),
    (r"^apply azelaic acid$",           "azelaic acid serum"),
    (r"^apply centella serum$",         "calming serum"),
    (r"^apply retinoid \(pea\)$",       "retinoid (pea-sized) on dry skin"),
    (r"^dermastamp face$",              "dermastamp your face"),
    (r"^facial massage \((\d+)s\)$",    r"face massage — \1s"),
    (r"^drink water — 1l target$",      "drink water"),
    (r"^skip seed oils \+ sugar$",      "skip seed oils + sugar today"),
    (r"^take zinc \+ collagen$",        "take zinc + collagen"),
    (r"^skip actives — barrier rest$",  "rest your barrier — no actives"),
    (r"^pillowcase change$",            "swap pillowcase"),
    (r"^weekly exfoliation \(.+?\)$",   "weekly exfoliation"),
    (r"^hydration mask \(15 min\)$",    "hydration mask"),
    (r"^photo: face front \+ sides$",   "take a skin photo"),
    (r"^monthly skin review$",          "monthly skin check-in"),
    (r"^schedule derm check \(6mo\)$",  "book a derm visit"),

    # ────────────────────────── HAIR ──────────────────────────────────
    (r"^minoxidil am$",                 "apply minoxidil"),
    (r"^minoxidil pm$",                 "apply minoxidil before bed"),
    (r"^shampoo \+ condition$",         "shampoo + condition"),
    (r"^60s scalp massage$",            "scalp massage — 60s"),
    (r"^scalp microneedle 0\.5mm$",     "microneedle your scalp"),
    (r"^style \+ product am$",          "style your hair"),
    (r"^rinse out product pm$",         "rinse out hair product"),
    (r"^finasteride daily$",            "take finasteride"),
    (r"^scalp/hairline photo$",         "take a hair photo"),
    (r"^heat protectant spray$",        "spray heat protectant"),
    (r"^beard / neckline trim$",        "trim beard / neckline"),
    (r"^wash \+ condition$",            "shampoo + condition"),
    (r"^co-wash curls$",                "co-wash your curls"),
    (r"^apply leave-in$",               "apply leave-in conditioner"),
    (r"^style with product$",           "style your hair"),
    (r"^rinse out product \(pm\)$",     "rinse out hair product"),
    (r"^massage scalp \(60s\)$",        "scalp massage — 60s"),
    (r"^apply minoxidil \(am, 1ml\)$",  "apply minoxidil — 1ml"),
    (r"^apply minoxidil \(pm, 1ml\)$",  "apply minoxidil before bed — 1ml"),
    (r"^microneedle scalp 0\.5mm$",     "microneedle your scalp"),
    (r"^take finasteride$",             "take finasteride"),
    (r"^photo: scalp \+ hairline$",     "take a hair photo"),
    (r"^trim beard / neckline$",        "trim beard / neckline"),
    (r"^apply heat protectant$",        "spray heat protectant"),
    (r"^book next haircut$",            "book your next haircut"),
    (r"^ketoconazole shampoo wash$",    "ketoconazole wash"),
    (r"^deep-condition mask$",          "deep-condition your hair"),
    (r"^monthly hair review$",          "monthly hair check-in"),
    (r"^bloodwork check \(quarterly\)$", "get bloodwork done"),

    # ───────────── BONE / MEWING / FACE ──────────────────────────────
    (r"^mastic gum session$",           "chew mastic gum"),
    (r"^facial fascia / lymph — am$",   "AM face massage"),
    (r"^facial fascia / lymph — pm$",   "PM face massage"),
    (r"^facial fascia / lymph$",        "face massage"),
    (r"^mewing — morning set$",         "mew — 60s hold"),
    (r"^mewing — midday reset$",        "mewing reset"),
    (r"^mewing — night set$",           "mew before bed"),
    (r"^chin tucks bundle$",            "do 10 chin tucks"),
    (r"^neck training — full session$", "train your neck"),
    (r"^neck training — solo day$",     "train your neck"),
    (r"^vitamin d3 \+ k2 with food$",   "take D3 + K2 with food"),
    (r"^magnesium glycinate pm$",       "take magnesium before bed"),
    (r"^mastic gum — ramp set$",        "chew mastic gum"),
    (r"^mewing \(am set, (\d+)s\)$",    r"mew — \1s hold"),
    (r"^mewing reset \(midday, (\d+)s\)$", r"mewing reset — \1s"),
    (r"^mewing \(night set\)$",         "mew before bed"),
    (r"^chew mastic gum \((\d+) min\)$", r"chew mastic gum — \1 min"),
    (r"^chew mastic gum \(ramp\)$",     "chew mastic gum"),
    (r"^facial massage \(am\)$",        "AM face massage"),
    (r"^facial fascia release \(pm\)$", "PM face massage"),
    (r"^nasal-breathing check$",        "check your nasal breathing"),
    (r"^neck training \(full set\)$",   "train your neck"),
    (r"^neck training \(solo day\)$",   "train your neck"),
    (r"^chin tucks ×(\d+)$",            r"do \1 chin tucks"),
    (r"^symmetry / posture check$",     "check your posture"),
    (r"^take d3 \+ k2 \(with food\)$",  "take D3 + K2 with food"),
    (r"^take magnesium \(pm\)$",        "take magnesium before bed"),
    (r"^photo: jaw \+ side profile$",   "take a jaw photo"),
    (r"^monthly jaw review$",           "monthly jaw check-in"),
    (r"^hard mewing \(60s suction hold\)$", "hard mew — 60s suction hold"),
    (r"^lip tape \(bedtime\)$",         "tape your lips (paper tape)"),
    (r"^alternate chewing sides$",      "alternate chewing sides"),

    # ────────────────────────── HEIGHT ────────────────────────────────
    (r"^am mobility \(5 min\)$",        "AM mobility — 5 min"),
    (r"^desk reset \(5 min\)$",         "stand up + reset posture"),
    (r"^pm decompression \(5 min\)$",   "decompress your spine — 5 min"),
    (r"^dead hang \(60s\)$",            "dead hang — 60s"),
    (r"^wall posture drill$",           "wall posture drill"),
    (r"^face pulls 3×12$",              "face pulls — 3×12"),
    (r"^glute bridge 3×15$",            "glute bridges — 3×15"),
    (r"^check sleep window$",           "start winding down"),
    (r"^hit protein \(~1g/lb\)$",       "hit your protein (~1g/lb)"),
    (r"^10 min am sunlight$",           "get 10 min of morning sun"),
    (r"^outfit proportions check$",     "check your outfit proportions"),
    (r"^rotate shoes \(weekly\)$",      "rotate your shoes"),
    (r"^mirror posture check$",         "mirror posture check"),
    (r"^chin tucks ×15$",               "do 15 chin tucks"),
    (r"^foam-roll upper back$",         "foam-roll upper back"),
    (r"^log am height$",                "log your morning height"),
    (r"^photo: full-body posture$",     "take a posture photo"),
    (r"^monthly height review$",        "monthly height check-in"),
    (r"^inversion table \(5 min\)$",    "inversion — 5 min"),
    (r"^calcium-rich meal$",            "eat a calcium-rich meal"),

    # ─────────────────────────── FIT ──────────────────────────────────
    (r"^training session$",             "hit your lift"),
    (r"^post-workout protein$",         "post-workout protein (40g)"),
    (r"^pre-workout fuel \+ hydration$", "pre-workout fuel + caffeine"),
    (r"^am nutrition — protein-forward breakfast$", "eat your AM protein meal"),
    (r"^pm nutrition — last meal anchor$", "eat your PM meal (protein + carb)"),
    (r"^midday training tip$",          "midday training cue"),
    (r"^liss cardio — 30 min$",         "LISS cardio — 30 min"),
    (r"^daily step target$",            "hit your step target"),
    (r"^weekly weigh-in$",              "weigh in (fasted)"),
    (r"^monthly progress photo$",       "take a progress photo"),
    (r"^deload week check-in$",         "deload week — drop volume"),
    (r"^eat am protein meal$",          "eat your AM protein meal"),
    (r"^midday training cue$",          "midday training cue"),
    (r"^eat pm meal \(protein \+ carb\)$", "eat your PM meal (protein + carb)"),
    (r"^pre-workout fuel$",             "pre-workout fuel + caffeine"),
    (r"^lift session$",                 "hit your lift"),
    (r"^hit step target$",              "hit your step target"),
    (r"^liss cardio \(30 min\)$",       "LISS cardio — 30 min"),
    (r"^take progress photo$",          "take a progress photo"),
    (r"^deload week — drop volume$",    "deload week — half the volume"),
    (r"^hydration check$",              "drink water"),
    (r"^mobility warm-up \(10 min\)$",  "mobility warm-up — 10 min"),
    (r"^wind down — bed in 60 min$",    "start winding down — bed in 60"),
    (r"^lunch protein hit$",            "lunch — hit 30–40g protein"),
    (r"^pm stretch \(8 min\)$",         "PM stretch — 8 min"),
    (r"^weekly progress review$",       "weekly progress check-in"),
    (r"^monthly check-in$",             "monthly progress check-in"),
    (r"^form-check video$",             "film a form-check video"),
    (r"^take creatine \(5g\)$",         "take creatine — 5g"),
    # Workout split labels — turn "Upper A — push focus" into something
    # the user actually reads as "the workout I'm doing today".
    (r"^full body a$",                  "hit full body A"),
    (r"^full body b$",                  "hit full body B"),
    (r"^full body c$",                  "hit full body C"),
    (r"^upper a — push focus$",         "hit upper body (push)"),
    (r"^lower a — squat focus$",        "hit lower body (squat)"),
    (r"^upper b — pull focus$",         "hit upper body (pull)"),
    (r"^lower b — deadlift focus$",     "hit lower body (deadlift)"),
    (r"^push day a$",                   "hit push day"),
    (r"^pull day a$",                   "hit pull day"),
    (r"^legs day a$",                   "hit legs"),
    (r"^push day b$",                   "hit push day (B)"),
    (r"^pull day b$",                   "hit pull day (B)"),
    (r"^legs day b$",                   "hit legs (B)"),
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
            return _strip_em_dashes(_normalize_title_case(new))
    return _strip_em_dashes(base)


@dataclass
class ValidationError:
    severity: str  # "hard" | "soft"
    code: str
    message: str
    day_index: int | None = None
    task_id: str | None = None


def _guard_day_distribution(
    days: list[dict],
    errors: list["ValidationError"],
    *,
    expected_day_count: int | None = None,
) -> list[dict]:
    """Day-distribution safety net — guarantees the multi-day SHAPE survives.

    The single worst schedule failure is "every task pushed into one day".
    Dates are stamped downstream by array position (``enumerate``), so the
    invariant that protects against collapse is simply: *the day list keeps
    one distinct, sequentially-indexed entry per planned day*. This pass
    enforces that, and ONLY that:

      • Re-stamps ``day_index`` to its array position (0..n-1) whenever the
        incoming indices are missing, non-int, or contain duplicates — the
        exact structural signature of a collapse. Idempotent: when indices
        are already ``0,1,2,…`` it changes nothing.

    It deliberately does **not** move tasks between days. On the skeleton
    path each day's task set is cadence-meaningful (daily vs. periodic
    tasks), so shuffling tasks to "balance counts" would corrupt the plan.
    The skeleton builder already emits one distinct-index entry per cadence
    day, so this is a strict no-op there — it exists purely as a tripwire +
    repair for any future/legacy producer that regresses the shape.

    Returns the (possibly re-indexed) list; never raises.
    """
    if not isinstance(days, list) or not days:
        return days

    raw_indices = [d.get("day_index") if isinstance(d, dict) else None for d in days]
    indices_healthy = all(
        isinstance(ix, int) and ix == pos for pos, ix in enumerate(raw_indices)
    )
    if not indices_healthy:
        # Duplicate / missing / out-of-order indices are the structural
        # fingerprint of a day-collapse. Re-stamp positionally so each
        # planned day keeps its own date downstream.
        dup = len(raw_indices) != len({str(ix) for ix in raw_indices})
        for pos, d in enumerate(days):
            if isinstance(d, dict):
                d["day_index"] = pos
        errors.append(ValidationError(
            "soft", "day_index_repaired",
            "re-stamped day_index positionally (collapse guard): "
            f"{'duplicate' if dup else 'missing/unordered'} indices",
        ))

    if expected_day_count and len(days) == 1 and expected_day_count > 1:
        # A multi-day plan that arrived as a single day entry is the literal
        # "all tasks in one day" failure. Surface it loudly for observability;
        # we can't safely re-split (task→day mapping is lost), but the caller
        # / monitors will see it and the skeleton path will have prevented it.
        errors.append(ValidationError(
            "soft", "day_bunching_detected",
            f"expected {expected_day_count} days but received a single day entry",
        ))

    return days


def validate_and_fix(
    *,
    maxx_id: str,
    days: list[dict],
    wake_time: str,
    sleep_time: str,
    user_ctx: dict[str, Any],
    expected_day_count: int | None = None,
    daily_task_budget: tuple[int, int] | None = None,
    start_date: "_date | None" = None,
) -> tuple[bool, list[ValidationError], list[dict]]:
    """Validate + fix-where-safe. Returns (clean, errors, fixed_days).

    `clean` is False ONLY when there are HARD errors. Soft fixes don't
    flip clean to False — they're applied silently.
    """
    errors: list[ValidationError] = []
    if not isinstance(days, list):
        errors.append(ValidationError("hard", "structure", "days must be a list"))
        return False, errors, []

    # Day-distribution safety net (strict no-op on healthy skeleton output):
    # guarantee distinct, sequential day_index so the plan can never collapse
    # onto a single date downstream. Runs first so the per-day loop and all
    # later passes operate on the corrected shape.
    days = _guard_day_distribution(days, errors, expected_day_count=expected_day_count)

    wake = parse_clock(wake_time, "07:00")
    sleep = parse_clock(sleep_time, "23:00")
    sleep_min = _sleep_minutes_normalized(wake, sleep)
    # Overnight (wake>sleep) schedules order tasks by minutes-since-wake so
    # post-midnight "before bed" tasks sort to the END of the day instead of
    # stacking at 23:59. Day-schedule users: overnight=False → plain clock.
    overnight = crosses_midnight(wake, sleep)
    wake_min = to_minutes(wake)

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

        clean_tasks = _enforce_separation(
            clean_tasks, day_index=di, errors=errors,
            wake_min=wake_min, overnight=overnight,
        )

        # Daily task budget — with a week-1 on-ramp. Foundation steps are the
        # floor; the OPTIONAL headroom layers in over the first two weeks for
        # chill/beginner users, so week 1 stays gentle instead of dumping the
        # full protocol on day 1. Sweatmode/advanced users see no ramp.
        if daily_task_budget:
            mn, mx = daily_task_budget
            if len(clean_tasks) < mn:
                errors.append(ValidationError(
                    "soft", "below_min_tasks",
                    f"day {di+1}: {len(clean_tasks)} tasks < min {mn}",
                    day_index=di,
                ))
            ess_count = sum(
                1 for t in clean_tasks
                if set(t.get("tags") or []) & _ESSENTIAL_TAGS
            )
            eff_max = _ramped_daily_max(mx, di, ess_count, user_ctx)
            if len(clean_tasks) > eff_max:
                # Drop lowest-intensity (cosmetic) tasks beyond the day's cap.
                clean_tasks = _truncate_by_intensity(clean_tasks, maxx_id, eff_max)
                errors.append(ValidationError(
                    "soft", "above_max_tasks",
                    f"day {di+1}: trimmed to budget max {eff_max}",
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

    # Final coherence pass — enforces hard ordering rules between specific
    # task pairs across the day. Runs AFTER routine-priority sorting so it
    # only fires when a task's time was edited (e.g. user moved their
    # workout) and another task that depends on it ends up in the wrong
    # spot. Idempotent — running twice is the same as running once.
    fixed_days = _enforce_coherence(
        fixed_days, errors=errors, wake_min=wake_min, overnight=overnight,
    )

    # Per-weekday windows + busy-time avoidance — the LAST pass so it
    # operates on final times. For each day it (a) resolves that weekday's
    # effective wake/sleep + obligations (weekly_timings override → global
    # default), (b) pushes any task landing before that day's wake or inside
    # a fixed obligation forward to clear it, and (c) keeps tasks inside that
    # day's waking window. Deliberately runs AFTER coherence (re-running
    # coherence here could pull a pre-workout back into a busy block). Strict
    # no-op when the user has set no per-weekday overrides and no busy windows.
    if (_has_weekly_overrides(user_ctx) or _busy_intervals_from_ctx(user_ctx)
            or bool(user_ctx.get("calendar_busy_by_date"))):
        fixed_days = _apply_day_windows(
            fixed_days, user_ctx,
            start_date=start_date or _date.today(),
            global_wake=wake_time, global_sleep=sleep_time,
            errors=errors,
        )

    # Authoritative final ordering. A day's task array is what the mobile app
    # renders top-to-bottom, so the LAST word on order belongs here — after
    # every placement pass (separation, coherence, day-windows), each of which
    # works in clock-minute space internally. For an overnight (wake>sleep)
    # user, re-stamp the array by minutes-since-wake so a 03:30am wind-down
    # task sits at the END of the lived day instead of floating to the top
    # (raw clock order would rank 03:30 above the 14:00 wake routine). Gated on
    # `overnight`, so it's a literal no-op — untouched arrays — for the common
    # day-schedule case. Times themselves are never changed, only their order.
    if overnight:
        for d in fixed_days:
            tlist = d.get("tasks") or []
            if isinstance(tlist, list):
                tlist.sort(key=lambda t: order_minutes(_parse_time_field(t.get("time")) or 0, wake_min))
                d["tasks"] = tlist

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
    description = _strip_em_dashes(description)
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


def _enforce_separation(
    tasks: list[dict],
    *,
    day_index: int,
    errors: list[ValidationError],
    wake_min: int = 0,
    overnight: bool = False,
) -> list[dict]:
    """Sort tasks by (slot bucket, routine priority, original time); push
    later tasks forward to enforce min gap.

    Routine priority means: within the same ~30-min window, cleanse fires
    before serum before moisturizer before SPF before minoxidil before
    supplements — regardless of which block emitted them. Without this,
    cross-block emission order followed declaration order in the .md doc,
    so a hairmax minox AM block declared above a skinmax SPF block could
    fire MINOX FIRST then SPF, causing minox migration to face skin.

    All internal math runs in a "working minute" space. For an overnight
    (wake>sleep) user that space is minutes-SINCE-WAKE, so a 03:30am bedtime
    task sorts AFTER a 14:00 wake task and forward-spacing never wraps back
    onto the morning. For a day-schedule user the transform is the identity
    (working minute == clock minute), so behaviour is byte-identical.
    """
    if not tasks:
        return tasks

    def _to_work(clock: int) -> int:
        return order_minutes(clock, wake_min) if overnight else clock

    def _to_clock_str(work: int) -> str:
        return from_minutes((wake_min + work) if overnight else work).strftime("%H:%M")

    # Bucket size: tasks landing within 45 min of each other are treated
    # as the "same routine block" and re-ordered by priority. Beyond
    # that, the original time wins (lunch should not get pulled into the
    # morning routine because it has the lowest score).
    BUCKET_MIN = 45

    timed = [(t, _to_work(_parse_time_field(t["time"]) or 0)) for t in tasks]
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

    # Stamp times sequentially with MIN_TASK_GAP_MIN spacing. `start` is in
    # working-minute space; render it back to a wall-clock string (wrapping
    # across midnight for overnight users).
    last_end = -1
    out = []
    for t, anchor in reordered:
        start = max(anchor, last_end + MIN_TASK_GAP_MIN if last_end >= 0 else anchor)
        original_start = _to_work(_parse_time_field(t["time"]) or 0)
        if start != original_start:
            new_time = _to_clock_str(start)
            errors.append(ValidationError(
                "soft", "time_collision",
                f"day {day_index+1}: re-stamped {t['title']!r} to {new_time}",
                day_index=day_index, task_id=t.get("catalog_id"),
            ))
            t = {**t, "time": new_time}
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


def _intensity_week1_optional_frac(user_ctx: dict[str, Any]) -> float:
    """How much of the OPTIONAL daily load a user carries in week 1 (days 0-6).

    1.0 = no on-ramp (week 1 already at full load); 0.0 = foundation-only week
    1 (every optional active deferred to week 2). The foundation tasks (cleanse
    / moisturize / SPF / the lift itself) are NEVER ramped away — only the
    optional actives layer in over time, which is how a real coach onboards a
    beginner. Explicit `intensity_preference` wins; absent that we infer from
    how experienced the user says they are.
    """
    pref = str(user_ctx.get("intensity_preference") or "").strip().lower()
    if pref == "sweatmode":
        return 1.0
    if pref == "chill":
        return 0.0
    if pref == "standard":
        return 0.5
    # No explicit preference: infer a sensible ramp from stated experience.
    lvl = str(
        user_ctx.get("routine_level") or user_ctx.get("experience_level") or ""
    ).strip().lower()
    if lvl == "advanced":
        return 1.0
    if lvl in ("beginner", "none", "basic"):
        return 0.0
    return 0.5


def _ramped_daily_max(
    base_max: int, day_index: int, ess_count: int, user_ctx: dict[str, Any]
) -> int:
    """Per-day task ceiling with a gentle week-1 on-ramp.

    The foundation steps are always kept (`ess_count` is the hard floor); only
    the OPTIONAL headroom (`base_max - ess_count`) ramps in. In week 1 a chill /
    beginner user carries just a fraction of that headroom — often zero, i.e. a
    foundation-only first week — growing to the full budget from week 2 on.
    Sweatmode / advanced users get no ramp (full load from day 0). The result is
    never below `ess_count` (foundation is sacred) nor above `base_max`.
    """
    if day_index >= 7:
        return base_max
    frac = _intensity_week1_optional_frac(user_ctx)
    if frac >= 1.0:
        return base_max
    room = max(0, base_max - ess_count)
    return min(base_max, ess_count + int(round(frac * room)))


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


# --- Coherence rules: hard ordering between specific task pairs --------- #
# Each rule: dependent task X must come AT LEAST `gap_min` minutes AFTER
# the END of any prerequisite task in the same day. If X is currently
# earlier (e.g. user dragged their workout later in the day, leaving
# post-workout protein stranded in the morning), slide X forward.
#
# Format: (dependent_id, [prerequisite_ids], gap_min, max_gap_min_or_None)
#   gap_min      = minimum minutes between prerequisite end and dependent start
#   max_gap_min  = if not None and dependent runs LATER than this past the
#                  prerequisite end, slide it CLOSER (used for pre/post-workout
#                  windows where being too far away breaks the protocol)
#
# Order matters: rules earlier in the list resolve first; later rules see the
# moved tasks. Cross-module rules included so blending stays coherent
# (skin SPF must finish before hair minox in the same window, etc.).
_COHERENCE_RULES: list[tuple[str, list[str], int, int | None]] = [
    # AM SKINCARE: cleanse → moisturize → SPF (immediately after, no real gap)
    ("skin.moisturize_am",  ["skin.cleanse_am"],                              0, None),
    ("skin.spf",            ["skin.moisturize_am", "skin.cleanse_am"],        0, None),
    ("skin.azelaic_am",     ["skin.cleanse_am"],                              0, None),
    ("skin.centella_am",    ["skin.cleanse_am"],                              0, None),
    ("skin.zinc_supp",      ["skin.cleanse_am"],                              0, None),
    # PM SKINCARE: cleanse → wait 15 min for dry skin → retinoid → moisturize
    ("skin.retinoid_pm",      ["skin.cleanse_pm"],                            15, None),
    ("skin.dermastamp_pm",    ["skin.cleanse_pm"],                            15, None),
    ("skin.rest_night_serum", ["skin.cleanse_pm"],                             5, None),
    ("skin.weekly_exfoliation", ["skin.cleanse_pm"],                           5, None),
    ("skin.hydration_mask",   ["skin.cleanse_pm"],                             5, None),
    ("skin.moisturize_pm",  [
        "skin.retinoid_pm", "skin.dermastamp_pm", "skin.rest_night_serum",
        "skin.weekly_exfoliation", "skin.hydration_mask", "skin.cleanse_pm",
    ], 0, None),
    # HAIR ON FACE-AREA: minoxidil only after the face is fully sealed
    # (otherwise the alcohol vehicle migrates onto skincare-coated skin
    # → unwanted facial hair, irritation).
    ("hair.minoxidil_am",   ["skin.spf"],                                      5, None),
    ("hair.microneedle_pm", ["skin.cleanse_pm"],                              30, None),
    # WORKOUT WINDOW: pre-workout fuel 30-45 min BEFORE lift, post-workout
    # protein within ~75 min AFTER lift starts. The reverse-direction rule
    # (preworkout BEFORE workout) is handled below by treating preworkout as
    # the dependent — we move it CLOSER if it's too far before workout.
    ("fit.postworkout",     ["fit.workout_session"],                           1, None),
    ("fit.postworkout",     [
        "fit.workout_fullbody_a", "fit.workout_fullbody_b", "fit.workout_fullbody_c",
        "fit.workout_upper_a", "fit.workout_lower_a", "fit.workout_upper_b", "fit.workout_lower_b",
        "fit.workout_push", "fit.workout_pull", "fit.workout_legs",
        "fit.workout_push_b", "fit.workout_pull_b", "fit.workout_legs_b",
    ], 1, None),
    # MEWING NIGHT must be the LAST routine task — it's a bedtime cue.
    # If the user moves something else later, mewing night still anchors
    # ~30 min before bed; we don't move it via this rule (slot already
    # handles), but we DO move bone.magnesium_pm and bone.lip_tape after
    # mewing night so they're the literal last steps before sleep.
    ("bone.magnesium_pm",   ["bone.mewing_night"],                            0, None),
    ("bone.lip_tape",       ["bone.mewing_night"],                            5, None),
    # FACIAL FASCIA / RELEASE — if face is being treated, do fascia AFTER
    # so we don't spread product around with hands during massage.
    ("bone.fascia_am",      ["skin.spf"],                                      5, None),
    ("bone.fascia_pm",      ["skin.moisturize_pm"],                            5, None),
]

# Pre-workout MUST land 30-45 min BEFORE the workout. Implemented separately
# because it's a "dependent must precede" rule not a "must follow".
_PRE_WORKOUT_TARGET_GAP_MIN = 30  # ideal lead time
_PRE_WORKOUT_MAX_LEAD_MIN = 90    # if more than this far ahead, slide CLOSER


def _enforce_coherence(
    days: list[dict],
    *,
    errors: list[ValidationError],
    wake_min: int = 0,
    overnight: bool = False,
) -> list[dict]:
    """Slide tasks to satisfy hard ordering rules between specific pairs.

    Iterates each day, walks _COHERENCE_RULES, and pushes the dependent
    task forward (or pre-workout backward) when a prerequisite is later
    than expected. Caps the iteration at 5 passes per day to avoid loops
    when rules conflict (would only happen on misconfigured rule sets).

    The final per-day re-sort honors the user's *lived* day: for an
    overnight (wake>sleep) user it orders by minutes-since-wake, so a
    03:30am wind-down task lands at the END of the day's task array (where
    the user actually does it) instead of jumping to the top because 03:30
    is numerically small. Day-schedule users sort by plain clock (no-op).
    """
    def _sort_key(t: dict) -> int:
        clock = _parse_time_field(t.get("time")) or 0
        return order_minutes(clock, wake_min) if overnight else clock
    for di, day in enumerate(days):
        tasks: list[dict] = day.get("tasks") or []
        if len(tasks) < 2:
            continue

        # Index by catalog_id for O(1) lookup. There can be duplicates if
        # two modules emit the same id; we operate on the first.
        def _index() -> dict[str, dict]:
            return {t.get("catalog_id"): t for t in tasks if t.get("catalog_id")}

        for _ in range(5):
            changed = False
            idx = _index()

            # Forward rules: dependent must come AFTER prerequisite end + gap.
            for dep_id, prereq_ids, gap_min, _max in _COHERENCE_RULES:
                dep = idx.get(dep_id)
                if not dep:
                    continue
                dep_start = _parse_time_field(dep.get("time")) or 0
                # Latest prerequisite end on this day.
                latest_prereq_end = -1
                for pid in prereq_ids:
                    pre = idx.get(pid)
                    if not pre:
                        continue
                    pre_start = _parse_time_field(pre.get("time")) or 0
                    pre_end = pre_start + max(1, int(pre.get("duration_min", 1)))
                    if pre_end > latest_prereq_end:
                        latest_prereq_end = pre_end
                if latest_prereq_end < 0:
                    continue
                required_start = latest_prereq_end + gap_min
                if dep_start < required_start:
                    new_time = from_minutes(required_start).strftime("%H:%M")
                    errors.append(ValidationError(
                        "soft", "coherence_slide",
                        f"day {di+1}: slid {dep.get('title','?')!r} to {new_time} "
                        f"(must come after {prereq_ids[0]})",
                        day_index=di, task_id=dep_id,
                    ))
                    dep["time"] = new_time
                    changed = True

            # Pre-workout rule: stay within [target, max_lead] before workout.
            workout_ids = {
                "fit.workout_session", "fit.workout_fullbody_a", "fit.workout_fullbody_b",
                "fit.workout_fullbody_c", "fit.workout_upper_a", "fit.workout_lower_a",
                "fit.workout_upper_b", "fit.workout_lower_b", "fit.workout_push",
                "fit.workout_pull", "fit.workout_legs", "fit.workout_push_b",
                "fit.workout_pull_b", "fit.workout_legs_b",
            }
            pre = idx.get("fit.preworkout")
            workout = next((idx[w] for w in workout_ids if w in idx), None)
            if pre and workout:
                workout_start = _parse_time_field(workout.get("time")) or 0
                pre_start = _parse_time_field(pre.get("time")) or 0
                lead = workout_start - pre_start
                if lead < 0 or lead > _PRE_WORKOUT_MAX_LEAD_MIN:
                    new_pre = max(0, workout_start - _PRE_WORKOUT_TARGET_GAP_MIN)
                    new_time = from_minutes(new_pre).strftime("%H:%M")
                    errors.append(ValidationError(
                        "soft", "coherence_slide",
                        f"day {di+1}: slid 'pre-workout' to {new_time} "
                        f"(should be {_PRE_WORKOUT_TARGET_GAP_MIN} min before workout)",
                        day_index=di, task_id="fit.preworkout",
                    ))
                    pre["time"] = new_time
                    changed = True

            if not changed:
                break

        # Re-sort tasks by time after the slides so the day stays
        # chronological (mobile renders in array order). Overnight users
        # sort by minutes-since-wake so post-midnight tasks stay at the end.
        tasks.sort(key=_sort_key)
        day["tasks"] = tasks

    return days


def _busy_intervals_from_ctx(user_ctx: dict[str, Any]) -> list[tuple[int, int]]:
    """Collect the user's fixed daily busy windows as (start_min, end_min).

    Two sources, both optional:
      1. Work/school hours — whenever work_start/work_end parse and end >
         start, REGARDLESS of the work_schedule label. A user who told us
         concrete hours (06:00-12:00) has those hours blocked whether they
         called the job "fixed" or "flexible"; placing a routine task mid-shift
         is forcing looksmaxxing into time the user already gave away. The
         null-gate keeps this safe: real flexible/no-work users carry null
         work_start/end (the planner migrates a fixed block into an obligation
         and nulls these), so nothing is blocked for them. (Pre-Slice-1 this
         only fired for work_schedule == "fixed", so flexible shift workers
         got no protection at all.)
      2. obligations — a list of {label, start "HH:MM", end "HH:MM"} dicts
         the user added in the Day Planner. Each valid entry becomes a busy
         window.

    Overlapping/adjacent windows are merged so downstream eviction treats a
    back-to-back work block + meeting as one continuous busy span. Returns
    [] when the user has set nothing — the caller then skips the avoidance
    pass entirely (zero behaviour change for users with no fixed schedule).
    """
    if not isinstance(user_ctx, dict):
        return []

    raw: list[tuple[int, int]] = []

    ws = _parse_time_field(user_ctx.get("work_start"))
    we = _parse_time_field(user_ctx.get("work_end"))
    if ws is not None and we is not None and we > ws:
        raw.append((ws, we))

    obligations = user_ctx.get("obligations")
    if isinstance(obligations, list):
        for ob in obligations:
            if not isinstance(ob, dict):
                continue
            s = _parse_time_field(ob.get("start"))
            e = _parse_time_field(ob.get("end"))
            # Skip malformed / zero-length / overnight (end <= start) entries;
            # v1 only models same-day daytime blocks.
            if s is None or e is None or e <= s:
                continue
            raw.append((s, e))

    # Meals the user eats are busy windows too — don't schedule a routine task
    # while they're eating. Breakfast (30m) and dinner (60m) are protected; lunch
    # is left open since the user may deliberately train on a lunch break.
    skipped = {str(x).strip().lower() for x in (user_ctx.get("meals_skipped") or [])}
    for meal, dur in (("breakfast_time", 30), ("dinner_time", 60)):
        if meal.split("_")[0] in skipped:
            continue
        ms = _parse_time_field(user_ctx.get(meal))
        if ms is not None:
            raw.append((ms, ms + dur))

    if not raw:
        return []

    raw.sort()
    merged: list[list[int]] = [list(raw[0])]
    for s, e in raw[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _calendar_busy_for_date(user_ctx: dict[str, Any], iso_date: str) -> list[tuple[int, int]]:
    """This DATE's real calendar events as (start_min, end_min).

    Distinct from `_busy_intervals_from_ctx`, which returns the user's WEEKLY
    recurring commitments. Calendar events are one-off, so they are keyed by
    absolute date and must never ride in the per-weekday cache.
    """
    if not isinstance(user_ctx, dict) or not iso_date:
        return []
    by_date = user_ctx.get("calendar_busy_by_date")
    if not isinstance(by_date, dict):
        return []
    spans = by_date.get(iso_date)
    if not isinstance(spans, list):
        return []
    out: list[tuple[int, int]] = []
    for sp in spans:
        if not isinstance(sp, dict):
            continue
        st = _parse_time_field(sp.get("start"))
        en = _parse_time_field(sp.get("end"))
        if st is None or en is None or en <= st:
            continue
        out.append((st, en))
    return out


_WEEKDAY_NAMES = (
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
)
_WEEKDAY_SET = frozenset(_WEEKDAY_NAMES)
_WEEKDAYS_MF = frozenset(_WEEKDAY_NAMES[:5])
_WEEKENDS_SS = frozenset(_WEEKDAY_NAMES[5:])


def _obligation_applies(ob: Any, weekday_name: str) -> bool:
    """True if obligation `ob` recurs on `weekday_name`.

    Each obligation may carry a `days` recurrence so it doesn't have to happen
    every single day. Accepted forms:
      - absent / None / "all" / "everyday" / "daily"  → every day,
      - "weekdays" (Mon-Fri),  "weekends" (Sat/Sun),
      - a single lowercase weekday name ("wednesday"),
      - a list mixing weekday names and the "weekdays"/"weekends" tokens
        (e.g. ["monday","wednesday"] or ["weekdays","saturday"]).
    Unknown / malformed values fall back to applying EVERY day — a commitment
    is never silently dropped from the schedule.
    """
    if not isinstance(ob, dict):
        return False
    days = ob.get("days")
    if days in (None, "", "all", "everyday", "daily"):
        return True
    if isinstance(days, str):
        d = days.strip().lower()
        if d in ("weekday", "weekdays"):
            return weekday_name in _WEEKDAYS_MF
        if d in ("weekend", "weekends"):
            return weekday_name in _WEEKENDS_SS
        if d in _WEEKDAY_SET:
            return weekday_name == d
        return True  # unknown string token → safe default: every day
    if isinstance(days, (list, tuple)):
        names = {str(x).strip().lower() for x in days}
        if not names:
            return True
        if ("weekdays" in names or "weekday" in names) and weekday_name in _WEEKDAYS_MF:
            return True
        if ("weekends" in names or "weekend" in names) and weekday_name in _WEEKENDS_SS:
            return True
        return weekday_name in names
    return True


def _obligations_for_weekday(obligations: Any, weekday_name: str) -> list:
    """Filter a recurring-obligations list to those that occur on `weekday_name`."""
    if not isinstance(obligations, list):
        return []
    return [ob for ob in obligations if _obligation_applies(ob, weekday_name)]


def _has_weekly_overrides(user_ctx: dict[str, Any]) -> bool:
    """True if the user has set any per-weekday override at all."""
    if not isinstance(user_ctx, dict):
        return False
    wt = user_ctx.get("weekly_timings")
    if not isinstance(wt, dict):
        return False
    return any(isinstance(v, dict) and v for v in wt.values())


def _effective_day_ctx(
    user_ctx: dict[str, Any], weekday_name: str, *, global_wake: str, global_sleep: str,
) -> dict[str, Any]:
    """Resolve one weekday's effective rhythm: weekday override → global default.

    Returns a dict shaped like user_ctx (wake_time/sleep_time/work_* /
    obligations) so it can be fed straight into _busy_intervals_from_ctx.
    A weekday entry overrides only the fields it sets; everything else falls
    through to the top-level onboarding value.
    """
    ov: dict[str, Any] = {}
    wt = user_ctx.get("weekly_timings") if isinstance(user_ctx, dict) else None
    if isinstance(wt, dict):
        cand = wt.get(weekday_name)
        if isinstance(cand, dict):
            ov = cand

    def _pick(key: str, default: Any) -> Any:
        v = ov.get(key)
        return v if v not in (None, "") else default

    # Resolve each rhythm axis (wake / sleep) honoring override precedence:
    #   1. this weekday set a RANGE  → use it (+ its own midpoint scalar),
    #   2. this weekday set only the EXACT scalar → use it, drop any inherited
    #      range (so an exact weekend override isn't widened by the global one),
    #   3. neither → inherit the global window + global scalar.
    # `schedulable_anchors` then collapses the axis to the guaranteed-awake
    # anchor (latest-wake / earliest-sleep), matching generation exactly.
    def _axis(window_key: str, scalar_key: str, g_scalar: str) -> tuple[Any, Any]:
        if isinstance(ov.get(window_key), (list, tuple)):
            return ov[window_key], (ov.get(scalar_key) or g_scalar)
        if ov.get(scalar_key) not in (None, ""):
            return None, ov[scalar_key]
        return user_ctx.get(window_key), (user_ctx.get(scalar_key) or g_scalar)

    wake_win, wake_scalar = _axis("wake_window", "wake_time", global_wake)
    sleep_win, sleep_scalar = _axis("sleep_window", "sleep_time", global_sleep)
    eff_wake, eff_sleep = schedulable_anchors(
        {
            "wake_window": wake_win,
            "sleep_window": sleep_win,
            "wake_time": wake_scalar,
            "sleep_time": sleep_scalar,
        },
        default_wake=global_wake,
        default_sleep=global_sleep,
    )

    eff: dict[str, Any] = {
        "wake_time": eff_wake,
        "sleep_time": eff_sleep,
        "work_schedule": _pick("work_schedule", user_ctx.get("work_schedule")),
        "work_start": _pick("work_start", user_ctx.get("work_start")),
        "work_end": _pick("work_end", user_ctx.get("work_end")),
    }
    # Obligations resolution:
    #   1. a weekday entry that *includes* the key fully REPLACES the global list
    #      for that day (legacy per-day override; lets a day clear with []),
    #   2. otherwise inherit the global recurring obligations, FILTERED to those
    #      whose `days` recurrence includes this weekday (all/weekdays/weekends/
    #      specific days) — so a Mon/Wed class or a weekday work block only lands
    #      on the days it actually happens.
    if "obligations" in ov:
        eff["obligations"] = ov["obligations"]
    else:
        eff["obligations"] = _obligations_for_weekday(user_ctx.get("obligations"), weekday_name)
    return eff


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sort + merge overlapping/adjacent (start, end) minute intervals."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged: list[list[int]] = [list(ordered[0])]
    for s, e in ordered[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _overlapping_window(
    start: int, dur: int, windows: list[tuple[int, int]],
) -> tuple[int, int] | None:
    for bs, be in windows:
        if start < be and start + dur > bs:
            return (bs, be)
    return None


def _apply_day_windows(
    days: list[dict],
    user_ctx: dict[str, Any],
    *,
    start_date: _date,
    global_wake: str,
    global_sleep: str,
    errors: list[ValidationError],
) -> list[dict]:
    """Push tasks to respect each weekday's waking window + fixed obligations.

    day_index 0 == `start_date` (generation always starts "today"), so each
    day's weekday is `start_date.weekday() + day_index`. For each day we:
      - resolve that weekday's wake/sleep + busy windows (override → global),
      - treat [00:00, wake) as busy when the day wakes LATER than the global
        default (a weekend lie-in pushes the AM routine back),
      - evict any task overlapping a busy window to just after it ends,
      - clamp the day inside its bedtime ceiling for weekdays that override
        the global window.

    Per task this only shifts FORWARD (floor + busy), except the final sleep
    clamp, which pulls a task that would run past that weekday's bedtime back
    to just before it. Strict no-op for a day with no busy windows and no
    window override. `from_minutes` clamps to 23:59 so an over-subscribed day
    degrades to a late pile-up rather than crashing.
    """
    LAST_SLOT = 24 * 60 - 1
    global_wake_min = to_minutes(parse_clock(global_wake, "07:00"))

    # Cache per-weekday resolution so a 14-day plan resolves each weekday once.
    cache: dict[str, tuple[int, int, list[tuple[int, int]], bool]] = {}

    def _params(weekday_name: str) -> tuple[int, int, list[tuple[int, int]], bool]:
        if weekday_name in cache:
            return cache[weekday_name]
        eff = _effective_day_ctx(
            user_ctx, weekday_name, global_wake=global_wake, global_sleep=global_sleep,
        )
        wake_dt = parse_clock(eff["wake_time"], "07:00")
        day_wake_min = to_minutes(wake_dt)
        day_sleep_min = _sleep_minutes_normalized(wake_dt, parse_clock(eff["sleep_time"], "23:00"))
        busy = _busy_intervals_from_ctx(eff)
        window_override = (
            str(eff.get("wake_time")) != str(global_wake)
            or str(eff.get("sleep_time")) != str(global_sleep)
        )
        cache[weekday_name] = (day_wake_min, day_sleep_min, busy, window_override)
        return cache[weekday_name]

    for di, day in enumerate(days):
        tasks: list[dict] = day.get("tasks") or []
        if not tasks:
            continue

        day_date = start_date + _timedelta(days=di)
        weekday_name = _WEEKDAY_NAMES[day_date.weekday()]
        day_wake_min, day_sleep_min, busy, window_override = _params(weekday_name)

        # Build this day's effective busy list. When the day wakes later than
        # the global default, the pre-wake span counts as busy too.
        eff_busy = list(busy)
        if window_override and day_wake_min > global_wake_min:
            eff_busy.append((0, day_wake_min))
        # The user's REAL calendar for this specific date (meetings, class,
        # flights). Weekly obligations come from _params above; these don't
        # recur, so they're keyed by date and merged in here.
        cal_busy = _calendar_busy_for_date(user_ctx, (day.get("date") or day_date.isoformat()))
        eff_busy.extend(cal_busy)
        eff_busy = _merge_intervals(eff_busy)

        if not eff_busy and not window_override:
            continue  # nothing to enforce for this weekday

        # Day ceiling: that weekday's bedtime when it overrides the global
        # window, else just shy of midnight (legacy behaviour).
        ceil = min(day_sleep_min if window_override else LAST_SLOT, LAST_SLOT)

        tasks.sort(key=lambda t: _parse_time_field(t.get("time")) or 0)
        floor = -1
        for t in tasks:
            original = _parse_time_field(t.get("time")) or 0
            dur = max(1, int(t.get("duration_min", 1)))
            start = original

            # Settle against the floor and busy windows together.
            for _ in range(8):
                moved = False
                if floor >= 0 and start < floor:
                    start = floor
                    moved = True
                win = _overlapping_window(start, dur, eff_busy)
                if win is not None:
                    start = win[1]
                    moved = True
                if not moved:
                    break

            # Keep the task inside the day's bedtime ceiling — pull it back to
            # just before sleep rather than letting it spill past.
            if start + dur > ceil:
                start = max(day_wake_min if window_override else 0, ceil - dur)
            if start > LAST_SLOT:
                start = LAST_SLOT

            if start != original:
                new_time = from_minutes(start).strftime("%H:%M")
                errors.append(ValidationError(
                    "soft", "busy_avoidance",
                    f"day {di+1}: moved {t.get('title','?')!r} to {new_time} "
                    f"({weekday_name} window/obligation)",
                    day_index=di, task_id=t.get("catalog_id"),
                ))
                t["time"] = new_time

            floor = start + dur + MIN_TASK_GAP_MIN

        tasks.sort(key=lambda t: _parse_time_field(t.get("time")) or 0)
        day["tasks"] = tasks

    return days


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
