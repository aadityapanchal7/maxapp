"""
Scheduler Job - Background tasks: SMS schedule reminders, coaching check-ins,
bedtime progress-picture prompts (SMS/MMS), weekly resets.
Schedule task reminders are SMS-only (mandatory for active schedules; not written to chat).
Proactive SMS (coaching, bedtime, weekly) is not stored in in-app chat history.
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from db.sqlalchemy import AsyncSessionLocal
from services.sendblue_service import sendblue_service, onboarding_allows_proactive_sms
from services.notification_prefs import (
    user_allows_proactive_push,
    schedule_needs_any_channel,
    schedule_sms_marked_sent,
    schedule_push_marked_sent,
    mark_schedule_sms_sent,
    mark_schedule_push_sent,
)
from services.apns_service import send_apns_alert, apns_response_should_invalidate_token
from models.sqlalchemy_models import UserSchedule, User, UserCoachingState
from config import settings

logger = logging.getLogger(__name__)

# When sms_scheduler_test_fast_mode: avoid spamming coaching / weekly every minute (once per uid until server restart).
_COACHING_FAST_TEST_UIDS: set = set()
_WEEKLY_FAST_TEST_UIDS: set = set()

# After task time, keep retrying SMS every job tick until this many minutes past (job runs every 5 min).
SCHEDULE_REMINDER_GRACE_AFTER_TASK_MINUTES = 120


def _sms_fast_mode() -> bool:
    return bool(getattr(settings, "sms_scheduler_test_fast_mode", False))


def _parse_task_time_parts(task_time: str) -> tuple[int, int] | None:
    """Return (hour, minute) in 24h for task time strings."""
    if not task_time or not str(task_time).strip():
        return None
    try:
        task_time_clean = str(task_time).strip().upper()
        if "AM" in task_time_clean or "PM" in task_time_clean:
            parsed_time = datetime.strptime(task_time_clean, "%I:%M %p").time()
            return parsed_time.hour, parsed_time.minute
        parts = task_time_clean.split(":")
        task_hour, task_min = int(parts[0]), int(parts[1][:2])
        return task_hour, task_min
    except (ValueError, TypeError, IndexError):
        return None


def _notification_intent_bucket(task: dict) -> str:
    """
    Coarse intent for SMS deduplication across multiple active schedules.
    """
    text = f"{task.get('title', '')} {task.get('description', '')}".lower()
    if any(
        k in text
        for k in (
            "good night",
            "bedtime",
            "wind-down",
            "wind down",
            "before bed",
            "sleep tight",
        )
    ):
        return "evening_meta"
    if any(
        k in text
        for k in (
            "good morning",
            "morning check",
            "let me know you",
            "you're awake",
            "youre awake",
            "wake up",
            "rise and shine",
            "rise & shine",
            "time to rise",
        )
    ):
        return "morning_wake"
    if ("check-in" in text or "check in" in text) and any(
        k in text for k in ("morning", "wake", "awake", "rise", "sunrise", "start your day", "up and")
    ):
        return "morning_wake"
    if "midday" in text or ("lunch" in text and "remind" in text):
        return "midday_ping"
    if any(k in text for k in ("hydration", "drink water", "glass of water", "stay hydrated")):
        return "hydration"
    if any(
        k in text
        for k in (
            "workout",
            "gym session",
            "training session",
            "push day",
            "pull day",
            "leg day",
            "upper body",
            "lower body",
            "lift day",
        )
    ):
        return "workout"
    if any(
        k in text
        for k in ("skincare", "cleanser", "moisturizer", "moisturiser", "serum", "sunscreen")
    ):
        return "skincare"
    if any(k in text for k in ("mewing", "tongue posture", "tongue on the roof", "hard mew")):
        return "jaw_posture"
    return "other"


def _title_slug(title: str) -> str:
    t = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    return " ".join(t.split()[:5]) or "task"


def _dedupe_group_key(bucket: str, task_dt: datetime, task: dict) -> tuple:
    """Group tasks so one SMS covers duplicates across modules."""
    hm = task_dt.hour * 60 + task_dt.minute
    if bucket == "morning_wake":
        return ("morning_wake", hm // 20)
    if bucket == "midday_ping":
        return ("midday_ping", hm // 20)
    if bucket == "evening_meta":
        return ("evening_meta", hm // 30)
    if bucket == "hydration":
        return ("hydration", hm // 15)
    if bucket == "other":
        return ("other", task_dt.hour, task_dt.minute, _title_slug(task.get("title", "")))
    return (bucket, task_dt.hour, task_dt.minute)


def _pending_morning_wake_tasks_today(schedules: list, today_iso: str) -> bool:
    """True if schedule SMS will cover morning wake intent (skip redundant coaching morning)."""
    for s in schedules:
        for day in s.days or []:
            if day.get("date") != today_iso:
                continue
            for task in day.get("tasks", []):
                if task.get("status") != "pending":
                    continue
                if _notification_intent_bucket(task) != "morning_wake":
                    continue
                parts = _parse_task_time_parts(task.get("time", ""))
                if not parts:
                    continue
                h, m = parts
                if 5 <= h <= 11 or (h == 12 and m == 0):
                    return True
    return False


async def send_due_notifications():
    """Check for schedule tasks that are due; send SMS and/or APNs (deduped per user)."""
    try:
        if _sms_fast_mode():
            logger.debug("SMS fast mode: schedule reminders ignore task time window (today's pending tasks only)")
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(UserSchedule).where(UserSchedule.is_active == True))
            schedules = result.scalars().all()

            by_user: dict = defaultdict(list)
            for schedule in schedules:
                by_user[schedule.user_id].append(schedule)

            for user_id, user_schedules in by_user.items():
                user = await db.get(User, user_id)
                if not user:
                    continue
                want_sms = bool(user.phone_number) and onboarding_allows_proactive_sms(user.onboarding)
                want_push = user_allows_proactive_push(user.onboarding, user.apns_device_token)
                if not want_sms and not want_push:
                    continue

                tz_name = (user.onboarding or {}).get("timezone", "UTC")
                try:
                    user_tz = ZoneInfo(tz_name)
                except Exception:
                    user_tz = ZoneInfo("UTC")

                now_utc = datetime.now(ZoneInfo("UTC"))
                local_now = now_utc.astimezone(user_tz)
                today_iso = local_now.date().isoformat()

                candidates: list[dict] = []
                for schedule in user_schedules:
                    prefs = schedule.preferences or {}
                    days = schedule.days or []
                    for day in days:
                        if day.get("date") != today_iso:
                            continue
                        for task in day.get("tasks", []):
                            if not schedule_needs_any_channel(
                                task, want_sms=want_sms, want_push=want_push
                            ):
                                continue
                            task_time = task.get("time", "")
                            parts = _parse_task_time_parts(task_time)
                            if not parts:
                                continue
                            task_hour, task_min = parts
                            try:
                                task_dt = local_now.replace(
                                    hour=task_hour, minute=task_min, second=0, microsecond=0
                                )
                            except ValueError:
                                continue
                            reminder_offset = prefs.get("notification_minutes_before", 5)
                            notify_at = task_dt - timedelta(minutes=reminder_offset)
                            window_end = task_dt + timedelta(
                                minutes=SCHEDULE_REMINDER_GRACE_AFTER_TASK_MINUTES
                            )
                            in_window = notify_at <= local_now <= window_end
                            if not (_sms_fast_mode() or in_window):
                                continue
                            bucket = _notification_intent_bucket(task)
                            key = _dedupe_group_key(bucket, task_dt, task)
                            candidates.append(
                                {
                                    "schedule": schedule,
                                    "task": task,
                                    "task_time_str": task_time,
                                    "key": key,
                                }
                            )

                groups: dict[tuple, list[dict]] = defaultdict(list)
                for c in candidates:
                    groups[c["key"]].append(c)

                touched_schedules: set = set()
                for _key, group in groups.items():
                    sms_unsent = [it for it in group if not schedule_sms_marked_sent(it["task"])]
                    push_unsent = [it for it in group if not schedule_push_marked_sent(it["task"])]

                    if want_sms and sms_unsent:
                        sms_payload = [(it["task"], it["task_time_str"]) for it in sms_unsent]
                        success = await sendblue_service.send_schedule_reminder_group(
                            user.phone_number, sms_payload
                        )
                        if success:
                            for item in sms_unsent:
                                mark_schedule_sms_sent(item["task"])
                                touched_schedules.add(item["schedule"])
                            logger.info(
                                "Sent deduped schedule SMS to user %s (%s task(s), key=%s)",
                                user.id,
                                len(sms_unsent),
                                _key,
                            )

                    if want_push and push_unsent and (user.apns_device_token or "").strip():
                        push_payload = [(it["task"], it["task_time_str"]) for it in push_unsent]
                        title, body = sendblue_service.build_schedule_reminder_push_content(push_payload)
                        ok, http_status = await send_apns_alert(
                            user.apns_device_token, title, body
                        )
                        if apns_response_should_invalidate_token(http_status):
                            user.apns_device_token = None
                            user.apns_token_updated_at = None
                        if ok:
                            for item in push_unsent:
                                mark_schedule_push_sent(item["task"])
                                touched_schedules.add(item["schedule"])
                            logger.info(
                                "Sent deduped schedule APNs to user %s (%s task(s), key=%s)",
                                user.id,
                                len(push_unsent),
                                _key,
                            )

                for schedule in touched_schedules:
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

        now_utc = datetime.now(ZoneInfo("UTC"))

        async with AsyncSessionLocal() as db:
            sched_result = await db.execute(
                select(UserSchedule).where(UserSchedule.is_active == True)
            )
            by_user: dict = {}
            for row in sched_result.scalars().all():
                by_user.setdefault(row.user_id, []).append(row)

        for uid, schedules in by_user.items():
            try:
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, uid)
                    if not user or not user.is_paid:
                        continue

                    want_sms = bool(user.phone_number) and onboarding_allows_proactive_sms(
                        user.onboarding
                    )
                    want_push = user_allows_proactive_push(
                        user.onboarding, user.apns_device_token
                    )
                    if not want_sms and not want_push:
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
                    in_bedtime_window = window_start <= local_now < window_end
                    if not (_sms_fast_mode() or in_bedtime_window):
                        continue

                    phone = user.phone_number
                    apns_tok = (user.apns_device_token or "").strip()
                    user_uuid = user.id

                msg = await coaching_service.generate_bedtime_progress_picture_prompt(
                    str(user_uuid), None, None
                )
                delivered = False
                if want_sms and phone:
                    delivered = bool(await sendblue_service.send_coaching_sms(phone, msg))
                if want_push and apns_tok:
                    ok, http_status = await send_apns_alert(apns_tok, "Agartha", msg)
                    if apns_response_should_invalidate_token(http_status):
                        async with AsyncSessionLocal() as db2:
                            u2 = await db2.get(User, user_uuid)
                            if u2:
                                u2.apns_device_token = None
                                u2.apns_token_updated_at = None
                                await db2.commit()
                    delivered = delivered or ok
                if not delivered:
                    continue

                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_uuid)
                    if not user:
                        continue
                    user.last_progress_prompt_date = today_iso
                    user.updated_at = datetime.utcnow()
                    await db.commit()
                    logger.info("Sent bedtime progress picture prompt to user %s", user.id)
            except Exception as e:
                logger.warning("Bedtime progress prompt failed for %s: %s", uid, e)

    except Exception as e:
        logger.error("Bedtime progress picture prompts job error: %s", e, exc_info=True)


async def send_coaching_check_ins():
    """
    Proactive coaching check-ins — morning, midday, night, missed-task nudges.
    Runs every 30 min. AI generates all messages dynamically from context.
    DB sessions are short-lived; Gemini runs with db=None so pool slots are not held during LLM.
    """
    try:
        from services.coaching_service import coaching_service, COACHING_CONFIG

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.is_paid == True))
            paid_ids = [u.id for u in result.scalars().all()]

        for uid in paid_ids:
            try:
                if _sms_fast_mode() and uid in _COACHING_FAST_TEST_UIDS:
                    continue
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, uid)
                    if not user:
                        continue

                    onboarding = user.onboarding or {}
                    tz_name = onboarding.get("timezone", "UTC")
                    try:
                        user_tz = ZoneInfo(tz_name)
                    except Exception:
                        user_tz = ZoneInfo("UTC")

                    local_now = datetime.now(ZoneInfo("UTC")).astimezone(user_tz)
                    hour = local_now.hour
                    today_iso = local_now.date().isoformat()

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

                    state_result = await db.execute(
                        select(UserCoachingState).where(UserCoachingState.user_id == user.id)
                    )
                    state = state_result.scalar_one_or_none()
                    if not state:
                        state = UserCoachingState(user_id=user.id)
                        db.add(state)
                        await db.commit()
                        await db.refresh(state)

                    cooldown_hours = 0 if _sms_fast_mode() else COACHING_CONFIG.get("check_in_cooldown_hours", 8)
                    if state.last_check_in and not _sms_fast_mode():
                        last_ci = state.last_check_in
                        if last_ci.tzinfo is None:
                            last_ci = last_ci.replace(tzinfo=ZoneInfo("UTC"))
                        hours_since = (datetime.now(ZoneInfo("UTC")) - last_ci).total_seconds() / 3600
                        if hours_since < cooldown_hours:
                            await db.commit()
                            continue

                    check_in_type = None
                    if _sms_fast_mode():
                        check_in_type = "morning"
                    elif 6 <= hour <= 9:
                        check_in_type = "morning"
                    elif 12 <= hour <= 14:
                        check_in_type = "midday"
                    elif 21 <= hour <= 23:
                        check_in_type = "night"

                    if not check_in_type:
                        await db.commit()
                        continue

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
                        today_fitmax = next(
                            (d for d in (fitmax_schedule.days or []) if d.get("date") == today_iso), None
                        )
                        tasks = today_fitmax.get("tasks", []) if today_fitmax else []
                        has_session = any(
                            any(
                                k in (t.get("title", "").lower())
                                for k in ["push", "pull", "legs", "upper", "lower", "workout", "session"]
                            )
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

                    # Avoid duplicate SMS: schedule already has a pending morning wake/check-in today
                    if check_in_type in (
                        "morning",
                        "morning_training_day",
                        "morning_rest_day",
                    ):
                        if _pending_morning_wake_tasks_today(schedules, today_iso):
                            await db.commit()
                            continue

                    want_sms = bool(user.phone_number) and onboarding_allows_proactive_sms(
                        user.onboarding
                    )
                    want_push = user_allows_proactive_push(
                        user.onboarding, user.apns_device_token
                    )
                    if not want_sms and not want_push:
                        await db.commit()
                        continue

                    phone = user.phone_number
                    apns_tok = (user.apns_device_token or "").strip()
                    uid_str = str(user.id)
                    ct = check_in_type
                    mt = missed_today
                    await db.commit()

                msg_text = await coaching_service.generate_check_in_message(
                    uid_str, None, None, ct, mt
                )

                delivered = False
                if want_sms and phone:
                    delivered = bool(await sendblue_service.send_coaching_sms(phone, msg_text))
                if want_push and apns_tok:
                    ok, http_status = await send_apns_alert(apns_tok, "Agartha", msg_text)
                    if apns_response_should_invalidate_token(http_status):
                        async with AsyncSessionLocal() as db2:
                            u2 = await db2.get(User, uid)
                            if u2:
                                u2.apns_device_token = None
                                u2.apns_token_updated_at = None
                                await db2.commit()
                    delivered = delivered or ok

                if not delivered:
                    continue

                async with AsyncSessionLocal() as db:
                    st_res = await db.execute(
                        select(UserCoachingState).where(UserCoachingState.user_id == uid)
                    )
                    st = st_res.scalar_one_or_none()
                    if st:
                        st.last_check_in = datetime.utcnow()
                        st.updated_at = datetime.utcnow()
                        if mt > 0:
                            st.missed_days = (st.missed_days or 0) + 1
                            st.streak_days = 0

                    await db.commit()
                    logger.info(
                        "Sent %s check-in to %s (sms=%s push=%s)",
                        ct,
                        uid,
                        want_sms and bool(phone),
                        want_push and bool(apns_tok),
                    )
                    if _sms_fast_mode():
                        _COACHING_FAST_TEST_UIDS.add(uid)

            except Exception as loop_err:
                logger.warning("Coaching check-in failed for %s: %s", uid, loop_err, exc_info=True)

    except Exception as e:
        logger.error(f"Coaching check-ins job error: {e}", exc_info=True)


async def send_weekly_resets():
    """Weekly coaching reset — runs once per week. AI generates message dynamically."""
    try:
        from services.coaching_service import coaching_service

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.is_paid == True))
            paid_ids = [u.id for u in result.scalars().all()]

        for uid in paid_ids:
            try:
                if _sms_fast_mode() and uid in _WEEKLY_FAST_TEST_UIDS:
                    continue
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, uid)
                    if not user:
                        continue
                    want_sms = bool(user.phone_number) and onboarding_allows_proactive_sms(
                        user.onboarding
                    )
                    want_push = user_allows_proactive_push(
                        user.onboarding, user.apns_device_token
                    )
                    if not want_sms and not want_push:
                        continue

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
                    if not _sms_fast_mode():
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

                    phone = user.phone_number
                    apns_tok = (user.apns_device_token or "").strip()
                    uid_str = str(user.id)
                    check_key = "weekly_fitmax_summary" if has_fitmax else "weekly"
                    await db.commit()

                msg_text = await coaching_service.generate_check_in_message(
                    uid_str, None, None, check_key, 0
                )

                delivered = False
                if want_sms and phone:
                    delivered = bool(await sendblue_service.send_coaching_sms(phone, msg_text))
                if want_push and apns_tok:
                    ok, http_status = await send_apns_alert(apns_tok, "Agartha", msg_text)
                    if apns_response_should_invalidate_token(http_status):
                        async with AsyncSessionLocal() as db2:
                            u2 = await db2.get(User, uid)
                            if u2:
                                u2.apns_device_token = None
                                u2.apns_token_updated_at = None
                                await db2.commit()
                    delivered = delivered or ok

                if not delivered:
                    continue

                async with AsyncSessionLocal() as db:
                    st_res = await db.execute(
                        select(UserCoachingState).where(UserCoachingState.user_id == uid)
                    )
                    st = st_res.scalar_one_or_none()
                    if st:
                        st.missed_days = 0
                        st.updated_at = datetime.utcnow()

                    await db.commit()
                    logger.info(
                        "Sent weekly reset to %s (sms=%s push=%s)",
                        uid,
                        want_sms and bool(phone),
                        want_push and bool(apns_tok),
                    )
                    if _sms_fast_mode():
                        _WEEKLY_FAST_TEST_UIDS.add(uid)

            except Exception as loop_err:
                logger.warning("Weekly reset failed for %s: %s", uid, loop_err, exc_info=True)

    except Exception as e:
        logger.error(f"Weekly reset job error: {e}", exc_info=True)


def start_scheduler(app):
    """Start the APScheduler background job."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        fast = _sms_fast_mode()
        if fast:
            logger.warning(
                "SMS_SCHEDULER_TEST_FAST_MODE is ON — 1-minute job intervals; schedule/bedtime windows bypassed; "
                "coaching + weekly at most once per user until API restart. Turn OFF for production."
            )

        sched_m = 1 if fast else 5
        bed_m = 1 if fast else 10
        coach_m = 1 if fast else 30
        weekly_m = 1 if fast else 60

        # Safety flags on every job:
        #   max_instances=1 → a slow run won't fan out into overlapping SMS sends
        #   coalesce=True   → if we miss ticks (deploy, CPU spike), catch up once, not N times
        #   misfire_grace   → tolerate brief event-loop stalls without skipping the job
        job_defaults = {
            "max_instances": 1,
            "coalesce": True,
            "misfire_grace_time": 60,
            "replace_existing": True,
        }
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            send_due_notifications,
            "interval",
            minutes=sched_m,
            id="schedule_notifications",
            **job_defaults,
        )
        scheduler.add_job(
            send_bedtime_progress_picture_prompts,
            "interval",
            minutes=bed_m,
            id="bedtime_progress_picture_prompts",
            **job_defaults,
        )
        scheduler.add_job(
            send_coaching_check_ins,
            "interval",
            minutes=coach_m,
            id="coaching_check_ins",
            **job_defaults,
        )
        scheduler.add_job(
            send_weekly_resets,
            "interval",
            minutes=weekly_m,
            id="weekly_resets",
            **job_defaults,
        )
        from services.prompt_loader import refresh_prompt_cache
        scheduler.add_job(
            refresh_prompt_cache,
            "interval",
            minutes=60,
            id="prompt_cache_refresh",
            **job_defaults,
        )
        scheduler.start()
        logger.info(
            "APScheduler started — schedule SMS every %sm, bedtime %sm, coaching %sm, weekly %sm%s",
            sched_m,
            bed_m,
            coach_m,
            weekly_m,
            " (TEST FAST MODE)" if fast else "",
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
