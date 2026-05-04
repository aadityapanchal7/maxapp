"""
LCEL (LangChain Expression Language) chains for the Agartha chat pipeline and coaching.

Two-pass chat pipeline:
  Pass 1 — build_first_pass_chain(): LLM with tools bound; returns AIMessage.
            Inspect .tool_calls to decide if Pass 2 is needed.
  Pass 2 — build_second_pass_chain(): LLM without tools + tool results injected;
            returns plain text string via StrOutputParser.

Coaching helpers:
  run_coaching_compression_chain(): replaces asyncio.to_thread(sync_llm_plain_text)
  run_tone_detection_chain():       replaces asyncio.to_thread(sync_llm_plain_text)
"""

from __future__ import annotations

import logging
from typing import List

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chat prompt template
# ---------------------------------------------------------------------------

def build_chat_prompt_template() -> ChatPromptTemplate:
    """
    System prompt + conversation history placeholder + current user message.

    Input variables expected at invoke time:
        system_prompt  — full system prompt string (from prompt_loader / S3)
        history        — list[BaseMessage] (HumanMessage / AIMessage)
        user_input     — current user message string
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", "{system_prompt}"),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{user_input}"),
        ]
    )


def build_tool_results_prompt_template() -> ChatPromptTemplate:
    """
    Second-pass prompt: tool results injected into the system message.

    Tool results are placed in the system context (not as a second consecutive
    human message) for two reasons:
      1. Mistral and some other providers reject consecutive user-role messages.
      2. System-level injection treats the results as authoritative context,
         which produces more grounded responses.

    Input variables:
        system_prompt, history, user_input, tool_results
    """
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "{system_prompt}\n\n"
                "[TOOL_RESULTS — use these to write your response to the user]\n"
                "{tool_results}",
            ),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{user_input}"),
        ]
    )


# ---------------------------------------------------------------------------
# Chat chains
# ---------------------------------------------------------------------------

def build_first_pass_chain(llm_with_tools: BaseChatModel) -> Runnable:
    """
    Pass 1: detect tool calls.

    Returns the raw AIMessage (NOT parsed to str) so the caller can inspect
    .tool_calls and decide whether to execute them and run Pass 2.

    llm_with_tools should already have .bind_tools(CHAT_TOOLS) applied.
    """
    prompt = build_chat_prompt_template()
    return prompt | llm_with_tools


def build_second_pass_chain(llm: BaseChatModel) -> Runnable:
    """
    Pass 2: synthesise a user-facing response after tool execution.

    Injects tool results into the prompt and returns a plain text string.
    No tools are bound on this pass.
    """
    prompt = build_tool_results_prompt_template()
    return prompt | llm | StrOutputParser()


# ---------------------------------------------------------------------------
# Coaching LCEL chains (replace asyncio.to_thread(sync_llm_plain_text, prompt))
# ---------------------------------------------------------------------------

async def run_coaching_compression_chain(prompt: str) -> str:
    """
    Async wrapper used by coaching_service.generate_conversation_summary().

    The prompt is already fully assembled by the caller (template + convo).
    Uses the primary LLM with fallback and a hard asyncio timeout.
    """
    import asyncio
    from config import settings
    from services.lc_providers import get_chat_llm_with_fallback

    try:
        llm = get_chat_llm_with_fallback(max_tokens=512)
        chain = llm | StrOutputParser()
        result: str = await asyncio.wait_for(
            chain.ainvoke(prompt),
            timeout=float(settings.llm_timeout_seconds) * 2,
        )
        return result.strip()
    except Exception as e:
        logger.error("[lc_chains] coaching compression chain failed: %s", e)
        raise


async def run_tone_detection_chain(prompt: str) -> str:
    """
    Async wrapper used by coaching_service.detect_tone_preference().

    The prompt is already fully assembled by the caller. Returns the LLM
    output (expected to be one of: direct / aggressive / chill).
    Uses the primary LLM with fallback and a hard asyncio timeout.
    """
    import asyncio
    from config import settings
    from services.lc_providers import get_chat_llm_with_fallback

    try:
        llm = get_chat_llm_with_fallback(max_tokens=16)
        chain = llm | StrOutputParser()
        result: str = await asyncio.wait_for(
            chain.ainvoke(prompt),
            timeout=float(settings.llm_timeout_seconds) * 2,
        )
        return result.strip()
    except Exception as e:
        logger.error("[lc_chains] tone detection chain failed: %s", e)
        raise
