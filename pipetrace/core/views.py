"""Small views that are not part of the resident site or staff tools."""

from __future__ import annotations

import mimetypes
import os
import re

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils._os import safe_join
from django.utils.translation import get_language_from_request

from pipetrace.buildinfo import get_build_info

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def root(request):
    """Send visitors to the site in their browser's language."""
    return redirect(f"/{get_language_from_request(request)}/")


def healthz(request):
    """Liveness/readiness probe: checks the database and reports the build."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database, status = "ok", 200
    except Exception as exc:
        database, status = f"error: {exc.__class__.__name__}", 503
    return JsonResponse(
        {
            "status": "ok" if status == 200 else "error",
            "database": database,
            **get_build_info().as_dict(),
        },
        status=status,
    )


def robots(request):
    lines = ["User-agent: *", "Disallow: /staff/", "Disallow: /admin/", "Disallow: /api/"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def not_found(request, exception=None):
    return render(request, "404.html", status=404)


def server_error(request):
    return render(request, "500.html", status=500)


def basemap(request, path: str):
    """Serve a local PMTiles basemap with HTTP Range support (PMTiles needs it)."""
    try:
        full = safe_join(settings.PIPETRACE_BASEMAP_DIR, path)
    except SuspiciousFileOperation as exc:
        raise Http404 from exc
    if not os.path.isfile(full):
        raise Http404
    size = os.path.getsize(full)
    content_type = mimetypes.guess_type(full)[0] or "application/octet-stream"
    match = _RANGE_RE.fullmatch(request.headers.get("Range", "").strip())
    if match and (match.group(1) or match.group(2)):
        start_s, end_s = match.groups()
        if start_s:
            start = int(start_s)
            end = min(int(end_s), size - 1) if end_s else size - 1
        else:
            start, end = max(size - int(end_s), 0), size - 1
        if start > end or start >= size:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        with open(full, "rb") as handle:
            handle.seek(start)
            data = handle.read(end - start + 1)
        response = HttpResponse(data, status=206, content_type=content_type)
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
    else:
        response = FileResponse(open(full, "rb"), content_type=content_type)  # noqa: SIM115
    response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = "public, max-age=86400"
    return response
