"""Curated product catalog — single source of truth for recommendations.

Two design rules drive everything in this module:

  1. **Direct product URLs only.** The catalog stores `https://amazon.com/dp/<ASIN>`
     style links (or the brand's product page). No search URLs. The LLM
     gets these strings handed to it pre-filtered; it doesn't construct
     them. The downstream link validator rejects any URL that isn't in
     `allowed_urls()`.

  2. **Fact-aware filtering at the catalog layer.** Each product carries
     a `tags` dict (`vegan`, `vegetarian`, `fragrance_free`, etc.). The
     filter takes the user's `user_facts` blob and drops products whose
     tags say they conflict — a vegan user never sees whey, a fragrance-
     allergic user never sees Anthelios. This complements the post-hoc
     `user_facts_validator` (which catches free-form mentions); together
     the two layers make a closed loop.

API:
  load_catalog()                 → list[Product] (cached on first call)
  find_products(module, concerns, user_facts, limit) → list[Product]
  format_for_prompt(products)    → str (markdown bullets, ready to inject)
  allowed_urls()                 → set[str]
  reload()                       → drop the cache (useful in dev)

Storage: `backend/data/product_catalog.yaml`. To add a product, edit the
YAML and ensure it follows the schema documented in the file header.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


_CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "product_catalog.yaml",
)


# --------------------------------------------------------------------------- #
#  Data class                                                                 #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Product:
    id: str
    name: str
    brand: str
    module: str
    concerns: tuple[str, ...]
    url: str
    price_tier: str
    tags: dict[str, Optional[bool]]
    rationale: str
    references: tuple[str, ...]

    def to_markdown_bullet(self, max_rationale_chars: int = 100) -> str:
        rationale = self.rationale or ""
        if len(rationale) > max_rationale_chars:
            rationale = rationale[: max_rationale_chars - 1].rstrip() + "…"
        sep = " — " if rationale else ""
        return f"- [{self.name}]({self.url}){sep}{rationale}"


# --------------------------------------------------------------------------- #
#  Loader                                                                     #
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def load_catalog() -> tuple[Product, ...]:
    """Load the YAML catalog once per process. Returns a tuple of
    Product. Empty tuple on read/parse failure (the bot still works,
    just without catalog-backed recommendations)."""
    try:
        import yaml  # PyYAML — already a dependency
    except Exception as e:
        logger.warning("[catalog] yaml import failed: %s", e)
        return ()
    try:
        with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("[catalog] file not found: %s", _CATALOG_PATH)
        return ()
    except Exception as e:
        logger.warning("[catalog] load failed: %s", e)
        return ()

    items = raw.get("products") or []
    out: list[Product] = []
    for i, entry in enumerate(items):
        try:
            out.append(Product(
                id=str(entry["id"]).strip(),
                name=str(entry["name"]).strip(),
                brand=str(entry.get("brand") or "").strip(),
                module=str(entry.get("module") or "general").strip().lower(),
                concerns=tuple(str(c).strip().lower() for c in (entry.get("concerns") or [])),
                url=str(entry["url"]).strip(),
                price_tier=str(entry.get("price_tier") or "mid").strip().lower(),
                tags={str(k): _coerce_tag(v) for k, v in (entry.get("tags") or {}).items()},
                rationale=str(entry.get("rationale") or "").strip(),
                references=tuple(str(r).strip() for r in (entry.get("references") or [])),
            ))
        except Exception as e:
            logger.warning("[catalog] entry #%d skipped (%s): %s", i, e, entry.get("id"))
    logger.info("[catalog] loaded %d products from %s", len(out), _CATALOG_PATH)
    return tuple(out)


def reload() -> None:
    """Drop the cache so the next `load_catalog()` re-reads the YAML."""
    load_catalog.cache_clear()


def _coerce_tag(v: Any) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "yes", "y", "1"):
        return True
    if s in ("false", "no", "n", "0"):
        return False
    return None


# --------------------------------------------------------------------------- #
#  Fact-aware filter                                                          #
# --------------------------------------------------------------------------- #

# Maps a user_facts diet/health/allergy entry to a list of (tag_name,
# required_value) pairs. If ANY of those fail, the product is dropped.
# `required_value=True` means the product's tag must be True (e.g.
# fragrance_free=True for fragrance-allergic users).
_FACT_TO_TAG_REQUIREMENTS: list[tuple[str, str, list[tuple[str, bool]]]] = [
    # category, fact-substring, required tags
    ("diet", "vegan",         [("vegan", True)]),
    ("diet", "vegetarian",    [("vegetarian", True)]),
    ("diet", "no meat",       [("vegetarian", True)]),
    ("diet", "plant",         [("vegetarian", True)]),
    ("diet", "no dairy",      [("dairy_free", True)]),
    ("diet", "lactose",       [("dairy_free", True)]),
    ("diet", "no gluten",     [("gluten_free", True)]),
    ("diet", "celiac",        [("gluten_free", True)]),
    ("allergies", "fragrance",[("fragrance_free", True)]),
    ("allergies", "perfume",  [("fragrance_free", True)]),
    ("allergies", "sulfate",  [("sulfate_free", True)]),
    ("allergies", "sls",      [("sulfate_free", True)]),
    ("allergies", "gluten",   [("gluten_free", True)]),
    ("allergies", "dairy",    [("dairy_free", True)]),
    ("allergies", "lactose",  [("dairy_free", True)]),
    # Health-driven sensitivity → only show fragrance-free.
    ("health",    "eczema",   [("fragrance_free", True)]),
    ("health",    "rosacea",  [("fragrance_free", True)]),
]


def _passes_user_facts(p: Product, user_facts: Optional[dict]) -> bool:
    """Return False if the product's tags say it conflicts with a fact."""
    if not user_facts:
        return True
    for category, substr, required in _FACT_TO_TAG_REQUIREMENTS:
        values = user_facts.get(category) or []
        if not isinstance(values, list):
            continue
        if not any(substr in str(v).lower() for v in values):
            continue
        # The user has this fact — enforce the required tag values.
        for tag_name, required_value in required:
            tag_val = p.tags.get(tag_name)
            # `None` means we don't know — be conservative and drop the
            # product when a hard constraint is at stake. Users with
            # explicit "vegan" / "fragrance allergy" benefit from the
            # caution; the catalog editor should set tags explicitly.
            if tag_val is None or tag_val != required_value:
                return False
    return True


