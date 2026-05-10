from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.members.models import OrgMembership
from apps.workspaces.models import Workspace

from .defaults import APP_DEFAULTS
from .models import OrgSetting, WorkspaceSetting

ORG_SETTING_KEYS = {k for k in APP_DEFAULTS if k.startswith(("org.", "infra."))}
WORKSPACE_SETTING_KEYS = {k for k in APP_DEFAULTS if not k.startswith(("org.", "infra."))}

SETTING_META = {
    "org.2fa_enforcement": {"label": "Require 2FA for all members", "type": "bool", "group": "Security"},
    "org.login_rate_limit_max_attempts": {"label": "Login max attempts", "type": "int", "group": "Security"},
    "org.login_rate_limit_lockout_minutes": {"label": "Lockout duration (minutes)", "type": "int", "group": "Security"},
    "org.session_duration_days": {"label": "Session duration (days)", "type": "int", "group": "Security"},
    "org.invitation_expiry_days": {"label": "Invitation expiry (days)", "type": "int", "group": "Members"},
    "org.magic_link_expiry_days": {"label": "Magic link expiry (days)", "type": "int", "group": "Members"},
    "org.deletion_grace_period_days": {"label": "Deletion grace period (days)", "type": "int", "group": "Data"},
    "org.deletion_confirmation_link_expiry_hours": {
        "label": "Deletion link expiry (hours)",
        "type": "int",
        "group": "Data",
    },
    "org.publish_log_retention_days": {"label": "Publish log retention (days)", "type": "int", "group": "Data"},
    "org.webhook_delivery_log_retention_days": {
        "label": "Webhook log retention (days)",
        "type": "int",
        "group": "Data",
    },
    "org.audit_log_retention_days": {"label": "Audit log retention (days)", "type": "int", "group": "Data"},
    "org.stock_media_attribution": {"label": "Require stock media attribution", "type": "bool", "group": "Media"},
    "org.email_batching_delay_minutes": {
        "label": "Email batching delay (minutes)",
        "type": "int",
        "group": "Notifications",
    },
    "infra.publishing_poll_seconds": {
        "label": "Publishing poll interval (seconds)",
        "type": "int",
        "group": "Infrastructure",
    },
    "infra.account_health_check_hours": {
        "label": "Account health check (hours)",
        "type": "int",
        "group": "Infrastructure",
    },
    "infra.token_refresh_check_hours": {
        "label": "Token refresh check (hours)",
        "type": "int",
        "group": "Infrastructure",
    },
    "infra.token_refresh_lookahead_hours": {
        "label": "Token refresh lookahead (hours)",
        "type": "int",
        "group": "Infrastructure",
    },
    "infra.max_concurrent_publish_jobs": {
        "label": "Max concurrent publish jobs",
        "type": "int",
        "group": "Infrastructure",
    },
    "infra.media_preprocessing_lookahead_minutes": {
        "label": "Media preprocessing lookahead (minutes)",
        "type": "int",
        "group": "Infrastructure",
    },
    "infra.recurrence_generation_interval": {
        "label": "Recurrence generation interval",
        "type": "str",
        "group": "Infrastructure",
    },
    "infra.cleanup_job_schedule": {"label": "Cleanup job schedule", "type": "str", "group": "Infrastructure"},
    "approval.internal_reminder_hours": {
        "label": "Internal reminder interval (hours)",
        "type": "int",
        "group": "Approvals",
    },
    "approval.client_reminder_hours": {
        "label": "Client reminder interval (hours)",
        "type": "int",
        "group": "Approvals",
    },
    "approval.max_reminders_per_post": {"label": "Max reminders per post", "type": "int", "group": "Approvals"},
    "approval.stalled_post_escalation": {"label": "Escalate stalled posts", "type": "bool", "group": "Approvals"},
    "approval.email_subject_template": {
        "label": "Approval email subject template",
        "type": "str",
        "group": "Approvals",
    },
    "publishing.first_comment_delay_seconds": {
        "label": "First comment delay (seconds)",
        "type": "int",
        "group": "Publishing",
    },
    "publishing.retry_max_attempts": {"label": "Retry max attempts", "type": "int", "group": "Publishing"},
    "publishing.retry_backoff_schedule": {"label": "Retry backoff schedule", "type": "str", "group": "Publishing"},
    "scheduling.recurring_post_lookahead_days": {
        "label": "Recurring post lookahead (days)",
        "type": "int",
        "group": "Scheduling",
    },
    "scheduling.queue_empty_slot_warning_days": {
        "label": "Empty slot warning (days)",
        "type": "int",
        "group": "Scheduling",
    },
    "inbox.sync_interval_minutes": {"label": "Sync interval (minutes)", "type": "int", "group": "Inbox"},
    "inbox.auto_resolve_on_reply": {"label": "Auto-resolve on reply", "type": "bool", "group": "Inbox"},
    "inbox.sla_target_response_minutes": {"label": "SLA target response (minutes)", "type": "int", "group": "Inbox"},
    "analytics.optimal_time_lookback_days": {
        "label": "Optimal time lookback (days)",
        "type": "int",
        "group": "Analytics",
    },
    "analytics.optimal_time_min_posts": {"label": "Optimal time min posts", "type": "int", "group": "Analytics"},
    "analytics.high_frequency_collection_hours": {
        "label": "High-frequency collection (hours)",
        "type": "int",
        "group": "Analytics",
    },
    "notifications.quiet_hours_start": {"label": "Quiet hours start (HH:MM)", "type": "str", "group": "Notifications"},
    "notifications.quiet_hours_end": {"label": "Quiet hours end (HH:MM)", "type": "str", "group": "Notifications"},
    "notifications.digest_mode": {
        "label": "Digest mode (batch notifications)",
        "type": "bool",
        "group": "Notifications",
    },
    "onboarding.client_connection_link_expiry_days": {
        "label": "Client connection link expiry (days)",
        "type": "int",
        "group": "Onboarding",
    },
}


