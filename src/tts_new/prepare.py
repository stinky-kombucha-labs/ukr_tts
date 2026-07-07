from __future__ import annotations

from time import time

from .config import AppConfig
from .paths import NovelPaths, ensure_novel_dirs
from .quality import write_quality_report
from .text import load_glossary, prepare_text
from .util import read_text, sha256_file, write_json_atomic, write_text_atomic


def prepare_novel(config: AppConfig, paths: NovelPaths) -> dict:
    """Turn input/<novel>/*.txt into TTS-ready work/<novel>/prepared/*.txt."""
    ensure_novel_dirs(paths)
    input_files = sorted(paths.input.glob("*.txt"))
    glossary = load_glossary(config.root / "glossary.json")

    started = time()
    rows: list[dict] = []
    for src in input_files:
        original = read_text(src)
        prepared = prepare_text(original, config.text, glossary)
        write_text_atomic(paths.prepared / src.name, prepared.text)
        rows.append(
            {
                "file": src.name,
                "input_sha256": sha256_file(src),
                "input_chars": len(original),
                "prepared_lines": len(prepared.lines),
                "prepared_chars": len(prepared.text),
                "max_line_chars": prepared.max_line_chars,
                "dropped_lines": prepared.dropped_lines,
                "glossary_replacements": prepared.glossary_replacements,
            }
        )

    quality = write_quality_report(
        sorted(paths.prepared.glob("*.txt")),
        paths.reports / "prepared_quality.json",
        hard_limit=config.text.hard_limit_chars,
    )

    report = {
        "novel": paths.name,
        "input_files": len(input_files),
        "prepared_files": len(rows),
        "seconds": round(time() - started, 3),
        "quality_issues": len(quality.issues),
        "rows": rows,
    }
    write_json_atomic(paths.reports / "prepare_report.json", report)
    return report
