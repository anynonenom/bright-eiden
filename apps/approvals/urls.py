from django.urls import path

from . import views

app_name = "approvals"

urlpatterns = [
    path("approvals/", views.approval_queue, name="queue"),
    path("approvals/<uuid:post_id>/panel/", views.post_detail_panel, name="post_detail_panel"),
    path("approvals/<uuid:post_id>/approve/", views.approve, name="approve"),
    path("approvals/<uuid:post_id>/request-changes/", views.request_changes_view, name="request_changes"),
    path("approvals/<uuid:post_id>/reject/", views.reject, name="reject"),
    path("approvals/<uuid:post_id>/schedule/", views.schedule_post, name="schedule_post"),
    path("approvals/<uuid:post_id>/comments/", views.add_comment, name="add_comment"),
    path("approvals/<uuid:post_id>/comments/<uuid:comment_id>/edit/", views.edit_comment, name="edit_comment"),
    path("approvals/<uuid:post_id>/comments/<uuid:comment_id>/delete/", views.delete_comment, name="delete_comment"),
]
