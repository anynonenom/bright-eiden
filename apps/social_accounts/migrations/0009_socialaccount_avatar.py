from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("social_accounts", "0008_socialaccount_is_virtual"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialaccount",
            name="avatar",
            field=models.ImageField(blank=True, upload_to="social_accounts/avatars/%Y/%m/"),
        ),
    ]
