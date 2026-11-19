"""What residents send back: inspection requests and photos of their pipe."""

from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from pipetrace.inventory.choices import Material

# Unambiguous characters for reference codes read over the phone (no 0/O, 1/I/L).
_REF_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def make_reference(prefix: str) -> str:
    code = "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))
    return f"{prefix}-{code[:3]}-{code[3:]}"


class Language(models.TextChoices):
    EN = "en", _("English")
    ES = "es", _("Spanish")


class Submission(models.Model):
    """Fields shared by everything a resident can send."""

    reference = models.CharField(_("reference"), max_length=20, unique=True, editable=False)
    service_line = models.ForeignKey(
        "inventory.ServiceLine",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)ss",
        verbose_name=_("service line"),
    )
    address = models.CharField(_("address"), max_length=255)
    name = models.CharField(_("name"), max_length=150, blank=True)
    email = models.EmailField(_("email"), blank=True)
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    language = models.CharField(
        _("language"), max_length=5, choices=Language.choices, default=Language.EN
    )
    created_at = models.DateTimeField(_("received"), auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    staff_notes = models.TextField(_("staff notes"), blank=True)
    via_static_site = models.BooleanField(_("sent from the static site"), default=False)

    reference_prefix = "PT"

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.reference} · {self.address}"

    def save(self, *args, **kwargs):
        if not self.reference:
            model = type(self)
            for _attempt in range(10):
                candidate = make_reference(self.reference_prefix)
                if not model.objects.filter(reference=candidate).exists():
                    self.reference = candidate
                    break
        super().save(*args, **kwargs)

    @property
    def contact(self) -> str:
        return " · ".join(p for p in [self.name, self.phone, self.email] if p)


class InspectionRequest(Submission):
    """A resident asking the utility to come and check their service line."""

    class State(models.TextChoices):
        NEW = "new", _("New")
        CONTACTED = "contacted", _("Contacted")
        SCHEDULED = "scheduled", _("Visit scheduled")
        COMPLETED = "completed", _("Inspected")
        CLOSED = "closed", _("Closed")

    class Relationship(models.TextChoices):
        OWNER = "owner", _("I own the property")
        RENTER = "renter", _("I rent")
        MANAGER = "manager", _("I manage the property")
        OTHER = "other", _("Other")

    class ContactBy(models.TextChoices):
        PHONE = "phone", _("Phone call")
        TEXT = "text", _("Text message")
        EMAIL = "email", _("Email")

    relationship = models.CharField(
        _("relationship to the property"),
        max_length=10,
        choices=Relationship.choices,
        default=Relationship.OWNER,
    )
    contact_by = models.CharField(
        _("preferred contact"), max_length=10, choices=ContactBy.choices, default=ContactBy.PHONE
    )
    best_time = models.CharField(_("best time to reach you"), max_length=150, blank=True)
    message = models.TextField(_("message"), blank=True)
    state = models.CharField(
        _("status"), max_length=20, choices=State.choices, default=State.NEW, db_index=True
    )

    reference_prefix = "IR"

    class Meta(Submission.Meta):
        verbose_name = _("inspection request")
        verbose_name_plural = _("inspection requests")


class PipeCheck(Submission):
    """A resident's own coin-and-magnet check, with a photo, for staff to review."""

    class Scratch(models.TextChoices):
        SILVER = "silver", _("Shiny silver, scratches easily")
        COPPER = "copper", _("Copper colored, like a penny")
        GRAY = "gray", _("Dull gray, hard to scratch")
        PLASTIC = "plastic", _("Plastic (white, black or blue)")
        NOT_SURE = "not_sure", _("I'm not sure")

    class Magnet(models.TextChoices):
        STICKS = "sticks", _("The magnet sticks")
        NO_STICK = "no_stick", _("The magnet does not stick")
        NOT_TESTED = "not_tested", _("I didn't try a magnet")

    class State(models.TextChoices):
        NEW = "new", _("Waiting for review")
        REVIEWED = "reviewed", _("Reviewed")
        NEED_VISIT = "need_visit", _("Needs a site visit")

    photo = models.ImageField(_("photo"), upload_to="pipe-photos/%Y/%m/")
    photo_2 = models.ImageField(_("second photo"), upload_to="pipe-photos/%Y/%m/", blank=True)
    scratch = models.CharField(
        _("scratch test"), max_length=10, choices=Scratch.choices, default=Scratch.NOT_SURE
    )
    magnet = models.CharField(
        _("magnet test"), max_length=10, choices=Magnet.choices, default=Magnet.NOT_TESTED
    )
    notes = models.TextField(_("notes"), blank=True)
    resident_result = models.CharField(
        _("what the guide suggested"),
        max_length=20,
        choices=Material.choices,
        default=Material.UNKNOWN,
    )

    state = models.CharField(
        _("status"), max_length=20, choices=State.choices, default=State.NEW, db_index=True
    )
    staff_material = models.CharField(
        _("material confirmed by staff"), max_length=20, choices=Material.choices, blank=True
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    applied_to_line = models.BooleanField(_("applied to the inventory"), default=False)

    reference_prefix = "PC"

    class Meta(Submission.Meta):
        verbose_name = _("pipe photo")
        verbose_name_plural = _("pipe photos")


def guess_material(scratch: str, magnet: str) -> str:
    """What the coin-and-magnet guide suggests the customer-side pipe is.

    * Lead is soft and dull gray, scratches to shiny silver, and a magnet won't stick.
    * Galvanized steel is dull gray and hard to scratch, and a magnet sticks.
    * Copper scratches to a penny color, and a magnet won't stick.
    """
    if scratch == PipeCheck.Scratch.PLASTIC:
        return Material.PLASTIC
    if scratch == PipeCheck.Scratch.COPPER and magnet != PipeCheck.Magnet.STICKS:
        return Material.COPPER
    if magnet == PipeCheck.Magnet.STICKS:
        return Material.GALVANIZED
    if scratch == PipeCheck.Scratch.SILVER:
        return Material.LEAD
    if scratch == PipeCheck.Scratch.GRAY and magnet == PipeCheck.Magnet.NO_STICK:
        # Gray but not magnetic: most likely lead that hasn't been scratched through.
        return Material.LEAD
    return Material.UNKNOWN
