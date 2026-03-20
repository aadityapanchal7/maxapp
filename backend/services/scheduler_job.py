"""
Scheduler Job - Background tasks: SMS schedule reminders, coaching check-ins,
bedtime progress-picture prompts (SMS/MMS), weekly resets.
Outbound check-ins route to SMS (and are mirrored to in-app chat history).
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
    """Check for schedule tasks that are due and send SMS reminders."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserSchedule).where(UserSchedule.is_active == True)
            )
            schedules = result.scalars().all()

            for schedule in schedules:
                user = await db.get(User, schedule.user_id)
                if not user or not user.phone_number:
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
                                success = await twilio_service.send_schedule_reminder(
                                    phone=user.phone_number,
                                    task_title=task.get("title", "Task"),
                                    task_description=task.get("description", ""),
                                    task_time=task_time,
                                )
                                if success:
                                    task["notification_sent"] = True
                                    updated = True
                                    logger.info(f"Sent SMS reminder to {user.id} for task {task.get('task_id')}")
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid task time '{task_time}': {e}")
                            continue

                if updated:
                    schedule.days = days
                    flag_modified(schedule, "days")
                    schedule.updated_at = datetime.utcnow()

            await db.commit()

    except Exception as e:
        logger.error(f"Scheduler job error: {e}", exc_info=True)


