"""Direct retrieval + answer path for straightforward knowledge questions."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from collections import OrderedDict
from typing import Optional

from config import settings
from services.chat_telemetry import log_prompt_budget
from services.lc_providers import get_chat_llm_with_fallback
from services.rag_prompt_selector import _LEXICONS, select_rag_system_prompt
from services.rag_service import retrieve_chunks, VALID_MAXX_IDS
from services.token_budget import count_tokens

logger = logging.getLogger(__name__)


# --- Broad-fan-out cache --------------------------------------------------
# When a query misses the chosen module, we re-retrieve across all 6 indexes
# (skinmax/fitmax/hairmax/heightmax/bonemax/general). That's 6x retrieve_chunks
# calls. Most of the cost is the BM25 score computation — already <1ms warm,
# but we cache by (message_normalized) so identical re-asks (the user retries
# the same question) skip the work entirely.
_BROAD_CACHE: "OrderedDict[str, tuple[float, list[dict]]]" = OrderedDict()
_BROAD_CACHE_MAX = 256
_BROAD_CACHE_TTL_S = 300.0  # 5 minutes — long enough for a retry, short
                            # enough that doc edits show up quickly.


def _normalize_for_cache(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _broad_cache_key(message: str) -> str:
    norm = _normalize_for_cache(message)
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def _broad_cache_get(key: str) -> Optional[list[dict]]:
    entry = _BROAD_CACHE.get(key)
    if not entry:
        return None
    ts, rows = entry
    if (time.time() - ts) > _BROAD_CACHE_TTL_S:
        _BROAD_CACHE.pop(key, None)
        return None
    # LRU touch
    _BROAD_CACHE.move_to_end(key)
    return rows


def _broad_cache_put(key: str, rows: list[dict]) -> None:
    _BROAD_CACHE[key] = (time.time(), rows)
    _BROAD_CACHE.move_to_end(key)
    while len(_BROAD_CACHE) > _BROAD_CACHE_MAX:
        _BROAD_CACHE.popitem(last=False)


async def _broad_fanout_retrieval(
    message: str,
    *,
    k_total: int = 5,
    min_similarity: Optional[float] = None,
) -> list[dict]:
    """Re-retrieve across ALL maxx indexes when the targeted retrieval missed.

    Used as a second pass before falling to the foundational-knowledge
    template. Multi-topic queries like "acne and aging" or queries where
    the classifier picked the wrong module recover here without paying the
    cost of a generic LLM call that ignores the docs.

    Cached by normalized message text — identical re-asks (user retries
    the same question) skip the 6x retrieve cost entirely.
    """
    cache_key = _broad_cache_key(message)
    cached = _broad_cache_get(cache_key)
    if cached is not None:
        return list(cached)  # defensive copy — callers mutate

    threshold = float(
        min_similarity
        if min_similarity is not None
        else (getattr(settings, "rag_score_threshold", 0.35) or 0.35)
    )
    # Per-module budget kept small so the merge favors strong-signal modules
    # rather than bulk-importing weak hits from every index.
    k_per_maxx = max(2, k_total // 3 + 1)

    async def _one(maxx: str) -> list[dict]:
        try:
            rows = await retrieve_chunks(
                None, maxx, message, k=k_per_maxx, min_similarity=threshold,
            )
            return [{**row, "_maxx": maxx} for row in rows]
        except Exception:
            return []

    gathered = await asyncio.gather(*[_one(m) for m in VALID_MAXX_IDS])
    flat = [row for rows in gathered for row in rows]
    flat.sort(key=lambda c: c.get("similarity", 0.0), reverse=True)
    top = flat[:k_total]
    _broad_cache_put(cache_key, top)
    return top


# Per-module fallback expansion terms. Only the highest-weight (3) lexicon
# entries — they push BM25 toward canonical doc content when the user's
# unexpanded query produces zero hits. Stripped to single-word tokens; multi-
# word phrases dilute the tokenizer with no extra recall.
_EXPANSION_TERMS: dict[str, list[str]] = {
    maxx: [t for t, w in lex.items() if w >= 3 and " " not in t]
    for maxx, lex in _LEXICONS.items()
}


def _expand_query(query: str, maxx: str) -> str:
    """Append module-anchor terms to a short query that needs help.

    Only used as a SECOND-PASS retrieval fallback when the unexpanded query
    returns nothing — running expansion on every query was empirically worse
    (long-tail queries got dragged into the most-anchor-heavy doc, e.g. all
    bonemax queries pulled toward the Bonesmashing doc).
    """
    if len(query.split()) >= 8:
        return query
    expansion = _EXPANSION_TERMS.get(maxx, [])
    if not expansion:
        return query
    q_lower = query.lower()
    extras = [t for t in expansion[:6] if t not in q_lower]
    if not extras:
        return query
    return f"{query} {' '.join(extras)}"

_CITATION_RE = re.compile(r"\[(?:source|sources):[^\]]+\]", re.IGNORECASE)


def _clean_citations(text: str, retrieved: list[dict]) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"\n{3,}", "\n\n", raw).strip()
    matches = _CITATION_RE.findall(cleaned)
    if matches:
        seen: set[str] = set()
        for match in matches:
            key = match.lower()
            if key in seen:
                cleaned = cleaned.replace(match, "", 1)
            else:
                seen.add(key)
        return re.sub(r"\s{2,}", " ", cleaned).strip()
    if not retrieved:
        return cleaned
    chunk = retrieved[0]
    meta = chunk.get("metadata") or {}
    source = meta.get("source") or f"{chunk.get('_maxx')}/{chunk.get('doc_title')}.md"
    section = meta.get("section") or chunk.get("doc_title") or "section"
    return f"{cleaned} [source: {source} > {section}]".strip()


async def gather_rag_evidence(
    *,
    message: str,
    maxx_hints: list[str],
    active_maxx: Optional[str] = None,
    max_chunks: Optional[int] = None,
) -> list[dict]:
    """Retrieve and merge evidence rows across hinted modules."""
    hints = [h for h in (maxx_hints or []) if h]
    if not hints and active_maxx:
        hints = [active_maxx]
    if not hints:
        return []

    k_total = int(max_chunks or getattr(settings, "rag_top_k", 4) or 4)
    k_per_maxx = max(2, k_total // max(1, len(hints)) + 1)
    min_similarity = float(getattr(settings, "rag_score_threshold", 0.35) or 0.35)

    async def _one(maxx: str) -> list[dict]:
        # Pass 1: original query — this is what works for ~95% of turns.
        rows = await retrieve_chunks(
            None,
            maxx,
            message,
            k=k_per_maxx,
            min_similarity=min_similarity,
        )
        if rows:
            return [{**row, "_maxx": maxx} for row in rows]
        # Pass 2 (fallback): query expansion. Only fires when the original
        # query produced zero hits — typical case is a 1-2 word slang query
        # whose tokens don't match any indexed doc title verbatim.
        expanded = _expand_query(message, maxx)
        if expanded == message:
            return []
        rows = await retrieve_chunks(
            None,
            maxx,
            expanded,
            k=k_per_maxx,
            min_similarity=min_similarity,
        )
        return [{**row, "_maxx": maxx} for row in rows]

    gathered = await asyncio.gather(*[_one(h) for h in hints])
    retrieved = [row for rows in gathered for row in rows]
    retrieved.sort(key=lambda c: c.get("similarity", 0.0), reverse=True)
    return retrieved[:k_total]


_RESPONSE_LENGTH_BLOCKS: dict[str, str] = {
    "concise": (
        "\n\n## USER RESPONSE LENGTH PREFERENCE: CONCISE  (overrides any other length rule above)\n"
        "- Hard cap: 1 sentence. 2 only if the question literally has two parts.\n"
        "- No bullets, no headers, no lists, no lead-ins.\n"
        "- One inline citation is fine; skip others. Pick the single most useful specific."
    ),
    "medium": (
        "\n\n## USER RESPONSE LENGTH PREFERENCE: MEDIUM  (default)\n"
        "- 2-3 sentences. Or up to 4 short bullets if a list genuinely helps.\n"
        "- Answer first, then one concrete specific (product, dose, timing, or timeframe) with inline citation."
    ),
    "detailed": (
        "\n\n## USER RESPONSE LENGTH PREFERENCE: DETAILED  (overrides any other length rule above)\n"
        "- Up to ~8 sentences, or a tight bulleted structure. Still lowercase, still Max's voice — length is not license to pad.\n"
        "- Every specific you name (ingredient %, minutes, reps, macros) needs an inline citation.\n"
        "- Structure: direct answer → specifics with citations → one sentence on why. No intros, no end-summaries."
    ),
}


def _length_suffix(response_length: Optional[str]) -> str:
    key = (response_length or "").strip().lower()
    return _RESPONSE_LENGTH_BLOCKS.get(key, _RESPONSE_LENGTH_BLOCKS["medium"])


# When retrieval returns nothing, switch the system prompt into "standard
# template" mode. This OVERRIDES the strict-grounding rules from the base RAG
# prompt for this specific turn — the user gets a competent answer from the
# LLM's foundational knowledge, plus a short up-front disclosure that it's a
# template (not the user's personalized doc-grounded protocol).
_STANDARD_TEMPLATE_SUFFIX = """

