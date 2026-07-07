from __future__ import annotations

from pathlib import Path

from .config import AppConfig
from .paths import NovelPaths, ensure_novel_dirs
from .util import write_json_atomic, write_text_atomic


def _duration_ms(path: Path) -> tuple[int | None, str | None]:
    try:
        from pydub import AudioSegment

        return len(AudioSegment.from_file(path, format="mp3")), None
    except Exception as exc:
        return None, repr(exc)


def verify_novel(config: AppConfig, paths: NovelPaths) -> dict:
    """Every known chapter (input, prepared or processed) must have a healthy MP3."""
    ensure_novel_dirs(paths)
    stems = sorted(
        {txt.stem for folder in (paths.input, paths.prepared, paths.processed) for txt in folder.glob("*.txt")}
    )

    rows: list[dict] = []
    issue_count = 0
    for stem in stems:
        mp3 = paths.output / f"{stem}.mp3"
        row: dict = {"chapter": stem, "mp3": str(mp3), "issues": []}
        if not mp3.exists():
            row["issues"].append("missing_mp3")
        else:
            size_kb = mp3.stat().st_size / 1024
            row["size_kb"] = round(size_kb, 1)
            if size_kb < config.audio.min_size_kb:
                row["issues"].append("short_size")

            duration_ms, error = _duration_ms(mp3)
            if error:
                row["issues"].append("corrupt_or_unreadable")
                row["audio_error"] = error
            else:
                row["duration_sec"] = round(duration_ms / 1000, 2)
                if duration_ms < config.audio.min_duration_sec * 1000:
                    row["issues"].append("short_duration")

        issue_count += len(row["issues"])
        rows.append(row)

    known = set(stems)
    orphans = sorted(mp3.name for mp3 in paths.output.glob("*.mp3") if mp3.stem not in known)

    report = {
        "novel": paths.name,
        "chapters": len(stems),
        "audio_files": len(list(paths.output.glob("*.mp3"))),
        "issue_count": issue_count,
        "orphan_mp3s": orphans,
        "rows": rows,
    }
    write_json_atomic(paths.reports / "integrity_report.json", report)

    md = [
        "# Integrity Report",
        "",
        f"- novel: {paths.name}",
        f"- chapters: {report['chapters']}",
        f"- audio_files: {report['audio_files']}",
        f"- issue_count: {issue_count}",
        "",
    ]
    for row in rows:
        if row["issues"]:
            md.append(f"- {row['chapter']}: {', '.join(row['issues'])}")
    for orphan in orphans:
        md.append(f"- orphan mp3 without source text: {orphan}")
    if issue_count == 0 and not orphans:
        md.append("No issues found.")
    write_text_atomic(paths.reports / "integrity_report.md", "\n".join(md) + "\n")
    return report
