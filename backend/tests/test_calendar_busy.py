"""Calendar-aware generation: projection rules + the no-overlap invariant.

Pure-function tests (no DB, no live Google), matching the house style.
"""

from datetime import date, datetime, timedelta

import pytest

from services.calendar_busy import (
    apply_calendar_busy,
    busy_fingerprint,
    project_events_to_busy_by_date,
)


def ev(start: str, end: str, *, status="confirmed", is_busy=True, all_day=False,
       external_event_id=None, raw=None, title="Meeting"):
    return {
        "starts_at": datetime.fromisoformat(start),
        "ends_at": datetime.fromisoformat(end),
        "status": status,
        "is_busy": is_busy,
        "all_day": all_day,
        "external_event_id": external_event_id,
        "raw": raw or {},
        "title": title,
    }


WIN_START = date(2026, 3, 2)   # a Monday
WIN_END = date(2026, 3, 16)


def _project(events):
    return project_events_to_busy_by_date(events, WIN_START, WIN_END)


# --------------------------------------------------------------------------- #
#  Projection rules                                                            #
# --------------------------------------------------------------------------- #

def test_confirmed_busy_timed_event_becomes_an_interval():
    out = _project([ev("2026-03-03T09:00", "2026-03-03T10:30")])
    assert out == {"2026-03-03": [{"start": "09:00", "end": "10:30", "label": "busy"}]}


def test_label_never_leaks_the_event_title():
    out = _project([ev("2026-03-03T09:00", "2026-03-03T10:00", title="Therapy — Dr Chen")])
    assert out["2026-03-03"][0]["label"] == "busy"
    assert "Therapy" not in str(out)


@pytest.mark.parametrize("kwargs", [
    {"status": "proposed"},    # Gmail guess the user never confirmed
    {"status": "dismissed"},   # user explicitly rejected it
    {"is_busy": False},        # marked Free in Google
    {"all_day": True},         # a label, not 24h of unavailability
])
def test_non_blocking_events_are_excluded(kwargs):
    assert _project([ev("2026-03-03T09:00", "2026-03-03T10:00", **kwargs)]) == {}


@pytest.mark.parametrize("kwargs", [
    {"raw": {"max_authored": True}},
    {"external_event_id": "max:abc123"},
])
def test_max_authored_events_never_block_us(kwargs):
    """Our own mirrored routine must never be read back as busy time."""
    assert _project([ev("2026-03-03T09:00", "2026-03-03T10:00", **kwargs)]) == {}


def test_multi_day_event_splits_and_clamps_per_date():
    out = _project([ev("2026-03-03T22:00", "2026-03-04T06:00")])
    assert out["2026-03-03"] == [{"start": "22:00", "end": "23:59", "label": "busy"}]
    assert out["2026-03-04"] == [{"start": "00:00", "end": "06:00", "label": "busy"}]


def test_overlapping_events_merge_into_one_span():
    out = _project([
        ev("2026-03-03T09:00", "2026-03-03T10:00"),
        ev("2026-03-03T09:30", "2026-03-03T11:00"),
    ])
    assert out["2026-03-03"] == [{"start": "09:00", "end": "11:00", "label": "busy"}]


def test_events_outside_the_window_are_ignored():
    assert _project([ev("2026-02-01T09:00", "2026-02-01T10:00")]) == {}
    assert _project([ev("2026-04-01T09:00", "2026-04-01T10:00")]) == {}


def test_zero_length_and_inverted_events_dropped():
    assert _project([ev("2026-03-03T09:00", "2026-03-03T09:00")]) == {}
    assert _project([ev("2026-03-03T10:00", "2026-03-03T09:00")]) == {}


# --------------------------------------------------------------------------- #
#  Fingerprint (drift detection)                                               #
# --------------------------------------------------------------------------- #

def test_fingerprint_stable_for_identical_calendars():
    a = [ev("2026-03-03T09:00", "2026-03-03T10:00"), ev("2026-03-04T14:00", "2026-03-04T15:00")]
    b = list(reversed(a))
    assert busy_fingerprint(a) == busy_fingerprint(b)


def test_fingerprint_changes_when_a_meeting_moves():
    a = [ev("2026-03-03T09:00", "2026-03-03T10:00")]
    b = [ev("2026-03-03T11:00", "2026-03-03T12:00")]
    assert busy_fingerprint(a) != busy_fingerprint(b)


def test_fingerprint_ignores_churn_we_do_not_honor():
    base = [ev("2026-03-03T09:00", "2026-03-03T10:00")]
    noisy = base + [
        ev("2026-03-05T09:00", "2026-03-05T10:00", status="proposed"),
        ev("2026-03-06T00:00", "2026-03-07T00:00", all_day=True),
    ]
    assert busy_fingerprint(base) == busy_fingerprint(noisy)


