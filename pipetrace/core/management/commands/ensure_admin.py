import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Create a superuser from PIPETRACE_ADMIN_USER / PIPETRACE_ADMIN_PASSWORD / "
        "PIPETRACE_ADMIN_EMAIL if no user with that name exists (used by the Docker image)."
    )

    def handle(self, *args, **options):
        username = os.environ.get("PIPETRACE_ADMIN_USER", "").strip()
        password = os.environ.get("PIPETRACE_ADMIN_PASSWORD", "")
        if not username or not password:
            self.stdout.write("PIPETRACE_ADMIN_USER/PASSWORD not set; no admin created.")
            return
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Admin user {username!r} already exists.")
            return
        User.objects.create_superuser(
            username=username,
            password=password,
            email=os.environ.get("PIPETRACE_ADMIN_EMAIL", ""),
        )
        self.stdout.write(self.style.SUCCESS(f"Created admin user {username!r}."))
