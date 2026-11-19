"""Site-wide settings that a utility edits in the admin."""

from __future__ import annotations

import datetime

from django.core.cache import cache
from django.db import models
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

CACHE_KEY = "pipetrace:siteconfig"


class SiteConfig(models.Model):
    """A single row of settings describing the water system that runs this site."""

    utility_name = models.CharField(_("utility name"), max_length=200, default="Your Water Utility")
    utility_name_es = models.CharField(
        _("utility name (Spanish)"),
        max_length=200,
        blank=True,
        help_text=_("Leave blank to use the English name."),
    )
    pwsid = models.CharField(
        _("public water system ID"),
        max_length=20,
        blank=True,
        help_text=_("Your PWSID, for example IL0310450."),
    )
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    email = models.EmailField(_("email"), blank=True)
    website = models.URLField(_("website"), blank=True)
    office_address = models.CharField(_("office address"), max_length=300, blank=True)
    office_hours = models.CharField(_("office hours"), max_length=200, blank=True)
    office_hours_es = models.CharField(_("office hours (Spanish)"), max_length=200, blank=True)

    default_city = models.CharField(
        _("default city"),
        max_length=100,
        blank=True,
        help_text=_("Used when an inventory row has no city (needed for geocoding)."),
    )
    default_state = models.CharField(_("default state"), max_length=2, blank=True)
    default_zip = models.CharField(_("default ZIP code"), max_length=10, blank=True)

    replacement_deadline = models.DateField(
        _("replacement deadline"),
        default=datetime.date(2037, 11, 1),
        help_text=_(
            "Date by which all lead and galvanized-requiring-replacement lines must be replaced."
        ),
    )
    replacement_program = models.TextField(
        _("replacement program"),
        blank=True,
        help_text=_(
            "Who pays, how residents sign up, what to expect. Shown on lead and galvanized results."
        ),
    )
    replacement_program_es = models.TextField(_("replacement program (Spanish)"), blank=True)
    filter_program = models.TextField(
        _("filter program"),
        blank=True,
        help_text=_("Where residents can pick up a free or discounted filter, if you offer one."),
    )
    filter_program_es = models.TextField(_("filter program (Spanish)"), blank=True)
    unknown_program = models.TextField(
        _("plan for unknown lines"),
        blank=True,
        help_text=_("How and when you will identify lines whose material is unknown."),
    )
    unknown_program_es = models.TextField(_("plan for unknown lines (Spanish)"), blank=True)

    map_center_lat = models.FloatField(_("map center latitude"), null=True, blank=True)
    map_center_lon = models.FloatField(_("map center longitude"), null=True, blank=True)
    map_zoom = models.FloatField(_("map zoom"), null=True, blank=True)
    basemap_pmtiles_url = models.CharField(
        _("basemap PMTiles URL"),
        max_length=500,
        blank=True,
        help_text=_(
            "URL of a Protomaps .pmtiles extract of your service area, e.g. "
            "/basemap/area.pmtiles. Leave blank for a map without a basemap."
        ),
    )

    static_form_endpoint = models.URLField(
        _("form endpoint for the static site"),
        blank=True,
        help_text=_(
            "In a static export, forms POST here (for example this server's "
            "/api/submit/ URL or a form service). Blank: forms open an email instead."
        ),
    )

    inventory_updated = models.DateField(_("inventory last updated"), null=True, blank=True)
    demo_mode = models.BooleanField(
        _("demo mode"),
        default=False,
        help_text=_("Shows a banner saying the data is fictional and draws the demo street map."),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("site settings")
        verbose_name_plural = _("site settings")

    def __str__(self) -> str:
        return str(_("Site settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY)

    def delete(self, *args, **kwargs):  # pragma: no cover - the singleton is never deleted
        cache.delete(CACHE_KEY)
        return super().delete(*args, **kwargs)

    @classmethod
    def load(cls) -> SiteConfig:
        config = cache.get(CACHE_KEY)
        if config is None:
            config, _created = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY, config, 300)
        return config

    def localized(self, field: str) -> str:
        """Return ``field`` in the active language, falling back to English."""
        if (get_language() or "en").startswith("es"):
            spanish = getattr(self, f"{field}_es", "")
            if spanish:
                return spanish
        return getattr(self, field)

    @property
    def display_name(self) -> str:
        return self.localized("utility_name")

    @property
    def phone_href(self) -> str:
        digits = "".join(ch for ch in self.phone if ch.isdigit() or ch == "+")
        return f"tel:{digits}" if digits else ""
