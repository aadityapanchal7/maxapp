"""
Scheduler Job - Background tasks: push/SMS schedule reminders (governed by the
v2 notification PLANNER), coaching check-ins, bedtime progress-picture prompts,
weekly resets, queued-broadcast worker.

Task reminders are PUSH-FIRST (APNs); SMS is the fallback when push is off. The
single daily planner (services.notification_planner) governs WHICH and WHEN, so
there is exactly one path that emits task pushes — never push AND SMS for the
same task (cross-channel dedup).
"""

import asyncio
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
from services.notification_copy import CAT_TASK_DUE, build_push_custom
from services.notification_candidates import build_candidates
from services.notification_planner import (
    PlannerConfig,
    PlannerContext,
    plan_day,
    due_now,
    effective_cap,
    choose_channel,
)
import services.notification_state as ns
from services.schedule_streak import STREAK_KEY
from models.sqlalchemy_models import UserSchedule, User, UserCoachingState
from config import settings

logger = logging.getLogger(__name__)


def _user_why(onboarding: dict | None) -> str | None:
    ob = onboarding or {}
    for k in ("why", "goal", "primary_goal", "motivation"):
        v = ob.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().rstrip(".")
    goals = ob.get("goals")
    if isinstance(goals, dict):
        v = goals.get("why")
        if isinstance(v, str) and v.strip():
            return v.strip().rstrip(".")
    return None

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


# How many users' schedules a tick materializes at once. Schedule rows carry the
# full `days` JSONB (tens-to-hundreds of KB each), so loading EVERY active
# schedule in one query — the old behavior — scales the tick's memory with the
# user base and OOMs a small instance long before 10k users. An id-only sweep
# + per-chunk loads keeps peak memory constant regardless of user count.
_TICK_USER_CHUNK = 200


def _chunked(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


async def _active_schedule_user_ids(paid_with_phone_only: bool = False) -> list:
    """Id-only sweep of users with an active schedule (tiny rows, any scale).
    `paid_with_phone_only` pushes the SMS-job eligibility filter into SQL so
    those ticks never even look at the (majority) ineligible users."""
    async with AsyncSessionLocal() as db:
        q = select(UserSchedule.user_id).where(UserSchedule.is_active.is_(True)).distinct()
        if paid_with_phone_only:
            q = (
                select(UserSchedule.user_id)
                .join(User, User.id == UserSchedule.user_id)
                .where(
                    UserSchedule.is_active.is_(True),
                    User.is_paid.is_(True),
                    User.phone_number.isnot(None),
                )
                .distinct()
            )
        res = await db.execute(q)
        return [r[0] for r in res.all()]


async def send_due_notifications():
    """Planner-governed push/SMS sends. The v2 daily planner is the SINGLE path
    that emits task reminders + the broad daily categories: it enforces the
    per-user cap, min-interval, wake/sleep window, dedup, adaptive backoff and
    foreground suppression, and picks ONE channel per user (push, else SMS) so a
    task is never double-notified across channels."""
    if bool(getattr(settings, "notif_kill_switch", False)):
        return
    try:
        cfg = PlannerConfig.from_settings()
        lapse_days = int(getattr(settings, "notif_lapse_days", 4) or 4)
        user_ids = await _active_schedule_user_ids()
        # Fresh session per chunk: bounded identity map + released JSONB blobs,
        # so tick memory stays flat no matter how many schedules exist.
        for chunk in _chunked(user_ids, _TICK_USER_CHUNK):
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(UserSchedule).where(
                        UserSchedule.is_active.is_(True),
                        UserSchedule.user_id.in_(chunk),
                    )
                )
                by_user: dict = defaultdict(list)
                for schedule in result.scalars().all():
                    by_user[schedule.user_id].append(schedule)

                # Warm the identity map with ONE query so the per-user db.get(User)
                # inside _plan_and_send_for_user is a cache hit, not an N+1 SELECT.
                if by_user:
                    await db.execute(select(User).where(User.id.in_(list(by_user.keys()))))

                for user_id, user_schedules in by_user.items():
                    try:
                        await _plan_and_send_for_user(db, user_id, user_schedules, cfg, lapse_days)
                    except Exception as ue:
                        logger.warning("planner send failed for %s: %s", user_id, ue, exc_info=True)

                await db.commit()

    except Exception as e:
        logger.error(f"Scheduler job error: {e}", exc_info=True)


