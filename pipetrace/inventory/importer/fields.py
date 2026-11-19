"""The fields Pipetrace can read from an inventory file, and how to recognise them.

Header recognition covers the field names in EPA's service line inventory
template (location identifier, system-owned and customer-owned portion material,
entire service line classification, basis of classification, lead connector,
"ever downstream of lead"...) plus the many variants found in state templates and
home-grown spreadsheets. Anything not recognised can be mapped by hand on the
column-mapping screen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _

# Field kinds
TEXT = "text"
MATERIAL = "material"
STATUS = "status"
YES_NO = "yes_no"
CONNECTOR = "connector"
REPLACEMENT = "replacement"
DATE = "date"
YEAR = "year"
SCHEDULE = "schedule"
LATITUDE = "latitude"
LONGITUDE = "longitude"
ZIP = "zip"
STATE = "state"

#: Kinds whose values are mapped to a fixed vocabulary on the value-mapping screen.
ENUM_KINDS = {MATERIAL, STATUS, YES_NO, CONNECTOR, REPLACEMENT}

SYSTEM_WORDS = {"system", "utility", "public", "pws", "supplier", "municipal", "district"}
CUSTOMER_WORDS = {
    "customer",
    "cust",
    "private",
    "owner",
    "property",
    "house",
    "home",
    "building",
    "resident",
    "consumer",
}
HISTORY_WORDS = {
    "ever",
    "previously",
    "previous",
    "history",
    "historic",
    "upstream",
    "downstream",
    "former",
    "formerly",
}
META_WORDS = {
    "date",
    "year",
    "basis",
    "method",
    "verified",
    "verification",
    "install",
    "installed",
    "installation",
    "source",
    "diameter",
    "size",
    "connector",
    "gooseneck",
    "pigtail",
    "notes",
    "comment",
    "comments",
    "confidence",
    "how",
    "evidence",
    "inspection",
    "length",
    "depth",
}
MAILING_WORDS = {"mailing", "billing", "mail", "owner", "postal", "remit"}


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    kind: str = TEXT
    help: str = ""
    synonyms: tuple[str, ...] = ()
    #: Matched only when the whole header equals one of these (for short/ambiguous names).
    exact: tuple[str, ...] = ()
    #: Header (with its group label) must contain a word from each of these sets.
    need_any: tuple[frozenset[str], ...] = ()
    #: Header containing any of these words is not this field.
    avoid: frozenset[str] = field(default_factory=frozenset)
    group: str = ""


FIELDS: list[FieldSpec] = [
    FieldSpec(
        "source_id",
        _("Service line ID"),
        group="location",
        help=_(
            "The utility's own ID for the line. Used to match lines when you upload an "
            "updated file. Optional."
        ),
        synonyms=(
            "service line id",
            "service line identifier",
            "service line number",
            "sl id",
            "line id",
            "service id",
            "service connection id",
            "connection id",
            "account number",
            "account no",
            "account id",
            "acct no",
            "acct number",
            "premise id",
            "premise number",
            "location id",
            "asset id",
            "facility id",
            "inventory id",
            "record id",
            "unique id",
            "gis id",
            "service number",
            "service line no",
        ),
        exact=("id", "slid", "acct", "account", "objectid", "premise", "sl no", "sl number"),
        avoid=frozenset({"meter", "parcel", "pin", "tax"}),
    ),
    FieldSpec(
        "address",
        _("Street address"),
        group="location",
        help=_(
            "House number and street, e.g. 214 Maple St. Required unless you map house "
            "number and street name separately."
        ),
        synonyms=(
            "location identifier",
            "street address",
            "service address",
            "property address",
            "site address",
            "premise address",
            "location address",
            "address line 1",
            "address 1",
            "physical address",
            "full address",
            "service location",
            "service line address",
            "address",
            "location street address",
            "service addr",
            "svc address",
            "svc addr",
            "site addr",
            "location addr",
            "property addr",
            "street addr",
            "premise addr",
            "service location address",
        ),
        exact=("location", "addr", "situs", "situs address"),
        avoid=frozenset({"email", "city", "zip", "state", "number", "unit"} | MAILING_WORDS),
    ),
    FieldSpec(
        "house_number",
        _("House number"),
        group="location",
        help=_("Only if the house number is in its own column."),
        synonyms=(
            "house number",
            "house no",
            "house num",
            "street number",
            "street no",
            "address number",
            "addr number",
            "addr no",
            "hse no",
            "building number",
        ),
        exact=("number", "no", "st no", "st num", "num"),
        avoid=frozenset({"account", "phone"}),
    ),
    FieldSpec(
        "street_name",
        _("Street name"),
        group="location",
        help=_("Only if the street name is in its own column."),
        synonyms=("street name", "st name", "road name", "street name full", "full street name"),
        exact=("street", "road"),
        avoid=frozenset({"address", "number"}),
    ),
    FieldSpec(
        "unit",
        _("Unit or apartment"),
        group="location",
        synonyms=(
            "unit number",
            "unit no",
            "apartment number",
            "apt number",
            "apt no",
            "suite number",
        ),
        exact=("unit", "apt", "apartment", "suite", "ste"),
    ),
    FieldSpec(
        "city",
        _("City"),
        group="location",
        synonyms=(
            "city",
            "town",
            "municipality",
            "locality",
            "city town",
            "city name",
            "service city",
            "community",
            "village",
        ),
        avoid=frozenset(MAILING_WORDS),
    ),
    FieldSpec(
        "state",
        _("State"),
        STATE,
        group="location",
        synonyms=("state", "state code", "state abbreviation"),
        exact=("st",),
        avoid=frozenset(MAILING_WORDS | {"status"}),
    ),
    FieldSpec(
        "zip_code",
        _("ZIP code"),
        ZIP,
        group="location",
        synonyms=("zip", "zip code", "zipcode", "postal code", "postcode", "zip5", "zip 5"),
        avoid=frozenset(MAILING_WORDS - {"postal"}),
    ),
    FieldSpec(
        "latitude",
        _("Latitude"),
        LATITUDE,
        group="location",
        help=_("Decimal degrees (WGS 84). Lines with coordinates are not geocoded."),
        synonyms=(
            "latitude",
            "lat dd",
            "gps latitude",
            "y coordinate",
            "y coord",
            "point y",
            "lat decimal",
        ),
        exact=("lat", "y"),
    ),
    FieldSpec(
        "longitude",
        _("Longitude"),
        LONGITUDE,
        group="location",
        synonyms=(
            "longitude",
            "long dd",
            "gps longitude",
            "x coordinate",
            "x coord",
            "point x",
            "lon decimal",
        ),
        exact=("lon", "lng", "long", "x"),
    ),
    FieldSpec(
        "system_material",
        _("Utility-side material"),
        MATERIAL,
        group="material",
        help=_("Material of the system-owned (utility) portion."),
        synonyms=(
            "system owned portion material",
            "system owned material",
            "system material",
            "utility side material",
            "utility owned material",
            "public side material",
            "material classification",
            "service line material",
            "material",
            "pipe material",
            "system side",
            "utility side",
            "public side",
            "system owned portion",
            "utility owned portion",
            "pws owned portion",
            "main to curb",
        ),
        need_any=(frozenset(SYSTEM_WORDS | {"main"}),),
        avoid=frozenset(HISTORY_WORDS | META_WORDS | CUSTOMER_WORDS | {"entire", "overall"}),
    ),
    FieldSpec(
        "customer_material",
        _("Customer-side material"),
        MATERIAL,
        group="material",
        help=_("Material of the customer-owned (private) portion."),
        synonyms=(
            "customer owned portion material",
            "customer owned material",
            "customer material",
            "customer side material",
            "private side material",
            "owner side material",
            "material classification",
            "service line material",
            "material",
            "pipe material",
            "customer side",
            "private side",
            "owner side",
            "customer owned portion",
            "private portion",
            "curb to house",
            "cust side",
            "cust material",
            "cust side material",
        ),
        need_any=(frozenset(CUSTOMER_WORDS),),
        avoid=frozenset(
            HISTORY_WORDS | META_WORDS | {"system", "utility", "public", "entire", "overall"}
        ),
    ),
    FieldSpec(
        "status",
        _("Overall classification"),
        STATUS,
        group="material",
        help=_(
            "Lead, galvanized requiring replacement, non-lead or lead status unknown. If "
            "you leave this unmapped, Pipetrace works it out from the two portions."
        ),
        synonyms=(
            "entire service line material classification",
            "service line material classification",
            "entire service line classification",
            "service line classification",
            "overall classification",
            "material classification",
            "lead status",
            "service line category",
            "sl category",
            "inventory classification",
            "lcri classification",
            "lcrr classification",
            "classification",
            "service line status",
            "lead service line status",
            "lsl status",
            "overall material",
            "entire service line material",
            "lead service line",
            "lsl y n",
            "is lead",
            "lead line",
        ),
        exact=("lsl", "lead", "lsl status", "status"),
        avoid=frozenset(
            SYSTEM_WORDS
            | CUSTOMER_WORDS
            | HISTORY_WORDS
            | {"basis", "method", "date", "replacement", "replaced", "connector"}
        ),
    ),
    FieldSpec(
        "downstream_of_lead",
        _("Galvanized ever downstream of lead?"),
        YES_NO,
        group="material",
        help=_(
            "Yes / No / Unknown. A galvanized line is treated as needing replacement unless "
            "this says No."
        ),
        synonyms=(
            "ever downstream of lead",
            "galvanized ever downstream of lead",
            "downstream of lead",
            "ever downstream of a lead",
            "ever previously lead",
            "previously lead",
            "ever lead",
            "was ever lead",
            "lead upstream",
            "upstream lead",
            "ever been lead",
            "lead ever present",
        ),
    ),
    FieldSpec(
        "connector",
        _("Lead connector"),
        CONNECTOR,
        group="material",
        help=_("Whether a lead gooseneck, pigtail or connector is present."),
        synonyms=(
            "lead connector",
            "connector material",
            "gooseneck",
            "pigtail",
            "lead gooseneck",
            "gooseneck pigtail",
            "connector",
            "lead pigtail",
            "lead connector present",
        ),
    ),
    FieldSpec(
        "basis",
        _("Basis of classification"),
        group="material",
        help=_("How the material was determined (records, field inspection, ...)."),
        synonyms=(
            "basis of classification",
            "basis of material classification",
            "basis for classification",
            "classification basis",
            "verification method",
            "method of verification",
            "how classified",
            "source of information",
            "information source",
            "data source",
            "classification method",
            "basis",
            "identification method",
            "method of identification",
        ),
    ),
    FieldSpec(
        "verified_on",
        _("Date verified"),
        DATE,
        group="material",
        synonyms=(
            "date verified",
            "verification date",
            "date of verification",
            "inspection date",
            "date inspected",
            "field verification date",
            "verified date",
            "date of field verification",
            "date of inspection",
            "verified on",
        ),
    ),
    FieldSpec(
        "installed_year",
        _("Year installed"),
        YEAR,
        group="material",
        synonyms=(
            "installation date",
            "install date",
            "year installed",
            "install year",
            "date installed",
            "service installation date",
            "installed",
            "installation year",
        ),
    ),
    FieldSpec(
        "building_year",
        _("Year built"),
        YEAR,
        group="material",
        synonyms=(
            "year built",
            "building year",
            "construction year",
            "year of construction",
            "building construction date",
            "date built",
            "structure year built",
            "construction date",
            "built",
        ),
    ),
    FieldSpec(
        "replacement",
        _("Replacement status"),
        REPLACEMENT,
        group="replacement",
        synonyms=(
            "replacement status",
            "lslr status",
            "lsl replacement status",
            "status of replacement",
            "replacement complete",
            "replaced",
            "work status",
            "replacement",
            "replacement progress",
        ),
        avoid=frozenset({"date", "year", "planned", "scheduled", "schedule", "phase", "cost"}),
    ),
    FieldSpec(
        "scheduled",
        _("Scheduled replacement"),
        SCHEDULE,
        group="replacement",
        help=_('A date, a year, or text like "Spring 2027" or "Phase 2".'),
        synonyms=(
            "scheduled replacement",
            "scheduled replacement date",
            "planned replacement",
            "planned replacement date",
            "replacement schedule",
            "target replacement date",
            "scheduled date",
            "planned year",
            "replacement year",
            "projected replacement",
            "anticipated replacement",
            "replacement phase",
            "phase",
            "planned date",
            "target date",
            "schedule",
            "sched date",
        ),
        exact=("sched", "scheduled"),
    ),
    FieldSpec(
        "replaced_on",
        _("Date replaced"),
        DATE,
        group="replacement",
        synonyms=(
            "replacement date",
            "date replaced",
            "replaced date",
            "date of replacement",
            "replacement completed date",
            "replacement completion date",
            "completed date",
            "date completed",
        ),
    ),
    FieldSpec(
        "public_note",
        _("Public note"),
        group="other",
        help=_("Shown to residents on the line's page."),
        synonyms=("public notes", "public note", "notes for residents", "public comments"),
        exact=("notes", "note", "comments", "comment", "remarks"),
    ),
]

FIELDS_BY_KEY = {f.key: f for f in FIELDS}

FIELD_GROUPS = [
    ("location", _("Where the line is")),
    ("material", _("What it is made of")),
    ("replacement", _("Replacement")),
    ("other", _("Other")),
]
