"""Google Calendar routine mirror: identity, diffing, and the two hard promises.

No live Google, no DB — these exercise the pure reconcile logic that guarantees
"never a duplicate, never an overlap".
"""

from datetime import date
from types import SimpleNamespace

import pytest

from services.gcal_mirror import (
    build_desired,
    diff_desired_vs_links,
    event_key,
    fingerprint,
)

USER = "11111111-1111-1111-1111-111111111111"
TZ = "America/New_York"


def task(title="Morning skincare", time="07:30", *, catalog_id="skin.am",
         dur=15, status="pending", maxx_id="skinmax", task_id="whatever",
         program_id=None):
    t = {
        "title": title, "time": time, "duration_min": dur, "status": status,
        "catalog_id": catalog_id, "maxx_id": maxx_id, "task_id": task_id,
    }
    if program_id:
        t["provenance"] = {"program_id": program_id}
    return t


def view(*days):
    return list(days)


def day(iso, tasks):
    return {"date": iso, "tasks": tasks}


# --------------------------------------------------------------------------- #
#  Identity — the no-duplicates backbone                                       #
# --------------------------------------------------------------------------- #

def test_key_survives_task_id_churn():
    """task_id is a fresh uuid4 on every expansion; the key must not move."""
    a = event_key(USER, task(task_id="uuid-A"), "2026-03-03")
    b = event_key(USER, task(task_id="uuid-B"), "2026-03-03")
    assert a == b


def test_key_differs_per_date():
    a = event_key(USER, task(), "2026-03-03")
    b = event_key(USER, task(), "2026-03-04")
    assert a != b


def test_key_differs_per_user():
    other = "22222222-2222-2222-2222-222222222222"
    assert event_key(USER, task(), "2026-03-03") != event_key(other, task(), "2026-03-03")


def test_key_differs_per_program():
    a = event_key(USER, task(program_id="skinmax"), "2026-03-03")
    b = event_key(USER, task(program_id="hairmax"), "2026-03-03")
    assert a != b


def test_key_falls_back_to_title_slug_without_catalog_id():
    """LLM-path and free-text tasks still need a stable identity."""
    a = event_key(USER, task(catalog_id=None, title="Cold shower"), "2026-03-03")
    b = event_key(USER, task(catalog_id=None, title="Cold shower", task_id="other"), "2026-03-03")
    assert a == b
    c = event_key(USER, task(catalog_id=None, title="Hot shower"), "2026-03-03")
    assert a != c


def test_same_catalog_twice_a_day_gets_distinct_keys():
    d = build_desired(view(day("2026-03-03", [
        task(title="Skincare AM", time="07:30", catalog_id="skin.routine"),
        task(title="Skincare PM", time="21:30", catalog_id="skin.routine"),
    ])), USER, TZ)
    assert len(d) == 2, "an AM and PM block sharing a catalog_id must not collide"


# --------------------------------------------------------------------------- #
#  Fingerprint                                                                 #
# --------------------------------------------------------------------------- #

def test_fingerprint_moves_with_time_and_title():
    base = dict(title="A", date_iso="2026-03-03", time_str="07:30", duration_min=15, tz_name=TZ)
    assert fingerprint(**base) == fingerprint(**base)
    assert fingerprint(**{**base, "time_str": "08:00"}) != fingerprint(**base)
    assert fingerprint(**{**base, "title": "B"}) != fingerprint(**base)
    assert fingerprint(**{**base, "duration_min": 30}) != fingerprint(**base)


# --------------------------------------------------------------------------- #
#  Desired state                                                               #
# --------------------------------------------------------------------------- #

def test_basic_event_times_and_timezone():
    d = build_desired(view(day("2026-03-03", [task(time="07:30", dur=20)])), USER, TZ)
    ev = next(iter(d.values()))
    assert ev.start_local == "2026-03-03T07:30:00"
    assert ev.end_local == "2026-03-03T07:50:00"
    assert ev.tz_name == TZ
    assert ev.event_date == date(2026, 3, 3)


def test_completed_task_gets_a_checkmark():
    d = build_desired(view(day("2026-03-03", [task(status="completed")])), USER, TZ)
    assert next(iter(d.values())).title.startswith("✓ ")


def test_skipped_task_is_absent_so_the_diff_deletes_it():
    d = build_desired(view(day("2026-03-03", [task(status="skipped")])), USER, TZ)
    assert d == {}


def test_overnight_task_rolls_to_the_next_calendar_date():
    """A 01:30 wind-down stored on the 3rd belongs on the 4th in a calendar."""
    d = build_desired(view(day("2026-03-03", [task(time="01:30")])), USER, TZ)
    ev = next(iter(d.values()))
    assert ev.start_local.startswith("2026-03-04")
    assert ev.event_date == date(2026, 3, 4)


def test_early_morning_after_cutoff_stays_on_its_own_date():
    d = build_desired(view(day("2026-03-03", [task(time="05:30")])), USER, TZ)
    assert next(iter(d.values())).start_local.startswith("2026-03-03")