async def _plan_and_send_for_user(db, user_id, user_schedules, cfg, lapse_days):
    user = await db.get(User, user_id)
    if not user:
        return
    want_sms = bool(user.phone_number) and onboarding_allows_proactive_sms(user.onboarding)
    want_push = user_allows_proactive_push(user.onboarding, user.apns_device_token)
    # Cross-channel dedup (review item 4): exactly ONE channel per user.
    channel = choose_channel(want_push=want_push, want_sms=want_sms)
    if channel is None:
        return

    ob = dict(user.onboarding or {})
    try:
        user_tz = ZoneInfo(ob.get("timezone") or "UTC")
    except Exception:
        user_tz = ZoneInfo("UTC")
    local_now = datetime.now(ZoneInfo("UTC")).astimezone(user_tz)
    local_naive = local_now.replace(tzinfo=None)
    today_iso = local_now.date().isoformat()
    now_min = local_now.hour * 60 + local_now.minute

    wake_p = _parse_task_time_parts(str(ob.get("wake_time") or "07:00")) or (7, 0)
    sleep_p = _parse_task_time_parts(str(ob.get("sleep_time") or "23:00")) or (23, 0)
    wake_min, sleep_min = wake_p[0] * 60 + wake_p[1], sleep_p[0] * 60 + sleep_p[1]

    profile = dict(user.profile or {})
    state = ns.get_state(profile)

    # Foreground suppression — never push while the app is open / just used.
    if channel == "push" and not _sms_fast_mode() and ns.foreground_recent(
        state, local_naive, cfg.foreground_suppress_min
    ):
        return

    # Gather today's tasks across all active schedules; keep a uuid -> (schedule,
    # task) map so we can mark the right one sent.
    tasks: list[dict] = []
    ref: dict[str, tuple] = {}
    for schedule in user_schedules:
        for day in (schedule.days or []):
            if day.get("date") != today_iso:
                continue
            for task in day.get("tasks", []):
                parts = _parse_task_time_parts(task.get("time", ""))
                if not parts:
                    continue
                uuid = str(task.get("task_uuid") or task.get("uuid") or f"{schedule.maxx_id}:{task.get('title','')}:{parts[0]}{parts[1]}")
                tasks.append({
                    "uuid": uuid,
                    "title": task.get("title") or "your routine",
                    "time_min": parts[0] * 60 + parts[1],
                    "maxx": schedule.maxx_id,
                    "pending": task.get("status") == "pending",
                })
                ref[uuid] = (schedule, task)

    active_plans = {s.maxx_id for s in user_schedules}
    streak = int(profile.get(STREAK_KEY) or 0)
    name = (user.first_name or ob.get("first_name") or "").strip() or None
    why = _user_why(ob)

    deliv, opened, returning = ns.backoff_inputs(state, local_now, lapse_days=lapse_days)
    cap = effective_cap(cfg.cap, recent_delivered=deliv, recent_opened=opened, returning_lapsed=returning)

    lapsed = ns.is_lapsed(state, local_now, lapse_days)
    cands = build_candidates(
        tasks=tasks, now_min=now_min, wake_min=wake_min, sleep_min=sleep_min,
        weekday=local_now.weekday(), name=name, why=why, streak=streak,
        active_plans=active_plans, rotation=deliv, lapsed=lapsed,
        coaching_tone=getattr(user, "coaching_tone", None),
    )
    # SMS users only get task reminders (broad categories are push-only to avoid
    # SMS spam); push users get the full set.
    if channel == "sms":
        cands = [c for c in cands if c.category == CAT_TASK_DUE]

    # Tasks already nudged on THIS channel are off the table.
    already = {
        uuid for uuid, (_s, t) in ref.items()
        if (schedule_push_marked_sent(t) if channel == "push" else schedule_sms_marked_sent(t))
    }

    # Cross-tick enforcement: plan_day only knows about THIS tick, so the daily
    # cap and min-interval must be reduced by what was already sent earlier today
    # (state persists across ticks). Without this, the cap/interval reset every
    # 5-min tick and a user could be nudged far past the intended ceiling.
    if not _sms_fast_mode():
        already_today = ns.sent_count_today(state, today_iso)
        remaining_cap = max(0, cap - already_today)
        if remaining_cap == 0:
            return
        last_send = ns.last_send_min_today(state, today_iso)
        if last_send is not None and (now_min - last_send) < cfg.min_interval_min:
            return
        cap = remaining_cap

    ctx = PlannerContext(
        now_min=now_min, wake_min=wake_min, sleep_min=sleep_min,
        cap=cap, min_interval_min=cfg.min_interval_min,
        muted_categories=ns.muted_categories(ob),
        already_nudged_tasks=frozenset(already),
        already_sent_keys=ns.sent_keys_today(state, today_iso),
        foreground_recent=False,
    )
    selected = plan_day(ctx, cands)
    due = due_now(selected, now_min) if not _sms_fast_mode() else selected

    touched_schedules: set = set()
    changed = False
    for c in due:
        if c.dedup_key in ns.sent_keys_today(state, today_iso):
            continue
        # Respect the min-interval within this tick too: once we send one, the
        # rest wait for a future tick (state is updated by record_sent below).
        if not _sms_fast_mode():
            ls = ns.last_send_min_today(state, today_iso)
            if ls is not None and (now_min - ls) < cfg.min_interval_min:
                break
        ok = False
        if channel == "push":
            custom = build_push_custom(c.category, c.route, c.params)
            ok, http_status = await send_apns_alert(
                (user.apns_device_token or "").strip(), c.title, c.body, custom=custom
            )
            if apns_response_should_invalidate_token(http_status):
                user.apns_device_token = None
                user.apns_token_updated_at = None
                break
        else:  # sms — task reminders only
            ok = bool(await sendblue_service.send_coaching_sms(user.phone_number, c.body))

        if not ok:
            continue
        state = ns.record_delivered(state, local_now)
        state = ns.record_sent(state, today_iso, c.dedup_key, local_now)
        state = ns.push_recent_template(state, c.category, c.template_id)
        changed = True
        if c.category == CAT_TASK_DUE and c.task_uuid in ref:
            sched, task = ref[c.task_uuid]
            if channel == "push":
                mark_schedule_push_sent(task)
            else:
                mark_schedule_sms_sent(task)
            touched_schedules.add(sched)
        logger.info("notif planner sent %s to %s via %s", c.category, user.id, channel)

    for sched in touched_schedules:
        flag_modified(sched, "days")
        sched.updated_at = datetime.utcnow()
    if changed:
        user.profile = ns.put_state(dict(user.profile or {}), state)
        flag_modified(user, "profile")


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


