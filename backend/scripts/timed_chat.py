"""Time each phase of process_chat_message by monkey-patching key calls."""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from db.sqlalchemy import AsyncSessionLocal, engine
from models.sqlalchemy_models import User
from api import chat as chat_mod

def _wrap(label, async_fn):
    async def wrapper(*a, **kw):
        t = time.perf_counter()
        try:
            return await async_fn(*a, **kw)
        finally:
            print(f"[t] {label}: {time.perf_counter()-t:.2f}s")
    return wrapper


async def main():
    email = sys.argv[1] if len(sys.argv) > 1 else "sameerbicha@gmail.com"
    msg = sys.argv[2] if len(sys.argv) > 2 else "what's my schedule today"

    # Monkey-patch timing into the module references used by chat.py
    chat_mod.run_chat_agent = _wrap("run_chat_agent", chat_mod.run_chat_agent)
    chat_mod.rag_retrieve_chunks = _wrap("rag_retrieve_chunks", chat_mod.rag_retrieve_chunks)
    chat_mod.answer_from_rag = _wrap("answer_from_rag", chat_mod.answer_from_rag)

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            print(f"no user {email}")
            return
        user_id = str(user.id)
        print(f"[user] id={user_id} email={user.email}")

        print(f">>> {msg}")
        t0 = time.perf_counter()
        text, choices = await chat_mod.process_chat_message(
            user_id=user_id, message_text=msg, db=db, rds_db=None, channel="app",
        )
        print(f"[t] TOTAL: {time.perf_counter()-t0:.2f}s")
        print(f"<<< {text}")

    await engine.dispose()


asyncio.run(main())
