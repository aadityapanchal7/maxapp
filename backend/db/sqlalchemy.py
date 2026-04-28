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
    echo=getattr(settings, "sql_echo", False),
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
        tables_to_create = list(Base.metadata.sorted_tables)
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
        # subscription_id was unique but Apple reuses originalTransactionId across renewals
        "ALTER TABLE app_users DROP CONSTRAINT IF EXISTS app_users_subscription_id_key",
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
    """Add chat_history columns + multi-conversation wiring.

    Each migration runs in its OWN transaction so a failure in one can't roll
    back the others. Previously the conversation_id FK + backfill block was
    grouped with the basic-column adds in a single transaction — if Supabase
    perms or `chat_conversations` not-yet-existing made the FK ALTER fail,
    `retrieved_chunk_ids` and `conversation_id` itself both rolled back too.
    Production hit exactly this and queries that selected `conversation_id`
    started 500ing.

    retrieved_chunk_ids: the RAG refactor changed the column type from
    BIGINT[] to JSONB. We only drop+re-add it when the existing type is
    not already JSONB so the audit trail isn't wiped on every boot.
    """
    # ---- 1. Basic columns. These must succeed independently of any other
    # table's existence. -----------------------------------------------------
    basic_statements = [
        "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS channel VARCHAR DEFAULT 'app'",
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'chat_history'
                  AND column_name = 'retrieved_chunk_ids'
                  AND data_type <> 'jsonb'
            ) THEN
                ALTER TABLE chat_history DROP COLUMN retrieved_chunk_ids;
            END IF;
        END $$;
        """,
        "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS retrieved_chunk_ids JSONB",
        "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS partner_rule_ids BIGINT[]",
    ]
    for sql in basic_statements:
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SET lock_timeout = '30s'"))
                await conn.execute(text(sql))
        except Exception as e:
            print(f"[WARNING] chat_history basic migration failed: {e}")

    # ---- 2. Ensure chat_conversations table exists. create_all() should
    # have done this from the ORM model, but if Supabase RLS or a transient
    # error blocked it, we recreate it here from the canonical SQL so the
    # subsequent FK + index + backfill don't fail with "relation does not
    # exist". ----------------------------------------------------------------
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '30s'"))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS public.chat_conversations (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id uuid NOT NULL,
                    title varchar(120) NOT NULL DEFAULT 'new chat',
                    is_archived boolean NOT NULL DEFAULT false,
                    last_message_at timestamptz,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_chat_conversations_user
                    ON public.chat_conversations(user_id, is_archived, last_message_at DESC)
            """))
    except Exception as e:
        print(f"[WARNING] chat_conversations bootstrap failed: {e}")

    # ---- 3. Add conversation_id column WITHOUT the FK constraint first.
    # The column is what the ORM SELECTs reference — it must exist even if
    # the FK can't be installed (e.g. permission lockouts, lock contention).
    # -----------------------------------------------------------------------
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '30s'"))
            await conn.execute(text(
                "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS conversation_id uuid"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_chat_history_conversation "
                "ON chat_history(conversation_id, created_at)"
            ))
        print("[OK] chat_history.conversation_id column ensured")
    except Exception as e:
        print(f"[WARNING] chat_history.conversation_id column add failed: {e}")

    # ---- 4. Best-effort: install FK constraint pointing at chat_conversations.
    # If this fails (e.g. orphan rows, permissions), we keep the column
    # without referential integrity rather than blowing up the whole boot.
    # -----------------------------------------------------------------------
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '30s'"))
            await conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE table_name = 'chat_history'
                          AND constraint_name = 'chat_history_conversation_id_fkey'
                    ) AND EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'chat_conversations'
                    ) THEN
                        ALTER TABLE chat_history
                            ADD CONSTRAINT chat_history_conversation_id_fkey
                            FOREIGN KEY (conversation_id)
                            REFERENCES chat_conversations(id)
                            ON DELETE CASCADE;
                    END IF;
                END $$;
            """))
    except Exception as e:
        print(f"[WARNING] chat_history.conversation_id FK install skipped: {e}")

    # ---- 5. One-time backfill so legacy rows have a thread to live in.
    # Each runs idempotently — the WHERE clauses guard on conversation_id
    # IS NULL, so re-running is a no-op once everything is migrated.
    # -----------------------------------------------------------------------
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '30s'"))
            await conn.execute(text("""
                INSERT INTO chat_conversations (user_id, title, last_message_at)
                SELECT ch.user_id, 'Chat history', MAX(ch.created_at)
                FROM chat_history ch
                WHERE ch.conversation_id IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM chat_conversations cc
                      WHERE cc.user_id = ch.user_id
                  )
                GROUP BY ch.user_id
            """))
            await conn.execute(text("""
                UPDATE chat_history ch
                SET conversation_id = cc.id
                FROM chat_conversations cc
                WHERE ch.conversation_id IS NULL
                  AND cc.user_id = ch.user_id
                  AND cc.title = 'Chat history'
            """))
        print("[OK] chat_history conversation_id backfill complete")
    except Exception as e:
        print(f"[WARNING] chat_history conversation_id backfill skipped: {e}")


async def _run_column_migrations():
    """Add missing columns to existing tables (safe to run repeatedly).

    Each migration runs in its own transaction so a lock timeout or failure on
    one table (e.g. user_schedules held by another session) does not abort the
    others.
    """
    migrations = [
        "ALTER TABLE user_progress_photos ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'app'",
        "ALTER TABLE user_progress_photos ADD COLUMN IF NOT EXISTS face_rating DOUBLE PRECISION",
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS schedule_type VARCHAR DEFAULT 'course'",
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS maxx_id VARCHAR",
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS schedule_context JSONB DEFAULT '{}'",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS is_scan_user BOOLEAN DEFAULT FALSE",
        "ALTER TABLE user_schedules ALTER COLUMN course_id DROP NOT NULL",
        "ALTER TABLE user_schedules ALTER COLUMN module_number DROP NOT NULL",
    ]
    applied = 0
    for sql in migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SET lock_timeout = '5s'"))
                await conn.execute(text(sql))
            applied += 1
        except Exception as e:
            print(f"[INFO] Column migration skipped ({sql[:80]}...): {e}")
    print(f"[OK] Column migrations applied ({applied}/{len(migrations)})")

    # rag_documents.embedding → nullable so content can be added/edited without vectors
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '5s'"))
            await conn.execute(text(
                "ALTER TABLE rag_documents ALTER COLUMN embedding DROP NOT NULL"
            ))
        print("[OK] rag_documents.embedding made nullable")
    except Exception as e:
        print(f"[INFO] rag_documents embedding migration note: {e}")

async def close_db():
    """Close database connections"""
    try:
        await engine.dispose()
        print("[OK] Supabase connection closed")
    except Exception:
        pass
