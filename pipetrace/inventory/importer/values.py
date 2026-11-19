"""Turn the many ways spreadsheets spell things into Pipetrace's vocabulary."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from pipetrace.inventory.choices import (
    Connector,
    Material,
    Replacement,
    Status,
    YesNoUnknown,
)
from pipetrace.inventory.importer import fields as F


@dataclass(frozen=True)
class Interpretation:
    """How a raw cell value was understood."""

    value: str | None  # canonical value, or None for blank / not recognised
    recognized: bool = True
    ambiguous: bool = False


BLANK = Interpretation(None)
UNRECOGNIZED = Interpretation(None, recognized=False)

_BLANK_WORDS = {"", "n a", "na", "null", "nan", "none given", "blank", "not applicable"}
_UNKNOWN_WORDS = {
    "unknown",
    "unk",
    "u",
    "lsu",
    "lu",
    "lead status unknown",
    "status unknown",
    "unknown material",
    "material unknown",
    "tbd",
    "to be determined",
    "not known",
    "undetermined",
    "unverified",
    "unknown unknown",
    "not verified",
    "pending",
    "un",
    "unknown lead status",
    "lead status unknown u",
    "unknown u",
    "u unknown",
    "lead status unknown lsu",
    "unkn",
    "unknwn",
}
_MAYBE_LEAD = {
    "likely lead",
    "suspected lead",
    "potential lead",
    "possible lead",
    "probable lead",
    "potentially lead",
    "unknown likely lead",
    "unknown suspected lead",
    "lead suspected",
    "likely lead unknown",
}
_NOT_LEAD_PHRASES = ("non lead", "nonlead", "not lead", "no lead", "lead free", "non lsl")

_MATERIAL_WORDS: list[tuple[str, tuple[str, ...]]] = [
    (Material.COPPER, ("copper", "cu", "type k", "k copper", "type l copper", "cooper")),
    (
        Material.PLASTIC,
        (
            "plastic",
            "pvc",
            "cpvc",
            "pe",
            "hdpe",
            "ldpe",
            "mdpe",
            "pex",
            "polyethylene",
            "polybutylene",
            "poly",
            "abs",
            "ctspe",
            "cts pe",
            "polyvinyl",
            "pp",
        ),
    ),
    (
        Material.IRON,
        ("cast iron", "ductile iron", "ductile", "ci", "di", "dip", "cip", "iron", "cast"),
    ),
    (
        Material.OTHER_NON_LEAD,
        (
            "brass",
            "asbestos cement",
            "ac",
            "transite",
            "concrete",
            "black steel",
            "stainless",
            "stainless steel",
            "steel",
            "other",
            "other non lead",
            "wrought iron",
            "bronze",
            "cement",
        ),
    ),
]
_SHORT_CODES = {
    "l": Material.LEAD,
    "pb": Material.LEAD,
    "lsl": Material.LEAD,
    "ld": Material.LEAD,
    "g": Material.GALVANIZED,
    "gs": Material.GALVANIZED,
    "gi": Material.GALVANIZED,
    "galv": Material.GALVANIZED,
    "grr": Material.GALVANIZED,
    "gal": Material.GALVANIZED,
    "c": Material.COPPER,
    "cu": Material.COPPER,
    "p": Material.PLASTIC,
    "nl": Material.NON_LEAD,
    "n": Material.NON_LEAD,
    "non": Material.NON_LEAD,
}
#: Codes that mean different things in different files; staff should confirm them.
_AMBIGUOUS = {"pb", "g", "c", "p", "n", "pp", "cast", "steel", "poly"}


def clean(raw: str) -> str:
    text = (raw or "").lower().replace("–", "-").replace("—", "-")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _has(text: str, word: str) -> bool:
    return re.search(rf"(?:^| ){re.escape(word)}(?: |$)", text) is not None


def _question(raw: str) -> bool:
    return bool(raw) and set(raw.strip()) <= {"?"}


def interpret_material(raw: str) -> Interpretation:
    if _question(raw):
        return Interpretation(Material.UNKNOWN)
    text = clean(raw)
    if text in _BLANK_WORDS:
        return BLANK
    if text in _MAYBE_LEAD:
        return Interpretation(Material.UNKNOWN, ambiguous=True)
    if text in _UNKNOWN_WORDS or text.startswith("unknown") or _has(text, "unknown"):
        return Interpretation(Material.UNKNOWN)
    if text in _SHORT_CODES:
        return Interpretation(_SHORT_CODES[text], ambiguous=text in _AMBIGUOUS)
    if "lead lined" in text or "lead lined galvanized" in text:
        return Interpretation(Material.LEAD)
    if "requiring replacement" in text or _has(text, "grr"):
        return Interpretation(Material.GALVANIZED)
    not_lead = any(p in text for p in _NOT_LEAD_PHRASES) or text.startswith("nl ")
    if not not_lead and (_has(text, "lead") or _has(text, "lsl") or text == "lead pipe"):
        if "assumed" in text or "presumed" in text:
            return Interpretation(Material.LEAD, ambiguous=True)
        return Interpretation(Material.LEAD)
    if "galv" in text:
        return Interpretation(Material.GALVANIZED)
    for material, words in _MATERIAL_WORDS:
        for word in words:
            if _has(text, word):
                return Interpretation(material, ambiguous=word in _AMBIGUOUS)
    if not_lead:
        return Interpretation(Material.NON_LEAD)
    if text in {"no", "none"}:
        return Interpretation(Material.NON_LEAD, ambiguous=True)
    return UNRECOGNIZED


def interpret_status(raw: str) -> Interpretation:
    if _question(raw):
        return Interpretation(Status.UNKNOWN)
    text = clean(raw)
    if text in _BLANK_WORDS:
        return BLANK
    if text in {"y", "yes", "true", "x"}:
        # A "Lead service line?" column answered yes.
        return Interpretation(Status.LEAD, ambiguous=True)
    if text in {
        "grr",
        "g",
        "galvanized requiring replacement",
        "galv requiring replacement",
        "galvanized requiring replacement grr",
        "grr galvanized requiring replacement",
    }:
        return Interpretation(Status.GRR)
    material = interpret_material(raw)
    if not material.recognized or material.value is None:
        return material
    status = {
        Material.LEAD: Status.LEAD,
        Material.GALVANIZED: Status.GRR,
        Material.UNKNOWN: Status.UNKNOWN,
    }.get(material.value, Status.NON_LEAD)
    return Interpretation(status, ambiguous=material.ambiguous)


def interpret_yes_no(raw: str) -> Interpretation:
    if _question(raw):
        return Interpretation(YesNoUnknown.UNKNOWN)
    text = clean(raw)
    if text in _BLANK_WORDS:
        return BLANK
    if text in {"y", "yes", "true", "t", "1", "x", "si"} or text.startswith("yes"):
        return Interpretation(YesNoUnknown.YES)
    if text in {"n", "no", "false", "f", "0", "never", "not"} or text.startswith("no "):
        return Interpretation(YesNoUnknown.NO)
    if text in _UNKNOWN_WORDS or "unknown" in text:
        return Interpretation(YesNoUnknown.UNKNOWN)
    return UNRECOGNIZED


def interpret_connector(raw: str) -> Interpretation:
    if _question(raw):
        return Interpretation(Connector.UNKNOWN)
    text = clean(raw)
    if text in _BLANK_WORDS:
        return BLANK
    if text in {
        "none",
        "no connector",
        "not present",
        "none present",
        "no gooseneck",
        "no connector present",
        "absent",
    }:
        return Interpretation(Connector.NONE)
    if text in _UNKNOWN_WORDS or "unknown" in text:
        return Interpretation(Connector.UNKNOWN)
    if text in {"n", "no", "false", "0"} or any(p in text for p in _NOT_LEAD_PHRASES):
        return Interpretation(Connector.NON_LEAD)
    if text in {"y", "yes", "true", "1", "x"} or _has(text, "lead") or text in {"l", "pb"}:
        return Interpretation(Connector.LEAD)
    material = interpret_material(raw)
    if material.value and material.value not in {Material.LEAD, Material.UNKNOWN}:
        return Interpretation(Connector.NON_LEAD)
    return UNRECOGNIZED


def interpret_replacement(raw: str) -> Interpretation:
    text = clean(raw)
    if text in _BLANK_WORDS:
        return BLANK
    if text in {"not needed", "not required", "n a", "no replacement needed"}:
        return Interpretation(Replacement.NOT_NEEDED)
    if any(w in text for w in ("not scheduled", "unscheduled", "not started", "not planned")):
        return Interpretation(Replacement.NOT_SCHEDULED)
    if any(
        w in text
        for w in ("in progress", "under construction", "started", "partial", "underway", "ongoing")
    ):
        return Interpretation(Replacement.IN_PROGRESS)
    if any(w in text for w in ("replaced", "complete", "completed", "done", "finished")) or (
        text in {"yes", "y", "true", "1", "x"}
    ):
        return Interpretation(Replacement.REPLACED)
    if any(w in text for w in ("scheduled", "planned", "pending", "upcoming", "queued")):
        return Interpretation(Replacement.SCHEDULED)
    if text in {"no", "n", "false", "0", "none"}:
        return Interpretation(Replacement.NOT_SCHEDULED)
    return UNRECOGNIZED


INTERPRETERS = {
    F.MATERIAL: interpret_material,
    F.STATUS: interpret_status,
    F.YES_NO: interpret_yes_no,
    F.CONNECTOR: interpret_connector,
    F.REPLACEMENT: interpret_replacement,
}

CHOICES = {
    F.MATERIAL: Material.choices,
    F.STATUS: Status.choices,
    F.YES_NO: YesNoUnknown.choices,
    F.CONNECTOR: Connector.choices,
    F.REPLACEMENT: Replacement.choices,
}


def value_key(raw: str) -> str:
    """Key used to store per-value overrides from the value-mapping screen."""
    return " ".join((raw or "").strip().lower().split())


# --- Dates, years, numbers --------------------------------------------------------
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
_SEASONS = {
    "spring": 4,
    "summer": 7,
    "fall": 10,
    "autumn": 10,
    "winter": 1,
    "primavera": 4,
    "verano": 7,
    "otono": 10,
    "invierno": 1,
}


def parse_date(raw: str) -> dt.date | None:
    text = (raw or "").strip()
    if not text:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", text)
    if m:
        y, mo, d = map(int, m.groups())
        return _safe_date(y, mo, d)
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", text)
    if m:
        mo, d, y = map(int, m.groups())
        if y < 100:
            y += 2000 if y < 70 else 1900
        return _safe_date(y, mo, d)
    m = re.fullmatch(r"([A-Za-z]{3,})\.? (\d{1,2}),? (\d{4})", text)
    if m and m.group(1)[:3].lower() in _MONTHS:
        return _safe_date(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    m = re.fullmatch(r"([A-Za-z]{3,})\.?,? (\d{4})", text)
    if m and m.group(1)[:3].lower() in _MONTHS:
        return _safe_date(int(m.group(2)), _MONTHS[m.group(1)[:3].lower()], 1)
    m = re.fullmatch(r"(\d{4})", text)
    if m and 1800 <= int(text) <= 2100:
        return dt.date(int(text), 1, 1)
    # Excel serial date that arrived as text.
    if re.fullmatch(r"\d{5}(\.0)?", text):
        serial = int(float(text))
        if 20000 < serial < 80000:
            return dt.date(1899, 12, 30) + dt.timedelta(days=serial)
    return None


def _safe_date(y: int, mo: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def parse_year(raw: str) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    m = re.search(r"\b(1[89]\d{2}|20\d{2}|2100)\b", text)
    if m:
        return int(m.group(1))
    date = parse_date(text)
    return date.year if date else None


def parse_schedule(raw: str) -> tuple[dt.date | None, str]:
    """Return ``(date, label)`` for a schedule cell.

    A full date gives just the date. Anything vaguer ("2027", "Spring 2027",
    "Q3 2028", "Phase 2") keeps its text as the label, with an approximate date
    when a year can be found so lines can still be sorted and counted.
    """
    text = " ".join((raw or "").split())
    if not text:
        return None, ""
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}.*|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", text):
        return parse_date(text), ""
    year = parse_year(text)
    if year is None:
        return None, text[:100]
    lower = clean(text)
    month = 1
    for season, start in _SEASONS.items():
        if season in lower:
            month = start
    m = re.search(r"\bq([1-4])\b", lower)
    if m:
        month = (int(m.group(1)) - 1) * 3 + 1
    for name, number in _MONTHS.items():
        if re.search(rf"\b{name}[a-z]*\b", lower):
            month = number
    return dt.date(year, month, 1), text[:100]


def parse_float(raw: str) -> float | None:
    text = (raw or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*°?\s*([NSEW])", text, re.I)
        if m:
            value = float(m.group(1))
            return -value if m.group(2).upper() in {"S", "W"} else value
        return None


def parse_zip(raw: str) -> str:
    text = (raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if not digits:
        return ""
    if len(digits) == 9:
        return f"{digits[:5]}-{digits[5:]}"
    if len(digits) in (3, 4) and text.isdigit():
        # Excel stored the ZIP as a number and dropped its leading zeros (e.g. 2134).
        return digits.zfill(5)
    return digits[:5]


STATES = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "puerto rico": "PR",
    "guam": "GU",
    "american samoa": "AS",
    "us virgin islands": "VI",
    "virgin islands": "VI",
    "northern mariana islands": "MP",
}


def parse_state(raw: str) -> str:
    text = (raw or "").strip()
    if len(text) == 2 and text.isalpha():
        return text.upper()
    return STATES.get(clean(text), text[:2].upper() if text else "")
