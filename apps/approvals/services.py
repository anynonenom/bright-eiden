"""Approval workflow business logic.

Editorial status now lives on ``PlatformPost`` so every social account flows
through the workflow independently. The functions in this module accept either
a ``Post`` (apply the action to *all* eligible children — the historical
"bundled" behaviour) or a single ``PlatformPost`` (per-account decision).

For the bundled case the resulting :class:`ApprovalAction` row stores
``platform_post=None``; for per-account decisions ``platform_post`` is set so
the audit trail remembers exactly which target was acted on.
"""

import logging

from django.db import transaction

from apps.composer.models import PlatformPost, Post
from apps.members.models import WorkspaceMembership
from apps.notifications.engine import notify
from apps.notifications.models import EventType

from .models import ApprovalAction, ApprovalReminder, PostApprovalStage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_targets(target, *, eligible_from_states=None):
    """Normalise *target* into ``(post, [platform_posts], is_bundled)``.

    ``target`` may be a :class:`Post` (returns every child whose current state
    is in ``eligible_from_states``, or all children if not specified) or a
    :class:`PlatformPost` (returns just that one). Eligibility filtering keeps
    bundled actions from blowing up on already-published or already-approved
    siblings.
    """
    if isinstance(target, PlatformPost):
        return target.post, [target], False

    if not isinstance(target, Post):
        raise TypeError(f"Expected Post or PlatformPost, got {type(target).__name__}")

    children = list(target.platform_posts.select_related("social_account"))
    if eligible_from_states is not None:
        children = [pp for pp in children if pp.status in eligible_from_states]
    return target, children, True


def _transition_or_skip(pp, target_status):
    """Transition *pp* to *target_status*, returning True on success."""
    if pp.status == target_status:
        return True
    if not pp.can_transition_to(target_status):
        return False
    pp.transition_to(target_status)
    pp.save(update_fields=["status", "published_at", "updated_at"])
    return True


def _record_action(post, platform_post, user, action, comment=""):
    """Create an ApprovalAction row for either a bundled or per-PP action."""
    return ApprovalAction.objects.create(
        post=post,
        platform_post=platform_post,
        user=user,
        action=action,
        comment=comment,
    )


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


def submit_for_review(target, user, workspace, stages=None):
    """Submit a post (or single platform post) for internal review.

    ``stages`` is an optional list of dicts: [{name, assigned_to_id}, ...] in
    desired order. When provided, custom :class:`PostApprovalStage` rows are
    created and only the first-stage assignee is notified. When omitted the
    historic behaviour (notify every reviewer) applies.
    """
    post, targets, is_bundled = _resolve_targets(
        target, eligible_from_states={"draft", "changes_requested", "rejected"}
    )

    moved = []
    with transaction.atomic():
        for pp in targets:
            if _transition_or_skip(pp, "pending_review"):
                moved.append(pp)
        if not moved:
            return post

        if is_bundled:
            _record_action(post, None, user, ApprovalAction.ActionType.SUBMITTED)
        else:
            for pp in moved:
                _record_action(post, pp, user, ApprovalAction.ActionType.SUBMITTED)

        ApprovalReminder.objects.update_or_create(
            post=post,
            stage="pending_review",
            defaults={"reminder_count": 0, "last_reminder_at": None, "escalated": False},
        )

        if stages:
            PostApprovalStage.objects.filter(post=post).delete()
            for i, stage_data in enumerate(stages):
                PostApprovalStage.objects.create(
                    post=post,
                    name=stage_data["name"],
                    order=i + 1,
                    assigned_to_id=stage_data.get("assigned_to_id") or None,
                )

    if stages:
        first_stage = PostApprovalStage.objects.filter(post=post).order_by("order").first()
        if first_stage and first_stage.assigned_to and first_stage.assigned_to != user:
            notify(
                user=first_stage.assigned_to,
                event_type=EventType.POST_SUBMITTED,
                title=f'Review needed: {first_stage.name}',
                body=f'{user.display_name} is waiting on your review "{post.caption_snippet}"',
                data={"post_id": str(post.id), "workspace_id": str(workspace.id)},
            )
    else:
        # Notify all reviewers (members with approve_posts permission)
        reviewers = WorkspaceMembership.objects.filter(workspace=workspace).select_related("user", "custom_role")
        for membership in reviewers:
            perms = membership.effective_permissions
            if perms.get("approve_posts", False) and membership.user != user:
                notify(
                    user=membership.user,
                    event_type=EventType.POST_SUBMITTED,
                    title="Post submitted for review",
                    body=f'{user.display_name} submitted a post for your review: "{post.caption_snippet}"',
                    data={
                        "post_id": str(post.id),
                        "workspace_id": str(workspace.id),
                    },
                )

    return post


