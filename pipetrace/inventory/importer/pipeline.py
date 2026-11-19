"""Read an inventory sheet with a column mapping, preview it, and save it.

The flow is the same for the staff wizard and ``manage.py import_inventory``:

1. :func:`analyze` finds the sheet, header row and columns and suggests a mapping.
2. :func:`value_report` lists the distinct values in material/status columns and how
   each will be read, so staff can correct odd codes.
3. :func:`extract` turns rows into clean records.
4. :func:`plan` compares the records with the database (what will be added,
   updated, retired) and :func:`commit` saves them.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from pipetrace.inventory import addresses
from pipetrace.inventory.choices import GeocodeStatus, Replacement, Status
from pipetrace.inventory.classification import check_classification
from pipetrace.inventory.importer import fields as F
from pipetrace.inventory.importer import values as V
from pipetrace.inventory.importer.detect import (
    Column,
    build_columns,
    detect_header_row,
    phrase,
    suggest_mapping,
)
from pipetrace.inventory.importer.readers import Workbook

MAX_MESSAGES = 300
MAX_EXTRA_COLUMNS = 40

# --------------------------------------------------------------------------------------
# 1. Layout
# --------------------------------------------------------------------------------------


@dataclass
class Layout:
    sheet: str
    sheet_names: list[str]
    header_row: int  # 1-based, as shown in Excel
    data_start_row: int  # 1-based
    columns: list[Column]
    total_rows: int

    def column(self, index: int) -> Column | None:
        for col in self.columns:
            if col.index == index:
                return col
        return None


def _skip_code_rows(rows: list[list[str]], start: int) -> int:
    """Skip instruction/example rows that some templates put right under the header."""
    idx = start
    while idx < len(rows) and idx < start + 3:
        row = rows[idx]
        first = next((c for c in row if c), "").lower()
        if not any(row):
            idx += 1
            continue
        if first.startswith(("example", "e.g", "sample", "instructions", "(select", "select ")):
            idx += 1
            continue
        filled = [c for c in row if c]
        codes = sum(
            1
            for c in filled
            if re.search(r"[,/;]\s*\w", c) and len(c) < 80 and ("(" in c or "/" in c or c.isupper())
        )
        if filled and codes / len(filled) > 0.6:
            idx += 1
            continue
        break
    return idx


def analyze(
    workbook: Workbook,
    sheet: str | None = None,
    header_row: int | None = None,
    data_start_row: int | None = None,
) -> Layout:
    target = workbook.sheet(sheet)
    rows = target.rows
    header_idx = (header_row - 1) if header_row else detect_header_row(rows)
    header_idx = max(0, min(header_idx, max(len(rows) - 1, 0)))
    start_idx = (data_start_row - 1) if data_start_row else _skip_code_rows(rows, header_idx + 1)
    start_idx = max(header_idx + 1, start_idx)
    columns = build_columns(rows, header_idx, start_idx)
    return Layout(
        sheet=target.name,
        sheet_names=workbook.sheet_names,
        header_row=header_idx + 1,
        data_start_row=start_idx + 1,
        columns=columns,
        total_rows=len(rows),
    )


def auto_mapping(layout: Layout) -> dict[str, int]:
    return suggest_mapping(layout.columns)


def validate_mapping(mapping: dict[str, int]) -> list[str]:
    problems = []
    if "address" not in mapping and not {"house_number", "street_name"} <= mapping.keys():
        problems.append(
            _(
                "Choose the column with the street address (or both the house number "
                "and street name columns)."
            )
        )
    used = Counter(mapping.values())
    duplicates = [k for k, v in mapping.items() if used[v] > 1]
    if duplicates:
        problems.append(_("Each column can only be used once."))
    if ("latitude" in mapping) != ("longitude" in mapping):
        problems.append(_("Map both latitude and longitude, or neither."))
    return problems


# --------------------------------------------------------------------------------------
# 2. Values
# --------------------------------------------------------------------------------------


@dataclass
class ValueRow:
    raw: str
    key: str
    count: int
    auto: str
    recognized: bool
    ambiguous: bool
    chosen: str

    @property
    def needs_review(self) -> bool:
        return not self.recognized or self.ambiguous


def _data_rows(rows: list[list[str]], layout: Layout):
    for number, row in enumerate(rows[layout.data_start_row - 1 :], start=layout.data_start_row):
        if any(row):
            yield number, row


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def value_report(
    rows: list[list[str]],
    layout: Layout,
    mapping: dict[str, int],
    value_map: dict[str, dict[str, str]],
    limit: int = 80,
) -> dict[str, list[ValueRow]]:
    report: dict[str, list[ValueRow]] = {}
    for key, index in mapping.items():
        spec = F.FIELDS_BY_KEY.get(key)
        if not spec or spec.kind not in F.ENUM_KINDS:
            continue
        counter: Counter[str] = Counter()
        for _number, row in _data_rows(rows, layout):
            value = _cell(row, index)
            if value:
                counter[value] += 1
        overrides = value_map.get(key, {})
        entries = []
        merged: dict[str, ValueRow] = {}
        for raw, count in counter.most_common():
            vkey = V.value_key(raw)
            if vkey in merged:
                merged[vkey].count += count
                continue
            interp = V.INTERPRETERS[spec.kind](raw)
            chosen = overrides.get(vkey, interp.value or "")
            entry = ValueRow(
                raw=raw,
                key=vkey,
                count=count,
                auto=interp.value or "",
                recognized=interp.recognized,
                ambiguous=interp.ambiguous,
                chosen=chosen,
            )
            merged[vkey] = entry
            entries.append(entry)
        entries.sort(key=lambda e: (not e.needs_review, -e.count))
        report[key] = entries[:limit]
    return report


# --------------------------------------------------------------------------------------
# 3. Records
# --------------------------------------------------------------------------------------


@dataclass
class Record:
    row: int
    data: dict
    key: str
    warnings: list[str] = field(default_factory=list)

    @property
    def street_line(self) -> str:
        unit = self.data.get("unit") or ""
        return f"{self.data['address']} {'#' + unit if unit else ''}".strip()


@dataclass
class Extraction:
    records: list[Record]
    mapped_fields: set[str]
    errors: list[dict]
    warnings: list[dict]
    skipped_rows: int = 0
    duplicate_rows: int = 0
    conflicts: list[dict] = field(default_factory=list)

    @property
    def status_counts(self) -> dict[str, int]:
        counts = Counter(r.data["final_status"] for r in self.records)
        return {s.value: counts.get(s.value, 0) for s in Status}


_FULL_ADDRESS_RE = re.compile(
    r"^(?P<street>[^,]+),\s*(?P<city>[^,]+?)\s*,?\s+(?P<state>[A-Za-z]{2})\.?"
    r"(?:\s+(?P<zip>\d{5}(?:-\d{4})?))?\s*$"
)


def split_full_address(text: str) -> tuple[str, str, str, str]:
    """ "214 Maple St, Millbrook, IL 62000" -> (street, city, state, zip)."""
    m = _FULL_ADDRESS_RE.match(text.strip())
    if not m:
        return text, "", "", ""
    return (
        m.group("street").strip(),
        m.group("city").strip(),
        m.group("state").upper(),
        (m.group("zip") or ""),
    )


def record_key(source_id: str, street_line: str, city: str) -> str:
    if source_id:
        return "id:" + source_id.strip().lower()
    return "addr:" + addresses.normalize(street_line) + "|" + addresses.normalize(city)


def _enum(kind: str, key: str, raw: str, value_map: dict, warnings: list[str]) -> str | None:
    if not raw:
        return None
    overrides = value_map.get(key, {})
    vkey = V.value_key(raw)
    if vkey in overrides:
        return overrides[vkey] or None
    interp = V.INTERPRETERS[kind](raw)
    if not interp.recognized:
        label = F.FIELDS_BY_KEY[key].label
        warnings.append(
            _('"%(value)s" in %(field)s was not recognised and was left blank.')
            % {"value": raw, "field": label}
        )
    return interp.value


def _coordinates(lat_raw: str, lon_raw: str, warnings: list[str]) -> tuple[float, float] | None:
    lat, lon = V.parse_float(lat_raw), V.parse_float(lon_raw)
    if lat is None or lon is None:
        return None
    if lat == 0 and lon == 0:
        return None
    if abs(lat) > 90 >= abs(lon) or (lat < -50 and 15 < lon < 72):
        lat, lon = lon, lat  # columns swapped (U.S. latitudes are 15-72 north)
    if abs(lat) > 90 or abs(lon) > 180:
        warnings.append(
            _(
                "Coordinates look projected (not latitude/longitude); the address "
                "will be geocoded instead."
            )
        )
        return None
    if lon > 0 and 15 < lat < 72:
        # U.S. longitudes are west (negative); a missing minus sign is a common slip.
        lon = -lon
    return lat, lon


def extract(
    rows: list[list[str]],
    layout: Layout,
    mapping: dict[str, int],
    value_map: dict[str, dict[str, str]] | None = None,
    defaults: dict[str, str] | None = None,
) -> Extraction:
    value_map = value_map or {}
    defaults = defaults or {}
    mapped = set(mapping)
    col = mapping.get
    records: dict[str, Record] = {}
    errors: list[dict] = []
    warnings: list[dict] = []
    conflicts: list[dict] = []
    skipped = duplicates = 0
    header_labels = {phrase(c.header) for c in layout.columns if c.header}
    mapped_indexes = set(mapping.values())
    extra_columns = [c for c in layout.columns if c.index not in mapped_indexes and c.header]

    for number, row in _data_rows(rows, layout):
        if not any(_cell(row, i) for i in mapped_indexes):
            skipped += 1
            continue
        row_warnings: list[str] = []
        address = _cell(row, col("address"))
        if not address:
            address = " ".join(
                p for p in (_cell(row, col("house_number")), _cell(row, col("street_name"))) if p
            )
        if phrase(address) in header_labels:
            skipped += 1  # a repeated header row
            continue
        if not address:
            errors.append({"row": number, "message": _("No street address; row skipped.")})
            continue

        city = _cell(row, col("city"))
        state = V.parse_state(_cell(row, col("state")))
        zip_code = V.parse_zip(_cell(row, col("zip_code")))
        if "," in address and not city:
            address, city_part, state_part, zip_part = split_full_address(address)
            city = city_part
            state = state or state_part
            zip_code = zip_code or zip_part
        city = city or defaults.get("city", "")
        state = state or defaults.get("state", "")
        zip_code = zip_code or defaults.get("zip", "")

        system = _enum(
            F.MATERIAL,
            "system_material",
            _cell(row, col("system_material")),
            value_map,
            row_warnings,
        )
        customer = _enum(
            F.MATERIAL,
            "customer_material",
            _cell(row, col("customer_material")),
            value_map,
            row_warnings,
        )
        downstream = _enum(
            F.YES_NO,
            "downstream_of_lead",
            _cell(row, col("downstream_of_lead")),
            value_map,
            row_warnings,
        )
        stated = _enum(F.STATUS, "status", _cell(row, col("status")), value_map, row_warnings)
        connector = _enum(
            F.CONNECTOR, "connector", _cell(row, col("connector")), value_map, row_warnings
        )
        replacement = _enum(
            F.REPLACEMENT, "replacement", _cell(row, col("replacement")), value_map, row_warnings
        )
        scheduled_on, scheduled_label = V.parse_schedule(_cell(row, col("scheduled")))
        replaced_on = V.parse_date(_cell(row, col("replaced_on")))
        if not replacement:
            if replaced_on:
                replacement = Replacement.REPLACED
            elif scheduled_on or scheduled_label:
                replacement = Replacement.SCHEDULED

        check = check_classification(stated, system, customer, downstream)
        final_status = Status.NON_LEAD if replacement == Replacement.REPLACED else check.final
        if check.conflict:
            conflicts.append(
                {
                    "row": number,
                    "address": address,
                    "stated": check.stated.label if check.stated else "",
                    "derived": check.derived.label,
                }
            )

        coords = None
        if "latitude" in mapped:
            coords = _coordinates(
                _cell(row, col("latitude")), _cell(row, col("longitude")), row_warnings
            )

        source_id = _cell(row, col("source_id"))[:100]
        data = {
            "source_id": source_id,
            "address": address[:255],
            "unit": _cell(row, col("unit"))[:50],
            "city": city[:100],
            "state": state[:2],
            "zip_code": zip_code[:10],
            "coords": coords,
            "system_material": system or "",
            "customer_material": customer or "",
            "downstream_of_lead": downstream or "",
            "stated_status": check.stated.value if check.stated else "",
            "final_status": final_status.value if hasattr(final_status, "value") else final_status,
            "connector": connector or "",
            "basis": _cell(row, col("basis"))[:300],
            "verified_on": V.parse_date(_cell(row, col("verified_on"))),
            "installed_year": V.parse_year(_cell(row, col("installed_year"))),
            "building_year": V.parse_year(_cell(row, col("building_year"))),
            "replacement": replacement or "",
            "scheduled_on": scheduled_on,
            "scheduled_label": scheduled_label,
            "replaced_on": replaced_on,
            "public_note": _cell(row, col("public_note")),
            "extra": {
                c.label[:80]: _cell(row, c.index)[:500]
                for c in extra_columns[:MAX_EXTRA_COLUMNS]
                if _cell(row, c.index)
            },
        }
        unit_suffix = f" #{data['unit']}" if data["unit"] else ""
        key = record_key(source_id, data["address"] + unit_suffix, data["city"])
        record = Record(row=number, data=data, key=key, warnings=row_warnings)
        if key in records:
            duplicates += 1
            warnings.append(
                {
                    "row": number,
                    "message": _("Same line as row %(row)s (%(address)s); the later row was used.")
                    % {"row": records[key].row, "address": address},
                }
            )
        records[key] = record
        for message in row_warnings:
            warnings.append({"row": number, "message": message})

    return Extraction(
        records=list(records.values()),
        mapped_fields=mapped,
        errors=errors[:MAX_MESSAGES],
        warnings=warnings[:MAX_MESSAGES],
        skipped_rows=skipped,
        duplicate_rows=duplicates,
        conflicts=conflicts[:MAX_MESSAGES],
    )


# --------------------------------------------------------------------------------------
# 4. Plan and commit
# --------------------------------------------------------------------------------------

#: Model fields filled from each importer field (only touched when the field is mapped).
FIELD_TARGETS = {
    "source_id": ["source_id"],
    "address": ["address"],
    "house_number": ["address"],
    "street_name": ["address"],
    "unit": ["unit"],
    "city": ["city"],
    "state": ["state"],
    "zip_code": ["zip_code"],
    "system_material": ["system_material"],
    "customer_material": ["customer_material"],
    "downstream_of_lead": ["downstream_of_lead"],
    "connector": ["connector"],
    "basis": ["basis"],
    "verified_on": ["verified_on"],
    "installed_year": ["installed_year"],
    "building_year": ["building_year"],
    "replacement": ["replacement"],
    "scheduled": ["scheduled_on", "scheduled_label"],
    "replaced_on": ["replaced_on"],
    "public_note": ["public_note"],
}

COMPARE_FIELDS = [
    "source_id",
    "address",
    "unit",
    "city",
    "state",
    "zip_code",
    "status",
    "status_from_file",
    "system_material",
    "customer_material",
    "downstream_of_lead",
    "connector",
    "basis",
    "verified_on",
    "installed_year",
    "building_year",
    "replacement",
    "scheduled_on",
    "scheduled_label",
    "replaced_on",
    "public_note",
    "extra",
    "active",
]

SAVE_FIELDS = [
    *COMPARE_FIELDS,
    "normalized",
    "house_number",
    "house_number_int",
    "street_key",
    "street_display",
    "location",
    "geocode_status",
    "geocode_score",
    "geocode_match",
    "geocoded_at",
    "import_batch",
    "updated_at",
]


@dataclass
class Plan:
    create: int = 0
    update: int = 0
    unchanged: int = 0
    retire: int = 0
    pending_geocode: int = 0


def _existing_index():
    from pipetrace.inventory.models import ServiceLine

    by_id: dict[str, ServiceLine] = {}
    by_addr: dict[str, ServiceLine] = {}
    for line in ServiceLine.objects.all().iterator(chunk_size=2000):
        if line.source_id:
            by_id[record_key(line.source_id, "", "")] = line
        by_addr[record_key("", line.street_line, line.city)] = line
    return by_id, by_addr


def _match(record: Record, by_id: dict, by_addr: dict):
    if record.key in by_id:
        return by_id[record.key]
    addr_key = record_key("", record.street_line, record.data["city"])
    line = by_addr.get(addr_key)
    if line is not None and (not line.source_id or not record.data["source_id"]):
        return line
    return None


def _snapshot(line) -> tuple:
    coords = line.location.coords if line.location else None
    return (*(getattr(line, f) for f in COMPARE_FIELDS), coords)


def _apply(line, record: Record, mapped: set[str], batch, now) -> None:
    data = record.data
    old_location_key = (line.normalized, line.city, line.zip_code) if line.pk else None
    targets: set[str] = set()
    for importer_field in mapped:
        targets.update(FIELD_TARGETS.get(importer_field, []))
    for target in targets:
        value = data.get(target)
        if target in {
            "installed_year",
            "building_year",
            "verified_on",
            "scheduled_on",
            "replaced_on",
        }:
            setattr(line, target, value)
        else:
            setattr(line, target, value or "")
    if not line.pk:
        # New lines get every field so model defaults don't hide blanks.
        for target in ("system_material", "customer_material"):
            if not getattr(line, target):
                setattr(line, target, "unknown")
    if "replacement" not in mapped and data["replacement"]:
        line.replacement = data["replacement"]
    if not line.system_material:
        line.system_material = "unknown"
    if not line.customer_material:
        line.customer_material = "unknown"
    if not line.replacement:
        line.replacement = Replacement.NOT_SCHEDULED
    if "status" in mapped:
        line.status_from_file = bool(data["stated_status"])
        if data["stated_status"]:
            line.status = data["stated_status"]
    line.extra = data["extra"]
    line.active = True
    line.import_batch = batch
    line.refresh_derived()

    coords = data.get("coords")
    if coords:
        point = Point(coords[1], coords[0], srid=4326)
        if (
            not line.location
            or line.location.coords != point.coords
            or (line.geocode_status != GeocodeStatus.PROVIDED)
        ):
            line.location = point
            line.geocode_status = GeocodeStatus.PROVIDED
            line.geocode_score = None
            line.geocode_match = ""
            line.geocoded_at = now
    elif not line.pk:
        line.location = None
        line.geocode_status = GeocodeStatus.PENDING
    elif old_location_key != (line.normalized, line.city, line.zip_code) and (
        line.geocode_status not in {GeocodeStatus.MANUAL, GeocodeStatus.PROVIDED}
    ):
        line.location = None
        line.geocode_status = GeocodeStatus.PENDING
        line.geocode_match = ""


def plan(extraction: Extraction, mode: str) -> Plan:
    by_id, by_addr = _existing_index()
    result = Plan()
    seen: set[int] = set()
    now = timezone.now()
    for record in extraction.records:
        line = _match(record, by_id, by_addr)
        if line is None:
            result.create += 1
            if not record.data.get("coords"):
                result.pending_geocode += 1
            continue
        seen.add(line.pk)
        before = _snapshot(line)
        clone = _copy(line)
        _apply(clone, record, extraction.mapped_fields, line.import_batch, now)
        if _snapshot(clone) == before:
            result.unchanged += 1
        else:
            result.update += 1
        if clone.geocode_status == GeocodeStatus.PENDING:
            result.pending_geocode += 1
    if mode == "replace":
        result.retire = sum(
            1
            for line in {*by_id.values(), *by_addr.values()}
            if line.active and line.pk not in seen
        )
    return result


def _copy(line):
    clone = type(line)()
    for f in line._meta.concrete_fields:
        setattr(clone, f.attname, getattr(line, f.attname))
    clone._state.adding = False
    clone._state.db = line._state.db
    if line.location:
        clone.location = line.location.clone()
    if isinstance(line.extra, dict):
        clone.extra = dict(line.extra)
    return clone


def _unique_public_id(line, taken: set[str]) -> None:
    base = line.public_id
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    line.public_id = candidate
    taken.add(candidate)


@transaction.atomic
def commit(batch, extraction: Extraction, mode: str) -> dict:
    """Save ``extraction`` to the database and return statistics."""
    from pipetrace.core.models import SiteConfig
    from pipetrace.inventory.models import ServiceLine

    by_id, by_addr = _existing_index()
    taken = set(ServiceLine.objects.values_list("public_id", flat=True))
    now = timezone.now()
    to_create, to_update = [], []
    seen: set[int] = set()
    unchanged = 0
    for record in extraction.records:
        line = _match(record, by_id, by_addr)
        if line is None:
            line = ServiceLine()
            _apply(line, record, extraction.mapped_fields, batch, now)
            _unique_public_id(line, taken)
            line.created_at = now
            line.updated_at = now
            to_create.append(line)
            continue
        if line.pk in seen:
            continue
        seen.add(line.pk)
        before = _snapshot(line)
        _apply(line, record, extraction.mapped_fields, batch, now)
        if _snapshot(line) == before:
            unchanged += 1
            continue
        line.updated_at = now
        to_update.append(line)

    ServiceLine.objects.bulk_create(to_create, batch_size=1000)
    ServiceLine.objects.bulk_update(to_update, SAVE_FIELDS, batch_size=1000)
    # Lines that did not change still belong to this import.
    if seen:
        ServiceLine.objects.filter(pk__in=seen).update(import_batch=batch)

    retired = 0
    if mode == "replace":
        retired = (
            ServiceLine.objects.filter(active=True)
            .exclude(pk__in=seen)
            .exclude(pk__in=[line.pk for line in to_create])
            .update(active=False, updated_at=now)
        )

    config = SiteConfig.load()
    config.inventory_updated = timezone.localdate()
    config.save()

    stats = {
        "rows": len(extraction.records)
        + extraction.skipped_rows
        + len(extraction.errors)
        + extraction.duplicate_rows,
        "created": len(to_create),
        "updated": len(to_update),
        "unchanged": unchanged,
        "retired": retired,
        "errors": len(extraction.errors),
        "warnings": len(extraction.warnings),
        "conflicts": len(extraction.conflicts),
        "status_counts": extraction.status_counts,
        "pending_geocode": ServiceLine.objects.public()
        .filter(geocode_status=GeocodeStatus.PENDING)
        .count(),
    }
    batch.stats = stats
    batch.messages = (
        [{"level": "error", **e} for e in extraction.errors]
        + [{"level": "warning", **w} for w in extraction.warnings]
    )[:MAX_MESSAGES]
    batch.state = batch.State.COMMITTED
    batch.committed_at = now
    batch.save()
    return stats


def defaults_from_config() -> dict[str, str]:
    from pipetrace.core.models import SiteConfig

    config = SiteConfig.load()
    return {
        "city": config.default_city,
        "state": config.default_state.upper(),
        "zip": config.default_zip,
    }
