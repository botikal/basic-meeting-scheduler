"""One-time OAuth authorization for the Google Calendar integration.

    python manage.py google_oauth_setup path/to/client_secret.json

Opens a browser for the calendar's owner to sign in and approve access, then
saves a token file that scheduling/googlecal.py uses from then on. The token
file includes a refresh token, so this only needs to run once (re-run it if
access is ever revoked).
"""

from django.core.management.base import BaseCommand, CommandError

from scheduling.googlecal import SCOPES


class Command(BaseCommand):
    help = "Authorize this app against a Google Calendar (one-time OAuth setup)."

    def add_arguments(self, parser):
        parser.add_argument(
            "client_secret_file",
            help="The OAuth client JSON downloaded from Google Cloud Console "
            "(Credentials -> OAuth client ID -> Desktop app).",
        )
        parser.add_argument(
            "--out",
            default="token.json",
            help="Where to save the resulting token (default: token.json).",
        )

    def handle(self, *args, **options):
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise CommandError(
                "google-auth-oauthlib isn't installed - run: pip install -r requirements.txt"
            ) from exc

        out_path = options["out"]
        self.stdout.write("Opening your browser to sign in to Google...")
        flow = InstalledAppFlow.from_client_secrets_file(options["client_secret_file"], SCOPES)
        credentials = flow.run_local_server(port=0)

        with open(out_path, "w") as f:
            f.write(credentials.to_json())

        self.stdout.write(self.style.SUCCESS(f"Saved credentials to {out_path}"))
        self.stdout.write(
            f"Now set GOOGLE_TOKEN_FILE={out_path} and GOOGLE_CALENDAR_ID=... in your .env."
        )
