"""One-off: add is_scan_user column to app_users."""
import asyncio
import os
import sys

# Ensure we're importing from backend/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from sqlalchemy import text
from db.sqlalchemy import engine


async def main():
    async with engine.begin() as conn:
        await conn.execute(text("SET lock_timeout = '10s'"))
        await conn.execute(text(
            "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS is_scan_user BOOLEAN DEFAULT FALSE"
        ))
    print("[OK] is_scan_user column ensured on app_users")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