def approve_post(target, user, workspace, comment=""):
    """Approve a post or single platform post.

    When the post has custom :class:`PostApprovalStage` rows the approval
    advances to the next pending stage rather than fully approving immediately.
    Once all stages are cleared the post is fully approved.
    """
    from django.utils import timezone

    post, targets, is_bundled = _resolve_targets(
        target, eligible_from_states={"pending_review", "draft", "rejected", "changes_requested"}
    )

    # --- Custom stage pipeline ---
    current_stage = PostApprovalStage.objects.filter(post=post, status="pending").order_by("order").first()
    if current_stage:
        with transaction.atomic():
            current_stage.status = PostApprovalStage.Status.APPROVED
            current_stage.approved_at = timezone.now()
            current_stage.approved_by = user
            current_stage.comment = comment
            current_stage.save()
            _record_action(post, None, user, ApprovalAction.ActionType.APPROVED, comment)

        next_stage = PostApprovalStage.objects.filter(post=post, status="pending").order_by("order").first()
        if next_stage:
            if next_stage.assigned_to and next_stage.assigned_to != user:
                notify(
                    user=next_stage.assigned_to,
                    event_type=EventType.POST_SUBMITTED,
                    title=f'Your review needed: {next_stage.name}',
                    body=f'Stage "{current_stage.name}" was cleared — your review is up: "{post.caption_snippet}"',
                    data={"post_id": str(post.id), "workspace_id": str(workspace.id)},
                )
            return post
        # All stages done — fall through to full approval below

    # --- Standard approval ---
    moved = []
    with transaction.atomic():
        for pp in targets:
            if not _transition_or_skip(pp, "approved"):
                continue
            moved.append(pp)

        if not moved:
            return post

        if is_bundled:
            _record_action(post, None, user, ApprovalAction.ActionType.APPROVED, comment)
        else:
            for pp in moved:
                _record_action(post, pp, user, ApprovalAction.ActionType.APPROVED, comment)

    if post.author and post.author != user:
        notify(
            user=post.author,
            event_type=EventType.POST_APPROVED,
            title="Post approved",
            body=f'Your post "{post.caption_snippet}" was approved by {user.display_name}.',
            data={
                "post_id": str(post.id),
                "workspace_id": str(workspace.id),
            },
        )

    return post


def request_changes(target, user, workspace, comment):
    """Request changes on a post or single platform post. Comment is required."""
    if not comment.strip():
        raise ValueError("A comment is required when requesting changes.")

    post, targets, is_bundled = _resolve_targets(target, eligible_from_states={"pending_review"})

    moved = []
    with transaction.atomic():
        for pp in targets:
            if _transition_or_skip(pp, "changes_requested"):
                moved.append(pp)
        if not moved:
            return post

        if is_bundled:
            _record_action(post, None, user, ApprovalAction.ActionType.CHANGES_REQUESTED, comment)
        else:
            for pp in moved:
                _record_action(post, pp, user, ApprovalAction.ActionType.CHANGES_REQUESTED, comment)

    if post.author and post.author != user:
        notify(
            user=post.author,
            event_type=EventType.POST_CHANGES_REQUESTED,
            title="Changes requested on your post",
            body=f'{user.display_name} requested changes: "{comment[:100]}"',
            data={
                "post_id": str(post.id),
                "workspace_id": str(workspace.id),
            },
        )

    return post


