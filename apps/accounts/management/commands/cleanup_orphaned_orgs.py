"""
Delete auto-created personal orgs for members who belong to another org.

Run: python manage.py cleanup_orphaned_orgs
"""

from django.core.management.base import BaseCommand

from apps.members.models import OrgMembership


class Command(BaseCommand):
    help = "Delete auto-created personal orgs for users who are members of a real org."

    def handle(self, *args, **options):
        deleted = 0
        # Find users who have MORE than one org membership
        from django.db.models import Count
        users_with_multi_orgs = (
            OrgMembership.objects.values("user")
            .annotate(org_count=Count("organization"))
            .filter(org_count__gt=1)
            .values_list("user", flat=True)
        )

        for user_id in users_with_multi_orgs:
            memberships = OrgMembership.objects.filter(user_id=user_id).select_related("organization")
            # Identify personal orgs: named "My Organization" with only this one member
            for m in memberships:
                org = m.organization
                member_count = OrgMembership.objects.filter(organization=org).count()
                if org.name == "My Organization" and member_count == 1:
                    self.stdout.write(f"Deleting personal org '{org.name}' (id={org.id}) for user {user_id}")
                    org.delete()
                    deleted += 1

        self.stdout.write(self.style.SUCCESS(f"Done. Deleted {deleted} orphaned org(s)."))
