import pytest

from pipetrace.inventory import addresses


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("214 Maple Street", "214 MAPLE ST"),
        ("214 maple st.", "214 MAPLE ST"),
        ("214 N. Maple Avenue Apt 2", "214 N MAPLE AVE # 2"),
        ("214 North Maple Ave, #2", "214 N MAPLE AVE # 2"),
        ("12 First Street", "12 1ST ST"),
        ("5 Calle Peña", "5 CALLE PENA"),
        ("7 A & B Road", "7 A AND B RD"),
    ],
)
def test_normalize(raw, expected):
    assert addresses.normalize(raw) == expected


def test_street_line_drops_city_state_zip():
    assert addresses.street_line("214 Maple St, Testville, IL 60000") == "214 Maple St"
    assert addresses.street_line("214 Maple St 60000") == "214 Maple St"


def test_parse_and_display():
    parsed = addresses.parse("214-1/2 Maple St Apt 3")
    assert parsed.house_number == "214-1/2"
    assert parsed.street == "MAPLE ST"
    assert parsed.unit == "3"
    assert addresses.parse("214 1/2 Maple St").house_number == "214 1/2"
    assert addresses.parse("Maple St").house_number == ""
    assert addresses.display_street("214 Maple St Apt 3") == "Maple St"


def q(text):
    return addresses.tokens(addresses.street_line(text))


def test_score_exact_beats_partial():
    candidate = q("214 Maple St")
    assert (
        addresses.score(q("214 Maple St"), candidate) > addresses.score(q("214 Map"), candidate) > 0
    )


def test_score_prefix_and_expansions():
    candidate = q("12 Pine St")
    assert addresses.score(q("12 Pin"), candidate) > 0  # PINE is stored as PNE
    assert addresses.score(q("12 Pine Stre"), candidate) > 0  # typing "Street"
    assert addresses.score(q("1"), q("12 Pine St")) > 0  # house number being typed


def test_score_typos_and_mismatches():
    candidate = q("214 Maple St")
    assert addresses.score(q("214 Mpale St"), candidate) > 0  # transposition
    assert addresses.score(q("214 Mapel"), candidate) > 0
    assert addresses.score(q("215 Maple St"), candidate) == 0  # wrong house number
    assert addresses.score(q("214 Oak St"), candidate) == 0


def test_search_config_shape():
    config = addresses.search_config()
    assert config["abbr"]["STREET"] == "ST"
    assert "APT" in config["units"]