# --------------------------------------------------------------------------- #
#  apply_calendar_busy — the end-to-end invariant                              #
# --------------------------------------------------------------------------- #

def _day(iso, tasks):
    return {"date": iso, "tasks": tasks}


def _task(title, time, dur=15):
    return {"title": title, "time": time, "duration_min": dur, "catalog_id": title}


def _overlaps(t, span_start, span_end):
    from services.schedule_validator import _parse_time_field
    s = _parse_time_field(t["time"])
    e = s + int(t.get("duration_min") or 1)
    return s < span_end and e > span_start


def test_task_inside_a_meeting_is_pushed_clear():
    days = [_day("2026-03-03", [_task("Skincare", "09:30")])]
    busy = {"2026-03-03": [{"start": "09:00", "end": "10:30", "label": "busy"}]}
    out = apply_calendar_busy(days, busy)
    assert not _overlaps(out[0]["tasks"][0], 9 * 60, 10 * 60 + 30)
    assert out[0]["tasks"][0]["time"] == "10:30"


def test_task_already_clear_is_untouched():
    days = [_day("2026-03-03", [_task("Skincare", "07:00")])]
    before = dict(days[0]["tasks"][0])
    out = apply_calendar_busy(days, {"2026-03-03": [{"start": "09:00", "end": "10:00", "label": "busy"}]})
    assert out[0]["tasks"][0] == before


def test_other_dates_are_untouched():
    days = [
        _day("2026-03-03", [_task("A", "09:30")]),
        _day("2026-03-04", [_task("B", "09:30")]),
    ]
    out = apply_calendar_busy(days, {"2026-03-03": [{"start": "09:00", "end": "10:00", "label": "busy"}]})
    assert out[1]["tasks"][0]["time"] == "09:30"


def test_multiple_tasks_never_overlap_each_other_or_the_meeting():
    days = [_day("2026-03-03", [_task("A", "09:10"), _task("B", "09:20"), _task("C", "09:40")])]
    busy = {"2026-03-03": [{"start": "09:00", "end": "10:00", "label": "busy"}]}
    out = apply_calendar_busy(days, busy)
    tasks = out[0]["tasks"]
    for t in tasks:
        assert not _overlaps(t, 9 * 60, 10 * 60), f"{t['title']} still inside the meeting"
    from services.schedule_validator import _parse_time_field
    starts = [_parse_time_field(t["time"]) for t in tasks]
    assert starts == sorted(starts)
    for a, b in zip(tasks, tasks[1:]):
        a_end = _parse_time_field(a["time"]) + a["duration_min"]
        assert _parse_time_field(b["time"]) >= a_end


def test_empty_busy_map_is_a_noop():
    days = [_day("2026-03-03", [_task("A", "09:30")])]
    assert apply_calendar_busy(days, {}) == days


# --------------------------------------------------------------------------- #
#  Validator integration — per-date busy actually evicts                       #
# --------------------------------------------------------------------------- #

def test_validator_evicts_around_a_dated_calendar_event():
    from services.schedule_validator import _apply_day_windows

    start = date(2026, 3, 3)
    days = [
        {"date": "2026-03-03", "tasks": [_task("Morning routine", "09:15")]},
        {"date": "2026-03-04", "tasks": [_task("Morning routine", "09:15")]},
    ]
    user_ctx = {
        "wake_time": "07:00",
        "sleep_time": "23:00",
        "calendar_busy_by_date": {
            "2026-03-03": [{"start": "09:00", "end": "11:00", "label": "busy"}]
        },
    }
    errors = []
    out = _apply_day_windows(
        days, user_ctx, start_date=start,
        global_wake="07:00", global_sleep="23:00", errors=errors,
    )
    # The dated meeting cleared day 0...
    assert not _overlaps(out[0]["tasks"][0], 9 * 60, 11 * 60)
    # ...and the very next day, which has no event, is untouched.
    assert out[1]["tasks"][0]["time"] == "09:15"


def test_calendar_busy_for_date_ignores_malformed_spans():
    from services.schedule_validator import _calendar_busy_for_date

    ctx = {"calendar_busy_by_date": {"2026-03-03": [
        {"start": "09:00", "end": "10:00"},
        {"start": "bad", "end": "10:00"},
        {"start": "11:00", "end": "11:00"},
        {"start": "13:00", "end": "12:00"},
        "not-a-dict",
    ]}}
    assert _calendar_busy_for_date(ctx, "2026-03-03") == [(540, 600)]
    assert _calendar_busy_for_date(ctx, "2026-03-04") == []
    assert _calendar_busy_for_date({}, "2026-03-03") == []