def _resolve_user_sleep_time(
    user, schedules: list, weekday: str | None = None
) -> tuple[int, int] | None:
    """Bedtime for THIS night, preferring the Planner tab's per-weekday override.

    Precedence (first hit wins):
      1. onboarding.weekly_timings[weekday].sleep_time — the bedtime the user
         set for this specific weekday in the Planner (e.g. a later Friday).
      2. onboarding.sleep_time — the global default rhythm.
      3. schedule_preferences.sleep_time.
      4. any active schedule's preferences.sleep_time.

    `weekday` is a lowercase day name ("monday".."sunday"); pass it so a user
    who sleeps in / stays up on certain days gets the prompt at the right hour
    on those days. Omitted → behaves like the old global-only lookup.
    """
    ob = user.onboarding or {}
    sp = user.schedule_preferences or {}
    if weekday:
        wt = ob.get("weekly_timings")
        if isinstance(wt, dict):
            day_ov = wt.get(weekday)
            if isinstance(day_ov, dict):
                p = _parse_sleep_hh_mm(day_ov.get("sleep_time"))
                if p:
                    return p
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

        # This job is SMS-only for PAID users with a phone — filter in SQL so the
        # sweep touches only eligible users, then load their schedules (full
        # `days` JSONB) one bounded chunk at a time; each chunk is fully
        # processed and released before the next loads, so tick memory stays
        # flat at any user count.
        user_ids = await _active_schedule_user_ids(paid_with_phone_only=True)
        for chunk in _chunked(user_ids, _TICK_USER_CHUNK):
            by_user: dict = {}
            async with AsyncSessionLocal() as db:
                sched_result = await db.execute(
                    select(UserSchedule).where(
                        UserSchedule.is_active.is_(True),
                        UserSchedule.user_id.in_(chunk),
                    )
                )
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
                        # Push is consolidated into the v2 planner
                        # (send_due_notifications). Legacy coaching jobs are SMS-only
                        # so there's exactly one path emitting pushes.
                        want_push = False
                        if not want_sms and not want_push:
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

                        # Bedtime for *tonight* — prefer the Planner's per-weekday
                        # override so a later-Friday / sleep-in-Sunday user gets the
                        # prompt at the hour they actually wind down that day. The
                        # window fires before bed, so the winding-down weekday is
                        # local_now's (correct for the common pre-midnight bedtime).
                        weekday = local_now.strftime("%A").lower()  # monday..sunday
                        sleep_hm = _resolve_user_sleep_time(user, schedules, weekday=weekday)
                        if not sleep_hm:
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

                    delivered = False
                    if want_sms and phone:
                        # SMS users reply to the thread with a photo.
                        sms_msg = await coaching_service.generate_bedtime_progress_picture_prompt(
                            str(user_uuid), None, None, channel="sms"
                        )
                        delivered = bool(await sendblue_service.send_coaching_sms(phone, sms_msg))
                    if want_push and apns_tok:
                        # Push users can't reply with a photo, so the copy invites a
                        # tap and the payload deep-links straight to the progress
                        # archive where they add tonight's pic.
                        push_msg = await coaching_service.generate_bedtime_progress_picture_prompt(
                            str(user_uuid), None, None, channel="push"
                        )
                        ok, http_status = await send_apns_alert(
                            apns_tok, "Max", push_msg, custom={"route": "ProgressArchive"}
                        )
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
                    # Push is consolidated into the v2 planner
                    # (send_due_notifications). Legacy coaching jobs are SMS-only
                    # so there's exactly one path emitting pushes.
                    want_push = False
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
                    ok, http_status = await send_apns_alert(apns_tok, "Max", msg_text)
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


