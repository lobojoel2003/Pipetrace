#!/usr/bin/env python
"""Prepare a release: bump the version and date the changelog.

    python scripts/release.py 1.1.0

1. Sets ``__version__`` in pipetrace/__init__.py.
2. Turns the "Unreleased" section of CHANGELOG.md into "[1.1.0] - <today>" and adds
   a fresh empty "Unreleased" section and compare links.
3. Prints the git commands that commit, tag and push. Pushing the tag ``v1.1.0``
   (or running the Release workflow by hand with the version) tests, builds and
   publishes everything.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "pipetrace" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"
REPO = "https://github.com/lobojoel2003/Pipetrace"
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def current_version() -> str:
    return re.search(r'__version__ = "([^"]+)"', INIT.read_text()).group(1)


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not SEMVER.match(argv[0]):
        print(__doc__)
        return 2
    new = argv[0]
    old = current_version()
    if new == old:
        print(f"Already at {new}.")
        return 1
    INIT.write_text(INIT.read_text().replace(f'"{old}"', f'"{new}"'))

    text = CHANGELOG.read_text()
    if "## [Unreleased]" not in text:
        print("CHANGELOG.md has no '## [Unreleased]' section.")
        return 1
    today = dt.date.today().isoformat()
    text = text.replace("## [Unreleased]", f"## [Unreleased]\n\n## [{new}] - {today}", 1)
    text = re.sub(
        r"^\[Unreleased\]: .*$",
        f"[Unreleased]: {REPO}/compare/v{new}...HEAD\n[{new}]: {REPO}/compare/v{old}...v{new}",
        text,
        count=1,
        flags=re.M,
    )
    CHANGELOG.write_text(text)
    print(f"Version {old} -> {new}. Review CHANGELOG.md, then:\n")
    print(f'  git commit -am "Release {new}"')
    print(f'  git tag -a v{new} -m "Pipetrace {new}"')
    print("  git push origin main --follow-tags")
    print(f"\nor push main and run Actions -> Release -> Run workflow with version {new}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
