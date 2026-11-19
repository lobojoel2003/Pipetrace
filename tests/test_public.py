import io
import json

import pytest
from django.core import mail
from django.urls import reverse
from PIL import Image

from pipetrace.inventory.search import best_match, same_street, search
from pipetrace.residents.forms import started_token
from pipetrace.residents.models import InspectionRequest, PipeCheck, guess_material

pytestmark = pytest.mark.django_db


def test_root_redirects_by_language(client):
    assert client.get("/").url == "/en/"
    assert client.get("/", HTTP_ACCEPT_LANGUAGE="es-MX,es;q=0.9").url == "/es/"


def test_home_in_both_languages(client, lines):
    response = client.get("/en/")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Is the water pipe to your home made of lead?" in body
    assert 'hreflang="es"' in body
    assert "Content-Security-Policy" in response
    response = client.get("/es/")
    assert response.status_code == 200
    assert 'lang="es"' in response.content.decode()


def test_search_redirects_to_single_match(client, lines):
    response = client.get("/en/search/", {"q": "12 maple street, Testville IL"})
    assert response.status_code == 302
    assert response.url == lines["lead"].get_absolute_url()


def test_search_lists_several_matches(client, lines):
    response = client.get("/en/search/", {"q": "maple"})
    assert response.status_code == 200
    assert response.content.decode().count('class="addr"') == 4


def test_search_suggests_same_street(client, lines):
    response = client.get("/en/search/", {"q": "999 Maple St"})
    body = response.content.decode()
    assert "We couldn" in body
    assert "Addresses on that street" in body


def test_search_functions(lines):
    assert best_match("16 maple st") == lines["unknown"]
    assert best_match("maple") is None
    assert [m.line for m in search("210 oak")] == [lines["non_lead"]]
    assert len(same_street("99 Maple St")) == 4


@pytest.mark.parametrize(
    ("key", "text"),
    [
        ("lead", "Scheduled for replacement"),
        ("grr", "galvanized steel that needs to be replaced"),
        ("unknown", "Help us find out in about two minutes"),
        ("non_lead", "Lead can still come from inside a building"),
        ("replaced", "This lead service line was replaced on"),
    ],
)
def test_line_pages(client, lines, key, text):
    response = client.get(lines[key].get_absolute_url())
    assert response.status_code == 200
    assert text in response.content.decode()


def test_line_page_spanish_url(client, lines):
    url = reverse("residents:line", kwargs={"public_id": lines["lead"].public_id})
    assert url.startswith("/en/")
    assert client.get(url.replace("/en/", "/es/")).status_code == 200


def test_hidden_lines_are_not_public(client, lines):
    line = lines["lead"]
    line.active = False
    line.save()
    assert client.get(line.get_absolute_url()).status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/en/check-your-pipe/",
        "/es/check-your-pipe/",
        "/en/filters/",
        "/en/about/",
        "/en/streets/",
        "/en/streets/maple-st/",
        "/en/request-inspection/",
        "/en/check-your-pipe/send-photo/",
        "/robots.txt",
    ],
)
def test_static_pages(client, lines, path):
    assert client.get(path).status_code == 200


def test_unknown_street_404(client, lines):
    assert client.get("/en/streets/no-such-street/").status_code == 404


def test_api_search(client, lines):
    data = client.get("/api/search/", {"q": "14 map", "lang": "es"}).json()
    assert data["results"][0]["id"] == lines["grr"].public_id
    assert data["results"][0]["code"] == "G"
    assert data["results"][0]["label"] == "Galvanizada, hay que reemplazarla"
    assert client.get("/api/search/").json()["results"] == []
    # A house number that isn't in the inventory falls back to the rest of the street.
    fallback = client.get("/api/search/", {"q": "999 Maple St"}).json()["results"]
    assert {r["address"] for r in fallback} >= {"12 Maple St", "14 Maple St"}


def test_api_geojson_stats_index(client, lines):
    geo = client.get("/api/lines.geojson").json()
    assert len(geo["features"]) == 5
    props = {f["properties"]["i"]: f["properties"] for f in geo["features"]}
    assert props[lines["replaced"].public_id] == {
        "i": lines["replaced"].public_id,
        "a": "18 Maple St",
        "s": "N",
        "r": 1,
    }
    stats = client.get("/api/stats.json").json()
    assert stats["counts"] == {"lead": 1, "grr": 1, "unknown": 1, "non_lead": 2}
    assert stats["replaced"] == 1
    assert stats["remaining"] == 2
    assert stats["build"]["version"]
    index = client.get("/api/search-index.json").json()
    assert len(index["lines"]) == 5
    assert index["config"]["abbr"]["AVENUE"] == "AVE"


def test_healthz(client, db):
    data = client.get("/healthz").json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"


def _form(**extra):
    data = {
        "address": "12 Maple St",
        "name": "Ana",
        "phone": "555-0100",
        "email": "",
        "language": "es",
        "started": "",
        "website": "",
    }
    data.update(extra)
    return data


def _old_token(monkeypatch):
    import time

    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() - 60)
    token = started_token()
    monkeypatch.setattr(time, "time", real)
    return token


