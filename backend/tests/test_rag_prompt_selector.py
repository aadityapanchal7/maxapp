"""Unit tests + accuracy backtest for the RAG prompt selector."""

from __future__ import annotations

import pytest

from services import prompt_loader
from services.prompt_loader import PromptKey
from services.rag_prompt_selector import (
    _LEXICONS,
    SelectedRagPrompt,
    select_rag_system_prompt,
)


@pytest.fixture(autouse=True)
def _seed_cache():
    """Seed the prompt cache with stub reference bodies so selector output is deterministic."""
    prompt_loader.clear_prompt_cache()
    prompt_loader._CACHE.update({
        PromptKey.RAG_ANSWER_SYSTEM: "BASE RAG SYSTEM PROMPT.",
        "skinmax_coaching_reference": "SKINMAX REFERENCE BODY",
        "fitmax_coaching_reference": "FITMAX REFERENCE BODY",
        "hairmax_coaching_reference": "HAIRMAX REFERENCE BODY",
        "bonemax_coaching_reference": "BONEMAX REFERENCE BODY",
        "heightmax_coaching_reference": "HEIGHTMAX REFERENCE BODY",
    })
    yield
    prompt_loader.clear_prompt_cache()


# --------------------------------------------------------------------------- #
#  Unit tests                                                                  #
# --------------------------------------------------------------------------- #

def test_single_hint_is_trusted_even_without_lexicon_match():
    result = select_rag_system_prompt("what time is it", maxx_hints=["skinmax"])
    assert isinstance(result, SelectedRagPrompt)
    assert result.chosen_maxx == "skinmax"
    assert "SKINMAX REFERENCE BODY" in result.system_prompt
    assert "BASE RAG SYSTEM PROMPT." in result.system_prompt
    assert "classifier hint=skinmax" in result.reason


def test_multi_hint_tiebreak_picks_best_lexicon_match():
    result = select_rag_system_prompt(
        "how often should i reapply minoxidil to a receding hairline?",
        maxx_hints=["skinmax", "hairmax"],
    )
    assert result.chosen_maxx == "hairmax"
    assert "HAIRMAX REFERENCE BODY" in result.system_prompt
    assert "tiebreak" in result.reason


def test_no_hint_lexicon_winner_when_signal_is_strong():
    result = select_rag_system_prompt(
        "what is the best split for hypertrophy with creatine and whey protein?"
    )
    assert result.chosen_maxx == "fitmax"
    assert "FITMAX REFERENCE BODY" in result.system_prompt
    assert result.score > 0


def test_no_hint_no_signal_falls_back_to_active_maxx():
    result = select_rag_system_prompt(
        "anything new today?", active_maxx="skinmax"
    )
    assert result.chosen_maxx == "skinmax"
    assert "fallback active_maxx=skinmax" in result.reason


def test_no_hint_no_active_maxx_returns_generic_base():
    result = select_rag_system_prompt("anything new today?")
    assert result.chosen_maxx is None
    assert "generic base" in result.reason
    # System prompt is just the base — no MODULE REFERENCE block.
    assert "BASE RAG SYSTEM PROMPT." in result.system_prompt
    assert "MODULE REFERENCE" not in result.system_prompt


def test_missing_reference_in_cache_returns_base_and_reports():
    prompt_loader._CACHE.pop("skinmax_coaching_reference", None)
    result = select_rag_system_prompt(
        "what should i do for acne", maxx_hints=["skinmax"]
    )
    assert result.chosen_maxx == "skinmax"
    assert "reference prompt missing" in result.reason
    # Falls back to base only — no module reference body available
    assert "BASE RAG SYSTEM PROMPT." in result.system_prompt
    assert "SKINMAX REFERENCE BODY" not in result.system_prompt


def test_lexicon_is_comprehensive():
    """Every known maxx must have a lexicon entry (guard against schema drift)."""
    assert set(_LEXICONS.keys()) == {"skinmax", "fitmax", "hairmax", "bonemax", "heightmax"}
    for maxx, lex in _LEXICONS.items():
        assert lex, f"{maxx} lexicon is empty"


# --------------------------------------------------------------------------- #
#  Backtest — 50 labeled queries, assert ≥ 88% accuracy                        #
# --------------------------------------------------------------------------- #

