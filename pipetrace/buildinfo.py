"""Version and build metadata.

The version comes from :data:`pipetrace.__version__`. Build metadata (CI build
number, git commit, build date) is injected at build time, either through
environment variables (``PIPETRACE_BUILD_NUMBER``, ``PIPETRACE_GIT_SHA``,
``PIPETRACE_BUILD_DATE``) or a ``pipetrace/_build.json`` file written by CI and
the Docker build. Environment variables win over the file.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from pipetrace import __version__

BUILD_FILE = Path(__file__).with_name("_build.json")


@dataclass(frozen=True)
class BuildInfo:
    version: str
    build_number: str
    commit: str
    build_date: str

    @property
    def short_commit(self) -> str:
        return self.commit[:7]

    @property
    def full_version(self) -> str:
        """SemVer string with build metadata, e.g. ``1.0.0+build.42.3f9a2b1``."""
        meta = []
        if self.build_number:
            meta.append(f"build.{self.build_number}")
        if self.short_commit:
            meta.append(self.short_commit)
        return f"{self.version}+{'.'.join(meta)}" if meta else self.version

    @property
    def label(self) -> str:
        """Human-readable label for page footers, e.g. ``v1.0.0 (build 42)``."""
        label = f"v{self.version}"
        if self.build_number:
            label += f" (build {self.build_number})"
        return label

    def as_dict(self) -> dict[str, str]:
        data = asdict(self)
        data["full_version"] = self.full_version
        return data


def _read_build_file() -> dict[str, str]:
    try:
        return json.loads(BUILD_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=1)
def get_build_info() -> BuildInfo:
    file_data = _read_build_file()

    def pick(env: str, key: str) -> str:
        return (os.environ.get(env) or str(file_data.get(key) or "")).strip()

    return BuildInfo(
        version=__version__,
        build_number=pick("PIPETRACE_BUILD_NUMBER", "build_number"),
        commit=pick("PIPETRACE_GIT_SHA", "commit"),
        build_date=pick("PIPETRACE_BUILD_DATE", "build_date"),
    )
