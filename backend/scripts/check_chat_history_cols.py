"""Check chat_history columns and run the migration if missing."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.sqlalchemy import engine, _run_chat_history_column_migrations
from sqlalchemy import text


async def list_cols(label):
    async with engine.connect() as c:
        rows = await c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='chat_history' ORDER BY column_name"
        ))
        cols = [r[0] for r in rows]
    print(f"[{label}] chat_history columns: {cols}")
    for needed in ("channel", "retrieved_chunk_ids", "partner_rule_ids"):
        marker = "OK" if needed in cols else "MISSING"
        print(f"  {marker}: {needed}")
    return cols


async def main():
    print("=== BEFORE migration ===")
    await list_cols("before")
    print("\n=== Running _run_chat_history_column_migrations ===")
    await _run_chat_history_column_migrations()
    print("\n=== AFTER migration ===")
    await list_cols("after")
    await engine.dispose()


asyncio.run(main())
