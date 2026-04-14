"""End-to-end test of process_chat_message against a real user row.

Exercises: DB session, user loading, active schedule lookup, RAG retrieval,
persona preamble, partner rule matching, agent tool call, chat_history save.

Usage:
    # Use an existing user email
    python scripts/test_chat_e2e.py --email you@example.com "how do i debloat"

    # Force a maxx context even without an active schedule
    python scripts/test_chat_e2e.py --email you@example.com --maxx skinmax "how do i debloat"

    # Explicit start-schedule kickoff (matches the app button flow)
    python scripts/test_chat_e2e.py --email you@example.com --maxx hairmax --intent start_schedule "I want to start my HairMax schedule."
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from api.chat import process_chat_message
from db.sqlalchemy import AsyncSessionLocal, engine
from models.sqlalchemy_models import User


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("message", help="Message the user sends")
    parser.add_argument("--email", required=True, help="Email of an existing app_users row")
    parser.add_argument("--maxx", default=None, help="Override init_context to force a maxx (e.g. skinmax)")
    parser.add_argument("--intent", default=None, help="Optional explicit chat_intent, e.g. start_schedule")
    parser.add_argument("--channel", default="app", choices=["app", "sms"])
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == args.email))).scalar_one_or_none()
        if not user:
            print(f"No user with email {args.email}")
            await engine.dispose()
            return

        print(f"[user] id={user.id} email={user.email} coaching_tone={user.coaching_tone}")
        print(f">>> {args.message}\n")

        text, choices = await process_chat_message(
            user_id=str(user.id),
            message_text=args.message,
            db=db,
            rds_db=None,
            init_context=args.maxx,
            chat_intent=args.intent,
            channel=args.channel,
        )
        print(f"<<< {text}")
        if choices:
            print(f"    choices: {choices}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
