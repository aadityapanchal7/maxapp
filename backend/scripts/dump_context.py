"""Dump what context reaches the LLM for a given user."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from db.sqlalchemy import AsyncSessionLocal, engine
from models.sqlalchemy_models import User
from services.coaching_service import coaching_service
from services.schedule_service import schedule_service
from api.chat import _merge_onboarding_with_schedule_prefs


async def main():
    email = sys.argv[1]
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            print(f"no user {email}"); return
        uid = str(user.id)
        ctx = await coaching_service.build_full_context(uid, db, None)
        sched = await schedule_service.get_current_schedule(uid, db=db)
        ob = _merge_onboarding_with_schedule_prefs(user)
        print("="*70); print("COACHING CONTEXT"); print("="*70)
        print(ctx or "(empty)")
        print("\n"+"="*70); print("ACTIVE SCHEDULE"); print("="*70)
        print(json.dumps(sched, default=str, indent=2)[:1500])
        print("\n"+"="*70); print("ONBOARDING (selected)"); print("="*70)
        for k in ("wake_time","sleep_time","age","gender","height","weight","goals","fitmax_primary_goal","skin_type","timezone"):
            print(f"  {k} = {ob.get(k)}")
    await engine.dispose()

asyncio.run(main())
