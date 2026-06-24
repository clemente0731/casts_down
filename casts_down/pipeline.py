"""Download/transcribe pipeline coordination."""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from casts_down.transcribe import transcribe_one


@dataclass
class PipelineItem:
    index: int
    source_url: str
    title: str
    audio_path: Path | None = None
    download_status: str = "pending"
    transcribe_status: str = "pending"
    error: str | None = None
    outputs: list[Path] = field(default_factory=list)
    download_elapsed: float = 0.0
    transcribe_elapsed: float = 0.0


@dataclass
class PipelineResult:
    items: list[PipelineItem]
    elapsed: float

    @property
    def failed_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.download_status == "failed" or item.transcribe_status == "failed"
        )


def allocate_pipeline_workers(
    user_concurrent: int,
    selected_count: int,
    transcribe: bool,
) -> tuple[int, int]:
    if selected_count <= 0:
        return (0, 0)

    effective = min(max(1, user_concurrent), selected_count)
    if not transcribe:
        return (effective, 0)
    if effective == 1:
        return (1, 0)
    return (max(1, effective - 1), 1)


async def run_file_pipeline(
    items: list[PipelineItem],
    download_one: Callable[[PipelineItem, Callable[[PipelineItem, Path, str], None]], Any],
    engine: Any,
    user_concurrent: int,
    transcribe: bool = True,
    language: str | None = None,
    event_log: list[str] | None = None,
) -> PipelineResult:
    started_at = time.monotonic()
    download_workers, transcribe_workers = allocate_pipeline_workers(
        user_concurrent,
        len(items),
        transcribe,
    )
    if download_workers == 0:
        return PipelineResult(items=items, elapsed=time.monotonic() - started_at)

    transcribe_queue: asyncio.Queue[PipelineItem | None] = asyncio.Queue()

    def on_done(item: PipelineItem, path: Path, message: str) -> None:
        item.audio_path = Path(path)
        item.download_status = "succeeded"
        if transcribe_workers > 0:
            item.transcribe_status = "queued"
            transcribe_queue.put_nowait(item)
        else:
            item.transcribe_status = "skipped"

    async def run_transcription_worker() -> None:
        while True:
            item = await transcribe_queue.get()
            try:
                if item is None:
                    return
                await _transcribe_item(item, engine, language, event_log)
            finally:
                transcribe_queue.task_done()

    async def run_download_worker(queue: asyncio.Queue[PipelineItem]) -> None:
        while True:
            try:
                item = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                await _download_item(item, download_one, on_done)
            finally:
                queue.task_done()

    item_queue: asyncio.Queue[PipelineItem] = asyncio.Queue()
    for item in items:
        item_queue.put_nowait(item)

    transcribe_task = None
    if transcribe_workers > 0:
        transcribe_task = asyncio.create_task(run_transcription_worker())

    download_tasks = [
        asyncio.create_task(run_download_worker(item_queue))
        for _ in range(download_workers)
    ]
    await asyncio.gather(*download_tasks)

    if transcribe_task is not None:
        await transcribe_queue.join()
        transcribe_queue.put_nowait(None)
        await transcribe_task

    return PipelineResult(items=items, elapsed=time.monotonic() - started_at)


async def _download_item(
    item: PipelineItem,
    download_one: Callable[[PipelineItem, Callable[[PipelineItem, Path, str], None]], Any],
    on_done: Callable[[PipelineItem, Path, str], None],
) -> None:
    started_at = time.monotonic()
    item.download_status = "running"
    try:
        result = download_one(item, on_done)
        if inspect.isawaitable(result):
            await result
        if item.download_status != "succeeded":
            item.download_status = "succeeded"
            item.transcribe_status = "skipped"
    except Exception as exc:
        item.download_status = "failed"
        item.transcribe_status = "skipped"
        item.error = f"{type(exc).__name__}: {exc}"
    finally:
        item.download_elapsed = time.monotonic() - started_at


async def _transcribe_item(
    item: PipelineItem,
    engine: Any,
    language: str | None,
    event_log: list[str] | None,
) -> None:
    if item.audio_path is None:
        item.transcribe_status = "failed"
        item.error = "Missing audio path"
        return

    item.transcribe_status = "running"
    if event_log is not None:
        event_log.append(f"transcribe {item.audio_path.name}")
    started_at = time.monotonic()
    result = await asyncio.to_thread(
        transcribe_one,
        item.audio_path,
        engine=engine,
        language=language,
    )
    item.transcribe_elapsed = float(
        result.get("duration") or time.monotonic() - started_at
    )
    item.outputs = list(result.get("outputs") or [])
    item.transcribe_status = result.get("status") or (
        "succeeded" if result.get("success") else "failed"
    )
    if item.transcribe_status == "failed" or result.get("success") is False:
        item.transcribe_status = "failed"
        item.error = result.get("error") or "Transcription failed"
