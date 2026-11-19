import json

from django.core.management.base import BaseCommand, CommandError

from pipetrace.inventory.importer import pipeline
from pipetrace.inventory.importer.detect import mapping_by_label, mapping_from_labels
from pipetrace.inventory.importer.fields import FIELDS_BY_KEY
from pipetrace.inventory.importer.readers import UnsupportedFile, read_workbook
from pipetrace.inventory.models import ImportBatch


class Command(BaseCommand):
    help = (
        "Import a service line inventory spreadsheet (.xlsx or .csv). Columns are detected "
        "automatically; use --show-mapping to check, and --mapping to override."
    )

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--sheet", help="Sheet name (default: the one that looks like data).")
        parser.add_argument("--header-row", type=int, help="1-based header row (default: auto).")
        parser.add_argument(
            "--mode",
            choices=["merge", "replace"],
            default="merge",
            help="merge: update and add lines (default). replace: also hide "
            "lines that are not in this file.",
        )
        parser.add_argument(
            "--mapping", help="JSON file {field: column header} to override the detected columns."
        )
        parser.add_argument("--save-mapping", help="Write the mapping used to this JSON file.")
        parser.add_argument(
            "--show-mapping", action="store_true", help="Print the detected columns and stop."
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Read and check the file without saving anything.",
        )

    def handle(self, *args, **opts):
        try:
            workbook = read_workbook(opts["file"])
        except (OSError, UnsupportedFile) as exc:
            raise CommandError(str(exc)) from exc
        layout = pipeline.analyze(workbook, sheet=opts["sheet"], header_row=opts["header_row"])
        mapping = pipeline.auto_mapping(layout)
        if opts["mapping"]:
            with open(opts["mapping"], encoding="utf-8") as handle:
                mapping.update(mapping_from_labels(json.load(handle), layout.columns))
        self.stdout.write(
            f"Sheet “{layout.sheet}”, header on row {layout.header_row}, data from "
            f"row {layout.data_start_row}."
        )
        for key, index in mapping.items():
            column = layout.column(index)
            self.stdout.write(f"  {FIELDS_BY_KEY[key].label:<38} ← {column.letter}: {column.label}")
        if opts["save_mapping"]:
            with open(opts["save_mapping"], "w", encoding="utf-8") as handle:
                json.dump(mapping_by_label(mapping, layout.columns), handle, indent=2)
        if opts["show_mapping"]:
            return
        problems = pipeline.validate_mapping(mapping)
        if problems:
            raise CommandError(" ".join(problems))

        rows = workbook.sheet(layout.sheet).rows
        extraction = pipeline.extract(rows, layout, mapping, {}, pipeline.defaults_from_config())
        counts = extraction.status_counts
        self.stdout.write(
            f"{len(extraction.records)} lines: {counts['lead']} lead, {counts['grr']} galvanized "
            f"requiring replacement, {counts['unknown']} unknown, {counts['non_lead']} not lead."
        )
        for message in extraction.errors[:20]:
            self.stderr.write(f"  row {message['row']}: {message['message']}")
        if len(extraction.warnings):
            self.stdout.write(
                f"{len(extraction.warnings)} warnings, {len(extraction.conflicts)} "
                "classification conflicts (see the staff import page for detail)."
            )
        if opts["dry_run"]:
            plan = pipeline.plan(extraction, opts["mode"])
            self.stdout.write(
                f"Dry run: would add {plan.create}, update {plan.update}, leave "
                f"{plan.unchanged} unchanged, hide {plan.retire}."
            )
            return

        batch = ImportBatch(
            original_name=opts["file"].rsplit("/", 1)[-1][:255],
            mode=opts["mode"],
            sheet_name=layout.sheet,
            header_row=layout.header_row,
            data_start_row=layout.data_start_row,
            columns=[c.as_dict() for c in layout.columns],
            column_map=mapping,
        )
        with open(opts["file"], "rb") as handle:
            from django.core.files import File

            batch.file.save(batch.original_name, File(handle), save=False)
        batch.save()
        stats = pipeline.commit(batch, extraction, opts["mode"])
        batch.stats = {**stats, "column_labels": mapping_by_label(mapping, layout.columns)}
        batch.save(update_fields=["stats"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported: {stats['created']} added, {stats['updated']} updated, "
                f"{stats['unchanged']} unchanged, {stats['retired']} hidden. "
                f"{stats['pending_geocode']} lines need geocoding (run manage.py geocode)."
            )
        )