# --------------------------------------------------------------------------- #
#  Search                                                                     #
# --------------------------------------------------------------------------- #

def find_products(
    *,
    module: Optional[str] = None,
    concerns: Optional[Iterable[str]] = None,
    user_facts: Optional[dict] = None,
    limit: int = 3,
    price_tier: Optional[str] = None,
) -> list[Product]:
    """Return up to `limit` products matching `module` and `concerns`,
    after filtering through `user_facts`. Ranked by concern-overlap then
    price tier (budget first when tied — accessible defaults).

    All args are optional. Calling with nothing returns up to `limit`
    catalog products in stable order (useful for "show me anything").
    """
    catalog = load_catalog()
    if not catalog:
        return []

    target_module = (module or "").strip().lower() or None
    concern_set = {c.strip().lower() for c in (concerns or []) if c}

    scored: list[tuple[int, int, Product]] = []  # (overlap, tier_priority, p)
    tier_priority = {"budget": 0, "mid": 1, "premium": 2}

    for p in catalog:
        if target_module and p.module != target_module and p.module != "general":
            continue
        if not _passes_user_facts(p, user_facts):
            continue
        overlap = len(concern_set & set(p.concerns)) if concern_set else 0
        # When concerns are given but nothing overlaps, skip — better to
        # return [] than off-topic product.
        if concern_set and overlap == 0:
            continue
        if price_tier and p.price_tier != price_tier.strip().lower():
            continue
        scored.append((overlap, tier_priority.get(p.price_tier, 1), p))

    # Higher overlap first; break ties with cheaper-first.
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [p for _, _, p in scored[:limit]]


# --------------------------------------------------------------------------- #
#  Prompt formatting                                                          #
# --------------------------------------------------------------------------- #

def format_for_prompt(
    products: list[Product],
    *,
    header: str = "## CATALOG-VETTED PRODUCTS (use these EXACT links — do not invent URLs)",
) -> str:
    """Render products as a markdown block ready to inject into an LLM
    prompt. Returns "" when the list is empty."""
    if not products:
        return ""
    lines = [p.to_markdown_bullet() for p in products]
    return f"{header}\n" + "\n".join(lines)


def format_brief(products: list[Product]) -> str:
    """One-line summary for inclusion in tool outputs / logs."""
    if not products:
        return "(no catalog products matched)"
    return ", ".join(f"{p.name} [{p.price_tier}]" for p in products)


# --------------------------------------------------------------------------- #
#  Validator helpers                                                          #
# --------------------------------------------------------------------------- #

def allowed_urls() -> set[str]:
    """Set of URLs the link validator considers safe."""
    return {p.url for p in load_catalog()}


def lookup_by_brand_and_name(brand: str, name_substr: str) -> Optional[Product]:
    """Find the catalog entry whose brand matches (case-insensitive) and
    whose name contains `name_substr`. Used by the link rewriter to
    upgrade a brand mention into a direct URL."""
    if not brand or not name_substr:
        return None
    b = brand.strip().lower()
    n = name_substr.strip().lower()
    for p in load_catalog():
        if p.brand.lower() == b and n in p.name.lower():
            return p
    return None


_TOKEN_RE = __import__("re").compile(r"[a-z0-9%+]+")


def _tokens(s: str) -> set[str]:
    """Lowercase alphanumeric tokens, dropping common stopwords that
    cause spurious matches. We keep '%' and '+' as part of tokens so
    "10%" and "B5" survive."""
    drop = {"the", "for", "and", "with", "a", "an", "of"}
    return {t for t in _TOKEN_RE.findall(s.lower()) if t not in drop}


def lookup_by_name(name_substr: str, *, min_overlap: int = 2) -> Optional[Product]:
    """Token-overlap matcher.

    Picks the catalog entry with the largest token overlap with the
    input, requiring at least `min_overlap` shared tokens (so "CeraVe
    Hydrating Cleanser" matches "CeraVe Hydrating Facial Cleanser" via
    {cerave, hydrating, cleanser}).

    Returns None when nothing crosses the threshold — the caller should
    fall back to a search URL in that case.
    """
    if not name_substr:
        return None
    target = _tokens(name_substr)
    if len(target) < min_overlap:
        return None
    best: Optional[tuple[int, Product]] = None
    for p in load_catalog():
        overlap = len(target & _tokens(p.name))
        if overlap < min_overlap:
            continue
        if best is None or overlap > best[0]:
            best = (overlap, p)
    return best[1] if best else None
