"""Tiny expression evaluator + window resolver for the schedule system.

The expression language is intentionally minimal — only what the
applies_when / contraindicated_when / prompt_modifiers blocks need.
NO eval, NO arbitrary code paths. Hand-written parser, ~80 lines.

Supported forms:
    always
    field
    !field          (negation, truthy)
    field == value
    field != value
    field < value   field <= value   field > value   field >= value
    field in [a, b, c]
    field not in [a, b, c]
    expr_a and expr_b   (AND chains; OR is not supported on purpose —
                         encode disjunctions as multiple list entries)

`evaluate_all(exprs, ctx)` returns True iff every expression is true.
This lets `applies_when: [a, b]` mean "a AND b".

Window resolver maps named windows (am_open, pm_active, ...) to
(start_minute, end_minute) tuples relative to the user's wake/sleep.
"""

from __future__ import annotations

import logging
import re
from datetime import time as dtime
from typing import Any

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Expression evaluator                                                       #
# --------------------------------------------------------------------------- #

_LIST_RE = re.compile(r"^\[(.*)\]$")


def evaluate(expr: str, ctx: dict[str, Any]) -> bool:
    """Evaluate one expression against ctx. Returns False on parse errors
    (with a log) — never raises during scheduling."""
    if not expr:
        return False
    e = expr.strip()
    if e.lower() == "always":
        return True

    # AND chain
    if " and " in e:
        return all(evaluate(part, ctx) for part in _split_top_level_and(e))

    # in / not in
    m = re.match(r"^(\w[\w\.]*)\s+(not\s+in|in)\s+(\[.*\])$", e)
    if m:
        field, op, list_lit = m.group(1), m.group(2).strip(), m.group(3)
        values = _parse_list(list_lit)
        actual = _normalize(ctx.get(field))
        in_list = actual in values
        return (in_list if op == "in" else not in_list)

    # comparison (==, !=, <, <=, >, >=)
    m = re.match(r"^(\w[\w\.]*)\s*(==|!=|<=|>=|<|>)\s*(.+)$", e)
    if m:
        field, op, raw_val = m.group(1), m.group(2), m.group(3).strip()
        actual = ctx.get(field)
        target = _coerce_literal(raw_val)
        try:
            if op == "==":
                return _normalize(actual) == _normalize(target)
            if op == "!=":
                return _normalize(actual) != _normalize(target)
            if op == "<":
                return float(actual) < float(target)
            if op == "<=":
                return float(actual) <= float(target)
            if op == ">":
                return float(actual) > float(target)
            if op == ">=":
                return float(actual) >= float(target)
        except (TypeError, ValueError):
            return False

    # negation
    if e.startswith("!"):
        return not _truthy(ctx.get(e[1:].strip()))

    # bare field — truthiness
    if re.match(r"^\w[\w\.]*$", e):
        return _truthy(ctx.get(e))

    logger.debug("schedule_dsl: unparseable expression: %r", expr)
    return False


def evaluate_all(exprs: list[str], ctx: dict[str, Any]) -> bool:
    if not exprs:
        return True
    return all(evaluate(x, ctx) for x in exprs)


def evaluate_any(exprs: list[str], ctx: dict[str, Any]) -> bool:
    return any(evaluate(x, ctx) for x in exprs)


def _split_top_level_and(s: str) -> list[str]:
    # Naive: respect [...] list literals
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if depth == 0 and s[i:i+5].lower() == " and ":
            parts.append("".join(cur).strip())
            cur = []
            i += 5
            continue
        cur.append(ch)
        i += 1
    if cur:
        parts.append("".join(cur).strip())
    return parts


def _parse_list(literal: str) -> list[Any]:
    m = _LIST_RE.match(literal.strip())
    if not m:
        return []
    inner = m.group(1).strip()
    if not inner:
        return []
    return [_coerce_literal(x.strip()) for x in inner.split(",")]


def _coerce_literal(s: str) -> Any:
    s = s.strip().strip("\"'")
    low = s.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "none"):
        return None
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def _normalize(v: Any) -> Any:
    if isinstance(v, str):
        return v.strip().lower()
    return v


def _truthy(v: Any) -> bool:
    if v is None or v is False:
        return False
    if isinstance(v, str) and v.strip().lower() in ("", "no", "false", "none", "null"):
        return False
    return bool(v)


# --------------------------------------------------------------------------- #
#  Window resolver                                                            #
# --------------------------------------------------------------------------- #

