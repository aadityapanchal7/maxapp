"""Route chat and triple-scan vision to Gemini or OpenAI based on settings.

Includes automatic failover: if the primary provider fails (timeout, rate-limit,
5xx, etc.), we transparently retry with the alternate provider so a single
vendor outage doesn't take chat or scans down.
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


async def llm_analyze_triple_full(
    front: bytes,
    left: bytes,
    right: bytes,
    onboarding_json: str = "{}",
) -> Dict[str, Any]:
    primary_is_openai = use_openai()
    primary = _call_openai_triple if primary_is_openai else _call_gemini_triple
    fallback = _call_gemini_triple if primary_is_openai else _call_openai_triple
    primary_name = "openai" if primary_is_openai else "gemini"
    fallback_name = "gemini" if primary_is_openai else "openai"

    try:
        return await primary(front, left, right, onboarding_json)
    except Exception as primary_err:
        logger.warning(
            "Vision primary provider %s failed (%s: %s); trying %s",
            primary_name,
            type(primary_err).__name__,
            primary_err,
            fallback_name,
        )
        try:
            return await fallback(front, left, right, onboarding_json)
        except Exception as fallback_err:
            logger.exception(
                "Vision fallback provider %s also failed: %s", fallback_name, fallback_err
            )
            raise primary_err
