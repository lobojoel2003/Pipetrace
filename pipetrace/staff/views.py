"""Staff tools: import the inventory, place lines on the map, answer residents."""

from __future__ import annotations

import csv
import io
import tempfile
from functools import lru_cache
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from pipetrace.core.models import SiteConfig
from pipetrace.inventory import geocoding, stats
from pipetrace.inventory.choices import (
    GeocodeStatus,
    Material,
    Status,
)
from pipetrace.inventory.importer import fields as F
from pipetrace.inventory.importer import pipeline
from pipetrace.inventory.importer.detect import (
    header_signature,
    mapping_by_label,
    mapping_from_labels,
)
from pipetrace.inventory.importer.readers import UnsupportedFile, read_workbook
from pipetrace.inventory.importer.values import CHOICES
from pipetrace.inventory.models import ImportBatch, ServiceLine
from pipetrace.residents.models import InspectionRequest, PipeCheck
from pipetrace.staff.forms import InspectionUpdateForm, PhotoReviewForm, UploadForm

staff_required = user_passes_test(lambda u: u.is_active and u.is_staff, login_url="staff:login")


@staff_required
def dashboard(request):
    return render(
        request,
        "staff/dashboard.html",
        {
            "summary": stats.summary(),
            "geocode": stats.geocode_counts(),
            "new_requests": InspectionRequest.objects.filter(
                state=InspectionRequest.State.NEW
            ).count(),
            "new_photos": PipeCheck.objects.filter(state=PipeCheck.State.NEW).count(),
            "recent_requests": InspectionRequest.objects.all()[:5],
            "recent_photos": PipeCheck.objects.all()[:5],
            "last_import": ImportBatch.objects.filter(state=ImportBatch.State.COMMITTED).first(),
        },
    )


# --- Import wizard ----------------------------------------------------------------------


@lru_cache(maxsize=4)
def _read_cached(path: str, mtime: float, name: str):
    with open(path, "rb") as handle:
        return read_workbook(handle, name)


def _workbook(batch: ImportBatch):
    path = batch.file.path
    return _read_cached(path, Path(path).stat().st_mtime, batch.original_name)


def _layout(batch: ImportBatch, workbook):
    return pipeline.analyze(
        workbook,
        sheet=batch.sheet_name or None,
        header_row=batch.header_row or None,
        data_start_row=batch.data_start_row or None,
    )


@staff_required
def imports(request):
    return render(
        request,
        "staff/imports.html",
        {
            "batches": ImportBatch.objects.select_related("uploaded_by")[:50],
        },
    )


