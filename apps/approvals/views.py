"""Views for the Approval Workflow (F-2.2)."""

import json
import zoneinfo
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.composer.models import Post
from apps.members.decorators import require_permission, require_workspace_role
from apps.workspaces.models import Workspace

from . import comments as comment_service
from . import services
from .models import PostComment


def _get_workspace(request, workspace_id):
    from django.core.exceptions import PermissionDenied

    from apps.members.models import WorkspaceMembership

    workspace = get_object_or_404(Workspace, id=workspace_id)
    if not request.user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    if not WorkspaceMembership.objects.filter(user=request.user, workspace=workspace).exists():
        raise PermissionDenied("You do not have access to this workspace.")
    return workspace


# ---------------------------------------------------------------------------
# Approval Queue
# ---------------------------------------------------------------------------


@login_required
@require_permission("approve_posts")
@require_GET
def approval_queue(request, workspace_id):
    """Workspace-level approval queue showing posts by status."""
    workspace = _get_workspace(request, workspace_id)

    status_filter = request.GET.get("status", "pending_review")

    from apps.composer.models import PlatformPost

    base_qs = (
        Post.objects.for_workspace(workspace.id)
        .select_related("author")
        .prefetch_related("platform_posts__social_account", "media_attachments__media_asset")
    )

    status_map = {
        "pending_review": {"platform_posts__status": "pending_review"},
        "approved": {"platform_posts__status": "approved"},
        "changes_requested": {"platform_posts__status": "changes_requested"},
        "rejected": {"platform_posts__status": "rejected"},
    }
    filter_kwargs = status_map.get(status_filter, {"platform_posts__status": "pending_review"})
    order = "scheduled_at" if status_filter in ("pending_review", "approved") else "-created_at"
    posts = base_qs.filter(**filter_kwargs).distinct().order_by(order)

    pp_qs = PlatformPost.objects.filter(post__workspace=workspace)
    pending_review_count = pp_qs.filter(status="pending_review").values("post_id").distinct().count()
    approved_count = pp_qs.filter(status="approved").values("post_id").distinct().count()
    changes_requested_count = pp_qs.filter(status="changes_requested").values("post_id").distinct().count()
    rejected_count = pp_qs.filter(status="rejected").values("post_id").distinct().count()

    context = {
        "workspace": workspace,
        "posts": posts,
        "status_filter": status_filter,
        "pending_review_count": pending_review_count,
        "approved_count": approved_count,
        "changes_requested_count": changes_requested_count,
        "rejected_count": rejected_count,
    }

    if request.htmx:
        return render(request, "approvals/partials/post_list.html", context)

    return render(request, "approvals/queue.html", context)


# ---------------------------------------------------------------------------
# Approval Actions
# ---------------------------------------------------------------------------


@login_required
@require_permission("approve_posts")
@require_http_methods(["GET", "POST"])
def approve(request, workspace_id, post_id):
    """Approve a post."""
    workspace = _get_workspace(request, workspace_id)
    if request.method == "GET":
        return redirect("approvals:queue", workspace_id=workspace_id)
    post = get_object_or_404(Post, id=post_id, workspace=workspace)
    comment_text = request.POST.get("comment", "")

    try:
        services.approve_post(post, request.user, workspace, comment_text)
    except ValueError as e:
        return HttpResponse(str(e), status=400)

    if request.htmx:
        # Return updated post row partial
        return render(
            request,
            "approvals/partials/post_row.html",
            {
                "post": post,
                "workspace": workspace,
            },
        )

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": json.dumps({"approvalAction": {"postId": str(post.id), "action": "approved"}}),
        },
    )


@login_required
@require_permission("approve_posts")
@require_http_methods(["GET", "POST"])
def request_changes_view(request, workspace_id, post_id):
    """Request changes on a post."""
    workspace = _get_workspace(request, workspace_id)
    post = get_object_or_404(Post, id=post_id, workspace=workspace)

    if request.method == "GET":
        return redirect("approvals:queue", workspace_id=workspace_id)

    comment_text = request.POST.get("comment", "")

    try:
        services.request_changes(post, request.user, workspace, comment_text)
    except ValueError as e:
        return HttpResponse(str(e), status=400)

    if request.htmx:
        return render(
            request,
            "approvals/partials/post_row.html",
            {
                "post": post,
                "workspace": workspace,
            },
        )

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": json.dumps({"approvalAction": {"postId": str(post.id), "action": "changes_requested"}}),
        },
    )


