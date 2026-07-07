from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"

RUN_ACTIONS = ("doctor", "prepare", "synth", "verify", "full")


@dataclass(frozen=True)
class EngineConfig:
    vendor_dir: Path
    model_dir: Path
    voice: str
    stress: str
    device: str


@dataclass(frozen=True)
class TextConfig:
    target_chars: int
    hard_limit_chars: int


@dataclass(frozen=True)
class AudioConfig:
    workers: int
    bitrate: str
    min_size_kb: int
    min_duration_sec: int


@dataclass(frozen=True)
class RunConfig:
    action: str
    force: bool
    limit: int | None


@dataclass(frozen=True)
class AppConfig:
    root: Path
    input_dir: Path
    output_dir: Path
    work_dir: Path
    engine: EngineConfig
    text: TextConfig
    audio: AudioConfig
    run: RunConfig


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (root / path).resolve()


def load_config(config_path: Path | None = None) -> AppConfig:
    config_path = config_path or DEFAULT_CONFIG_PATH
    root = config_path.resolve().parent

    with config_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    dirs = raw.get("dirs", {})
    engine_raw = raw.get("engine", {})
    text_raw = raw.get("text", {})
    audio_raw = raw.get("audio", {})
    run_raw = raw.get("run", {})

    action = str(run_raw.get("action", "full")).lower().strip()
    if action not in RUN_ACTIONS:
        raise ValueError(f"run.action must be one of: {', '.join(RUN_ACTIONS)}")

    return AppConfig(
        root=root,
        input_dir=_resolve_path(root, dirs.get("input", "input")),
        output_dir=_resolve_path(root, dirs.get("output", "output")),
        work_dir=_resolve_path(root, dirs.get("work", "work")),
        engine=EngineConfig(
            vendor_dir=_resolve_path(root, engine_raw.get("vendor_dir", "vendor")),
            model_dir=_resolve_path(root, engine_raw.get("model_dir", "models")),
            voice=str(engine_raw.get("voice", "oleksa")),
            stress=str(engine_raw.get("stress", "dictionary")),
            device=str(engine_raw.get("device", "cuda")),
        ),
        text=TextConfig(
            target_chars=int(text_raw.get("target_chars", 450)),
            hard_limit_chars=int(text_raw.get("hard_limit_chars", 520)),
        ),
        audio=AudioConfig(
            workers=max(1, int(audio_raw.get("workers", 3))),
            bitrate=str(audio_raw.get("bitrate", "192k")),
            min_size_kb=int(audio_raw.get("min_size_kb", 500)),
            min_duration_sec=int(audio_raw.get("min_duration_sec", 30)),
        ),
        run=RunConfig(
            action=action,
            force=bool(run_raw.get("force", False)),
            limit=None if run_raw.get("limit") is None else int(run_raw.get("limit")),
        ),
    )
