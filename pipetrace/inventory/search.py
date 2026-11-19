"""Find service lines by address, the way a resident would type it."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.postgres.search import TrigramSimilarity

from pipetrace.inventory import addresses
from pipetrace.inventory.models import ServiceLine

CANDIDATE_LIMIT = 400


@dataclass
class Match:
    line: ServiceLine
    score: float
    exact: bool


def _candidates(q_tokens: list[str], normalized: str):
    qs = ServiceLine.objects.public()
    number = q_tokens[0] if q_tokens[0][0].isdigit() else None
    street_tokens = q_tokens[1:] if number else q_tokens
    if number and not street_tokens:
        return list(
            qs.filter(house_number__startswith=number).order_by("house_number_int", "street_key")[
                :CANDIDATE_LIMIT
            ]
        )
    found: dict[int, ServiceLine] = {}
    if number:
        exact_number = qs.filter(house_number__iexact=number)
        if len(q_tokens) == 1 or not exact_number.exists():
            exact_number = qs.filter(house_number__startswith=number)
        for line in exact_number[:CANDIDATE_LIMIT]:
            found[line.pk] = line
    else:
        first = street_tokens[0]
        for line in qs.filter(street_key__icontains=first[:3])[:CANDIDATE_LIMIT]:
            found[line.pk] = line
    if len(found) < 10:
        similar = (
            qs.annotate(sim=TrigramSimilarity("normalized", normalized))
            .filter(sim__gt=0.15)
            .order_by("-sim")[:60]
        )
        for line in similar:
            found.setdefault(line.pk, line)
    return list(found.values())


def search(query: str, limit: int = 8) -> list[Match]:
    street = addresses.street_line(query)
    q_tokens = addresses.tokens(street)
    if not q_tokens:
        return []
    normalized = " ".join(q_tokens)
    matches = []
    for line in _candidates(q_tokens, normalized):
        c_tokens = line.normalized.split()
        score = addresses.score(q_tokens, c_tokens)
        if score <= 0:
            continue
        exact = line.normalized == normalized or (
            # "214 Maple St" matches "214 MAPLE ST #2" only when there's one unit.
            line.normalized.startswith(normalized + " #")
        )
        matches.append(Match(line=line, score=score + (5 if exact else 0), exact=exact))
    matches.sort(
        key=lambda m: (-m.score, m.line.street_key, m.line.house_number_int or 0, m.line.unit)
    )
    return matches[:limit]


def best_match(query: str) -> ServiceLine | None:
    """The single line a query clearly refers to, if there is one.

    Either the only exact address match, or the only match at all when the house
    number typed is exactly the line's house number. Several units at the same
    address are not "clear": the resident chooses.
    """
    matches = search(query, limit=3)
    exact = [m for m in matches if m.exact]
    if len(exact) == 1:
        return exact[0].line
    if len(matches) == 1 and not exact:
        q_tokens = addresses.tokens(addresses.street_line(query))
        if len(q_tokens) > 1 and q_tokens[0] == matches[0].line.house_number:
            return matches[0].line
    return None


def same_street(query: str, limit: int = 12) -> list[Match]:
    """When a house number isn't found, offer the other addresses on that street."""
    q_tokens = addresses.tokens(addresses.street_line(query))
    if len(q_tokens) < 2 or not q_tokens[0][0].isdigit():
        return []
    return search(" ".join(q_tokens[1:]), limit=limit)