def test_overlapping_durations_are_clamped():
    """Two Max events must never overlap, whatever the durations claim."""
    d = build_desired(view(day("2026-03-03", [
        task(title="A", time="07:00", dur=90, catalog_id="a"),
        task(title="B", time="07:30", dur=15, catalog_id="b"),
    ])), USER, TZ)
    by_title = {e.title: e for e in d.values()}
    assert by_title["A"].end_local <= by_title["B"].start_local


def test_tasks_without_a_time_are_skipped():
    d = build_desired(view(day("2026-03-03", [task(time=None)])), USER, TZ)
    assert d == {}


# --------------------------------------------------------------------------- #
#  Diff                                                                        #
# --------------------------------------------------------------------------- #

def _links_from(desired):
    return {k: SimpleNamespace(fingerprint=v.fingerprint) for k, v in desired.items()}


def test_first_run_is_all_inserts():
    d = build_desired(view(day("2026-03-03", [task()])), USER, TZ)
    ins, pat, dele = diff_desired_vs_links(d, {})
    assert len(ins) == 1 and not pat and not dele


def test_second_run_over_pushed_state_is_a_complete_noop():
    """The steady state must cost zero Google API calls."""
    d = build_desired(view(day("2026-03-03", [task()])), USER, TZ)
    ins, pat, dele = diff_desired_vs_links(d, _links_from(d))
    assert not ins and not pat and not dele


def test_time_change_produces_exactly_one_patch():
    before = build_desired(view(day("2026-03-03", [task(time="07:30")])), USER, TZ)
    after = build_desired(view(day("2026-03-03", [task(time="09:00")])), USER, TZ)
    ins, pat, dele = diff_desired_vs_links(after, _links_from(before))
    assert not ins and not dele and len(pat) == 1


def test_completing_a_task_patches_rather_than_duplicates():
    before = build_desired(view(day("2026-03-03", [task()])), USER, TZ)
    after = build_desired(view(day("2026-03-03", [task(status="completed")])), USER, TZ)
    ins, pat, dele = diff_desired_vs_links(after, _links_from(before))
    assert not ins, "completion must not create a second event"
    assert len(pat) == 1


def test_skipping_a_task_deletes_its_event():
    before = build_desired(view(day("2026-03-03", [task()])), USER, TZ)
    after = build_desired(view(day("2026-03-03", [task(status="skipped")])), USER, TZ)
    ins, pat, dele = diff_desired_vs_links(after, _links_from(before))
    assert len(dele) == 1 and not ins and not pat


def test_dropped_task_is_deleted_and_new_one_inserted():
    before = build_desired(view(day("2026-03-03", [task(catalog_id="old", title="Old")])), USER, TZ)
    after = build_desired(view(day("2026-03-03", [task(catalog_id="new", title="New")])), USER, TZ)
    ins, pat, dele = diff_desired_vs_links(after, _links_from(before))
    assert len(ins) == 1 and len(dele) == 1


def test_regeneration_with_new_task_ids_produces_no_churn():
    """The whole point: a regen that changes every task_id must be a no-op."""
    before = build_desired(view(day("2026-03-03", [
        task(catalog_id="a", title="A", task_id="old-1"),
        task(catalog_id="b", title="B", time="08:00", task_id="old-2"),
    ])), USER, TZ)
    after = build_desired(view(day("2026-03-03", [
        task(catalog_id="a", title="A", task_id="new-1"),
        task(catalog_id="b", title="B", time="08:00", task_id="new-2"),
    ])), USER, TZ)
    ins, pat, dele = diff_desired_vs_links(after, _links_from(before))
    assert not (ins or pat or dele)


# --------------------------------------------------------------------------- #
#  Trigger                                                                     #
# --------------------------------------------------------------------------- #

def test_kick_is_inert_when_the_feature_is_off(monkeypatch):
    import services.gcal_mirror as gm
    monkeypatch.setattr(gm.settings, "gcal_write_enabled", False, raising=False)
    gm.kick_gcal_mirror(USER)
    assert USER not in gm._in_flight


def test_kick_without_an_event_loop_does_not_strand_the_claim(monkeypatch):
    """A sync caller (script/test) must not leave the user permanently 'in flight'."""
    import services.gcal_mirror as gm
    monkeypatch.setattr(gm.settings, "gcal_write_enabled", True, raising=False)
    gm.kick_gcal_mirror(USER)
    assert USER not in gm._in_flight


@pytest.mark.asyncio
async def test_second_kick_during_a_run_coalesces_into_one_rerun(monkeypatch):
    import asyncio

    import services.gcal_mirror as gm
    monkeypatch.setattr(gm.settings, "gcal_write_enabled", True, raising=False)

    runs = []

    class _FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    async def fake_mirror(uid, db):
        runs.append(uid)
        if len(runs) == 1:
            gm.kick_gcal_mirror(uid)   # a change lands mid-run
        return {}

    monkeypatch.setattr(gm, "mirror_user_calendar", fake_mirror)
    import db.sqlalchemy as dbmod
    monkeypatch.setattr(dbmod, "AsyncSessionLocal", lambda: _FakeSession())

    gm.kick_gcal_mirror(USER, delay=0)
    for _ in range(20):
        await asyncio.sleep(0.01)
        if USER not in gm._in_flight:
            break
    assert len(runs) == 2, "the mid-run change should trigger exactly one rerun"
    assert USER not in gm._in_flight
