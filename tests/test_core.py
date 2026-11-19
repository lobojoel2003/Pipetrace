import json
import re

import pytest
from django.core.management import call_command

from pipetrace import __version__
from pipetrace.buildinfo import BuildInfo, get_build_info
from pipetrace.core.middleware import build_csp
from pipetrace.core.models import SiteConfig


def test_build_info_from_environment(monkeypatch):
    get_build_info.cache_clear()
    monkeypatch.setenv("PIPETRACE_BUILD_NUMBER", "42")
    monkeypatch.setenv("PIPETRACE_GIT_SHA", "3f9a2b1c0d")
    info = get_build_info()
    assert info.version == __version__
    assert info.full_version == f"{__version__}+build.42.3f9a2b1"
    assert info.label == f"v{__version__} (build 42)"
    get_build_info.cache_clear()


def test_build_info_without_metadata():
    info = BuildInfo(version="1.2.3", build_number="", commit="", build_date="")
    assert info.full_version == "1.2.3"
    assert info.label == "v1.2.3"


def test_csp_allows_basemap_origin():
    csp = build_csp(["https://tiles.example.org/area.pmtiles", "/basemap/local.pmtiles"])
    assert "connect-src 'self' https://tiles.example.org" in csp
    assert "frame-ancestors 'none'" in csp


@pytest.mark.django_db
def test_site_config_is_a_cached_singleton():
    first = SiteConfig.load()
    first.utility_name = "Changed"
    first.utility_name_es = "Cambiado"
    first.save()
    assert SiteConfig.objects.count() == 1
    assert SiteConfig.load().utility_name == "Changed"
    from django.utils import translation

    with translation.override("es"):
        assert SiteConfig.load().display_name == "Cambiado"
    assert SiteConfig.load().display_name == "Changed"


@pytest.mark.django_db
def test_basemap_command(lines, capsys):
    call_command("basemap")
    out = capsys.readouterr().out
    assert "pmtiles extract" in out
    assert "--bbox=" in out


def test_version_matches_changelog():
    from pathlib import Path

    changelog = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text()
    assert f"## [{__version__}]" in changelog


def test_package_json_free():
    # The front end needs no build step: every module the pages load is committed.
    from pathlib import Path

    static = Path(__file__).resolve().parents[1] / "pipetrace" / "static" / "pipetrace"
    for name in [
        "app.js",
        "search.js",
        "map.js",
        "forms.js",
        "pipecheck.js",
        "shapes.js",
        "staff.js",
    ]:
        assert (static / "js" / name).exists()
    assert json.loads((static / "demo" / "millbrook-basemap.geojson").read_text())["features"]


@pytest.mark.django_db
def test_pages_render_with_production_static_storage(settings, tmp_path, lines, client):
    """Hashed static files (as in the Docker image) must resolve on every page type."""
    settings.STATIC_ROOT = tmp_path / "static"
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    call_command("collectstatic", interactive=False, verbosity=0)
    for path in [
        "/en/",
        "/es/",
        lines["lead"].get_absolute_url(),
        "/en/check-your-pipe/",
        "/en/check-your-pipe/send-photo/",
        "/en/about/",
        "/en/streets/",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
    body = client.get("/en/").content.decode()
    assert '"assets": "/static/pipetrace/vendor/basemaps-assets"' in body
    assert re.search(r"/static/pipetrace/css/app\.[0-9a-f]{12}\.css", body)
