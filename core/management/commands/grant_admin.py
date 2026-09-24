"""Grant full admin access to a user.

    python manage.py grant_admin <username>
    python manage.py grant_admin --revoke <username>

Staff/superusers bypass all rate limits and plan quotas and can reach the
``/api/admin/`` operator endpoints.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from core.models import UserProfile


class Command(BaseCommand):
    help = "Grant (or revoke) staff/superuser admin access for a user."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--revoke", action="store_true", help="Remove admin access")

    def handle(self, *args, **options):
        username = options["username"]
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"No such user: {username}")

        grant = not options["revoke"]
        user.is_staff = grant
        user.is_superuser = grant
        user.save(update_fields=["is_staff", "is_superuser"])
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if grant:
            profile.plan = UserProfile.Plan.PRO
            profile.save(update_fields=["plan"])

        action = "granted" if grant else "revoked"
        self.stdout.write(
            self.style.SUCCESS(
                f"Admin access {action} for {username} "
                f"(is_staff={user.is_staff}, is_superuser={user.is_superuser})."
            )
        )
