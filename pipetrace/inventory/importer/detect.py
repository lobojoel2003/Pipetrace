"""Find the header row in a messy sheet and guess which column is which field."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from pipetrace.inventory.importer.fields import FIELDS, FieldSpec

MAX_HEADER_SCAN = 30
_WORD_RE = re.compile(r"[a-z0-9]+")


def words(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower().replace("-", " "))


def phrase(text: str) -> str:
    return " ".join(words(text))


_ALL_SYNONYMS = {phrase(s) for f in FIELDS for s in (*f.synonyms, *f.exact)}
_ALL_WORDS = {w for s in _ALL_SYNONYMS for w in s.split()}


@dataclass
class Column:
    index: int
    header: str
    group: str = ""
    samples: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        if self.group and self.group.lower() not in self.header.lower():
            return f"{self.group} › {self.header}" if self.header else self.group
        return self.header or self.letter

    @property
    def letter(self) -> str:
        n = self.index + 1
        out = ""
        while n:
            n, rem = divmod(n - 1, 26)
            out = chr(65 + rem) + out
        return out

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "header": self.header,
            "group": self.group,
            "label": self.label,
            "letter": self.letter,
            "samples": list(self.samples),
        }


def _looks_like_value(cell: str) -> bool:
    if not cell:
        return False
    if re.fullmatch(r"[-+]?\d+([.,]\d+)?", cell):
        return True
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}.*|\d{1,2}/\d{1,2}/\d{2,4}", cell))


def _row_score(row: list[str]) -> float:
    filled = [c for c in row if c]
    if len(filled) < 2:
        return 0.0
    labels = [c for c in filled if not _looks_like_value(c) and len(c) <= 120]
    hits = 0.0
    for cell in labels:
        p = phrase(cell)
        if p in _ALL_SYNONYMS:
            hits += 2
        elif any(w in _ALL_WORDS for w in p.split()):
            hits += 0.5
    long_text = sum(1 for c in filled if len(c) > 120)
    return len(labels) + 3 * hits - 2 * long_text - 2 * (len(filled) - len(labels))


def detect_header_row(rows: list[list[str]]) -> int:
    """Return the 0-based index of the most header-like row near the top."""
    best_idx, best = 0, float("-inf")
    for idx, row in enumerate(rows[:MAX_HEADER_SCAN]):
        score = _row_score(row)
        if score > best:
            best_idx, best = idx, score
    return best_idx


def _group_labels(rows: list[list[str]], header_idx: int, width: int) -> list[str]:
    """Labels from a group row above the header (e.g. "System-Owned Portion").

    Merged cells only carry a value in their first column, so labels are carried
    to the right until the next label - but only over columns that have a header.
    """
    if header_idx == 0:
        return [""] * width
    above = rows[header_idx - 1]
    header = rows[header_idx]
    filled = [c for c in above if c]
    header_filled = [c for c in header if c]
    # A group row is sparse compared with the header and made of short labels.
    if not filled or len(filled) >= len(header_filled) or any(len(c) > 80 for c in filled):
        return [""] * width
    groups, current = [], ""
    for i in range(width):
        cell = above[i] if i < len(above) else ""
        if cell:
            current = cell
        elif i < len(header) and not header[i]:
            current = ""
        groups.append(current)
    return groups


def build_columns(
    rows: list[list[str]], header_idx: int, data_start: int | None = None, sample_size: int = 4
) -> list[Column]:
    width = max((len(r) for r in rows), default=0)
    header = rows[header_idx] if rows else []
    groups = _group_labels(rows, header_idx, width)
    start = header_idx + 1 if data_start is None else data_start
    columns = []
    for i in range(width):
        name = header[i] if i < len(header) else ""
        samples: list[str] = []
        for row in rows[start:]:
            if i < len(row) and row[i] and row[i] not in samples:
                samples.append(row[i])
                if len(samples) >= sample_size:
                    break
        if not name and not samples and not groups[i]:
            continue
        columns.append(Column(index=i, header=name, group=groups[i], samples=tuple(samples)))
    return columns


def header_signature(columns: list[Column]) -> str:
    """Fingerprint of a file layout, used to reuse the last mapping for the same layout."""
    key = "|".join(phrase(c.label) for c in columns)
    return hashlib.sha256(key.encode()).hexdigest()


def _score(spec: FieldSpec, column: Column) -> float:
    head = phrase(column.header)
    group = phrase(column.group)
    full = f"{group} {head}".strip()
    all_words = set(full.split())
    if not head and not group:
        return 0.0
    if spec.avoid & all_words:
        return 0.0
    for need in spec.need_any:
        if not need & all_words:
            return 0.0
    best = 0.0
    if head in {phrase(e) for e in spec.exact}:
        best = 90.0
    for syn in spec.synonyms:
        s = phrase(syn)
        if not s:
            continue
        if head == s or full == s:
            best = max(best, 100.0)
        elif re.search(rf"\b{re.escape(s)}\b", full):
            best = max(best, 50.0 + 6 * len(s.split()) - 0.5 * (len(all_words) - len(s.split())))
    return best


def suggest_mapping(columns: list[Column]) -> dict[str, int]:
    """Greedy best-first assignment of fields to columns."""
    candidates = []
    for spec in FIELDS:
        for col in columns:
            score = _score(spec, col)
            if score >= 45:
                candidates.append((score, spec.key, col.index))
    candidates.sort(key=lambda c: (-c[0], c[2]))
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for _score_value, key, index in candidates:
        if key in mapping or index in used:
            continue
        mapping[key] = index
        used.add(index)
    # A single combined address column makes separate number/street columns redundant.
    if "address" in mapping:
        for key in ("house_number", "street_name"):
            mapping.pop(key, None)
    return mapping


def mapping_by_label(mapping: dict[str, int], columns: list[Column]) -> dict[str, str]:
    labels = {c.index: c.label for c in columns}
    return {k: labels[v] for k, v in mapping.items() if v in labels}


def mapping_from_labels(saved: dict[str, str], columns: list[Column]) -> dict[str, int]:
    by_label = {phrase(c.label): c.index for c in columns}
    out = {}
    for key, label in saved.items():
        idx = by_label.get(phrase(label))
        if idx is not None:
            out[key] = idx
    return out
