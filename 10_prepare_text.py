#!/usr/bin/env python3
"""PyCharm entrypoint: clean and segment input/<novel>/*.txt for TTS."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tts_new.cli import run_prepare  # noqa: E402
from tts_new.config import load_config  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(run_prepare(load_config()))
