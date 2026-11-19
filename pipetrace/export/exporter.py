"""Write the whole resident site as plain files.

A small utility can upload the result to any free static host (GitHub Pages,
Netlify, Cloudflare Pages, an S3 bucket, the city's existing web server). Pages
are rendered by the same views as the live site, with ``request.static_export``
set so templates switch search to the browser and point forms at
``SiteConfig.static_form_endpoint`` (or an email link when there is none).
"""

from __future__ import annotations

import json
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.staticfiles import finders
from django.test import RequestFactory, override_settings
from django.urls import get_script_prefix, resolve, reverse, set_script_prefix
from django.utils import timezone, translation

from pipetrace.buildinfo import get_build_info
from pipetrace.core.models import SiteConfig
from pipetrace.inventory import stats
from pipetrace.inventory.models import ServiceLine
from pipetrace.residents import api as api_views
from pipetrace.residents import views

STATIC_SKIP_PREFIXES = ("admin/",)


@dataclass
class ExportResult:
    path: Path
    pages: int = 0
    files: int = 0
    zip_path: Path | None = None
    languages: list[str] = field(default_factory=list)


def normalize_base(base_url: str) -> str:
    base = (base_url or "/").strip()
    if not base.startswith(("/", "http://", "https://")):
        base = "/" + base
    if not base.endswith("/"):
        base += "/"
    return base


class _Renderer:
    def __init__(self, out: Path, base: str):
        self.out = out
        self.base = base
        self.factory = RequestFactory()
        self.pages = 0
        self.files = 0

    def _target(self, url: str) -> Path:
        path = url[len(self.base) :] if url.startswith(self.base) else url.lstrip("/")
        path = path.split("?", 1)[0]
        if not path or path.endswith("/"):
            path += "index.html"
        return self.out / path

    def write(self, url: str, content: bytes | str) -> None:
        target = self._target(url)
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            content = content.encode("utf-8")
        target.write_bytes(content)
        self.files += 1

    def page(self, url_name: str, language: str, view: Callable, **kwargs) -> None:
        with translation.override(language):
            url = reverse(url_name, kwargs=kwargs or None)
            unprefixed = "/" + url[len(self.base) :]
            request = self.factory.get(unprefixed)
            request.path = url
            request.static_export = True
            request.LANGUAGE_CODE = language
            request.user = AnonymousUser()
            request.resolver_match = resolve(unprefixed)
            response = view(request, **kwargs)
            if response.status_code != 200:
                raise RuntimeError(f"{url} returned HTTP {response.status_code}")
            self.write(url, response.content)
            self.pages += 1

    def json(self, url_name: str, data: dict) -> None:
        url = reverse(url_name)
        self.write(url, json.dumps(data, separators=(",", ":"), ensure_ascii=False))


def _copy_static(out: Path) -> int:
    count = 0
    seen: set[str] = set()
    for finder in finders.get_finders():
        for path, storage in finder.list(["CVS", ".*", "*~", "*.map"]):
            if path in seen or path.startswith(STATIC_SKIP_PREFIXES):
                continue
            seen.add(path)
            target = out / "static" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            with storage.open(path) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            count += 1
    return count


def _copy_basemap(out: Path, site: SiteConfig, base: str) -> int:
    url = site.basemap_pmtiles_url
    if not url or not url.startswith("/basemap/"):
        return 0
    source = Path(settings.PIPETRACE_BASEMAP_DIR) / url[len("/basemap/") :]
    if not source.is_file():
        return 0
    target = out / "basemap" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return 1


ROOT_INDEX = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta http-equiv="refresh" content="0; url={base}en/">
<script>
(function () {{
  var lang = (navigator.languages && navigator.languages[0]) || navigator.language || "en";
  location.replace("{base}" + (lang.toLowerCase().indexOf("es") === 0 ? "es/" : "en/"));
}})();
</script>
</head><body>
<p><a href="{base}en/">English</a> · <a href="{base}es/" lang="es">Español</a></p>
</body></html>
"""


def export_site(
    out_dir: str | Path,
    base_url: str = "/",
    zip_path: str | Path | None = None,
    languages: list[str] | None = None,
    progress: Callable[[str], None] | None = None,
) -> ExportResult:
    out = Path(out_dir)
    base = normalize_base(base_url)
    path_base = "/" + base.split("://", 1)[1].split("/", 1)[1] if "://" in base else base
    languages = languages or [code for code, _name in settings.LANGUAGES]
    say = progress or (lambda _msg: None)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    site = SiteConfig.load()
    old_prefix = get_script_prefix()
    storages = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    result = ExportResult(path=out, languages=languages)
    with override_settings(STATIC_URL=base + "static/", STORAGES=storages):
        set_script_prefix(path_base)
        try:
            r = _Renderer(out, path_base)
            lines = list(ServiceLine.objects.public())
            street_rows = stats.streets()
            for language in languages:
                say(f"Rendering {language} pages…")
                r.page("residents:home", language, views.home)
                r.page("residents:search", language, views.search_view)
                r.page("residents:guide", language, views.guide)
                r.page("residents:send_photo", language, views.send_photo)
                r.page("residents:request_inspection", language, views.request_inspection)
                r.page("residents:filters", language, views.filters)
                r.page("residents:about", language, views.about)
                r.page("residents:streets", language, views.streets)
                for row in street_rows:
                    r.page("residents:street", language, views.street, slug=row["slug"])
                for line in lines:
                    r.page("residents:line", language, views.line_view, public_id=line.public_id)
            say("Writing data files…")
            r.json("api:lines", stats.lines_geojson())
            r.json("api:search_index", api_views.search_index())
            r.json("api:stats", {**stats.summary(), "build": get_build_info().as_dict()})
            with translation.override(languages[0]):
                from django.template.loader import render_to_string

                not_found = render_to_string(
                    "404.html",
                    {
                        "site": site,
                        "build": get_build_info(),
                        "static_mode": True,
                    },
                )
            r.write(path_base + "404.html", not_found)
            r.write(
                path_base + "index.html", ROOT_INDEX.format(base=path_base, title=site.utility_name)
            )
            r.write(path_base + "robots.txt", "User-agent: *\nAllow: /\n")
            r.write(path_base + ".nojekyll", "")
            r.write(
                path_base + "build.json",
                json.dumps(
                    {
                        **get_build_info().as_dict(),
                        "exported_at": timezone.now().isoformat(timespec="seconds"),
                        "lines": len(lines),
                        "languages": languages,
                        "base_url": base,
                    },
                    indent=2,
                ),
            )
            result.pages = r.pages
            result.files = r.files
        finally:
            set_script_prefix(old_prefix)
    say("Copying static files…")
    result.files += _copy_static(out)
    result.files += _copy_basemap(out, site, base)

    if zip_path:
        zip_path = Path(zip_path)
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(out.rglob("*")):
                if file.is_file():
                    archive.write(file, file.relative_to(out))
        result.zip_path = zip_path
    return result
