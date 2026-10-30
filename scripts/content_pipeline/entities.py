"""Entities stage: ground-truth sensitive strings from the MLOX project.

OCR detection only finds what it can read; this list is what *must not* be
readable. It is built from the mlox CLI's JSON server/service listings and
feeds both `redact` (matching) and `verify` (the publish gate).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

FILENAME = "entities.json"
MIN_LEN = 5  # shorter tokens ("tool", "dev") are too generic to redact

IPV4_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b")
GIT_SSH_RE = re.compile(r"git@[\w.-]+:([\w.-]+)/([\w.-]+?)(?:\.git)?(?=$|[@/\s])")
GIT_HTTPS_RE = re.compile(
    r"https?://(?:github\.com|gitlab\.com|bitbucket\.org)/([\w.-]+)/([\w.-]+?)(?:\.git)?(?=$|[/\s])")
URL_RE = re.compile(r"[a-z][a-z0-9+.-]*://[^\s]+", re.IGNORECASE)

SAFE_IP_PREFIXES = ("127.", "0.", "198.51.100.", "192.0.2.", "203.0.113.")
PUBLIC_HOSTS = {
    "localhost", "github.com", "gitlab.com", "bitbucket.org", "docker.io",
    "ghcr.io", "quay.io", "registry.k8s.io", "mlflow.org", "pypi.org",
}


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _from_text(text: str) -> tuple[set[str], set[str]]:
    """Return (identities, tokens); identities are kept regardless of length."""
    found: set[str] = set()
    owners: set[str] = set()
    for ip in IPV4_RE.findall(text):
        if not ip.startswith(SAFE_IP_PREFIXES):
            found.add(ip)
    for owner, repo in GIT_SSH_RE.findall(text) + GIT_HTTPS_RE.findall(text):
        owners.add(owner)
        found.add(repo)
    for url in URL_RE.findall(text):
        host = (urlparse(url).hostname or "").lower()
        if host and not IPV4_RE.fullmatch(host) and host not in PUBLIC_HOSTS:
            found.add(host)
    for email in EMAIL_RE.findall(text):
        if not email.startswith("git@"):
            owners.add(email)
    return owners, found


def extract(servers: list[dict], services: list[dict]) -> list[str]:
    """Sensitive strings in mlox CLI server/service listings, sorted."""
    keep: set[str] = set()
    for text in _strings([servers, services]):
        owners, tokens = _from_text(text)
        keep |= owners | {t for t in tokens if len(t) >= MIN_LEN}
    return sorted(keep, key=str.lower)


def _cli_json(args: list[str], env: dict[str, str]) -> dict:
    cmd = [sys.executable, "-m", "mlox.cli", "--output", "json", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {}
    if proc.returncode != 0 or not payload.get("success"):
        raise RuntimeError(
            f"mlox {' '.join(args)} failed: {payload.get('message') or proc.stderr.strip()}")
    return payload["data"]


def from_mlox_cli(project: str, *, password: str) -> list[str]:
    """Run the mlox CLI against a project and extract its entities.

    The password travels via the environment, never via argv.
    """
    env = {**os.environ, "MLOX_PROJECT_PATH": project, "MLOX_PROJECT_PASSWORD": password}
    servers = _cli_json(["server", "list"], env)["servers"]
    services = _cli_json(["service", "list"], env)["services"]
    return extract(servers, services)


def save(work_dir: Path, found: list[str]) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / FILENAME
    out.write_text(json.dumps({"entities": sorted(set(found), key=str.lower)}, indent=2))
    return out


def load(work_dir: Path) -> list[str]:
    path = work_dir / FILENAME
    if not path.exists():
        return []
    return json.loads(path.read_text())["entities"]
