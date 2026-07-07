from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import shutil
import sys

from .audio_engine import missing_model_files
from .config import AppConfig, load_config
from .integrity import verify_novel
from .paths import discover_novels, novel_paths
from .prepare import prepare_novel
from .synthesize import synthesize_novels


def doctor(config: AppConfig) -> int:
    failed = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failed
        print(f"{'OK     ' if ok else 'MISSING'} {label}{': ' + detail if detail else ''}")
        if not ok:
            failed += 1

    check("engine code", (config.engine.vendor_dir / "ukrainian_tts").is_dir(), str(config.engine.vendor_dir))
    missing = missing_model_files(config.engine.model_dir)
    check(
        "model files",
        not missing,
        str(config.engine.model_dir) + (f" (missing: {', '.join(missing)} — will be downloaded on first run)" if missing else ""),
    )
    check("ffmpeg", shutil.which("ffmpeg") is not None)
    try:
        import pydub  # noqa: F401

        check("pydub", True)
    except Exception as exc:
        check("pydub", False, repr(exc))
    try:
        import torch

        check("torch", True, torch.__version__)
        if config.engine.device.startswith("cuda"):
            check("cuda device", torch.cuda.is_available())
    except Exception as exc:
        check("torch", False, repr(exc))

    novels = discover_novels(config)
    print(f"novels found: {', '.join(novels) if novels else '(none — put chapters into input/<novel>/)'}")
    return 1 if failed else 0


def _novels(config: AppConfig, only: str | None) -> list:
    names = discover_novels(config, only)
    if not names:
        print("Nothing to do: put .txt chapters into input/<novel>/")
    return [novel_paths(config, name) for name in names]


def run_prepare(config: AppConfig, only: str | None = None) -> int:
    for paths in _novels(config, only):
        report = prepare_novel(config, paths)
        print(
            f"[{paths.name}] prepared {report['prepared_files']} file(s), "
            f"quality issues: {report['quality_issues']}"
        )
    return 0


def run_synth(
    config: AppConfig,
    only: str | None = None,
    workers: int | None = None,
    force: bool = False,
    limit: int | None = None,
) -> int:
    novels = _novels(config, only)
    if not novels:
        return 0
    report = synthesize_novels(config, novels, workers=workers, force=force, limit=limit)
    print(f"synthesis: {report['status_counts']} in {report['seconds']}s")
    bad = sum(report["status_counts"].get(s, 0) for s in ("failed", "crashed"))
    return 1 if bad else 0


def run_verify(config: AppConfig, only: str | None = None) -> int:
    issues = 0
    for paths in _novels(config, only):
        report = verify_novel(config, paths)
        issues += report["issue_count"]
        print(
            f"[{paths.name}] chapters: {report['chapters']}, "
            f"mp3: {report['audio_files']}, issues: {report['issue_count']}"
        )
    return 1 if issues else 0


def run_full(
    config: AppConfig,
    only: str | None = None,
    workers: int | None = None,
    force: bool = False,
    limit: int | None = None,
) -> int:
    run_prepare(config, only)
    code = run_synth(config, only, workers=workers, force=force, limit=limit)
    verify_code = run_verify(config, only)
    return code or verify_code


def run_configured_action(config: AppConfig) -> int:
    action = config.run.action
    print(f"action: {action}")
    if action == "doctor":
        return doctor(config)
    if action == "prepare":
        return run_prepare(config)
    if action == "synth":
        return run_synth(config, force=config.run.force, limit=config.run.limit)
    if action == "verify":
        return run_verify(config)
    return run_full(config, force=config.run.force, limit=config.run.limit)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="tts_new",
        description="Convert input/<novel>/*.txt chapters into output/<novel>/*.mp3.",
    )
    parser.add_argument("--config", help="Path to config.json")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check engine, models and runtime dependencies.")

    p = sub.add_parser("prepare", help="Build TTS-ready text in work/<novel>/prepared/.")
    p.add_argument("--novel", help="Only this novel (default: all).")

    p = sub.add_parser("synth", help="Render prepared chapters to MP3.")
    p.add_argument("--novel", help="Only this novel (default: all).")
    p.add_argument("--workers", type=int, help="Override audio.workers.")
    p.add_argument("--force", action="store_true", help="Re-render existing MP3s.")
    p.add_argument("--limit", type=int, help="Render only the first N chapters.")

    p = sub.add_parser("verify", help="Verify that every chapter has a healthy MP3.")
    p.add_argument("--novel", help="Only this novel (default: all).")

    p = sub.add_parser("full", help="prepare + synth + verify.")
    p.add_argument("--novel", help="Only this novel (default: all).")
    p.add_argument("--workers", type=int)
    p.add_argument("--force", action="store_true")
    p.add_argument("--limit", type=int)
    return parser


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    try:
        if not argv:
            config = load_config()
            raise SystemExit(run_configured_action(config))

        parser = build_parser()
        args = parser.parse_args(argv)
        config = load_config(Path(args.config) if args.config else None)

        if args.command == "doctor":
            raise SystemExit(doctor(config))
        if args.command == "prepare":
            raise SystemExit(run_prepare(config, args.novel))
        if args.command == "synth":
            raise SystemExit(
                run_synth(config, args.novel, workers=args.workers, force=args.force, limit=args.limit)
            )
        if args.command == "verify":
            raise SystemExit(run_verify(config, args.novel))
        raise SystemExit(
            run_full(config, args.novel, workers=args.workers, force=args.force, limit=args.limit)
        )
    except KeyboardInterrupt:
        raise SystemExit(130)
