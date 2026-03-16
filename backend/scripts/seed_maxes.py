"""
Seed Script — Maxes Modules
Creates 5 test courses for the Maxes (Bonemax, Heightmax, Skinmax, Hairmax, Fitmax).

Usage:
    cd backend
    .\venv\Scripts\python.exe scripts/seed_maxes.py
"""

import asyncio
import sys
import os
from datetime import datetime

# Add parent directory to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.mongo import mongo_client, get_database

MAXES = [
    {
        "title": "Bonemax",
        "description": "Unlock your facial structure potential. Focus on jawline definition, facial symmetry, and overall bone health.",
        "category": "bonemax",
        "thumbnail_url": None,
        "difficulty": "beginner",
        "estimated_weeks": 4,
        "is_active": True,
        "modules": [
            {
                "module_number": 1,
                "title": "Bonemax Fundamentals",
                "description": "Daily routines for facial structure improvement including mewing, chewing, and posture.",
                "unlock_after_days": 0,
                "guidelines": {
                    "exercises": ["Mewing", "Hard Chewing", "Neck Posture Correction", "Facial Massage"],
                    "frequency_hints": ["Mewing: continuous", "Hard Chewing: 20 mins every other day", "Neck Posture: daily", "Facial Massage: before bed"],
                    "duration_ranges": ["10-20 mins active, continuous passive"],
                    "tips": ["Consistency is key for bone changes", "Do not over-chew to avoid TMJ", "Focus on tongue posture at all times"],
                    "difficulty_progression": "gradual",
                    "focus_areas": ["jawline", "cheekbones", "neck posture"]
                },
                "chapters": [
                    {
                        "chapter_id": "bonemax-m1-c1",
                        "title": "Intro to Bonemaxing",
                        "description": "Understanding the principles of facial structure adaptation.",
                        "type": "text",
                        "content": "Bonemaxing is about optimizing your facial structure...",
                        "duration_minutes": 5,
                        "instructions": ["Read the materials", "Set up your daily reminders"],
                        "tips": ["Patience is required"]
                    }
                ]
            }
        ]
    },
    {
        "title": "Heightmax",
        "description": "Optimize your height through posture, nutrition, and targeted stretching.",
        "category": "heightmax",
        "thumbnail_url": None,
        "difficulty": "intermediate",
        "estimated_weeks": 4,
        "is_active": True,
        "modules": [
            {
                "module_number": 1,
                "title": "Heightmax Fundamentals",
                "description": "Daily routines for spinal decompression and posture improvement.",
                "unlock_after_days": 0,
                "guidelines": {
                    "exercises": ["Dead Hangs", "Cobra Pose", "Pelvic Tilts", "Dietary Check"],
                    "frequency_hints": ["Dead Hangs: morning and night", "Stretching: daily", "Dietary Check: continuous"],
                    "duration_ranges": ["15 mins per session"],
                    "tips": ["Sleep is when you grow", "Maintain perfectly straight posture", "Decompress spine before bed"],
                    "difficulty_progression": "steady",
                    "focus_areas": ["spine", "posture", "sleep"]
                },
                "chapters": [
                    {
                        "chapter_id": "heightmax-m1-c1",
                        "title": "Intro to Heightmaxing",
                        "description": "Understanding height optimization.",
                        "type": "text",
                        "content": "Heightmaxing focuses on maximizing your genetic height potential...",
                        "duration_minutes": 5,
                        "instructions": ["Read the materials", "Set up your daily reminders"],
                        "tips": ["HGH is released during deep sleep"]
                    }
                ]
            }
        ]
    },
    {
        "title": "Skinmax",
        "description": "Achieve flawless skin through an optimized skincare routine, diet, and hydration.",
        "category": "skinmax",
        "thumbnail_url": None,
        "difficulty": "beginner",
        "estimated_weeks": 4,
        "is_active": True,
        "modules": [
            {
                "module_number": 1,
                "title": "Skinmax Fundamentals",
                "description": "Daily routines for clear, glowing skin.",
                "unlock_after_days": 0,
                "guidelines": {
                    "exercises": ["Cleansing", "Moisturizing", "Sunscreen Application", "Exfoliation"],
                    "frequency_hints": ["Cleansing: 2x daily", "Sunscreen: every morning", "Exfoliation: 1-2x per week"],
                    "duration_ranges": ["5-10 mins per session"],
                    "tips": ["Never skip sunscreen", "Hydration is as important as topical products", "Be gentle with your skin barrier"],
                    "difficulty_progression": "easy",
                    "focus_areas": ["face", "diet", "hydration"]
                },
                "chapters": [
                    {
                        "chapter_id": "skinmax-m1-c1",
                        "title": "Intro to Skinmaxing",
                        "description": "Understanding your skin type and needs.",
                        "type": "text",
                        "content": "Skinmaxing is about achieving the best possible complexion...",
                        "duration_minutes": 5,
                        "instructions": ["Read the materials", "Set up your daily reminders"],
                        "tips": ["Consistency is key"]
                    }
                ]
            }
        ]
    },
    {
        "title": "Hairmax",
        "description": "Optimize hair growth, thickness, and health through targeted routines.",
        "category": "hairmax",
        "thumbnail_url": None,
        "difficulty": "advanced",
        "estimated_weeks": 4,
        "is_active": True,
        "modules": [
            {
                "module_number": 1,
                "title": "Hairmax Fundamentals",
                "description": "Daily routines for scalp health and hair growth.",
                "unlock_after_days": 0,
                "guidelines": {
                    "exercises": ["Scalp Massage", "Oiling", "Derma Rolling", "Supplement Check"],
                    "frequency_hints": ["Scalp Massage: daily", "Oiling: 2x per week", "Derma Rolling: 1x per week"],
                    "duration_ranges": ["10-15 mins per session"],
                    "tips": ["Be consistent with treatments", "Don't over-wash your hair", "Ensure proper vitamin intake"],
                    "difficulty_progression": "steady",
                    "focus_areas": ["scalp", "hairline", "nutrition"]
                },
                "chapters": [
                    {
                        "chapter_id": "hairmax-m1-c1",
                        "title": "Intro to Hairmaxing",
                        "description": "Understanding hair growth cycles.",
                        "type": "text",
                        "content": "Hairmaxing focuses on preserving and enhancing hair...",
                        "duration_minutes": 5,
                        "instructions": ["Read the materials", "Set up your daily reminders"],
                        "tips": ["Treatments take months to show results"]
                    }
                ]
            }
        ]
    },
    {
        "title": "Fitmax",
        "description": "Build an aesthetic physique through optimized training and nutrition.",
        "category": "fitmax",
        "thumbnail_url": None,
        "difficulty": "intermediate",
        "estimated_weeks": 4,
        "is_active": True,
        "modules": [
            {
                "module_number": 1,
                "title": "Fitmax Fundamentals",
                "description": "Daily routines for building muscle and losing fat.",
                "unlock_after_days": 0,
                "guidelines": {
                    "exercises": ["Weightlifting", "Cardio", "Meal Prep", "Stretching"],
                    "frequency_hints": ["Weightlifting: 3-5x per week", "Cardio: 2-3x per week", "Meal Prep: daily"],
                    "duration_ranges": ["45-60 mins per session"],
                    "tips": ["Track your macros", "Progressive overload is essential", "Rest days are when you build muscle"],
                    "difficulty_progression": "progressive",
                    "focus_areas": ["physique", "strength", "nutrition"]
                },
                "chapters": [
                    {
                        "chapter_id": "fitmax-m1-c1",
                        "title": "Intro to Fitmaxing",
                        "description": "Understanding body recomposition.",
                        "type": "text",
                        "content": "Fitmaxing is about achieving an aesthetic, healthy body...",
                        "duration_minutes": 5,
                        "instructions": ["Read the materials", "Set up your daily reminders"],
                        "tips": ["Diet is 80% of the work"]
                    }
                ]
            }
        ]
    }
]

async def seed():
    """Seed the maxes courses"""
    await mongo_client.connect()
    db = get_database()

    for course_data in MAXES:
        existing = await db.courses.find_one({"title": course_data["title"]})
        if existing:
            print(f"✅ {course_data['title']} already exists (id: {existing['_id']})")
        else:
            course = course_data.copy()
            course["created_at"] = datetime.utcnow()
            course["updated_at"] = datetime.utcnow()
            result = await db.courses.insert_one(course)
            print(f"✅ Seeded {course_data['title']} (id: {result.inserted_id})")

    await mongo_client.disconnect()


if __name__ == "__main__":
    asyncio.run(seed())
