import pytest
import requests

from pipetrace.inventory import geocoding
from pipetrace.inventory.choices import GeocodeStatus
from pipetrace.inventory.geocoding import Address, CensusGeocoder, PeliasGeocoder

from .conftest import make_line

CENSUS_CSV = (
    '"1","12 MAPLE ST, TESTVILLE, IL, 60000","Match","Exact","12 MAPLE ST, TESTVILLE, IL, '
    '60000","-89.012345,40.012345","123456","L"\n'
    '"2","14 MAPLE ST, TESTVILLE, IL, 60000","Match","Non_Exact","14 MAPLE ST, TESTVILLE, IL, '
    '60000","-89.1,40.1","123457","R"\n'
    '"3","99 NOWHERE RD, TESTVILLE, IL, 60000","No_Match"\n'
    '"4","1 TIE ST, TESTVILLE, IL, 60000","Tie"\n'
)


class FakeResponse:
    def __init__(self, text="", json_data=None, status=200):
        self.text = text
        self._json = json_data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.headers = {}
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


def test_census_parse_batch():
    results = CensusGeocoder.parse_batch(CENSUS_CSV)
    assert results["1"].status == GeocodeStatus.MATCHED
    assert (results["1"].lat, results["1"].lon) == (40.012345, -89.012345)
    assert results["2"].status == GeocodeStatus.APPROXIMATE
    assert results["3"].status == GeocodeStatus.NO_MATCH
    assert results["4"].status == GeocodeStatus.NO_MATCH


def test_census_sends_csv_batch(settings):
    session = FakeSession(FakeResponse(CENSUS_CSV))
    geocoder = CensusGeocoder(session=session)
    out = geocoder.geocode([Address("1", "12 Maple St", "Testville", "IL", "60000")])
    url, kwargs = session.calls[0]
    assert url.endswith("/locations/addressbatch")
    assert kwargs["data"]["benchmark"] == "Public_AR_Current"
    assert b"12 Maple St,Testville,IL,60000" in kwargs["files"]["addressFile"][1]
    assert out["1"].status == GeocodeStatus.MATCHED


def test_census_oneline():
    payload = {
        "result": {
            "addressMatches": [
                {"matchedAddress": "12 MAPLE ST", "coordinates": {"x": -89.0, "y": 40.0}}
            ]
        }
    }
    geocoder = CensusGeocoder(session=FakeSession(FakeResponse(json_data=payload)))
    result = geocoder.geocode_one("12 Maple St, Testville, IL")
    assert (result.lat, result.lon, result.status) == (40.0, -89.0, GeocodeStatus.MATCHED)
    empty = CensusGeocoder(
        session=FakeSession(FakeResponse(json_data={"result": {"addressMatches": []}}))
    )
    assert empty.geocode_one("nowhere").status == GeocodeStatus.NO_MATCH


def test_census_errors_are_wrapped():
    geocoder = CensusGeocoder(session=FakeSession(error=requests.ConnectionError("down")))
    with pytest.raises(geocoding.GeocoderError, match="Census"):
        geocoder.geocode([Address("1", "12 Maple St")])


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        (
            {
                "features": [
                    {
                        "geometry": {"coordinates": [-89, 40]},
                        "properties": {
                            "layer": "address",
                            "confidence": 0.95,
                            "match_type": "exact",
                            "label": "12 Maple St",
                        },
                    }
                ]
            },
            GeocodeStatus.MATCHED,
        ),
        (
            {
                "features": [
                    {
                        "geometry": {"coordinates": [-89, 40]},
                        "properties": {"layer": "street", "confidence": 0.7},
                    }
                ]
            },
            GeocodeStatus.APPROXIMATE,
        ),
        (
            {
                "features": [
                    {
                        "geometry": {"coordinates": [-89, 40]},
                        "properties": {"layer": "locality", "confidence": 0.9},
                    }
                ]
            },
            GeocodeStatus.NO_MATCH,
        ),
        ({"features": []}, GeocodeStatus.NO_MATCH),
    ],
)
def test_pelias_parse(payload, status):
    assert PeliasGeocoder.parse_feature(payload).status == status


def test_pelias_structured_request():
    payload = {
        "features": [
            {
                "geometry": {"coordinates": [-89, 40]},
                "properties": {"layer": "address", "confidence": 1, "label": "x"},
            }
        ]
    }
    session = FakeSession(FakeResponse(json_data=payload))
    geocoder = PeliasGeocoder(base_url="http://pelias:4000", api_key="k", session=session)
    out = geocoder.geocode([Address("7", "12 Maple St", "Testville", "IL", "60000")])
    url, kwargs = session.calls[0]
    assert url == "http://pelias:4000/v1/search/structured"
    assert kwargs["params"]["locality"] == "Testville"
    assert kwargs["params"]["api_key"] == "k"
    assert out["7"].status == GeocodeStatus.MATCHED


class StubGeocoder(geocoding.Geocoder):
    name = "stub"

    def __init__(self, fail=False):
        self.fail = fail
        self.seen = []

    def geocode(self, addresses):
        if self.fail:
            raise geocoding.GeocoderError("offline")
        self.seen.extend(addresses)
        return {
            a.id: geocoding.Result(GeocodeStatus.MATCHED, lat=40.5, lon=-89.5, matched="M")
            for a in addresses
            if "Nowhere" not in a.street
        }


@pytest.mark.django_db
def test_geocode_batch_updates_lines(site):
    found = make_line(address="12 Maple St", location=None, geocode_status="pending", city="")
    missing = make_line(address="1 Nowhere Rd", location=None, geocode_status="pending")
    make_line(address="5 Oak Ave")  # already located: untouched
    stub = StubGeocoder()
    progress = geocoding.geocode_batch(stub, batch_size=10)
    assert (progress.processed, progress.matched, progress.failed, progress.remaining) == (
        2,
        1,
        1,
        0,
    )
    assert stub.seen[0].city == "Testville"  # default city filled in
    found.refresh_from_db()
    missing.refresh_from_db()
    assert found.location.y == 40.5
    assert found.geocode_status == GeocodeStatus.MATCHED
    assert missing.geocode_status == GeocodeStatus.NO_MATCH
    assert geocoding.reset_failed() == 1


@pytest.mark.django_db
def test_geocode_batch_reports_errors(site):
    make_line(location=None, geocode_status="pending")
    progress = geocoding.geocode_batch(StubGeocoder(fail=True))
    assert progress.error == "offline"
    assert progress.remaining == 1
    off = geocoding.geocode_batch(None)  # PIPETRACE_GEOCODER=none in tests
    assert "turned off" in off.error


def test_get_geocoder(settings):
    assert isinstance(geocoding.get_geocoder("census"), CensusGeocoder)
    assert isinstance(geocoding.get_geocoder("pelias"), PeliasGeocoder)
    assert geocoding.get_geocoder("none") is None