def test_inspection_request_flow(client, lines, monkeypatch, settings):
    settings.PIPETRACE = {**settings.PIPETRACE, "NOTIFY_EMAILS": ["staff@testville.example"]}
    data = _form(
        started=_old_token(monkeypatch),
        contact_by="text",
        relationship="renter",
        consent="on",
        email="ana@example.com",
    )
    response = client.post("/es/request-inspection/", data)
    assert response.status_code == 302, response.content.decode()[:500]
    item = InspectionRequest.objects.get()
    assert item.service_line == lines["lead"]
    assert item.reference.startswith("IR-")
    assert response.url == f"/es/thanks/{item.reference}/"
    assert client.get(response.url).status_code == 200
    assert {tuple(m.to) for m in mail.outbox} == {
        ("staff@testville.example",),
        ("ana@example.com",),
    }


def test_inspection_request_validation(client, lines, monkeypatch):
    token = _old_token(monkeypatch)
    # No phone or email.
    response = client.post("/en/request-inspection/", _form(started=token, phone="", consent="on"))
    assert "phone number or an email" in response.content.decode()
    # Honeypot filled.
    client.post("/en/request-inspection/", _form(started=token, consent="on", website="spam"))
    # Submitted instantly.
    client.post("/en/request-inspection/", _form(started=started_token(), consent="on"))
    assert InspectionRequest.objects.count() == 0


def _photo(fmt="JPEG"):
    image = Image.new("RGB", (3000, 2000), (120, 120, 120))
    out = io.BytesIO()
    exif = Image.Exif()
    exif[0x8825] = {2: (40, 0, 0)}  # GPS info
    image.save(out, fmt, exif=exif) if fmt == "JPEG" else image.save(out, fmt)
    out.seek(0)
    out.name = f"pipe.{fmt.lower()}"
    return out


def test_photo_upload_strips_metadata(client, lines, monkeypatch):
    data = _form(
        started=_old_token(monkeypatch), scratch="silver", magnet="no_stick", photo=_photo()
    )
    response = client.post(
        f"/en/check-your-pipe/send-photo/?line={lines['unknown'].public_id}", data
    )
    assert response.status_code == 302, response.content.decode()[:800]
    check = PipeCheck.objects.get()
    assert check.service_line == lines["unknown"]
    assert check.resident_result == "lead"
    with Image.open(check.photo.path) as stored:
        assert max(stored.size) == 2400
        assert not stored.getexif().get(0x8825)
    # Photos are not public media.
    assert client.get("/media/" + check.photo.name).status_code == 404


def test_photo_upload_rejects_non_images(client, lines, monkeypatch):
    bogus = io.BytesIO(b"not an image")
    bogus.name = "x.jpg"
    response = client.post(
        "/en/check-your-pipe/send-photo/", _form(started=_old_token(monkeypatch), photo=bogus)
    )
    assert response.status_code == 200
    assert PipeCheck.objects.count() == 0


@pytest.mark.parametrize(
    ("scratch", "magnet", "expected"),
    [
        ("silver", "no_stick", "lead"),
        ("gray", "sticks", "galvanized"),
        ("copper", "no_stick", "copper"),
        ("plastic", "not_tested", "plastic"),
        ("gray", "no_stick", "lead"),
        ("not_sure", "not_tested", "unknown"),
    ],
)
def test_guess_material(scratch, magnet, expected):
    assert guess_material(scratch, magnet) == expected


def test_submit_api_for_static_sites(client, lines):
    response = client.options("/api/submit/")
    assert response["Access-Control-Allow-Origin"] == "*"
    response = client.post(
        "/api/submit/",
        {
            "kind": "inspection",
            "address": "16 Maple St",
            "phone": "555",
            "consent": "on",
            "contact_by": "phone",
            "relationship": "owner",
            "language": "en",
            "line": lines["unknown"].public_id,
        },
    )
    assert response.status_code == 201, response.content
    item = InspectionRequest.objects.get(reference=response.json()["reference"])
    assert item.via_static_site
    assert item.service_line == lines["unknown"]
    bad = client.post("/api/submit/", {"kind": "inspection", "address": "x"})
    assert bad.status_code == 400
    assert "phone" in json.dumps(bad.json()) or "__all__" in bad.json()["errors"]
    assert client.post("/api/submit/", {"kind": "nope"}).status_code == 400
    assert client.get("/api/submit/").status_code == 405


def test_rate_limit(client, lines, settings):
    settings.PIPETRACE = {**settings.PIPETRACE, "SUBMISSIONS_PER_HOUR": 1}
    payload = {
        "kind": "inspection",
        "address": "16 Maple St",
        "phone": "555",
        "consent": "on",
        "contact_by": "phone",
        "relationship": "owner",
    }
    assert client.post("/api/submit/", payload).status_code == 201
    assert client.post("/api/submit/", payload).status_code == 429


def test_basemap_range_requests(client, settings):
    settings.PIPETRACE_BASEMAP_DIR.mkdir(parents=True)
    (settings.PIPETRACE_BASEMAP_DIR / "area.pmtiles").write_bytes(bytes(range(256)))
    full = client.get("/basemap/area.pmtiles")
    assert full.status_code == 200
    assert full["Accept-Ranges"] == "bytes"
    part = client.get("/basemap/area.pmtiles", HTTP_RANGE="bytes=10-19")
    assert part.status_code == 206
    assert part.content == bytes(range(10, 20))
    assert part["Content-Range"] == "bytes 10-19/256"
    assert client.get("/basemap/area.pmtiles", HTTP_RANGE="bytes=-6").content == bytes(
        range(250, 256)
    )
    assert client.get("/basemap/area.pmtiles", HTTP_RANGE="bytes=900-").status_code == 416
    assert client.get("/basemap/../settings.py").status_code == 404
    assert client.get("/basemap/missing.pmtiles").status_code == 404
