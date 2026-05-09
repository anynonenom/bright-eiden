from django.urls import path

from . import views

app_name = "credentials"

urlpatterns = [
    path("", views.credentials_list, name="list"),
    path("<str:platform>/save/", views.credential_save, name="save"),
    path("<str:platform>/clear/", views.credential_clear, name="clear"),
]
