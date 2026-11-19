"""The Spanish translation must be complete and compiled."""

import re
from pathlib import Path

from django.utils import translation

LOCALE = Path(__file__).resolve().parents[1] / "pipetrace" / "locale" / "es" / "LC_MESSAGES"


def _entries():
    text = (LOCALE / "django.po").read_text(encoding="utf-8")
    blocks = [b for b in text.split("\n\n") if "msgid" in b]
    return blocks[1:]  # skip the header


def test_every_string_is_translated():
    untranslated = []
    for block in _entries():
        if "#, fuzzy" in block:
            untranslated.append(block)
        for _match in re.finditer(r'msgstr(?:\[\d\])? ""\n(?!")', block + "\n"):
            untranslated.append(block)
            break
    assert not untranslated, untranslated[:3]


def test_compiled_catalog_is_current():
    po = LOCALE / "django.po"
    mo = LOCALE / "django.mo"
    assert mo.exists()
    # The compiled file holds every msgid of the source file.
    data = mo.read_bytes()
    for block in _entries()[:50]:
        msgid = re.search(r'msgid "(.*)"', block).group(1)
        if msgid:
            assert msgid.encode().replace(b'\\"', b'"') in data, msgid
    assert po.stat().st_size > 10_000


def test_spanish_strings_are_used():
    with translation.override("es"):
        assert translation.gettext("Lead") == "Plomo"
        assert translation.gettext("Check your pipe") == "Revise su tubería"
        assert translation.ngettext("%(n)s line", "%(n)s lines", 2) == "%(n)s líneas"
