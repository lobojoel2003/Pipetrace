"""Summary numbers and map data for the public site."""

from __future__ import annotations

from django.core.cache import cache
from django.db.models import Count, Max, Q
from django.utils.text import slugify

from pipetrace.inventory.choices import (
    NEEDS_REPLACEMENT,
    STATUS_CODES,
    STATUS_ORDER,
    GeocodeStatus,
    Replacement,
    Status,
)
from pipetrace.inventory.models import ServiceLine


def _version() -> str:
    agg = ServiceLine.objects.aggregate(n=Count("pk"), last=Max("updated_at"))
    return f"{agg['n']}:{agg['last'].timestamp() if agg['last'] else 0}"


def summary() -> dict:
    key = f"pipetrace:summary:{_version()}"
    data = cache.get(key)
    if data is not None:
        return data
    qs = ServiceLine.objects.public()
    counts = dict(qs.values_list("status").annotate(n=Count("pk")).values_list("status", "n"))
    replaced = qs.filter(replacement=Replacement.REPLACED).count()
    remaining = (
        qs.filter(status__in=NEEDS_REPLACEMENT).exclude(replacement=Replacement.REPLACED).count()
    )
    scheduled = qs.filter(
        status__in=NEEDS_REPLACEMENT,
        replacement__in=[Replacement.SCHEDULED, Replacement.IN_PROGRESS],
    ).count()
    total = sum(counts.values())
    located = qs.filter(location__isnull=False).count()
    by_status = [
        {
            "status": s.value,
            "code": STATUS_CODES[s],
            "label": str(s.label),
            "count": counts.get(s.value, 0),
            "percent": round(100 * counts.get(s.value, 0) / total, 1) if total else 0,
        }
        for s in STATUS_ORDER
    ]
    goal = replaced + remaining
    data = {
        "total": total,
        "by_status": by_status,
        "counts": {s.value: counts.get(s.value, 0) for s in Status},
        "replaced": replaced,
        "remaining": remaining,
        "scheduled": scheduled,
        "replacement_goal": goal,
        "replacement_percent": round(100 * replaced / goal) if goal else 0,
        "located": located,
        "not_located": total - located,
    }
    cache.set(key, data, 600)
    return data


def lines_geojson() -> dict:
    """Every located public line as compact GeoJSON for the map.

    Properties: ``i`` public ID, ``a`` street address, ``s`` status code
    (L lead, G galvanized requiring replacement, U unknown, N not lead),
    ``r`` 1 when the line has been replaced.
    """
    key = f"pipetrace:geojson:{_version()}"
    data = cache.get(key)
    if data is not None:
        return data
    features = []
    qs = (
        ServiceLine.objects.public()
        .filter(location__isnull=False)
        .only("public_id", "address", "unit", "status", "location", "replacement")
    )
    for line in qs.iterator(chunk_size=2000):
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(line.location.x, 6), round(line.location.y, 6)],
                },
                "properties": {
                    "i": line.public_id,
                    "a": line.street_line,
                    "s": STATUS_CODES[Status(line.status)],
                    **({"r": 1} if line.replacement == Replacement.REPLACED else {}),
                },
            }
        )
    data = {"type": "FeatureCollection", "features": features}
    cache.set(key, data, 600)
    return data


def map_view() -> dict | None:
    """Center and bounds for the map, or None when no line has a location."""
    from django.contrib.gis.db.models import Extent

    qs = ServiceLine.objects.public().filter(location__isnull=False)
    extent = qs.aggregate(e=Extent("location"))["e"]
    if not extent:
        return None
    west, south, east, north = extent
    return {
        "bounds": [[west, south], [east, north]],
        "center": [(west + east) / 2, (south + north) / 2],
    }


def geocode_counts() -> dict[str, int]:
    qs = ServiceLine.objects.public()
    counts = dict(
        qs.values_list("geocode_status").annotate(n=Count("pk")).values_list("geocode_status", "n")
    )
    return {s.value: counts.get(s.value, 0) for s in GeocodeStatus}


def streets() -> list[dict]:
    """Streets with their number of lines and how many need replacement."""
    rows = (
        ServiceLine.objects.public()
        .exclude(street_key="")
        .values("street_key")
        .annotate(
            n=Count("pk"),
            display=Max("street_display"),
            lead=Count(
                "pk", filter=Q(status__in=NEEDS_REPLACEMENT) & ~Q(replacement=Replacement.REPLACED)
            ),
            unknown=Count("pk", filter=Q(status=Status.UNKNOWN)),
        )
        .order_by("display")
    )
    return [{**row, "slug": slugify(row["street_key"])} for row in rows]
