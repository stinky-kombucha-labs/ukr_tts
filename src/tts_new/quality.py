from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import re

from .util import read_text, write_json_atomic, write_text_atomic


LATIN_RE = re.compile(r"[A-Za-z]{2,}")
MIXED_WORD_RE = re.compile(
    r"\S*[A-Za-z]+['-]?[А-Яа-яІіЇїЄєҐґ]+\S*|"
    r"\S*[А-Яа-яІіЇїЄєҐґ]+['-]?[A-Za-z]+\S*"
)
CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff]+")
RISKY_SYMBOL_RE = re.compile(r"[*#~`_<>{}\\|@^]")
LONG_ROMAN_RE = re.compile(r"(?<![A-Za-zА-Яа-яІіЇїЄєҐґ])([IVXLCDM]{2,})(?![A-Za-zА-Яа-яІіЇїЄєҐґ])")


@dataclass
class TextIssue:
    kind: str
    file: str
    line: int
    value: str
    context: str


@dataclass
class TextStats:
    files: int
    lines: int
    chars: int
    max_line_chars: int
    lines_over_520: int
    issues: list[TextIssue]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["issues"] = [asdict(issue) for issue in self.issues]
        return data


def _add_issue(issues: list[TextIssue], kind: str, path: Path, line_no: int, value: str, line: str) -> None:
    issues.append(
        TextIssue(
            kind=kind,
            file=path.name,
            line=line_no,
            value=value.strip()[:160],
            context=line.strip()[:240],
        )
    )


def analyze_files(files: list[Path], hard_limit: int = 520) -> TextStats:
    issues: list[TextIssue] = []
    total_lines = 0
    total_chars = 0
    max_line = 0
    over_limit = 0

    for path in files:
        text = read_text(path)
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped:
                continue
            total_lines += 1
            total_chars += len(stripped)
            max_line = max(max_line, len(stripped))
            if len(stripped) > hard_limit:
                over_limit += 1
                _add_issue(issues, "line_too_long", path, line_no, str(len(stripped)), stripped)

            for match in MIXED_WORD_RE.findall(stripped):
                _add_issue(issues, "mixed_script_word", path, line_no, match, stripped)
            for match in CJK_RE.findall(stripped):
                _add_issue(issues, "cjk_text", path, line_no, match, stripped)
            for match in RISKY_SYMBOL_RE.findall(stripped):
                _add_issue(issues, "risky_symbol", path, line_no, match, stripped)
            for match in LONG_ROMAN_RE.findall(stripped):
                _add_issue(issues, "roman_or_abbreviation", path, line_no, match, stripped)
            for match in LATIN_RE.findall(stripped):
                _add_issue(issues, "latin_token", path, line_no, match, stripped)

    return TextStats(
        files=len(files),
        lines=total_lines,
        chars=total_chars,
        max_line_chars=max_line,
        lines_over_520=over_limit,
        issues=issues,
    )


def write_quality_report(files: list[Path], report_json: Path, hard_limit: int = 520) -> TextStats:
    stats = analyze_files(files, hard_limit=hard_limit)
    write_json_atomic(report_json, stats.to_dict())

    by_kind: dict[str, int] = {}
    for issue in stats.issues:
        by_kind[issue.kind] = by_kind.get(issue.kind, 0) + 1

    lines = [
        "# Text Quality Report",
        "",
        f"- files: {stats.files}",
        f"- lines: {stats.lines}",
        f"- chars: {stats.chars}",
        f"- max_line_chars: {stats.max_line_chars}",
        f"- lines_over_520: {stats.lines_over_520}",
        f"- issues: {len(stats.issues)}",
        "",
    ]
    if by_kind:
        lines.append("## Issues By Kind")
        lines.append("")
        for kind, count in sorted(by_kind.items()):
            lines.append(f"- {kind}: {count}")
        lines.append("")
        lines.append("## First Issues")
        lines.append("")
        for issue in stats.issues[:80]:
            lines.append(f"- {issue.kind} | {issue.file}:{issue.line} | `{issue.value}`")
    else:
        lines.append("No issues found.")
    write_text_atomic(report_json.with_suffix(".md"), "\n".join(lines) + "\n")
    return stats