def reject_post(target, user, workspace, comment):
    """Reject a post or single platform post. Comment is required."""
    if not comment.strip():
        raise ValueError("A comment is required when rejecting a post.")

    post, targets, is_bundled = _resolve_targets(target, eligible_from_states={"pending_review"})

    moved = []
    with transaction.atomic():
        for pp in targets:
            if _transition_or_skip(pp, "rejected"):
                moved.append(pp)
        if not moved:
            return post

        if is_bundled:
            _record_action(post, None, user, ApprovalAction.ActionType.REJECTED, comment)
        else:
            for pp in moved:
                _record_action(post, pp, user, ApprovalAction.ActionType.REJECTED, comment)

    if post.author and post.author != user:
        notify(
            user=post.author,
            event_type=EventType.POST_REJECTED,
            title="Post rejected",
            body=f'{user.display_name} rejected your post: "{comment[:100]}"',
            data={
                "post_id": str(post.id),
                "workspace_id": str(workspace.id),
            },
        )

    return post


def resubmit_post(target, user, workspace):
    """Resubmit a post or single platform post after changes/rejection."""
    post, targets, is_bundled = _resolve_targets(target, eligible_from_states={"changes_requested", "rejected"})

    moved = []
    with transaction.atomic():
        for pp in targets:
            if _transition_or_skip(pp, "pending_review"):
                moved.append(pp)
        if not moved:
            return post

        if is_bundled:
            _record_action(post, None, user, ApprovalAction.ActionType.RESUBMITTED)
        else:
            for pp in moved:
                _record_action(post, pp, user, ApprovalAction.ActionType.RESUBMITTED)

        ApprovalReminder.objects.update_or_create(
            post=post,
            stage="pending_review",
            defaults={"reminder_count": 0, "last_reminder_at": None, "escalated": False},
        )

    reviewers = WorkspaceMembership.objects.filter(workspace=workspace).select_related("user", "custom_role")
    for membership in reviewers:
        perms = membership.effective_permissions
        if perms.get("approve_posts", False) and membership.user != user:
            notify(
                user=membership.user,
                event_type=EventType.POST_SUBMITTED,
                title="Post resubmitted for review",
                body=f'{user.display_name} resubmitted a post: "{post.caption_snippet}"',
                data={
                    "post_id": str(post.id),
                    "workspace_id": str(workspace.id),
                },
            )

    return post


def bulk_approve(post_ids, user, workspace):
    """Approve all eligible PlatformPosts under each post (bundled per post)."""
    results = []
    posts = Post.objects.filter(
        id__in=post_ids,
        workspace=workspace,
        platform_posts__status__in=["pending_review"],
    ).distinct()

    for post in posts:
        try:
            approve_post(post, user, workspace)
            results.append((str(post.id), True, None))
        except ValueError as e:
            results.append((str(post.id), False, str(e)))

    return results


def bulk_reject(post_ids, user, workspace, comment):
    """Reject all eligible PlatformPosts under each post (bundled per post)."""
    if not comment.strip():
        raise ValueError("A comment is required for bulk rejection.")

    results = []
    posts = Post.objects.filter(
        id__in=post_ids,
        workspace=workspace,
        platform_posts__status__in=["pending_review"],
    ).distinct()

    for post in posts:
        try:
            reject_post(post, user, workspace, comment)
            results.append((str(post.id), True, None))
        except ValueError as e:
            results.append((str(post.id), False, str(e)))

    return results


def _notify_clients(post, workspace):
    """Send CLIENT_APPROVAL_REQUESTED notification to all client members."""
    client_memberships = WorkspaceMembership.objects.filter(
        workspace=workspace,
        workspace_role=WorkspaceMembership.WorkspaceRole.CLIENT,
    ).select_related("user")

    for membership in client_memberships:
        notify(
            user=membership.user,
            event_type=EventType.CLIENT_APPROVAL_REQUESTED,
            title="Posts ready for your review",
            body=f"A post in {workspace.name} is waiting for your approval.",
            data={
                "post_id": str(post.id),
                "workspace_id": str(workspace.id),
            },
        )
