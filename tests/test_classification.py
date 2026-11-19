import pytest

from pipetrace.inventory.choices import Status
from pipetrace.inventory.classification import check_classification, classify


@pytest.mark.parametrize(
    ("system", "customer", "history", "expected"),
    [
        ("lead", "copper", None, Status.LEAD),
        ("copper", "lead", None, Status.LEAD),
        ("unknown", "lead", None, Status.LEAD),
        ("copper", "galvanized", None, Status.GRR),
        ("copper", "galvanized", "yes", Status.GRR),
        ("copper", "galvanized", "unknown", Status.GRR),
        ("copper", "galvanized", "no", Status.NON_LEAD),
        ("unknown", "galvanized", "no", Status.GRR),  # upstream unknown: still GRR
        ("galvanized", "galvanized", "no", Status.NON_LEAD),
        ("copper", "copper", None, Status.NON_LEAD),
        ("plastic", "iron", None, Status.NON_LEAD),
        ("non_lead", "other_non_lead", None, Status.NON_LEAD),
        ("copper", "unknown", None, Status.UNKNOWN),
        ("", "", None, Status.UNKNOWN),
        (None, "copper", None, Status.UNKNOWN),
    ],
)
def test_classify(system, customer, history, expected):
    assert classify(system, customer, history) == expected


def test_stated_classification_wins():
    check = check_classification("lead", "copper", "copper")
    assert check.final == Status.LEAD
    assert check.conflict


def test_no_conflict_without_portion_detail():
    check = check_classification("lead", "", "")
    assert check.final == Status.LEAD
    assert not check.conflict


def test_galvanized_with_known_history_is_not_a_conflict():
    check = check_classification("non_lead", "copper", "galvanized")
    assert check.derived == Status.GRR
    assert not check.conflict


def test_derived_used_when_not_stated():
    check = check_classification(None, "copper", "galvanized", "yes")
    assert check.final == Status.GRR
