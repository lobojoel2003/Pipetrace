"""Pages for residents."""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.mail import send_mail
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET

from pipetrace.inventory import stats
from pipetrace.inventory.choices import (
    NEEDS_REPLACEMENT,
    STATUS_ORDER,
    Connector,
    Material,
    Replacement,
)
from pipetrace.inventory.models import ServiceLine
from pipetrace.inventory.search import best_match, same_street, search
from pipetrace.residents.forms import InspectionRequestForm, PipeCheckForm, started_token
from pipetrace.residents.models import InspectionRequest, PipeCheck
from pipetrace.residents.status import status_text

log = logging.getLogger(__name__)


def _lang() -> str:
    return (get_language() or "en")[:2]


def _local_url(url: str) -> str:
    """Prefix site-relative URLs (like /basemap/area.pmtiles) for sub-path static exports."""
    from django.urls import get_script_prefix

    if url.startswith("/") and not url.startswith("//"):
        return get_script_prefix().rstrip("/") + url
    return url


def map_config(request, focus: ServiceLine | None = None) -> dict:
    """Settings for ``map.js``. In a static export every URL here is a file."""
    from django.templatetags.static import static

    from pipetrace.core.models import SiteConfig

    site = SiteConfig.load()
    view = stats.map_view()
    config = {
        "data": reverse("api:lines"),
        # A folder, not a file: the manifest only knows files, so build the URL directly.
        "assets": settings.STATIC_URL.rstrip("/") + "/pipetrace/vendor/basemaps-assets",
        "pmtiles": _local_url(site.basemap_pmtiles_url),
        "demo": static("pipetrace/demo/millbrook-basemap.geojson") if site.demo_mode else "",
        "lang": _lang(),
        "bounds": view["bounds"] if view else None,
        "center": [site.map_center_lon, site.map_center_lat]
        if site.map_center_lat is not None and site.map_center_lon is not None
        else (view["center"] if view else None),
        "zoom": site.map_zoom,
    }
    if focus and focus.location:
        config["focus"] = {"id": focus.public_id, "lon": focus.location.x, "lat": focus.location.y}
    return config


def home(request):
    summary = stats.summary()
    by_status = [{**row, **status_text(row["status"])} for row in summary["by_status"]]
    return render(
        request,
        "residents/home.html",
        {
            "summary": summary,
            "by_status": by_status,
            "map_config": map_config(request),
        },
    )


def search_view(request):
    query = (request.GET.get("q") or "").strip()[:200]
    matches = []
    if query and not getattr(request, "static_export", False):
        if request.GET.get("all") != "1":
            line = best_match(query)
            if line is not None:
                return redirect(line)
        matches = search(query, limit=25)
    results = [{"line": m.line, **status_text(m.line.status)} for m in matches]
    nearby = []
    if query and not matches and not getattr(request, "static_export", False):
        nearby = [{"line": m.line, **status_text(m.line.status)} for m in same_street(query)]
    return render(
        request,
        "residents/search.html",
        {
            "query": query,
            "results": results,
            "nearby": nearby,
        },
    )


def _schedule_text(line: ServiceLine) -> str:
    if line.scheduled_label:
        return line.scheduled_label
    if line.scheduled_on:
        from django.utils.formats import date_format

        return date_format(line.scheduled_on, "YEAR_MONTH_FORMAT")
    return ""


def line_view(request, public_id: str):
    line = get_object_or_404(ServiceLine.objects.public(), public_id=public_id)
    info = status_text(line.status)
    replaced = line.replacement == Replacement.REPLACED
    portions = [
        {
            "label": _("Utility side"),
            "help": _("From the water main to the curb or meter"),
            "material": line.get_system_material_display(),
            "is_lead": line.system_material in {Material.LEAD, Material.GALVANIZED},
            "known": line.system_material != Material.UNKNOWN,
        },
        {
            "label": _("Your side"),
            "help": _("From the curb or meter to your building"),
            "material": line.get_customer_material_display(),
            "is_lead": line.customer_material in {Material.LEAD, Material.GALVANIZED},
            "known": line.customer_material != Material.UNKNOWN,
        },
    ]
    return render(
        request,
        "residents/line.html",
        {
            "line": line,
            "info": info,
            "replaced": replaced,
            "needs_replacement": line.status in NEEDS_REPLACEMENT and not replaced,
            "portions": portions,
            "lead_connector": line.connector == Connector.LEAD,
            "schedule_text": _schedule_text(line),
            "note": line.localized_note(_lang()),
            "map_config": map_config(request, focus=line),
        },
    )


