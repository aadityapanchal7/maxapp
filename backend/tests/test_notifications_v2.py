"""Tests for the v2 notification system: copy engine + daily planner.

Covers success criteria 1-3, 5, 8, 9, 11 deterministically. Broadcast/admin
(criterion 4) is covered in test_admin_notifications.py.
"""

import os
import re

import pytest

from services.notification_copy import (
    ALL_CATEGORIES,
    CAT_TASK_DUE,
    CAT_MORNING_PREVIEW,
    CAT_REENGAGE,
    CAT_STREAK,
    CAT_MILESTONE,
    CAT_TIP,
    DEEP_LINK_ROUTES,
    compose,
    passes_taste_bar,
    validate_all_templates,
)
from services.notification_planner import (
    Candidate,
    PlannerContext,
    choose_channel,
    effective_cap,
    in_window,
    next_in_window_min,
    plan_day,
)

SAMPLE = dict(name="anish", task="morning skincare", streak=6, count=3, why="a sharper jaw", plan="skinmax")

BANNED_SNIPPETS = [
    "don't miss out", "miss out", "!!!", "last chance", "hurry",
    "your streak's watching", "ghosting", "crime", "don't lose", "don't break",
    "lose your", "shame", "guilt", "failure", "you failed",
]


# --- copy: every category is short, in-voice, personalized --------------------


def test_templates_self_validate():
    assert validate_all_templates() == []


# --- Phase 4: warmer personalized variants (flag-gated, default OFF) ----------

def _bodies(category, **kw):
    """All distinct bodies the rotation can produce for a category + signals."""
    return {compose(category, rotation=i, **kw)["body"] for i in range(12)}


def test_personalized_notif_copy_off_by_default_is_unchanged():
    # Default (no flag, no arg) must equal explicitly-off, for every category.
    for cat in (CAT_TASK_DUE, CAT_MORNING_PREVIEW, CAT_STREAK, CAT_REENGAGE):
        for i in range(12):
            default = compose(cat, rotation=i, **SAMPLE)
            off = compose(cat, rotation=i, personalized_copy=False, **SAMPLE)
            assert default == off


def test_personalized_reengage_variant_appears_only_when_enabled():
    phrase = "you started this for"
    off = _bodies(CAT_REENGAGE, personalized_copy=False, **SAMPLE)
    on = _bodies(CAT_REENGAGE, personalized_copy=True, **SAMPLE)
    # The warm why-variant is absent when off, reachable when on…
    assert not any(phrase in b for b in off)
    assert any(phrase in b and "a sharper jaw" in b for b in on)
    # …and all base lines are still reachable (additive, never removed).
    assert off <= on


def test_personalized_variants_require_their_signal_and_pass_taste_bar():
    # No {why}/{plan} signal → the warm variants never fire even when enabled.
    no_signal = _bodies(CAT_REENGAGE, personalized_copy=True)
    assert not any("you started this for" in b for b in no_signal)
    # Everything the rotation can emit (enabled, rich signals) clears the bar.
    for cat in (CAT_TASK_DUE, CAT_MORNING_PREVIEW, CAT_STREAK, CAT_REENGAGE):
        for i in range(12):
            out = compose(cat, rotation=i, personalized_copy=True, **SAMPLE)
            assert passes_taste_bar(out["title"]) and passes_taste_bar(out["body"])


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_category_copy_shape(category):
    out = compose(category, **SAMPLE)
    title, body = out["title"], out["body"]
    # title <= ~6 words
    assert len(title.split()) <= 6, f"{category} title too long: {title!r}"
    # body one short sentence <= ~90 chars
    assert len(body) <= 90, f"{category} body too long ({len(body)}): {body!r}"
    # lowercase, sharp-friend voice (no Title Case shouting)
    assert title == title.lower() or any(ch.isdigit() for ch in title)
    # taste bar
    assert passes_taste_bar(title) and passes_taste_bar(body)
    for snip in BANNED_SNIPPETS:
        assert snip not in title.lower()
        assert snip not in body.lower()


def test_task_due_names_the_task():
    out = compose(CAT_TASK_DUE, **SAMPLE)
    assert "skincare" in (out["title"] + out["body"]).lower()


def test_name_and_streak_appear_when_present():
    out = compose(CAT_STREAK, **SAMPLE)
    assert "anish" in out["body"].lower()
    assert "6" in (out["title"] + out["body"])  # streak day count surfaced


