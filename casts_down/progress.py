"""Progress and report rendering for the download/transcribe pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import click

TaskState = Literal[
    "pending",
    "queued",
    "running",
    "succeeded",
    "skipped",
    "backfilled",
    "failed",
]


@dataclass
class PipelineTaskView:
    index: int
    file_name: str
    download_status: str = "pending"
    transcribe_status: str = "pending"
    status: TaskState = "pending"
    size_label: str = "-"
    download_detail: str = "-"
    transcribe_detail: str = "-"
    error: str = "-"
    audio_path: Path | None = None
    output_paths: list[Path] = field(default_factory=list)


@dataclass
class ProgressTotals:
    total: int
    done: int = 0
    running: int = 0
    queued: int = 0
    failed: int = 0
    download_ok: int = 0
    download_failed: int = 0
    download_active: int = 0
    transcribe_ok: int = 0
    transcribe_failed: int = 0
    transcribe_active: int = 0
    transcribe_queued: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    audio_done: str = "-"
    audio_total: str = "-"
    elapsed: str = "0m00s"
    active_budget: str = "0/0"
    download_eta: str = "-"
    transcribe_eta: str = "-"


def color_status(status: str) -> str:
    normalized = status.lower()
    if normalized in {"succeeded", "done", "ok"}:
        return "green"
    if normalized in {"failed", "error"}:
        return "red"
    return "yellow"


def render_eta(value: str, tty: bool) -> str:
    text = f"ETA {value}"
    if not tty:
        return text
    return click.style(text, fg="black", bg="yellow")


def render_overall_progress(totals: ProgressTotals, tty: bool) -> str:
    transcribe_total = max(0, totals.total - totals.download_failed)
    lines = [
        "=== Overall Progress ===",
        (
            f"Total: {totals.total} | Done: {totals.done} | "
            f"Running: {totals.running} | Queued: {totals.queued} | "
            f"Failed: {totals.failed}"
        ),
        (
            f"Download: {totals.download_ok}/{totals.total} ok, "
            f"{totals.download_failed} failed, {totals.download_active} active | "
            f"{_format_bytes(totals.bytes_done)} / {_format_bytes(totals.bytes_total)} | "
            f"{render_eta(totals.download_eta, tty)}"
        ),
        (
            f"Transcribe: {totals.transcribe_ok}/{transcribe_total} ok, "
            f"{totals.transcribe_active} active, {totals.transcribe_queued} queued | "
            f"audio {totals.audio_done} / {totals.audio_total} | "
            f"{render_eta(totals.transcribe_eta, tty)}"
        ),
        f"Elapsed: {totals.elapsed} | Active budget: {totals.active_budget}",
    ]
    return "\n".join(lines)


def render_task_progress(rows: list[PipelineTaskView], tty: bool) -> str:
    lines = [
        "=== Task Progress ===",
        "Status   #   File                 Download          Transcribe         Size     Error",
    ]
    for row in rows:
        color = color_status(row.status)
        status_label = _style_status(f"{color.upper():<8}", color, tty)
        lines.append(
            f"{status_label} "
            f"{row.index:02d}  "
            f"{_fit(row.file_name, 20):<20} "
            f"{_fit(row.download_status, 17):<17} "
            f"{_fit(row.transcribe_status, 17):<17} "
            f"{_fit(row.size_label, 8):<8} "
            f"{row.error or '-'}"
        )
    return "\n".join(lines)


def _style_status(label: str, color: str, tty: bool) -> str:
    if not tty:
        return label
    return click.style(label, fg=color)


def _format_bytes(value: int) -> str:
    if value <= 0:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(value)
    unit = units[0]
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            break
        amount /= 1024
    if unit == "B":
        return f"{int(amount)} {unit}"
    return f"{amount:.1f} {unit}"


def _fit(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 1:
        return value[:width]
    return value[: width - 1] + "~"