@staff_required
def import_upload(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            upload = form.cleaned_data["file"]
            try:
                workbook = read_workbook(upload, upload.name)
            except UnsupportedFile as exc:
                form.add_error("file", str(exc))
            else:
                layout = pipeline.analyze(workbook)
                batch = ImportBatch(
                    original_name=upload.name[:255],
                    uploaded_by=request.user,
                    mode=form.cleaned_data["mode"],
                    sheet_name=layout.sheet,
                    header_row=layout.header_row,
                    data_start_row=layout.data_start_row,
                    columns=[c.as_dict() for c in layout.columns],
                    header_signature=header_signature(layout.columns),
                )
                upload.seek(0)
                batch.file.save(upload.name, upload, save=False)
                batch.column_map, batch.value_map = _initial_mapping(layout, batch)
                batch.save()
                return redirect("staff:import_map", pk=batch.pk)
    else:
        form = UploadForm()
    return render(request, "staff/import_upload.html", {"form": form, "fields": F.FIELDS})


def _initial_mapping(layout, batch) -> tuple[dict, dict]:
    """Reuse the last mapping for a file with the same columns, else auto-detect."""
    previous = (
        ImportBatch.objects.filter(
            header_signature=batch.header_signature, state=ImportBatch.State.COMMITTED
        )
        .exclude(pk=batch.pk)
        .first()
    )
    if previous and previous.column_map:
        saved_labels = previous.stats.get("column_labels") or {}
        mapping = (
            mapping_from_labels(saved_labels, layout.columns)
            if saved_labels
            else {k: v for k, v in previous.column_map.items() if layout.column(v) is not None}
        )
        return mapping, previous.value_map or {}
    return pipeline.auto_mapping(layout), {}


@staff_required
def import_map(request, pk: int):
    batch = get_object_or_404(ImportBatch, pk=pk)
    if batch.state == ImportBatch.State.COMMITTED:
        return redirect(batch)
    workbook = _workbook(batch)

    # Changing sheet or header row re-reads the layout and re-guesses the mapping.
    changed = False
    sheet = request.GET.get("sheet")
    if sheet in workbook.sheet_names and sheet != batch.sheet_name:
        batch.sheet_name = sheet
        batch.header_row = 0
        batch.data_start_row = 0
        changed = True
    for param, attr in (("header_row", "header_row"), ("data_start_row", "data_start_row")):
        value = request.GET.get(param, "")
        if value.isdigit() and int(value) != getattr(batch, attr):
            setattr(batch, attr, int(value))
            if attr == "header_row":
                batch.data_start_row = 0
            changed = True
    layout = _layout(batch, workbook)
    if changed:
        batch.sheet_name = layout.sheet
        batch.header_row = layout.header_row
        batch.data_start_row = layout.data_start_row
        batch.columns = [c.as_dict() for c in layout.columns]
        batch.header_signature = header_signature(layout.columns)
        batch.column_map = pipeline.auto_mapping(layout)
        batch.save()

    problems: list[str] = []
    if request.method == "POST":
        mapping = {}
        for spec in F.FIELDS:
            raw = request.POST.get(f"map_{spec.key}", "")
            if raw.isdigit() and layout.column(int(raw)) is not None:
                mapping[spec.key] = int(raw)
        problems = pipeline.validate_mapping(mapping)
        batch.column_map = mapping
        if not problems:
            batch.state = ImportBatch.State.MAPPED
            batch.save()
            return redirect("staff:import_values", pk=batch.pk)
        batch.save()

    sheet = workbook.sheet(layout.sheet)
    preview_start = max(0, layout.header_row - 3)
    preview_rows = [
        {
            "number": i + 1,
            "cells": [row[c.index] if c.index < len(row) else "" for c in layout.columns],
            "is_header": i + 1 == layout.header_row,
            "is_data": i + 1 >= layout.data_start_row,
        }
        for i, row in enumerate(
            sheet.rows[preview_start : layout.data_start_row + 5], start=preview_start
        )
    ]
    used = {v: k for k, v in batch.column_map.items()}
    groups = [
        {
            "label": label,
            "fields": [
                {"spec": spec, "selected": batch.column_map.get(spec.key)}
                for spec in F.FIELDS
                if spec.group == key
            ],
        }
        for key, label in F.FIELD_GROUPS
    ]
    return render(
        request,
        "staff/import_map.html",
        {
            "batch": batch,
            "layout": layout,
            "groups": groups,
            "columns": layout.columns,
            "preview_rows": preview_rows,
            "problems": problems,
            "used": used,
            "unmapped": [c for c in layout.columns if c.index not in used],
            "header_choices": range(1, min(sheet.non_empty_rows(), 40) + 1),
        },
    )


@staff_required
def import_values(request, pk: int):
    batch = get_object_or_404(ImportBatch, pk=pk)
    if batch.state == ImportBatch.State.COMMITTED:
        return redirect(batch)
    if not batch.column_map:
        return redirect("staff:import_map", pk=pk)
    workbook = _workbook(batch)
    layout = _layout(batch, workbook)
    rows = workbook.sheet(layout.sheet).rows
    report = pipeline.value_report(rows, layout, batch.column_map, batch.value_map)
    if request.method == "POST":
        value_map: dict[str, dict[str, str]] = {}
        for key, entries in report.items():
            valid = {c[0] for c in CHOICES[F.FIELDS_BY_KEY[key].kind]}
            for entry in entries:
                chosen = request.POST.get(f"value_{key}_{entry.key}")
                if chosen is None:
                    continue
                if chosen and chosen not in valid:
                    continue
                if chosen != entry.auto or entry.needs_review:
                    value_map.setdefault(key, {})[entry.key] = chosen
        batch.value_map = value_map
        batch.save()
        return redirect("staff:import_preview", pk=pk)
    if not report:
        return redirect("staff:import_preview", pk=pk)
    sections = [
        {
            "key": key,
            "spec": F.FIELDS_BY_KEY[key],
            "entries": entries,
            "choices": CHOICES[F.FIELDS_BY_KEY[key].kind],
            "review": sum(1 for e in entries if e.needs_review),
        }
        for key, entries in report.items()
    ]
    return render(request, "staff/import_values.html", {"batch": batch, "sections": sections})


@staff_required
def import_preview(request, pk: int):
    batch = get_object_or_404(ImportBatch, pk=pk)
    if batch.state == ImportBatch.State.COMMITTED:
        return redirect(batch)
    if not batch.column_map:
        return redirect("staff:import_map", pk=pk)
    workbook = _workbook(batch)
    layout = _layout(batch, workbook)
    rows = workbook.sheet(layout.sheet).rows
    extraction = pipeline.extract(
        rows, layout, batch.column_map, batch.value_map, pipeline.defaults_from_config()
    )
    if request.method == "POST":
        if request.POST.get("mode") in ImportBatch.Mode.values:
            batch.mode = request.POST["mode"]
        stats_ = pipeline.commit(batch, extraction, batch.mode)
        batch.stats = {
            **stats_,
            "column_labels": mapping_by_label(batch.column_map, layout.columns),
        }
        batch.save(update_fields=["stats"])
        messages.success(
            request,
            _("Imported %(created)s new and %(updated)s updated lines.")
            % {"created": stats_["created"], "updated": stats_["updated"]},
        )
        if stats_["pending_geocode"]:
            return redirect(f"{reverse('staff:geocode')}?from_import={batch.pk}")
        return redirect(batch)
    plan = pipeline.plan(extraction, batch.mode)
    sample = extraction.records[:15]
    return render(
        request,
        "staff/import_preview.html",
        {
            "batch": batch,
            "extraction": extraction,
            "plan": plan,
            "sample": sample,
            "status_counts": [
                {"status": s, "label": s.label, "count": extraction.status_counts[s.value]}
                for s in (Status.LEAD, Status.GRR, Status.UNKNOWN, Status.NON_LEAD)
            ],
            "material_labels": dict(Material.choices),
            "status_labels": dict(Status.choices),
        },
    )


@staff_required
def import_detail(request, pk: int):
    batch = get_object_or_404(ImportBatch, pk=pk)
    return render(
        request, "staff/import_detail.html", {"batch": batch, "status_labels": dict(Status.choices)}
    )


# --- Geocoding ------------------------------------------------------------------------


@staff_required
def geocode(request):
    counts = stats.geocode_counts()
    unmatched = ServiceLine.objects.public().filter(geocode_status=GeocodeStatus.NO_MATCH)[:100]
    return render(
        request,
        "staff/geocode.html",
        {
            "counts": counts,
            "unmatched": unmatched,
            "geocoder": geocoding.get_geocoder(),
            "pending": counts[GeocodeStatus.PENDING],
            "from_import": request.GET.get("from_import"),
        },
    )


@staff_required
@require_POST
def geocode_step(request):
    progress = geocoding.geocode_batch()
    return JsonResponse(progress.as_dict(), status=502 if progress.error else 200)


@staff_required
@require_POST
def geocode_retry(request):
    count = geocoding.reset_failed()
    messages.info(request, _("%(count)s addresses queued to try again.") % {"count": count})
    return redirect("staff:geocode")


# --- Inventory list and exports -------------------------------------------------------


@staff_required
def lines(request):
    qs = ServiceLine.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(address__icontains=q) | Q(source_id__icontains=q) | Q(normalized__icontains=q.upper())
        )
    for param in ("status", "replacement", "geocode_status"):
        value = request.GET.get(param)
        if value:
            qs = qs.filter(**{param: value})
    if request.GET.get("inactive") != "1":
        qs = qs.filter(active=True)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "staff/lines.html",
        {
            "page": page,
            "q": q,
            "filters": request.GET,
            "status_choices": Status.choices,
            "geocode_choices": GeocodeStatus.choices,
        },
    )


