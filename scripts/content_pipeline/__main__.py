"""Content pipeline CLI.

    uv run python -m scripts.content_pipeline <stage> …
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from scripts.content_pipeline import (
    config,
    cut,
    entities,
    ingest,
    normalize,
    redact,
    render,
    transcribe as stt,
    verify,
)

DEFAULT_REGISTRY = "content/registry.yaml"


def load_env_file(repo_root: Path) -> None:
    """Populate os.environ from a repo .env (existing env wins)."""
    env_file = repo_root / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def repo_root(args: argparse.Namespace) -> Path:
    return Path(args.repo_root).resolve()


def work_dir(args: argparse.Namespace) -> Path:
    return repo_root(args) / "content" / ".work" / args.slug


def piece_config(args: argparse.Namespace) -> config.Piece:
    registry = config.load_registry(repo_root(args) / args.registry)
    return registry.piece(args.slug), registry


def cmd_ingest(args: argparse.Namespace) -> int:
    data = ingest.probe(args.video)
    registry = config.load_registry(repo_root(args) / args.registry)
    warnings = ingest.check(data, registry.defaults)
    print(f"{args.video}: {data['width']}x{data['height']} @ {data['fps']} fps, "
          f"{data['duration']:.1f}s, {data['codec']}/{data['pix_fmt']}, "
          f"{data['bit_rate'] // 1000} kbit/s")
    for warning in warnings:
        print(f"WARN: {warning}")
    return 0


def cmd_normalize(args: argparse.Namespace) -> int:
    registry = config.load_registry(repo_root(args) / args.registry)
    video = registry.defaults.get("video", {})
    out = normalize.normalize(
        args.video,
        work_dir(args) / "normalized.mp4",
        max_width=int(video.get("working_max_width", 1920)),
        max_height=int(video.get("working_max_height", 1440)),
        fps=int(video.get("fps", 30)),
    )
    print(f"wrote {out}")
    return 0


def cmd_redact(args: argparse.Namespace) -> int:
    piece, registry = piece_config(args)
    piece_redact = {
        **registry.defaults.get("redact", {}),
        **piece.redact,
    }
    wd = work_dir(args)
    saved = wd / "redaction.json"
    if args.yes and saved.exists():
        # Apply the map the contributor already reviewed; do not regenerate it.
        payload = json.loads(saved.read_text())
    else:
        payload = redact.detect(
            args.video, wd,
            literals=piece_redact.get("literals"),
            prefixes=piece_redact.get("prefixes"),
            ip_prefix=piece_redact.get("ip_replacement_prefix", redact.DEFAULT_IP_PREFIX),
            entities=entities.load(wd),
            style=args.style,
            fps=args.fps,
        )
    mapping = {p["replacement"] for p in payload["patches"]}
    print(f"{len(payload['patches'])} patches, originals: "
          f"{len(payload['originals'])}, replacements: {sorted(mapping)}")
    if not args.yes:
        answer = input("Apply this mapping? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Aborted — review content/.work/"
                  f"{args.slug}/redaction.json and re-run with --yes.")
            return 1
    if args.refine:
        added = redact.refine(args.video, wd, entities=entities.load(wd),
                              rounds=args.refine, fps=args.fps)
        print(f"refine: {added} patches added for text still readable after redaction")
        out = wd / "redacted.mp4"
    else:
        out = redact.apply(args.video, wd)
    print(f"wrote {out}")
    return 0


def cmd_entities(args: argparse.Namespace) -> int:
    from mlox.application.use_cases.project import project_password_env_name

    project = Path(args.project)
    env_name = args.password_env or project_password_env_name(project.stem)
    password = os.environ.get(env_name) or os.environ.get("MLOX_PROJECT_PASSWORD")
    if not password:
        print(f"Set {env_name} (or MLOX_PROJECT_PASSWORD) to the project password.")
        return 2
    found = entities.from_mlox_cli(str(project), password=password)
    out = entities.save(work_dir(args), found)
    print(f"wrote {out}: {len(found)} entities")
    return 0


def cmd_cut(args: argparse.Namespace) -> int:
    wd = work_dir(args)
    made = []
    if args.shots:
        for at in args.shots:
            made.append(cut.screenshot(
                args.video, at, Path(args.out) / f"shot-{at:.0f}s.png", wd))
    if args.gif:
        start, end = float(args.gif[0]), float(args.gif[1])
        registry = config.load_registry(Path(args.registry))
        gif_preset = registry.defaults.get("gif", {})
        made.append(cut.gif(
            args.video, start, end, Path(args.out) / "demo.gif", wd,
            fps=int(gif_preset.get("fps", 12)),
            width=int(gif_preset.get("width", 960))))
    for item in made:
        print(f"wrote {item}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    leaks = verify.verify(args.artifacts, work_dir(args))
    if leaks:
        for leak in leaks:
            print(f"LEAK: {leak}")
        return 1
    print("verify gate passed: no original entities found.")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    piece, _ = piece_config(args)
    timeline_path = work_dir(args) / "timeline.json"
    timeline = None
    if timeline_path.exists():
        timeline = json.loads(timeline_path.read_text())
    for output in piece.outputs:
        if output.get("type") == "article":
            dest = render.publish_article(args.script, repo_root(args) / output["dest"])
            print(f"wrote {dest}")
            return 0
    print("Piece has no article output.")
    return 1


def cmd_transcribe(args: argparse.Namespace) -> int:
    piece, registry = piece_config(args)
    stt_conf = {
        **registry.defaults.get("stt", {}),
        **piece.redact.get("stt", {}),
    }
    work = work_dir(args)
    audio = stt.extract_audio(args.video, work / "audio.ogg")
    segments = stt.transcribe(
        audio,
        model=stt_conf.get("model", stt.DEFAULT_MODEL),
        language=stt_conf.get("language", stt.DEFAULT_LANGUAGE),
        chunk_seconds=float(stt_conf.get("chunk_seconds", 30.0)),
        mode=stt_conf.get("mode", "chunked"),
        work_dir=work,
    )
    transcript, captions = stt.save_transcript(segments, work)
    markers = stt.extract_markers(segments)
    print(f"wrote {transcript} and {captions}")
    for name, at in markers:
        print(f"  chapter {name} @ {at:.0f}s")
    if not markers:
        print("No chapter markers heard — add spoken 'chapter <name>' cues "
              "or edit timeline.json by hand.")
    return 0


def cmd_align(args: argparse.Namespace) -> int:
    from scripts.content_pipeline import align as align_mod

    align_mod.align(args.video, args.script, str(work_dir(args) / "timeline.json"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="content_pipeline")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest")
    p.add_argument("video")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("normalize")
    p.add_argument("video")
    p.add_argument("--slug", required=True)
    p.set_defaults(func=cmd_normalize)

    p = sub.add_parser("entities",
                       help="collect sensitive strings from an MLOX project via the mlox CLI")
    p.add_argument("--slug", required=True)
    p.add_argument("--project", required=True, help="path to the .mlox project file")
    p.add_argument("--password-env",
                   help="env var holding the password (default: MLOX_PROJECT_PASSWORD_<NAME>)")
    p.set_defaults(func=cmd_entities)

    p = sub.add_parser("redact")
    p.add_argument("video")
    p.add_argument("--slug", required=True)
    p.add_argument("--style", choices=redact.STYLES, default="blur",
                   help="blur (default), box (black out) or replace (fake text)")
    p.add_argument("--fps", type=float, default=1.0,
                   help="periodic OCR sampling rate; scene changes are always sampled")
    p.add_argument("--refine", type=int, default=2, metavar="ROUNDS",
                   help="re-OCR the redacted video and patch leftovers (0 disables)")
    p.add_argument("--yes", action="store_true",
                   help="apply without interactive confirmation")
    p.set_defaults(func=cmd_redact)

    p = sub.add_parser("cut")
    p.add_argument("video")
    p.add_argument("--slug", required=True)
    p.add_argument("--shots", type=float, nargs="*", default=[])
    p.add_argument("--gif", nargs=2, metavar=("START", "END"))
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_cut)

    p = sub.add_parser("verify")
    p.add_argument("artifacts", nargs="+")
    p.add_argument("--slug", required=True)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("render")
    p.add_argument("--slug", required=True)
    p.add_argument("--script", required=True)
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("transcribe")
    p.add_argument("video")
    p.add_argument("--slug", required=True)
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("align")
    p.add_argument("video")
    p.add_argument("--slug", required=True)
    p.add_argument("--script", required=True)
    p.set_defaults(func=cmd_align)

    args = parser.parse_args(argv)
    load_env_file(Path(args.repo_root).resolve())
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
