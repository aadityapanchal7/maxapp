"""User notification channel preferences (SMS vs APNs) derived from onboarding JSON + device token."""


def onboarding_allows_proactive_sms(onboarding: dict | None) -> bool:
    """Same rules as sendblue_service.onboarding_allows_proactive_sms — imported for callers that avoid circular imports."""
    from services.sendblue_service import onboarding_allows_proactive_sms as _sms

    return _sms(onboarding)


def user_allows_proactive_push(onboarding: dict | None, apns_device_token: str | None) -> bool:
    """True when user opted into app notifications and we have an APNs token."""
    if not (apns_device_token or "").strip():
        return False
    ob = onboarding or {}
    if ob.get("app_notifications_opt_in") is False:
        return False
    return True


def schedule_sms_marked_sent(task: dict) -> bool:
    """SMS reminder already delivered (including legacy notification_sent)."""
    if task.get("notification_sent_sms") is True:
        return True
    if task.get("notification_sent") is True:
        return True
    return False


def schedule_push_marked_sent(task: dict) -> bool:
    """APNs reminder already delivered for this task."""
    return task.get("notification_sent_push") is True


def schedule_needs_any_channel(
    task: dict,
    *,
    want_sms: bool,
    want_push: bool,
) -> bool:
    """True if this pending task still needs at least one enabled channel."""
    if task.get("status") != "pending":
        return False
    sms_pending = want_sms and not schedule_sms_marked_sent(task)
    push_pending = want_push and not schedule_push_marked_sent(task)
    return sms_pending or push_pending


def mark_schedule_sms_sent(task: dict) -> None:
    task["notification_sent_sms"] = True
    task["notification_sent"] = True


def mark_schedule_push_sent(task: dict) -> None:
    task["notification_sent_push"] = True
