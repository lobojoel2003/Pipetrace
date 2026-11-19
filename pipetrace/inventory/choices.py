"""Vocabulary for service line inventories.

The four overall classifications follow the federal Lead and Copper Rule
Improvements (40 CFR 141.84): lead, galvanized requiring replacement, non-lead
and lead status unknown.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Status(models.TextChoices):
    """Overall classification of a service line."""

    LEAD = "lead", _("Lead")
    GRR = "grr", _("Galvanized requiring replacement")
    UNKNOWN = "unknown", _("Lead status unknown")
    NON_LEAD = "non_lead", _("Not lead")


#: Order used for legends, summaries and sorting (most urgent first).
STATUS_ORDER = [Status.LEAD, Status.GRR, Status.UNKNOWN, Status.NON_LEAD]

#: Short codes used in compact map/search data files.
STATUS_CODES = {Status.LEAD: "L", Status.GRR: "G", Status.UNKNOWN: "U", Status.NON_LEAD: "N"}

#: Statuses that the federal rule requires to be replaced.
NEEDS_REPLACEMENT = {Status.LEAD, Status.GRR}


class Material(models.TextChoices):
    """Material of one portion (utility side or customer side) of a service line."""

    LEAD = "lead", _("Lead")
    GALVANIZED = "galvanized", _("Galvanized steel")
    COPPER = "copper", _("Copper")
    PLASTIC = "plastic", _("Plastic")
    IRON = "iron", _("Cast or ductile iron")
    OTHER_NON_LEAD = "other_non_lead", _("Other non-lead material")
    NON_LEAD = "non_lead", _("Non-lead (material not recorded)")
    UNKNOWN = "unknown", _("Unknown")


NON_LEAD_MATERIALS = {
    Material.COPPER,
    Material.PLASTIC,
    Material.IRON,
    Material.OTHER_NON_LEAD,
    Material.NON_LEAD,
}


class YesNoUnknown(models.TextChoices):
    YES = "yes", _("Yes")
    NO = "no", _("No")
    UNKNOWN = "unknown", _("Unknown")


class Connector(models.TextChoices):
    """Lead connector (gooseneck, pigtail) between the main and the service line."""

    LEAD = "lead", _("Lead connector")
    NON_LEAD = "non_lead", _("Non-lead connector")
    NONE = "none", _("No connector")
    UNKNOWN = "unknown", _("Connector material unknown")


class Replacement(models.TextChoices):
    NOT_NEEDED = "not_needed", _("Not needed")
    NOT_SCHEDULED = "not_scheduled", _("Not yet scheduled")
    SCHEDULED = "scheduled", _("Scheduled")
    IN_PROGRESS = "in_progress", _("In progress")
    REPLACED = "replaced", _("Replaced")


class GeocodeStatus(models.TextChoices):
    PENDING = "pending", _("Waiting to be located")
    PROVIDED = "provided", _("Coordinates from the inventory file")
    MATCHED = "matched", _("Located by address")
    APPROXIMATE = "approximate", _("Located approximately")
    NO_MATCH = "no_match", _("Address not found")
    MANUAL = "manual", _("Placed by staff")
    SKIPPED = "skipped", _("Not located")