def _is_org_admin(request):
    try:
        m = OrgMembership.objects.get(user=request.user, organization=request.org)
        return m.org_role in (OrgMembership.OrgRole.OWNER, OrgMembership.OrgRole.ADMIN)
    except OrgMembership.DoesNotExist:
        return False


def _coerce(value_str, setting_type):
    if setting_type == "bool":
        return value_str in ("1", "true", "on", "yes")
    if setting_type == "int":
        try:
            return int(value_str)
        except (ValueError, TypeError):
            return None
    return value_str


def _build_org_sections(org):
    overrides = {s.key: s.value for s in OrgSetting.objects.filter(organization=org)}
    groups = {}
    for key in ORG_SETTING_KEYS:
        meta = SETTING_META.get(key, {"label": key, "type": "str", "group": "Other"})
        group = meta["group"]
        groups.setdefault(group, [])
        groups[group].append(
            {
                "key": key,
                "label": meta["label"],
                "type": meta["type"],
                "default": APP_DEFAULTS.get(key),
                "value": overrides.get(key, APP_DEFAULTS.get(key)),
                "overridden": key in overrides,
            }
        )
    return [{"group": g, "settings": s} for g, s in sorted(groups.items())]


def _build_workspace_sections(workspace):
    overrides = {s.key: s.value for s in WorkspaceSetting.objects.filter(workspace=workspace)}
    groups = {}
    for key in WORKSPACE_SETTING_KEYS:
        meta = SETTING_META.get(key, {"label": key, "type": "str", "group": "Other"})
        group = meta["group"]
        groups.setdefault(group, [])
        groups[group].append(
            {
                "key": key,
                "label": meta["label"],
                "type": meta["type"],
                "default": APP_DEFAULTS.get(key),
                "value": overrides.get(key, APP_DEFAULTS.get(key)),
                "overridden": key in overrides,
            }
        )
    return [{"group": g, "settings": s} for g, s in sorted(groups.items())]


@login_required
def settings_index(request):
    if not _is_org_admin(request):
        messages.error(request, "Only organization admins can manage settings.")
        return redirect("/")

    org = request.org
    workspaces = list(Workspace.objects.filter(organization=org).order_by("name"))

    active_workspace_id = request.GET.get("workspace")
    active_workspace = None
    if active_workspace_id:
        active_workspace = next((w for w in workspaces if str(w.id) == active_workspace_id), None)

    org_sections = _build_org_sections(org)
    workspace_sections = _build_workspace_sections(active_workspace) if active_workspace else []

    return render(
        request,
        "settings_manager/index.html",
        {
            "settings_active": "settings",
            "org_sections": org_sections,
            "workspaces": workspaces,
            "active_workspace": active_workspace,
            "workspace_sections": workspace_sections,
        },
    )


@login_required
@require_POST
def save_org_setting(request, key):
    if not _is_org_admin(request):
        return JsonResponse({"error": "Permission denied"}, status=403)
    if key not in ORG_SETTING_KEYS:
        return JsonResponse({"error": "Unknown setting"}, status=400)

    meta = SETTING_META.get(key, {"type": "str"})
    raw = request.POST.get("value", "")
    value = _coerce(raw, meta["type"])

    if value is None and meta["type"] == "int":
        messages.error(request, "Invalid number.")
        return redirect(request.META.get("HTTP_REFERER", "/settings/"))

    OrgSetting.objects.update_or_create(
        organization=request.org,
        key=key,
        defaults={"value": value},
    )
    messages.success(request, "Setting saved.")
    return redirect(request.META.get("HTTP_REFERER", "/settings/"))


@login_required
@require_POST
def reset_org_setting(request, key):
    if not _is_org_admin(request):
        return JsonResponse({"error": "Permission denied"}, status=403)
    OrgSetting.objects.filter(organization=request.org, key=key).delete()
    messages.success(request, "Setting reset to default.")
    return redirect(request.META.get("HTTP_REFERER", "/settings/"))


@login_required
@require_POST
def save_workspace_setting(request, workspace_id, key):
    if not _is_org_admin(request):
        return JsonResponse({"error": "Permission denied"}, status=403)
    if key not in WORKSPACE_SETTING_KEYS:
        return JsonResponse({"error": "Unknown setting"}, status=400)

    workspace = get_object_or_404(Workspace, id=str(workspace_id), organization=request.org)
    meta = SETTING_META.get(key, {"type": "str"})
    raw = request.POST.get("value", "")
    value = _coerce(raw, meta["type"])

    if value is None and meta["type"] == "int":
        messages.error(request, "Invalid number.")
        return redirect(f"/settings/?workspace={workspace_id}")

    WorkspaceSetting.objects.update_or_create(
        workspace=workspace,
        key=key,
        defaults={"value": value},
    )
    messages.success(request, "Setting saved.")
    return redirect(f"/settings/?workspace={workspace_id}")


@login_required
@require_POST
def reset_workspace_setting(request, workspace_id, key):
    if not _is_org_admin(request):
        return JsonResponse({"error": "Permission denied"}, status=403)
    workspace = get_object_or_404(Workspace, id=str(workspace_id), organization=request.org)
    WorkspaceSetting.objects.filter(workspace=workspace, key=key).delete()
    messages.success(request, "Setting reset to default.")
    return redirect(f"/settings/?workspace={workspace_id}")
