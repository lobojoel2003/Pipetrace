"""Derive a service line's overall classification from its two portions.

Rules follow the Lead and Copper Rule Improvements (40 CFR 141.84(a)):

* A line is **lead** if any portion is lead (lead-lined galvanized counts as lead).
* A line is **galvanized requiring replacement (GRR)** if any portion is
  galvanized and the line is, was, or may have been downstream of lead. A system
  that cannot show a galvanized line was *never* downstream of lead must treat it
  as GRR, so galvanized defaults to GRR unless history says "no".
* A line is **non-lead** only when both portions are known non-lead materials.
* Everything else is **lead status unknown**.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipetrace.inventory.choices import (
    NON_LEAD_MATERIALS,
    Material,
    Status,
    YesNoUnknown,
)


def classify(
    system_material: str | None,
    customer_material: str | None,
    downstream_of_lead: str | None = None,
) -> Status:
    """Return the overall :class:`Status` for a line with the given portions.

    ``system_material`` and ``customer_material`` are :class:`Material` values (or
    blank). ``downstream_of_lead`` is a :class:`YesNoUnknown` value saying whether
    galvanized pipe is, or ever was, downstream of a lead line.
    """
    portions = [system_material or Material.UNKNOWN, customer_material or Material.UNKNOWN]

    if Material.LEAD in portions:
        return Status.LEAD

    if Material.GALVANIZED in portions:
        other = [p for p in portions if p != Material.GALVANIZED]
        upstream_unknown = any(p == Material.UNKNOWN for p in other)
        if downstream_of_lead == YesNoUnknown.NO and not upstream_unknown:
            return Status.NON_LEAD
        return Status.GRR

    if all(p in NON_LEAD_MATERIALS for p in portions):
        return Status.NON_LEAD

    return Status.UNKNOWN


@dataclass(frozen=True)
class ClassificationCheck:
    """Result of comparing a file's stated classification with the derived one."""

    stated: Status | None
    derived: Status
    portions_known: bool

    @property
    def final(self) -> Status:
        """The utility's stated classification wins; otherwise use the derived one."""
        return self.stated or self.derived

    @property
    def conflict(self) -> bool:
        """True when the stated classification contradicts the portion materials.

        Only flagged when the portions say something definite: a file that
        classifies a line as "lead" while both portions are blank is not a
        conflict, it simply has no portion detail.
        """
        if self.stated is None or not self.portions_known:
            return False
        if self.stated == self.derived:
            return False
        # A GRR line whose history is not recorded derives to GRR, and one whose
        # history says "never downstream of lead" derives to non-lead; trust the file.
        return not (
            {self.stated, self.derived} <= {Status.GRR, Status.NON_LEAD}
            and self.derived == Status.GRR
        )


def check_classification(
    stated: str | None,
    system_material: str | None,
    customer_material: str | None,
    downstream_of_lead: str | None = None,
) -> ClassificationCheck:
    derived = classify(system_material, customer_material, downstream_of_lead)
    known = any(m and m != Material.UNKNOWN for m in (system_material, customer_material))
    return ClassificationCheck(
        stated=Status(stated) if stated else None,
        derived=derived,
        portions_known=known,
    )
