"""
LangChain LLM provider factory — single source of truth for ALL LLM access.

No direct google.generativeai / openai / mistralai SDK imports anywhere else.
Everything goes through these builders.

Supports three providers via LLM_PROVIDER env var:
  gemini   — Google Gemini (default)
  openai   — OpenAI GPT
  mistral  — Mistral AI

Public API:
  get_primary_llm()                         — primary provider, no fallback
  get_chat_llm_with_fallback()              — primary + fallback chain (plain, no tools)
  get_chat_llm_with_tools_and_fallback()    — primary + fallback chain, tools bound to EACH
                                              provider before chaining (fixes the bind_tools bug)
  get_sync_json_llm()                       — synchronous, JSON-mode LLM for asyncio.to_thread
  get_sync_plain_llm()                      — synchronous plain-text LLM for asyncio.to_thread
  get_vision_llm()                          — multimodal LLM for image analysis (vision)

Fallback priority (when keys are available):
  primary=gemini   → openai → mistral
  primary=openai   → gemini → mistral
  primary=mistral  → gemini → openai

Timeout:
  LLM_TIMEOUT_SECONDS controls per-provider HTTP timeout. Default: 25 s.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from config import settings
from services.llm_provider import llm_provider

logger = logging.getLogger(__name__)


def _disable_gemini_internal_retries() -> None:
    """
    langchain-google-genai's `_create_retry_decorator` hardcodes max_retries=2
    with 1-60s exponential backoff (chat_models.py:140-155). On 429 / quota
    errors that adds 5-15s of dead time per call BEFORE our llm_router can
    fail over to OpenAI. Replace the decorator with a no-op so failures
    surface immediately and fallback fires fast.
    """
    try:
        from langchain_google_genai import chat_models as _gm

        def _noop_retry_decorator():
            def _identity(fn):
                return fn
            return _identity

        _gm._create_retry_decorator = _noop_retry_decorator
        logger.info("[lc_providers] disabled langchain-google-genai internal retry loop")
    except Exception as e:  # pragma: no cover — patch is best-effort
        logger.warning("[lc_providers] could not patch gemini retry: %s", e)


_disable_gemini_internal_retries()


def _llm_fallback_exception_types() -> tuple[type[BaseException], ...]:
    """
    Exceptions that should trigger trying the next LLM provider.

    Intentionally excludes broad ``Exception`` so programming errors surface
    instead of being masked by fallback. Network / quota / transient API
    failures from common HTTP + vendor SDKs are included.
    """
    types_list: list[type[BaseException]] = []
    try:
        import httpx

        types_list.extend(
            (
                httpx.HTTPStatusError,
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.ConnectTimeout,
                httpx.RemoteProtocolError,
                httpx.PoolTimeout,
            )
        )
    except Exception:
        pass
    try:
        from openai import APIConnectionError, APITimeoutError, RateLimitError

        types_list.extend((APIConnectionError, APITimeoutError, RateLimitError))
    except Exception:
        pass
    try:
        from openai import InternalServerError as OpenAIInternalServerError

        types_list.append(OpenAIInternalServerError)
    except Exception:
        pass
    try:
        from google.api_core import exceptions as google_api_exceptions

        for _name in (
            "ResourceExhausted",
            "DeadlineExceeded",
            "ServiceUnavailable",
            "TooManyRequests",
            "Aborted",
            "InternalServerError",
        ):
            _exc = getattr(google_api_exceptions, _name, None)
            if _exc is not None:
                types_list.append(_exc)
    except Exception:
        pass
    if not types_list:
        return (Exception,)
    return tuple(types_list)


_LLM_FALLBACK_EXCEPTIONS = _llm_fallback_exception_types()


# ---------------------------------------------------------------------------
# Per-provider builders
# ---------------------------------------------------------------------------

def _build_gemini_llm(max_tokens: int) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    key = (settings.gemini_api_key or "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY is not set")

    model = (settings.gemini_model or "gemini-2.5-flash").strip()
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=key,
        max_output_tokens=max_tokens,
        temperature=0.7,
        timeout=settings.llm_timeout_seconds,
        # Disable LangChain's internal retry loop. llm_router does provider-level
        # failover (gemini → openai), so per-call retries just add 30-90s of dead
        # time on quota / 429 errors before the fallback fires.
        max_retries=0,
    )


def _build_openai_llm(max_tokens: int) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    key = (settings.openai_api_key or "").strip()
    if not key:
        raise ValueError("OPENAI_API_KEY is not set")

    model = (settings.openai_model or "gpt-4o-mini").strip()
    return ChatOpenAI(
        model=model,
        api_key=key,
        max_tokens=max_tokens,
        temperature=0.7,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
    )


def _build_mistral_llm(max_tokens: int) -> BaseChatModel:
    from langchain_mistralai import ChatMistralAI

    key = (settings.mistral_api_key or "").strip()
    if not key:
        raise ValueError("MISTRAL_API_KEY is not set")

    model = (settings.mistral_model or "mistral-large-latest").strip()
    return ChatMistralAI(
        model=model,
        mistral_api_key=key,
        max_tokens=max_tokens,
        temperature=0.7,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
    )


# ---------------------------------------------------------------------------
# Provider registry — ordered fallback chains per primary
# ---------------------------------------------------------------------------

_BUILDERS = {
    "gemini":  _build_gemini_llm,
    "openai":  _build_openai_llm,
    "mistral": _build_mistral_llm,
}

_FALLBACK_ORDER: dict[str, list[str]] = {
    "gemini":  ["openai", "mistral"],
    "openai":  ["gemini", "mistral"],
    "mistral": ["gemini", "openai"],
}


def _try_build(provider: str, max_tokens: int) -> Optional[BaseChatModel]:
    """Attempt to build a provider LLM; return None if the key is missing."""
    try:
        return _BUILDERS[provider](max_tokens)
    except Exception:
        return None


def _build_fallback_list(primary_name: str, max_tokens: int) -> List[BaseChatModel]:
    """Return all available fallback LLMs in priority order (primary excluded)."""
    fallbacks: List[BaseChatModel] = []
    for candidate in _FALLBACK_ORDER.get(primary_name, []):
        llm = _try_build(candidate, max_tokens)
        if llm is not None:
            fallbacks.append(llm)
    return fallbacks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_primary_llm(max_tokens: int = 768) -> BaseChatModel:
    """Return the primary LLM configured by LLM_PROVIDER. No fallback."""
    provider = llm_provider()
    llm = _try_build(provider, max_tokens)
    if llm is None:
        raise ValueError(
            f"LLM_PROVIDER={provider!r} but the corresponding API key is not set. "
            f"Set {provider.upper()}_API_KEY in your .env."
        )
    return llm


def get_chat_llm_with_fallback(max_tokens: int = 768) -> BaseChatModel:
    """
    Return the primary LLM with available fallback(s) registered via
    LangChain's native .with_fallbacks(). Use for plain text generation
    (Pass 2, coaching chains) where tool binding is NOT required.
    """
    primary_name = llm_provider()
    logger.debug("[lc_providers] primary=%s max_tokens=%d", primary_name, max_tokens)

    primary = get_primary_llm(max_tokens)
    fallbacks = _build_fallback_list(primary_name, max_tokens)

    if not fallbacks:
        logger.warning(
            "[lc_providers] No fallback providers available (only %s key is set).",
            primary_name,
        )
        return primary

    logger.debug("[lc_providers] fallback chain: %s → %s", primary_name,
                 " → ".join(_FALLBACK_ORDER[primary_name][:len(fallbacks)]))
    return primary.with_fallbacks(fallbacks, exceptions_to_handle=_LLM_FALLBACK_EXCEPTIONS)


def get_chat_llm_with_tools_and_fallback(
    tools: Sequence[BaseTool],
    max_tokens: int = 768,
) -> BaseChatModel:
    """
    Return a tool-calling LLM with fallback for the agent's tool-calling step.

    IMPORTANT: Tools must be bound to each provider BEFORE creating the
    fallback chain. Calling .bind_tools() on a with_fallbacks() wrapper
    only binds tools to the outermost (primary) model — fallback models
    would run without tools and cannot emit tool calls.

    This function binds tools to each provider individually, then chains
    them: primary_with_tools.with_fallbacks([fallback_with_tools, ...])
    """
    primary_name = llm_provider()
    logger.debug("[lc_providers] tools+fallback primary=%s tools=%d",
                 primary_name, len(tools))

    primary_llm = get_primary_llm(max_tokens)
    primary_with_tools = primary_llm.bind_tools(tools)

    fallback_llms = _build_fallback_list(primary_name, max_tokens)
    if not fallback_llms:
        logger.warning(
            "[lc_providers] No fallback for tool-calling (only %s key is set).",
            primary_name,
        )
        return primary_with_tools

    fallbacks_with_tools = [llm.bind_tools(tools) for llm in fallback_llms]
    logger.debug("[lc_providers] tool fallback chain: %s → %s", primary_name,
                 " → ".join(_FALLBACK_ORDER[primary_name][:len(fallbacks_with_tools)]))
    return primary_with_tools.with_fallbacks(
        fallbacks_with_tools, exceptions_to_handle=_LLM_FALLBACK_EXCEPTIONS
    )


# ---------------------------------------------------------------------------
# Sync LLM factories — for use inside asyncio.to_thread (schedule gen, coaching)
# ---------------------------------------------------------------------------

def get_sync_json_llm(max_tokens: int = 4096) -> BaseChatModel:
    """
    Synchronous LLM with JSON output mode.
    Call via asyncio.to_thread(lambda: get_sync_json_llm().invoke(prompt)).
    """
    provider = llm_provider()
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        key = (settings.openai_api_key or "").strip()
        if not key:
            raise ValueError("OPENAI_API_KEY is not set")
        return ChatOpenAI(
            model=(settings.openai_model or "gpt-4o-mini").strip(),
            api_key=key,
            max_tokens=max_tokens,
            temperature=0.2,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    if provider == "mistral":
        from langchain_mistralai import ChatMistralAI
        key = (settings.mistral_api_key or "").strip()
        if not key:
            raise ValueError("MISTRAL_API_KEY is not set")
        return ChatMistralAI(
            model=(settings.mistral_model or "mistral-large-latest").strip(),
            mistral_api_key=key,
            max_tokens=max_tokens,
            temperature=0.2,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    from langchain_google_genai import ChatGoogleGenerativeAI
    key = (settings.gemini_api_key or "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY is not set")
    return ChatGoogleGenerativeAI(
        model=(settings.gemini_model or "gemini-2.5-flash").strip(),
        google_api_key=key,
        max_output_tokens=max_tokens,
        temperature=0.2,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
        generation_config={"response_mime_type": "application/json"},
    )


def get_sync_plain_llm(max_tokens: int = 512) -> BaseChatModel:
    """Synchronous plain-text LLM. Call via asyncio.to_thread."""
    return get_primary_llm(max_tokens=max_tokens)


# ---------------------------------------------------------------------------
# Vision LLM — multimodal, for image analysis (face scans, triple photos)
# ---------------------------------------------------------------------------

def get_vision_llm(json_mode: bool = False) -> BaseChatModel:
    """
    Return a multimodal LLM for image analysis.

    Gemini is preferred for vision; falls back to OpenAI gpt-4o if Gemini key
    is missing. Mistral does not support vision — falls back to Gemini/OpenAI.
    json_mode=True enables structured JSON output (for scan parsing).
    """
    provider = llm_provider()

    if provider == "mistral":
        gemini_key = (settings.gemini_api_key or "").strip()
        if gemini_key:
            provider = "gemini"
        else:
            openai_key = (settings.openai_api_key or "").strip()
            if openai_key:
                provider = "openai"
            else:
                raise ValueError("Vision requires GEMINI_API_KEY or OPENAI_API_KEY")

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        key = (settings.openai_api_key or "").strip()
        if not key:
            raise ValueError("OPENAI_API_KEY is not set")
        vision_model = getattr(settings, "openai_vision_model", None) or settings.openai_model or "gpt-4o"
        kwargs: dict = dict(model=vision_model.strip(), api_key=key, max_tokens=4096, temperature=0.1)
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(**kwargs)

    from langchain_google_genai import ChatGoogleGenerativeAI
    key = (settings.gemini_api_key or "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY is not set")
    gen_cfg: dict = {}
    if json_mode:
        gen_cfg["response_mime_type"] = "application/json"
    return ChatGoogleGenerativeAI(
        model=(settings.gemini_model or "gemini-2.5-flash").strip(),
        google_api_key=key,
        max_output_tokens=4096,
        temperature=0.1,
        **({"generation_config": gen_cfg} if gen_cfg else {}),
    )
