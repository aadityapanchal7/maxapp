"""Partner brand injection: keyword-triggered prompt suffix rules.

Rules are stored in `partner_rules`. On each chat turn we scan the user message
(plus any RAG-retrieved chunks) for trigger keywords, and append the matching
rule's `prompt_suffix` to the system prompt so the LLM recommends the partner.

Simple cache: rules reload every 60s — avoids hitting the DB per chat turn.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.sqlalchemy_models import PartnerRule

logger = logging.getLogger(__name__)


_CACHE: dict = {"rows": [], "loaded_at": 0.0}
_CACHE_TTL_SECONDS = 60


async def _load_active_rules(db: AsyncSession) -> List[PartnerRule]:
    now = time.time()
    if _CACHE["rows"] and (now - _CACHE["loaded_at"]) < _CACHE_TTL_SECONDS:
        return _CACHE["rows"]
    try:
        res = await db.execute(select(PartnerRule).where(PartnerRule.active.is_(True)))
        rows = list(res.scalars().all())
    except Exception as e:
        logger.warning("[partner_rules] load failed: %s", e)
        return []
    _CACHE["rows"] = rows
    _CACHE["loaded_at"] = now
    return rows


def _is_in_window(rule: PartnerRule, now_utc: datetime) -> bool:
    if rule.start_date and now_utc < rule.start_date:
        return False
    if rule.end_date and now_utc > rule.end_date:
        return False
    return True


def _matches(keywords: Iterable[str], haystack: str) -> bool:
    h = haystack.lower()
    return any(k and k.strip().lower() in h for k in keywords)


async def get_matching_rule_suffix(
    db: AsyncSession,
    user_message: str,
    extra_texts: Optional[List[str]] = None,
) -> Tuple[str, List[int]]:
    """Return (prompt_suffix_block, matching_rule_ids).

    If multiple rules match, all their suffixes are concatenated. Empty string
    and empty list on no matches or load failure.
    """
    rules = await _load_active_rules(db)
    if not rules:
        return "", []

    now = datetime.now(timezone.utc)
    haystack = "\n".join([user_message or "", *(extra_texts or [])])

    suffixes: List[str] = []
    ids: List[int] = []
    for rule in rules:
        if not _is_in_window(rule, now):
            continue
        if _matches(rule.trigger_keywords or [], haystack):
            suffixes.append(f"[PARTNER RULE: {rule.name}]\n{rule.prompt_suffix}")
            ids.append(int(rule.id))

    if not suffixes:
        return "", []
    return "\n\n".join(suffixes), ids


def invalidate_cache() -> None:
    """Call after admin CRUD to force reload on the next turn."""
    _CACHE["rows"] = []
    _CACHE["loaded_at"] = 0.0
