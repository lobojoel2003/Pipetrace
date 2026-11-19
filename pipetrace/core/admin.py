from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from pipetrace.core.models import SiteConfig

admin.site.site_header = _("Pipetrace administration")
admin.site.site_title = _("Pipetrace")
admin.site.index_title = _("Inventory, requests and settings")
admin.site.site_url = "/staff/"


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    fieldsets = [
        (
            _("Your utility"),
            {
                "fields": [
                    "utility_name",
                    "utility_name_es",
                    "pwsid",
                    "phone",
                    "email",
                    "website",
                    "office_address",
                    "office_hours",
                    "office_hours_es",
                ]
            },
        ),
        (_("Defaults for addresses"), {"fields": ["default_city", "default_state", "default_zip"]}),
        (
            _("Programs shown to residents"),
            {
                "fields": [
                    "replacement_deadline",
                    "replacement_program",
                    "replacement_program_es",
                    "filter_program",
                    "filter_program_es",
                    "unknown_program",
                    "unknown_program_es",
                ]
            },
        ),
        (
            _("Map"),
            {"fields": ["basemap_pmtiles_url", "map_center_lat", "map_center_lon", "map_zoom"]},
        ),
        (_("Static site"), {"fields": ["static_form_endpoint"]}),
        (_("Status"), {"fields": ["inventory_updated", "demo_mode"]}),
    ]

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        config = SiteConfig.load()
        return redirect(reverse("admin:core_siteconfig_change", args=[config.pk]))
