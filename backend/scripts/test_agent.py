"""Minimal agent smoke test — calls run_chat_agent with no DB or user.

Good for:
- Confirming the LLM provider + API keys are wired up
- Seeing the raw system prompt the agent gets
- Testing tool definitions without hitting Supabase

Not testing: RAG retrieval (needs active schedule), schedule tools (need DB),
persistence (no ChatHistory writes). For the full flow, use test_chat_e2e.py.

Usage:
    python scripts/test_agent.py "how do i debloat my face"
    python scripts/test_agent.py "what is mewing" --maxx bonemax
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.lc_agent import run_chat_agent


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("message", help="User message to send")
    parser.add_argument("--maxx", default=None, help="Optional maxx_id context (skinmax, bonemax, …)")
    parser.add_argument("--channel", default="app", choices=["app", "sms"])
    args = parser.parse_args()

    # Empty user_context — no coaching state, no RAG, no tone
    user_context = {"coaching_context": "", "active_schedule": None, "onboarding": {}}

    # No tools = plain chat, agent just answers directly
    tools: list = []

    print(f"\n>>> USER: {args.message}")
    response, mutated = await run_chat_agent(
        message=args.message,
        lc_history=[],
        user_context=user_context,
        image_data=None,
        delivery_channel=args.channel,
        tools=tools,
        db=None,
        maxx_id=args.maxx,
    )
    print(f"\n<<< ASSISTANT: {response}")
    print(f"\n[schedule_mutated={mutated}]")


if __name__ == "__main__":
    asyncio.run(main())
