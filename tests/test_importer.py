import datetime as dt
import io

import pytest

from pipetrace.inventory.choices import (
    Connector,
    GeocodeStatus,
    Material,
    Replacement,
    Status,
    YesNoUnknown,
)
from pipetrace.inventory.importer import pipeline
from pipetrace.inventory.importer import values as V
from pipetrace.inventory.importer.detect import (
    build_columns,
    detect_header_row,
    header_signature,
    mapping_by_label,
    mapping_from_labels,
    suggest_mapping,
)
from pipetrace.inventory.importer.readers import (
    UnsupportedFile,
    cell_text,
    read_text,
    read_workbook,
)
from pipetrace.inventory.models import ImportBatch, ServiceLine

from .conftest import xlsx_bytes

# --- Reading -------------------------------------------------------------------------------


def test_cell_text_cleans_excel_values():
    assert cell_text(60601.0) == "60601"
    assert cell_text(dt.datetime(2024, 5, 1)) == "2024-05-01"
    assert cell_text("  Maple  St \n") == "Maple St"
    assert cell_text(None) == ""
    assert cell_text(True) == "TRUE"


def test_read_csv_sniffs_delimiter_and_encoding():
    data = "Address;Material\n12 Peña St;Lead\n".encode("cp1252")
    book = read_text(data, "inv.csv")
    assert book.sheet().rows == [["Address", "Material"], ["12 Peña St", "Lead"]]


def test_read_workbook_picks_inventory_sheet(epa_rows):
    data = xlsx_bytes(epa_rows, sheet="Lines", extra_sheets={"Instructions": [["Read me"]]})
    book = read_workbook(data, "inventory.xlsx")
    assert book.sheet_names == ["Lines", "Instructions"]
    assert book.best_sheet().name == "Lines"


def test_old_xls_is_rejected_with_advice():
    with pytest.raises(UnsupportedFile, match=r"\.xlsx"):
        read_workbook(io.BytesIO(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 100), "old.xls")
    with pytest.raises(UnsupportedFile):
        read_workbook(io.BytesIO(b"%PDF-1.4"), "inventory.pdf")


# --- Detection -------------------------------------------------------------------------------


def test_detects_header_below_title_and_group_rows(epa_rows):
    rows = read_workbook(xlsx_bytes(epa_rows), "x.xlsx").sheet().rows
    assert detect_header_row(rows) == 3
    columns = build_columns(rows, 3)
    labels = {c.index: c.label for c in columns}
    assert labels[5] == "System-Owned Portion › Material"
    assert labels[7] == "Customer-Owned Portion › Material"


def test_epa_layout_maps_every_column(epa_rows):
    book = read_workbook(xlsx_bytes(epa_rows), "x.xlsx")
    layout = pipeline.analyze(book)
    assert layout.header_row == 4
    assert layout.data_start_row == 6  # the codes row is skipped
    mapping = pipeline.auto_mapping(layout)
    assert mapping == {
        "source_id": 0,
        "address": 1,
        "city": 2,
        "state": 3,
        "zip_code": 4,
        "system_material": 5,
        "downstream_of_lead": 6,
        "customer_material": 7,
        "installed_year": 8,
        "status": 9,
        "connector": 10,
        "replacement": 11,
        "scheduled": 12,
    }


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        (
            ["Acct #", "Service Addr", "Town", "Utility Side", "Cust Side", "LSL?", "Y", "X"],
            {
                "source_id": 0,
                "address": 1,
                "city": 2,
                "system_material": 3,
                "customer_material": 4,
                "status": 5,
                "latitude": 6,
                "longitude": 7,
            },
        ),
        (
            ["House Number", "Street Name", "Public Side Material", "Private Side Material"],
            {"house_number": 0, "street_name": 1, "system_material": 2, "customer_material": 3},
        ),
        (["Mailing Address", "Service Address", "Owner City", "City"], {"address": 1, "city": 3}),
    ],
)
def test_messy_headers(headers, expected):
    data = ",".join(headers) + "\n" + ",".join(["sample"] * len(headers))
    book = read_text(data.encode(), "f.csv")
    layout = pipeline.analyze(book)
    assert pipeline.auto_mapping(layout) == expected


