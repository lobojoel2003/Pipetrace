from django.contrib import admin

from pipetrace.residents.models import InspectionRequest, PipeCheck


@admin.register(InspectionRequest)
class InspectionRequestAdmin(admin.ModelAdmin):
    list_display = ["reference", "address", "name", "phone", "email", "state", "created_at"]
    list_filter = ["state", "language", "contact_by", "via_static_site"]
    search_fields = ["reference", "address", "name", "email", "phone"]
    readonly_fields = ["reference", "created_at", "updated_at"]
    raw_id_fields = ["service_line"]


@admin.register(PipeCheck)
class PipeCheckAdmin(admin.ModelAdmin):
    list_display = [
        "reference",
        "address",
        "scratch",
        "magnet",
        "resident_result",
        "state",
        "created_at",
    ]
    list_filter = ["state", "resident_result", "staff_material", "language"]
    search_fields = ["reference", "address", "name", "email"]
    readonly_fields = ["reference", "created_at", "updated_at", "reviewed_by", "reviewed_at"]
    raw_id_fields = ["service_line"]