def test_rotation_returns_different_lines():
    bodies = {compose("tip", rotation=i)["body"] for i in range(4)}
    assert len(bodies) >= 3, bodies


def test_do_not_repeat_recently_guard():
    first = compose("tip", rotation=0)
    second = compose("tip", rotation=0, recent=[first["template_id"]])
    assert second["template_id"] != first["template_id"]


def test_graceful_degradation_no_signals():
    out = compose(CAT_TASK_DUE)  # no name/streak/why
    assert out["title"] and out["body"]
    assert passes_taste_bar(out["body"])
    assert "{" not in out["body"] and "}" not in out["body"]


def test_taste_bar_rejects_shame_and_fomo():
    assert not passes_taste_bar("don't miss out!!!")
    assert not passes_taste_bar("your streak's watching, don't lose it")
    assert not passes_taste_bar("ghosting now would be a crime")
    assert passes_taste_bar("day 6 looks good on you. one more keeps it going.")


# --- deep-link: every category routes to an allowed screen --------------------


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_every_category_has_allowed_route(category):
    out = compose(category, **SAMPLE)
    assert out["route"] in DEEP_LINK_ROUTES
    assert out["params"]["category"] == category


def test_task_due_deeplinks_to_specific_task():
    out = compose(CAT_TASK_DUE, route_params={"task_uuid": "abc", "maxx": "skinmax"})
    assert out["route"] == "TaskGuide"
    assert out["params"]["task_uuid"] == "abc"


def test_milestone_routes_to_achievements():
    assert compose(CAT_MILESTONE, **SAMPLE)["route"] == "Achievements"


def test_mobile_allowlist_covers_every_backend_route():
    """Guard against the backend route map and the mobile App.tsx deep-link
    allow-list drifting apart — a route emitted by the server but missing from
    App.tsx would silently fail to deep-link (criterion 6)."""
    app_tsx = os.path.join(os.path.dirname(__file__), "..", "..", "mobile", "App.tsx")
    if not os.path.exists(app_tsx):
        pytest.skip("mobile/App.tsx not present in this checkout")
    with open(app_tsx, "r", encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"NOTIFICATION_DEEP_LINK_ROUTES\s*=\s*new Set<string>\(\[(.*?)\]\)", src, re.S)
    assert m, "could not find NOTIFICATION_DEEP_LINK_ROUTES in App.tsx"
    mobile_routes = set(re.findall(r"['\"]([A-Za-z]+)['\"]", m.group(1)))
    # Every route the backend can emit must be handled by the mobile app.
    backend_routes = {compose(c, **SAMPLE)["route"] for c in ALL_CATEGORIES}
    missing = backend_routes - mobile_routes
    assert not missing, f"App.tsx is missing deep-link routes the backend emits: {missing}"
    assert backend_routes <= DEEP_LINK_ROUTES


# --- planner: cap, priority, window, interval, dedup --------------------------


def _ctx(**kw):
    base = dict(now_min=8 * 60, wake_min=7 * 60, sleep_min=23 * 60, cap=5, min_interval_min=90)
    base.update(kw)
    return PlannerContext(**base)


def _day_candidates():
    return [
        Candidate(CAT_TASK_DUE, 8 * 60, task_uuid="t1"),
        Candidate(CAT_TASK_DUE, 8 * 60 + 30, task_uuid="t2"),
        Candidate(CAT_TASK_DUE, 9 * 60, task_uuid="t3"),
        Candidate(CAT_STREAK, 16 * 60),
        Candidate("evening_recap", 21 * 60),
        Candidate("morning_preview", 7 * 60 + 15),
        Candidate("tip", 13 * 60),
    ]


def test_planner_caps_and_prioritizes():
    ctx = _ctx(cap=5)
    sel = plan_day(ctx, _day_candidates())
    assert len(sel) <= ctx.cap
    cats = [c.category for c in sel]
    # 8:00 / 8:30 / 9:00 all sit inside one min-interval span — the cluster
    # collapses to its 8:00 leader so the reminder fires ON TIME instead of the
    # tail being dragged late by spacing.
    assert cats.count(CAT_TASK_DUE) == 1
    task_due = next(c for c in sel if c.category == CAT_TASK_DUE)
    assert task_due.task_uuid == "t1"
    assert task_due.params["send_min"] == 8 * 60


