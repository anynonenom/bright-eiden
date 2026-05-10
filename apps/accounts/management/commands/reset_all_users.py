from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.organizations.models import Organization


class Command(BaseCommand):
    help = "Delete all users and organizations (one-time reset)"

    def handle(self, *args, **options):
        org_count, _ = Organization.objects.all().delete()
        user_count, _ = User.objects.all().delete()
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {org_count} organizations and {user_count} users.")
        )
