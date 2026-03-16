"""
MongoDB Connection Manager
Uses Motor for async MongoDB operations
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
import certifi
from config import settings


class MongoDBClient:
    """Singleton MongoDB client manager"""
    
    _client: Optional[AsyncIOMotorClient] = None
    _database: Optional[AsyncIOMotorDatabase] = None
    
    @classmethod
    async def connect(cls) -> None:
        """Initialize MongoDB connection"""
        if cls._client is None:
            # Use certifi for SSL/TLS verification (common requirement on Windows)
            # Added tlsAllowInvalidCertificates=True for diagnostics
            cls._client = AsyncIOMotorClient(
                settings.mongodb_uri,
                tlsCAFile=certifi.where(),
                tlsAllowInvalidCertificates=True
            )
            cls._database = cls._client[settings.mongodb_database]
            
            # Create indexes
            await cls._create_indexes()
            
            print(f"✅ Connected to MongoDB: {settings.mongodb_database}")
    
    @classmethod
    async def disconnect(cls) -> None:
        """Close MongoDB connection"""
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            cls._database = None
            print("🔌 Disconnected from MongoDB")
    
    @classmethod
    def get_database(cls) -> AsyncIOMotorDatabase:
        """Get database instance"""
        if cls._database is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return cls._database
    
    @classmethod
    async def _create_indexes(cls) -> None:
        """Create database indexes for performance"""
        db = cls._database
        
        # Users collection indexes
        await db.users.create_index("email", unique=True)
        
        # Scans collection indexes
        await db.scans.create_index("user_id")
        await db.scans.create_index([("user_id", 1), ("created_at", -1)])
        
        # Payments collection indexes
        await db.payments.create_index("user_id")
        await db.payments.create_index("stripe_session_id", unique=True, sparse=True)
        await db.payments.create_index("stripe_subscription_id", sparse=True)
        
        # Courses collection indexes
        await db.courses.create_index("category")
        await db.courses.create_index("is_active")
        
        # User course progress indexes
        await db.user_course_progress.create_index([("user_id", 1), ("course_id", 1)], unique=True)
        
        # Events collection indexes
        await db.events.create_index("scheduled_at")
        await db.events.create_index("is_live")
        
        # Forums indexes
        await db.forums.create_index("slug", unique=True)
        await db.forum_threads.create_index("forum_id")
        await db.forum_threads.create_index([("forum_id", 1), ("created_at", -1)])
        await db.forum_replies.create_index("thread_id")
        
        # Leaderboard indexes
        await db.leaderboard.create_index("user_id", unique=True)
        await db.leaderboard.create_index([("score", -1)])
        await db.leaderboard.create_index([("rank", 1)])
        
        # Chat history indexes
        await db.chat_history.create_index("user_id")
        await db.chat_history.create_index([("user_id", 1), ("created_at", -1)])

        # Progress photos indexes
        await db.user_progress_photos.create_index("user_id")
        await db.user_progress_photos.create_index([("user_id", 1), ("created_at", -1)])
        
        print("📊 Database indexes created")


# Convenience functions
mongo_client = MongoDBClient()


def get_database() -> AsyncIOMotorDatabase:
    """Get database instance for dependency injection"""
    return MongoDBClient.get_database()