def test_mapping_round_trip_by_label(epa_rows):
    layout = pipeline.analyze(read_workbook(xlsx_bytes(epa_rows), "x.xlsx"))
    mapping = suggest_mapping(layout.columns)
    labels = mapping_by_label(mapping, layout.columns)
    assert mapping_from_labels(labels, layout.columns) == mapping
    assert len(header_signature(layout.columns)) == 64


def test_validate_mapping():
    assert pipeline.validate_mapping({"address": 0}) == []
    assert pipeline.validate_mapping({"house_number": 0, "street_name": 1}) == []
    assert pipeline.validate_mapping({}) != []
    assert pipeline.validate_mapping({"address": 0, "city": 0}) != []
    assert pipeline.validate_mapping({"address": 0, "latitude": 1}) != []


# --- Values ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "value", "ambiguous"),
    [
        ("Lead", Material.LEAD, False),
        ("LSL", Material.LEAD, False),
        ("Pb", Material.LEAD, True),
        ("Lead-lined galvanized", Material.LEAD, False),
        ("GALV", Material.GALVANIZED, False),
        ("Galvanized Requiring Replacement", Material.GALVANIZED, False),
        ("Cu", Material.COPPER, False),
        ("Non-Lead - Copper", Material.COPPER, False),
        ("PEX", Material.PLASTIC, False),
        ("HDPE", Material.PLASTIC, False),
        ("Ductile Iron", Material.IRON, False),
        ("Transite", Material.OTHER_NON_LEAD, False),
        ("NL", Material.NON_LEAD, False),
        ("Non-lead", Material.NON_LEAD, False),
        ("Unknown", Material.UNKNOWN, False),
        ("Lead Status Unknown", Material.UNKNOWN, False),
        ("Unknown - likely lead", Material.UNKNOWN, True),
        ("?", Material.UNKNOWN, False),
        ("Suspected lead", Material.UNKNOWN, True),
    ],
)
def test_interpret_material(raw, value, ambiguous):
    result = V.interpret_material(raw)
    assert result.value == value
    assert result.ambiguous == ambiguous


def test_interpret_material_blank_and_unrecognised():
    assert V.interpret_material("").value is None
    assert V.interpret_material("N/A").value is None
    assert not V.interpret_material("zzz").recognized


@pytest.mark.parametrize(
    ("raw", "value"),
    [
        ("L", Status.LEAD),
        ("GRR", Status.GRR),
        ("NL", Status.NON_LEAD),
        ("U", Status.UNKNOWN),
        ("Non-Lead", Status.NON_LEAD),
        ("Copper", Status.NON_LEAD),
        ("Galvanized Requiring Replacement", Status.GRR),
        ("Lead Status Unknown", Status.UNKNOWN),
        ("YES", Status.LEAD),
    ],
)
def test_interpret_status(raw, value):
    assert V.interpret_status(raw).value == value


def test_interpret_other_vocabularies():
    assert V.interpret_yes_no("Y").value == YesNoUnknown.YES
    assert V.interpret_yes_no("never").value == YesNoUnknown.NO
    assert V.interpret_yes_no("unk").value == YesNoUnknown.UNKNOWN
    assert V.interpret_connector("Lead gooseneck").value == Connector.LEAD
    assert V.interpret_connector("No connector present").value == Connector.NONE
    assert V.interpret_connector("Copper").value == Connector.NON_LEAD
    assert V.interpret_replacement("Completed 2025").value == Replacement.REPLACED
    assert V.interpret_replacement("Not scheduled").value == Replacement.NOT_SCHEDULED
    assert V.interpret_replacement("Planned").value == Replacement.SCHEDULED
    assert V.interpret_replacement("Under construction").value == Replacement.IN_PROGRESS


def test_parse_dates_years_and_schedules():
    assert V.parse_date("2024-05-01") == dt.date(2024, 5, 1)
    assert V.parse_date("5/1/24") == dt.date(2024, 5, 1)
    assert V.parse_date("May 1, 2024") == dt.date(2024, 5, 1)
    assert V.parse_date("45413") == dt.date(2024, 5, 1)
    assert V.parse_date("2/30/2024") is None
    assert V.parse_year("installed c. 1931") == 1931
    assert V.parse_schedule("2027-04-15") == (dt.date(2027, 4, 15), "")
    assert V.parse_schedule("Spring 2027") == (dt.date(2027, 4, 1), "Spring 2027")
    assert V.parse_schedule("Q3 2028") == (dt.date(2028, 7, 1), "Q3 2028")
    assert V.parse_schedule("Phase 2") == (None, "Phase 2")


