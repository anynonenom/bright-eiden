import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models
import apps.common.managers


class Migration(migrations.Migration):

    dependencies = [
        ("composer", "0016_add_ready_to_post_status"),
        ("workspaces", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="HashtagSet",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                ("hashtags", models.TextField(help_text="Space or newline-separated hashtags. Each should start with #.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hashtag_sets",
                        to="workspaces.workspace",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "composer_hashtag_set",
                "ordering": ["name"],
            },
            managers=[("objects", apps.common.managers.WorkspaceScopedManager())],
        ),
    ]
