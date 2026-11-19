"""Place inventory lines on the map from their address.

Two free options:

* The **U.S. Census Bureau geocoder** (default). No key; its batch endpoint takes up
  to 10,000 addresses per request. https://geocoding.geo.census.gov/
* A **self-hosted Pelias** server, for systems that cannot send addresses to a
  third party or need better rural coverage. https://pelias.io/

Geocoding runs in small batches (``PIPETRACE_GEOCODE_BATCH_SIZE``) so each web
request stays short; the staff page drives the batches from the browser and
``manage.py geocode`` loops over them from the command line or cron.
"""

from __future__ import annotations

import csv
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests
from django.conf import settings
from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone

from pipetrace import __version__
from pipetrace.inventory.choices import GeocodeStatus

log = logging.getLogger(__name__)
USER_AGENT = f"Pipetrace/{__version__} (+https://github.com/lobojoel2003/Pipetrace)"


class GeocoderError(RuntimeError):
    """The geocoding service could not be reached or returned something unusable."""


@dataclass(frozen=True)
class Address:
    id: str
    street: str
    city: str = ""
    state: str = ""
    zip_code: str = ""

    @property
    def oneline(self) -> str:
        locality = " ".join(p for p in (self.state, self.zip_code) if p)
        return ", ".join(p for p in (self.street, self.city, locality) if p)


@dataclass(frozen=True)
class Result:
    status: str  # a GeocodeStatus value
    lat: float | None = None
    lon: float | None = None
    matched: str = ""
    score: float | None = None


NO_MATCH = Result(GeocodeStatus.NO_MATCH)


class Geocoder:
    name = "base"

    def geocode(self, addresses: list[Address]) -> dict[str, Result]:  # pragma: no cover
        raise NotImplementedError


