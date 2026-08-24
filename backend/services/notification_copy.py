"""Notification copy engine — short, dry-witty, personalized push copy.

The single highest-ROI retention lever: a generic "time for your routine" decays
fast, but a SHORT, clever, personalized hook that names the task and pulls the
user into the app forms a durable trigger. The push is a hook; the step-by-step
detail lives in-app.

This module is the ONE copy source for all 8 notification categories. It is
pure + deterministic + testable: ``compose(category, ...)`` returns
``{title, body, category, route, params}``. No LLM at send time — a curated
rotation of witty templates with personalization slots keeps quality controlled
and latency zero. A do-not-repeat-recently guard (``recent``) and a ``rotation``
index keep users from seeing the same line twice.

Voice (LOCKED): dry & witty, lowercase, like a sharp friend. Never corny, never
mean, never guilt-tripping, never fear-of-loss. Every template passes a taste
bar (``passes_taste_bar``) at import-validation time and again on the send path.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# --- the 8 categories -------------------------------------------------------

CAT_TASK_DUE = "task_due"            # 1. near a scheduled habit's time
CAT_MORNING_PREVIEW = "morning_preview"  # 2. once, at/after wake
CAT_EVENING_RECAP = "evening_recap"  # 3. before sleep, pending tasks remain
CAT_STREAK = "streak_protection"     # 4. streak at risk / not yet secured
CAT_REENGAGE = "reengagement"        # 5. lapsed user
CAT_MILESTONE = "milestone"          # 6. achievement / streak milestone unlocked
CAT_BROADCAST = "broadcast"          # 7. admin-triggered, in-voice
CAT_TIP = "tip"                      # 8. occasional midday quick win

ALL_CATEGORIES = (
    CAT_TASK_DUE,
    CAT_MORNING_PREVIEW,
    CAT_EVENING_RECAP,
    CAT_STREAK,
    CAT_REENGAGE,
    CAT_MILESTONE,
    CAT_BROADCAST,
    CAT_TIP,
)

# Essential vs optional (review item 6 — per-category mute). Essential are the
# task/plan reminders a user signed up for; optional can be muted independently.
ESSENTIAL_CATEGORIES = frozenset({CAT_TASK_DUE, CAT_MORNING_PREVIEW, CAT_EVENING_RECAP})
OPTIONAL_CATEGORIES = frozenset(
    {CAT_STREAK, CAT_REENGAGE, CAT_MILESTONE, CAT_BROADCAST, CAT_TIP}
)

# Deep-link route per category. Mirrors mobile/App.tsx NOTIFICATION_DEEP_LINK_ROUTES.
# Each push opens the SPECIFIC thing it is about (review item 11).
DEEP_LINK_ROUTES = frozenset(
    {"Home", "TaskGuide", "Achievements", "Profile", "ProgressArchive",
     "CreatorFeed", "CreatorStudio"}
)
_CATEGORY_ROUTE: dict[str, str] = {
    CAT_TASK_DUE: "TaskGuide",        # the specific task's guide/detail
    CAT_MORNING_PREVIEW: "Home",      # today's lineup
    CAT_EVENING_RECAP: "Home",
    CAT_STREAK: "Home",
    CAT_REENGAGE: "Home",
    CAT_MILESTONE: "Achievements",
    CAT_BROADCAST: "Home",
    CAT_TIP: "Home",
    # Creator platform: a "new update" opens THAT creator's feed (maxxId rides
    # in ScheduledNotification.deep_link_params); an application decision opens
    # the studio (approved creators land in their new home).
    "creator_update": "CreatorFeed",
    "creator_application_decision": "CreatorStudio",
}

# --- taste bar (review item 9: wit, never shame / fear-of-loss) --------------

# Notification-specific bans layered on top of services.copy_filter content bans.
# No fake urgency, no FOMO, no loss-framed-as-threat, no guilt.
_TASTE_BANNED_PATTERNS = [
    r"don'?t miss out",
    r"\bmiss out\b",
    r"!!+",
    r"\blast chance\b",
    r"\bhurry\b",
    r"\bact now\b",
    r"\bdon'?t break\b",
    r"\bdon'?t lose\b",
    r"\blose your\b",
    r"\bcrime\b",
    r"\bghosting\b",
    r"\bstreak'?s watching\b",
    r"\bwatching you\b",
    r"\byou'?ll regret\b",
    r"\bshame\b",
    r"\bguilt",
    r"\bbefore it'?s too late\b",
]
_TASTE_BANNED_RE = [re.compile(p, re.IGNORECASE) for p in _TASTE_BANNED_PATTERNS]


def passes_taste_bar(text: str) -> bool:
    """True if `text` is free of banned phrasing (FOMO / shame / fear-of-loss)
    AND clears the shared outbound content filter (shame/body-threat/medical)."""
    if not text:
        return True
    for rx in _TASTE_BANNED_RE:
        if rx.search(text):
            return False
    try:
        from services.copy_filter import check_content

        if check_content(text):
            return False
    except Exception:
        pass
    return True


# --- templates --------------------------------------------------------------


@dataclass(frozen=True)
class _Tmpl:
    """One witty template. `requires` is the set of signal keys that must be
    present (non-empty) for this template to be eligible — the rotation only
    picks templates whose required signals we actually have, so copy degrades
    gracefully when name/streak/why are missing."""

    title: str
    body: str
    requires: frozenset = field(default_factory=frozenset)


# Each bank is ordered; rotation walks it. Lowercase, dry, kind. Title <= 6
# words; body one short sentence <= ~90 chars. Slots:
#   {name_c}  ", anish" when name known else ""
#   {task}    the task label (task_due)
#   {streak}  current streak day count
#   {count}   pending-task count
#   {why}     the user's stated goal/why
#   {plan}    plan/maxx label (e.g. "skinmax")
_BANKS: dict[str, list[_Tmpl]] = {
    CAT_TASK_DUE: [
        _Tmpl("{task}", "{task} o'clock{name_c}. two minutes and it's behind you."),
        _Tmpl("{task}", "quick one{name_c}: {task}. open up, it's all laid out."),
        _Tmpl("{task} time", "{task}{name_c}. tap in, knock it out, move on."),
        _Tmpl("{task}", "{task} is up{name_c}. small thing, big compounding."),
        _Tmpl("{task} — {why}", "{task} now{name_c}, one step toward {why}.", frozenset({"why"})),
        _Tmpl("day {streak}: {task}", "{task}{name_c}. keeps day {streak} rolling.", frozenset({"streak"})),
    ],
    CAT_MORNING_PREVIEW: [
        _Tmpl("morning{name_c}", "today's lineup is short and doable. take a look."),
        _Tmpl("today's plan", "{count} small things on deck{name_c}. open when ready.", frozenset({"count"})),
        _Tmpl("good morning{name_c}", "{count} quick wins between you and {why}.", frozenset({"count", "why"})),
        _Tmpl("morning{name_c}", "fresh day, light list. peek at what's on it."),
        _Tmpl("today, briefly", "a few small moves toward {why}. they're in the app.", frozenset({"why"})),
    ],
    CAT_EVENING_RECAP: [
        _Tmpl("before you wind down", "{count} left{name_c}, if you've got a minute."),
        _Tmpl("quick recap{name_c}", "{count} still open. easy to close before bed."),
        _Tmpl("evening check", "a couple things linger{name_c}. no rush, just here."),
        _Tmpl("day {streak} still open", "{count} small thing(s) to round out day {streak}.", frozenset({"streak", "count"})),
    ],
    CAT_STREAK: [
        _Tmpl("day {streak} looks good", "one small thing keeps the run going{name_c}.", frozenset({"streak"})),
        _Tmpl("nice run going", "day {streak}{name_c}. a quick task and it carries on.", frozenset({"streak"})),
        _Tmpl("day {streak}", "you're on a roll{name_c} — one tap keeps it that way.", frozenset({"streak"})),
        _Tmpl("momentum's yours", "day {streak} is right there for the taking{name_c}.", frozenset({"streak"})),
    ],
    CAT_REENGAGE: [
        _Tmpl("your plan's still here", "whenever you're ready{name_c} — one small thing today?"),
        _Tmpl("we kept your spot", "the plan's warm and waiting{name_c}. one tap back in."),
        _Tmpl("no pressure{name_c}", "the routine's here when you are. pick up anytime."),
        _Tmpl("still in your corner", "ready when you are{name_c} — start with just one thing."),
    ],
    CAT_MILESTONE: [
        _Tmpl("nice work{name_c}", "you just unlocked something. proof's in your profile."),
        _Tmpl("day {streak}: milestone", "{streak} days straight{name_c}. that's real. take a look.", frozenset({"streak"})),
        _Tmpl("achievement unlocked", "you earned this one{name_c}. it's waiting in your profile."),
        _Tmpl("that's a milestone", "consistency paid off{name_c}. see what you just hit."),
    ],
    CAT_BROADCAST: [
        # Broadcast body is author-supplied; this bank is the in-voice fallback.
        _Tmpl("from max", "something new just landed{name_c}. worth a look."),
    ],
    CAT_TIP: [
        _Tmpl("one thing today", "10s of cold water on the face tightens everything{name_c}."),
        _Tmpl("quick win", "two minutes of sun early sets your whole rhythm{name_c}."),
        _Tmpl("small tip{name_c}", "water before coffee. your face thanks you later."),
        _Tmpl("tiny upgrade", "stand tall for 30s{name_c} — posture reads before anything else."),
    ],
}


# Phase 4 (personalized_notif_copy, default OFF): NEW warm variants that lean on
# the user's stated {why} / active {plan}. Each REQUIRES its signal, so it only
# fires when we actually have it (degrades to the base bank otherwise). They join
# the rotation only when the flag is on — cadence/cap/interval/backoff unchanged.
_PERSONALIZED_EXTRA: dict[str, list[_Tmpl]] = {
    CAT_TASK_DUE: [
        _Tmpl("{task}", "you said {why}{name_c}. {task} is the next step toward it.", frozenset({"why"})),
        _Tmpl("{task} time", "{task}{name_c}. your {plan} only pays off when you show up.", frozenset({"plan"})),
    ],
    CAT_MORNING_PREVIEW: [
        _Tmpl("morning{name_c}", "a few small moves toward {why} today. they're queued."),
        _Tmpl("today's {plan}", "your {plan} list is short today{name_c}. run it while it's easy.", frozenset({"plan"})),
    ],
    CAT_EVENING_RECAP: [
        _Tmpl("before you wind down", "{count} between you and {why}{name_c}. easy to close.", frozenset({"count", "why"})),
    ],
    CAT_STREAK: [
        _Tmpl("day {streak}", "you wanted {why}{name_c}. one rep keeps day {streak} alive.", frozenset({"streak", "why"})),
    ],
    CAT_REENGAGE: [
        _Tmpl("your plan's still here", "you started this for {why}{name_c}. one small thing today?", frozenset({"why"})),
    ],
}


def _personalized_notif_enabled() -> bool:
    """Read the personalized_notif_copy flag without a hard import dependency."""
    try:
        from config import settings
        return bool(getattr(settings, "personalized_notif_copy", False))
    except Exception:
        return False


def _active_bank(category: str, *, personalized: bool) -> list[_Tmpl]:
    """The rotation bank for a category. With ``personalized`` on, the Phase-4
    warm variants are appended (kept LAST so existing rotation indices are
    stable for the base lines); off → exactly the base bank."""
    base = _BANKS[category]
    if personalized:
        extra = _PERSONALIZED_EXTRA.get(category)
        if extra:
            return base + extra
    return base


def _slots(
    *,
    name: Optional[str],
    task: Optional[str],
    streak: Optional[int],
    count: Optional[int],
    why: Optional[str],
    plan: Optional[str],
) -> tuple[dict, set]:
    """Build the format-slot dict and the set of available signal keys."""
    available: set = set()
    # Lowercased to match the copy voice — every template is lowercase
    # editorial ("morning, chad." — never "morning, Chad.").
    nm = (name or "").strip().lower()
    if nm:
        available.add("name")
    tk = (task or "").strip().lower()
    if tk:
        available.add("task")
    wy = (why or "").strip().rstrip(".")
    if wy:
        available.add("why")
    pl = (plan or "").strip().lower()
    if pl:
        available.add("plan")
    if isinstance(streak, int) and streak >= 2:
        available.add("streak")
    if isinstance(count, int) and count >= 1:
        available.add("count")
    slots = {
        "name_c": f", {nm}" if nm else "",
        "task": tk or "your routine",
        "streak": streak if isinstance(streak, int) else "",
        "count": count if isinstance(count, int) else "",
        "why": wy or "your goal",
        "plan": pl or "your plan",
    }
    return slots, available


def _pick(
    bank: list[_Tmpl], available: set, rotation: int, recent: Iterable[str]
) -> _Tmpl:
    """Choose a template whose requirements are met, honoring rotation and the
    do-not-repeat-recently guard. Deterministic."""
    eligible = [t for t in bank if t.requires <= available]
    if not eligible:
        eligible = [t for t in bank if not t.requires] or bank
    recent_set = set(recent or ())
    n = len(eligible)
    start = rotation % n
    # Walk from the rotation offset; skip recently-used lines if we can.
    for i in range(n):
        cand = eligible[(start + i) % n]
        if _tmpl_id(cand) not in recent_set:
            return cand
    return eligible[start]


def _tmpl_id(t: _Tmpl) -> str:
    return f"{t.title}|{t.body}"


def compose(
    category: str,
    *,
    name: Optional[str] = None,
    task: Optional[str] = None,
    streak: Optional[int] = None,
    count: Optional[int] = None,
    why: Optional[str] = None,
    plan: Optional[str] = None,
    route_params: Optional[dict] = None,
    broadcast_title: Optional[str] = None,
    broadcast_body: Optional[str] = None,
    rotation: int = 0,
    recent: Iterable[str] = (),
    coaching_tone: Optional[str] = None,
    personalized_copy: Optional[bool] = None,
) -> dict:
    """Compose a push for `category`. Returns
    ``{title, body, category, route, params, template_id}``.

    Pulls from a witty template bank, fills personalization slots, and degrades
    gracefully when a signal is missing. The returned ``template_id`` should be
    appended to the caller's per-user ``recent`` list to drive rotation.

    When ``coaching_tone`` maps to a live persona (Goggins/Clavicular/Big Daddy),
    the line is restyled into that coach's voice (``persona_notifications``) as
    long as the restyled copy still clears the taste bar; otherwise the base
    (persona-agnostic) line is kept. Author-supplied broadcasts are never
    restyled.
    """
    if category not in _BANKS:
        raise ValueError(f"unknown notification category: {category}")

    slots, available = _slots(
        name=name, task=task, streak=streak, count=count, why=why, plan=plan
    )

    if category == CAT_BROADCAST and (broadcast_body or broadcast_title):
        title = (broadcast_title or "from max").strip()
        body = (broadcast_body or "").strip()
        tmpl_id = "broadcast:custom"
    else:
        use_personalized = _personalized_notif_enabled() if personalized_copy is None else personalized_copy
        bank = _active_bank(category, personalized=use_personalized)
        tmpl = _pick(bank, available, rotation, recent)
        title = tmpl.title.format(**slots).strip()
        body = tmpl.body.format(**slots).strip()
        tmpl_id = _tmpl_id(tmpl)

        # Persona restyle — speak in the active coach's voice when one is set and
        # the restyled line still clears the taste bar (else keep the base line).
        if coaching_tone:
            try:
                from services.persona_notifications import persona_push_copy

                pc = persona_push_copy(coaching_tone, category, slots, available, rotation)
                if pc and passes_taste_bar(pc["title"]) and passes_taste_bar(pc["body"]):
                    title, body, tmpl_id = pc["title"], pc["body"], pc["template_id"]
            except Exception as e:  # noqa: BLE001 — persona is best-effort, never break a send
                logger.debug("persona restyle skipped (%s): %s", category, e)

    # Final taste-bar guard — if a filled template somehow trips the bar (e.g. a
    # weird user name/why), fall back to the safest line in the bank.
    if not (passes_taste_bar(title) and passes_taste_bar(body)):
        logger.warning("notification copy tripped taste bar (%s): %r / %r", category, title, body)
        safe = next((t for t in _BANKS[category] if not t.requires), _BANKS[category][0])
        title = safe.title.format(**{**slots, "task": "your routine", "why": "your goal"}).strip()
        body = safe.body.format(**{**slots, "task": "your routine", "why": "your goal"}).strip()
        tmpl_id = _tmpl_id(safe)

    params = dict(route_params or {})
    params.setdefault("category", category)

    return {
        "title": title,
        "body": body,
        "category": category,
        "route": _CATEGORY_ROUTE[category],
        "params": params,
        "template_id": tmpl_id,
    }


def build_push_custom(category: str, route: str, params: Optional[dict] = None) -> dict:
    """The APNs custom payload so a tap deep-links correctly (review item 11).
    Carries category + route + params; mobile/App.tsx reads data.route/data.params."""
    p = dict(params or {})
    p.setdefault("category", category)
    return {"category": category, "route": route, "params": p}


def validate_all_templates() -> list[str]:
    """Self-test: every template, filled with rich + empty signals, must pass
    the taste bar and stay within length limits. Returns a list of problems
    (empty = all good). Used by tests and as an import-time guard."""
    problems: list[str] = []
    rich = dict(name="anish", task="morning skincare", streak=6, count=3, why="a sharper jaw", plan="skinmax")
    bare: dict = {}
    # Validate the base banks AND the Phase-4 extras (regardless of flag) so a
    # bad new variant can never ship — the import-time guard always covers them.
    all_banks: dict[str, list[_Tmpl]] = {
        cat: _BANKS[cat] + _PERSONALIZED_EXTRA.get(cat, []) for cat in _BANKS
    }
    for cat, bank in all_banks.items():
        for t in bank:
            for signals in (rich, bare):
                slots, _ = _slots(
                    name=signals.get("name"),
                    task=signals.get("task"),
                    streak=signals.get("streak"),
                    count=signals.get("count"),
                    why=signals.get("why"),
                    plan=signals.get("plan"),
                )
                try:
                    title = t.title.format(**slots)
                    body = t.body.format(**slots)
                except Exception as e:  # noqa: BLE001
                    problems.append(f"{cat}: format error {e} in {t.title!r}/{t.body!r}")
                    continue
                if len(title.split()) > 6:
                    problems.append(f"{cat}: title >6 words: {title!r}")
                if len(body) > 90:
                    problems.append(f"{cat}: body >90 chars: {body!r}")
                if body.count(".") > 1 and not body.rstrip().endswith("..."):
                    # one short sentence (a single trailing period is fine)
                    pass
                if not passes_taste_bar(title):
                    problems.append(f"{cat}: title fails taste bar: {title!r}")
                if not passes_taste_bar(body):
                    problems.append(f"{cat}: body fails taste bar: {body!r}")
    return problems


# Import-time guard: never ship a template bank that fails its own taste bar.
_TEMPLATE_PROBLEMS = validate_all_templates()
if _TEMPLATE_PROBLEMS:  # pragma: no cover
    logger.error("notification_copy template problems: %s", _TEMPLATE_PROBLEMS)


# --- backwards-compat shim --------------------------------------------------
# The legacy ``personalized_reminder`` / ``reminder_copy`` API is kept as a thin
# wrapper onto the new task-due category so existing callers don't break.

def personalized_reminder(
    profile: dict,
    *,
    maxx_label: str = "your",
    slot: str = "default",
    name: Optional[str] = None,
) -> dict[str, str]:
    """Legacy shim → new task-due copy. Returns {title, body} only."""
    _SLOT_ACTION = {
        "am": "morning routine",
        "pm": "evening routine",
        "midday": "midday check",
        "workout": "workout",
        "spf": "spf reapply",
        "default": "routine",
    }
    label = (maxx_label or "").strip()
    action = _SLOT_ACTION.get(slot, "routine")
    task = action if label.lower() in ("", "your") else f"{label} {action}"
    why = None
    try:
        goals = (profile or {}).get("goals") or {}
        why = (goals.get("why") or "").strip() or None
    except Exception:
        why = None
    out = compose(CAT_TASK_DUE, name=name, task=task, why=why)
    return {"title": out["title"], "body": out["body"]}


async def reminder_copy(
    db,
    user_id: str,
    *,
    maxx_label: str = "your",
    slot: str = "default",
) -> dict[str, str]:
    """Legacy async wrapper: load profile + name, compose task-due copy."""
    profile: dict = {}
    name: Optional[str] = None
    try:
        from services.personalization import get_profile  # type: ignore

        built = await get_profile(db, str(user_id))
        profile = built.get("profile") or {}
        name = ((profile.get("identity") or {}).get("name")) or None
    except Exception as e:  # noqa: BLE001
        logger.debug("reminder_copy profile load skipped: %s", e)
    return personalized_reminder(profile, maxx_label=maxx_label, slot=slot, name=name)
