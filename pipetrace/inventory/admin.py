from django import forms
from django.contrib import admin, messages
from django.contrib.gis.geos import Point
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from pipetrace.inventory.choices import GeocodeStatus, Replacement
from pipetrace.inventory.models import ImportBatch, ServiceLine


class ServiceLineForm(forms.ModelForm):
    """Edit coordinates as plain numbers (no external map tiles in the admin)."""

    latitude = forms.FloatField(label=_("Latitude"), required=False, min_value=-90, max_value=90)
    longitude = forms.FloatField(
        label=_("Longitude"), required=False, min_value=-180, max_value=180
    )

    class Meta:
        model = ServiceLine
        exclude = ["location"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.location:
            self.fields["latitude"].initial = round(self.instance.location.y, 7)
            self.fields["longitude"].initial = round(self.instance.location.x, 7)

    def clean(self):
        data = super().clean()
        if (data.get("latitude") is None) != (data.get("longitude") is None):
            raise forms.ValidationError(_("Enter both latitude and longitude, or neither."))
        return data

    def save(self, commit=True):
        line = super().save(commit=False)
        lat, lon = self.cleaned_data.get("latitude"), self.cleaned_data.get("longitude")
        old = (round(line.location.y, 7), round(line.location.x, 7)) if line.location else None
        if lat is not None and lon is not None:
            if old != (round(lat, 7), round(lon, 7)):
                line.location = Point(lon, lat, srid=4326)
                line.geocode_status = GeocodeStatus.MANUAL
                line.geocoded_at = timezone.now()
        elif old is not None:
            line.location = None
            line.geocode_status = GeocodeStatus.PENDING
        if commit:
            line.save()
        return line


@admin.register(ServiceLine)
class ServiceLineAdmin(admin.ModelAdmin):
    form = ServiceLineForm
    list_display = [
        "full_address",
        "status",
        "system_material",
        "customer_material",
        "replacement",
        "geocode_status",
        "active",
        "view_link",
    ]
    list_filter = [
        "status",
        "replacement",
        "geocode_status",
        "system_material",
        "customer_material",
        "connector",
        "active",
    ]
    search_fields = ["address", "source_id", "city", "zip_code", "normalized"]
    readonly_fields = [
        "public_id",
        "geocode_match",
        "geocode_score",
        "geocoded_at",
        "import_batch",
        "created_at",
        "updated_at",
    ]
    list_per_page = 50
    actions = ["queue_geocoding", "mark_replaced"]
    fieldsets = [
        (
            _("Location"),
            {
                "fields": [
                    "public_id",
                    "source_id",
                    "address",
                    "unit",
                    "city",
                    "state",
                    "zip_code",
                    ("latitude", "longitude"),
                    "geocode_status",
                    "geocode_match",
                    "geocode_score",
                    "geocoded_at",
                ]
            },
        ),
        (
            _("Material"),
            {
                "fields": [
                    "status",
                    "status_from_file",
                    "system_material",
                    "customer_material",
                    "downstream_of_lead",
                    "connector",
                    "basis",
                    "verified_on",
                    "installed_year",
                    "building_year",
                ]
            },
        ),
        (
            _("Replacement"),
            {"fields": ["replacement", "scheduled_on", "scheduled_label", "replaced_on"]},
        ),
        (_("Notes"), {"fields": ["public_note", "public_note_es", "internal_note", "extra"]}),
        (_("Record"), {"fields": ["active", "import_batch", "created_at", "updated_at"]}),
    ]

    def get_readonly_fields(self, request, obj=None):
        return [*self.readonly_fields, "status_from_file"]

    @admin.display(description=_("Address"), ordering="street_key")
    def full_address(self, obj):
        return obj.full_address

    @admin.display(description=_("Public page"))
    def view_link(self, obj):
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">{}</a>', obj.get_absolute_url(), _("View")
        )

    def save_model(self, request, obj, form, change):
        # Staff edits to the materials should drive the classification again.
        if (
            change
            and {"system_material", "customer_material", "downstream_of_lead"}
            & set(form.changed_data)
            and "status" not in form.changed_data
        ):
            obj.status_from_file = False
        if "status" in form.changed_data:
            obj.status_from_file = True
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Look up the location again from the address"))
    def queue_geocoding(self, request, queryset):
        count = queryset.update(geocode_status=GeocodeStatus.PENDING, location=None)
        self.message_user(
            request, _("%(count)d lines queued for geocoding.") % {"count": count}, messages.SUCCESS
        )

    @admin.action(description=_("Mark as replaced today"))
    def mark_replaced(self, request, queryset):
        today = timezone.localdate()
        for line in queryset:
            line.replacement = Replacement.REPLACED
            line.replaced_on = line.replaced_on or today
            line.save()
        self.message_user(
            request,
            _("%(count)d lines marked as replaced.") % {"count": queryset.count()},
            messages.SUCCESS,
        )


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ["original_name", "created_at", "state", "mode", "uploaded_by"]
    list_filter = ["state", "mode"]
    readonly_fields = [f.name for f in ImportBatch._meta.fields]

    def has_add_permission(self, request):
        return False
