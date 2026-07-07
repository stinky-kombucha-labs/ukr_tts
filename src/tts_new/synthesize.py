from __future__ import annotations

from multiprocessing import Process, Queue, set_start_method
from pathlib import Path
from time import time
import os
import queue
import shutil
import traceback

from .config import AppConfig
from .paths import NovelPaths, ensure_novel_dirs
from .util import load_json, read_text, sha256_file, write_json_atomic


DURATION_TOLERANCE_MS = 2_000


def _engine_payload(config: AppConfig) -> dict:
    return {
        "vendor_dir": str(config.engine.vendor_dir),
        "model_dir": str(config.engine.model_dir),
        "voice": config.engine.voice,
        "stress": config.engine.stress,
        "device": config.engine.device,
        "bitrate": config.audio.bitrate,
        "min_size_kb": config.audio.min_size_kb,
        "min_duration_sec": config.audio.min_duration_sec,
        "cpu_threads_per_worker": max(1, (os.cpu_count() or 4) // max(1, config.audio.workers)),
    }


def _paths_payload(paths: NovelPaths) -> dict:
    return {
        "input": str(paths.input),
        "output": str(paths.output),
        "prepared": str(paths.prepared),
        "processed": str(paths.processed),
        "failed": str(paths.failed),
        "reports": str(paths.reports),
    }


def _lines(path: Path) -> list[str]:
    return [line.strip() for line in read_text(path).splitlines() if line.strip()]


def _quality_warnings(size_bytes: int, duration_ms: int, payload: dict) -> list[str]:
    warnings = []
    if size_bytes < payload["min_size_kb"] * 1024:
        warnings.append(f"size_below_min:{size_bytes // 1024}kb")
    if duration_ms < payload["min_duration_sec"] * 1000:
        warnings.append(f"duration_below_min:{round(duration_ms / 1000, 1)}s")
    return warnings


def _decoded_duration_ms(mp3_path: Path) -> int:
    from pydub import AudioSegment

    return len(AudioSegment.from_file(mp3_path, format="mp3"))


def _consume_source(novel_dirs: dict, stem: str) -> None:
    """A chapter is done: archive its input .txt and drop the prepared copy.

    Runs only after the final MP3 is verified, so a crash at any earlier point
    leaves the chapter queued for the next run.
    """
    input_txt = Path(novel_dirs["input"]) / f"{stem}.txt"
    processed_txt = Path(novel_dirs["processed"]) / f"{stem}.txt"
    prepared_txt = Path(novel_dirs["prepared"]) / f"{stem}.txt"
    if input_txt.exists():
        shutil.move(str(input_txt), str(processed_txt))
    prepared_txt.unlink(missing_ok=True)


def _render_chapter(prepared_txt: Path, novel_dirs: dict, payload: dict, engine) -> dict:
    from pydub import AudioSegment

    stem = prepared_txt.stem
    output_path = Path(novel_dirs["output"]) / f"{stem}.mp3"
    temp_path = output_path.with_suffix(".mp3.tmp")
    started = time()

    lines = _lines(prepared_txt)
    if not lines:
        return {"file": prepared_txt.name, "status": "empty", "line_count": 0}
    source_sha256 = sha256_file(prepared_txt)

    audio = AudioSegment.empty()
    for line_no, line in enumerate(lines, 1):
        try:
            wav_buffer, _ = engine.render_wav(line)
            audio += AudioSegment.from_wav(wav_buffer)
        except Exception as exc:
            # Do not ship a partial chapter: report the line, keep sources queued.
            temp_path.unlink(missing_ok=True)
            shutil.copy2(prepared_txt, Path(novel_dirs["failed"]) / prepared_txt.name)
            write_json_atomic(
                Path(novel_dirs["reports"]) / f"{stem}.tts_errors.json",
                {
                    "file": prepared_txt.name,
                    "failed_line": line_no,
                    "failed_text": line,
                    "error": repr(exc),
                    "traceback": traceback.format_exc(limit=8),
                },
            )
            return {
                "file": prepared_txt.name,
                "status": "failed",
                "failed_line": line_no,
                "error": repr(exc),
                "line_count": len(lines),
            }

    audio.export(temp_path, format="mp3", bitrate=payload["bitrate"])

    decoded_ms = _decoded_duration_ms(temp_path)
    if abs(decoded_ms - len(audio)) > DURATION_TOLERANCE_MS:
        temp_path.unlink(missing_ok=True)
        return {
            "file": prepared_txt.name,
            "status": "failed",
            "error": f"exported mp3 duration mismatch: {decoded_ms}ms vs {len(audio)}ms",
            "line_count": len(lines),
        }

    os.replace(temp_path, output_path)
    _consume_source(novel_dirs, stem)

    size_bytes = output_path.stat().st_size
    return {
        "file": prepared_txt.name,
        "status": "ok",
        "prepared_sha256": source_sha256,
        "line_count": len(lines),
        "mp3": str(output_path),
        "duration_ms": decoded_ms,
        "size_bytes": size_bytes,
        "render_seconds": round(time() - started, 1),
        "warnings": _quality_warnings(size_bytes, decoded_ms, payload),
    }


def _worker(worker_id: int, tasks: Queue, results: Queue, novels: dict, payload: dict) -> None:
    # Cap CPU threads per worker so N workers do not oversubscribe the machine.
    threads = str(payload["cpu_threads_per_worker"])
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ.setdefault(var, threads)

    from .audio_engine import UkrainianTTSEngine
    from .config import EngineConfig

    engine = UkrainianTTSEngine(
        EngineConfig(
            vendor_dir=Path(payload["vendor_dir"]),
            model_dir=Path(payload["model_dir"]),
            voice=payload["voice"],
            stress=payload["stress"],
            device=payload["device"],
        )
    )
    while True:
        try:
            raw = tasks.get(timeout=5)
        except queue.Empty:
            continue
        except KeyboardInterrupt:
            break
        if raw is None:
            break
        novel, file_name = raw
        prepared_txt = Path(novels[novel]["prepared"]) / file_name
        try:
            result = _render_chapter(prepared_txt, novels[novel], payload, engine)
        except Exception as exc:
            result = {
                "file": file_name,
                "status": "crashed",
                "error": repr(exc),
                "traceback": traceback.format_exc(limit=12),
            }
        result["novel"] = novel
        result["worker"] = worker_id
        results.put(result)


def _cleanup_stale_tmp(paths: NovelPaths) -> int:
    stale = list(paths.output.glob("*.mp3.tmp"))
    for tmp in stale:
        tmp.unlink()
    return len(stale)


def _verified_existing(mp3: Path, payload: dict) -> bool:
    if not mp3.exists():
        return False
    try:
        duration_ms = _decoded_duration_ms(mp3)
    except Exception:
        return False
    return mp3.stat().st_size >= payload["min_size_kb"] * 1024 and (
        duration_ms >= payload["min_duration_sec"] * 1000
    )


def _plan_novel(paths: NovelPaths, payload: dict, force: bool) -> tuple[list[str], list[dict]]:
    """Split a novel's prepared chapters into render queue vs already-done rows."""
    ensure_novel_dirs(paths)
    removed_tmp = _cleanup_stale_tmp(paths)
    if removed_tmp:
        print(f"[{paths.name}] removed {removed_tmp} stale .tmp file(s)")

    novel_dirs = _paths_payload(paths)
    to_render: list[str] = []
    done_rows: list[dict] = []
    for prepared_txt in sorted(paths.prepared.glob("*.txt")):
        mp3 = paths.output / f"{prepared_txt.stem}.mp3"
        if not force and _verified_existing(mp3, payload):
            _consume_source(novel_dirs, prepared_txt.stem)
            done_rows.append(
                {
                    "novel": paths.name,
                    "file": prepared_txt.name,
                    "status": "skipped_verified",
                    "mp3": str(mp3),
                }
            )
        else:
            if mp3.exists() and not force:
                print(f"[{paths.name}] {mp3.name} exists but fails checks — re-rendering")
            to_render.append(prepared_txt.name)
    return to_render, done_rows


def _append_manifest(reports_dir: Path, row: dict) -> None:
    manifest_path = reports_dir / "synthesis_manifest.json"
    manifest = load_json(manifest_path, {"files": {}})
    if not isinstance(manifest, dict) or "files" not in manifest:
        manifest = {"files": {}}
    manifest["files"][row["file"]] = row
    write_json_atomic(manifest_path, manifest)


def _print_row(row: dict, index: int, total: int) -> None:
    name = f"{row['novel']}/{row['file']}"
    status = row["status"]
    if status == "ok":
        minutes = row["duration_ms"] / 60_000
        extra = f"{minutes:.1f} min audio, {row['line_count']} lines, {row['render_seconds']}s render"
        if row.get("warnings"):
            extra += f", WARNINGS: {', '.join(row['warnings'])}"
    else:
        extra = row.get("error", "")
    print(f"[{index}/{total}] {name}: {status} {extra}".rstrip())


def synthesize_novels(
    config: AppConfig,
    novels: list[NovelPaths],
    workers: int | None = None,
    force: bool = False,
    limit: int | None = None,
) -> dict:
    payload = _engine_payload(config)
    novel_dirs = {paths.name: _paths_payload(paths) for paths in novels}
    reports_dirs = {paths.name: paths.reports for paths in novels}

    tasks_list: list[tuple[str, str]] = []
    rows: list[dict] = []
    for paths in novels:
        to_render, done_rows = _plan_novel(paths, payload, force)
        rows.extend(done_rows)
        tasks_list.extend((paths.name, file_name) for file_name in to_render)
        for row in done_rows:
            _append_manifest(paths.reports, row)

    if limit is not None:
        skipped = len(tasks_list) - limit
        tasks_list = tasks_list[:limit]
        if skipped > 0:
            print(f"limit={limit}: postponing {skipped} chapter(s)")

    worker_count = max(1, min(workers or config.audio.workers, len(tasks_list) or 1))
    payload["cpu_threads_per_worker"] = max(1, (os.cpu_count() or 4) // worker_count)
    started = time()
    total = len(tasks_list)
    print(f"chapters to render: {total}; already done: {len(rows)}; workers: {worker_count}")

    interrupted = False
    if total and worker_count == 1:
        from .audio_engine import UkrainianTTSEngine

        engine = UkrainianTTSEngine(config.engine)
        try:
            for index, (novel, file_name) in enumerate(tasks_list, 1):
                prepared_txt = Path(novel_dirs[novel]["prepared"]) / file_name
                row = _render_chapter(prepared_txt, novel_dirs[novel], payload, engine)
                row["novel"] = novel
                rows.append(row)
                _append_manifest(reports_dirs[novel], row)
                _print_row(row, index, total)
        except KeyboardInterrupt:
            interrupted = True
    elif total:
        try:
            set_start_method("spawn", force=True)
        except RuntimeError:
            pass
        task_queue: Queue = Queue()
        result_queue: Queue = Queue()
        processes = [
            Process(
                target=_worker,
                args=(i + 1, task_queue, result_queue, novel_dirs, payload),
                daemon=True,
            )
            for i in range(worker_count)
        ]
        for process in processes:
            process.start()
        for task in tasks_list:
            task_queue.put(task)
        for _ in processes:
            task_queue.put(None)

        collected = 0
        try:
            while collected < total:
                try:
                    row = result_queue.get(timeout=30)
                except queue.Empty:
                    if not any(p.is_alive() for p in processes):
                        print("ERROR: all workers exited before finishing the queue")
                        break
                    continue
                collected += 1
                rows.append(row)
                _append_manifest(reports_dirs[row["novel"]], row)
                _print_row(row, collected, total)
            for process in processes:
                process.join(timeout=30)
        except KeyboardInterrupt:
            interrupted = True
            print("\ninterrupted — finished chapters are safe, the rest stays queued")
            for process in processes:
                process.terminate()

    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    report = {
        "novels": [paths.name for paths in novels],
        "chapters_total": total + len([r for r in rows if r["status"] == "skipped_verified"]),
        "workers": worker_count,
        "interrupted": interrupted,
        "seconds": round(time() - started, 1),
        "status_counts": status_counts,
        "rows": rows,
    }
    for paths in novels:
        novel_rows = [row for row in rows if row.get("novel") == paths.name]
        write_json_atomic(
            paths.reports / "synthesis_report.json",
            {**report, "novels": [paths.name], "rows": novel_rows},
        )
    if interrupted:
        raise KeyboardInterrupt
    return report