def test_planner_cluster_collapse_frees_cap_for_evening_tasks():
    """Two tight clusters (4 tasks pre-7am, 2 at night) — the old '5 earliest'
    selection spent the whole cap on the morning cluster (whose tail then
    drifted hours late) and left the evening silent. Each cluster now sends one
    on-time reminder and the evening keeps its slot."""
    cands = [
        Candidate(CAT_TASK_DUE, 5 * 60 + 5, task_uuid="am1"),
        Candidate(CAT_TASK_DUE, 5 * 60 + 20, task_uuid="am2"),
        Candidate(CAT_TASK_DUE, 5 * 60 + 47, task_uuid="am3"),
        Candidate(CAT_TASK_DUE, 6 * 60 + 7, task_uuid="am4"),
        Candidate(CAT_TASK_DUE, 21 * 60 + 30, task_uuid="pm1"),
        Candidate(CAT_TASK_DUE, 21 * 60 + 50, task_uuid="pm2"),
        Candidate("morning_preview", 5 * 60),
        Candidate("evening_recap", 21 * 60),
    ]
    ctx = _ctx(now_min=5 * 60, wake_min=5 * 60, cap=5)
    sel = plan_day(ctx, cands)
    fired = {c.task_uuid: c.params["send_min"] for c in sel if c.category == CAT_TASK_DUE}
    # one leader per cluster, each AT its own scheduled minute
    assert fired == {"am1": 5 * 60 + 5, "pm1": 21 * 60 + 30}


def test_planner_respects_window_and_interval():
    ctx = _ctx()
    sel = plan_day(ctx, _day_candidates())
    sends = [c.params["send_min"] for c in sel]
    for s in sends:
        assert in_window(s, ctx.wake_min, ctx.sleep_min)
    for a, b in zip(sends, sends[1:]):
        assert b - a >= ctx.min_interval_min


def test_planner_no_duplicate_keys_or_double_nudge():
    ctx = _ctx()
    sel = plan_day(ctx, _day_candidates())
    keys = [c.dedup_key for c in sel]
    assert len(keys) == len(set(keys))


def test_planner_skips_already_nudged_task():
    ctx = _ctx(already_nudged_tasks=frozenset({"t1"}))
    sel = plan_day(ctx, _day_candidates())
    assert all(c.task_uuid != "t1" for c in sel)


def test_planner_honors_mute():
    ctx = _ctx(muted_categories=frozenset({"tip", CAT_STREAK}))
    sel = plan_day(ctx, _day_candidates())
    assert all(c.category not in ("tip", CAT_STREAK) for c in sel)


def test_planner_suppresses_when_foreground():
    ctx = _ctx(foreground_recent=True)
    assert plan_day(ctx, _day_candidates()) == []


def test_planner_drops_out_of_window_candidate():
    ctx = _ctx()
    cands = [Candidate(CAT_TASK_DUE, 3 * 60, task_uuid="night")]  # 3am, asleep
    assert plan_day(ctx, cands) == []


# --- window / timezone math ---------------------------------------------------


def test_window_overnight_sleep_crossing_midnight():
    # wake 07:00, sleep 01:00 next day
    assert in_window(23 * 60, 7 * 60, 1 * 60)      # 11pm awake
    assert in_window(0 * 60 + 30, 7 * 60, 1 * 60)  # 12:30am awake
    assert not in_window(3 * 60, 7 * 60, 1 * 60)   # 3am asleep


def test_asleep_user_gets_nothing_now_but_queues_to_wake():
    # asleep at 3am; next in-window slot is wake (07:00)
    assert not in_window(3 * 60, 7 * 60, 23 * 60)
    assert next_in_window_min(3 * 60, 7 * 60, 23 * 60) == 7 * 60
    # already awake -> queue is "now"
    assert next_in_window_min(9 * 60, 7 * 60, 23 * 60) == 9 * 60


# --- adaptive backoff ---------------------------------------------------------


def test_backoff_steps_down_for_ignored_pushes():
    assert effective_cap(5, recent_delivered=10, recent_opened=0) == 1
    assert effective_cap(5, recent_delivered=10, recent_opened=1) == 2
    assert effective_cap(5, recent_delivered=10, recent_opened=2) == 3
    assert effective_cap(5, recent_delivered=10, recent_opened=5) == 5


