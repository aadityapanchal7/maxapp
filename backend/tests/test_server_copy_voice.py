"""Golden voice tests for SERVER-GENERATED user-facing strings (the review
found these bypassed copy_filter's golden coverage): today-read lines,
held-back reason lines, win-back rungs, learner/welcome-back copy."""

from datetime import date

from api.planner import _REASON_LINES, _today_read
from services.copy_filter import filter_outbound_copy
from services.learner import welcome_back_state


def _assert_voice(s: str):
    result = filter_outbound_copy(s)
    assert result.clean, f"server copy fails the voice gate: {s!r} -> {result.mechanical + result.content}"


def test_today_read_lines_pass_voice_gate():
    cases = [
        _today_read(3, [], 8.0),                                   # green
        _today_read(3, [], 8.0, calendar_busy_minutes=6 * 60),     # yellow busy
        _today_read(3, [{"reason_code": "day_full"}], 8.0),        # yellow held
        _today_read(10, [], 8.0),                                  # yellow full
        _today_read(3, [], 6.0),                                   # yellow sleep
        _today_read(7, [{"reason_code": "day_full_hard"}], 8.0),   # red
    ]
    seen_lines = set()
    for verdict in cases:
        _assert_voice(verdict["line"])
        seen_lines.add(verdict["line"])
    # The line must state the trigger - six different cases, distinct copy.
    assert len(seen_lines) >= 5


def test_today_read_never_claims_trim_without_ledger():
    verdict = _today_read(10, [], 8.0)  # heavy day, nothing held back
    assert "trim" not in verdict["line"].lower()


def test_stated_short_sleep_alone_is_never_red():
    verdict = _today_read(7, [], 5.0)
    assert verdict["level"] != "red"


def test_reason_lines_pass_voice_gate():
    for line in _REASON_LINES.values():
        _assert_voice(line)


def test_welcome_back_copy_passes_voice_gate():
    state = welcome_back_state(
        {"master_schedule_streak_last_perfect_date": "2026-06-01"}, date(2026, 6, 10)
    )
    _assert_voice(state["line"])
    _assert_voice(state["sub"])
