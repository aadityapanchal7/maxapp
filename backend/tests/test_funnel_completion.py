"""Funnel-completion pass — the pure logic (picks ranking + seeded transcript).

The DB-bound halves (auto-enroll, chat seed) are exercised against prod-shaped
sessions in the sim E2E; here we pin the decision logic that routes them.
"""
from services.funnel_completion import _ranked_picks, _transcript


class TestRankedPicks:
    def test_goals_win_and_filter_unknown(self):
        ob = {"goals": ["skinmax", "notreal", "fitmax"]}
        assert _ranked_picks(ob) == ["skinmax", "fitmax"]

    def test_priority_order_tokens_fallback(self):
        ob = {"goals": [], "priority_order": ["body", "face_structure", "bogus"]}
        assert _ranked_picks(ob) == ["fitmax", "bonemax"]

    def test_empty(self):
        assert _ranked_picks({}) == []


class TestTranscript:
    def test_full_answers_shape(self):
        ob = {
            "goals": ["skinmax", "fitmax"],
            "motivation": "mog",
            "effort_level": "steady",
            "wake_time": "05:00",
        }
        turns = _transcript(ob, first_name="Chad")
        roles = [r for r, _ in turns]
        # Alternates and ends on the assistant's hand-off line.
        assert roles == ["assistant", "user", "assistant", "user", "assistant", "user", "assistant"]
        text = " | ".join(c for _, c in turns)
        # lowercase editorial voice — the name must not re-capitalize
        assert ", chad" in turns[0][1]
        assert "Chad" not in turns[0][1]
        assert "Skinmax + Fitmax" in text
        assert "i just want to mog" in text
        assert "steady — tweaking my daily routine" in text
        assert "05:00" in turns[-1][1]
        assert "Skinmax" in turns[-1][1]  # top pick named in the hand-off

    def test_motivation_other_uses_free_text(self):
        ob = {"goals": ["hairmax"], "motivation": "other", "motivation_other": "wedding in june"}
        text = " | ".join(c for _, c in _transcript(ob))
        assert "wedding in june" in text

    def test_missing_answers_skip_their_turns(self):
        turns = _transcript({"goals": ["bonemax"]})
        roles = [r for r, _ in turns]
        assert roles == ["assistant", "user", "assistant"]
        assert "Bonemax" in turns[1][1]

    def test_no_picks_still_coherent(self):
        turns = _transcript({})
        assert turns[1][1] == "not sure yet"
        assert "your plan" in turns[-1][1]
