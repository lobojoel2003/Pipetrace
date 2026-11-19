from django.core.management.base import BaseCommand, CommandError

from pipetrace.inventory import geocoding


class Command(BaseCommand):
    help = "Find map locations for lines that don't have one (U.S. Census geocoder or Pelias)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--retry-failed",
            action="store_true",
            help="Also retry addresses that were not found before.",
        )
        parser.add_argument("--batch-size", type=int, help="Addresses per request.")
        parser.add_argument(
            "--geocoder", choices=["census", "pelias"], help="Override PIPETRACE_GEOCODER."
        )
        parser.add_argument(
            "--max-batches",
            type=int,
            default=0,
            help="Stop after this many batches (0 = until done).",
        )

    def handle(self, *args, **opts):
        geocoder = geocoding.get_geocoder(opts["geocoder"])
        if geocoder is None:
            raise CommandError("Geocoding is turned off. Set PIPETRACE_GEOCODER=census or pelias.")
        if opts["retry_failed"]:
            self.stdout.write(f"{geocoding.reset_failed()} unmatched addresses queued again.")
        batches = 0
        totals = geocoding.Progress()
        while True:
            progress = geocoding.geocode_batch(geocoder, opts["batch_size"])
            if progress.error:
                raise CommandError(progress.error)
            batches += 1
            totals.processed += progress.processed
            totals.matched += progress.matched
            totals.approximate += progress.approximate
            totals.failed += progress.failed
            self.stdout.write(
                f"Batch {batches}: {progress.matched} matched, "
                f"{progress.approximate} approximate, {progress.failed} not found; "
                f"{progress.remaining} left."
            )
            if not progress.processed or not progress.remaining:
                break
            if opts["max_batches"] and batches >= opts["max_batches"]:
                break
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {totals.matched} matched, {totals.approximate} approximate, "
                f"{totals.failed} not found."
            )
        )