@login_required
@require_permission("approve_posts")
@require_http_methods(["GET", "POST"])
def reject(request, workspace_id, post_id):
    """Reject a post."""
    workspace = _get_workspace(request, workspace_id)
    if request.method == "GET":
        return redirect("approvals:queue", workspace_id=workspace_id)
    post = get_object_or_404(Post, id=post_id, workspace=workspace)
    comment_text = request.POST.get("comment", "")

    try:
        services.reject_post(post, request.user, workspace, comment_text)
    except ValueError as e:
        return HttpResponse(str(e), status=400)

    if request.htmx:
        return render(
            request,
            "approvals/partials/post_row.html",
            {
                "post": post,
                "workspace": workspace,
            },
        )

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": json.dumps({"approvalAction": {"postId": str(post.id), "action": "rejected"}}),
        },
    )


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------


@login_required
@require_permission("approve_posts")
@require_POST
def schedule_post(request, workspace_id, post_id):
    """Schedule an approved post directly from the approval queue."""
    workspace = _get_workspace(request, workspace_id)
    post = get_object_or_404(Post, id=post_id, workspace=workspace)

    scheduled_date = request.POST.get("scheduled_date", "").strip()
    scheduled_time = request.POST.get("scheduled_time", "").strip()

    if not scheduled_date or not scheduled_time:
        return HttpResponse("Date and time are required.", status=400)

    try:
        naive_dt = datetime.strptime(f"{scheduled_date} {scheduled_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return HttpResponse("Invalid date or time format.", status=400)

    tz_name = getattr(workspace, "effective_timezone", None) or "UTC"
    tz = zoneinfo.ZoneInfo(tz_name)
    aware_dt = naive_dt.replace(tzinfo=tz)

    if aware_dt <= timezone.now():
        return HttpResponse("Scheduled time must be in the future.", status=400)

    post.scheduled_at = aware_dt
    post.save(update_fields=["scheduled_at", "updated_at"])

    for pp in post.platform_posts.all():
        if pp.status == "approved":
            pp.scheduled_at = aware_dt
            pp.status = "scheduled"
            pp.save(update_fields=["status", "scheduled_at", "updated_at"])

    if request.htmx:
        return render(
            request,
            "approvals/partials/post_row.html",
            {"post": post, "workspace": workspace},
        )

    return HttpResponse(status=204)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


@login_required
@require_workspace_role("viewer")
@require_POST
def add_comment(request, workspace_id, post_id):
    """Add a comment to a post."""
    workspace = _get_workspace(request, workspace_id)
    post = get_object_or_404(Post, id=post_id, workspace=workspace)

    body = request.POST.get("body", "").strip()
    if not body:
        return HttpResponse("Comment body is required.", status=400)

    visibility = request.POST.get("visibility", PostComment.Visibility.EXTERNAL)
    parent_id = request.POST.get("parent_id") or None
    attachment = request.FILES.get("attachment")

    try:
        comment_service.create_comment(
            post=post,
            author=request.user,
            body=body,
            visibility=visibility,
            parent_id=parent_id,
            attachment=attachment,
        )
    except ValueError as e:
        return HttpResponse(str(e), status=400)

    # Return updated comment list
    comments = comment_service.get_comments_for_post(post, request.user)
    return render(
        request,
        "approvals/partials/comment_list.html",
        {
            "comments": comments,
            "post": post,
            "workspace": workspace,
        },
    )


@login_required
@require_workspace_role("viewer")
@require_POST
def edit_comment(request, workspace_id, post_id, comment_id):
    """Edit a comment."""
    _get_workspace(request, workspace_id)
    body = request.POST.get("body", "").strip()

    if not body:
        return HttpResponse("Comment body is required.", status=400)

    try:
        comment_service.update_comment(comment_id, request.user, body)
    except (ValueError, PermissionError) as e:
        return HttpResponse(str(e), status=400 if isinstance(e, ValueError) else 403)

    post = get_object_or_404(Post, id=post_id)
    comments = comment_service.get_comments_for_post(post, request.user)
    return render(
        request,
        "approvals/partials/comment_list.html",
        {
            "comments": comments,
            "post": post,
            "workspace": post.workspace,
        },
    )


@login_required
@require_workspace_role("viewer")
@require_POST
def delete_comment(request, workspace_id, post_id, comment_id):
    """Soft-delete a comment."""
    workspace = _get_workspace(request, workspace_id)

    try:
        comment_service.delete_comment(comment_id, request.user, workspace)
    except (ValueError, PermissionError) as e:
        return HttpResponse(str(e), status=400 if isinstance(e, ValueError) else 403)

    post = get_object_or_404(Post, id=post_id, workspace=workspace)
    comments = comment_service.get_comments_for_post(post, request.user)
    return render(
        request,
        "approvals/partials/comment_list.html",
        {
            "comments": comments,
            "post": post,
            "workspace": workspace,
        },
    )


