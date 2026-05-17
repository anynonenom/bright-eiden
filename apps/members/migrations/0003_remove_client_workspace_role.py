from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0002_invitation_org_role"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workspacemembership",
            name="workspace_role",
            field=models.CharField(
                choices=[
                    ("owner", "Owner"),
                    ("manager", "Manager"),
                    ("editor", "Editor"),
                    ("contributor", "Contributor"),
                    ("viewer", "Viewer"),
                ],
                default="viewer",
                max_length=30,
            ),
        ),
    ]
