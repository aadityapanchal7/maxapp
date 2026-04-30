"""
Synchronous LLM calls for use inside asyncio.to_thread.

All calls go through LangChain providers (lc_providers.py).
No direct google.generativeai / openai / mistralai SDK imports here.
"""

from langchain_core.output_parsers import StrOutputParser


def sync_llm_json_response(prompt: str, max_tokens: int = 8192) -> str:
    """
    Return raw JSON string from the configured provider.
    Runs synchronously — call via asyncio.to_thread() from async code.

    JSON mode is enabled per-provider:
      OpenAI / Mistral — response_format=json_object
      Gemini           — response_mime_type=application/json

    max_tokens defaults to 8192. Callers that return very large JSON (e.g. schedule
    adaptation) should pass a higher max_tokens (see settings.schedule_adapt_max_output_tokens).
    """
    from services.lc_providers import get_sync_json_llm

    llm = get_sync_json_llm(max_tokens=max_tokens)
    result = (llm | StrOutputParser()).invoke(prompt)
    return result or "{}"


async def async_llm_json_response(prompt: str, max_tokens: int = 8192) -> str:
    """
    Return raw JSON string from configured provider using async invoke.
    Use inside async request paths to avoid thread offloading.
    """
    from services.lc_providers import get_sync_json_llm

    llm = get_sync_json_llm(max_tokens=max_tokens)
    result = await (llm | StrOutputParser()).ainvoke(prompt)
    return result or "{}"


def sync_llm_plain_text(prompt: str) -> str:
    """
    Return plain text from the configured provider.
    Runs synchronously — call via asyncio.to_thread() from async code.
    """
    from services.lc_providers import get_sync_plain_llm

    llm = get_sync_plain_llm(max_tokens=512)
    result = (llm | StrOutputParser()).invoke(prompt)
    return (result or "").strip()
