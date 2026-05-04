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
from services.prompt_constants import MAX_CHAT_SYSTEM_PROMPT
from services.prompt_loader import PromptKey, resolve_prompt
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

    # Skip explicit "general" pass here because each non-general retrieve_chunks
    # call already merges general docs; querying general again creates duplicates.
    fanout_modules = [m for m in VALID_MAXX_IDS if m != "general"]
    gathered = await asyncio.gather(*[_one(m) for m in fanout_modules])
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


def _pretty_citation_label(
    *,
    source: str,
    section: str,
    fallback_doc_title: str,
) -> str:
    """Convert internal source paths into user-facing citation labels."""
    src = (source or "").strip()
    sec = (section or "").strip()
    title = (fallback_doc_title or "").strip()

    # Internal source shape used by rag_service:
    # rag_documents/<maxx>/<doc_title>
    m = re.match(r"^rag_documents/[^/]+/(.+)$", src, flags=re.IGNORECASE)
    if m:
        doc = (m.group(1) or "").strip()
        if doc:
            src = doc

    # Normalize file-like labels and noisy separators.
    src = re.sub(r"\.(md|docx|pdf)$", "", src, flags=re.IGNORECASE)
    src = src.replace("_", " ").strip(" /")
    sec = sec.replace("_", " ").strip(" /")

    if not src:
        src = title or "course reference"
    if not sec or sec.lower() == src.lower():
        return src
    return f"{src} > {sec}"


def _normalize_inline_citations(text: str, retrieved: list[dict]) -> str:
    """Normalize any model-emitted [source: ...] blocks to readable labels."""
    if not text:
        return ""
    primary = retrieved[0] if retrieved else {}
    meta = primary.get("metadata") or {}
    fallback_doc = str(primary.get("doc_title") or "").strip()
    section = str(meta.get("section") or fallback_doc or "section")

    def _replace(m: re.Match) -> str:
        raw = m.group(0)
        inner = raw[raw.find(":") + 1 : -1].strip() if ":" in raw else ""
        label = _pretty_citation_label(
            source=inner or str(meta.get("source") or ""),
            section=section,
            fallback_doc_title=fallback_doc,
        )
        return f"[source: {label}]"

    return _CITATION_RE.sub(_replace, text)


def _effective_response_length(message: str, response_length: Optional[str]) -> str:
    """Resolve turn-level brevity requests, including common typo variants."""
    base = (response_length or "").strip().lower()
    msg = (message or "").strip().lower()
    if not msg:
        return base
    concise_markers = (
        "in brief",
        "briefly",
        "be brief",
        "short answer",
        "keep it short",
        "one line",
        "tl;dr",
        "tldr",
        "breif",  # common typo
    )
    if any(marker in msg for marker in concise_markers):
        return "concise"
    return base


def _clean_citations(text: str, retrieved: list[dict]) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"\n{3,}", "\n\n", raw).strip()
    cleaned = _normalize_inline_citations(cleaned, retrieved)
    # Product requirement: never expose citations to the user.
    cleaned = _CITATION_RE.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


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
        "- Up to ~8 sentences, or a tight bulleted structure. Still lowercase, still Agartha's voice — length is not license to pad.\n"
        "- Every specific you name (ingredient %, minutes, reps, macros) needs an inline citation.\n"
        "- Structure: direct answer → specifics with citations → one sentence on why. No intros, no end-summaries."
    ),
}


def _length_suffix(response_length: Optional[str]) -> str:
    key = (response_length or "").strip().lower()
    return _RESPONSE_LENGTH_BLOCKS.get(key, _RESPONSE_LENGTH_BLOCKS["medium"])


