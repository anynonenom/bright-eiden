from django.db import migrations


def enable_approval_workflow(apps, schema_editor):
    Workspace = apps.get_model("workspaces", "Workspace")
    Workspace.objects.filter(approval_workflow_mode="none").update(
        approval_workflow_mode="required_internal"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0002_replace_icon_url_with_icon"),
    ]

    operations = [
        migrations.RunPython(enable_approval_workflow, migrations.RunPython.noop),
    ]
