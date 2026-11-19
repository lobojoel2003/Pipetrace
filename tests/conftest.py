from __future__ import annotations

import io

import pytest
from django.contrib.gis.geos import Point
from django.core.cache import cache
from openpyxl import Workbook

from pipetrace.core.models import SiteConfig
from pipetrace.inventory.models import ServiceLine


@pytest.fixture(autouse=True)
def _isolate(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.PIPETRACE_BASEMAP_DIR = tmp_path / "media" / "basemap"
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.PIPETRACE = {**settings.PIPETRACE, "GEOCODER": "none", "NOTIFY_EMAILS": []}
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def site(db):
    config = SiteConfig.load()
    config.utility_name = "Testville Water"
    config.phone = "(555) 010-0100"
    config.email = "water@testville.example"
    config.default_city = "Testville"
    config.default_state = "IL"
    config.save()
    return config


def make_line(**kwargs) -> ServiceLine:
    defaults = {
        "address": "100 Maple St",
        "city": "Testville",
        "state": "IL",
        "zip_code": "60000",
        "system_material": "copper",
        "customer_material": "copper",
        "location": Point(-89.0, 40.0, srid=4326),
        "geocode_status": "provided",
    }
    defaults.update(kwargs)
    return ServiceLine.objects.create(**defaults)


@pytest.fixture
def lines(site):
    return {
        "lead": make_line(
            address="12 Maple St",
            source_id="A-1",
            system_material="lead",
            customer_material="copper",
            replacement="scheduled",
            scheduled_label="Spring 2027",
        ),
        "grr": make_line(
            address="14 Maple St",
            source_id="A-2",
            system_material="unknown",
            customer_material="galvanized",
        ),
        "unknown": make_line(
            address="16 Maple Street",
            source_id="A-3",
            system_material="unknown",
            customer_material="unknown",
        ),
        "non_lead": make_line(address="210 Oak Ave", source_id="A-4"),
        "replaced": make_line(
            address="18 Maple St",
            source_id="A-5",
            system_material="lead",
            customer_material="lead",
            replacement="replaced",
        ),
    }


def xlsx_bytes(rows: list[list], sheet: str = "Inventory", extra_sheets: dict | None = None):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for row in rows:
        ws.append(row)
    for name, content in (extra_sheets or {}).items():
        other = wb.create_sheet(name)
        for row in content:
            other.append(row)
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out


@pytest.fixture
def epa_rows():
    """A small inventory laid out like the EPA template (title, groups, codes row)."""
    return [
        ["Service Line Inventory - Testville"],
        [],
        [
            "Location Identifier",
            None,
            None,
            None,
            None,
            "System-Owned Portion",
            None,
            "Customer-Owned Portion",
            None,
            "Entire Service Line",
            None,
            "Replacement",
            None,
        ],
        [
            "Service Line ID",
            "Street Address",
            "City",
            "State",
            "Zip Code",
            "Material",
            "Was Material Ever Previously Lead?",
            "Material",
            "Installation Date",
            "Entire Service Line Material Classification",
            "Lead Connector",
            "Replacement Status",
            "Scheduled Replacement",
        ],
        [
            None,
            None,
            None,
            None,
            None,
            "Lead / Copper / Unknown",
            "Yes / No / Unknown",
            "Lead / Galvanized / Copper",
            None,
            "L, GRR, NL, U",
            None,
            None,
            None,
        ],
        [
            "T-1",
            "12 Maple St",
            "Testville",
            "IL",
            2134,
            "Lead",
            "",
            "Copper",
            1931,
            "L",
            "Yes",
            "Scheduled",
            "Spring 2027",
        ],
        [
            "T-2",
            "14 Maple St",
            "Testville",
            "IL",
            2134,
            "Cu",
            "Yes",
            "GALV",
            1950,
            "GRR",
            "No",
            "Not scheduled",
            None,
        ],
        [
            "T-3",
            "16 Maple Street",
            "Testville",
            "IL",
            2134,
            "UNK",
            "",
            "Unknown",
            None,
            "U",
            "Unknown",
            None,
            None,
        ],
        [
            "T-4",
            "210 Oak Avenue",
            "Testville",
            "IL",
            2134,
            "Copper",
            "",
            "PEX",
            1998,
            "NL",
            "None",
            None,
            None,
        ],
        [None, None, None, None, None, None, None, None, None, None, None, None, None],
        ["T-5", None, "Testville", "IL", 2134, "Lead", "", "Lead", None, "L", "", None, None],
    ]