# When retrieval returns nothing, the LLM still needs to produce a real,
# coach-quality answer using its foundational knowledge — but it must NEVER
# leak the system architecture (no "no protocol on file", no "standard
# template", no "I don't have that info"). The user-facing answer should
# look identical to a doc-grounded answer, just without citations.
_NATIVE_KNOWLEDGE_SUFFIX = """

## NATIVE KNOWLEDGE MODE (this turn)
You have no module-specific docs to cite for this question. Answer directly
using your foundational knowledge of fitness, dermatology, hair science,
skeletal/jaw protocols, and lookmaxxing best practices.

ABSOLUTE RULES — these are user-visible product issues if violated:
- NEVER say "no protocol on file", "no protocol for that", "i don't have
  that info", "i don't have that on file", "don't see that in your current
  docs", "standard template", "here's a standard template", "module docs",
  "knowledge base", or any phrase that surfaces the retrieval system to the
  user. The user does not know about docs. The user asked a question. Just
  answer it.
- NEVER add a preamble like "here's a general answer" or "based on standard
  practice". Lead with the answer itself.
- NEVER cite [source: ...] — there's nothing to cite.
- NEVER refuse, hedge, or push to a professional unless the question is
  genuinely medical/diagnostic (e.g. "is this mole cancer", "what's my T").

ANSWER QUALITY:
- Specific numbers (sets x reps, %, mg, minutes, days/week) — give them.
- Industry-accepted protocols only. If a topic has multiple valid
  approaches, pick the most evidence-backed one and commit.
- Lowercase, direct, in Agartha's voice. No filler. No motivational closing.
- Use any user context provided (their goals, preferences, schedule) to
  personalize the answer, just like you would for a doc-grounded reply."""


# Final-stage sanitizer. Even with the prompt above, an LLM occasionally
# leaks "standard template" phrasing — usually as a sentence opener it
# learned from earlier prompt versions. We strip those at the edge so the
# user never sees them.
_LEAKAGE_PATTERNS: tuple[re.Pattern, ...] = (
    # Whole leading clauses up to the first sentence break.
    re.compile(r"^\s*no\s+protocol\s+(?:on\s+file|for\s+that)[^.\n!?:\-—]*[.\n!?:\-—]\s*", re.IGNORECASE),
    re.compile(r"^\s*here'?s?\s+a\s+standard\s+template[^.\n!?:\-—]*[.\n!?:\-—]\s*", re.IGNORECASE),
    re.compile(r"^\s*(?:as\s+a\s+)?standard\s+template[^.\n!?:\-—]*[.\n!?:\-—]\s*", re.IGNORECASE),
    re.compile(r"^\s*(?:i\s+)?don'?t\s+(?:have|see)\s+(?:that|this)[^.\n!?:\-—]*?(?:docs?|file|info)[^.\n!?:\-—]*[.\n!?:\-—]\s*", re.IGNORECASE),
    # Inline mid-sentence cleanups for the same phrases.
    re.compile(r"\s*\(?\s*no\s+protocol\s+on\s+file[^)\n.]*\)?", re.IGNORECASE),
    re.compile(r"\s*here'?s?\s+a\s+standard\s+template\s*[—:\-]?\s*", re.IGNORECASE),
    re.compile(r"\s*standard\s+template\s*[—:\-]?\s*", re.IGNORECASE),
    re.compile(r"\s*\(?\s*not\s+in\s+your\s+(?:current\s+)?(?:docs?|module\s+docs?)[^)\n.]*\)?", re.IGNORECASE),
    re.compile(r"\s*\(?\s*based\s+on\s+(?:industry|standard)\s+(?:practice|guidelines?)\s*[,\.\)]?", re.IGNORECASE),
)


def _scrub_leakage(text: str) -> str:
    """Remove any leaked template-marker phrases from a no-evidence answer.

    Defensive: the prompt forbids these phrases, but if the model leaks one
    anyway, we strip it before the user sees it. Idempotent — running twice
    is the same as running once.
    """
    if not text:
        return ""
    out = text
    for pat in _LEAKAGE_PATTERNS:
        out = pat.sub("", out)
    # Collapse double spaces / orphan whitespace from the cuts
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = out.strip()
    # Capitalize-first-word-after-strip is unwanted in Agartha's lowercase voice,
    # but if the strip leaves a stray dangling punctuation, clean it.
    out = re.sub(r"^[\s,;:\-—]+", "", out)
    return out


