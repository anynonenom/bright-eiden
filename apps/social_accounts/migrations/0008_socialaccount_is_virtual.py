from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("social_accounts", "0007_increase_avatar_url_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialaccount",
            name="is_virtual",
            field=models.BooleanField(default=False),
        ),
    ]
