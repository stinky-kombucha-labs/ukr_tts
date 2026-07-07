#!/usr/bin/env python3
"""CLI entrypoint. No arguments: runs the action from config.json (run.action)."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tts_new.cli import main  # noqa: E402


if __name__ == "__main__":
    main()
