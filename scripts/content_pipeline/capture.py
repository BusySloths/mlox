"""Capture visible Herdr pane snapshots without desktop screen recording."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path


def capture(panes: list[str], out: Path, *, duration: float, interval: float) -> None:
    if duration <= 0 or interval <= 0:
        raise ValueError("duration and interval must be positive")
    out.mkdir(parents=True, exist_ok=True)
    previous: dict[str, str] = {}
    started = time.monotonic()
    with (out / "frames.jsonl").open("a", encoding="utf-8") as index:
        while time.monotonic() - started < duration:
            for pane in panes:
                result = subprocess.run(
                    ["herdr", "pane", "read", pane, "--source", "visible", "--format", "ansi"],
                    capture_output=True, check=True,
                )
                digest = hashlib.sha256(result.stdout).hexdigest()
                if previous.get(pane) == digest:
                    continue
                name = re.sub(r"[^\w-]", "_", pane)
                filename = f"{time.time_ns()}_{name}.ansi"
                (out / filename).write_bytes(result.stdout)
                index.write(json.dumps({"file": filename, "pane": pane,
                                        "elapsed": time.monotonic() - started}) + "\n")
                index.flush()
                previous[pane] = digest
            time.sleep(min(interval, max(0, duration - (time.monotonic() - started))))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pane", action="append", required=True, dest="panes")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=5400)
    parser.add_argument("--interval", type=float, default=2)
    args = parser.parse_args(argv)
    try:
        capture(args.panes, args.out, duration=args.duration, interval=args.interval)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
