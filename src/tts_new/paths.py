from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .config import AppConfig


NOVEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class NovelPaths:
    name: str
    input: Path
    output: Path
    prepared: Path
    processed: Path
    failed: Path
    reports: Path


def validate_novel_name(name: str) -> str:
    if not NOVEL_NAME_RE.match(name):
        raise ValueError(
            f"Bad novel folder name: {name!r}. Use only letters, digits, dot, "
            "underscore and dash; start with a letter or digit."
        )
    return name


def novel_paths(config: AppConfig, name: str) -> NovelPaths:
    name = validate_novel_name(name)
    work = config.work_dir / name
    return NovelPaths(
        name=name,
        input=config.input_dir / name,
        output=config.output_dir / name,
        prepared=work / "prepared",
        processed=work / "processed",
        failed=work / "failed",
        reports=work / "reports",
    )


def ensure_novel_dirs(paths: NovelPaths) -> None:
    for folder in (
        paths.input,
        paths.output,
        paths.prepared,
        paths.processed,
        paths.failed,
        paths.reports,
    ):
        folder.mkdir(parents=True, exist_ok=True)


def _subdirs(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {child.name for child in root.iterdir() if child.is_dir()}


def discover_novels(config: AppConfig, only: str | None = None) -> list[str]:
    """Novels are subfolders of input/; work/ and output/ keep finished ones visible."""
    names = _subdirs(config.input_dir) | _subdirs(config.work_dir) | _subdirs(config.output_dir)
    if only is not None:
        validate_novel_name(only)
        if only not in names:
            raise FileNotFoundError(f"Novel not found in input/, work/ or output/: {only}")
        names = {only}
    for name in names:
        validate_novel_name(name)

    loose = sorted(config.input_dir.glob("*.txt")) if config.input_dir.is_dir() else []
    if loose:
        raise ValueError(
            "Found .txt files directly in input/. Put chapters into a subfolder, "
            f"e.g. input/my-novel/{loose[0].name}"
        )
    return sorted(names)
