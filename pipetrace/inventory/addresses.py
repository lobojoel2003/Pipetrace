"""Address normalisation and fuzzy matching.

Residents type addresses many ways ("214 Maple Street", "214 maple st.",
"214 MAPLE ST APT 2"). Normalising both the inventory and the query to USPS
Publication 28 abbreviations lets a simple token comparison find the right line.

The same tables are shipped to the browser in the static export
(:func:`search_config`), so the client-side search in ``search.js`` behaves
exactly like the server.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

SUFFIXES = {
    "ALLEY": "ALY",
    "ALLY": "ALY",
    "ANNEX": "ANX",
    "ARCADE": "ARC",
    "AVENUE": "AVE",
    "AVEN": "AVE",
    "AVENU": "AVE",
    "AVN": "AVE",
    "AVNUE": "AVE",
    "AV": "AVE",
    "BAYOU": "BYU",
    "BEACH": "BCH",
    "BEND": "BND",
    "BLUFF": "BLF",
    "BOULEVARD": "BLVD",
    "BOUL": "BLVD",
    "BOULV": "BLVD",
    "BRANCH": "BR",
    "BRIDGE": "BRG",
    "BROOK": "BRK",
    "BYPASS": "BYP",
    "CAUSEWAY": "CSWY",
    "CENTER": "CTR",
    "CENTRE": "CTR",
    "CIRCLE": "CIR",
    "CIRC": "CIR",
    "CIRCL": "CIR",
    "CLIFF": "CLF",
    "CLUB": "CLB",
    "COMMON": "CMN",
    "CORNER": "COR",
    "COURSE": "CRSE",
    "COURT": "CT",
    "COVE": "CV",
    "CREEK": "CRK",
    "CRESCENT": "CRES",
    "CREST": "CRST",
    "CROSSING": "XING",
    "CROSSROAD": "XRD",
    "CURVE": "CURV",
    "DALE": "DL",
    "DAM": "DM",
    "DIVIDE": "DV",
    "DRIVE": "DR",
    "DRIV": "DR",
    "DRV": "DR",
    "ESTATE": "EST",
    "ESTATES": "ESTS",
    "EXPRESSWAY": "EXPY",
    "EXTENSION": "EXT",
    "FALLS": "FLS",
    "FERRY": "FRY",
    "FIELD": "FLD",
    "FIELDS": "FLDS",
    "FLAT": "FLT",
    "FOREST": "FRST",
    "FORGE": "FRG",
    "FORK": "FRK",
    "FORT": "FT",
    "FREEWAY": "FWY",
    "GARDEN": "GDN",
    "GARDENS": "GDNS",
    "GATEWAY": "GTWY",
    "GLEN": "GLN",
    "GREEN": "GRN",
    "GROVE": "GRV",
    "HARBOR": "HBR",
    "HAVEN": "HVN",
    "HEIGHTS": "HTS",
    "HIGHWAY": "HWY",
    "HIGHWY": "HWY",
    "HIWAY": "HWY",
    "HILL": "HL",
    "HILLS": "HLS",
    "HOLLOW": "HOLW",
    "INLET": "INLT",
    "ISLAND": "IS",
    "JUNCTION": "JCT",
    "KNOLL": "KNL",
    "LAKE": "LK",
    "LAKES": "LKS",
    "LANDING": "LNDG",
    "LANE": "LN",
    "LIGHT": "LGT",
    "LOCK": "LCK",
    "LODGE": "LDG",
    "MANOR": "MNR",
    "MEADOW": "MDW",
    "MEADOWS": "MDWS",
    "MILL": "ML",
    "MISSION": "MSN",
    "MOTORWAY": "MTWY",
    "MOUNT": "MT",
    "MOUNTAIN": "MTN",
    "ORCHARD": "ORCH",
    "OVERPASS": "OPAS",
    "PARKWAY": "PKWY",
    "PARKWY": "PKWY",
    "PASSAGE": "PSGE",
    "PINE": "PNE",
    "PINES": "PNES",
    "PLACE": "PL",
    "PLAIN": "PLN",
    "PLAINS": "PLNS",
    "PLAZA": "PLZ",
    "POINT": "PT",
    "PORT": "PRT",
    "PRAIRIE": "PR",
    "RANCH": "RNCH",
    "RIDGE": "RDG",
    "RIVER": "RIV",
    "ROAD": "RD",
    "ROUTE": "RTE",
    "SHORE": "SHR",
    "SHORES": "SHRS",
    "SKYWAY": "SKWY",
    "SPRING": "SPG",
    "SPRINGS": "SPGS",
    "SQUARE": "SQ",
    "STATION": "STA",
    "STREAM": "STRM",
    "STREET": "ST",
    "STR": "ST",
    "STRT": "ST",
    "SUMMIT": "SMT",
    "TERRACE": "TER",
    "TERR": "TER",
    "TRACE": "TRCE",
    "TRAIL": "TRL",
    "TRAILS": "TRL",
    "TUNNEL": "TUNL",
    "TURNPIKE": "TPKE",
    "UNION": "UN",
    "VALLEY": "VLY",
    "VIADUCT": "VIA",
    "VIEW": "VW",
    "VILLAGE": "VLG",
    "VILLE": "VL",
    "VISTA": "VIS",
    "WALK": "WALK",
    "WELL": "WL",
    "WELLS": "WLS",
}

DIRECTIONALS = {
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
    "NORTHEAST": "NE",
    "NORTHWEST": "NW",
    "SOUTHEAST": "SE",
    "SOUTHWEST": "SW",
    "NORTE": "N",
    "SUR": "S",
    "ESTE": "E",
    "OESTE": "W",
}

ORDINALS = {
    "FIRST": "1ST",
    "SECOND": "2ND",
    "THIRD": "3RD",
    "FOURTH": "4TH",
    "FIFTH": "5TH",
    "SIXTH": "6TH",
    "SEVENTH": "7TH",
    "EIGHTH": "8TH",
    "NINTH": "9TH",
    "TENTH": "10TH",
    "ELEVENTH": "11TH",
    "TWELFTH": "12TH",
    "THIRTEENTH": "13TH",
    "FOURTEENTH": "14TH",
    "FIFTEENTH": "15TH",
    "SIXTEENTH": "16TH",
    "SEVENTEENTH": "17TH",
    "EIGHTEENTH": "18TH",
    "NINETEENTH": "19TH",
    "TWENTIETH": "20TH",
}

UNIT_WORDS = {
    "APARTMENT": "#",
    "APT": "#",
    "UNIT": "#",
    "SUITE": "#",
    "STE": "#",
    "NO": "#",
    "NUM": "#",
    "NUMBER": "#",
    "LOT": "#",
    "SPACE": "#",
    "SPC": "#",
    "RM": "#",
    "ROOM": "#",
    "FL": "#",
    "FLOOR": "#",
    "BLDG": "#",
    "BUILDING": "#",
    "TRLR": "#",
    "DEPTO": "#",
    "DEPARTAMENTO": "#",
}

#: Words dropped entirely. Includes "NO" handled above only after a number.
NOISE = {"THE"}

ABBREVIATIONS: dict[str, str] = {**SUFFIXES, **DIRECTIONALS, **ORDINALS}

#: Abbreviation -> the full words it stands for, so a half-typed "Pin" still
#: matches "PNE" (Pine) and "Stre" matches "ST".
EXPANSIONS: dict[str, list[str]] = {}
for _word, _abbr in ABBREVIATIONS.items():
    EXPANSIONS.setdefault(_abbr, []).append(_word)

_STRIP_RE = re.compile(r"[^\w#/\- ]+")
_SPACE_RE = re.compile(r"\s+")
_ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?$")
_NUMBER_RE = re.compile(r"^\d+[A-Z]?(?:-\d+[A-Z]?)?(?:\s+1/2)?")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tokens(text: str) -> list[str]:
    """Split ``text`` into normalised address tokens."""
    if not text:
        return []
    value = strip_accents(str(text)).upper().replace("&", " AND ")
    value = value.replace("#", " # ")
    value = _STRIP_RE.sub(" ", value)
    raw = [t.strip("-/") for t in _SPACE_RE.split(value) if t.strip("-/")]
    out: list[str] = []
    for i, token in enumerate(raw):
        if token in NOISE:
            continue
        if token in UNIT_WORDS and (i > 0 or token != "NO"):
            out.append("#")
            continue
        out.append(ABBREVIATIONS.get(token, token))
    # Collapse "# #" produced by e.g. "Apt #4".
    collapsed: list[str] = []
    for token in out:
        if token == "#" and collapsed and collapsed[-1] == "#":
            continue
        collapsed.append(token)
    return collapsed


def normalize(text: str) -> str:
    """Return the canonical search key for an address line."""
    return " ".join(tokens(text))


def street_line(query: str) -> str:
    """Keep only the street part of a full address ("214 Maple St, Town, IL 62000")."""
    text = (query or "").strip()
    if "," in text:
        text = text.split(",", 1)[0]
    return _ZIP_RE.sub("", text).strip()


@dataclass(frozen=True)
class ParsedAddress:
    house_number: str
    street: str
    unit: str

    @property
    def house_number_int(self) -> int | None:
        digits = re.match(r"\d+", self.house_number or "")
        return int(digits.group()) if digits else None


def parse(address: str) -> ParsedAddress:
    """Split a normalised street line into house number, street and unit."""
    toks = tokens(street_line(address))
    number = ""
    if toks and re.match(r"^\d", toks[0]):
        number = toks.pop(0)
        if toks and toks[0] == "1/2":
            number += " 1/2"
            toks.pop(0)
    unit = ""
    if "#" in toks:
        idx = toks.index("#")
        unit = " ".join(toks[idx + 1 :])
        toks = toks[:idx]
    return ParsedAddress(house_number=number, street=" ".join(toks), unit=unit)


def display_street(address: str) -> str:
    """Street name for display, keeping the original capitalisation: "Maple St"."""
    text = street_line(address)
    text = re.sub(r"^\s*\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?(?:\s+1/2)?\s+", "", text)
    text = re.split(r"\s+(?:#|apt\.?|apartment|unit|suite|ste\.?)\s*", text, flags=re.I)[0]
    return text.strip(" ,.") or address


def _edit_distance_at_most_one(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diffs = sum(1 for x, y in zip(a, b, strict=True) if x != y)
        if diffs == 1:
            return True
        # Adjacent transposition ("Mpale" for "Maple").
        idx = [i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y]
        return (
            len(idx) == 2
            and idx[1] == idx[0] + 1
            and a[idx[0]] == b[idx[1]]
            and a[idx[1]] == b[idx[0]]
        )
    if len(a) > len(b):
        a, b = b, a
    i = j = 0
    skipped = False
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            if skipped:
                return False
            skipped = True
            j += 1
            continue
        i += 1
        j += 1
    return True


def score(query_tokens: list[str], candidate_tokens: list[str]) -> float:
    """Score how well ``candidate_tokens`` match a (possibly partial) query.

    Returns 0 when the candidate is not a plausible match. The last query token
    may be a prefix (the resident is still typing). House numbers must match
    exactly, or as a prefix while being typed. Street words tolerate one typo.
    Mirrors ``scoreTokens`` in ``static/pipetrace/js/search.js``.
    """
    if not query_tokens or not candidate_tokens:
        return 0.0
    total = 0.0
    used: set[int] = set()
    last = len(query_tokens) - 1
    for qi, q in enumerate(query_tokens):
        best = 0.0
        best_idx = -1
        for ci, c in enumerate(candidate_tokens):
            if ci in used:
                continue
            is_number = q[0].isdigit()
            forms = [c, *EXPANSIONS.get(c, ())]
            if q == c:
                s = 3.0 if is_number else 2.0
            elif qi == last and any(f.startswith(q) for f in forms):
                s = 1.0 if is_number else 1.5
            elif (
                not is_number
                and len(q) >= 4
                and any(_edit_distance_at_most_one(q, f) for f in forms)
            ):
                s = 1.0
            else:
                continue
            # Matching tokens in order is better than matching them anywhere.
            if ci == qi:
                s += 0.25
            if s > best:
                best, best_idx = s, ci
        if best_idx < 0:
            return 0.0
        used.add(best_idx)
        total += best
    # Prefer candidates without lots of extra tokens.
    return total - 0.05 * (len(candidate_tokens) - len(used))


def search_config() -> dict:
    """Normalisation tables for the browser search (see ``search.js``)."""
    return {"abbr": ABBREVIATIONS, "units": sorted(UNIT_WORDS), "noise": sorted(NOISE)}