async def reconcile_lapsed_creator_subs():
    """Hourly sweep: creator subscriptions whose expires_at passed WITHOUT an
    ASN EXPIRED webhook (missed/delayed webhooks happen) stay status='active'
    forever — the read paths treat them as inactive (_sub_active checks the
    timestamp), but enrollment + the habit UserSchedule were only revoked by
    the webhook path. Run the same deactivation so the paid program actually
    leaves Home/Planner when the money stops."""
    from datetime import timezone as _tz
    from models.sqlalchemy_models import Creator, CreatorSubscription
    from services import creator_service
    from db.sqlalchemy import AsyncSessionLocal as _S
    try:
        async with _S() as db:
            rows = (await db.execute(
                select(CreatorSubscription, Creator)
                .join(Creator, Creator.id == CreatorSubscription.creator_id)
                .where(
                    (CreatorSubscription.status == "active")
                    & (CreatorSubscription.expires_at.isnot(None))
                    & (CreatorSubscription.expires_at < datetime.now(_tz.utc))
                )
                .limit(200)
            )).all()
            for sub, creator in rows:
                try:
                    await creator_service.deactivate_creator_subscription(
                        user_id=str(sub.user_id), creator=creator, db=db, status="expired",
                    )
                    await db.commit()
                except Exception:
                    logger.exception(
                        "lapsed creator sub reconcile failed user=%s maxx=%s",
                        sub.user_id, creator.maxx_id,
                    )
                    await db.rollback()
            if rows:
                logger.info("reconciled %d lapsed creator subs", len(rows))
    except Exception:
        logger.exception("reconcile_lapsed_creator_subs sweep failed")


