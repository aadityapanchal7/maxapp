"""
SQLAlchemy Database Connection Manager
Async PostgreSQL via Supabase (user-specific data)
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from typing import AsyncGenerator
from config import settings


# Create async engine for Supabase
engine = create_async_engine(
    settings.supabase_db_url,
    echo=settings.debug,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args={
        "timeout": 30,
        "ssl": "require",
        "server_settings": {"application_name": "maxapp_backend"},
    },
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
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except BaseException:
            # Failed flush/commit leaves session in "needs rollback" state; clear before close.
            try:
                await session.rollback()
            except Exception:
                pass
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    try:
        await _terminate_stale_connections()

        from models.sqlalchemy_models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("[OK] Supabase tables created/verified")

        # app_users alters in their own transaction so a lock failure on other tables
        # cannot roll back critical columns (e.g. last_username_change).
        await _run_app_users_column_migrations()
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
    ]
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '30s'"))
            for sql in statements:
                await conn.execute(text(sql))
        print("[OK] app_users column migrations applied")
    except Exception as e:
        print(f"[WARNING] app_users column migrations: {e}")


async def _run_column_migrations():
    """Add missing columns to existing tables (safe to run repeatedly)."""
    migrations = [
        "ALTER TABLE user_progress_photos ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'app'",
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


async def close_db():
    """Close database connections"""
    try:
        await engine.dispose()
        print("[OK] Supabase connection closed")
    except Exception:
        pass