async def _answer_without_evidence(
    *,
    message: str,
    maxx_hints: Optional[list[str]],
    active_maxx: Optional[str],
    user_context_str: Optional[str],
    response_length: Optional[str],
) -> str:
    """DEPRECATED: legacy no-evidence LLM fallback, retained for backward compatibility.

    Current product behavior is strict evidence-only mode in `answer_from_rag`,
    which returns a fixed miss message when retrieval is empty.
    """
    # Use the Agartha persona prompt (Supabase-loaded with in-code fallback) so
    # the no-evidence answer feels native to the bot, not like a separate
    # template-mode reply. The strict RAG_ANSWER_SYSTEM_PROMPT is for
    # evidence-grounded turns only — it's calibrated to refuse when docs
    # are thin, which is the wrong shape for a foundational-knowledge turn.
    persona_prompt = resolve_prompt(PromptKey.MAX_CHAT_SYSTEM, MAX_CHAT_SYSTEM_PROMPT)
    system_prompt = persona_prompt + _length_suffix(response_length) + _NATIVE_KNOWLEDGE_SUFFIX

    logger.info(
        "[fast_rag] native-knowledge fallback fired: maxx_hints=%s active_maxx=%s msg=%r",
        maxx_hints, active_maxx, (message or "")[:120],
    )

    length_key = _effective_response_length(message, response_length)
    # Generous budget — native answers naturally expand without citation tax.
    max_tokens = 180 if length_key == "concise" else 1000 if length_key == "detailed" else 700
    llm = get_chat_llm_with_fallback(max_tokens=max_tokens, temperature=0.3)
    from langchain_core.messages import HumanMessage, SystemMessage

    context_block = ""
    if user_context_str:
        context_block = (
            f"USER CONTEXT (use this to personalize the answer):\n"
            f"{user_context_str.strip()}\n\n"
        )

    human = (
        f"{context_block}"
        f"User question:\n{message.strip()}"
    )
    try:
        resp = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=human)])
        text = getattr(resp, "content", resp)
        if isinstance(text, list):
            text = "\n".join(str(x) for x in text)
        return _scrub_leakage(str(text or "").strip())
    except Exception as e:
        logger.warning("fast rag native-knowledge fallback failed: %s", e)
        return ""