async def send_weekly_resets():
    """Weekly coaching reset — runs once per week. AI generates message dynamically."""
    try:
        from services.coaching_service import coaching_service

        async with AsyncSessionLocal() as db:
            # This job is SMS-only (want_push is hardcoded False) and skips
            # non-phone users immediately, and has no non-SMS side effects — so
            # filter to phone-holders in SQL instead of loading every paid user
            # and db.get()-ing them one at a time (collapses the O(N) sweep).
            result = await db.execute(
                select(User).where(
                    (User.is_paid == True) & (User.phone_number.isnot(None))
                )
            )
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
                    # Push is consolidated into the v2 planner
                    # (send_due_notifications). Legacy coaching jobs are SMS-only
                    # so there's exactly one path emitting pushes.
                    want_push = False
                    if not want_sms and not want_push:
                        continue

                    onboarding = user.onboarding or {}
                    tz_name = onboarding.get("timezone", "UTC")
                    try:
                        user_tz = ZoneInfo(tz_name)
                    except Exception:
                        user_tz = ZoneInfo("UTC")

                    local_now = datetime.now(ZoneInfo("UTC")).astimezone(user_tz)
                    _iso = local_now.isocalendar()
                    iso_wk = f"{_iso[0]}-W{_iso[1]:02d}"
                    fitmax_result = await db.execute(
                        select(UserSchedule).where(
                            (UserSchedule.user_id == user.id)
                            & (UserSchedule.maxx_id == "fitmax")
                            & (UserSchedule.is_active == True)
                        ).limit(1)
                    )
                    has_fitmax = fitmax_result.scalar_one_or_none() is not None
                    if not _sms_fast_mode():
                        # Widened from an EXACT hour to a 2-hour window: a deploy/
                        # restart re-anchors the interval timer and can push the
                        # fire past a single target hour, skipping the whole week.
                        # The ISO-week idempotency check below keeps this safe.
                        if has_fitmax:
                            if local_now.weekday() != 6 or not (19 <= local_now.hour <= 20):
                                continue
                        else:
                            if local_now.weekday() != 0 or not (9 <= local_now.hour <= 10):
                                continue

                    state_result = await db.execute(
                        select(UserCoachingState).where(UserCoachingState.user_id == user.id)
                    )
                    state = state_result.scalar_one_or_none()
                    if not state:
                        continue
                    # Idempotency: at most one weekly reset per ISO week per user,
                    # so the widened window can't double-send.
                    if not _sms_fast_mode() and state.last_weekly_reset_iso_week == iso_wk:
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
                    ok, http_status = await send_apns_alert(apns_tok, "Max", msg_text)
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
                        st.last_weekly_reset_iso_week = iso_wk
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


async def sync_google_calendars():
    """Poll Google Calendar for every connected user (30-min cadence). The
    events land in the same calendar_events table the device path uses, so
    the merge/today-read/feasibility logic is identical either way."""
    try:
        from models.sqlalchemy_models import CalendarConnection
        from services.google_integration import google_oauth_available, sync_google_calendar

        if not google_oauth_available():
            return
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(CalendarConnection).where(
                    (CalendarConnection.provider == "google")
                    & (CalendarConnection.is_active.is_(True))
                )
            )
            user_ids = [c.user_id for c in res.scalars().all()]

        # Sync users with BOUNDED concurrency (was fully serial → >30min at
        # scale). Cap at 3, NOT higher: sync_google_calendar holds its pooled
        # connection across the ~20s httpx round-trip, and the Supabase pooler
        # can be as small as a few slots — a wide fan-out would starve live
        # API traffic. Each user gets its own session + per-user error isolation.
        sem = asyncio.Semaphore(3)

        async def _sync_one(uid):
            async with sem:
                try:
                    async with AsyncSessionLocal() as db:
                        await sync_google_calendar(uid, db)
                except Exception as e:
                    logger.warning("google calendar poll failed for %s: %s", uid, e)

        await asyncio.gather(*[_sync_one(uid) for uid in user_ids])
    except Exception as e:
        logger.error(f"Google calendar poll job error: {e}", exc_info=True)


