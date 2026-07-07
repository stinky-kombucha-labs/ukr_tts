#!/usr/bin/env python3
"""PyCharm entrypoint: render prepared chapters to output/<novel>/*.mp3, then verify."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tts_new.cli import run_synth, run_verify  # noqa: E402
from tts_new.config import load_config  # noqa: E402


if __name__ == "__main__":
    config = load_config()
    code = run_synth(config, force=config.run.force, limit=config.run.limit)
    raise SystemExit(code or run_verify(config))