def test_backoff_ramps_lapsed_user_gently():
    assert effective_cap(6, returning_lapsed=True) == 2


def test_backoff_ignores_tiny_sample():
    # too few delivered to judge -> full cap
    assert effective_cap(5, recent_delivered=2, recent_opened=0) == 5


# --- kill switch (review item 10) --------------------------------------------


@pytest.mark.asyncio
async def test_kill_switch_short_circuits_apns(monkeypatch):
    """Kill switch suppresses every push at the APNs layer, before any network
    call — returns (False, None) without attempting delivery."""
    import services.apns_service as apns
    monkeypatch.setattr(apns.settings, "notif_kill_switch", True, raising=False)
    # Even with a token present, nothing is sent.
    ok, status = await apns.send_apns_alert("deadbeef", "title", "body")
    assert ok is False and status is None


# --- cross-channel dedup (criterion 10): one channel per user -----------------


def test_choose_channel_prefers_push_never_both():
    assert choose_channel(want_push=True, want_sms=True) == "push"   # never both
    assert choose_channel(want_push=True, want_sms=False) == "push"
    assert choose_channel(want_push=False, want_sms=True) == "sms"
    assert choose_channel(want_push=False, want_sms=False) is None


# --- timezone: morning push lands near the user's LOCAL wake (review item 1) --


def test_morning_push_is_in_local_window_regardless_of_server_tz():
    # User wakes 07:00 *local*. The planner works in local minutes-of-day, so a
    # morning-preview built at wake+15 is in-window and selected no matter what
    # timezone the server runs in.
    from services.notification_candidates import build_candidates

    wake_min = 7 * 60
    cands = build_candidates(
        tasks=_TASKS, now_min=wake_min, wake_min=wake_min, sleep_min=23 * 60,
        weekday=1, name="anish", why=None, streak=0, active_plans={"skinmax"},
    )
    morning = next(c for c in cands if c.category == "morning_preview")
    assert in_window(morning.at_min, wake_min, 23 * 60)
    assert abs(morning.at_min - wake_min) <= 30  # near their wake, not server's

    ctx = PlannerContext(now_min=wake_min, wake_min=wake_min, sleep_min=23 * 60, cap=5, min_interval_min=90)
    sel = plan_day(ctx, cands)
    assert any(c.category == "morning_preview" for c in sel)
    # A pre-dawn (3am local) candidate would be suppressed by the same window.
    assert not in_window(3 * 60, wake_min, 23 * 60)


# --- candidate builder: empty-state + plan-relevance guards -------------------

from services.notification_candidates import build_candidates

_TASKS = [{"uuid": "t1", "title": "morning skincare", "time_min": 480, "maxx": "skinmax", "pending": True}]


def _cats(**kw):
    base = dict(
        tasks=_TASKS, now_min=480, wake_min=420, sleep_min=1380, weekday=0,
        name="anish", why="a sharper jaw", streak=6, active_plans={"skinmax"},
    )
    base.update(kw)
    return [c.category for c in build_candidates(**base)]


def test_new_user_no_streak_push():
    assert CAT_STREAK not in _cats(streak=0)
    assert CAT_STREAK not in _cats(streak=1)


def test_established_user_gets_streak_push():
    assert CAT_STREAK in _cats(streak=6)


def test_no_recap_when_nothing_pending():
    done = [{"uuid": "t1", "title": "x", "time_min": 480, "maxx": "skinmax", "pending": False}]
    assert "evening_recap" not in _cats(tasks=done)


def test_tip_requires_active_plan_and_weekday():
    assert CAT_TIP not in _cats(active_plans=set())     # no plan
    assert CAT_TIP not in _cats(weekday=6)              # weekend
    assert CAT_TIP in _cats(active_plans={"skinmax"}, weekday=0)


def test_task_due_candidate_carries_task_deeplink():
    cands = build_candidates(
        tasks=_TASKS, now_min=480, wake_min=420, sleep_min=1380, weekday=1,
        name="anish", why=None, streak=0, active_plans={"skinmax"},
    )
    td = next(c for c in cands if c.category == CAT_TASK_DUE)
    assert td.route == "TaskGuide"
    assert td.params["task_uuid"] == "t1"
    assert "skincare" in (td.title + td.body).lower()