def _parse_sleep_hh_mm(raw: str | None) -> tuple[int, int] | None:
    """Parse sleep time like 23:00 or 11:30 from stored strings."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        parts = s.replace(".", ":").split(":")
        if len(parts) < 2:
            return None
        h, m = int(parts[0]), int(parts[1][:2])
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, TypeError):
        pass
    return None


def _resolve_user_sleep_time(user, schedules: list) -> tuple[int, int] | None:
    """sleep_time from onboarding, schedule_preferences, or active schedule preferences."""
    ob = user.onboarding or {}
    sp = user.schedule_preferences or {}
    for src in (ob.get("sleep_time"), sp.get("sleep_time")):
        p = _parse_sleep_hh_mm(src)
        if p:
            return p
    for sched in schedules:
        prefs = sched.preferences or {}
        p = _parse_sleep_hh_mm(prefs.get("sleep_time"))
        if p:
            return p
    return None


async def send_bedtime_progress_picture_prompts():
    """
    Once per local night: SMS ~30–60 min before the user's saved sleep_time.
    Only for paid users with a phone + at least one active schedule.
    AI-generated copy + explicit MMS reply CTA. Same SMS channel as coaching check-ins.
    """
    try:
        from services.coaching_service import coaching_service

        # Minutes before bedtime to start / end the send window (job runs every 10 min)
        WINDOW_START_BEFORE_SLEEP_MIN = 60
        WINDOW_END_BEFORE_SLEEP_MIN = 30

        async with AsyncSessionLocal() as db:
            now_utc = datetime.now(ZoneInfo("UTC"))

            sched_result = await db.execute(
                select(UserSchedule).where(UserSchedule.is_active == True)
            )
            by_user: dict = {}
            for row in sched_result.scalars().all():
                by_user.setdefault(row.user_id, []).append(row)

            for user_id, schedules in by_user.items():
                user = await db.get(User, user_id)
                if not user or not user.is_paid or not user.phone_number:
                    continue

                sleep_hm = _resolve_user_sleep_time(user, schedules)
                if not sleep_hm:
                    continue

                tz_name = (user.onboarding or {}).get("timezone", "UTC")
                try:
                    user_tz = ZoneInfo(tz_name)
                except Exception:
                    user_tz = ZoneInfo("UTC")

                local_now = now_utc.astimezone(user_tz)
                today_iso = local_now.date().isoformat()

                if user.last_progress_prompt_date == today_iso:
                    continue

                sh, sm = sleep_hm
                sleep_dt = local_now.replace(hour=sh, minute=sm, second=0, microsecond=0)
                if sleep_dt <= local_now:
                    sleep_dt = sleep_dt + timedelta(days=1)

                window_start = sleep_dt - timedelta(minutes=WINDOW_START_BEFORE_SLEEP_MIN)
                window_end = sleep_dt - timedelta(minutes=WINDOW_END_BEFORE_SLEEP_MIN)
                if not (window_start <= local_now < window_end):
                    continue

                try:
                    msg = await coaching_service.generate_bedtime_progress_picture_prompt(
                        str(user.id), db, None
                    )
                    ok = await twilio_service.send_coaching_sms(user.phone_number, msg)
                    if ok:
                        user.last_progress_prompt_date = today_iso
                        user.updated_at = datetime.utcnow()
                        chat_msg = ChatHistory(
                            user_id=user.id,
                            role="assistant",
                            content=msg,
                            created_at=datetime.utcnow(),
                        )
                        db.add(chat_msg)
                        logger.info("Sent bedtime progress picture prompt to user %s", user.id)
                except Exception as e:
                    logger.warning("Bedtime progress prompt failed for %s: %s", user.id, e)

            await db.commit()

    except Exception as e:
        logger.error("Bedtime progress picture prompts job error: %s", e, exc_info=True)


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
                fitmax_schedule = next((s for s in schedules if s.maxx_id == "fitmax"), None)
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

                if fitmax_schedule and check_in_type:
                    today_fitmax = next((d for d in (fitmax_schedule.days or []) if d.get("date") == today_iso), None)
                    tasks = today_fitmax.get("tasks", []) if today_fitmax else []
                    has_session = any(
                        any(k in (t.get("title", "").lower()) for k in ["push", "pull", "legs", "upper", "lower", "workout", "session"])
                        for t in tasks
                    )
                    if check_in_type == "morning":
                        check_in_type = "morning_training_day" if has_session else "morning_rest_day"
                    elif check_in_type == "midday":
                        check_in_type = "preworkout"
                    elif check_in_type == "night":
                        check_in_type = "evening_nutrition"
                    elif check_in_type == "missed_task":
                        check_in_type = "postworkout"

                # Generate check-in message via AI and send as SMS
                if not user.phone_number:
                    continue

                msg_text = await coaching_service.generate_check_in_message(
                    str(user.id), db, None, check_in_type, missed_today
                )

                await twilio_service.send_coaching_sms(user.phone_number, msg_text)

                # Also save to chat history so it shows in-app too
                chat_msg = ChatHistory(
                    user_id=user.id,
                    role="assistant",
                    content=msg_text,
                    created_at=datetime.utcnow(),
                )
                db.add(chat_msg)

                state.last_check_in = datetime.utcnow()
                state.updated_at = datetime.utcnow()

                if missed_today > 0:
                    state.missed_days = (state.missed_days or 0) + 1
                    state.streak_days = 0

                logger.info(f"Sent {check_in_type} check-in SMS to {user.id}")

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
                fitmax_result = await db.execute(
                    select(UserSchedule).where(
                        (UserSchedule.user_id == user.id)
                        & (UserSchedule.maxx_id == "fitmax")
                        & (UserSchedule.is_active == True)
                    ).limit(1)
                )
                has_fitmax = fitmax_result.scalar_one_or_none() is not None
                if has_fitmax:
                    if local_now.weekday() != 6 or local_now.hour != 19:
                        continue
                else:
                    if local_now.weekday() != 0 or local_now.hour != 9:
                        continue

                state_result = await db.execute(
                    select(UserCoachingState).where(UserCoachingState.user_id == user.id)
                )
                state = state_result.scalar_one_or_none()
                if not state:
                    continue

                msg_text = await coaching_service.generate_check_in_message(
                    str(user.id), db, None, "weekly_fitmax_summary" if has_fitmax else "weekly", 0
                )

                if user.phone_number:
                    await twilio_service.send_coaching_sms(user.phone_number, msg_text)

                chat_msg = ChatHistory(
                    user_id=user.id,
                    role="assistant",
                    content=msg_text,
                    created_at=datetime.utcnow(),
                )
                db.add(chat_msg)

                state.missed_days = 0
                state.updated_at = datetime.utcnow()
                logger.info(f"Sent weekly reset SMS to {user.id}")

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
            send_bedtime_progress_picture_prompts,
            "interval",
            minutes=10,
            id="bedtime_progress_picture_prompts",
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
        logger.info(
            "APScheduler started — schedule SMS 5min, bedtime progress pics 10min, coaching 30min, weekly 60min"
        )
        return scheduler
    except ImportError:
        logger.warning("APScheduler not installed — background notifications disabled. Run: pip install apscheduler")
        return None


def stop_scheduler(scheduler):
    """Gracefully shut down the scheduler"""
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