## STANDARD-TEMPLATE FALLBACK (this turn only)
No matching evidence was retrieved for the user's question. Override the
"don't see that in your current docs" rule for this turn:

- Use your foundational knowledge of fitness, dermatology, hair, skeletal,
  and lookmaxxing protocols to give a competent, standard answer.
- Open the answer with ONE short clause noting it's a standard template
  (e.g. "no protocol on file for that — here's a standard template:").
- Then deliver the answer at full quality. Specific numbers, products,
  ingredients, doses, sets/reps — give them. Standard means industry-
  accepted, not vague.
- Do NOT cite [source: ...] — there's no evidence to cite.
- Do NOT refuse, hedge, or push the user to "consult a professional"
  unless the question is genuinely medical/diagnostic.
- Keep the same Max voice: lowercase, direct, no fluff."""


async def _answer_without_evidence(
    *,
    message: str,
    maxx_hints: Optional[list[str]],
    active_maxx: Optional[str],
    user_context_str: Optional[str],
    response_length: Optional[str],
) -> str:
    """LLM call when retrieval returned zero chunks.

    Uses the same selector + length budget as the evidence path, but appends
    `_STANDARD_TEMPLATE_SUFFIX` so the LLM is explicitly permitted to draw on
    general knowledge. The user gets a useful answer instead of a refusal.
    """
    selection = select_rag_system_prompt(
        message, maxx_hints=maxx_hints or [], active_maxx=active_maxx
    )
    system_prompt = (
        selection.system_prompt + _length_suffix(response_length) + _STANDARD_TEMPLATE_SUFFIX
    )
    logger.info(
        "[fast_rag] no-evidence fallback: chosen_maxx=%s reason=%s",
        selection.chosen_maxx, selection.reason,
    )

    length_key = (response_length or "").strip().lower()
    # Bumped from the evidence-path budget — template responses got truncated
    # mid-sentence in production ("here's a standard template: adult acne and"
    # cut off). The template path needs more headroom because there's no
    # citation tax and the LLM expands more on standard-template content.
    max_tokens = 160 if length_key == "concise" else 900 if length_key == "detailed" else 600
    llm = get_chat_llm_with_fallback(max_tokens=max_tokens, temperature=0.3)
    from langchain_core.messages import HumanMessage, SystemMessage

    context_block = ""
    if user_context_str:
        context_block = f"User context (schedule, profile, onboarding):\n{user_context_str.strip()}\n\n"

    human = (
        f"{context_block}"
        f"User question:\n{message.strip()}\n\n"
        f"(No matching evidence in module docs. Use the standard-template "
        f"fallback rules above.)"
    )
    try:
        resp = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=human)])
        text = getattr(resp, "content", resp)
        if isinstance(text, list):
            text = "\n".join(str(x) for x in text)
        return str(text or "").strip()
    except Exception as e:
        logger.warning("fast rag standard-template fallback failed: %s", e)
        return ""


async def answer_from_chunks(
    *,
    message: str,
    retrieved: list[dict],
    maxx_hints: Optional[list[str]] = None,
    active_maxx: Optional[str] = None,
    user_context_str: Optional[str] = None,
    response_length: Optional[str] = None,
) -> str:
    """Answer a knowledge question from pre-retrieved evidence only.

    The system prompt is composed by `select_rag_system_prompt()` — it pulls
    `rag_answer_system` from the Supabase `system_prompts` cache and appends
    the best-matching `{maxx_id}_coaching_reference` based on the query.

    If `user_context_str` is provided (schedule / profile / onboarding summary)
    it is injected into the user message so grounded answers can reference the
    caller's live state without pulling the full coaching context hot path.
    """
    if not retrieved:
        return ""

    evidence_lines: list[str] = []
    for i, chunk in enumerate(retrieved, 1):
        meta = chunk.get("metadata") or {}
        source = meta.get("source") or f"{chunk.get('_maxx')}/{chunk.get('doc_title')}.md"
        section = meta.get("section") or chunk.get("doc_title") or "section"
        evidence_lines.append(
            f"[{i}] source={source} | section={section}\n{chunk.get('content', '').strip()}"
        )

    # Fall back to chunk-origin maxx when caller didn't pass hints (e.g. graph
    # retrieval already tagged each chunk with _maxx).
    if not maxx_hints:
        chunk_maxxes = [c.get("_maxx") for c in retrieved if c.get("_maxx")]
        maxx_hints = list(dict.fromkeys(m for m in chunk_maxxes if isinstance(m, str)))

    selection = select_rag_system_prompt(
        message, maxx_hints=maxx_hints, active_maxx=active_maxx
    )
    system_prompt = selection.system_prompt + _length_suffix(response_length)
    logger.info(
        "[fast_rag] selector chosen_maxx=%s score=%d runner_up=%d reason=%s length=%s",
        selection.chosen_maxx, selection.score, selection.runner_up_score, selection.reason,
        (response_length or "medium"),
    )

    length_key = (response_length or "").strip().lower()
    max_tokens = 120 if length_key == "concise" else 640 if length_key == "detailed" else 420
    llm = get_chat_llm_with_fallback(max_tokens=max_tokens, temperature=0.2)
    from langchain_core.messages import HumanMessage, SystemMessage

    context_block = ""
    if user_context_str:
        context_block = f"User context (schedule, profile, onboarding):\n{user_context_str.strip()}\n\n"

    human = (
        f"{context_block}"
        f"User question:\n{message.strip()}\n\n"
        f"Evidence from module docs:\n{chr(10).join(evidence_lines)}"
    )
    system_tokens = count_tokens(system_prompt)
    user_tokens = count_tokens(message)
    chunk_tokens = sum(count_tokens(c.get("content") or "") for c in retrieved)
    log_prompt_budget(
        path="fast_rag",
        system_tokens=system_tokens,
        coaching_context_tokens=count_tokens(user_context_str or ""),
        history_tokens=0,
        chunk_tokens=chunk_tokens,
        user_tokens=user_tokens,
        total_tokens=system_tokens + user_tokens + chunk_tokens + count_tokens(user_context_str or ""),
    )
    try:
        resp = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=human)])
        text = getattr(resp, "content", resp)
        if isinstance(text, list):
            text = "\n".join(str(x) for x in text)
        return _clean_citations(str(text or "").strip(), retrieved)
    except Exception as e:
        logger.warning("fast rag answer failed: %s", e)
        return ""


# Phrases that indicate the LLM produced a standard-template response. We
# detect on these and treat the answer as low-quality so the caller can re-
# attempt with broader retrieval. Lower-cased substring match — be liberal,
# false positives on real grounded answers are unlikely because grounded
# answers don't say "no protocol on file" or "standard template."
_TEMPLATE_OUTPUT_MARKERS: tuple[str, ...] = (
    "no protocol on file",
    "no protocol for that",
    "here's a standard template",
    "standard template",
    "no matching evidence",
    "don't see that in your current docs",
    "don't have that on file",
    "i don't have that info",
)


def _looks_like_template_response(text: str) -> bool:
    if not text:
        return False
    low = text.lower()
    if any(m in low for m in _TEMPLATE_OUTPUT_MARKERS):
        return True
    # Truncation heuristic: response ends mid-word with no terminal
    # punctuation (e.g. "adult acne and" in production). LLM hit max_tokens
    # before finishing — caller should retry with broader knowledge / higher
    # token budget. Threshold of 50 chars: lower than that and a one-clause
    # answer like "use cerave AM" isn't truncated, just terse.
    stripped = text.rstrip()
    if len(stripped) > 50 and not re.search(r"[.!?\"\)\]]\s*$", stripped):
        return True
    return False


async def answer_from_rag(
    *,
    message: str,
    maxx_hints: list[str],
    active_maxx: Optional[str] = None,
    max_chunks: Optional[int] = None,
    user_context_str: Optional[str] = None,
    response_length: Optional[str] = None,
) -> tuple[str, list[dict]]:
    """Return a direct RAG answer and the retrieved evidence used.

    Three-tier retrieval strategy:
      1. Targeted fan-out across maxx_hints (existing behavior, ~95% of turns).
      2. If targeted retrieval is empty: broad fan-out across ALL maxx
         indexes. This catches multi-topic queries ("acne and aging") and
         queries where the classifier picked the wrong module.
      3. Only if broad retrieval is ALSO empty: foundational-knowledge
         template fallback. This is now the last resort, not the first.

    Plus a quality-recovery layer: if the LLM's first answer looks like a
    no-evidence template response (truncated, "no protocol on file", etc.)
    AND broad fan-out finds chunks the targeted pass missed, we re-run
    `answer_from_chunks` with the broader evidence and return that.
    """
    retrieved = await gather_rag_evidence(
        message=message,
        maxx_hints=maxx_hints,
        active_maxx=active_maxx,
        max_chunks=max_chunks,
    )

    # Tier 1: targeted retrieval found chunks → answer from them.
    if retrieved:
        answer = await answer_from_chunks(
            message=message,
            retrieved=retrieved,
            maxx_hints=maxx_hints,
            active_maxx=active_maxx,
            user_context_str=user_context_str,
            response_length=response_length,
        )
        # Quality-recovery: if the LLM still produced a template-shaped
        # response despite having evidence (truncated output, refused tone,
        # "no protocol on file" leak), try the broader fan-out below.
        if answer and not _looks_like_template_response(answer):
            return answer, retrieved
        logger.info(
            "[fast_rag] tier-1 answer flagged as template-shaped; trying broad fan-out"
        )

    # Tier 2: broad fan-out — re-retrieve across every module before
    # giving up to the foundational-knowledge template.
    broad = await _broad_fanout_retrieval(message, k_total=int(max_chunks or 5))
    if broad:
        # Use chunk-origin maxx as the selector hint so the system prompt
        # picks the most relevant module reference.
        chunk_maxxes = [c.get("_maxx") for c in broad if c.get("_maxx")]
        broad_hints = list(dict.fromkeys(m for m in chunk_maxxes if isinstance(m, str)))
        answer = await answer_from_chunks(
            message=message,
            retrieved=broad,
            maxx_hints=broad_hints or maxx_hints,
            active_maxx=active_maxx,
            user_context_str=user_context_str,
            response_length=response_length,
        )
        if answer and not _looks_like_template_response(answer):
            logger.info(
                "[fast_rag] broad fan-out recovered answer (chunks=%d hints=%s)",
                len(broad), broad_hints,
            )
            return answer, broad

    # Tier 3: nothing in any index — foundational-knowledge template.
    logger.info(
        "[fast_rag] all retrieval exhausted; falling to standard-template (msg=%r)",
        (message or "")[:120],
    )
    fallback = await _answer_without_evidence(
        message=message,
        maxx_hints=maxx_hints,
        active_maxx=active_maxx,
        user_context_str=user_context_str,
        response_length=response_length,
    )
    return fallback, broad if broad else []
