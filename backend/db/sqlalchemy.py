"""
SQLAlchemy Database Connection Manager
Async PostgreSQL via Supabase (user-specific data)
"""

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from typing import AsyncGenerator
from config import settings


def _clean_asyncpg_url(raw_url: str) -> str:
    """Strip query params that asyncpg doesn't understand (e.g. ?pgbouncer=true)."""
    parsed = urlparse(raw_url)
    if not parsed.query:
        return raw_url
    known = {"ssl", "sslmode", "sslcert", "sslkey", "sslrootcert", "sslpassword"}
    qs = parse_qs(parsed.query)
    filtered = {k: v for k, v in qs.items() if k.lower() in known}
    clean = parsed._replace(query=urlencode(filtered, doseq=True) if filtered else "")
    return urlunparse(clean)


def _supabase_connect_args() -> dict:
    """
    Supabase Session pooler (5432) allows very few client slots → MaxClientsInSessionMode.
    Prefer Transaction pooler (6543) in Supabase Dashboard → Connect → Transaction mode.
    asyncpg must disable statement cache through Supabase pooler hosts (PgBouncer).
    """
    args: dict = {
        "timeout": 10,
        "ssl": "require",
        "server_settings": {
            "application_name": "maxapp_backend",
            # Force `extensions` onto search_path so pgvector's `vector` type resolves
            # unqualified. Supabase installs the extension into `extensions`, not `public`,
            # and the default role search_path doesn't include it.
            "search_path": "public,extensions",
        },
    }
    port = getattr(settings, "supabase_db_port", 5432)
    host = (getattr(settings, "supabase_db_host", "") or "").lower()
    if port == 6543 or "pooler.supabase" in host:
        args["statement_cache_size"] = 0
    return args


engine = create_async_engine(
    _clean_asyncpg_url(settings.supabase_db_url),
    echo=settings.debug,
    pool_size=settings.supabase_db_pool_size,
    max_overflow=settings.supabase_db_max_overflow,
    pool_recycle=180,
    pool_timeout=10,
    pool_pre_ping=True,
    connect_args=_supabase_connect_args(),
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection for database sessions
    Usage: db: AsyncSession = Depends(get_db)

    Use a plain `yield` inside `async with` only. Extra try/finally + session.close()
    duplicates the context manager exit and can break FastAPI's generator cleanup
    (RuntimeError: generator didn't stop after athrow()).
    """
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Initialize database tables"""
    try:
        await _terminate_stale_connections()

        from models.sqlalchemy_models import Base
        # RAG is file-based now (backend/rag_content/), so rag_documents is not needed.
        # Skip it from create_all to avoid the VECTOR type check that fails through Supabase's pooler.
        tables_to_create = [t for t in Base.metadata.sorted_tables if t.name != "rag_documents"]
        async with engine.begin() as conn:
            await conn.execute(text("SET search_path TO public, extensions"))
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables_to_create)
            )
        print("[OK] Supabase tables created/verified")

        # app_users alters in their own transaction so a lock failure on other tables
        # cannot roll back critical columns (e.g. last_username_change).
        await _run_app_users_column_migrations()
        await _run_chat_history_column_migrations()
        await _run_column_migrations()
    except Exception as e:
        print(f"[WARNING] Could not initialize Supabase database: {e}")
        print("[INFO] Ensure Supabase is accessible from deployment environment.")


async def _terminate_stale_connections():
    """Kill leftover connections from a previous server instance that may hold locks."""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE application_name = 'maxapp_backend' "
                "AND pid <> pg_backend_pid() "
                "AND state IN ('idle', 'idle in transaction', 'idle in transaction (aborted)')"
            ))
            terminated = result.rowcount
            if terminated:
                print(f"[OK] Terminated {terminated} stale backend connection(s)")
    except Exception as e:
        print(f"[INFO] Could not clean stale connections: {e}")


async def _run_app_users_column_migrations():
    """Add app_users columns in a dedicated transaction (commits even if other migrations fail)."""
    statements = [
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS last_username_change TIMESTAMPTZ",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS ai_context TEXT DEFAULT ''",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS ai_summaries JSONB DEFAULT '[]'",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS apns_device_token TEXT",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS apns_token_updated_at TIMESTAMPTZ",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS coaching_tone VARCHAR DEFAULT 'default'",
    ]
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '30s'"))
            for sql in statements:
                await conn.execute(text(sql))
        print("[OK] app_users column migrations applied")
    except Exception as e:
        print(f"[WARNING] app_users column migrations: {e}")


async def _run_chat_history_column_migrations():
    """Add chat_history columns in a dedicated transaction so they commit even if other migrations fail."""
    statements = [
        "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS channel VARCHAR DEFAULT 'app'",
        "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS retrieved_chunk_ids TEXT[]",
        "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS partner_rule_ids BIGINT[]",
    ]
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '30s'"))
            for sql in statements:
                await conn.execute(text(sql))
        print("[OK] chat_history column migrations applied")
    except Exception as e:
        print(f"[WARNING] chat_history column migrations: {e}")


async def _run_column_migrations():
    """Add missing columns to existing tables (safe to run repeatedly)."""
    migrations = [
        "ALTER TABLE user_progress_photos ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'app'",
        "ALTER TABLE user_progress_photos ADD COLUMN IF NOT EXISTS face_rating DOUBLE PRECISION",
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS schedule_type VARCHAR DEFAULT 'course'",
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS maxx_id VARCHAR",
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS schedule_context JSONB DEFAULT '{}'",
    ]
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '5s'"))
            for sql in migrations:
                await conn.execute(text(sql))
            await conn.execute(text(
                "ALTER TABLE user_schedules ALTER COLUMN course_id DROP NOT NULL"
            ))
            await conn.execute(text(
                "ALTER TABLE user_schedules ALTER COLUMN module_number DROP NOT NULL"
            ))
        print("[OK] Column migrations applied")
    except Exception as e:
        print(f"[INFO] Column migration note: {e}")

    # RAG is now file-based (backend/rag_content/<maxx_id>/*.md). No DB indexes needed.


async def _run_rag_migrations():
    """Enable pgvector extension and create rag_documents table (safe to run repeatedly)."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS rag_documents (
                    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    maxx_id     VARCHAR(50)  NOT NULL,
                    doc_title   VARCHAR(255) NOT NULL,
                    chunk_index INTEGER      NOT NULL DEFAULT 0,
                    content     TEXT         NOT NULL,
                    embedding   VECTOR(1536) NOT NULL,
                    metadata    JSONB        NOT NULL DEFAULT '{}',
                    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
                    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_rag_docs_maxx_id "
                "ON rag_documents (maxx_id)"
            ))
        print("[OK] RAG migrations applied (pgvector + rag_documents)")
    except Exception as e:
        print(f"[WARNING] RAG migrations: {e}")


async def close_db():
    """Close database connections"""
    try:
        await engine.dispose()
        print("[OK] Supabase connection closed")
    except Exception:
        pass