EXPORT_COLUMNS = [
    ("Service Line ID", "source_id"),
    ("Street Address", "address"),
    ("Unit", "unit"),
    ("City", "city"),
    ("State", "state"),
    ("ZIP Code", "zip_code"),
    ("System-Owned Portion Material", "system_material"),
    ("Customer-Owned Portion Material", "customer_material"),
    ("Entire Service Line Classification", "status"),
    ("Galvanized Ever Downstream of Lead", "downstream_of_lead"),
    ("Lead Connector", "connector"),
    ("Basis of Classification", "basis"),
    ("Date Verified", "verified_on"),
    ("Year Installed", "installed_year"),
    ("Year Built", "building_year"),
    ("Replacement Status", "replacement"),
    ("Scheduled Replacement", "scheduled_label"),
    ("Scheduled Date", "scheduled_on"),
    ("Date Replaced", "replaced_on"),
    ("Latitude", "lat"),
    ("Longitude", "lon"),
    ("Geocoding", "geocode_status"),
    ("Public Note", "public_note"),
    ("Pipetrace Page", "public_id"),
]


def _export_value(line: ServiceLine, attr: str):
    value = getattr(line, attr)
    if (
        attr
        in {
            "system_material",
            "customer_material",
            "status",
            "downstream_of_lead",
            "connector",
            "replacement",
            "geocode_status",
        }
        and value
    ):
        return getattr(line, f"get_{attr}_display")()
    if attr == "public_id":
        return reverse("residents:line", kwargs={"public_id": value})
    return "" if value is None else value


