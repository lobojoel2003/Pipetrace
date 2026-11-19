"""JSON endpoints used by the map, the search box and the static site's forms."""

from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse
from django.utils import translation
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from pipetrace.buildinfo import get_build_info
from pipetrace.inventory import addresses, stats
from pipetrace.inventory.choices import STATUS_CODES, Status
from pipetrace.inventory.models import ServiceLine
from pipetrace.inventory.search import same_street, search
from pipetrace.residents.forms import ApiInspectionRequestForm, ApiPipeCheckForm
from pipetrace.residents.status import status_text
from pipetrace.residents.views import notify, rate_limited


def _lang(request) -> str:
    lang = (request.GET.get("lang") or "en")[:2]
    return lang if lang in dict(settings.LANGUAGES) else "en"


@require_GET
def search_api(request):
    query = (request.GET.get("q") or "").strip()[:200]
    lang = _lang(request)
    with translation.override(lang):
        results = (
            [
                {
                    "id": m.line.public_id,
                    "address": m.line.street_line,
                    "city": m.line.city,
                    "code": STATUS_CODES[Status(m.line.status)],
                    "label": status_text(m.line.status)["short"],
                    "url": reverse("residents:line", kwargs={"public_id": m.line.public_id}),
                    "exact": m.exact,
                }
                for m in (search(query, limit=8) or same_street(query, limit=8))
            ]
            if query
            else []
        )
    response = JsonResponse({"query": query, "results": results})
    response["Cache-Control"] = "public, max-age=60"
    return response


@require_GET
def lines_geojson(request):
    response = JsonResponse(stats.lines_geojson())
    response["Cache-Control"] = "public, max-age=300"
    return response


@require_GET
def stats_api(request):
    data = {**stats.summary(), "build": get_build_info().as_dict()}
    return JsonResponse(data)


def search_index() -> dict:
    """Everything the browser needs to search without a server (static export)."""
    rows = []
    qs = ServiceLine.objects.public().only(
        "public_id", "address", "unit", "city", "normalized", "status"
    )
    for line in qs.iterator(chunk_size=2000):
        rows.append(
            [
                line.public_id,
                line.street_line,
                line.city,
                line.normalized,
                STATUS_CODES[Status(line.status)],
            ]
        )
    return {"config": addresses.search_config(), "lines": rows}


@require_GET
def search_index_api(request):
    response = JsonResponse(search_index())
    response["Cache-Control"] = "public, max-age=300"
    return response


def _cors(request, response):
    allowed = settings.PIPETRACE.get("STATIC_SITE_ORIGINS") or ["*"]
    origin = request.headers.get("Origin", "")
    if "*" in allowed:
        response["Access-Control-Allow-Origin"] = "*"
    elif origin in allowed:
        response["Access-Control-Allow-Origin"] = origin
        response["Vary"] = "Origin"
    response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    response["Access-Control-Max-Age"] = "86400"
    return response


@csrf_exempt
def submit_api(request):
    """Accept an inspection request or pipe photo posted by a static Pipetrace site."""
    if request.method == "OPTIONS":
        return _cors(request, JsonResponse({}))
    if request.method != "POST":
        return _cors(request, JsonResponse({"error": "POST only"}, status=405))
    kind = request.POST.get("kind")
    form_class = {"inspection": ApiInspectionRequestForm, "photo": ApiPipeCheckForm}.get(kind)
    if form_class is None:
        return _cors(request, JsonResponse({"error": "Unknown form."}, status=400))
    if rate_limited(request, kind):
        return _cors(request, JsonResponse({"error": "Too many submissions."}, status=429))
    lang = _lang(request) if request.GET.get("lang") else (request.POST.get("language") or "en")
    with translation.override(lang if lang in dict(settings.LANGUAGES) else "en"):
        form = form_class(request.POST, request.FILES)
        if not form.is_valid():
            errors = {k: [str(e) for e in v] for k, v in form.errors.items()}
            return _cors(request, JsonResponse({"errors": errors}, status=400))
        submission = form.save(commit=False)
        submission.via_static_site = True
        line_id = request.POST.get("line")
        if line_id:
            submission.service_line = ServiceLine.objects.public().filter(public_id=line_id).first()
        if submission.service_line is None:
            from pipetrace.inventory.search import best_match

            submission.service_line = best_match(submission.address)
        submission.save()
        notify(submission, kind)
    return _cors(request, JsonResponse({"reference": submission.reference}, status=201))