# (query, expected_maxx, [hints])  — hints=None means the selector runs
# without any classifier signal (hardest case — pure NLP).
BACKTEST_CASES: list[tuple[str, str, list[str] | None]] = [
    # skinmax
    ("what should i do for acne at night?", "skinmax", None),
    ("is adapalene safe to use every day?", "skinmax", None),
    ("how do i get rid of blackheads on my nose", "skinmax", None),
    ("best spf for oily skin", "skinmax", None),
    ("my pores look huge after cleanser", "skinmax", None),
    ("niacinamide vs azelaic acid for redness?", "skinmax", None),
    ("should i dermaroll if i have active breakouts?", "skinmax", None),
    ("how long does tretinoin take to work", "skinmax", None),
    ("pm routine for rosacea", "skinmax", None),
    ("i have a pimple before a date, fastest fix?", "skinmax", None),

    # fitmax
    ("what macros should i hit for cutting?", "fitmax", None),
    ("is a push pull legs split good for hypertrophy", "fitmax", None),
    ("how much protein for lean bulk", "fitmax", None),
    ("whats a good deload week look like", "fitmax", None),
    ("creatine on rest days?", "fitmax", None),
    ("rpe 8 vs rpe 9 for squats", "fitmax", None),
    ("how do i calculate my tdee", "fitmax", None),
    ("is recomp possible as intermediate", "fitmax", None),
    ("best compound lifts for mass", "fitmax", None),
    ("how to bench more without shoulder pain", "fitmax", None),

    # hairmax
    ("how often should i apply minoxidil", "hairmax", None),
    ("does finasteride actually regrow hair", "hairmax", None),
    ("is dutasteride stronger than finas", "hairmax", None),
    ("ketoconazole shampoo how many times a week", "hairmax", None),
    ("my hairline is receding, what do i do", "hairmax", None),
    ("dht blockers worth it", "hairmax", None),
    ("dermaroller for hair growth schedule", "hairmax", None),
    ("scalp massage actually work for shedding?", "hairmax", None),
    ("nizoral side effects", "hairmax", None),
    ("hair density improving on rogaine how long", "hairmax", None),

    # bonemax
    ("what is mewing exactly", "bonemax", None),
    ("hard mewing vs soft mewing", "bonemax", None),
    ("how long until mastic gum changes jawline", "bonemax", None),
    ("tmj from chewing gum too hard", "bonemax", None),
    ("how to fix facial symmetry", "bonemax", None),
    ("mouth breathing affecting my maxilla?", "bonemax", None),
    ("falim gum daily safe?", "bonemax", None),
    ("neck training for jaw appearance", "bonemax", None),
    ("fascia release for jawline", "bonemax", None),
    ("chin tucks routine frequency", "bonemax", None),

    # heightmax
    ("spinal decompression actually help grow taller?", "heightmax", None),
    ("hanging bar daily reps", "heightmax", None),
    ("does sprinting release growth hormone", "heightmax", None),
    ("forward head posture fix", "heightmax", None),
    ("inversion table routine", "heightmax", None),
    ("kyphosis exercises", "heightmax", None),
    ("sleep posture for spine decompression", "heightmax", None),
    ("growth plate fused can i still grow", "heightmax", None),
    ("best stretches for height", "heightmax", None),
    ("lordosis correction plan", "heightmax", None),
]


def test_backtest_selector_accuracy_no_hints():
    """Pure NLP accuracy — no classifier hints, no active_maxx."""
    correct = 0
    wrong: list[tuple[str, str, str | None]] = []
    per_class: dict[str, dict[str, int]] = {}

    for query, expected, hints in BACKTEST_CASES:
        per_class.setdefault(expected, {"total": 0, "correct": 0})
        per_class[expected]["total"] += 1
        result = select_rag_system_prompt(query, maxx_hints=hints)
        if result.chosen_maxx == expected:
            correct += 1
            per_class[expected]["correct"] += 1
        else:
            wrong.append((query, expected, result.chosen_maxx))

    total = len(BACKTEST_CASES)
    accuracy = correct / total
    print(f"\n[rag_selector backtest] overall accuracy={accuracy:.1%}  ({correct}/{total})")
    for maxx, stats in sorted(per_class.items()):
        c = stats["correct"]; t = stats["total"]
        print(f"  {maxx:<10} {c}/{t}  ({c/t:.0%})")
    if wrong:
        print(f"  misses ({len(wrong)}):")
        for q, exp, got in wrong[:10]:
            print(f"    expected={exp:<9} got={str(got):<9}  {q!r}")

    # Keep the bar high but not brittle — 88% on hand-crafted queries is
    # well within the lexicon's power without requiring a learned model.
    assert accuracy >= 0.88, (
        f"selector accuracy {accuracy:.1%} below 88% floor; misses={wrong[:5]}"
    )


def test_backtest_with_classifier_hint_is_perfect():
    """When the classifier passes a single hint, accuracy must be 100%."""
    for query, expected, _ in BACKTEST_CASES:
        result = select_rag_system_prompt(query, maxx_hints=[expected])
        assert result.chosen_maxx == expected, (
            f"hinted selector returned {result.chosen_maxx} for {query!r}"
        )
