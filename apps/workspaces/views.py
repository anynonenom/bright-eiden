from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.members import services as member_services
from apps.members.decorators import require_org_role
from apps.members.models import Invitation, OrgMembership, WorkspaceMembership

from .models import Workspace


@login_required
def workspace_list(request):
    memberships = WorkspaceMembership.objects.filter(user=request.user).select_related("workspace")
    workspaces = [m.workspace for m in memberships if not m.workspace.is_archived]
    return render(request, "workspaces/list.html", {"workspaces": workspaces})


@login_required
@require_POST
@require_org_role(OrgMembership.OrgRole.ADMIN)
def workspace_create(request):
    """Create a new workspace in the user's organization."""
    name = request.POST.get("name", "").strip()
    if not name:
        return redirect("dashboard")

    if not request.org:
        return redirect("dashboard")

    workspace = Workspace.objects.create(
        organization=request.org,
        name=name,
    )

    WorkspaceMembership.objects.create(
        user=request.user,
        workspace=workspace,
        workspace_role=WorkspaceMembership.WorkspaceRole.OWNER,
    )

    # Set as current workspace
    request.user.last_workspace_id = workspace.id
    request.user.save(update_fields=["last_workspace_id"])

    return redirect("calendar:calendar", workspace_id=workspace.id)


