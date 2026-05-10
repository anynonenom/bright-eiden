from django.urls import path, re_path

from . import views

app_name = "settings_manager"

_key = r"(?P<key>[\w.]+)"

urlpatterns = [
    path("", views.settings_index, name="index"),
    re_path(rf"org/{_key}/save/$", views.save_org_setting, name="save_org"),
    re_path(rf"org/{_key}/reset/$", views.reset_org_setting, name="reset_org"),
    re_path(
        rf"workspace/(?P<workspace_id>[0-9a-f-]+)/{_key}/save/$", views.save_workspace_setting, name="save_workspace"
    ),
    re_path(
        rf"workspace/(?P<workspace_id>[0-9a-f-]+)/{_key}/reset/$", views.reset_workspace_setting, name="reset_workspace"
    ),
]
