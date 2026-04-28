"""Pick the best system prompt + module-specific reference for a KNOWLEDGE turn.

Inputs per call:
    - the user's message
    - maxx_hints from classify_turn (may be empty)
    - the user's active_maxx (fallback when hints are empty)

Output:
    - a single system prompt string (base `rag_answer_system` plus the chosen
      `{maxx_id}_coaching_reference`, when one matches)
    - the chosen maxx (or None if the message isn't domain-specific)
    - a short human-readable reason string, for telemetry

Selection strategy (cheap NLP, no external model calls):
    1. If `maxx_hints` has exactly one entry, trust it.
    2. If `maxx_hints` has multiple, score each against the message lexicon
       and pick the winner.
    3. If hints are empty: score ALL five modules' lexicons against the
       message tokens; pick the top one IF its score clears a floor,
       otherwise fall back to `active_maxx` (soft signal) or None (module-agnostic).

The lexicons are hand-curated from the `{maxx_id}_coaching_reference` prompts
currently in Supabase. Keep them narrow and authoritative — false positives
are worse than no match (wrong reference drags the answer sideways).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from services.prompt_constants import RAG_ANSWER_SYSTEM_PROMPT
from services.prompt_loader import PromptKey, resolve_prompt

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Module lexicons                                                             #
# --------------------------------------------------------------------------- #

# Keywords are lowercase. Multi-word phrases are matched as substrings; single
# tokens must match whole words (word-boundary). Weight: strong = 3, medium = 2,
# weak = 1. Only include tokens that are *unambiguously* tied to one module.

_LEXICONS: dict[str, dict[str, int]] = {
    "skinmax": {
        # products / ingredients
        "acne": 3, "adapalene": 3, "tretinoin": 3, "retinol": 3, "retinoid": 3,
        "salicylic": 3, "benzoyl": 3, "azelaic": 3, "niacinamide": 3, "cerave": 2,
        "cetaphil": 2, "spf": 3, "sunscreen": 3, "moisturizer": 2, "cleanser": 2,
        # concerns (include plurals)
        "breakout": 3, "breakouts": 3, "pimple": 3, "pimples": 3,
        "blackhead": 3, "blackheads": 3, "whitehead": 3, "whiteheads": 3,
        "blemish": 2, "blemishes": 2, "pore": 2, "pores": 2,
        "pigmentation": 2, "dark spot": 2, "melasma": 3, "rosacea": 3,
        "redness": 2, "dermatitis": 3,
        # debloat / puffy face concerns (high signal, often short queries)
        "debloat": 3, "debloating": 3, "bloat": 3, "bloated": 3,
        "puffy": 3, "puffiness": 3, "puffy face": 3, "face bloat": 3,
        "water retention": 3, "lymphatic": 2, "gua sha": 3, "ice roller": 3,
        # routines
        "skincare": 3, "skin routine": 3, "am routine": 2, "pm routine": 2,
        "exfoliate": 2, "exfoliation": 2,
        "dermaroll": 3, "dermarolls": 3, "dermarolling": 3, "microneedling": 3,
        "hydration": 1, "double cleanse": 3,
        # community slang
        "skinmaxxing": 3, "glowmax": 2, "glow up": 2,
    },
    "fitmax": {
        # training — keep generic words (pull/push/reps) low-weight so stretch
        # + mewing queries don't get mis-routed to fitmax
        "workout": 2, "workouts": 2, "training": 2, "split": 3, "hypertrophy": 3,
        "strength": 2, "deadlift": 3, "deadlifts": 3,
        "bench": 3, "bench press": 3, "squat": 2, "squats": 2, "ohp": 3,
        "rpe": 3, "volume": 2, "progressive overload": 3,
        "warmup": 2, "deload": 3, "compound lift": 3, "compound lifts": 3,
        # nutrition
        "macro": 3, "macros": 3, "protein": 2, "carbs": 2, "fats": 2,
        "calories": 3, "cut": 2, "cutting": 3, "bulk": 3, "bulking": 3,
        "recomp": 3, "maintenance": 2, "deficit": 3, "surplus": 3, "tdee": 3,
        "creatine": 3, "whey": 3, "supplement": 2, "supplements": 2,
        # body
        "body fat": 3, "bodyfat": 3, "lean": 2, "gains": 2, "gainz": 2,
        "gym": 2, "lift": 2, "lifts": 2, "lifting": 2,
        # community
        "fitmaxxing": 3, "leanmax": 3, "leanmaxxing": 3,
    },
    "hairmax": {
        # products / ingredients
        "minoxidil": 3, "finasteride": 3, "finas": 3, "fin": 1, "dutasteride": 3,
        "ketoconazole": 3, "nizoral": 3, "rogaine": 3, "propecia": 3,
        "dermaroller": 2, "hair dermaroll": 3, "microneedle scalp": 3,
        # concerns
        "hairline": 3, "receding": 3, "thinning": 3, "bald": 2, "balding": 3,
        "hair loss": 3, "shedding": 3, "hair shed": 3, "dht": 3, "alopecia": 3,
        "norwood": 3, "nw1": 3, "nw2": 3, "nw3": 3, "nw4": 3, "nw5": 3,
        "crown": 1, "widow": 2, "hair density": 3, "hair growth": 3,
        # routines
        "wash day": 2, "scalp massage": 3, "shampoo": 2, "conditioner": 2,
        "scalp": 2, "hair": 1, "hair care": 3,
        # community
        "hairmaxxing": 3, "hairmaxx": 3,
    },
    "bonemax": {
        # practices
        "mewing": 3, "hard mewing": 3, "soft mewing": 3, "tongue posture": 3,
        "masseter": 3, "mastic": 3, "mastic gum": 3, "falim": 3,
        "chewing": 2, "jaw exercise": 3, "jaw exercises": 3,
        # bonesmashing / community-named protocols (high signal — these queries
        # were previously routing to "no module" because nothing matched)
        "bonesmash": 3, "bonesmashing": 3, "bone smash": 3, "bone smashing": 3,
        "bonemashing": 3, "skull smashing": 3, "looksmax": 3, "looksmaxx": 3,
        "looksmaxxing": 3, "facemax": 3, "facemaxxing": 3, "bonemaxxing": 3,
        "psl": 2, "mog": 1, "mogger": 1,
        # anatomy / concerns
        "jaw": 2, "jawline": 3, "tmj": 3, "maxilla": 3, "mandible": 3,
        "palate": 3, "zygomatic": 3, "gonion": 3, "gonial": 3,
        "bite force": 3, "bite": 1,
        "face width": 3, "facial symmetry": 3, "symmetry": 2,
        "nasal breathing": 3, "mouth breath": 3, "mouth breathing": 3,
        "fascia": 3, "lymph drainage": 2, "neck training": 3,
        "chin tuck": 2, "chin tucks": 2,
    },
    "heightmax": {
        # practices
        "decompression": 3, "decompress": 3, "spinal decompression": 3,
        "hang": 2, "hanging": 3, "pullup bar": 3,
        "inversion": 3, "sprint": 2, "sprints": 2, "hgh": 3, "gh sleep": 3,
        "growth hormone": 3,
        # posture
        "posture": 3, "slouch": 2, "slouching": 2, "forward head": 3,
        "kyphosis": 3, "lordosis": 3, "spine": 2, "spinal": 2, "vertebral": 3,
        # height concerns
        "height": 3, "taller": 3, "grow taller": 3, "growth plate": 3,
        "epiphyseal": 3, "stretching": 1, "stretch routine": 2,
        # community
        "heightmaxxing": 3, "heightmax": 3, "heightmaxx": 3,
    },
}

_ALL_MAXXES = tuple(_LEXICONS.keys())

# Minimum absolute score (sum of keyword weights) to trust a lexicon match
# without an explicit hint. Too low → noisy prompt; too high → never matches.
_SCORE_FLOOR = 3

# How much the top module must beat #2 by to be trusted (prevents noise when
# the message mentions two modules equally).
_SCORE_MARGIN = 1


def _word_boundary_count(text: str, token: str) -> int:
    """Count occurrences of `token` as a whole word (or phrase) in `text`."""
    if " " in token:
        # Multi-word phrase — substring match is fine.
        return text.count(token)
    return len(re.findall(r"\b" + re.escape(token) + r"\b", text))


def _score_message(text_lower: str, lexicon: dict[str, int]) -> int:
    score = 0
    for token, weight in lexicon.items():
        hits = _word_boundary_count(text_lower, token)
        if hits:
            score += weight * hits
    return score


# --------------------------------------------------------------------------- #
#  Public API                                                                  #
# --------------------------------------------------------------------------- #

@dataclass
class SelectedRagPrompt:
    system_prompt: str
    chosen_maxx: Optional[str]
    reason: str
    score: int = 0
    runner_up_score: int = 0


def _protocol_reference_key(maxx: str) -> str:
    """Preferred KNOWLEDGE-path reference: tells the LLM what's in scope and
    what generic-wellness fluff to avoid. See prompt_constants.{MAXX}_PROTOCOL_REFERENCE."""
    return f"{maxx}_protocol_reference"


def _coaching_reference_key(maxx: str) -> str:
    """Legacy reference key — contains NOTIFICATION TIMING rules, not protocol.
    Kept as a fallback so the selector still attaches *something* when the new
    protocol_reference rows haven't been seeded into Supabase yet."""
    return f"{maxx}_coaching_reference"


