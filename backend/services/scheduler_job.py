"""
Scheduler Job - Background task that sends WhatsApp reminders for due schedule tasks.
Uses APScheduler to run every 5 minutes and check for tasks whose time has arrived.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from db.sqlalchemy import AsyncSessionLocal
from services.twilio_service import twilio_service
from models.sqlalchemy_models import UserSchedule, User

logger = logging.getLogger(__name__)


async def send_due_notifications():
    """Check for schedule tasks that are due and send WhatsApp reminders."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserSchedule).where(UserSchedule.is_active == True)
            )
            schedules = result.scalars().all()

            for schedule in schedules:
                user = await db.get(User, schedule.user_id)
                if not user:
                    continue

                tz_name = (user.onboarding or {}).get("timezone", "UTC")
                try:
                    user_tz = ZoneInfo(tz_name)
                except Exception:
                    user_tz = ZoneInfo("UTC")

                now_utc = datetime.now(ZoneInfo("UTC"))
                local_now = now_utc.astimezone(user_tz)

                today_iso = local_now.date().isoformat()
                prefs = schedule.preferences or {}

                if not prefs.get("notifications_enabled", True):
                    continue

                days = schedule.days or []
                updated = False
                for day in days:
                    if day.get("date") != today_iso:
                        continue

                    for task in day.get("tasks", []):
                        if task.get("notification_sent") or task.get("status") != "pending":
                            continue

                        task_time = task.get("time", "")
                        if not task_time:
                            continue

                        try:
                            task_time_clean = task_time.strip().upper()
                            if "AM" in task_time_clean or "PM" in task_time_clean:
                                from datetime import datetime as dt
                                parsed_time = dt.strptime(task_time_clean, "%I:%M %p").time()
                                task_hour, task_min = parsed_time.hour, parsed_time.minute
                            else:
                                task_hour, task_min = map(int, task_time_clean.split(":"))

                            task_dt = local_now.replace(hour=task_hour, minute=task_min, second=0, microsecond=0)
                            reminder_offset = prefs.get("notification_minutes_before", 5)
                            notify_at = task_dt - timedelta(minutes=reminder_offset)

                            if notify_at <= local_now <= task_dt + timedelta(minutes=5):
                                if user.phone_number:
                                    success = await twilio_service.send_schedule_reminder(
                                        phone=user.phone_number,
                                        task_title=task.get("title", "Task"),
                                        task_description=task.get("description", ""),
                                        task_time=task_time,
                                    )
                                    if success:
                                        task["notification_sent"] = True
                                        updated = True
                                        logger.info(f"Sent reminder to {user.id} for task {task.get('task_id')}")
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid task time '{task_time}': {e}")
                            continue

                if updated:
                    schedule.days = days
                    schedule.updated_at = datetime.utcnow()

            await db.commit()

    except Exception as e:
        logger.error(f"Scheduler job error: {e}", exc_info=True)


async def send_daily_progress_prompts():
    """Once-per-day WhatsApp prompts asking users for a progress picture."""
    try:
        async with AsyncSessionLocal() as db:
            now_utc = datetime.utcnow()

            result = await db.execute(select(User).where(User.phone_number.isnot(None)))
            users = result.scalars().all()

            for user in users:
                tz_name = (user.onboarding or {}).get("timezone", "UTC")
                try:
                    user_tz = ZoneInfo(tz_name)
                except Exception:
                    user_tz = ZoneInfo("UTC")

                local_now = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(user_tz)
                today_iso = local_now.date().isoformat()
                hour = local_now.hour

                if hour < 21:
                    continue

                if user.last_progress_prompt_date == today_iso:
                    continue

                if not user.phone_number:
                    continue

                try:
                    success = await twilio_service.send_daily_progress_prompt(
                        phone=user.phone_number,
                        name=user.first_name or user.email,
                    )
                    if success:
                        user.last_progress_prompt_date = today_iso
                        user.updated_at = datetime.utcnow()
                        logger.info(f"Sent daily progress prompt to user {user.id}")
                except Exception as e:
                    logger.warning(f"Failed to send daily progress prompt to {user.id}: {e}")

            await db.commit()

    except Exception as e:
        logger.error(f"Daily progress prompts job error: {e}", exc_info=True)


def start_scheduler(app):
    """Start the APScheduler background job."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            send_due_notifications,
            "interval",
            minutes=5,
            id="schedule_notifications",
            replace_existing=True,
        )
        scheduler.add_job(
            send_daily_progress_prompts,
            "interval",
            minutes=60,
            id="daily_progress_prompts",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("APScheduler started — checking for due notifications every 5 minutes and daily progress prompts hourly")
        return scheduler
    except ImportError:
        logger.warning("APScheduler not installed — background notifications disabled. Run: pip install apscheduler")
        return None


def stop_scheduler(scheduler):
    """Gracefully shut down the scheduler"""
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
