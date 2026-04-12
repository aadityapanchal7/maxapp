"""
Chat history adapter for LangChain.

Converts existing chat_history table rows (SQLAlchemy ChatHistory ORM objects
or plain dicts with "role"/"content" keys) into LangChain BaseMessage objects
(HumanMessage / AIMessage) so they can be injected into LCEL chain prompts
via the MessagesPlaceholder("history") slot.

Why not SQLChatMessageHistory directly?
  The existing chat_history table has a "channel" column (app vs sms) that is
  used for filtering, and writes go through the SQLAlchemy ORM in chat.py.
  SQLChatMessageHistory expects its own schema and owns its own connection.
  This adapter keeps the existing persistence layer intact.
"""

from __future__ import annotations

from typing import List, Union

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


class MaxChatMemory:
    """
    Lightweight adapter: converts chat_history rows → LangChain messages.

    Accepts either:
      - SQLAlchemy ChatHistory ORM instances (have .role / .content attrs)
      - Plain dicts with "role" and "content" keys (as used in llm_router)
    """

    def __init__(self, rows: list) -> None:
        self._rows = rows

    @classmethod
    def from_db_rows(cls, rows: list) -> "MaxChatMemory":
        """Construct from a list of ChatHistory ORM objects or dicts."""
        return cls(rows)

    def as_lc_messages(self) -> List[BaseMessage]:
        """
        Return rows as a list of HumanMessage / AIMessage objects.

        role == "user"      → HumanMessage
        role == "assistant" → AIMessage
        anything else is skipped.
        """
        messages: List[BaseMessage] = []
        for row in self._rows:
            if isinstance(row, dict):
                role = row.get("role", "")
                content = row.get("content") or ""
            else:
                role = getattr(row, "role", "")
                content = getattr(row, "content", "") or ""

            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

        return messages


def history_dicts_to_lc_messages(chat_history: list[dict]) -> List[BaseMessage]:
    """
    Convenience function: convert a list of {"role": ..., "content": ...} dicts
    directly to LangChain BaseMessage objects.

    Used by llm_router._lc_chat() to prepare the history placeholder.
    """
    return MaxChatMemory.from_db_rows(chat_history).as_lc_messages()
