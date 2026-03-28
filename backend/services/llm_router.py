"""Route chat and triple-scan vision to Gemini or OpenAI based on settings."""

from typing import Any, Dict, List, Optional

from services.llm_provider import use_openai


async def llm_chat(
    message: str,
    chat_history: List[dict],
    user_context: Optional[dict] = None,
    image_data: Optional[bytes] = None,
) -> dict:
    if use_openai():
        from services.openai_service import openai_service

        return await openai_service.chat(message, chat_history, user_context, image_data)
    from services.gemini_service import gemini_service

    return await gemini_service.chat(message, chat_history, user_context, image_data)


async def llm_analyze_triple_full(
    front: bytes,
    left: bytes,
    right: bytes,
    onboarding_json: str = "{}",
) -> Dict[str, Any]:
    if use_openai():
        from services.openai_service import openai_service

        return await openai_service.analyze_triple_full(front, left, right, onboarding_json)
    from services.gemini_service import gemini_service

    return await gemini_service.analyze_triple_full(front, left, right, onboarding_json)
