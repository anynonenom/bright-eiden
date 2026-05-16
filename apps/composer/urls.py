from django.urls import path

from . import views

app_name = "composer"

urlpatterns = [
    # Create landing page
    path("create/", views.create_landing, name="create_landing"),
    # Idea CRUD (HTMX endpoints)
    path("ideas/upload-media/", views.idea_upload_media, name="idea_upload_media"),
    path("ideas/create/", views.idea_create, name="idea_create"),
    path("ideas/<uuid:idea_id>/create-post/", views.idea_create_post, name="idea_create_post"),
    path("ideas/<uuid:idea_id>/edit/", views.idea_edit, name="idea_edit"),
    path("ideas/<uuid:idea_id>/delete/", views.idea_delete, name="idea_delete"),
    path("ideas/<uuid:idea_id>/move/", views.idea_move, name="idea_move"),
    # Idea approval workflow
    path("ideas/<uuid:idea_id>/submit/", views.idea_submit_for_review, name="idea_submit_for_review"),
    path("ideas/<uuid:idea_id>/approve/", views.idea_approve, name="idea_approve"),
    path("ideas/<uuid:idea_id>/reject/", views.idea_reject, name="idea_reject"),
    path("ideas/<uuid:idea_id>/request-changes/", views.idea_request_changes, name="idea_request_changes"),
    path("ideas/board/", views.idea_board, name="idea_board"),
    # Idea groups (Kanban columns)
    path("ideas/groups/create/", views.idea_group_create, name="idea_group_create"),
    path("ideas/groups/<uuid:group_id>/delete/", views.idea_group_delete, name="idea_group_delete"),
    path("ideas/groups/reorder/", views.idea_group_reorder, name="idea_group_reorder"),
    # Composer page
    path("compose/", views.compose, name="compose"),
    path("compose/<uuid:post_id>/", views.compose, name="compose_edit"),
    # Save actions
    path("compose/save/", views.save_post, name="save_post"),
    path("compose/<uuid:post_id>/save/", views.save_post, name="save_post_edit"),
    # Per-platform status transition (one PlatformPost at a time)
    path(
        "compose/<uuid:post_id>/platform-posts/<uuid:platform_post_id>/transition/",
        views.transition_platform_post,
        name="transition_platform_post",
    ),
    # Auto-save
    path("compose/autosave/", views.autosave, name="autosave"),
    path("compose/<uuid:post_id>/autosave/", views.autosave, name="autosave_edit"),
    # Live preview
    path("compose/preview/", views.preview, name="preview"),
    # Media
    path("compose/media-picker/", views.media_picker, name="media_picker"),
    path("compose/thumbnail-picker/", views.thumbnail_picker, name="thumbnail_picker"),
    path("compose/thumbnail-upload/", views.thumbnail_upload, name="thumbnail_upload"),
    path("compose/pinterest-boards/<uuid:account_id>/", views.pinterest_boards, name="pinterest_boards"),
    path("compose/<uuid:post_id>/media-picker/", views.media_picker, name="media_picker_post"),
    path("compose/<uuid:post_id>/attach-media/", views.attach_media, name="attach_media"),
    path("compose/attach-pending-media/", views.attach_pending_media, name="attach_pending_media"),
    path("compose/upload-media/", views.upload_media, name="upload_media"),
    path("compose/<uuid:post_id>/upload-media/", views.upload_media, name="upload_media_post"),
    path("compose/<uuid:post_id>/remove-media/<uuid:media_id>/", views.remove_media, name="remove_media"),
    path("compose/remove-pending-media/<uuid:asset_id>/", views.remove_pending_media, name="remove_pending_media"),
    # Drafts
    path("drafts/", views.drafts_list, name="drafts_list"),
    # Post delete
    path("compose/<uuid:post_id>/delete/", views.post_delete, name="post_delete"),
    # Content Categories
    path("categories/", views.category_list, name="category_list"),
    path("categories/create/", views.category_create, name="category_create"),
    path("categories/<uuid:category_id>/edit/", views.category_edit, name="category_edit"),
    path("categories/<uuid:category_id>/delete/", views.category_delete, name="category_delete"),
    # Hashtag Sets
    path("hashtags/", views.hashtag_set_list, name="hashtag_set_list"),
    path("hashtags/create/", views.hashtag_set_create, name="hashtag_set_create"),
    path("hashtags/<uuid:set_id>/delete/", views.hashtag_set_delete, name="hashtag_set_delete"),
    path("hashtags/api/", views.hashtag_sets_api, name="hashtag_sets_api"),
    # CSV Import
    path("import/csv/", views.csv_upload, name="csv_upload"),
    path("import/csv/preview/", views.csv_preview, name="csv_preview"),
    path("import/csv/confirm/", views.csv_confirm_import, name="csv_confirm_import"),
    # Tags
    path("tags/", views.tag_list, name="tag_list"),
    path("tags/create/", views.tag_create, name="tag_create"),
]
