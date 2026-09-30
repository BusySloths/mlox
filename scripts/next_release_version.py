#!/usr/bin/env python3
"""Calculate or validate a stable semantic release tag."""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from typing import Iterable


TAG_PATTERN = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


@dataclass(frozen=True, order=True)
class StableVersion:
    """A stable semantic version without prerelease or build metadata."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "StableVersion":
        match = TAG_PATTERN.fullmatch(value.strip())
        if not match:
            raise ValueError(
                f"Invalid stable release tag {value!r}; expected vMAJOR.MINOR.PATCH."
            )
        return cls(*(int(part) for part in match.groups()))

    @property
    def version(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def tag(self) -> str:
        return f"v{self.version}"

    def bump(self, kind: str) -> "StableVersion":
        if kind == "major":
            return StableVersion(self.major + 1, 0, 0)
        if kind == "minor":
            return StableVersion(self.major, self.minor + 1, 0)
        if kind == "patch":
            return StableVersion(self.major, self.minor, self.patch + 1)
        raise ValueError(f"Unsupported release bump {kind!r}.")


def latest_stable_version(tags: Iterable[str]) -> StableVersion:
    """Return the highest stable version, defaulting to 0.0.0 for a new project."""

    versions: list[StableVersion] = []
    for tag in tags:
        try:
            versions.append(StableVersion.parse(tag))
        except ValueError:
            continue
    return max(versions, default=StableVersion(0, 0, 0))


def git_tags() -> list[str]:
    result = subprocess.run(
        ["git", "tag", "--list"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def release_version(
    bump: str,
    *,
    resume_tag: str | None = None,
    tags: Iterable[str] | None = None,
) -> StableVersion:
    """Resolve an explicit recovery tag or calculate the next stable version."""

    if resume_tag:
        return StableVersion.parse(resume_tag)
    return latest_stable_version(tags if tags is not None else git_tags()).bump(bump)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bump", required=True, choices=("major", "minor", "patch"))
    parser.add_argument(
        "--resume-tag",
        help="Reuse an existing stable tag after a partially completed release.",
    )
    parser.add_argument(
        "--format",
        choices=("tag", "version"),
        default="tag",
        dest="output_format",
    )
    args = parser.parse_args()

    resolved = release_version(args.bump, resume_tag=args.resume_tag)
    print(resolved.tag if args.output_format == "tag" else resolved.version)


if __name__ == "__main__":
    main()
