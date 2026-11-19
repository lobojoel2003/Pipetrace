import json
import zipfile

import pytest
from django.core.management import call_command

from pipetrace.export.exporter import export_site, normalize_base

pytestmark = pytest.mark.django_db


def test_normalize_base():
    assert normalize_base("") == "/"
    assert normalize_base("Pipetrace") == "/Pipetrace/"
    assert normalize_base("/a/b") == "/a/b/"
    assert normalize_base("https://x.example/site") == "https://x.example/site/"


def test_export_static_site(lines, tmp_path):
    out = tmp_path / "site"
    result = export_site(out, base_url="/Pipetrace/", zip_path=tmp_path / "site.zip")
    assert result.pages == 2 * (8 + 2 + 5)  # fixed pages, streets, lines per language
    for path in [
        "index.html",
        "404.html",
        ".nojekyll",
        "robots.txt",
        "build.json",
        "en/index.html",
        "es/index.html",
        "en/search/index.html",
        f"en/line/{lines['lead'].public_id}/index.html",
        f"es/line/{lines['lead'].public_id}/index.html",
        "en/streets/maple-st/index.html",
        "api/lines.geojson",
        "api/search-index.json",
        "api/stats.json",
        "static/pipetrace/js/app.js",
        "static/pipetrace/css/app.css",
        "static/pipetrace/vendor/maplibre-gl/maplibre-gl.mjs",
    ]:
        assert (out / path).exists(), path
    assert not (out / "static" / "admin").exists()
    home = (out / "en" / "index.html").read_text()
    assert 'href="/Pipetrace/static/pipetrace/css/app.css"' in home
    assert 'href="/Pipetrace/en/check-your-pipe/"' in home
    assert '"static": true' in home
    assert "Staff sign in" not in home
    assert "csrfmiddlewaretoken" not in (out / "en/request-inspection/index.html").read_text()
    spanish = (out / "es" / "index.html").read_text()
    assert 'lang="es"' in spanish
    assert 'href="/Pipetrace/en/"' in spanish  # language switch
    assert json.loads((out / "api" / "search-index.json").read_text())["lines"]
    assert json.loads((out / "build.json").read_text())["lines"] == 5
    with zipfile.ZipFile(tmp_path / "site.zip") as archive:
        assert "en/index.html" in archive.namelist()


def test_export_uses_form_endpoint(lines, tmp_path, site):
    site.static_form_endpoint = "https://pipetrace.example/api/submit/"
    site.save()
    export_site(tmp_path / "s", languages=["en"])
    page = (tmp_path / "s" / "en" / "request-inspection" / "index.html").read_text()
    assert 'action="https://pipetrace.example/api/submit/"' in page
    assert not (tmp_path / "s" / "es").exists()


def test_export_copies_local_basemap(lines, tmp_path, site, settings):
    settings.PIPETRACE_BASEMAP_DIR.mkdir(parents=True)
    (settings.PIPETRACE_BASEMAP_DIR / "area.pmtiles").write_bytes(b"PMTiles")
    site.basemap_pmtiles_url = "/basemap/area.pmtiles"
    site.save()
    export_site(tmp_path / "s", base_url="/sub/", languages=["en"])
    assert (tmp_path / "s" / "basemap" / "area.pmtiles").read_bytes() == b"PMTiles"
    home = (tmp_path / "s" / "en" / "index.html").read_text()
    assert '"pmtiles": "/sub/basemap/area.pmtiles"' in home


def test_export_command(lines, tmp_path, capsys):
    call_command("export_static", str(tmp_path / "out"), "--language", "en")
    assert "Wrote" in capsys.readouterr().out
    assert (tmp_path / "out" / "en" / "index.html").exists()


def test_staff_download(client, lines):
    from django.contrib.auth.models import User

    client.force_login(User.objects.create_user("s", password="pw-test-12345", is_staff=True))
    response = client.get("/staff/export/site.zip")
    assert response["Content-Type"] == "application/zip"
    assert b"".join(response.streaming_content)[:2] == b"PK"