# Time slots anchored to a real human's day (wake 07, sleep 23 → defaults
# below). Slots are biology-aware, not vague: "morning_routine" is the
# 5-30 min after wake when a person is in the bathroom; "midday" is lunch
# protein + posture window; "pre_evening" is 4 hr before sleep so
# minoxidil dries before pillow contact.
#
# Old vague slots (am_open / am_active / midday / pm_active / pm_close /
# flexible) are kept as ALIASES that map onto the new anchors so existing
# docs render in sensible places without a mass rewrite. New blocks should
# prefer the named anchors.
_DEFAULT_WINDOWS: dict[str, tuple[str, str]] = {
    # --- New biology-anchored windows ---
    "morning_routine":   ("wake+0:05", "wake+0:30"),    # bathroom: skin AM, mewing, hair
    "post_routine":      ("wake+0:30", "wake+1:00"),    # supplements + breakfast
    "mid_morning":       ("wake+2:30", "wake+3:30"),    # one cue: posture / hydration
    "lunch":             ("wake+4:30", "wake+5:30"),    # protein + diet check
    "afternoon":         ("wake+7:00", "wake+8:30"),    # SPF reapply / posture reset
    "pre_evening":       ("sleep-4:00", "sleep-3:00"),  # evening minox (4hr dry-time)
    "workout":           ("sleep-3:30", "sleep-2:00"),  # late-afternoon strength window
    "post_workout":      ("sleep-2:00", "sleep-1:30"),  # protein hit + cooldown
    "pm_routine":        ("sleep-1:30", "sleep-0:45"),  # bathroom: skin PM, mewing
    "wind_down":         ("sleep-1:00", "sleep-0:15"),  # screens off, casein, magnesium

    # --- Legacy aliases (existing .md docs use these names) ---
    # am_open ≈ morning_routine; was 0:10-0:30, now slightly wider.
    "am_open":   ("wake+0:05", "wake+0:30"),
    # am_active ≈ post_routine (supplements + breakfast).
    "am_active": ("wake+0:30", "wake+1:30"),
    # midday ≈ lunch — split off the SPF reapply / afternoon reset
    # to its own slot via the new "afternoon" name where helpful.
    "midday":    ("wake+4:30", "wake+5:30"),
    # pm_active ≈ workout / post-workout window.
    "pm_active": ("sleep-3:30", "sleep-2:00"),
    # pm_close ≈ pm_routine (bathroom + bedtime stack).
    "pm_close":  ("sleep-1:30", "sleep-0:30"),
    # flexible — anywhere in the day, but avoid the dense morning/PM
    # windows so picker spreads it out.
    "flexible":  ("wake+1:30", "sleep-1:30"),
}


def parse_clock(s: str | None, default: str = "07:00") -> dtime:
    """Parse 'HH:MM' or 'H:MM' into datetime.time. Defaults on failure."""
    s = (s or default).strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if not m:
        m = re.match(r"^(\d{1,2})$", s)
        if m:
            return dtime(int(m.group(1)), 0)
        s = default
        m = re.match(r"^(\d{1,2}):(\d{2})$", default)
    h, mm = int(m.group(1)), int(m.group(2))
    return dtime(max(0, min(23, h)), max(0, min(59, mm)))


def to_minutes(t: dtime) -> int:
    return t.hour * 60 + t.minute


def from_minutes(m: int) -> dtime:
    m = max(0, min(24 * 60 - 1, int(m)))
    return dtime(m // 60, m % 60)


def resolve_window(
    window_name: str,
    *,
    wake: dtime,
    sleep: dtime,
    overrides: dict[str, list[str]] | None = None,
) -> tuple[int, int]:
    """Return (start_minute, end_minute) for a named window.

    Sleep can be < wake (e.g. wake 06:00, sleep 23:00) or > wake on
    the next-day clock (sleep 02:00 with wake 09:00). We normalize
    'sleep-X:YY' so that sleep is treated as "later in the same day"
    relative to wake.
    """
    overrides = overrides or {}
    spec = overrides.get(window_name) or _DEFAULT_WINDOWS.get(window_name)
    if not spec:
        # Unknown window → assume mid-waking.
        spec = ("wake+1:00", "sleep-1:00")

    start = _resolve_anchor(spec[0], wake=wake, sleep=sleep)
    end = _resolve_anchor(spec[1], wake=wake, sleep=sleep)
    if end < start:
        end = start + 30  # safety: keep window non-empty
    return start, end


def _resolve_anchor(expr: str, *, wake: dtime, sleep: dtime) -> int:
    """Parse 'wake+H:MM' or 'sleep-H:MM' into minutes-of-day."""
    e = expr.strip().lower()
    m = re.match(r"^(wake|sleep)\s*([+-])\s*(\d{1,2}):(\d{2})$", e)
    if not m:
        # Allow plain HH:MM clock literals as fallback.
        try:
            return to_minutes(parse_clock(e))
        except Exception:
            return to_minutes(wake) + 60

    base = to_minutes(wake) if m.group(1) == "wake" else _sleep_minutes(wake, sleep)
    delta_h, delta_m = int(m.group(3)), int(m.group(4))
    delta = delta_h * 60 + delta_m
    return base + delta if m.group(2) == "+" else base - delta


def _sleep_minutes(wake: dtime, sleep: dtime) -> int:
    """Sleep-time as minutes-of-day; if sleep clock < wake clock, treat
    sleep as next-day (so a later-in-day-than-wake number)."""
    s = to_minutes(sleep)
    w = to_minutes(wake)
    if s < w:
        s += 24 * 60
    return s
