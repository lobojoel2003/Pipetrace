"""Load the fictional Millbrook demo: settings, inventory and a few resident messages."""

from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFilter

from pipetrace.core.models import SiteConfig
from pipetrace.inventory.choices import Material, Status
from pipetrace.inventory.importer import pipeline
from pipetrace.inventory.importer.detect import mapping_by_label
from pipetrace.inventory.importer.readers import read_workbook
from pipetrace.inventory.models import ImportBatch, ServiceLine
from pipetrace.residents.models import InspectionRequest, PipeCheck

DEMO_FILE = Path(__file__).resolve().parents[2] / "demo" / "millbrook-inventory.xlsx"

SETTINGS = {
    "utility_name": "Millbrook Water Department",
    "utility_name_es": "Departamento de Agua de Millbrook",
    "pwsid": "DEMO-0001",
    "phone": "(555) 010-0142",
    "email": "water@millbrook.example",
    "website": "https://millbrook.example",
    "office_address": "100 Main St, Millbrook",
    "office_hours": "Monday–Friday, 8:00 am – 4:30 pm",
    "office_hours_es": "Lunes a viernes, 8:00 a. m. – 4:30 p. m.",
    "default_city": "Millbrook",
    "default_state": "IL",
    "default_zip": "60000",
    "replacement_deadline": dt.date(2037, 11, 1),
    "replacement_program": (
        "Millbrook replaces the whole service line, the utility side and your side, at no "
        "cost to you. We will send a letter at least 45 days before work on your street "
        "starts, and a crew will need about one day of access to the spot where the pipe "
        "enters your home."
    ),
    "replacement_program_es": (
        "Millbrook reemplaza toda la línea de servicio, la parte del servicio público y la "
        "suya, sin costo para usted. Le enviaremos una carta al menos 45 días antes de que "
        "empiecen los trabajos en su calle, y un equipo necesitará acceso durante "
        "aproximadamente un día al lugar donde la tubería entra a su casa."
    ),
    "filter_program": (
        "Households with a lead or galvanized line can pick up a free pitcher filter and "
        "replacement cartridges at Town Hall, 100 Main St, during office hours."
    ),
    "filter_program_es": (
        "Los hogares con una línea de plomo o galvanizada pueden recoger gratis una jarra "
        "con filtro y cartuchos de repuesto en el Ayuntamiento, 100 Main St, en horario de "
        "oficina."
    ),
    "unknown_program": (
        "We are checking every unknown line by the end of 2027, street by street, starting "
        "with homes built before 1950. Sending us a photo of your pipe moves you to the "
        "front of the line."
    ),
    "unknown_program_es": (
        "Revisaremos todas las líneas desconocidas antes de que termine 2027, calle por "
        "calle, empezando por las casas construidas antes de 1950. Si nos envía una foto de "
        "su tubería, pasa al principio de la lista."
    ),
    "demo_mode": True,
    "map_zoom": None,
}


def demo_photo(silver: bool = True) -> ContentFile:
    """A simple drawing of a scratched pipe, standing in for a resident's photo."""
    img = Image.new("RGB", (1200, 900), (196, 186, 170))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 1200, 380], fill=(178, 170, 156))  # wall
    draw.rectangle([0, 380, 1200, 900], fill=(120, 116, 108))  # floor
    pipe = (128, 128, 126) if silver else (150, 98, 58)
    draw.rectangle([520, 0, 640, 900], fill=pipe)
    draw.rectangle([520, 0, 540, 900], fill=tuple(min(255, c + 30) for c in pipe))
    scratch = (226, 228, 230) if silver else (214, 140, 82)
    draw.rounded_rectangle([560, 420, 600, 520], radius=12, fill=scratch)
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=82)
    return ContentFile(out.getvalue(), name="demo.jpg")


class Command(BaseCommand):
    help = "Load the fictional Millbrook demo (replaces the current inventory)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--if-empty",
            action="store_true",
            help="Do nothing if the inventory already has lines (safe on every start).",
        )
        parser.add_argument(
            "--no-submissions",
            action="store_true",
            help="Don't create sample inspection requests and photos.",
        )

    def handle(self, *args, **opts):
        if opts["if_empty"] and ServiceLine.objects.exists():
            self.stdout.write("The inventory already has lines; demo not loaded.")
            return
        config = SiteConfig.load()
        for key, value in SETTINGS.items():
            setattr(config, key, value)
        config.save()

        workbook = read_workbook(DEMO_FILE)
        layout = pipeline.analyze(workbook)
        mapping = pipeline.auto_mapping(layout)
        rows = workbook.sheet(layout.sheet).rows
        extraction = pipeline.extract(rows, layout, mapping, {}, pipeline.defaults_from_config())
        batch = ImportBatch(
            original_name=DEMO_FILE.name,
            mode=ImportBatch.Mode.REPLACE,
            sheet_name=layout.sheet,
            header_row=layout.header_row,
            data_start_row=layout.data_start_row,
            columns=[c.as_dict() for c in layout.columns],
            column_map=mapping,
        )
        batch.file.save(DEMO_FILE.name, ContentFile(DEMO_FILE.read_bytes()), save=False)
        batch.save()
        stats = pipeline.commit(batch, extraction, ImportBatch.Mode.REPLACE)
        batch.stats = {**stats, "column_labels": mapping_by_label(mapping, layout.columns)}
        batch.save(update_fields=["stats"])
        self.stdout.write(f"Imported {stats['created'] + stats['updated']} demo lines.")

        if not opts["no_submissions"] and not InspectionRequest.objects.exists():
            self._submissions()
        self.stdout.write(self.style.SUCCESS("Millbrook demo loaded. Remember: it is fictional."))

    def _submissions(self):
        lines = ServiceLine.objects.public()
        unknown = list(lines.filter(status=Status.UNKNOWN)[:4])
        lead = list(lines.filter(status=Status.LEAD)[:2])
        people = [
            ("Ana Morales", "(555) 010-0187", "", "es", InspectionRequest.ContactBy.TEXT),
            ("Jordan Lee", "", "jordan@example.com", "en", InspectionRequest.ContactBy.EMAIL),
            ("Sam Carter", "(555) 010-0163", "", "en", InspectionRequest.ContactBy.PHONE),
        ]
        for line, (name, phone, email, lang, contact) in zip(unknown + lead, people, strict=False):
            InspectionRequest.objects.create(
                service_line=line,
                address=line.full_address,
                name=name,
                phone=phone,
                email=email,
                language=lang,
                contact_by=contact,
                best_time="Weekday mornings" if lang == "en" else "Por las mañanas",
                message="We have a baby at home and want to know soon."
                if lang == "en"
                else "Tenemos un bebé en casa.",
            )
        for line, silver in zip(unknown[1:3], (True, False), strict=False):
            check = PipeCheck(
                service_line=line,
                address=line.full_address,
                name="Pat Rivera",
                email="pat@example.com",
                scratch="silver" if silver else "copper",
                magnet="no_stick",
                resident_result=Material.LEAD if silver else Material.COPPER,
                notes="Pipe comes up through the basement floor next to the meter.",
            )
            check.photo.save("demo.jpg", demo_photo(silver), save=False)
            check.save()
