#!/usr/bin/env python3
"""Enforce documentation governance in CI.

Checks that derived documentation has not drifted from its source and that
volatile facts are not hand-maintained where a source of truth exists.

Checks:
1. Regenerates `docs/SERVICES_CATALOG.md` and `wiki/Services-Catalog.md` from
   the YAML configs and fails if the committed files differ (i.e. run the
   generator and commit the result).
2. Forbids hardcoded volatile stats / hand-written catalog content in README,
   CLAUDE.md, and wiki Home that belong to the doctrine file or the generated
   catalog.
3. Ensures `docs/DOCTRINE.md` and `docs/SERVICES_CATALOG.md` exist.

Usage:

    python scripts/check_docs.py [--fix]

``--fix`` regenerates the catalog in place instead of failing.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "scripts" / "generate_service_catalog.py"
DOCTRINE = REPO_ROOT / "docs" / "DOCTRINE.md"
CATALOG = REPO_ROOT / "docs" / "SERVICES_CATALOG.md"

# Surfaces that must never hand-maintain facts. Regex loosely catches numbers
# that smell like catalogs/stats (e.g. "36 service configs") and stale
# hand-written catalog tables.
FORBIDDEN_STALE_PATTERNS: dict[str, list[str]] = {
    "README.md": [
        r"\|\s*(?:ML Platforms|Model Serving|LLMs & Inference|Kubernetes Add-ons)",
    ],
    "CLAUDE.md": [
        r"\d+\s+unit test func",
        r"~\d+\s+commits/",
        r"\d+\s+built-ins",
        r"\d+\s+integration test file",
    ],
    "wiki/Home.md": [
        r"\|\s*(?:ML Platforms|Model Serving|LLMs & Inference|Kubernetes Add-ons)",
    ],
}


def _run_generator() -> int:
    """Regenerate the catalog; returns process return code."""
    proc = subprocess.run(
        [sys.executable, str(GENERATOR)], cwd=str(REPO_ROOT), capture_output=True
    )
    print(proc.stdout.decode(), end="")
    if proc.returncode != 0:
        print(proc.stderr.decode(), end="", file=sys.stderr)
    return proc.returncode


def _check_catalog_regenerated() -> int:
    """Regenerate into a temp state and compare against committed files."""
    proc = subprocess.run(
        [sys.executable, str(GENERATOR)],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    if proc.returncode != 0:
        print(proc.stderr.decode(), end="", file=sys.stderr)
        print("::error::Catalog generator failed.", file=sys.stderr)
        return 1

    diff = subprocess.run(
        ["git", "diff", "--exit-code", "--", "docs/SERVICES_CATALOG.md",
         "wiki/Services-Catalog.md"],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    if diff.returncode != 0:
        print(
            "::error::Generated catalog is out of sync. Run "
            "`python scripts/generate_service_catalog.py` and commit the result.",
            file=sys.stderr,
        )
        return 1
    return 0


def _check_required_files() -> int:
    failures = 0
    for label, path in (("Doctrine", DOCTRINE), ("Catalog", CATALOG)):
        if not path.exists():
            print(f"::error::Missing {label}: {path.relative_to(REPO_ROOT)}")
            failures += 1
    return 1 if failures else 0


def _check_no_stale_patterns() -> int:
    failures = 0
    for rel, patterns in FORBIDDEN_STALE_PATTERNS.items():
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for pattern in patterns:
            if re.search(pattern, content, flags=re.IGNORECASE):
                print(
                    f"::error::{rel} contains a forbidden hand-maintained fact: "
                    f"`{pattern}`. Move it to docs/DOCTRINE.md or the generated catalog.",
                    file=sys.stderr,
                )
                failures += 1
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Regenerate the catalog in place instead of failing on drift.",
    )
    args = parser.parse_args()

    if args.fix:
        return _run_generator()

    failures = 0
    failures += _check_required_files()
    failures += _check_catalog_regenerated()
    failures += _check_no_stale_patterns()

    if failures:
        print(f"::error::Documentation governance check failed ({failures} issue(s)).")
        return 1
    print("OK: documentation is in sync with its sources of truth.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