@staff_required
def export_inventory(request):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([c[0] for c in EXPORT_COLUMNS])
    for line in ServiceLine.objects.public().iterator(chunk_size=2000):
        writer.writerow([_export_value(line, attr) for _label, attr in EXPORT_COLUMNS])
    response = HttpResponse(
        buffer.getvalue().encode("utf-8-sig"), content_type="text/csv; charset=utf-8"
    )
    stamp = timezone.localdate().isoformat()
    response["Content-Disposition"] = f'attachment; filename="service-line-inventory-{stamp}.csv"'
    return response


@staff_required
def export_site(request):
    """Build the static site and download it as a zip."""
    from pipetrace.export.exporter import export_site as build

    base = request.GET.get("base", "/").strip() or "/"
    tmp = Path(tempfile.mkdtemp(prefix="pipetrace-export-"))
    result = build(tmp / "site", base_url=base, zip_path=tmp / "site.zip")
    response = FileResponse(
        open(result.zip_path, "rb"),  # noqa: SIM115 - FileResponse closes it
        as_attachment=True,
        filename=f"pipetrace-site-{timezone.localdate().isoformat()}.zip",
    )
    return response


# --- Residents' requests and photos -------------------------------------------------------


@staff_required
def requests_list(request):
    state = request.GET.get("state", "")
    qs = InspectionRequest.objects.select_related("service_line")
    if state:
        qs = qs.filter(state=state)
    counts = dict(
        InspectionRequest.objects.values_list("state")
        .annotate(n=Count("pk"))
        .values_list("state", "n")
    )
    return render(
        request,
        "staff/requests.html",
        {
            "page": Paginator(qs, 30).get_page(request.GET.get("page")),
            "state": state,
            "states": InspectionRequest.State.choices,
            "counts": counts,
        },
    )


@staff_required
def request_detail(request, pk: int):
    item = get_object_or_404(InspectionRequest.objects.select_related("service_line"), pk=pk)
    form = InspectionUpdateForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Saved."))
        return redirect("staff:requests")
    return render(request, "staff/request_detail.html", {"item": item, "form": form})


@staff_required
def photos_list(request):
    state = request.GET.get("state", "")
    qs = PipeCheck.objects.select_related("service_line")
    if state:
        qs = qs.filter(state=state)
    return render(
        request,
        "staff/photos.html",
        {
            "page": Paginator(qs, 24).get_page(request.GET.get("page")),
            "state": state,
            "states": PipeCheck.State.choices,
        },
    )


@staff_required
def photo_detail(request, pk: int):
    item = get_object_or_404(PipeCheck.objects.select_related("service_line"), pk=pk)
    form = PhotoReviewForm(
        request.POST or None,
        instance=item,
        initial={"staff_material": item.staff_material or item.resident_result},
    )
    if request.method == "POST" and form.is_valid():
        check = form.save(commit=False)
        check.reviewed_by = request.user
        check.reviewed_at = timezone.now()
        if check.state == PipeCheck.State.NEW:
            check.state = PipeCheck.State.REVIEWED
        if form.cleaned_data.get("apply") and check.service_line:
            line = check.service_line
            line.customer_material = check.staff_material
            line.status_from_file = False
            line.basis = _("Resident photo reviewed by staff (%(ref)s)") % {"ref": check.reference}
            line.verified_on = timezone.localdate()
            line.save()
            check.applied_to_line = True
            messages.success(
                request,
                _("Inventory updated: %(address)s is now “%(status)s”.")
                % {"address": line.street_line, "status": line.get_status_display()},
            )
        check.save()
        return redirect("staff:photos")
    return render(request, "staff/photo_detail.html", {"item": item, "form": form})


@staff_required
def photo_file(request, pk: int, which: int = 1):
    """Serve a resident photo to staff only (photos are not public media)."""
    item = get_object_or_404(PipeCheck, pk=pk)
    field = item.photo if which == 1 else item.photo_2
    if not field:
        from django.http import Http404

        raise Http404
    return FileResponse(field.open("rb"), content_type="image/jpeg")


@staff_required
def settings_redirect(request):
    config = SiteConfig.load()
    return redirect(reverse("admin:core_siteconfig_change", args=[config.pk]))


class LoginView(auth_views.LoginView):
    """Django's login view, keeping ``site`` pointed at the utility settings."""

    template_name = "staff/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["site"] = SiteConfig.load()
        return context