def guide(request):
    return render(
        request,
        "residents/check_pipe.html",
        {
            "line": _line_from_query(request),
        },
    )


def filters(request):
    return render(request, "residents/filters.html")


def about(request):
    return render(
        request,
        "residents/about.html",
        {
            "summary": stats.summary(),
            "status_rows": [{"status": s.value, **status_text(s)} for s in STATUS_ORDER],
        },
    )


def streets(request):
    return render(request, "residents/streets.html", {"streets": stats.streets()})


def street(request, slug: str):
    key = slug.replace("-", " ").upper()
    lines = list(ServiceLine.objects.public().filter(street_key=key))
    if not lines:
        match = next((s for s in stats.streets() if s["slug"] == slug), None)
        if not match:
            raise Http404
        lines = list(ServiceLine.objects.public().filter(street_key=match["street_key"]))
    rows = [{"line": line, **status_text(line.status)} for line in lines]
    return render(
        request,
        "residents/street.html",
        {
            "street_name": lines[0].street_display,
            "rows": rows,
        },
    )


def _line_from_query(request) -> ServiceLine | None:
    public_id = request.GET.get("line")
    if not public_id:
        return None
    return ServiceLine.objects.public().filter(public_id=public_id).first()


def client_ip(request) -> str:
    if settings.SECURE_PROXY_SSL_HEADER:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def rate_limited(request, bucket: str) -> bool:
    """Allow a few submissions per visitor per hour."""
    import hashlib

    ip = hashlib.sha256(client_ip(request).encode()).hexdigest()[:16]
    key = f"pipetrace:rate:{bucket}:{ip}"
    count = cache.get(key, 0)
    if count >= settings.PIPETRACE["SUBMISSIONS_PER_HOUR"]:
        return True
    cache.set(key, count + 1, 60 * 60)
    return False


def notify(submission, kind: str) -> None:
    """Email staff about a new submission, and the resident a receipt."""
    from pipetrace.core.models import SiteConfig

    site = SiteConfig.load()
    staff_to = list(settings.PIPETRACE["NOTIFY_EMAILS"]) or ([site.email] if site.email else [])
    context = {"submission": submission, "kind": kind, "site": site}
    try:
        if staff_to:
            send_mail(
                subject=f"[Pipetrace] {submission.reference}: {submission.address}",
                message=render_to_string("residents/email/staff_notice.txt", context),
                from_email=None,
                recipient_list=staff_to,
                fail_silently=False,
            )
        if submission.email:
            send_mail(
                subject=_("We received your message (%(reference)s)")
                % {"reference": submission.reference},
                message=render_to_string("residents/email/receipt.txt", context),
                from_email=None,
                recipient_list=[submission.email],
                fail_silently=False,
            )
    except Exception:
        log.exception("Could not send notification email for %s", submission.reference)


def _submission_view(request, form_class, template: str, kind: str):
    line = _line_from_query(request)
    if request.method == "POST":
        form = form_class(request.POST, request.FILES)
        if rate_limited(request, kind):
            messages.error(
                request,
                _(
                    "You've sent several messages already. Please call us "
                    "instead, or try again in an hour."
                ),
            )
        elif form.is_valid():
            submission = form.save(commit=False)
            if line is None:
                from pipetrace.inventory.search import best_match as find

                line = find(submission.address)
            submission.service_line = line
            submission.save()
            notify(submission, kind)
            return redirect("residents:thanks", reference=submission.reference)
    else:
        initial = {"language": _lang(), "started": started_token()}
        if line:
            initial["address"] = line.full_address
        form = form_class(initial=initial)
    return render(request, template, {"form": form, "line": line})


def send_photo(request):
    return _submission_view(request, PipeCheckForm, "residents/send_photo.html", "photo")


def request_inspection(request):
    return _submission_view(
        request, InspectionRequestForm, "residents/request_inspection.html", "inspection"
    )


@require_GET
def thanks(request, reference: str):
    submission = (
        InspectionRequest.objects.filter(reference=reference).first()
        or PipeCheck.objects.filter(reference=reference).first()
    )
    if submission is None:
        raise Http404
    return render(
        request,
        "residents/thanks.html",
        {
            "reference": submission.reference,
            "kind": "photo" if isinstance(submission, PipeCheck) else "inspection",
        },
    )
