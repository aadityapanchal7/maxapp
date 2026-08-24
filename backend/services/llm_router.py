"""Route triple-scan vision to Gemini or OpenAI based on settings.

Includes automatic failover: if the primary provider fails (timeout, rate-limit,
5xx, etc.), we transparently retry with the alternate provider so a single
vendor outage doesn't take scans down.

Note: `llm_chat()` is retained for backward compatibility with older callers;
the production chat path uses LangChain agent execution in `services.lc_agent`.
"""

import logging
from typing import Any, Dict, List, Optional

from services.llm_provider import use_openai

logger = logging.getLogger(__name__)


async def _call_openai_chat(
    message: str,
    chat_history: List[dict],
    user_context: Optional[dict],
    image_data: Optional[bytes],
    delivery_channel: str,
) -> dict:
    from services.openai_service import openai_service

    return await openai_service.chat(
        message, chat_history, user_context, image_data, delivery_channel
    )


async def _call_gemini_chat(
    message: str,
    chat_history: List[dict],
    user_context: Optional[dict],
    image_data: Optional[bytes],
    delivery_channel: str,
) -> dict:
    from services.gemini_service import gemini_service

    return await gemini_service.chat(
        message, chat_history, user_context, image_data, delivery_channel
    )


async def llm_chat(
    message: str,
    chat_history: List[dict],
    user_context: Optional[dict] = None,
    image_data: Optional[bytes] = None,
    delivery_channel: str = "app",
) -> dict:
    primary_is_openai = use_openai()
    primary = _call_openai_chat if primary_is_openai else _call_gemini_chat
    fallback = _call_gemini_chat if primary_is_openai else _call_openai_chat
    primary_name = "openai" if primary_is_openai else "gemini"
    fallback_name = "gemini" if primary_is_openai else "openai"

    try:
        return await primary(message, chat_history, user_context, image_data, delivery_channel)
    except Exception as primary_err:
        logger.warning(
            "LLM primary provider %s failed (%s: %s); trying %s",
            primary_name,
            type(primary_err).__name__,
            primary_err,
            fallback_name,
        )
        try:
            return await fallback(message, chat_history, user_context, image_data, delivery_channel)
        except Exception as fallback_err:
            logger.exception(
                "LLM fallback provider %s also failed: %s", fallback_name, fallback_err
            )
            # Re-raise the primary error so upstream logging reflects the first failure.
            raise primary_err


async def _call_openai_triple(front: bytes, left: bytes, right: bytes, onboarding_json: str):
    from services.openai_service import openai_service

    return await openai_service.analyze_triple_full(front, left, right, onboarding_json)


async def _call_gemini_triple(front: bytes, left: bytes, right: bytes, onboarding_json: str):
    from services.gemini_service import gemini_service

    return await gemini_service.analyze_triple_full(front, left, right, onboarding_json)


async def _call_claude_triple(front: bytes, left: bytes, right: bytes, onboarding_json: str):
    from services.claude_service import claude_service

    return await claude_service.analyze_triple_full(front, left, right, onboarding_json)


async def llm_analyze_triple_full(
    front: bytes,
    left: bytes,
    right: bytes,
    onboarding_json: str = "{}",
) -> Dict[str, Any]:
    from services.llm_provider import use_openai, use_gemini, use_claude

    # Order the FULL provider set by the configured primary, then try every one.
    # Two reasons this is a chain and not a pair:
    #  1. A single exhausted key (e.g. OpenAI 402/429 "no credits") must never be
    #     able to hand every user a scan result — there is always another vendor.
    #  2. The providers do NOT raise on API failure: analyze_triple_full catches
    #     internally and RETURNS default_full_triple_dict(), a well-formed dict of
    #     flat 5.0s tagged source="fallback". An exception-only fallback chain is
    #     therefore dead code — the primary always looks like a success. That bug
    #     shipped 30 of 32 production scans as dummy scores. _is_fallback() below
    #     is what actually advances the chain.
    ALL = [
        ("claude", _call_claude_triple),
        ("gemini", _call_gemini_triple),
        ("openai", _call_openai_triple),
    ]
    if use_claude():
        primary_name = "claude"
    elif use_openai():
        primary_name = "openai"
    else:
        if not (use_openai() or use_gemini() or use_claude()):
            logger.warning("LLM_PROVIDER not set to a vision provider for face scan; defaulting to gemini")
        primary_name = "gemini"
    chain = sorted(ALL, key=lambda p: 0 if p[0] == primary_name else 1)

    def _is_fallback(result: Any) -> bool:
        """A provider's internal give-up sentinel — dummy 5.0s, not a real rating."""
        return isinstance(result, dict) and str(result.get("source") or "") == "fallback"

    last_fallback: Optional[Dict[str, Any]] = None
    first_err: Optional[Exception] = None

    for name, call in chain:
        try:
            result = await call(front, left, right, onboarding_json)
        except Exception as err:
            if first_err is None:
                first_err = err
            logger.warning(
                "Vision provider %s raised (%s: %s); trying next",
                name, type(err).__name__, err,
            )
            continue
        if _is_fallback(result):
            # Keep the first one so a total outage still returns a shaped result.
            if last_fallback is None:
                last_fallback = result
            logger.warning(
                "Vision provider %s returned its fallback sentinel (%s); trying next",
                name, str(result.get("preview_blurb") or "")[:120],
            )
            continue
        if name != primary_name:
            logger.info("Vision analysis served by %s (primary %s unavailable)", name, primary_name)
        return result

    logger.error(
        "ALL vision providers failed for face scan (chain: %s) — returning fallback scores",
        ", ".join(n for n, _ in chain),
    )
    if last_fallback is not None:
        return last_fallback
    raise first_err or RuntimeError("All vision providers failed")
