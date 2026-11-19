"""Service lines and the spreadsheet imports that create them."""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.postgres.indexes import GinIndex
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from pipetrace.inventory import addresses
from pipetrace.inventory.choices import (
    NEEDS_REPLACEMENT,
    STATUS_CODES,
    Connector,
    GeocodeStatus,
    Material,
    Replacement,
    Status,
    YesNoUnknown,
)
from pipetrace.inventory.classification import classify


class ServiceLineQuerySet(models.QuerySet):
    def public(self):
        return self.filter(active=True)

    def needs_replacement(self):
        return self.filter(status__in=NEEDS_REPLACEMENT)


class ServiceLine(models.Model):
    """One service line: the pipe from the water main to a building."""

    public_id = models.SlugField(_("public ID"), max_length=120, unique=True, editable=False)
    source_id = models.CharField(
        _("service line ID"),
        max_length=100,
        blank=True,
        db_index=True,
        help_text=_("The utility's own ID for this line, from the inventory file."),
    )

    # Location
    address = models.CharField(_("street address"), max_length=255)
    unit = models.CharField(_("unit"), max_length=50, blank=True)
    city = models.CharField(_("city"), max_length=100, blank=True)
    state = models.CharField(_("state"), max_length=2, blank=True)
    zip_code = models.CharField(_("ZIP code"), max_length=10, blank=True)
    normalized = models.CharField(max_length=300, db_index=True, editable=False)
    house_number = models.CharField(max_length=20, blank=True, db_index=True, editable=False)
    house_number_int = models.IntegerField(null=True, blank=True, editable=False)
    street_key = models.CharField(max_length=200, blank=True, db_index=True, editable=False)
    street_display = models.CharField(max_length=200, blank=True, editable=False)

    location = models.PointField(_("location"), srid=4326, null=True, blank=True)
    geocode_status = models.CharField(
        _("geocoding"),
        max_length=20,
        choices=GeocodeStatus.choices,
        default=GeocodeStatus.PENDING,
        db_index=True,
    )
    geocode_score = models.FloatField(null=True, blank=True)
    geocode_match = models.CharField(_("matched address"), max_length=300, blank=True)
    geocoded_at = models.DateTimeField(null=True, blank=True)

    # Material
    status = models.CharField(
        _("classification"),
        max_length=20,
        choices=Status.choices,
        default=Status.UNKNOWN,
        db_index=True,
    )
    status_from_file = models.BooleanField(
        default=False,
        editable=False,
        help_text="True when the classification was stated in the inventory file.",
    )
    system_material = models.CharField(
        _("utility-side material"),
        max_length=20,
        choices=Material.choices,
        default=Material.UNKNOWN,
    )
    customer_material = models.CharField(
        _("customer-side material"),
        max_length=20,
        choices=Material.choices,
        default=Material.UNKNOWN,
    )
    downstream_of_lead = models.CharField(
        _("galvanized ever downstream of lead"),
        max_length=10,
        choices=YesNoUnknown.choices,
        blank=True,
    )
    connector = models.CharField(
        _("lead connector"), max_length=10, choices=Connector.choices, blank=True
    )
    basis = models.CharField(_("basis of classification"), max_length=300, blank=True)
    verified_on = models.DateField(_("verified on"), null=True, blank=True)
    installed_year = models.PositiveSmallIntegerField(_("year installed"), null=True, blank=True)
    building_year = models.PositiveSmallIntegerField(_("year built"), null=True, blank=True)

    # Replacement
    replacement = models.CharField(
        _("replacement"),
        max_length=20,
        choices=Replacement.choices,
        default=Replacement.NOT_SCHEDULED,
    )
    scheduled_on = models.DateField(_("scheduled for"), null=True, blank=True)
    scheduled_label = models.CharField(
        _("schedule label"),
        max_length=100,
        blank=True,
        help_text=_('Shown instead of the date, e.g. "Spring 2027" or "Phase 2 (2028)".'),
    )
    replaced_on = models.DateField(_("replaced on"), null=True, blank=True)

    public_note = models.TextField(_("public note"), blank=True)
    public_note_es = models.TextField(_("public note (Spanish)"), blank=True)
    internal_note = models.TextField(_("internal note"), blank=True)
    extra = models.JSONField(
        _("other columns"),
        default=dict,
        blank=True,
        help_text=_("Columns from the inventory file that Pipetrace does not use."),
    )

    active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Lines removed from a later inventory file are kept but hidden."),
    )
    import_batch = models.ForeignKey(
        "inventory.ImportBatch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lines",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ServiceLineQuerySet.as_manager()

    class Meta:
        verbose_name = _("service line")
        verbose_name_plural = _("service lines")
        ordering = ["street_key", "house_number_int", "house_number", "unit"]
        indexes = [
            GinIndex(
                fields=["normalized"], name="line_normalized_trgm", opclasses=["gin_trgm_ops"]
            ),
            models.Index(fields=["active", "status"]),
        ]

    def __str__(self) -> str:
        return self.full_address

    # -- derived fields --------------------------------------------------------
    @property
    def street_line(self) -> str:
        return f"{self.address} {('#' + self.unit) if self.unit else ''}".strip()

    @property
    def full_address(self) -> str:
        locality = " ".join(p for p in [self.state, self.zip_code] if p)
        parts = [self.street_line, self.city, locality]
        return ", ".join(p for p in parts if p)

    @property
    def needs_replacement(self) -> bool:
        return self.status in NEEDS_REPLACEMENT and self.replacement != Replacement.REPLACED

    @property
    def status_code(self) -> str:
        return STATUS_CODES[Status(self.status)]

    @property
    def lat(self) -> float | None:
        return self.location.y if self.location else None

    @property
    def lon(self) -> float | None:
        return self.location.x if self.location else None

    def derived_status(self) -> Status:
        return classify(self.system_material, self.customer_material, self.downstream_of_lead)

    def refresh_derived(self) -> None:
        """Recompute search keys, slug and (unless stated in the file) the status."""
        parsed = addresses.parse(self.address)
        self.normalized = addresses.normalize(self.street_line)[:300]
        self.house_number = parsed.house_number[:20]
        self.house_number_int = parsed.house_number_int
        self.street_key = parsed.street[:200]
        self.street_display = addresses.display_street(self.address)[:200]
        if not self.status_from_file:
            self.status = self.derived_status()
        if self.replacement == Replacement.REPLACED:
            # A replaced line is no longer lead, whatever the old record said.
            self.status = Status.NON_LEAD
            if not self.replaced_on:
                self.replaced_on = timezone.localdate()
        if self.status == Status.NON_LEAD and self.replacement in {
            Replacement.NOT_SCHEDULED,
            "",
        }:
            self.replacement = Replacement.NOT_NEEDED
        if not self.public_id:
            self.public_id = make_public_id(self.source_id, self.street_line, self.city)

    def save(self, *args, **kwargs):
        self.refresh_derived()
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("residents:line", kwargs={"public_id": self.public_id})

    def localized_note(self, language: str) -> str:
        if language.startswith("es") and self.public_note_es:
            return self.public_note_es
        return self.public_note


def make_public_id(source_id: str, street_line: str, city: str = "") -> str:
    """Readable, stable URL slug: ``214-maple-st-3f9a2b``.

    The hash comes from the utility's line ID when there is one (so the URL survives
    an address correction), otherwise from the address itself.
    """
    key = (source_id or f"{street_line}|{city}").strip().lower()
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:6]
    slug = slugify(street_line)[:100].strip("-") or "line"
    return f"{slug}-{digest}"


