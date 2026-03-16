"""
Seed Script — Test Module for Schedule & Notification Testing
Creates a simple test course with AI guidelines for verifying the schedule system.

Usage:
    cd backend
    .\\venv\\Scripts\\python.exe scripts/seed_jawline_module.py
"""

import asyncio
import sys
import os

# Add parent directory to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.mongo import mongo_client, get_database


TEST_COURSE = {
    "title": "Schedule Test Module",
    "description": "A test course for verifying AI schedule generation and WhatsApp notifications. Contains a single module with sample guidelines.",
    "category": "mindset",
    "thumbnail_url": None,
    "difficulty": "beginner",
    "estimated_weeks": 1,
    "is_active": True,
    "modules": [
        {
            "module_number": 1,
            "title": "Daily Wellness Routine",
            "description": "A simple daily routine to test schedule generation — includes morning, midday, and evening tasks.",
            "unlock_after_days": 0,
            "guidelines": {
                "exercises": [
                    "Morning stretch",
                    "Hydration check",
                    "Breathing exercise",
                    "Evening reflection",
                ],
                "frequency_hints": [
                    "Morning stretch: once daily upon waking",
                    "Hydration check: every 3 hours",
                    "Breathing exercise: 2x daily (morning and afternoon)",
                    "Evening reflection: once before bed",
                ],
                "duration_ranges": [
                    "Morning stretch: 5-10 min",
                    "Hydration check: 1 min",
                    "Breathing exercise: 5 min",
                    "Evening reflection: 5-10 min",
                ],
                "tips": [
                    "Keep tasks short and simple for testing",
                    "Space tasks throughout the day",
                    "Include at least one reminder-type task",
                    "Make it achievable so completion stats look good",
                ],
                "difficulty_progression": "steady",
                "focus_areas": ["wellness", "hydration", "mindfulness"],
            },
            "chapters": [
                {
                    "chapter_id": "test-m1-c1",
                    "title": "Getting Started",
                    "description": "Overview of the daily wellness routine.",
                    "type": "text",
                    "content": "This is a test module for verifying schedule generation and notifications.",
                    "duration_minutes": 5,
                    "instructions": ["Follow the generated schedule", "Mark tasks as complete"],
                    "tips": ["Use this to verify WhatsApp notifications arrive on time"],
                },
            ],
        },
    ],
}


async def seed():
    """Seed the test course"""
    from datetime import datetime

    await mongo_client.connect()
    db = get_database()

    # Check if already seeded
    existing = await db.courses.find_one({"title": "Schedule Test Module"})
    if existing:
        print(f"✅ Schedule Test Module already exists (id: {existing['_id']})")
        print("   Delete it first if you want to re-seed:")
        print("   db.courses.deleteOne({title: 'Schedule Test Module'})")
        await mongo_client.disconnect()
        return

    course = TEST_COURSE.copy()
    course["created_at"] = datetime.utcnow()
    course["updated_at"] = datetime.utcnow()

    result = await db.courses.insert_one(course)
    print(f"✅ Schedule Test Module seeded successfully!")
    print(f"   Course ID: {result.inserted_id}")
    print(f"   Modules: {len(course['modules'])}")
    print(f"\n   Use this course ID to test schedule generation via the API:")
    print(f"   POST /api/schedules/generate")
    print(f'   {{"course_id": "{result.inserted_id}", "module_number": 1, "num_days": 3}}')

    await mongo_client.disconnect()


if __name__ == "__main__":
    asyncio.run(seed())
