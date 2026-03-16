"""
Skinmax routines and helper utilities.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Dict
import re

SKINMAX_CONCERNS: Dict[str, Dict[str, str]] = {
    "acne": {
        "label": "Acne / Congestion",
        "am": "Gentle cleanser -> benzoyl peroxide or salicylic acid -> lightweight moisturizer -> sunscreen",
        "pm": "Cleanser -> adapalene/retinoid -> moisturizer",
        "weekly": "Clay mask 1-2x, BHA exfoliant 1-3x, no strong peels if inflamed",
        "sunscreen": "Oil-free, non-comedogenic SPF 30+ every morning",
    },
    "pigmentation": {
        "label": "Pigmentation / Uneven Tone",
        "am": "Gentle cleanser -> vitamin C or azelaic acid -> moisturizer -> sunscreen",
        "pm": "Cleanser -> retinoid or azelaic acid -> moisturizer",
        "weekly": "Gentle exfoliant 1-2x, brightening mask 1x, mild peel occasionally",
        "sunscreen": "SPF 30-50 daily or dark spots will keep getting worse",
    },
    "texture": {
        "label": "Texture / Scarring",
        "am": "Gentle cleanser -> niacinamide or salicylic acid -> moisturizer -> sunscreen",
        "pm": "Cleanser -> retinoid -> moisturizer",
        "weekly": "AHA/BHA exfoliant 1-2x, smoothing mask 1x, mild peel occasionally",
        "sunscreen": "SPF 30+ daily to protect collagen and prevent scar darkening",
    },
    "redness": {
        "label": "Redness / Sensitivity",
        "am": "Gentle cleanser -> azelaic acid or calming serum -> barrier moisturizer -> sunscreen",
        "pm": "Gentle cleanser -> azelaic acid -> barrier moisturizer",
        "weekly": "Hydrating mask 1-2x, very mild exfoliation or none, avoid aggressive peels",
        "sunscreen": "Mineral SPF 30+ daily, especially if skin gets red easily",
    },
    "aging": {
        "label": "Aging / Skin Quality",
        "am": "Gentle cleanser -> vitamin C -> moisturizer -> sunscreen",
        "pm": "Cleanser -> retinoid/retinol -> moisturizer",
        "weekly": "Hydrating mask 1x, gentle exfoliant 1x, peel occasionally if tolerated",
        "sunscreen": "SPF 30-50 every day since UV ages your face faster than anything",
    },
}


def parse_time_from_text(text: str, default_meridian: Optional[str] = None) -> Optional[str]:
    if not text:
        return None
    s = text.strip().lower()
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    ampm = match.group(3) or default_meridian
    if minute > 59 or hour > 24:
        return None
    if ampm:
        if hour == 12:
            hour = 0
        if ampm == "pm":
            hour += 12
    if hour == 24:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def add_minutes(time_str: str, minutes: int) -> str:
    base = datetime.strptime(time_str, "%H:%M")
    dt = base + timedelta(minutes=minutes)
    return dt.time().strftime("%H:%M")


def get_concern_key(text: str) -> Optional[str]:
    s = (text or "").lower()
    if "acne" in s or "congestion" in s:
        return "acne"
    if "pigment" in s or "uneven" in s or "tone" in s or "dark spot" in s:
        return "pigmentation"
    if "texture" in s or "scar" in s:
        return "texture"
    if "red" in s or "sensitive" in s:
        return "redness"
    if "aging" in s or "age" in s or "quality" in s:
        return "aging"
    if s.strip() in {"1", "2", "3", "4", "5"}:
        return {"1": "acne", "2": "pigmentation", "3": "texture", "4": "redness", "5": "aging"}[s.strip()]
    return None