class ImportBatch(models.Model):
    """One uploaded inventory spreadsheet and the mapping used to read it."""

    class State(models.TextChoices):
        UPLOADED = "uploaded", _("Uploaded")
        MAPPED = "mapped", _("Columns mapped")
        COMMITTED = "committed", _("Imported")
        FAILED = "failed", _("Failed")

    class Mode(models.TextChoices):
        MERGE = "merge", _("Update matching lines and add new ones")
        REPLACE = "replace", _("Replace the whole inventory")

    file = models.FileField(_("file"), upload_to="imports/%Y/%m/")
    original_name = models.CharField(_("file name"), max_length=255)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=20, choices=State.choices, default=State.UPLOADED)
    mode = models.CharField(
        _("import mode"), max_length=10, choices=Mode.choices, default=Mode.MERGE
    )

    sheet_name = models.CharField(_("sheet"), max_length=100, blank=True)
    header_row = models.PositiveIntegerField(_("header row"), default=1)
    data_start_row = models.PositiveIntegerField(_("first data row"), default=2)
    columns = models.JSONField(default=list, blank=True)
    header_signature = models.CharField(max_length=64, blank=True, db_index=True)
    column_map = models.JSONField(default=dict, blank=True)
    value_map = models.JSONField(default=dict, blank=True)

    stats = models.JSONField(default=dict, blank=True)
    messages = models.JSONField(default=list, blank=True)
    committed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("inventory import")
        verbose_name_plural = _("inventory imports")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.original_name} ({self.created_at:%Y-%m-%d})"

    def get_absolute_url(self) -> str:
        return reverse("staff:import_detail", kwargs={"pk": self.pk})