class CensusGeocoder(Geocoder):
    """U.S. Census Bureau geocoder (batch endpoint)."""

    name = "census"

    def __init__(
        self,
        base_url: str | None = None,
        benchmark: str | None = None,
        timeout: int | None = None,
        session: requests.Session | None = None,
    ):
        cfg = settings.PIPETRACE
        self.base_url = (base_url or cfg["CENSUS_URL"]).rstrip("/")
        self.benchmark = benchmark or cfg["CENSUS_BENCHMARK"]
        self.timeout = timeout or cfg["GEOCODE_TIMEOUT"]
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)

    def geocode(self, addresses: list[Address]) -> dict[str, Result]:
        if not addresses:
            return {}
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        for a in addresses:
            writer.writerow([a.id, a.street, a.city, a.state, a.zip_code])
        try:
            response = self.session.post(
                f"{self.base_url}/locations/addressbatch",
                data={"benchmark": self.benchmark},
                files={"addressFile": ("addresses.csv", buffer.getvalue().encode(), "text/csv")},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GeocoderError(f"Could not reach the Census geocoder: {exc}") from exc
        return self.parse_batch(response.text)

    @staticmethod
    def parse_batch(text: str) -> dict[str, Result]:
        """Parse the Census batch CSV response.

        Columns: ID, input address, Match/No_Match/Tie, Exact/Non_Exact, matched
        address, "lon,lat", TIGER line ID, side.
        """
        results: dict[str, Result] = {}
        for row in csv.reader(io.StringIO(text)):
            if not row or not row[0].strip():
                continue
            line_id = row[0].strip()
            indicator = row[2].strip().lower() if len(row) > 2 else ""
            if indicator != "match" or len(row) < 6 or "," not in row[5]:
                results[line_id] = NO_MATCH
                continue
            try:
                lon_s, lat_s = row[5].split(",", 1)
                lon, lat = float(lon_s), float(lat_s)
            except ValueError:
                results[line_id] = NO_MATCH
                continue
            exact = row[3].strip().lower() == "exact"
            results[line_id] = Result(
                GeocodeStatus.MATCHED if exact else GeocodeStatus.APPROXIMATE,
                lat=lat,
                lon=lon,
                matched=row[4].strip()[:300],
                score=1.0 if exact else 0.8,
            )
        return results

    def geocode_one(self, oneline: str) -> Result:
        try:
            response = self.session.get(
                f"{self.base_url}/locations/onelineaddress",
                params={"address": oneline, "benchmark": self.benchmark, "format": "json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            matches = response.json()["result"]["addressMatches"]
        except (requests.RequestException, KeyError, ValueError) as exc:
            raise GeocoderError(f"Could not reach the Census geocoder: {exc}") from exc
        if not matches:
            return NO_MATCH
        best = matches[0]
        return Result(
            GeocodeStatus.MATCHED,
            lat=best["coordinates"]["y"],
            lon=best["coordinates"]["x"],
            matched=best.get("matchedAddress", ""),
            score=1.0,
        )


class PeliasGeocoder(Geocoder):
    """A self-hosted Pelias server (structured search, one request per address)."""

    name = "pelias"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
        session: requests.Session | None = None,
        workers: int = 4,
    ):
        cfg = settings.PIPETRACE
        self.base_url = (base_url or cfg["PELIAS_URL"]).rstrip("/")
        self.api_key = api_key if api_key is not None else cfg["PELIAS_API_KEY"]
        self.timeout = min(timeout or cfg["GEOCODE_TIMEOUT"], 30)
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.workers = workers

    def _one(self, address: Address) -> Result:
        params = {"address": address.street, "country": "USA", "size": 1}
        if address.city:
            params["locality"] = address.city
        if address.state:
            params["region"] = address.state
        if address.zip_code:
            params["postalcode"] = address.zip_code
        if self.api_key:
            params["api_key"] = self.api_key
        response = self.session.get(
            f"{self.base_url}/v1/search/structured", params=params, timeout=self.timeout
        )
        response.raise_for_status()
        return self.parse_feature(response.json())

    @staticmethod
    def parse_feature(payload: dict) -> Result:
        features = payload.get("features") or []
        if not features:
            return NO_MATCH
        feature = features[0]
        props = feature.get("properties", {})
        lon, lat = feature["geometry"]["coordinates"][:2]
        confidence = float(props.get("confidence") or 0)
        layer = props.get("layer", "")
        if layer not in {"address", "venue", "street"} or confidence < 0.5:
            return NO_MATCH
        exact = (
            layer in {"address", "venue"}
            and props.get("match_type") != "fallback"
            and (confidence >= 0.8)
        )
        return Result(
            GeocodeStatus.MATCHED if exact else GeocodeStatus.APPROXIMATE,
            lat=lat,
            lon=lon,
            matched=props.get("label", "")[:300],
            score=confidence,
        )

    def geocode(self, addresses: list[Address]) -> dict[str, Result]:
        def run(address: Address) -> tuple[str, Result]:
            return address.id, self._one(address)

        try:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                return dict(pool.map(run, addresses))
        except requests.RequestException as exc:
            raise GeocoderError(f"Could not reach the Pelias server: {exc}") from exc


def get_geocoder(name: str | None = None) -> Geocoder | None:
    name = (name or settings.PIPETRACE["GEOCODER"] or "none").lower()
    if name == "census":
        return CensusGeocoder()
    if name == "pelias":
        return PeliasGeocoder()
    return None


@dataclass
class Progress:
    processed: int = 0
    matched: int = 0
    approximate: int = 0
    failed: int = 0
    remaining: int = 0
    error: str = ""

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def pending_lines():
    from pipetrace.inventory.models import ServiceLine

    return ServiceLine.objects.public().filter(geocode_status=GeocodeStatus.PENDING)


def reset_failed() -> int:
    """Queue lines whose address was not found for another try."""
    from pipetrace.inventory.models import ServiceLine

    return (
        ServiceLine.objects.public()
        .filter(geocode_status=GeocodeStatus.NO_MATCH)
        .update(geocode_status=GeocodeStatus.PENDING)
    )


def geocode_batch(geocoder: Geocoder | None = None, batch_size: int | None = None) -> Progress:
    """Geocode one batch of lines that have no location yet."""
    from pipetrace.core.models import SiteConfig
    from pipetrace.inventory.models import ServiceLine

    geocoder = geocoder or get_geocoder()
    progress = Progress()
    if geocoder is None:
        progress.error = "Geocoding is turned off (PIPETRACE_GEOCODER=none)."
        progress.remaining = pending_lines().count()
        return progress
    size = batch_size or settings.PIPETRACE["GEOCODE_BATCH_SIZE"]
    lines = list(pending_lines().order_by("pk")[:size])
    config = SiteConfig.load()
    items = [
        Address(
            id=str(line.pk),
            street=line.street_line,
            city=line.city or config.default_city,
            state=line.state or config.default_state,
            zip_code=line.zip_code or config.default_zip,
        )
        for line in lines
    ]
    try:
        results = geocoder.geocode(items)
    except GeocoderError as exc:
        log.warning("Geocoding failed: %s", exc)
        progress.error = str(exc)
        progress.remaining = pending_lines().count()
        return progress

    now = timezone.now()
    for line in lines:
        result = results.get(str(line.pk), NO_MATCH)
        line.geocode_status = result.status
        line.geocode_score = result.score
        line.geocode_match = result.matched
        line.geocoded_at = now
        if result.lat is not None and result.lon is not None:
            line.location = Point(result.lon, result.lat, srid=4326)
        if result.status == GeocodeStatus.MATCHED:
            progress.matched += 1
        elif result.status == GeocodeStatus.APPROXIMATE:
            progress.approximate += 1
        else:
            progress.failed += 1
    if lines:
        with transaction.atomic():
            ServiceLine.objects.bulk_update(
                lines,
                ["geocode_status", "geocode_score", "geocode_match", "geocoded_at", "location"],
            )
    progress.processed = len(lines)
    progress.remaining = pending_lines().count()
    return progress
