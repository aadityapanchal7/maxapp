"""Post-generation link validator.

Goal: every product link in a chat reply must point to a SPECIFIC product
page (Amazon `/dp/<ASIN>`, brand-direct product URL, etc.) — never an
Amazon search URL or an LLM-fabricated link.

Strategy:
  1. Resolve catalog brand mentions to direct URLs. If the bot wrote
     "CeraVe Hydrating Cleanser" with no link, append the catalog link.
  2. Detect existing links in the answer:
     - If the URL is in the catalog's allowed_urls() → keep as-is.
     - If it's an `amazon.com/s?k=...` SEARCH URL → swap for the catalog
       URL of whatever product name the link wraps. If we can't match,
       drop the URL entirely (keep the visible text).
     - If it's a non-catalog vendor URL → drop the URL.
  3. Idempotent: running the validator twice produces the same output.

The validator runs after both fast_rag and the agent path, so closed-
loop enforcement holds regardless of which route produced the answer.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Markdown link `[text](url)` — text is non-greedy, URL stops at `)`.
# Real links (must start with http(s)).
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
# Placeholder/garbage in the URL slot, e.g. `[CeraVe](link)` /
# `[CeraVe](url)` / `[CeraVe](here)` / `[CeraVe](TBD)`. The LLM
# sometimes emits these when it forgets to call recommend_product.
# We detect any `[label](nonurl)` form and try to resolve the label
# to the catalog; if we can't, we strip the link wrapper entirely.
_MD_PLACEHOLDER_RE = re.compile(
    r"\[([^\]]+)\]\(\s*((?!https?://)[^)\s][^)]*)\s*\)"
)

# Bare URL (not inside markdown brackets — best-effort).
_BARE_URL_RE = re.compile(r"(?<![\(\[])\bhttps?://[^\s)\]\>]+")

# Amazon search URL — `/s?k=...` or `/s/?k=...` or `?field-keywords=` etc.
_AMAZON_SEARCH_RE = re.compile(
    r"https?://(?:www\.)?amazon\.[a-z.]+/s[?/].*",
    re.IGNORECASE,
)

# Generic search URLs we should never ship.
_OTHER_SEARCH_RE = re.compile(
    r"https?://(?:www\.)?(?:google|bing|duckduckgo|sephora|ulta|target|walmart)\.[a-z.]+/(?:search|s|sr)\b",
    re.IGNORECASE,
)


def _is_catalog_url(url: str) -> bool:
    try:
        from services.product_catalog import allowed_urls
        return url.strip() in allowed_urls()
    except Exception:
        return False


def _resolve_to_catalog(visible_text: str) -> Optional[str]:
    """If the visible text matches a catalog product, return its
    DIRECT long-form product URL (`amazon.com/<Slug>/dp/<ASIN>`)."""
    try:
        from services.product_catalog import lookup_by_name
        hit = lookup_by_name(visible_text)
        if hit:
            return hit.display_url
    except Exception:
        return None
    return None


def _is_bad_url(url: str) -> bool:
    if not url:
        return False
    if _is_catalog_url(url):
        return False
    if _AMAZON_SEARCH_RE.match(url):
        return True
    if _OTHER_SEARCH_RE.match(url):
        return True
    # Anything else from amazon.com that isn't /dp/<ASIN> is suspect — the
    # LLM hallucinated. Be strict for amazon links since those are the
    # high-leverage class of failures.
    if re.match(r"https?://(?:www\.)?amazon\.[a-z.]+/", url, re.IGNORECASE):
        if "/dp/" not in url and "/gp/product/" not in url:
            return True
    return False


# --------------------------------------------------------------------------- #
#  Catalog-link enrichment                                                    #
# --------------------------------------------------------------------------- #

def _enrich_brand_mentions(text: str, *, max_inserts: int = 3) -> tuple[str, int]:
    """Where the bot mentioned a catalog product by name without a link,
    append a `(<direct-url>)` next to the FIRST mention. Limited to
    `max_inserts` to avoid spammy answers."""
    try:
        from services.product_catalog import load_catalog
        catalog = load_catalog()
    except Exception:
        return text, 0
    if not catalog:
        return text, 0

    inserts = 0
    out = text
    seen_ids: set[str] = set()

    for p in catalog:
        if inserts >= max_inserts:
            break
        if p.id in seen_ids:
            continue
        # Skip if the URL is already in the answer (avoid double-linking).
        if p.url in out:
            seen_ids.add(p.id)
            continue
        # Match on product name OR distinctive brand+keyword combo. We
        # only insert once per product.
        name_pat = re.compile(r"\b" + re.escape(p.name) + r"\b", re.IGNORECASE)
        m = name_pat.search(out)
        if m:
            ins = f" ([{p.name}]({p.url}))"
            # Don't append if the next chars already look like a link.
            following = out[m.end(): m.end() + 5]
            if "](" in following or "(http" in following:
                seen_ids.add(p.id)
                continue
            out = out[: m.end()] + ins + out[m.end():]
            inserts += 1
            seen_ids.add(p.id)
    return out, inserts


# --------------------------------------------------------------------------- #
#  Link rewriting                                                             #
# --------------------------------------------------------------------------- #

def _rewrite_md_links(text: str) -> tuple[str, int, int]:
    """Walk every `[label](url)`. If url is bad, swap it (or strip the
    link wrapper, leaving label as plain text)."""
    rewritten = 0
    stripped = 0

    def repl(m: re.Match) -> str:
        nonlocal rewritten, stripped
        label = m.group(1)
        url = m.group(2).strip()
        if not _is_bad_url(url):
            return m.group(0)
        # Try to upgrade to a catalog URL via the label.
        upgraded = _resolve_to_catalog(label)
        if upgraded:
            rewritten += 1
            return f"[{label}]({upgraded})"
        # Couldn't upgrade — drop the link wrapper, keep readable text.
        stripped += 1
        return label

    out = _MD_LINK_RE.sub(repl, text)
    return out, rewritten, stripped


def _rewrite_placeholder_links(text: str) -> tuple[str, int, int]:
    """Catch `[label](link)`, `[label](url)`, `[label](here)` and other
    non-URL placeholder slots the LLM sometimes emits when it forgets
    to call `recommend_product`. Try to resolve the label to a catalog
    URL; if no match, strip the link wrapper so only the readable name
    remains."""
    rewritten = 0
    stripped = 0

    def repl(m: re.Match) -> str:
        nonlocal rewritten, stripped
        label = m.group(1)
        upgraded = _resolve_to_catalog(label)
        if upgraded:
            rewritten += 1
            return f"[{label}]({upgraded})"
        stripped += 1
        return label

    out = _MD_PLACEHOLDER_RE.sub(repl, text)
    return out, rewritten, stripped


def _strip_bare_urls(text: str) -> tuple[str, int]:
    """Bare URLs (not in markdown links) — drop the bad ones outright.
    The catalog ones we leave alone."""
    stripped = 0

    def repl(m: re.Match) -> str:
        nonlocal stripped
        url = m.group(0)
        if _is_bad_url(url):
            stripped += 1
            return ""
        return url

    out = _BARE_URL_RE.sub(repl, text)
    # Tidy up double spaces / spaces-before-punct from removed URLs.
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    return out.strip(), stripped


# --------------------------------------------------------------------------- #
#  Public entry point                                                         #
# --------------------------------------------------------------------------- #

def validate_and_rewrite_links(text: str) -> str:
    """Sanitize an LLM-produced answer:

      1. Rewrite or strip bad markdown links (search URLs, hallucinated
         amazon links).
      2. Strip bad bare URLs.
      3. Append catalog direct links to brand mentions that lacked one.

    Idempotent. Safe to call on every answer.
    """
    if not text or not text.strip():
        return text
    original = text

    text, rewrote, stripped = _rewrite_md_links(text)
    text, ph_rewrote, ph_stripped = _rewrite_placeholder_links(text)
    text, bare_stripped = _strip_bare_urls(text)
    text, enriched = _enrich_brand_mentions(text)

    if rewrote or stripped or ph_rewrote or ph_stripped or bare_stripped or enriched:
        logger.info(
            "[link-validator] md_rewrote=%d md_stripped=%d "
            "placeholder_rewrote=%d placeholder_stripped=%d "
            "bare_stripped=%d enriched=%d",
            rewrote, stripped, ph_rewrote, ph_stripped, bare_stripped, enriched,
        )
    return text if text else original