@login_required
@require_http_methods(["GET", "POST"])
def workspace_settings(request, workspace_id):
    try:
        workspace = Workspace.objects.get(id=workspace_id)
    except Workspace.DoesNotExist:
        raise Http404 from None

    membership = WorkspaceMembership.objects.filter(user=request.user, workspace=workspace).first()
    if not membership:
        raise Http404

    is_owner_or_manager = membership.workspace_role in (
        WorkspaceMembership.WorkspaceRole.OWNER,
        WorkspaceMembership.WorkspaceRole.MANAGER,
    )

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "archive_workspace" and is_owner_or_manager:
            with transaction.atomic():
                active_count = (
                    Workspace.objects.select_for_update()
                    .filter(organization=workspace.organization, is_archived=False)
                    .count()
                )
                if active_count <= 1:
                    messages.error(request, "Cannot archive the last workspace in the organization.")
                    return redirect("workspaces:settings", workspace_id=workspace.id)
                workspace.is_archived = True
                workspace.save(update_fields=["is_archived"])
            messages.success(request, f'Workspace "{workspace.name}" has been archived.')
            return redirect("organizations:workspaces")

        if action == "unarchive_workspace" and is_owner_or_manager:
            workspace.is_archived = False
            workspace.save(update_fields=["is_archived"])
            messages.success(request, f'Workspace "{workspace.name}" has been restored.')
            return redirect("workspaces:settings", workspace_id=workspace.id)

        if action == "delete_workspace" and is_owner_or_manager:
            with transaction.atomic():
                active_count = (
                    Workspace.objects.select_for_update()
                    .filter(organization=workspace.organization, is_archived=False)
                    .count()
                )
                if active_count <= 1 and not workspace.is_archived:
                    messages.error(request, "Cannot delete the last workspace in the organization.")
                    return redirect("workspaces:settings", workspace_id=workspace.id)
                workspace_name = workspace.name
                workspace.delete()
            messages.success(request, f'Workspace "{workspace_name}" has been permanently deleted.')
            return redirect("organizations:workspaces")

        name = request.POST.get("name", "").strip()

        if name:
            workspace.name = name

        # Handle logo deletion
        if request.POST.get("delete_icon") == "1":
            if workspace.icon:
                workspace.icon.delete(save=False)
        # Handle logo upload
        elif "icon" in request.FILES:
            icon = request.FILES["icon"]

            # Validate file type
            allowed_types = ("image/jpeg", "image/png", "image/webp", "image/gif")
            if icon.content_type not in allowed_types:
                messages.error(request, "Logo must be a JPEG, PNG, WebP, or GIF image.")
                return redirect("workspaces:settings", workspace_id=workspace.id)

            # Validate file size (2 MB max)
            max_size = 2 * 1024 * 1024
            if icon.size > max_size:
                messages.error(request, "Logo must be under 2 MB.")
                return redirect("workspaces:settings", workspace_id=workspace.id)

            # Delete old icon before saving new one
            if workspace.icon:
                workspace.icon.delete(save=False)
            workspace.icon = icon

        workspace.save()
        messages.success(request, "Workspace settings updated.")
        return redirect("workspaces:settings", workspace_id=workspace.id)

    active_count = Workspace.objects.filter(organization=workspace.organization, is_archived=False).count()
    is_last_active = active_count <= 1 and not workspace.is_archived
    can_archive = is_owner_or_manager and not workspace.is_archived and not is_last_active
    can_delete = is_owner_or_manager and not is_last_active

    return render(
        request,
        "workspaces/settings.html",
        {
            "workspace": workspace,
            "settings_active": "general",
            "is_owner_or_manager": is_owner_or_manager,
            "can_archive": can_archive,
            "can_delete": can_delete,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def approvals_settings(request, workspace_id):
    try:
        workspace = Workspace.objects.get(id=workspace_id)
    except Workspace.DoesNotExist:
        raise Http404 from None

    membership = WorkspaceMembership.objects.filter(user=request.user, workspace=workspace).first()
    if not membership:
        raise Http404

    is_owner_or_manager = membership.workspace_role in (
        WorkspaceMembership.WorkspaceRole.OWNER,
        WorkspaceMembership.WorkspaceRole.MANAGER,
    )

    if request.method == "POST":
        if not is_owner_or_manager:
            raise Http404

        mode = request.POST.get("approval_workflow_mode", "")
        valid_modes = Workspace.ApprovalWorkflowMode.values
        if mode not in valid_modes:
            messages.error(request, "Invalid approval workflow mode.")
            return redirect("workspaces:approvals_settings", workspace_id=workspace.id)

        workspace.approval_workflow_mode = mode
        workspace.save(update_fields=["approval_workflow_mode", "updated_at"])
        messages.success(request, "Approval workflow updated.")
        return redirect("workspaces:approvals_settings", workspace_id=workspace.id)

    return render(
        request,
        "workspaces/approvals_settings.html",
        {
            "workspace": workspace,
            "settings_active": "approvals",
            "is_owner_or_manager": is_owner_or_manager,
            "approval_modes": Workspace.ApprovalWorkflowMode,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def workspace_members(request, workspace_id):
    """Workspace-scoped members management."""
    workspace = get_object_or_404(Workspace, id=workspace_id, organization=request.org)

    my_membership = WorkspaceMembership.objects.filter(user=request.user, workspace=workspace).first()
    if not my_membership:
        raise Http404

    is_manager = my_membership.workspace_role in (
        WorkspaceMembership.WorkspaceRole.OWNER,
        WorkspaceMembership.WorkspaceRole.MANAGER,
    )

    if request.method == "POST":
        if not is_manager:
            return HttpResponse("Permission denied.", status=403)

        action = request.POST.get("action")

        if action == "invite":
            email = request.POST.get("email", "").strip()
            ws_role = request.POST.get("ws_role", WorkspaceMembership.WorkspaceRole.VIEWER)
            try:
                invitation = member_services.create_invitation(
                    org=request.org,
                    email=email,
                    org_role=OrgMembership.OrgRole.MEMBER,
                    workspace_assignments=[{"workspace_id": str(workspace.id), "role": ws_role}],
                    invited_by=request.user,
                )
            except ValueError as e:
                if request.headers.get("HX-Request"):
                    return HttpResponse(f'<p class="text-red-600 text-sm">{e}</p>', status=422)
                messages.error(request, str(e))
                return redirect("workspaces:workspace_members", workspace_id=workspace.id)

            if request.headers.get("HX-Request"):
                return render(request, "workspaces/partials/ws_invite_row.html", {
                    "invite": invitation,
                    "workspace": workspace,
                    "is_manager": is_manager,
                })
            messages.success(request, f"Invitation sent to {email}.")
            return redirect("workspaces:workspace_members", workspace_id=workspace.id)

        if action == "remove":
            membership_id = request.POST.get("membership_id")
            wm = get_object_or_404(WorkspaceMembership, id=membership_id, workspace=workspace)
            if wm.user == request.user:
                if request.headers.get("HX-Request"):
                    return HttpResponse("You cannot remove yourself.", status=400)
                messages.error(request, "You cannot remove yourself.")
                return redirect("workspaces:workspace_members", workspace_id=workspace.id)
            wm.delete()
            if request.headers.get("HX-Request"):
                return HttpResponse(status=200, headers={"HX-Trigger": "memberRemoved"})
            return redirect("workspaces:workspace_members", workspace_id=workspace.id)

        if action == "update_role":
            membership_id = request.POST.get("membership_id")
            new_role = request.POST.get("ws_role")
            wm = get_object_or_404(WorkspaceMembership, id=membership_id, workspace=workspace)
            valid_roles = [r for r, _ in WorkspaceMembership.WorkspaceRole.choices]
            if new_role in valid_roles:
                wm.workspace_role = new_role
                wm.save(update_fields=["workspace_role"])
            if request.headers.get("HX-Request"):
                return HttpResponse(status=200)
            return redirect("workspaces:workspace_members", workspace_id=workspace.id)

    # GET
    ws_memberships = (
        WorkspaceMembership.objects.filter(workspace=workspace)
        .select_related("user")
        .order_by("added_at")
    )

    pending_invites = (
        Invitation.objects.filter(
            organization=request.org,
            accepted_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .filter(workspace_assignments__contains=[{"workspace_id": str(workspace.id)}])
        .select_related("invited_by")
        .order_by("-created_at")
    ) if is_manager else []

    return render(request, "workspaces/workspace_members.html", {
        "workspace": workspace,
        "settings_active": "members",
        "ws_memberships": ws_memberships,
        "pending_invites": pending_invites,
        "is_manager": is_manager,
        "workspace_role_choices": WorkspaceMembership.WorkspaceRole.choices,
        "current_user": request.user,
    })
