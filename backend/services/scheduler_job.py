"""
Scheduler Job - Background tasks: WhatsApp reminders, in-app chat reminders,
proactive coaching check-ins (morning, midday, night, weekly, missed-task nudges).
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from db.sqlalchemy import AsyncSessionLocal
from services.twilio_service import twilio_service
from models.sqlalchemy_models import UserSchedule, User, ChatHistory, UserCoachingState

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


async def send_chat_reminders():
    """Insert Max chat messages for due schedule tasks (in-app reminders)."""
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

                days = schedule.days or []
                updated = False
                for day in days:
                    if day.get("date") != today_iso:
                        continue

                    for task in day.get("tasks", []):
                        if task.get("chat_reminded") or task.get("status") != "pending":
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

                            task_dt = local_now.replace(
                                hour=task_hour, minute=task_min, second=0, microsecond=0
                            )

                            if task_dt <= local_now <= task_dt + timedelta(minutes=10):
                                title = task.get("title", "Task")
                                desc = task.get("description", "")
                                msg = f"⏰ **{title}**\n{desc}" if desc else f"⏰ **{title}**"

                                chat_msg = ChatHistory(
                                    user_id=schedule.user_id,
                                    role="assistant",
                                    content=msg,
                                    created_at=datetime.utcnow(),
                                )
                                db.add(chat_msg)
                                task["chat_reminded"] = True
                                updated = True
                                logger.info(
                                    f"Sent chat reminder to {user.id} for task '{title}'"
                                )
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid task time '{task_time}': {e}")
                            continue

                if updated:
                    schedule.days = days
                    flag_modified(schedule, "days")
                    schedule.updated_at = datetime.utcnow()

            await db.commit()

    except Exception as e:
        logger.error(f"Chat reminders job error: {e}", exc_info=True)


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


async def send_coaching_check_ins():
    """
    Proactive coaching check-ins — morning, midday, night, missed-task nudges.
    Runs every 30 min. AI generates all messages dynamically from context.
    """
    try:
        from services.coaching_service import coaching_service, COACHING_CONFIG

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.is_paid == True)
            )
            users = result.scalars().all()

            for user in users:
                onboarding = user.onboarding or {}
                tz_name = onboarding.get("timezone", "UTC")
                try:
                    user_tz = ZoneInfo(tz_name)
                except Exception:
                    user_tz = ZoneInfo("UTC")

                local_now = datetime.now(ZoneInfo("UTC")).astimezone(user_tz)
                hour = local_now.hour
                today_iso = local_now.date().isoformat()

                # Daily refresh: clear outside_today for SkinMax schedules when date rolls over
                skinmax_result = await db.execute(
                    select(UserSchedule).where(
                        (UserSchedule.user_id == user.id)
                        & (UserSchedule.maxx_id == "skinmax")
                        & (UserSchedule.is_active == True)
                    )
                )
                for sched in skinmax_result.scalars().all():
                    ctx = sched.schedule_context or {}
                    outside_date = ctx.get("outside_today_date")
                    if outside_date and outside_date != today_iso:
                        ctx.pop("outside_today", None)
                        ctx.pop("outside_today_date", None)
                        sched.schedule_context = ctx
                        flag_modified(sched, "schedule_context")
                        logger.info(f"Reset outside_today for user {user.id} (date rolled over)")

                # Get coaching state
                state_result = await db.execute(
                    select(UserCoachingState).where(UserCoachingState.user_id == user.id)
                )
                state = state_result.scalar_one_or_none()
                if not state:
                    state = UserCoachingState(user_id=user.id)
                    db.add(state)
                    await db.commit()
                    await db.refresh(state)

                # Cooldown: don't check in if we did recently
                cooldown_hours = COACHING_CONFIG.get("check_in_cooldown_hours", 8)
                if state.last_check_in:
                    last_ci = state.last_check_in
                    if last_ci.tzinfo is None:
                        last_ci = last_ci.replace(tzinfo=ZoneInfo("UTC"))
                    hours_since = (datetime.now(ZoneInfo("UTC")) - last_ci).total_seconds() / 3600
                    if hours_since < cooldown_hours:
                        continue

                # Determine check-in type by time of day
                check_in_type = None
                if 6 <= hour <= 9:
                    check_in_type = "morning"
                elif 12 <= hour <= 14:
                    check_in_type = "midday"
                elif 21 <= hour <= 23:
                    check_in_type = "night"

                if not check_in_type:
                    continue

                # Check for missed tasks today
                sched_result = await db.execute(
                    select(UserSchedule).where(
                        (UserSchedule.user_id == user.id) & (UserSchedule.is_active == True)
                    )
                )
                schedules = sched_result.scalars().all()
                missed_today = 0
                for s in schedules:
                    for day in (s.days or []):
                        if day.get("date") == today_iso:
                            for task in day.get("tasks", []):
                                task_time = task.get("time", "")
                                if task.get("status") == "pending" and task_time:
                                    try:
                                        th, tm = map(int, task_time.split(":"))
                                        if local_now.hour > th + 1:
                                            missed_today += 1
                                    except ValueError:
                                        pass

                if missed_today > 0 and check_in_type != "morning":
                    check_in_type = "missed_task"

                # Generate check-in message via AI (fully dynamic)
                msg_text = await coaching_service.generate_check_in_message(
                    str(user.id), db, None, check_in_type, missed_today
                )

                chat_msg = ChatHistory(
                    user_id=user.id,
                    role="assistant",
                    content=msg_text,
                    created_at=datetime.utcnow(),
                )
                db.add(chat_msg)

                # Update last_check_in
                state.last_check_in = datetime.utcnow()
                state.updated_at = datetime.utcnow()

                if missed_today > 0:
                    state.missed_days = (state.missed_days or 0) + 1
                    state.streak_days = 0

                logger.info(f"Sent {check_in_type} check-in to {user.id}")

            await db.commit()

    except Exception as e:
        logger.error(f"Coaching check-ins job error: {e}", exc_info=True)


async def send_weekly_resets():
    """Weekly coaching reset — runs once per week. AI generates message dynamically."""
    try:
        from services.coaching_service import coaching_service

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.is_paid == True))
            users = result.scalars().all()

            for user in users:
                onboarding = user.onboarding or {}
                tz_name = onboarding.get("timezone", "UTC")
                try:
                    user_tz = ZoneInfo(tz_name)
                except Exception:
                    user_tz = ZoneInfo("UTC")

                local_now = datetime.now(ZoneInfo("UTC")).astimezone(user_tz)
                if local_now.weekday() != 0 or local_now.hour != 9:
                    continue

                state_result = await db.execute(
                    select(UserCoachingState).where(UserCoachingState.user_id == user.id)
                )
                state = state_result.scalar_one_or_none()
                if not state:
                    continue

                msg_text = await coaching_service.generate_check_in_message(
                    str(user.id), db, None, "weekly", 0
                )

                chat_msg = ChatHistory(
                    user_id=user.id,
                    role="assistant",
                    content=msg_text,
                    created_at=datetime.utcnow(),
                )
                db.add(chat_msg)

                # Reset weekly counters
                state.missed_days = 0
                state.updated_at = datetime.utcnow()
                logger.info(f"Sent weekly reset to {user.id}")

            await db.commit()

    except Exception as e:
        logger.error(f"Weekly reset job error: {e}", exc_info=True)


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
            send_chat_reminders,
            "interval",
            minutes=5,
            id="chat_reminders",
            replace_existing=True,
        )
        scheduler.add_job(
            send_daily_progress_prompts,
            "interval",
            minutes=60,
            id="daily_progress_prompts",
            replace_existing=True,
        )
        scheduler.add_job(
            send_coaching_check_ins,
            "interval",
            minutes=30,
            id="coaching_check_ins",
            replace_existing=True,
        )
        scheduler.add_job(
            send_weekly_resets,
            "interval",
            minutes=60,
            id="weekly_resets",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("APScheduler started — notifications 5min, chat 5min, coaching 30min, weekly 60min")
        return scheduler
    except ImportError:
        logger.warning("APScheduler not installed — background notifications disabled. Run: pip install apscheduler")
        return None


def stop_scheduler(scheduler):
    """Gracefully shut down the scheduler"""
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
