"""Simulate a full schedule-start conversation through the graph.

Turn 1: "yea i want to start skinmax"           → agent asks for concern
Turn 2: "acne"                                  → agent calls generate_maxx_schedule

Prints each turn's response, intent classification, and graph timings.

Usage:
    python scripts/test_schedule_flow.py --email you@example.com --maxx skinmax
    python scripts/test_schedule_flow.py --email you@example.com --maxx bonemax
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


# Reasonable second-turn answers per maxx so generate_maxx_schedule has what it needs.
FOLLOW_UPS = {
    "skinmax":   ["acne", "yes"],                         # concern, outside today
    "hairmax":   ["straight", "normal", "no", "no"],      # hair type, scalp, daily styling, thinning
    "bonemax":   ["3-4", "no", "no", "yes"],              # workout freq, tmj, gum, screen time
    "heightmax": ["22", "male", "5'10"],                  # age, sex, height
    "fitmax":    ["lean out"],                            # concern
}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--maxx", required=True, choices=list(FOLLOW_UPS.keys()))
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == args.email))).scalar_one_or_none()
        if not user:
            print(f"No user with email {args.email}")
            await engine.dispose()
            return

        print(f"[user] id={user.id} email={user.email}\n")

        turns = [f"yea i want to start {args.maxx}"] + FOLLOW_UPS[args.maxx]
        for i, msg in enumerate(turns, 1):
            print(f"--- turn {i} ---")
            print(f">>> {msg}")
            text, choices = await process_chat_message(
                user_id=str(user.id),
                message_text=msg,
                db=db,
                rds_db=None,
                init_context=args.maxx if i == 1 else None,
                channel="app",
            )
            print(f"<<< {text}")
            if choices:
                print(f"    choices: {choices}")
            print()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
