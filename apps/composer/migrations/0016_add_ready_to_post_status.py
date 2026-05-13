from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("composer", "0015_per_account_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="platformpost",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("pending_review", "Pending Review"),
                    ("pending_client", "Pending Client"),
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
                max_length=20,
            ),
        ),
    ]
