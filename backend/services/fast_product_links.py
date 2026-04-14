"""Lightweight product-link resolver for current module docs.

Returns Amazon search links for products explicitly present in module reference
files or retrieved evidence. This avoids forcing the full agent path for simple
"give me links" turns.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import quote_plus

from services.rag_service import retrieve_chunks

logger = logging.getLogger(__name__)

_SERVICES_DIR = Path(__file__).resolve().parent
_REFERENCE_FILES = {
    "skinmax": _SERVICES_DIR / "skinmax_notification_engine_reference.md",
    "hairmax": _SERVICES_DIR / "hairmax_notification_engine_reference.md",
    "bonemax": _SERVICES_DIR / "bonemax_notification_engine_reference.md",
    "heightmax": _SERVICES_DIR / "heightmax_notification_engine_reference.md",
    "fitmax": _SERVICES_DIR / "fitmax_notification_engine_reference.md",
}

_CURATED_PRODUCTS = {
    "skinmax": [
        "CeraVe Foaming Facial Cleanser",
        "CeraVe Hydrating Cleanser",
        "CeraVe PM Facial Moisturizing Lotion",
        "CeraVe Moisturizing Cream",
        "CeraVe Daily Moisturizing Lotion",
        "Paula's Choice 2% BHA Liquid Exfoliant",
        "EltaMD UV Clear SPF 46",
        "EltaMD UV Physical SPF 41",
        "La Roche-Posay Toleriane Gentle Cleanser",
        "La Roche-Posay Toleriane Hydrating Cleanser",
        "La Roche-Posay Anthelios SPF 50+",
        "La Roche-Posay Cicaplast Baume B5",
        "The Ordinary Azelaic Acid 10%",
        "The Ordinary Niacinamide 10% + Zinc 1%",
        "The Ordinary Alpha Arbutin 2%",
        "The Ordinary Hyaluronic Acid 2% + B5",
        "The Ordinary Glycolic Acid 7% Toning Solution",
        "The Ordinary AHA 30% + BHA 2% Peeling Solution",
        "Differin Adapalene 0.1%",
        "SkinCeuticals CE Ferulic",
        "Dr. Jart+ Ceramidin Cream",
    ],
    "hairmax": [
        "Minoxidil",
        "Finasteride",
        "Topical Finasteride",
        "Hims topical fin/min combo",
        "Ketoconazole Shampoo",
        "Nizoral",
        "Dermaroller",
    ],
}

_CURATED_BRANDS = {
    "skinmax": [
        "CeraVe",
        "Paula's Choice",
        "EltaMD",
        "La Roche-Posay",
        "The Ordinary",
        "Differin",
        "SkinCeuticals",
        "Dr. Jart+",
    ],
    "hairmax": [
        "Rogaine",
        "Hims",
        "Keeps",
        "Nizoral",
    ],
}

_PRODUCT_ALIASES = {
    "Paula's Choice 2% BHA Liquid Exfoliant": ["paulas choice bha", "paula's choice bha", "paulas choice"],
    "EltaMD UV Clear SPF 46": ["elta md", "eltamd", "elta md uv clear"],
    "EltaMD UV Physical SPF 41": ["elta md physical", "eltamd physical"],
    "La Roche-Posay Toleriane Gentle Cleanser": ["la roche posay toleriane", "la roche posay cleanser"],
    "La Roche-Posay Toleriane Hydrating Cleanser": ["la roche posay hydrating cleanser"],
    "La Roche-Posay Anthelios SPF 50+": ["la roche posay anthelios", "anthelios spf"],
    "CeraVe Foaming Facial Cleanser": ["cerave foaming cleanser", "cerave cleanser"],
}

_PRODUCT_PATTERN = re.compile(
    r"\b(?:[A-Z][a-zA-Z0-9+%.'/-]*)(?:\s+[A-Z0-9][a-zA-Z0-9+%.'/-]*){0,5}\b"
)
_BLOCKLIST = {
    "AM", "PM", "PM Routine", "AM Routine", "Skin Type", "Primary Concern",
    "Secondary Concern", "Midday Tip", "Hydration Check", "Retinoid Night",
    "Rest Night", "Weekly Exfoliation", "Monthly Progress Photo", "Monthly Routine Check-in",
    "BoneMax", "HeightMax", "HairMax", "Skinmax", "FitMax", "The", "Use", "Wake Time",
    "Combining", "Daily", "Bloodwork", "Real Talk", "Dermarolling",
}

_PRODUCT_CACHE: dict[str, list[str]] = {}


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _norm_tokens(s: str) -> list[str]:
    return [tok for tok in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(tok) >= 3]


def _extract_products(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in _PRODUCT_PATTERN.findall(text or ""):
        name = match.strip(" -:;,.()[]")
        if len(name) < 4 or name in _BLOCKLIST:
            continue
        if not re.search(r"[A-Z]", name):
            continue
        key = _normalize(name)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _module_products(maxx_id: str) -> list[str]:
    cached = _PRODUCT_CACHE.get(maxx_id)
    if cached is not None:
        return cached
    ref = _REFERENCE_FILES.get(maxx_id)
    if not ref or not ref.exists():
        _PRODUCT_CACHE[maxx_id] = []
        return []
    try:
        text = ref.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("product link ref read failed for %s: %s", maxx_id, e)
        _PRODUCT_CACHE[maxx_id] = []
        return []
    products = list(_CURATED_PRODUCTS.get(maxx_id, []))
    products.extend(_extract_products(text))
    _PRODUCT_CACHE[maxx_id] = products
    return products


def _amazon_search_url(name: str) -> str:
    return f"https://www.amazon.com/s?k={quote_plus(name)}"


def _brand_name(product_name: str) -> str:
    aliases = (
        ("paulaschoice", "Paula's Choice"),
        ("eltamd", "EltaMD"),
        ("larocheposay", "La Roche-Posay"),
        ("cerave", "CeraVe"),
        ("theordinary", "The Ordinary"),
        ("drjart", "Dr. Jart+"),
        ("skinceuticals", "SkinCeuticals"),
        ("hims", "Hims"),
        ("nizoral", "Nizoral"),
        ("rogaine", "Rogaine"),
        ("keeps", "Keeps"),
    )
    norm_full = _normalize(product_name)
    for needle, brand in aliases:
        if norm_full.startswith(needle):
            return brand
    toks = _norm_tokens(product_name)
    if not toks:
        return product_name
    return toks[0].title()


def product_brands_for_module(maxx_id: str, max_brands: int = 8) -> list[str]:
    curated = list(_CURATED_BRANDS.get(maxx_id, []))
    if curated:
        return curated[:max_brands]
    brands: list[str] = []
    seen: set[str] = set()
    for name in _module_products(maxx_id):
        brand = _brand_name(name)
        key = _normalize(brand)
        if not key or key in seen:
            continue
        seen.add(key)
        brands.append(brand)
        if len(brands) >= max_brands:
            break
    return brands


async def product_links_from_context(
    *,
    message: str,
    maxx_id: str,
    max_links: int = 5,
) -> str:
    """Return Amazon search links for module-relevant products."""
    module_products = _module_products(maxx_id)
    retrieved = await retrieve_chunks(None, maxx_id, message, k=4, min_similarity=0.35)
    evidence_text = "\n".join(c.get("content", "") for c in retrieved)
    evidence_products = _extract_products(evidence_text)

    ranked: list[tuple[int, str]] = []
    haystack = f"{message}\n{evidence_text}".lower()
    norm_message = _normalize(message)
    message_tokens = set(_norm_tokens(message))
    explicit_query_matches: list[str] = []
    explicit_seen: set[str] = set()
    for name in _CURATED_PRODUCTS.get(maxx_id, []):
        aliases = _PRODUCT_ALIASES.get(name, [])
        alias_hit = any(alias in message.lower() or _normalize(alias) in norm_message for alias in aliases)
        if name.lower() in message.lower() or _normalize(name) in norm_message or alias_hit:
            key = _normalize(name)
            if key not in explicit_seen:
                explicit_seen.add(key)
                explicit_query_matches.append(name)
        else:
            parts = set(_norm_tokens(name))
            overlap = len(parts & message_tokens)
            if overlap >= 2 or (overlap >= 1 and ("bha" in message_tokens or "spf" in message_tokens)):
                key = _normalize(name)
                if key not in explicit_seen:
                    explicit_seen.add(key)
                    explicit_query_matches.append(name)

    for name in module_products + evidence_products:
        key = _normalize(name)
        if not key:
            continue
        score = 0
        pretty = name.strip()
        if pretty.lower() in haystack:
            score += 3
        for part in pretty.lower().split():
            if len(part) >= 4 and part in haystack:
                score += 1
        if score > 0:
            ranked.append((score, pretty))

    for name in _CURATED_PRODUCTS.get(maxx_id, []):
        if name.lower() in haystack:
            ranked.append((10, name))

    if explicit_query_matches:
        ranked = [(100, name) for name in explicit_query_matches]
    elif not ranked:
        fallback = evidence_products[:max_links] or module_products[:max_links]
        if not fallback:
            return ""
        ranked = [(1, name) for name in fallback]

    chosen: list[str] = []
    seen: set[str] = set()
    for name in explicit_query_matches:
        key = _normalize(name)
        if key in seen:
            continue
        seen.add(key)
        chosen.append(name)
        if len(chosen) >= max_links:
            break
    for _score, name in sorted(ranked, key=lambda x: (-x[0], x[1]))[: max_links * 3]:
        key = _normalize(name)
        if key in seen:
            continue
        seen.add(key)
        chosen.append(name)
        if len(chosen) >= max_links:
            break

    if not chosen:
        return ""

    lines = ["here are quick amazon search links for the products mentioned in the current module docs:"]
    for name in chosen:
        lines.append(f"- {name}: {_amazon_search_url(name)}")
    lines.append("if you want, ask for cleanser / moisturizer / sunscreen only and i can narrow it down.")
    return "\n".join(lines)