def test_parse_zip_state_coordinates():
    assert V.parse_zip("2134") == "02134"
    assert V.parse_zip("606011234") == "60601-1234"
    assert V.parse_zip("60601-1234") == "60601-1234"
    assert V.parse_state("Illinois") == "IL"
    assert V.parse_state("il") == "IL"
    assert V.parse_float("89.5 W") == -89.5


# --- Extraction and commit ----------------------------------------------------------------------


def _extract(rows, value_map=None, defaults=None):
    book = read_workbook(xlsx_bytes(rows), "x.xlsx")
    layout = pipeline.analyze(book)
    mapping = pipeline.auto_mapping(layout)
    sheet_rows = book.sheet(layout.sheet).rows
    return layout, mapping, pipeline.extract(sheet_rows, layout, mapping, value_map, defaults)


def test_extract_epa_rows(epa_rows):
    _layout, _mapping, extraction = _extract(epa_rows)
    assert len(extraction.records) == 4
    assert len(extraction.errors) == 1  # T-5 has no address
    first = extraction.records[0].data
    assert first["zip_code"] == "02134"
    assert first["system_material"] == Material.LEAD
    assert first["final_status"] == Status.LEAD
    assert first["scheduled_on"] == dt.date(2027, 4, 1)
    assert first["installed_year"] == 1931
    assert extraction.status_counts == {"lead": 1, "grr": 1, "unknown": 1, "non_lead": 1}


def test_value_report_flags_codes_for_review(epa_rows):
    epa_rows[6][5] = "PB"
    book = read_workbook(xlsx_bytes(epa_rows), "x.xlsx")
    layout = pipeline.analyze(book)
    mapping = pipeline.auto_mapping(layout)
    report = pipeline.value_report(book.sheet().rows, layout, mapping, {})
    flagged = [e.raw for e in report["system_material"] if e.needs_review]
    assert flagged == ["PB"]


def test_value_overrides_apply(epa_rows):
    epa_rows[6][5] = "PB"
    _layout, _mapping, extraction = _extract(
        epa_rows, value_map={"system_material": {"pb": Material.PLASTIC}}
    )
    assert extraction.records[1].data["system_material"] == Material.PLASTIC


def test_full_address_column_is_split():
    rows = [["Address", "Material"], ["12 Maple St, Testville, IL 60000", "Lead"]]
    _l, _m, extraction = _extract(rows)
    data = extraction.records[0].data
    assert (data["address"], data["city"], data["state"], data["zip_code"]) == (
        "12 Maple St",
        "Testville",
        "IL",
        "60000",
    )


def test_defaults_fill_missing_city(epa_rows):
    rows = [["Address", "Material"], ["12 Maple St", "Lead"]]
    _l, _m, extraction = _extract(rows, defaults={"city": "Elsewhere", "state": "WI"})
    assert extraction.records[0].data["city"] == "Elsewhere"


def test_duplicates_and_conflicts():
    rows = [
        ["ID", "Address", "Utility Side Material", "Customer Side Material", "Classification"],
        ["1", "12 Maple St", "Copper", "Copper", "Lead"],
        ["1", "12 Maple St", "Lead", "Copper", "Non-lead"],
    ]
    _l, _m, extraction = _extract(rows)
    assert len(extraction.records) == 1
    assert extraction.duplicate_rows == 1
    assert len(extraction.conflicts) == 2


def test_coordinates_validation():
    warnings = []
    assert pipeline._coordinates("40.1", "-89.2", warnings) == (40.1, -89.2)
    assert pipeline._coordinates("-89.2", "40.1", warnings) == (40.1, -89.2)  # swapped
    assert pipeline._coordinates("40.1", "89.2", warnings) == (40.1, -89.2)  # missing minus
    assert pipeline._coordinates("1145000", "1900000", warnings) is None
    assert warnings  # projected coordinates are reported


