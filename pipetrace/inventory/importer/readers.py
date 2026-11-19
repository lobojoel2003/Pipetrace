"""Read inventory spreadsheets (.xlsx, .xlsm, .csv, .tsv, .txt) into rows of text."""

from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from openpyxl import load_workbook

EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xltx", ".xltm"}
TEXT_EXTENSIONS = {".csv", ".tsv", ".txt"}
SUPPORTED_EXTENSIONS = EXCEL_EXTENSIONS | TEXT_EXTENSIONS


class UnsupportedFile(ValueError):
    """The file is not a spreadsheet Pipetrace can read."""


def cell_text(value) -> str:
    """Turn a spreadsheet cell into clean text.

    Whole-number floats lose their ``.0`` (Excel stores ZIP codes and IDs as
    numbers), dates become ISO strings and whitespace is collapsed.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    if isinstance(value, dt.datetime):
        if value.time() == dt.time(0, 0):
            return value.date().isoformat()
        return value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, dt.date):
        return value.isoformat()
    text = str(value).replace(" ", " ").replace("\r", " ").replace("\n", " ")
    return " ".join(text.split())


@dataclass
class Sheet:
    name: str
    rows: list[list[str]] = field(default_factory=list)

    @property
    def width(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    def non_empty_rows(self) -> int:
        return sum(1 for r in self.rows if any(r))


@dataclass
class Workbook:
    kind: str
    sheets: list[Sheet]

    @property
    def sheet_names(self) -> list[str]:
        return [s.name for s in self.sheets]

    def sheet(self, name: str | None = None) -> Sheet:
        if name:
            for sheet in self.sheets:
                if sheet.name == name:
                    return sheet
        return self.best_sheet()

    def best_sheet(self) -> Sheet:
        """The sheet that most looks like the inventory (most filled rows)."""

        def weight(sheet: Sheet) -> tuple[int, int]:
            name = sheet.name.lower()
            bonus = 1 if any(w in name for w in ("inventory", "service", "line", "data")) else 0
            penalty = (
                1
                if any(
                    w in name
                    for w in ("instruction", "code", "summary", "readme", "lookup", "list")
                )
                else 0
            )
            return (bonus - penalty, sheet.non_empty_rows())

        return max(self.sheets, key=weight)


def _trim(rows: list[list[str]]) -> list[list[str]]:
    while rows and not any(rows[-1]):
        rows.pop()
    width = 0
    for row in rows:
        for i in range(len(row) - 1, -1, -1):
            if row[i]:
                width = max(width, i + 1)
                break
    return [(row + [""] * (width - len(row)))[:width] for row in rows]


def read_excel(source: BinaryIO | Path | str) -> Workbook:
    try:
        wb = load_workbook(source, read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many types for corrupt files
        raise UnsupportedFile(f"Could not open the Excel file: {exc}") from exc
    sheets = []
    try:
        for ws in wb.worksheets:
            if getattr(ws, "sheet_state", "visible") != "visible":
                continue
            rows = [[cell_text(v) for v in row] for row in ws.iter_rows(values_only=True)]
            sheets.append(Sheet(name=ws.title, rows=_trim(rows)))
    finally:
        wb.close()
    sheets = [s for s in sheets if s.rows] or sheets[:1]
    if not sheets:
        raise UnsupportedFile("The Excel file has no sheets with data.")
    return Workbook(kind="xlsx", sheets=sheets)


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")  # pragma: no cover - latin-1 never fails


def read_text(data: bytes, name: str = "") -> Workbook:
    text = _decode(data)
    sample = text[:20000]
    delimiter = "\t" if name.lower().endswith(".tsv") else ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        pass
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [[cell_text(v) for v in row] for row in reader]
    stem = Path(name).stem or "Sheet1"
    return Workbook(kind="csv", sheets=[Sheet(name=stem, rows=_trim(rows))])


def read_workbook(source: BinaryIO | Path | str, name: str | None = None) -> Workbook:
    """Read ``source`` (a path or binary file object) into a :class:`Workbook`."""
    filename = name or (
        str(source) if isinstance(source, (str, Path)) else getattr(source, "name", "")
    )
    ext = Path(filename).suffix.lower()
    if isinstance(source, (str, Path)):
        data = Path(source).read_bytes()
    else:
        if hasattr(source, "seek"):
            source.seek(0)
        data = source.read()
    if ext in EXCEL_EXTENSIONS or data[:4] == b"PK\x03\x04":
        return read_excel(io.BytesIO(data))
    if ext == ".xls" or data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise UnsupportedFile(
            "This is an old Excel 97-2003 (.xls) file. Open it in Excel or LibreOffice and "
            "save it as .xlsx or .csv, then upload it again."
        )
    if ext in TEXT_EXTENSIONS or not ext:
        return read_text(data, filename)
    raise UnsupportedFile(
        f"Pipetrace can read .xlsx and .csv files, not {ext or 'this file type'}."
    )
