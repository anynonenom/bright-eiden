"""Platform credentials management views.

Org admins can store encrypted app credentials (App ID / Secret) for each
social platform. These are used as the default when connecting social accounts.
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.members.models import OrgMembership

from .models import PlatformCredential

logger = logging.getLogger(__name__)


# Fields required per platform, in display order.
PLATFORM_FIELDS = {
    "facebook": [
        {"name": "app_id", "label": "App ID", "secret": False, "placeholder": "e.g. 123456789012345"},
        {"name": "app_secret", "label": "App Secret", "secret": True, "placeholder": "32-character hex"},
    ],
    "instagram": [
        {"name": "app_id", "label": "App ID", "secret": False, "placeholder": "Same as Facebook App ID"},
        {"name": "app_secret", "label": "App Secret", "secret": True, "placeholder": "Same as Facebook App Secret"},
    ],
    "instagram_login": [
        {"name": "app_id", "label": "App ID", "secret": False, "placeholder": "Instagram App ID"},
        {"name": "app_secret", "label": "App Secret", "secret": True, "placeholder": "Instagram App Secret"},
    ],
    "threads": [
        {"name": "app_id", "label": "App ID", "secret": False, "placeholder": "Same as Facebook App ID"},
        {"name": "app_secret", "label": "App Secret", "secret": True, "placeholder": "Same as Facebook App Secret"},
    ],
    "linkedin_personal": [
        {"name": "client_id", "label": "Client ID", "secret": False, "placeholder": "e.g. 86abc123xyz"},
        {"name": "client_secret", "label": "Client Secret", "secret": True, "placeholder": "LinkedIn app secret"},
    ],
    "linkedin_company": [
        {"name": "client_id", "label": "Client ID", "secret": False, "placeholder": "e.g. 86abc123xyz"},
        {"name": "client_secret", "label": "Client Secret", "secret": True, "placeholder": "LinkedIn app secret"},
    ],
    "tiktok": [
        {"name": "client_key", "label": "Client Key", "secret": False, "placeholder": "TikTok client key"},
        {"name": "client_secret", "label": "Client Secret", "secret": True, "placeholder": "TikTok client secret"},
    ],
    "youtube": [
        {"name": "client_id", "label": "Client ID", "secret": False, "placeholder": "Google OAuth client ID"},
        {
            "name": "client_secret",
            "label": "Client Secret",
            "secret": True,
            "placeholder": "Google OAuth client secret",
        },
    ],
    "google_business": [
        {
            "name": "client_id",
            "label": "Client ID",
            "secret": False,
            "placeholder": "Same as YouTube (shared Google app)",
        },
        {
            "name": "client_secret",
            "label": "Client Secret",
            "secret": True,
            "placeholder": "Same as YouTube (shared Google app)",
        },
    ],
    "pinterest": [
        {"name": "app_id", "label": "App ID", "secret": False, "placeholder": "Pinterest App ID"},
        {"name": "app_secret", "label": "App Secret", "secret": True, "placeholder": "Pinterest App Secret"},
    ],
    "bluesky": [],  # session-auth, no app credentials
    "mastodon": [],  # per-instance OAuth, no repo-wide credentials
}

# Developer docs and redirect URI info per platform.
PLATFORM_SETUP_INFO = {
    "facebook": {
        "docs_url": "https://developers.facebook.com/apps/",
        "redirect_path": "/social-accounts/oauth/callback/facebook/",
        "note": "Facebook, Instagram (via Facebook Login), and Threads share the same Meta App.",
    },
    "instagram": {
        "docs_url": "https://developers.facebook.com/apps/",
        "redirect_path": "/social-accounts/oauth/callback/instagram/",
        "note": "Uses the same Meta App as Facebook. Add Instagram Basic Display or Instagram Graph API product.",
    },
    "instagram_login": {
        "docs_url": "https://developers.facebook.com/apps/",
        "redirect_path": "/social-accounts/oauth/callback/instagram_login/",
        "note": "Separate Instagram App (Instagram Login). Lets Business/Creator accounts connect without a linked Facebook Page.",
    },
    "threads": {
        "docs_url": "https://developers.facebook.com/apps/",
        "redirect_path": "/social-accounts/oauth/callback/threads/",
        "note": "Uses the same Meta App as Facebook. Enable the Threads API product.",
    },
    "linkedin_personal": {
        "docs_url": "https://www.linkedin.com/developers/apps/",
        "redirect_path": "/social-accounts/oauth/callback/linkedin_personal/",
        "note": None,
    },
    "linkedin_company": {
        "docs_url": "https://www.linkedin.com/developers/apps/",
        "redirect_path": "/social-accounts/oauth/callback/linkedin_company/",
        "note": "Requires Community Management API access from LinkedIn.",
    },
    "tiktok": {
        "docs_url": "https://developers.tiktok.com/apps/",
        "redirect_path": "/social-accounts/oauth/callback/tiktok/",
        "note": None,
    },
    "youtube": {
        "docs_url": "https://console.cloud.google.com/apis/credentials",
        "redirect_path": "/social-accounts/oauth/callback/youtube/",
        "note": "YouTube and Google Business Profile share the same Google OAuth app.",
    },
    "google_business": {
        "docs_url": "https://console.cloud.google.com/apis/credentials",
        "redirect_path": "/social-accounts/oauth/callback/google_business/",
        "note": "Same Google OAuth app as YouTube.",
    },
    "pinterest": {
        "docs_url": "https://developers.pinterest.com/apps/",
        "redirect_path": "/social-accounts/oauth/callback/pinterest/",
        "note": None,
    },
    "bluesky": {
        "docs_url": None,
        "redirect_path": None,
        "note": "No app credentials needed. Users connect with their handle and an App Password.",
    },
    "mastodon": {
        "docs_url": None,
        "redirect_path": None,
        "note": "No credentials needed. The app registers itself automatically with each Mastodon instance.",
    },
}


def _is_org_admin(request):
    if not getattr(request, "org", None):
        return False
    try:
        membership = OrgMembership.objects.get(user=request.user, organization=request.org)
        return membership.org_role in (OrgMembership.OrgRole.OWNER, OrgMembership.OrgRole.ADMIN)
    except OrgMembership.DoesNotExist:
        return False


@login_required
def credentials_list(request):
    """Show all platforms with their credential status and a save form."""
    if not getattr(request, "org", None):
        messages.error(request, "No organization found. Please create or join an organization first.")
        return redirect("dashboard")
    if not _is_org_admin(request):
        messages.error(request, "Only organization admins can manage platform credentials.")
        return redirect("dashboard")

    # Load existing credentials keyed by platform
    existing = {c.platform: c for c in PlatformCredential.objects.for_org(request.org.id)}

    # Build context list in PlatformCredential.Platform order
    platform_data = []
    for value, label in PlatformCredential.Platform.choices:
        cred = existing.get(value)
        fields = PLATFORM_FIELDS.get(value, [])
        setup = PLATFORM_SETUP_INFO.get(value, {})
        app_url = request.build_absolute_uri("/").rstrip("/")
        platform_data.append(
            {
                "value": value,
                "label": label,
                "fields": fields,
                "is_configured": cred.is_configured if cred else False,
                "masked": cred.masked_credentials if cred else {},
                "test_result": cred.test_result if cred else PlatformCredential.TestResult.UNTESTED,
                "has_fields": bool(fields),
                "docs_url": setup.get("docs_url"),
                "redirect_uri": (app_url + setup["redirect_path"]) if setup.get("redirect_path") else None,
                "note": setup.get("note"),
            }
        )

    return render(
        request,
        "credentials/list.html",
        {
            "platform_data": platform_data,
            "settings_active": "credentials",
        },
    )


@login_required
@require_POST
def credential_save(request, platform):
    """Save (create or update) credentials for a platform."""
    if not getattr(request, "org", None):
        messages.error(request, "No organization found.")
        return redirect("dashboard")
    if not _is_org_admin(request):
        messages.error(request, "Only organization admins can manage platform credentials.")
        return redirect("credentials:list")

    if platform not in PLATFORM_FIELDS:
        messages.error(request, "Unknown platform.")
        return redirect("credentials:list")

    fields = PLATFORM_FIELDS[platform]
    if not fields:
        messages.info(request, "This platform does not require app credentials.")
        return redirect("credentials:list")

    # Collect submitted values
    new_creds = {}
    for field in fields:
        val = request.POST.get(field["name"], "").strip()
        if val:
            new_creds[field["name"]] = val

    # Merge with existing secrets for fields left blank (preserve previous secrets)
    cred, _ = PlatformCredential.objects.for_org(request.org.id).get_or_create(
        platform=platform,
        defaults={"organization": request.org, "credentials": {}},
    )
    existing_creds = dict(cred.credentials or {})
    for field in fields:
        name = field["name"]
        if name not in new_creds and name in existing_creds:
            new_creds[name] = existing_creds[name]

    all_filled = all(new_creds.get(f["name"], "").strip() for f in fields)

    cred.credentials = new_creds
    cred.is_configured = all_filled
    cred.test_result = PlatformCredential.TestResult.UNTESTED
    cred.save()

    if all_filled:
        messages.success(request, f"{cred.get_platform_display()} credentials saved.")
    else:
        messages.warning(
            request,
            f"{cred.get_platform_display()} credentials partially saved — fill all fields to enable the platform.",
        )

    return redirect("credentials:list")


@login_required
@require_POST
def credential_clear(request, platform):
    """Clear credentials for a platform."""
    if not getattr(request, "org", None):
        messages.error(request, "No organization found.")
        return redirect("dashboard")
    if not _is_org_admin(request):
        messages.error(request, "Only organization admins can manage platform credentials.")
        return redirect("credentials:list")

    try:
        cred = PlatformCredential.objects.for_org(request.org.id).get(platform=platform)
        cred.credentials = {}
        cred.is_configured = False
        cred.test_result = PlatformCredential.TestResult.UNTESTED
        cred.save()
        messages.success(request, f"{cred.get_platform_display()} credentials cleared.")
    except PlatformCredential.DoesNotExist:
        pass

    return redirect("credentials:list")
