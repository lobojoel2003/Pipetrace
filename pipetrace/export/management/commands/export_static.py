from django.core.management.base import BaseCommand

from pipetrace.export.exporter import export_site


class Command(BaseCommand):
    help = "Write the resident site (both languages) as static files for free hosting."

    def add_arguments(self, parser):
        parser.add_argument("output", help="Folder to write the site to (it is replaced).")
        parser.add_argument(
            "--base-url",
            default="/",
            help="Path the site will live under, e.g. /Pipetrace/ for a GitHub Pages "
            "project site. Default: /",
        )
        parser.add_argument("--zip", dest="zip_path", help="Also write a .zip of the site here.")
        parser.add_argument(
            "--language",
            action="append",
            dest="languages",
            help="Only export this language (repeatable). Default: all.",
        )

    def handle(self, *args, **options):
        result = export_site(
            options["output"],
            base_url=options["base_url"],
            zip_path=options["zip_path"],
            languages=options["languages"],
            progress=lambda msg: self.stdout.write(msg),
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {result.pages} pages and {result.files} files to {result.path}"
                + (f" (zip: {result.zip_path})" if result.zip_path else "")
            )
        )
