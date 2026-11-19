"""Template context shared by every page."""

from __future__ import annotations

from pipetrace.buildinfo import get_build_info
from pipetrace.core.models import SiteConfig


def pipetrace(request):
    return {
        "site": SiteConfig.load(),
        "build": get_build_info(),
        # Set to True by the static exporter; templates switch forms and search
        # to their client-side versions.
        "static_mode": getattr(request, "static_export", False),
    }
