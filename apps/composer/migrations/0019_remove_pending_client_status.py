from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("composer", "0018_add_idea_approval_workflow"),
    ]

    operations = [
        migrations.AlterField(
            model_name="platformpost",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("pending_review", "Pending Review"),
                    ("approved", "Approved"),
                    ("changes_requested", "Changes Requested"),
                    ("rejected", "Rejected"),
                    ("scheduled", "Scheduled"),
                    ("publishing", "Publishing"),
                    ("published", "Published"),
                    ("ready_to_post", "Ready to Post"),
                    ("failed", "Failed"),
                ],
                default="draft",
                max_length=30,
            ),
        ),
    ]
