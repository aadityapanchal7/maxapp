"""One-off diagnostic: connect exactly like the backend does and print what it sees."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from db.sqlalchemy import engine


async def main():
    async with engine.connect() as conn:
        r = await conn.execute(text(
            "select current_database() as db, current_user as usr, "
            "inet_server_addr()::text as host, current_setting('server_version') as ver"
        ))
        print("CONNECTION:", dict(r.mappings().one()))

        r = await conn.execute(text(
            "select table_schema, table_name from information_schema.tables "
            "where table_name in ('kb_chunks','app_users','scheduled_notifications','partner_rules') "
            "order by table_name"
        ))
        print("\nTABLES visible:")
        for row in r.mappings():
            print(f"  {row['table_schema']}.{row['table_name']}")

        r = await conn.execute(text("show search_path"))
        print(f"\nsearch_path: {r.scalar()}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
