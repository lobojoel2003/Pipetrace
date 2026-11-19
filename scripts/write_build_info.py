#!/usr/bin/env python
"""Write pipetrace/_build.json with the CI build number, commit and date.

Run by CI before building wheels or the static demo, so the version shown in the
site footer and /healthz identifies the exact build: ``1.0.0+build.42.3f9a2b1``.

    python scripts/write_build_info.py [--build-number N] [--commit SHA] [--date ISO]

Defaults come from GitHub Actions (GITHUB_RUN_NUMBER, GITHUB_SHA) and today's date.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "pipetrace" / "_build.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--build-number", default=os.environ.get("GITHUB_RUN_NUMBER", ""))
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--date", default=dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    args = parser.parse_args()
    data = {"build_number": args.build_number, "commit": args.commit, "build_date": args.date}
    TARGET.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(
        f"{TARGET.relative_to(Path.cwd()) if TARGET.is_relative_to(Path.cwd()) else TARGET}: {data}"
    )


if __name__ == "__main__":
    main()