@pytest.mark.django_db
def test_commit_merge_then_replace(site, epa_rows):
    _layout, _mapping, extraction = _extract(epa_rows)
    batch = ImportBatch.objects.create(original_name="a.xlsx", file="imports/a.xlsx")
    stats = pipeline.commit(batch, extraction, "merge")
    assert stats["created"] == 4
    assert stats["pending_geocode"] == 4
    line = ServiceLine.objects.get(source_id="T-2")
    assert line.status == Status.GRR
    assert line.status_from_file
    assert line.geocode_status == GeocodeStatus.PENDING
    assert line.public_id.startswith("14-maple-st-")

    # Same file again: nothing changes.
    batch2 = ImportBatch.objects.create(original_name="b.xlsx", file="imports/b.xlsx")
    assert pipeline.plan(extraction, "merge").unchanged == 4
    assert pipeline.commit(batch2, extraction, "merge")["unchanged"] == 4

    # A smaller file in replace mode hides the missing line and updates another.
    rows = [*epa_rows[:6], [*epa_rows[6][:7], "Copper", *epa_rows[6][8:]]]
    rows[-1][9] = "NL"
    _l, _m, smaller = _extract(rows)
    plan = pipeline.plan(smaller, "replace")
    assert (plan.update, plan.unchanged, plan.retire) == (1, 1, 2)
    stats = pipeline.commit(batch2, smaller, "replace")
    assert stats["retired"] == 2
    assert ServiceLine.objects.public().count() == 2
    assert ServiceLine.objects.get(source_id="T-2").status == Status.NON_LEAD
    assert site.__class__.load().inventory_updated is not None


@pytest.mark.django_db
def test_replaced_lines_are_not_lead(site):
    rows = [
        ["ID", "Address", "Classification", "Date Replaced"],
        ["9", "1 Elm St", "Lead", "2025-06-01"],
    ]
    _l, _m, extraction = _extract(rows)
    batch = ImportBatch.objects.create(original_name="c.xlsx", file="imports/c.xlsx")
    pipeline.commit(batch, extraction, "merge")
    line = ServiceLine.objects.get(source_id="9")
    assert line.replacement == Replacement.REPLACED
    assert line.status == Status.NON_LEAD
    assert line.replaced_on == dt.date(2025, 6, 1)


@pytest.mark.django_db
def test_address_change_requeues_geocoding(site):
    rows = [["ID", "Address", "Lat", "Lon"], ["1", "1 Elm St", "40", "-89"]]
    _l, _m, extraction = _extract(rows)
    batch = ImportBatch.objects.create(original_name="d.xlsx", file="imports/d.xlsx")
    pipeline.commit(batch, extraction, "merge")
    assert ServiceLine.objects.get().geocode_status == GeocodeStatus.PROVIDED

    rows = [["ID", "Address"], ["1", "3 Elm St"]]
    _l, _m, extraction = _extract(rows)
    line = ServiceLine.objects.get()
    line.geocode_status = GeocodeStatus.MATCHED
    line.save()
    pipeline.commit(batch, extraction, "merge")
    line.refresh_from_db()
    assert line.geocode_status == GeocodeStatus.PENDING
    assert line.location is None


@pytest.mark.django_db
def test_import_command(site, tmp_path, epa_rows, capsys):
    from django.core.management import call_command

    path = tmp_path / "inventory.xlsx"
    path.write_bytes(xlsx_bytes(epa_rows).getvalue())
    call_command("import_inventory", str(path), "--dry-run")
    assert ServiceLine.objects.count() == 0
    call_command("import_inventory", str(path), "--save-mapping", str(tmp_path / "map.json"))
    assert ServiceLine.objects.count() == 4
    out = capsys.readouterr().out
    assert "4 added" in out
    assert (tmp_path / "map.json").exists()


@pytest.mark.django_db
def test_demo_files_import(site):
    from django.core.management import call_command

    call_command("load_demo", "--no-submissions")
    assert ServiceLine.objects.public().count() > 400
    assert ServiceLine.objects.filter(status=Status.LEAD).exists()
    assert not ServiceLine.objects.filter(geocode_status=GeocodeStatus.PENDING).exists()
