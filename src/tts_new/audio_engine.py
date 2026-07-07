from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
import os
import sys

from .config import PROJECT_ROOT, EngineConfig


MODEL_FILES = ("model.pth", "config.yaml", "spk_xvector.ark", "feats_stats.npz")
DEPS_DIR = PROJECT_ROOT / "deps"


def missing_model_files(model_dir: Path) -> list[str]:
    return [name for name in MODEL_FILES if not (model_dir / name).exists()]


class UkrainianTTSEngine:
    """Thin adapter around the vendored ukrainian_tts package."""

    def __init__(self, engine: EngineConfig) -> None:
        vendor_dir = engine.vendor_dir.resolve()
        self._model_dir = engine.model_dir.resolve()
        self._voice = engine.voice
        self._stress = engine.stress

        if not (vendor_dir / "ukrainian_tts").is_dir():
            raise FileNotFoundError(f"Vendored engine not found: {vendor_dir / 'ukrainian_tts'}")
        if str(vendor_dir) not in sys.path:
            sys.path.insert(0, str(vendor_dir))
        # deps/ holds pip packages that must shadow older copies in the venv
        # (e.g. ukrainian-word-stress 1.1.1 with a richer accent dictionary).
        if DEPS_DIR.is_dir() and str(DEPS_DIR) not in sys.path:
            sys.path.insert(0, str(DEPS_DIR))

        from ukrainian_tts.tts import TTS  # type: ignore

        # If model files are absent, upstream TTS() downloads them (~430 MB)
        # into model_dir from the ukrainian-tts GitHub release.
        self._model_dir.mkdir(parents=True, exist_ok=True)

        # Upstream config.yaml refers to feats_stats.npz by a relative path,
        # so the engine must be constructed and used with cwd = model_dir.
        with self._model_cwd():
            self._tts = TTS(cache_folder=str(self._model_dir), device=engine.device)

    @contextmanager
    def _model_cwd(self):
        previous = Path.cwd()
        os.chdir(self._model_dir)
        try:
            yield
        finally:
            os.chdir(previous)

    def render_wav(self, text: str) -> tuple[BytesIO, str]:
        buffer = BytesIO()
        # Upstream prints an RTF line per call; silence it to keep logs readable.
        with self._model_cwd(), redirect_stdout(StringIO()):
            output, normalized_text = self._tts.tts(text, self._voice, self._stress, buffer)
        output.seek(0)
        return output, normalized_text
