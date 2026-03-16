import asyncio
import os
import hashlib
import bcrypt
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from bson import ObjectId

# Load environment variables
load_dotenv()

# Configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DATABASE", "cannon_db")

def hash_password(password: str) -> str:
    """Hash a password with SHA-256 pre-hashing (consistent with auth.py)"""
    pre_hash = hashlib.sha256(password.encode()).hexdigest().encode()
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pre_hash, salt).decode()

async def seed_db():
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[DB_NAME]
    
    print(f"Connecting to {MONGODB_URI}, DB: {DB_NAME}")
    print("Beginning comprehensive seed process...")
    
    # 1. Clear existing data
    collections = ["users", "courses", "forums", "threads", "events", "leaderboard"]
    for col in collections:
        await db[col].delete_many({})
        print(f"Cleared {col} collection.")

    # 2. Seed Users
    print("\nSeeding Users...")
    users = [
        {
            "email": "admin@example.com",
            "password_hash": hash_password("admin123"),
            "is_admin": True,
            "is_paid": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "onboarding": {"completed": True, "goals": ["overall"], "experience_level": "advanced"},
            "profile": {"current_level": 8.5, "rank": 1, "streak_days": 15, "improvement_percentage": 25.0}
        },
        {
            "email": "user@example.com",
            "password_hash": hash_password("user1234"),
            "is_admin": False,
            "is_paid": False,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "onboarding": {"completed": True, "goals": ["jawline", "skin"], "experience_level": "beginner"},
            "profile": {"current_level": 4.2, "rank": 10, "streak_days": 3, "improvement_percentage": 5.0}
        }
    ]
    user_ids = []
    for user in users:
        result = await db.users.insert_one(user)
        user_ids.append(str(result.inserted_id))
        print(f"Created user: {user['email']}")

    # 3. Seed Courses
    print("\nSeeding Courses...")
    courses = [
        {
            "title": "Jawline Sculptor 101",
            "description": "The ultimate beginner guide to defining your jawline through mewing and chewing exercises.",
            "category": "jawline",
            "difficulty": "beginner",
            "estimated_weeks": 4,
            "modules": [
                {
                    "module_number": 1,
                    "title": "Consultation & Basics",
                    "description": "Learning proper tongue posture.",
                    "chapters": [
                        {
                            "chapter_id": "j1_c1",
                            "title": "What is Mewing?",
                            "description": "Understanding the fundamentals of tongue posture.",
                            "type": "video",
                            "video_url": "https://example.com/videos/mewing-basics.mp4",
                            "duration_minutes": 5
                        },
                        {
                            "chapter_id": "j1_c2",
                            "title": "The 'N' Spot",
                            "description": "Finding the correct position for your tongue tip.",
                            "type": "image",
                            "image_url": "https://images.unsplash.com/photo-1597223506889-498ccf1e03a4",
                            "duration_minutes": 2
                        }
                    ],
                    "unlock_after_days": 0
                }
            ],
            "is_active": True,
            "thumbnail_url": "https://images.unsplash.com/photo-1597223506889-498ccf1e03a4?w=500&auto=format&fit=crop&q=60",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
    ]
    for course in courses:
        await db.courses.insert_one(course)
        print(f"Created course: {course['title']}")

    # 4. Seed Forums & Threads
    print("\nSeeding Forums...")
    forums = [
        {"name": "General Discussion", "slug": "general", "description": "Talk about anything.", "order": 1, "icon": "chatbubbles"},
        {"name": "Announcements", "slug": "announcements", "description": "Official updates.", "order": 0, "icon": "megaphone"}
    ]
    for forum in forums:
        forum["created_at"] = datetime.utcnow()
        result = await db.forums.insert_one(forum)
        if forum["slug"] == "general":
            thread = {
                "forum_id": str(result.inserted_id),
                "user_id": user_ids[0],
                "title": "Welcome to Max!",
                "content": "Let's start our journey to better looks!",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "reply_count": 0,
                "is_pinned": True
            }
            await db.threads.insert_one(thread)
        print(f"Created forum: {forum['name']}")

    # 5. Seed Events
    print("\nSeeding Events...")
    events = [
        {
            "title": "Weekly Q&A with Style Experts",
            "description": "Get your questions answered live on TikTok.",
            "tiktok_link": "https://tiktok.com/@max_app/live",
            "scheduled_at": datetime.utcnow() + timedelta(days=2),
            "duration_minutes": 45,
            "thumbnail_url": "https://images.unsplash.com/photo-1516280440614-37939bbacd81?w=500&auto=format&fit=crop&q=60",
            "is_live": False,
            "created_at": datetime.utcnow()
        },
        {
            "title": "Skin Care Masterclass",
            "description": "Learn the 7-step glass skin routine.",
            "tiktok_link": "https://tiktok.com/@max_app/live",
            "scheduled_at": datetime.utcnow() - timedelta(days=1),
            "duration_minutes": 60,
            "is_live": False,
            "created_at": datetime.utcnow()
        }
    ]
    for event in events:
        await db.events.insert_one(event)
        print(f"Created event: {event['title']}")

    # 6. Seed Leaderboard
    print("\nSeeding Leaderboard...")
    leaderboard_entries = [
        {
            "user_id": user_ids[1], "score": 450.0, "streak_days": 3, "scan_count": 2,
            "rank": 1, "level": 4.2, "improvement_percentage": 5.0, "updated_at": datetime.utcnow()
        }
    ]
    await db.leaderboard.insert_many(leaderboard_entries)
    print("Leaderboard seeded.")

    print("\nSeed process completed successfully!")
    client.close()

if __name__ == "__main__":
    asyncio.run(seed_db())