async def keep_plan_horizons():
    """Backstop for users who haven't opened the app: extend any active
    schedule whose runway is nearly out (the lazy check in /planner/today
    covers active users)."""
    try:
        from services.horizon import HORIZON_MIN_DAYS, ensure_plan_horizon
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(UserSchedule.user_id).where(UserSchedule.is_active.is_(True)).distinct()
            )
            user_ids = [r[0] for r in res.all()]
        for uid in user_ids:
            try:
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, uid)
                    if user is not None:
                        await ensure_plan_horizon(user, db)
            except Exception as e:
                logger.warning("horizon keep failed for %s: %s", uid, e)
    except Exception as e:
        logger.error(f"Horizon job error: {e}", exc_info=True)


async def send_queued_notifications():
    """Deliver queued pushes (e.g. broadcasts queued for an asleep user's next
    in-window slot) whose scheduled_for has arrived — still subject to the
    planner's window + cap + min-interval (review item 5), never bypassing them."""
    if bool(getattr(settings, "notif_kill_switch", False)):
        return
    try:
        from models.sqlalchemy_models import ScheduledNotification
        from services.notification_copy import build_push_custom, _CATEGORY_ROUTE
        from services.notification_planner import in_window, PlannerConfig
        cfg = PlannerConfig.from_settings()
        now_utc = datetime.now(ZoneInfo("UTC"))
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(ScheduledNotification)
                .where(
                    (ScheduledNotification.status == "pending")
                    & (ScheduledNotification.scheduled_for <= now_utc.replace(tzinfo=None))
                )
                .limit(500)
            )
            rows = res.scalars().all()
            # Warm the identity map with ONE query so the per-row db.get(User)
            # below is a cache hit rather than an N+1 across up to 500 rows.
            if rows:
                await db.execute(select(User).where(User.id.in_({r.user_id for r in rows})))
            for row in rows:
                try:
                    user = await db.get(User, row.user_id)
                    if not user or not user_allows_proactive_push(user.onboarding, user.apns_device_token):
                        row.status = "cancelled"
                        continue
                    ob = dict(user.onboarding or {})
                    category = row.category_id or "broadcast"
                    if category in ns.muted_categories(ob):
                        row.status = "cancelled"
                        continue
                    try:
                        tz = ZoneInfo(ob.get("timezone") or "UTC")
                    except Exception:
                        tz = ZoneInfo("UTC")
                    local_now = now_utc.astimezone(tz)
                    now_min = local_now.hour * 60 + local_now.minute
                    wake_p = _parse_task_time_parts(str(ob.get("wake_time") or "07:00")) or (7, 0)
                    sleep_p = _parse_task_time_parts(str(ob.get("sleep_time") or "23:00")) or (23, 0)
                    wake_min, sleep_min = wake_p[0] * 60 + wake_p[1], sleep_p[0] * 60 + sleep_p[1]
                    if not in_window(now_min, wake_min, sleep_min):
                        continue  # still asleep — try again next tick
                    state = ns.get_state(user.profile)
                    today_iso = local_now.date().isoformat()
                    # Respect the per-user daily cap + min-interval so a queued
                    # broadcast can't push a user over the ceiling. Use the ADAPTIVE
                    # effective_cap (matches the task-due path) rather than the raw
                    # cfg.cap — effective_cap only ever clamps <= cfg.cap, so this
                    # can only make queued delivery equal or more conservative.
                    lapse_days = int(getattr(settings, "notif_lapse_days", 4) or 4)
                    deliv, opened, returning = ns.backoff_inputs(state, local_now, lapse_days=lapse_days)
                    cap = effective_cap(cfg.cap, recent_delivered=deliv, recent_opened=opened, returning_lapsed=returning)
                    if ns.sent_count_today(state, today_iso) >= cap:
                        continue
                    last = ns.last_send_min_today(state, today_iso)
                    if last is not None and (now_min - last) < cfg.min_interval_min:
                        continue
                    route = _CATEGORY_ROUTE.get(category, "Home")
                    params: dict = {"category": category}
                    dlp = getattr(row, "deep_link_params", None)
                    if isinstance(dlp, dict) and dlp:
                        params.update(dlp)
                    # A feed deep-link is useless without its maxxId (the screen
                    # can't render) — degrade old/paramless rows to Home.
                    if route == "CreatorFeed" and not params.get("maxxId"):
                        route = "Home"
                    custom = build_push_custom(category, route, params)
                    name = ((user.profile or {}).get("identity") or {}).get("name")
                    title = "from max" if not name else f"from max, {name}"
                    ok, http_status = await send_apns_alert(
                        (user.apns_device_token or "").strip(), title, row.message, custom=custom
                    )
                    if apns_response_should_invalidate_token(http_status):
                        user.apns_device_token = None
                        user.apns_token_updated_at = None
                        row.status = "failed"
                        continue
                    if ok:
                        state = ns.record_delivered(state, local_now)
                        state = ns.record_sent(state, today_iso, f"cat:{category}", local_now)
                        user.profile = ns.put_state(dict(user.profile or {}), state)
                        flag_modified(user, "profile")
                        row.status = "sent"
                        row.sent_at = now_utc.replace(tzinfo=None)
                except Exception as re_err:
                    logger.warning("queued notif %s failed: %s", row.id, re_err)
            await db.commit()
    except Exception as e:
        logger.error(f"Queued notifications job error: {e}", exc_info=True)


