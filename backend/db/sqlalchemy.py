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
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    try:
        from models.sqlalchemy_models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("[OK] Supabase tables created/verified")

        # Run lightweight column migrations for new features
        await _run_column_migrations()
    except Exception as e:
        print(f"[WARNING] Could not initialize Supabase database: {e}")
        print("[INFO] Ensure Supabase is accessible from deployment environment.")


async def _run_column_migrations():
    """Add missing columns to existing tables (safe to run repeatedly)."""
    migrations = [
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS schedule_type VARCHAR DEFAULT 'course'",
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS maxx_id VARCHAR",
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS schedule_context JSONB DEFAULT '{}'",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS ai_context TEXT DEFAULT ''",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS ai_summaries JSONB DEFAULT '[]'",
    ]
    try:
        async with engine.begin() as conn:
            for sql in migrations:
                await conn.execute(text(sql))
            # Make course_id and module_number nullable if they aren't already
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