def _load_base_system() -> str:
    return resolve_prompt(PromptKey.RAG_ANSWER_SYSTEM, RAG_ANSWER_SYSTEM_PROMPT)


def _load_reference(maxx: str) -> Optional[str]:
    # Prefer the new protocol-reference (KNOWLEDGE-scoped). Fall through to
    # the legacy coaching-reference (notification-timing) if not yet seeded.
    protocol = resolve_prompt(_protocol_reference_key(maxx), "")
    if protocol:
        return protocol
    coaching = resolve_prompt(_coaching_reference_key(maxx), "")
    return coaching or None


def select_rag_system_prompt(
    message: str,
    *,
    maxx_hints: Optional[list[str]] = None,
    active_maxx: Optional[str] = None,
) -> SelectedRagPrompt:
    """Return the system prompt (base + optional module reference) for a KNOWLEDGE turn."""
    base = _load_base_system()
    text_lower = (message or "").lower()
    hints = [h for h in (maxx_hints or []) if h in _ALL_MAXXES]

    # ---- Path 1: single hint from the classifier — trust it
    if len(hints) == 1:
        chosen = hints[0]
        score = _score_message(text_lower, _LEXICONS[chosen])
        return _build_result(base, chosen, score=score, runner_up=0,
                             reason=f"classifier hint={chosen}")

    # ---- Path 2: multiple hints — score to break the tie
    if len(hints) > 1:
        ranked = sorted(
            ((h, _score_message(text_lower, _LEXICONS[h])) for h in hints),
            key=lambda kv: kv[1],
            reverse=True,
        )
        top_maxx, top_score = ranked[0]
        runner_up_score = ranked[1][1] if len(ranked) > 1 else 0
        return _build_result(
            base, top_maxx, score=top_score, runner_up=runner_up_score,
            reason=f"tiebreak between hints={hints} -> {top_maxx}",
        )

    # ---- Path 3: no hints — free-for-all lexicon match
    ranked_all = sorted(
        ((m, _score_message(text_lower, _LEXICONS[m])) for m in _ALL_MAXXES),
        key=lambda kv: kv[1],
        reverse=True,
    )
    top_maxx, top_score = ranked_all[0]
    runner_up_score = ranked_all[1][1] if len(ranked_all) > 1 else 0

    if top_score >= _SCORE_FLOOR and (top_score - runner_up_score) >= _SCORE_MARGIN:
        return _build_result(
            base, top_maxx, score=top_score, runner_up=runner_up_score,
            reason=f"lexicon winner={top_maxx} score={top_score}",
        )

    # ---- Path 4: soft fallback — use active_maxx if we have one
    if active_maxx and active_maxx in _ALL_MAXXES:
        return _build_result(
            base, active_maxx, score=top_score, runner_up=runner_up_score,
            reason=f"fallback active_maxx={active_maxx}",
        )

    # ---- Path 5: give up, module-agnostic base prompt
    return SelectedRagPrompt(
        system_prompt=base, chosen_maxx=None,
        reason="no match — generic base prompt",
        score=top_score, runner_up_score=runner_up_score,
    )


def _build_result(
    base: str,
    maxx: str,
    *,
    score: int,
    runner_up: int,
    reason: str,
) -> SelectedRagPrompt:
    reference = _load_reference(maxx)
    if not reference:
        # Prompt row missing from Supabase — still return the module selection
        # so telemetry/retrieval knows which maxx we think this is.
        return SelectedRagPrompt(
            system_prompt=base, chosen_maxx=maxx,
            reason=f"{reason} (reference prompt missing from cache)",
            score=score, runner_up_score=runner_up,
        )
    system_text = base.rstrip() + "\n\n## MODULE REFERENCE:\n" + reference.strip() + "\n"
    return SelectedRagPrompt(
        system_prompt=system_text, chosen_maxx=maxx,
        reason=reason, score=score, runner_up_score=runner_up,
    )
