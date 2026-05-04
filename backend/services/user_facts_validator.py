"""Centralized constraint enforcement for user_facts.

This is the infra layer that catches "bot recommends chicken to a vegetarian"
class of failures. Three pieces:

  1. compute_forbidden_terms(facts)
     Deterministically maps a user_facts blob to a {term -> reason} dict.
     Categories handled: diet, allergies, dislikes, health (partial).

  2. find_violations(text, facts)
     Word-boundary scan of `text` for any forbidden term. Returns a list
     of (term, reason) tuples — empty when clean.

  3. enforce_against_facts(answer_fn, facts)
     Wraps an async answer-producing function. Runs it; if the output
     trips the validator, regenerates ONCE with an explicit corrective
     directive ("you mentioned chicken — the user is vegetarian; rewrite
     without it"). Best-effort: if the second pass also leaks, return
     it anyway with the violations logged so the caller can decide.

Why this matters: prompt-time injection ("don't suggest meat") is
necessary but not sufficient — instruction-following models still drift
when the retrieved evidence is meat-heavy. A deterministic post-check +
targeted regen is the only thing that actually closes the loop.

Adding a new constraint = adding a row to FORBIDDEN_TERMS. No per-site
plumbing required — every call site that uses `enforce_against_facts`
inherits the new check automatically.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Forbidden-term registry                                                    #
# --------------------------------------------------------------------------- #
# (fact_category, fact_value_substring) -> (forbidden_terms, human_reason)
#
# Match logic for the lookup key:
#   - case-insensitive substring match against the user's stored fact value
#   - first hit wins (so "no meat" → vegetarian rules)
#
# Forbidden terms are matched with word-boundary regex against the answer.
#
# Add a new entry here when you discover a new failure mode. DO NOT
# scatter ad-hoc filters across the codebase.

_VEGETARIAN_FORBIDDEN = (
    # Animal proteins — common names + a few specifics that show up in
    # nutrition / lifting docs.
    "chicken", "beef", "pork", "turkey", "lamb", "duck", "venison",
    "fish", "salmon", "tuna", "cod", "tilapia", "sardine", "sardines",
    "anchovy", "anchovies", "mackerel", "trout",
    "shrimp", "prawn", "prawns", "crab", "lobster", "scallop", "scallops",
    "mussel", "mussels", "oyster", "oysters", "clam", "clams", "squid", "octopus",
    "bacon", "ham", "sausage", "pepperoni", "prosciutto", "salami", "jerky",
    "meat", "steak", "ground beef", "ground turkey", "veal", "liver",
    "seafood", "shellfish", "poultry",
)

_VEGAN_FORBIDDEN = _VEGETARIAN_FORBIDDEN + (
    "egg", "eggs", "egg white", "egg whites", "yolk", "yolks",
    "milk", "yogurt", "greek yogurt", "cheese", "cottage cheese",
    "butter", "ghee", "cream", "ice cream", "whey", "casein", "honey",
)

_PESCATARIAN_FORBIDDEN = (
    "chicken", "beef", "pork", "turkey", "lamb", "duck", "venison",
    "bacon", "ham", "sausage", "pepperoni", "prosciutto", "salami", "jerky",
    "meat", "steak", "ground beef", "ground turkey", "veal", "liver",
    "poultry",
)

_NO_DAIRY_FORBIDDEN = (
    "milk", "yogurt", "greek yogurt", "cheese", "cottage cheese",
    "butter", "ghee", "cream", "ice cream", "whey", "casein",
)

_NO_GLUTEN_FORBIDDEN = (
    "wheat", "bread", "pasta", "spaghetti", "pizza", "bagel", "bagels",
    "couscous", "barley", "rye", "seitan",
)


# Each entry: (category, predicate(value) -> bool, forbidden_terms, reason)
_DIET_RULES: list[tuple[str, Callable[[str], bool], tuple[str, ...], str]] = [
    ("diet", lambda v: v in {"vegan"} or "vegan" in v,
     _VEGAN_FORBIDDEN, "user is vegan"),
    ("diet", lambda v: v in {"vegetarian", "no meat", "plant based", "plant-based"}
                       or "vegetarian" in v or "no meat" in v or "plant based" in v
                       or "plant-based" in v or "doesn't eat meat" in v
                       or "dont eat meat" in v,
     _VEGETARIAN_FORBIDDEN, "user is vegetarian / doesn't eat meat"),
    ("diet", lambda v: v == "pescatarian" or "pescatarian" in v,
     _PESCATARIAN_FORBIDDEN, "user is pescatarian (no land-animal meat)"),
    ("diet", lambda v: "no chicken" in v, ("chicken",), "user said no chicken"),
    ("diet", lambda v: "no fish" in v, ("fish", "salmon", "tuna", "shellfish", "seafood"),
     "user said no fish"),
    ("diet", lambda v: "no pork" in v, ("pork", "bacon", "ham", "sausage", "prosciutto"),
     "user said no pork"),
    ("diet", lambda v: "no beef" in v or "no red meat" in v,
     ("beef", "steak", "ground beef", "veal", "lamb"), "user said no red meat"),
    ("diet", lambda v: "no eggs" in v or v == "no egg",
     ("egg", "eggs", "egg white", "egg whites", "yolk", "yolks"), "user said no eggs"),
    ("diet", lambda v: "no dairy" in v or "lactose" in v or "dairy free" in v
                       or "dairy-free" in v,
     _NO_DAIRY_FORBIDDEN, "user avoids dairy"),
    ("diet", lambda v: "no gluten" in v or "gluten free" in v or "gluten-free" in v
                       or "gluten intolerant" in v or "celiac" in v,
     _NO_GLUTEN_FORBIDDEN, "user avoids gluten"),
]


# Allergy → forbidden terms. The allergen string itself is always
# forbidden; we add common variants when relevant.
_ALLERGY_VARIANTS: dict[str, tuple[str, ...]] = {
    "peanut":      ("peanut", "peanuts", "peanut butter"),
    "peanuts":     ("peanut", "peanuts", "peanut butter"),
    "tree nut":    ("almond", "almonds", "cashew", "cashews", "walnut", "walnuts",
                    "pecan", "pecans", "hazelnut", "hazelnuts", "pistachio", "pistachios"),
    "tree nuts":   ("almond", "almonds", "cashew", "cashews", "walnut", "walnuts",
                    "pecan", "pecans", "hazelnut", "hazelnuts", "pistachio", "pistachios"),
    "nuts":        ("almond", "almonds", "cashew", "cashews", "walnut", "walnuts",
                    "pecan", "pecans", "peanut", "peanuts", "pistachio", "pistachios"),
    "shellfish":   ("shrimp", "prawn", "crab", "lobster", "scallop", "mussel",
                    "oyster", "clam"),
    "soy":         ("soy", "soybean", "tofu", "tempeh", "edamame", "soy sauce"),
    "egg":         ("egg", "eggs", "egg white", "yolk"),
    "eggs":        ("egg", "eggs", "egg white", "yolk"),
    "dairy":       _NO_DAIRY_FORBIDDEN,
    "lactose":     _NO_DAIRY_FORBIDDEN,
    "gluten":      _NO_GLUTEN_FORBIDDEN,
    "fragrance":   ("fragrance", "perfume", "scented", "essential oil"),
    "sulfate":     ("sulfate", "sulfates", "sls", "sodium lauryl sulfate"),
    "sulfates":    ("sulfate", "sulfates", "sls", "sodium lauryl sulfate"),
    "niacinamide": ("niacinamide",),
    "tret":        ("tretinoin", "tret", "retin-a"),
    "retinol":     ("retinol", "retinoid", "tretinoin"),
}


# Health → forbidden recommendation terms. These are products / ingredients
# that the user should avoid given a condition.
_HEALTH_FORBIDDEN: list[tuple[str, tuple[str, ...], str]] = [
    ("eczema",   ("fragrance", "perfume", "alcohol-based", "sodium lauryl sulfate", "sls"),
     "user has eczema — avoid irritants"),
    ("rosacea",  ("fragrance", "menthol", "alcohol-based", "harsh exfoliant"),
     "user has rosacea — avoid irritants"),
    ("on accutane", ("strong retinol", "harsh exfoliant", "glycolic acid", "salicylic acid"),
     "user is on accutane — skip strong actives"),
]


def compute_forbidden_terms(facts: Optional[dict[str, Any]]) -> dict[str, str]:
    """Map user_facts to {forbidden_term: reason_string}.

    Returns an empty dict when no constraints apply. Terms are lowercase.
    """
    if not facts:
        return {}
    forbidden: dict[str, str] = {}

    def _add(term: str, reason: str) -> None:
        t = term.strip().lower()
        if t and t not in forbidden:
            forbidden[t] = reason

    # Diet.
    for v in (facts.get("diet") or []):
        vs = str(v).lower().strip()
        for cat, pred, terms, reason in _DIET_RULES:
            try:
                if pred(vs):
                    for t in terms:
                        _add(t, reason)
                    break  # first matching diet rule wins
            except Exception:
                continue

    # Allergies — always forbid the raw allergen + known variants.
    for v in (facts.get("allergies") or []):
        vs = str(v).lower().strip()
        if not vs:
            continue
        _add(vs, f"user is allergic / sensitive to {vs}")
        for key, variants in _ALLERGY_VARIANTS.items():
            if key in vs:
                for t in variants:
                    _add(t, f"user is allergic / sensitive to {vs}")

    # Dislikes — soft-forbid (still flagged, treated same as hard for now).
    for v in (facts.get("dislikes") or []):
        vs = str(v).lower().strip()
        if vs:
            _add(vs, f"user said they avoid {vs}")

    # Health-driven product avoidance.
    health_list = facts.get("health") or []
    for v in health_list:
        vs = str(v).lower().strip()
        for cond, terms, reason in _HEALTH_FORBIDDEN:
            if cond in vs:
                for t in terms:
                    _add(t, reason)

    return forbidden


# --------------------------------------------------------------------------- #
#  Output validation                                                          #
# --------------------------------------------------------------------------- #

def _term_pattern(term: str) -> re.Pattern[str]:
    """Build a word-boundary regex for `term`. Multi-word phrases use \\s+
    between tokens to tolerate variable whitespace."""
    parts = [re.escape(p) for p in term.split() if p]
    if not parts:
        return re.compile(r"$^")  # never matches
    body = r"\s+".join(parts)
    # Use lookarounds rather than \b so we work inside punctuation like
    # "chicken,fish" or "chicken/fish".
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])", re.IGNORECASE)


def find_violations(
    text: str, facts: Optional[dict[str, Any]]
) -> list[tuple[str, str]]:
    """Return [(term, reason), ...] for every forbidden term that appears
    in `text`. Empty list = clean. Each term reported at most once even
    if it occurs multiple times."""
    if not text or not facts:
        return []
    forbidden = compute_forbidden_terms(facts)
    if not forbidden:
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for term, reason in forbidden.items():
        if term in seen:
            continue
        if _term_pattern(term).search(text):
            out.append((term, reason))
            seen.add(term)
    return out


def format_violation_directive(violations: list[tuple[str, str]]) -> str:
    """Produce a corrective directive to feed back to the LLM.

    Lists each violated term + reason, then tells the model exactly what
    to do. Designed to be appended to the original human message on the
    regen pass."""
    if not violations:
        return ""
    lines = ["You just produced an answer that VIOLATES the user's stated rules:"]
    for term, reason in violations:
        lines.append(f"  • mentioned '{term}' — but {reason}")
    lines.append(
        "Rewrite the answer WITHOUT any of those terms. Use the SUBSTITUTION "
        "GUIDE — pick concrete alternatives. Do not apologize, do not "
        "explain the rule, just produce the corrected answer."
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  Enforcement wrapper                                                        #
# --------------------------------------------------------------------------- #

async def enforce_against_facts(
    *,
    facts: Optional[dict[str, Any]],
    initial_answer: str,
    regen: Callable[[str], Awaitable[str]],
    max_attempts: int = 1,
) -> str:
    """Validate `initial_answer` against `facts`. If it violates a
    constraint, call `regen(corrective_directive)` to produce a new
    answer. Repeat up to `max_attempts` times.

    Args:
      facts:           user_facts blob (may be None / empty).
      initial_answer:  the model's first draft.
      regen:           async function that takes a corrective directive
                       string and returns a new answer.
      max_attempts:    how many regen cycles to allow (default 1 — one
                       extra round-trip on violation).

    Returns the cleanest answer produced. Logs unresolved violations so
    they show up in observability without crashing the turn.
    """
    if not facts or not initial_answer:
        return initial_answer
    answer = initial_answer
    attempt = 0
    while attempt < max_attempts:
        violations = find_violations(answer, facts)
        if not violations:
            return answer
        attempt += 1
        directive = format_violation_directive(violations)
        logger.info(
            "[facts-validator] attempt=%d violations=%s; regenerating",
            attempt, [v[0] for v in violations],
        )
        try:
            new_answer = await regen(directive)
        except Exception as e:
            logger.warning("[facts-validator] regen failed: %s", e)
            return answer
        if new_answer and new_answer.strip():
            answer = new_answer
        else:
            return answer
    # Final check after last regen.
    final_violations = find_violations(answer, facts)
    if final_violations:
        logger.warning(
            "[facts-validator] UNRESOLVED violations after %d attempts: %s",
            max_attempts, [v[0] for v in final_violations],
        )
    return answer
