"""
SQLAlchemy Database Connection Manager
Async PostgreSQL via Supabase
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
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
        "server_settings": {"application_name": "cannonapp_backend"}
    }
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
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
        print("[OK] Database tables created/verified")
    except Exception as e:
        print(f"[WARNING] Could not initialize database: {e}")
        print("[INFO] This is OK during development. Ensure Supabase is accessible from deployment environment.")


async def close_db():
    """Close database connections"""
    try:
        await engine.dispose()
        print("[OK] Database connection closed")
    except Exception:
        pass