async def answer_from_chunks(
    *,
    message: str,
    retrieved: list[dict],
    maxx_hints: Optional[list[str]] = None,
    active_maxx: Optional[str] = None,
    user_context_str: Optional[str] = None,
    response_length: Optional[str] = None,
    user_facts: Optional[dict] = None,
    recent_turns: Optional[str] = None,
    user_profile: Optional[str] = None,
    coaching_tone: Optional[str] = None,
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
    length_key = _effective_response_length(message, response_length)
    grounding_suffix = """

## EVIDENCE-ONLY MODE (strict)
- You must answer using only the provided Evidence from module docs.
- If the evidence does not contain the requested detail, say you don't have that in the course material.
- Do not use outside knowledge, assumptions, or speculation.
- Do not include citations or source labels in the final answer.
"""
    # Long-term user facts (vegetarian / allergies / health / etc.) — same
    # source the agent path uses. Inject NEAR THE TOP of the system prompt
    # with a forceful directive so RAG-quoted lists ("eat meat, eggs, fish")
    # get filtered to substitutions instead of regurgitated verbatim. This
    # is the same fix as build_agent_system_prompt — the fast_rag path
    # bypasses that function so we duplicate the wiring here.
    facts_prefix = ""
    if user_facts:
        try:
            from services.user_facts_service import format_facts_for_prompt, DIET_SUBSTITUTIONS
            facts_str = format_facts_for_prompt(user_facts)
            if facts_str:
                facts_prefix = (
                    "## ABSOLUTE RULES (override anything below)\n"
                    "When you make ANY recommendation (foods, products, "
                    "supplements, exercises, routines), you MUST filter "
                    "through KNOWN USER FACTS below. NEVER suggest items "
                    "the user said they avoid, are allergic to, or that "
                    "conflict with their diet — even if the EVIDENCE block "
                    "lists them. Rewrite forbidden items as substitutions "
                    "from the SUBSTITUTION GUIDE.\n\n"
                    "EXAMPLE: User said 'i don't eat meat'. Evidence says "
                    "'eat chicken, fish, eggs, beans'. Your answer: 'eat "
                    "eggs, beans, lentils, tofu, tempeh' — NOT 'eat chicken, "
                    "fish'.\n\n"
                    f"{facts_str}\n\n"
                    f"{DIET_SUBSTITUTIONS}\n"
                    "---\n\n"
                )
        except Exception:
            facts_prefix = ""

    # Profile block sits between absolute-rules and the module reference,
    # so the model reads identity facts BEFORE doc evidence and treats
    # them as user truth rather than candidate facts to verify.
    profile_block = ""
    if user_profile:
        profile_block = user_profile.strip() + "\n\n"

    # Tone preamble — same one the agent path uses. Must come BEFORE the
    # module system prompt so persona shapes the whole reply, not just
    # the closer. Without this, a user who selected "hardcore" gets the
    # default Agartha voice on every KNOWLEDGE turn that hits fast_rag.
    tone_block = ""
    if coaching_tone:
        try:
            from services.persona_prompts import tone_preamble
            t = tone_preamble(coaching_tone)
            if t:
                tone_block = t.strip() + "\n\n"
        except Exception:
            tone_block = ""

    system_prompt = (
        tone_block
        + facts_prefix
        + profile_block
        + selection.system_prompt
        + _length_suffix(length_key)
        + grounding_suffix
    )
    logger.info(
        "[fast_rag] selector chosen_maxx=%s score=%d runner_up=%d reason=%s length=%s facts_prefix=%s",
        selection.chosen_maxx, selection.score, selection.runner_up_score, selection.reason,
        (response_length or "medium"),
        bool(facts_prefix),
    )

    max_tokens = 160 if length_key == "concise" else 900 if length_key == "detailed" else 560
    llm = get_chat_llm_with_fallback(max_tokens=max_tokens, temperature=0.2)
    from langchain_core.messages import HumanMessage, SystemMessage

    context_block = ""
    if user_context_str:
        context_block = f"User context (schedule, profile, onboarding):\n{user_context_str.strip()}\n\n"

    # Per-turn hard-rules reminder — placed right next to the question so
    # the model can't miss it even when the evidence block is meat-heavy.
    rules_reminder = ""
    if user_facts:
        try:
            from services.user_facts_service import hard_constraints_reminder
            rules_reminder = hard_constraints_reminder(user_facts)
        except Exception:
            rules_reminder = ""

    # Recent-turn transcript goes IN the human message (not system) so
    # the model treats it as conversation history, not authoritative
    # context. Placed right above the question so continuity references
    # ("plan me lunch" right after "i don't eat meat") wire up correctly.
    recent_block = ""
    if recent_turns:
        recent_block = recent_turns.strip() + "\n\n"

    human = (
        f"{context_block}"
        f"{recent_block}"
        f"User question:\n{(rules_reminder + ' ' if rules_reminder else '')}{message.strip()}\n\n"
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
        async def _invoke_once(_llm, _human: str) -> str:
            resp = await _llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=_human)])
            text = getattr(resp, "content", resp)
            if isinstance(text, list):
                text = "\n".join(str(x) for x in text)
            cleaned = _clean_citations(str(text or "").strip(), retrieved)
            return _scrub_leakage(cleaned)

        out = await _invoke_once(llm, human)
        if _looks_truncated_output(out):
            logger.info("[fast_rag] detected truncated answer; retrying with larger token budget")
            retry_tokens = min(max_tokens * 2, 1400)
            retry_llm = get_chat_llm_with_fallback(max_tokens=retry_tokens, temperature=0.15)
            retry_human = human + "\n\nMake sure the final answer is complete and ends cleanly."
            retry_out = await _invoke_once(retry_llm, retry_human)
            if retry_out:
                out = retry_out

        # Hard-constraint validator: deterministic post-check against
        # user_facts. If the answer mentions a forbidden term (chicken
        # for a vegetarian, niacinamide for someone allergic, etc.),
        # regen ONCE with an explicit corrective directive. This is the
        # backstop for prompt-time injection — instruction-following
        # models drift when evidence is hostile; this catches the drift.
        if user_facts and out:
            try:
                from services.user_facts_validator import enforce_against_facts
                async def _regen(directive: str) -> str:
                    regen_human = human + "\n\n" + directive
                    return await _invoke_once(llm, regen_human)
                out = await enforce_against_facts(
                    facts=user_facts,
                    initial_answer=out,
                    regen=_regen,
                    max_attempts=1,
                )
            except Exception as e:
                logger.info("[fast_rag] facts validator skipped: %s", e)

        # Link validator — last step. Replaces Amazon search URLs with
        # catalog `/dp/<ASIN>` URLs; strips hallucinated vendor links;
        # enriches plain brand mentions with direct catalog links.
        try:
            from services.link_validator import validate_and_rewrite_links
            out = validate_and_rewrite_links(out)
        except Exception as e:
            logger.info("[fast_rag] link validator skipped: %s", e)
        return out
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