async def reconcile_expired_subscriptions():
    """Self-heal lapsed subscriptions the DB missed.

    An Apple EXPIRED / DID_FAIL_TO_RENEW ASN (or a comp expiry) can be dropped or
    delayed, leaving is_paid=True with a subscription_end_date already in the
    past. The middleware read-guard (auth_middleware._user_dict / require_paid_user)
    already denies access for those rows, but the stored is_paid stays stale and
    background jobs that filter on `is_paid == True` (coaching, weekly, etc.) keep
    treating them as active. Flip is_paid=False + status='expired' for any
    apple/referral_comp row whose end date has passed so the DB matches reality.
    Stripe is intentionally excluded here — Stripe manages its own dunning window
    and emits explicit cancel/expire events.
    """
    try:
        from datetime import timezone as _tz
        from sqlalchemy import update, and_, or_
        now_utc = datetime.now(_tz.utc)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(User)
                .where(
                    and_(
                        User.is_paid == True,  # noqa: E712
                        User.subscription_end_date.isnot(None),
                        User.subscription_end_date < now_utc,
                        or_(
                            User.billing_provider == "apple",
                            User.billing_provider == "referral_comp",
                        ),
                        # admins/scan users are never billing-gated
                        User.is_admin == False,  # noqa: E712
                    )
                )
                .values(is_paid=False, subscription_status="expired")
            )
            await db.commit()
            if result.rowcount:
                logger.info("reconcile_expired_subscriptions: expired %s stale row(s)", result.rowcount)
    except Exception as e:
        logger.error("reconcile_expired_subscriptions job error: %s", e, exc_info=True)


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
        scheduler.add_job(
            keep_plan_horizons,
            "interval",
            minutes=120,
            id="plan_horizons",
            **job_defaults,
        )
        scheduler.add_job(
            sync_google_calendars,
            "interval",
            minutes=30,
            id="google_calendar_poll",
            **job_defaults,
        )
        scheduler.add_job(
            reconcile_lapsed_creator_subs,
            "interval",
            minutes=60,
            id="creator_sub_reconcile",
            **job_defaults,
        )
        scheduler.add_job(
            send_queued_notifications,
            "interval",
            minutes=sched_m,
            id="queued_notifications",
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
        scheduler.add_job(
            reconcile_expired_subscriptions,
            "interval",
            minutes=60,
            id="reconcile_expired_subscriptions",
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
