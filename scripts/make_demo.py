#!/usr/bin/env python
"""Generate the fictional "Millbrook" demo inventory and its street map.

Outputs (committed to the repository, regenerate with ``python scripts/make_demo.py``):

* ``pipetrace/inventory/demo/millbrook-inventory.xlsx`` - an inventory laid out like
  EPA's template: title rows, group headers over two rows, a codes row, mixed codes.
* ``pipetrace/inventory/demo/millbrook-messy.csv`` - the same town as a messy export
  with odd headers, for trying the column-mapping screen.
* ``pipetrace/static/pipetrace/demo/millbrook-basemap.geojson`` - streets, creek,
  parks and building footprints drawn for the demo map (no real place is shown).

Everything is made up. Millbrook does not exist.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import random
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "pipetrace" / "inventory" / "demo"
STATIC_DEMO = ROOT / "pipetrace" / "static" / "pipetrace" / "demo"

LAT0, LON0 = 40.0, -89.0
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(LAT0))
TODAY = dt.date(2026, 10, 31)

rng = random.Random(20261031)


def ll(x: float, y: float) -> tuple[float, float]:
    """Local metres (east, north) to (lon, lat)."""
    return (round(LON0 + x / M_PER_DEG_LON, 6), round(LAT0 + y / M_PER_DEG_LAT, 6))


# --- Town plan --------------------------------------------------------------------------
BLOCK_W, BLOCK_H = 170.0, 115.0
# East-west streets (south to north). y in metres.
EW_STREETS = [
    ("Mill Rd", 0, "major"),
    ("Church St", 1, "minor"),
    ("Main St", 2, "major"),
    ("School St", 3, "minor"),
    ("Maple St", 4, "minor"),
    ("Oak St", 5, "minor"),
    ("Walnut St", 6, "minor"),
]
# North-south avenues (west to east). x in block units.
NS_STREETS = [
    ("River Rd", 0, "minor"),
    ("Cedar Ave", 1, "minor"),
    ("Elm Ave", 2, "minor"),
    ("Center Ave", 3, "major"),
    ("Pine Ave", 4, "minor"),
    ("Birch Ave", 5, "minor"),
]
X_MIN, X_MAX = 0.0, 5 * BLOCK_W
Y_MIN, Y_MAX = 0.0, 6 * BLOCK_H
PARK_BLOCK = (1, 2)  # Town Square: between Cedar/Elm and Main/School
SCHOOL_BLOCK = (4, 3)  # between Pine/Birch and School/Maple


def era(x: float, y: float) -> str:
    if x > X_MAX + 20:
        return "new"
    if x < 3 * BLOCK_W and y < 5 * BLOCK_H:
        return "old"
    return "mid"


# Hillcrest: a newer subdivision east of Birch Ave with curving streets.
def hillcrest_curve(t: float, radius: float, cx: float, cy: float, a0: float, a1: float):
    angle = a0 + (a1 - a0) * t
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


HILLCREST = [
    (
        "Hillcrest Dr",
        {
            "radius": 210,
            "cx": X_MAX + 40,
            "cy": 3.0 * BLOCK_H,
            "a0": -math.pi / 2.2,
            "a1": math.pi / 2.2,
        },
    ),
    (
        "Meadow Ln",
        {
            "radius": 120,
            "cx": X_MAX + 40,
            "cy": 3.0 * BLOCK_H,
            "a0": -math.pi / 2.6,
            "a1": math.pi / 2.6,
        },
    ),
]


def polyline_points(name: str, spec: dict, n: int = 40):
    return [hillcrest_curve(i / (n - 1), **spec) for i in range(n)]


# --- Lines ----------------------------------------------------------------------------------
MATERIALS = {
    "old": {
        "system": [("Lead", 42), ("Copper", 38), ("Unknown", 20)],
        "customer": [("Lead", 36), ("Galvanized", 20), ("Copper", 26), ("Unknown", 18)],
    },
    "mid": {
        "system": [("Copper", 62), ("Unknown", 22), ("Lead", 10), ("Galvanized", 6)],
        "customer": [("Copper", 46), ("Galvanized", 22), ("Unknown", 26), ("Plastic", 6)],
    },
    "new": {
        "system": [("Copper", 70), ("Plastic", 28), ("Unknown", 2)],
        "customer": [("Copper", 40), ("Plastic", 52), ("Unknown", 8)],
    },
}
MESSY = {
    "Copper": ["Copper", "Copper", "Copper", "CU", "copper ", "Cu"],
    "Lead": ["Lead", "Lead", "Lead", "LEAD", "Pb"],
    "Galvanized": ["Galvanized", "Galvanized", "GALV", "Galvanized Steel"],
    "Plastic": ["Plastic", "PVC", "PEX", "HDPE"],
    "Unknown": ["Unknown", "Unknown", "Unknown", "", "UNK"],
}
BASIS = {
    "records": "Records review (tap cards)",
    "field": "Field verification (excavation)",
    "visual": "Visual inspection at meter",
    "photo": "Customer self-identification (photo)",
    "permit": "Building permit records",
}


def pick(options):
    total = sum(w for _o, w in options)
    roll = rng.uniform(0, total)
    for option, weight in options:
        roll -= weight
        if roll <= 0:
            return option
    return options[-1][0]


def classify(system: str, customer: str, ever_lead: str) -> str:
    portions = {system, customer}
    if "Lead" in portions:
        return "L"
    if "Galvanized" in portions:
        if ever_lead == "No" and "Unknown" not in portions:
            return "NL"
        return "GRR"
    if "Unknown" in portions:
        return "U"
    return "NL"


def make_line(x: float, y: float, address: str, street_era: str, house_side: tuple):
    system = pick(MATERIALS[street_era]["system"])
    customer = pick(MATERIALS[street_era]["customer"])
    ever_lead = ""
    if customer == "Galvanized" or system == "Galvanized":
        ever_lead = rng.choice(["Yes", "Unknown", "Unknown", "No"]) if system != "Lead" else "Yes"
    status = classify(system, customer, ever_lead)
    built = {
        "old": rng.randint(1898, 1942),
        "mid": rng.randint(1946, 1978),
        "new": rng.randint(1988, 2014),
    }[street_era]
    installed = built if rng.random() < 0.8 else ""
    if system == "Copper" and street_era == "old":
        installed = rng.randint(1958, 1995)  # utility side renewed with a main replacement
    connector = ""
    if street_era == "old":
        connector = rng.choice(["Yes", "No", "Unknown", "Unknown", "No"])
    elif street_era == "mid":
        connector = rng.choice(["No", "No", "Unknown"])
    else:
        connector = "None"
    basis = []
    if system != "Unknown":
        basis.append(rng.choice([BASIS["records"], BASIS["records"], BASIS["field"]]))
    cust_basis = BASIS["visual"] if customer != "Unknown" else ""
    if customer != "Unknown" and rng.random() < 0.12:
        cust_basis = BASIS["photo"]
    verified = ""
    if customer != "Unknown" and rng.random() < 0.55:
        verified = TODAY - dt.timedelta(days=rng.randint(30, 900))

    replacement, scheduled, replaced = "", "", ""
    if status in {"L", "GRR"}:
        roll = rng.random()
        if street_era == "old" and roll < 0.30:
            replacement = "Replaced"
            replaced = dt.date(2025, 4, 1) + dt.timedelta(days=rng.randint(0, 540))
        elif roll < 0.62:
            replacement = "Scheduled"
            scheduled = rng.choice(
                ["Spring 2027", "Spring 2027", "Fall 2027", "2028", "Phase 3 (2029)"]
            )
        elif roll < 0.67:
            replacement = "In progress"
            scheduled = "December 2026"
        else:
            replacement = "Not scheduled"
    if replacement == "Replaced":
        system, customer, status, ever_lead = "Copper", "Copper", "NL", ""
        basis = [BASIS["field"]]
        cust_basis = BASIS["field"]
        verified = replaced
        installed = replaced.year
    note = ""
    if connector == "Yes" and replacement != "Replaced":
        note = "Lead gooseneck at the main will be replaced with the service line."
    return {
        "x": x,
        "y": y,
        "address": address,
        "system": system,
        "customer": customer,
        "ever_lead": ever_lead,
        "status": status,
        "connector": connector,
        "system_basis": "; ".join(basis),
        "customer_basis": cust_basis,
        "installed": installed,
        "built": built,
        "verified": verified,
        "replacement": replacement,
        "scheduled": scheduled,
        "replaced": replaced,
        "note": note,
        "side": house_side,
    }


def lots_along(x0, y0, x1, y1, start_number, step=2, spacing=24.0, inset=18.0):
    """Lot positions on both sides of a straight street segment."""
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    nx, ny = -uy, ux  # left normal
    count = int((length - 2 * inset) // spacing) + 1
    out = []
    for i in range(count):
        d = inset + i * spacing + rng.uniform(-2, 2)
        if rng.random() < 0.1:
            continue  # empty lot
        cx, cy = x0 + ux * d, y0 + uy * d
        number = start_number + i * step * 2
        out.append((cx + nx * 9, cy + ny * 9, number + 1, (nx, ny), (ux, uy)))  # odd: left
        if rng.random() < 0.92:
            out.append((cx - nx * 9, cy - ny * 9, number, (-nx, -ny), (ux, uy)))  # even: right
    return out


def build():
    lines, buildings = [], []

    def add_building(x, y, normal, direction, small=False):
        nx, ny = normal
        ux, uy = direction
        depth = rng.uniform(9, 13) if not small else 7
        width = rng.uniform(9, 14) if not small else 8
        bx, by = x + nx * (6 + depth / 2), y + ny * (6 + depth / 2)
        corners = []
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            px = bx + ux * sx * width / 2 + nx * sy * depth / 2
            py = by + uy * sx * width / 2 + ny * sy * depth / 2
            corners.append(ll(px, py))
        corners.append(corners[0])
        buildings.append(corners)

    def skip_block(x, y):
        bx, by = int(x // BLOCK_W), int(y // BLOCK_H)
        return (bx, by) in (PARK_BLOCK, SCHOOL_BLOCK) or x < 30

    # E-W streets: houses between avenues; numbers grow eastward.
    for name, row, _cls in EW_STREETS:
        y = row * BLOCK_H
        for block in range(5):
            x0, x1 = block * BLOCK_W, (block + 1) * BLOCK_W
            for x, yy, number, normal, direction in lots_along(x0, y, x1, y, 100 * (block + 1)):
                if skip_block(x, yy) or yy < 0 or yy > Y_MAX:
                    continue
                street_era = era(x, yy)
                line = make_line(x, yy, f"{number} {name}", street_era, normal)
                lines.append(line)
                add_building(x, yy, normal, direction)
    # N-S avenues: numbers grow northward; only the long blocks without E-W frontage.
    for name, col, _cls in NS_STREETS:
        x = col * BLOCK_W
        for block in range(6):
            y0, y1 = block * BLOCK_H, (block + 1) * BLOCK_H
            for xx, y, number, normal, direction in lots_along(
                x, y0, x, y1, 100 * (block + 1), spacing=27, inset=30
            ):
                if skip_block(xx, y) or xx > X_MAX + 5:
                    continue
                street_era = era(xx, y)
                line = make_line(xx, y, f"{number} {name}", street_era, normal)
                lines.append(line)
                add_building(xx, y, normal, direction)
    # Hillcrest subdivision.
    for name, spec in HILLCREST:
        pts = polyline_points(name, spec, n=60)
        number = 2
        for i in range(2, len(pts) - 2, 3):
            (x0, y0), (x1, y1) = pts[i - 1], pts[i + 1]
            length = math.hypot(x1 - x0, y1 - y0)
            ux, uy = (x1 - x0) / length, (y1 - y0) / length
            nx, ny = -uy, ux
            for side, sign in (("odd", 1), ("even", -1)):
                if name == "Meadow Ln" and side == "odd":
                    continue
                px, py = pts[i][0] + sign * nx * 9, pts[i][1] + sign * ny * 9
                n = number + (1 if side == "odd" else 0)
                line = make_line(px, py, f"{n} {name}", "new", (sign * nx, sign * ny))
                lines.append(line)
                add_building(px, py, (sign * nx, sign * ny), (ux, uy))
            number += 4
    # Apartments: a few units sharing one service line address on Main St.
    for line in rng.sample([ln for ln in lines if "Main St" in ln["address"]], 2):
        line["unit"] = "A"
    return lines, buildings


def basemap(buildings) -> dict:
    features = []

    def feature(kind, geometry, **props):
        features.append(
            {"type": "Feature", "properties": {"kind": kind, **props}, "geometry": geometry}
        )

    # Land, creek, parks first (drawn underneath).
    creek = [(-140, -60), (-95, 120), (-60, 300), (-75, 470), (-30, 640), (10, 760)]
    left = [(x - 14, y) for x, y in creek]
    right = [(x + 14, y) for x, y in reversed(creek)]
    feature(
        "water",
        {"type": "Polygon", "coordinates": [[ll(*p) for p in left + right + [left[0]]]]},
        name="Mill Creek",
    )
    feature(
        "waterway",
        {"type": "LineString", "coordinates": [ll(*p) for p in creek]},
        name="Mill Creek",
    )
    riverside = [(-40, 140), (-20, 560), (25, 560), (25, 140), (-40, 140)]
    feature(
        "park",
        {"type": "Polygon", "coordinates": [[ll(*p) for p in riverside]]},
        name="Riverside Park",
    )
    px, py = PARK_BLOCK
    square = [
        (px * BLOCK_W + 12, py * BLOCK_H + 12),
        ((px + 1) * BLOCK_W - 12, py * BLOCK_H + 12),
        ((px + 1) * BLOCK_W - 12, (py + 1) * BLOCK_H - 12),
        (px * BLOCK_W + 12, (py + 1) * BLOCK_H - 12),
    ]
    feature(
        "park",
        {"type": "Polygon", "coordinates": [[ll(*p) for p in square + square[:1]]]},
        name="Town Square",
    )
    sx, sy = SCHOOL_BLOCK
    school = [
        (sx * BLOCK_W + 10, sy * BLOCK_H + 10),
        ((sx + 1) * BLOCK_W - 10, sy * BLOCK_H + 10),
        ((sx + 1) * BLOCK_W - 10, (sy + 1) * BLOCK_H - 10),
        (sx * BLOCK_W + 10, (sy + 1) * BLOCK_H - 10),
    ]
    feature(
        "school",
        {"type": "Polygon", "coordinates": [[ll(*p) for p in school + school[:1]]]},
        name="Millbrook Elementary",
    )
    for ring in buildings:
        feature("building", {"type": "Polygon", "coordinates": [ring]})
    # Roads.
    for name, row, cls in EW_STREETS:
        y = row * BLOCK_H
        east = X_MAX + (60 if cls == "major" else 0)
        feature(
            "road",
            {
                "type": "LineString",
                "coordinates": [ll(-60 if cls == "major" else 0, y), ll(east, y)],
            },
            name=name,
            cls=cls,
        )
    for name, col, cls in NS_STREETS:
        x = col * BLOCK_W
        south = -80 if cls == "major" else 0
        feature(
            "road",
            {"type": "LineString", "coordinates": [ll(x, south), ll(x, Y_MAX)]},
            name=name,
            cls=cls,
        )
    for name, spec in HILLCREST:
        pts = polyline_points(name, spec, n=60)
        feature(
            "road",
            {"type": "LineString", "coordinates": [ll(*p) for p in pts]},
            name=name,
            cls="minor",
        )
    # Hillcrest entrance from Main St.
    feature(
        "road",
        {
            "type": "LineString",
            "coordinates": [ll(X_MAX, 3 * BLOCK_H), ll(X_MAX + 160, 3 * BLOCK_H)],
        },
        name="Sunset Ct",
        cls="minor",
    )
    # Place labels.
    feature(
        "place",
        {"type": "Point", "coordinates": ll(2.1 * BLOCK_W, 5.55 * BLOCK_H)},
        name="Old Town",
    )
    feature(
        "place", {"type": "Point", "coordinates": ll(X_MAX + 160, 4.9 * BLOCK_H)}, name="Hillcrest"
    )
    return {"type": "FeatureCollection", "features": features}


GROUPS = [
    ("Location Identifier", ["Service Line ID", "Street Address", "City", "State", "Zip Code"]),
    (
        "System-Owned Portion",
        ["Material", "Was Material Ever Previously Lead?", "Basis of Classification"],
    ),
    ("Customer-Owned Portion", ["Material", "Basis of Classification", "Installation Date"]),
    (
        "Entire Service Line",
        [
            "Entire Service Line Material Classification",
            "Lead Connector (Gooseneck/Pigtail)",
            "Date Verified",
        ],
    ),
    ("Replacement", ["Replacement Status", "Scheduled Replacement", "Date Replaced"]),
    ("Other", ["Year Built", "Notes", "Latitude", "Longitude"]),
]
CODES_ROW = {
    5: "Lead / Galvanized / Copper / Plastic / Unknown",
    6: "Yes / No / Unknown",
    8: "Lead / Galvanized / Copper / Plastic / Unknown",
    11: "L = Lead, GRR = Galvanized Requiring Replacement, NL = Non-Lead, U = Lead Status Unknown",
    12: "Yes / No / None / Unknown",
    14: "Not scheduled / Scheduled / In progress / Replaced",
}


def write_xlsx(lines, path: Path):
    wb = Workbook()
    readme = wb.active
    readme.title = "Instructions"
    for text in [
        "Millbrook Water Department - Service Line Inventory (DEMO)",
        "",
        "This workbook is fictional demo data for Pipetrace. Millbrook does not exist.",
        "It follows the layout of the EPA service line inventory template: one row per",
        "service line, with the system-owned and customer-owned portions recorded separately",
        "and an overall classification for the entire line.",
    ]:
        readme.append([text])
    readme["A1"].font = Font(bold=True, size=14)
    readme.column_dimensions["A"].width = 100

    ws = wb.create_sheet("Inventory")
    ws.append(["Service Line Inventory - Millbrook Water Department (fictional demo data)"])
    ws.append(["PWSID: DEMO-0001", "", "Inventory as of:", TODAY.isoformat()])
    ws.append([])
    group_row, header_row = [], []
    for group, cols in GROUPS:
        group_row += [group] + [""] * (len(cols) - 1)
        header_row += cols
    ws.append(group_row)
    ws.append(header_row)
    ws.append([CODES_ROW.get(i, "") for i in range(len(header_row))])

    def messy(value: str) -> str:
        return rng.choice(MESSY.get(value, [value]))

    codes = {"L": "L", "GRR": "GRR", "NL": "NL", "U": "U"}
    for i, line in enumerate(lines, start=1):
        lon, lat = ll(line["x"], line["y"])
        unit = line.get("unit")
        address = line["address"] + (f" Apt {unit}" if unit else "")
        ws.append(
            [
                f"MB-{i:05d}",
                address,
                "Millbrook",
                "IL",
                "60000",
                messy(line["system"]),
                line["ever_lead"],
                line["system_basis"],
                messy(line["customer"]),
                line["customer_basis"],
                line["installed"] or None,
                codes[line["status"]],
                line["connector"],
                line["verified"] or None,
                line["replacement"],
                line["scheduled"],
                line["replaced"] or None,
                line["built"],
                line["note"],
                lat,
                lon,
            ]
        )

    title = Font(bold=True, size=14, color="0B3B4F")
    ws["A1"].font = title
    group_fill = PatternFill("solid", fgColor="0B5D7A")
    head_fill = PatternFill("solid", fgColor="D9EDF3")
    thin = Side(style="thin", color="9FB6BF")
    col = 1
    for _group, cols in GROUPS:
        start, end = col, col + len(cols) - 1
        ws.merge_cells(start_row=4, start_column=start, end_row=4, end_column=end)
        cell = ws.cell(row=4, column=start)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = group_fill
        cell.alignment = Alignment(horizontal="center")
        col = end + 1
    for c in range(1, len(header_row) + 1):
        cell = ws.cell(row=5, column=c)
        cell.font = Font(bold=True)
        cell.fill = head_fill
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        cell.border = Border(bottom=thin)
        ws.cell(row=6, column=c).font = Font(italic=True, size=9, color="555555")
        ws.column_dimensions[get_column_letter(c)].width = 16
    ws.column_dimensions["B"].width = 24
    ws.row_dimensions[5].height = 45
    ws.freeze_panes = "C7"
    last = 6 + len(lines)
    validation = DataValidation(type="list", formula1='"L,GRR,NL,U"', allow_blank=True)
    ws.add_data_validation(validation)
    validation.add(f"L7:L{last}")
    for row in ws.iter_rows(min_row=7, max_row=last):
        for cell in row:
            if hasattr(cell.value, "year") and not isinstance(cell.value, int):
                cell.number_format = "yyyy-mm-dd"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def write_messy_csv(lines, path: Path):
    """Same town, exported from a billing system with unhelpful headers."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "Acct #",
                "Service Addr",
                "Town",
                "Utility Side",
                "Cust Side",
                "LSL?",
                "Gooseneck",
                "Sched",
                "Y",
                "X",
                "Comments",
            ]
        )
        for i, line in enumerate(lines[:120], start=1):
            lon, lat = ll(line["x"], line["y"])
            lsl = {"L": "YES", "GRR": "GALV-RR", "NL": "no", "U": "?"}[line["status"]]
            writer.writerow(
                [
                    f"{100000 + i}",
                    line["address"].upper(),
                    "MILLBROOK",
                    {
                        "Lead": "PB",
                        "Copper": "CU",
                        "Galvanized": "GALV",
                        "Plastic": "PE",
                        "Unknown": "UNK",
                    }[line["system"]],
                    {
                        "Lead": "LEAD",
                        "Copper": "COPPER",
                        "Galvanized": "GALVANIZED",
                        "Plastic": "PLASTIC",
                        "Unknown": "",
                    }[line["customer"]],
                    lsl,
                    {"Yes": "Y", "No": "N", "None": "NONE", "Unknown": "U", "": ""}[
                        line["connector"]
                    ],
                    line["scheduled"],
                    lat,
                    lon,
                    line["note"],
                ]
            )


def main():
    lines, buildings = build()
    write_xlsx(lines, DEMO_DIR / "millbrook-inventory.xlsx")
    write_messy_csv(lines, DEMO_DIR / "millbrook-messy.csv")
    STATIC_DEMO.mkdir(parents=True, exist_ok=True)
    (STATIC_DEMO / "millbrook-basemap.geojson").write_text(
        json.dumps(basemap(buildings), separators=(",", ":")), encoding="utf-8"
    )
    counts = {}
    for line in lines:
        counts[line["status"]] = counts.get(line["status"], 0) + 1
    print(f"{len(lines)} lines:", counts)


if __name__ == "__main__":
    main()
