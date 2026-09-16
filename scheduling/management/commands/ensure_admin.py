"""Bootstrap a staff superuser from env vars, if none with that username
exists yet. Safe to run on every boot (see entrypoint.sh) - it only ever
creates, never resets a password, so it won't clobber one you've since
changed via /admin/.

Set DJANGO_SUPERUSER_USERNAME + DJANGO_SUPERUSER_PASSWORD (and optionally
DJANGO_SUPERUSER_EMAIL) to use this; no-op if either is unset.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a staff superuser from DJANGO_SUPERUSER_* env vars, if missing."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not username or not password:
            return

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            return

        User.objects.create_superuser(
            username=username,
            email=os.environ.get("DJANGO_SUPERUSER_EMAIL", ""),
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f"Created superuser '{username}'"))
