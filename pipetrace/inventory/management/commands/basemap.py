from django.conf import settings
from django.contrib.gis.db.models import Extent
from django.core.management.base import BaseCommand, CommandError

from pipetrace.inventory.models import ServiceLine


class Command(BaseCommand):
    help = (
        "Print the command that cuts a Protomaps basemap for your service area, so the map "
        "needs no tile service or fees. Requires the pmtiles CLI (github.com/protomaps/go-pmtiles)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--margin",
            type=float,
            default=0.02,
            help="Degrees of margin around the lines (default 0.02).",
        )
        parser.add_argument("--maxzoom", type=int, default=15)
        parser.add_argument(
            "--build",
            default="https://build.protomaps.com/YYYYMMDD.pmtiles",
            help="Protomaps daily build URL (see maps.protomaps.com/builds).",
        )

    def handle(self, *args, **opts):
        extent = (
            ServiceLine.objects.public()
            .filter(location__isnull=False)
            .aggregate(e=Extent("location"))["e"]
        )
        if not extent:
            raise CommandError("No line has a location yet. Import and geocode first.")
        m = opts["margin"]
        west, south, east, north = extent
        bbox = f"{west - m:.4f},{south - m:.4f},{east + m:.4f},{north + m:.4f}"
        target = settings.PIPETRACE_BASEMAP_DIR / "area.pmtiles"
        self.stdout.write("1. Cut your area out of the free Protomaps world basemap:\n")
        self.stdout.write(
            f"   pmtiles extract {opts['build']} {target} \\\n"
            f"     --bbox={bbox} --maxzoom={opts['maxzoom']}\n"
        )
        self.stdout.write("2. In the admin, set Site settings → Basemap PMTiles URL to:\n")
        self.stdout.write("   /basemap/area.pmtiles\n")
        self.stdout.write("The static export copies the file, so the static site keeps working.")