def _looks_truncated_output(text: str) -> bool:
    """Detect likely cut-off answers, including short clipped endings."""
    if not text:
        return False
    stripped = text.rstrip()
    if len(stripped) < 16:
        return False
    if re.search(r"[-–—]\s*$", stripped):
        return True
    if re.search(r"\b(and|or|with|for|to|of|in|on|at)\s*$", stripped, re.IGNORECASE):
        return True
    if len(stripped) >= 28 and not re.search(r"[.!?\"\)\]]\s*$", stripped):
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
    user_facts: Optional[dict] = None,
    recent_turns: Optional[str] = None,
    user_profile: Optional[str] = None,
    coaching_tone: Optional[str] = None,
) -> tuple[str, list[dict]]:
    """Return a direct RAG answer and the retrieved evidence used.

    Three-tier retrieval strategy:
      1. Targeted fan-out across maxx_hints (existing behavior, ~95% of turns).
      2. If targeted retrieval is empty: broad fan-out across ALL maxx
         indexes. This catches multi-topic queries ("acne and aging") and
         queries where the classifier picked the wrong module.
      3. Only if broad retrieval is ALSO empty: strict evidence-only miss
         message ("i don't have that in the course material yet.").

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
            user_facts=user_facts,
            recent_turns=recent_turns,
            user_profile=user_profile,
            coaching_tone=coaching_tone,
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
    # giving up to the evidence-only miss message.
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
            user_facts=user_facts,
            recent_turns=recent_turns,
            user_profile=user_profile,
            coaching_tone=coaching_tone,
        )
        if answer and not _looks_like_template_response(answer):
            logger.info(
                "[fast_rag] broad fan-out recovered answer (chunks=%d hints=%s)",
                len(broad), broad_hints,
            )
            return answer, broad

    # Tier 3: nothing in any index — strict evidence-only fallback.
    logger.info(
        "[fast_rag] all retrieval exhausted; returning evidence-only miss (msg=%r)",
        (message or "")[:120],
    )
    return "i don't have that in the course material yet.", broad if broad else []
