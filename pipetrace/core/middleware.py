"""Security headers that Django does not set on its own."""

from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings


def _origin(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


def build_csp(extra_connect: list[str] | None = None) -> str:
    connect = ["'self'", *settings.PIPETRACE.get("CSP_CONNECT_SRC", [])]
    for url in extra_connect or []:
        origin = _origin(url)
        if origin and origin not in connect:
            connect.append(origin)
    directives = {
        "default-src": ["'self'"],
        "script-src": ["'self'"],
        # MapLibre positions popups and controls with inline styles.
        "style-src": ["'self'", "'unsafe-inline'"],
        "img-src": ["'self'", "data:", "blob:"],
        "font-src": ["'self'"],
        "connect-src": connect,
        "worker-src": ["'self'", "blob:"],
        "child-src": ["'self'", "blob:"],
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'none'"],
    }
    return "; ".join(f"{name} {' '.join(values)}" for name, values in directives.items())


class SecurityHeadersMiddleware:
    """Adds Content-Security-Policy and Permissions-Policy headers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/admin/"):
            # The Django admin ships inline scripts; leave it alone.
            return response
        if "Content-Security-Policy" not in response:
            from pipetrace.core.models import SiteConfig

            extra = []
            try:
                basemap = SiteConfig.load().basemap_pmtiles_url
                if basemap:
                    extra.append(basemap)
            except Exception:
                pass
            response["Content-Security-Policy"] = build_csp(extra)
        response.setdefault(
            "Permissions-Policy", "camera=(self), geolocation=(self), microphone=()"
        )
        return response
