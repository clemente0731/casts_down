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


@dataclass
class DownloadJob:
    source_url: str
    download: Callable[
        [
            int,
            Callable[[Path, Any, str], None],
            Callable[[Path | None, Any, str], None],
        ],
        Any,
    ]
    selected_count: int | None = None
    title: str | None = None


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


async def run_download_jobs_pipeline(
    jobs: list[DownloadJob],
    engine_factory: Callable[[], Any],
    user_concurrent: int,
    language: str | None = None,
    progress_callback: Callable[[list[PipelineItem], float], None] | None = None,
    event_log: list[str] | None = None,
) -> PipelineResult:
    started_at = time.monotonic()
    known_count = sum(job.selected_count or 0 for job in jobs)
    selected_count = known_count if known_count > 0 else max(1, user_concurrent)
    download_workers, transcribe_workers = allocate_pipeline_workers(
        user_concurrent,
        selected_count,
        transcribe=True,
    )
    if download_workers == 0:
        return PipelineResult(items=[], elapsed=time.monotonic() - started_at)

    items: list[PipelineItem] = []
    transcribe_queue: asyncio.Queue[PipelineItem | None] = asyncio.Queue()
    engine: Any | None = None

    def get_engine_sync() -> Any:
        nonlocal engine
        if engine is None:
            engine = engine_factory()
        return engine

    def emit_progress() -> None:
        if progress_callback is not None:
            progress_callback(items, time.monotonic() - started_at)

    def add_success_item(job: DownloadJob, path: Path, episode: Any, message: str) -> None:
        item = PipelineItem(
            index=len(items) + 1,
            source_url=job.source_url,
            title=_episode_title(episode, path, job),
            audio_path=Path(path),
            download_status="succeeded",
            transcribe_status="queued",
        )
        items.append(item)
        if transcribe_workers > 0:
            transcribe_queue.put_nowait(item)
        if event_log is not None:
            event_log.append(f"queued {Path(path).name}")
        emit_progress()
        if transcribe_workers == 0:
            try:
                engine_for_item = get_engine_sync()
            except Exception as exc:
                item.transcribe_status = "failed"
                item.error = f"{type(exc).__name__}: {exc}"
            else:
                _transcribe_item_sync(item, engine_for_item, language, event_log)
            emit_progress()

    def add_failed_item(
        job: DownloadJob,
        path: Path | None,
        episode: Any,
        message: str,
    ) -> None:
        item = PipelineItem(
            index=len(items) + 1,
            source_url=job.source_url,
            title=_episode_title(episode, path, job),
            audio_path=Path(path) if path is not None else None,
            download_status="failed",
            transcribe_status="skipped",
            error=message,
        )
        items.append(item)
        emit_progress()

    async def transcribe_worker() -> None:
        nonlocal engine
        while True:
            item = await transcribe_queue.get()
            try:
                if item is None:
                    return
                if engine is None:
                    engine = await _maybe_to_thread(engine_factory)
                await _transcribe_item(item, engine, language, event_log)
                emit_progress()
            finally:
                transcribe_queue.task_done()

    transcribe_task = None
    if transcribe_workers > 0:
        transcribe_task = asyncio.create_task(transcribe_worker())

    for job in jobs:
        job_started = time.monotonic()
        item_count_before_job = len(items)

        def on_file_done(path: Path, episode: Any, message: str, current_job: DownloadJob = job) -> None:
            add_success_item(current_job, path, episode, message)

        def on_file_failed(
            path: Path | None,
            episode: Any,
            message: str,
            current_job: DownloadJob = job,
        ) -> None:
            add_failed_item(current_job, path, episode, message)

        try:
            result = job.download(download_workers, on_file_done, on_file_failed)
            if inspect.isawaitable(result):
                await result
        except SystemExit as exc:
            if len(items) == item_count_before_job:
                code = exc.code if isinstance(exc.code, int) else 1
                add_failed_item(job, None, None, f"exited with status {code}")
        except Exception as exc:
            if len(items) == item_count_before_job:
                add_failed_item(job, None, None, f"{type(exc).__name__}: {exc}")
        finally:
            for item in items:
                if item.source_url == job.source_url and item.download_elapsed == 0.0:
                    item.download_elapsed = time.monotonic() - job_started

    if transcribe_task is None and transcribe_workers > 0:
        transcribe_task = asyncio.create_task(transcribe_worker())
    if transcribe_task is not None:
        await transcribe_queue.join()
        transcribe_queue.put_nowait(None)
        await transcribe_task

    return PipelineResult(items=items, elapsed=time.monotonic() - started_at)


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
        if item.audio_path is not None or item.download_status == "succeeded":
            return
        item.audio_path = Path(path)
        item.download_status = "succeeded"
        if transcribe_workers > 0:
            item.transcribe_status = "queued"
            transcribe_queue.put_nowait(item)
        elif not transcribe:
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
                if (
                    transcribe
                    and transcribe_workers == 0
                    and item.download_status == "succeeded"
                ):
                    await _transcribe_item(item, engine, language, event_log)
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


async def _maybe_to_thread(factory: Callable[[], Any]) -> Any:
    if inspect.iscoroutinefunction(factory):
        return await factory()
    result = await asyncio.to_thread(factory)
    if inspect.isawaitable(result):
        return await result
    return result


def _episode_title(episode: Any, path: Path | None, job: DownloadJob) -> str:
    if isinstance(episode, dict):
        return str(episode.get("title") or (path.stem if path else job.title or job.source_url))
    if episode is not None:
        return str(getattr(episode, "title", path.stem if path else job.title or job.source_url))
    if path is not None:
        return path.stem
    return job.title or job.source_url


def _transcribe_item_sync(
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
    try:
        result = transcribe_one(item.audio_path, engine=engine, language=language)
    except Exception as exc:
        item.transcribe_elapsed = time.monotonic() - started_at
        item.transcribe_status = "failed"
        item.error = f"{type(exc).__name__}: {exc}"
        return
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
        if item.audio_path is not None or item.download_status == "succeeded":
            return
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
    try:
        result = await asyncio.to_thread(
            transcribe_one,
            item.audio_path,
            engine=engine,
            language=language,
        )
    except Exception as exc:
        item.transcribe_elapsed = time.monotonic() - started_at
        item.transcribe_status = "failed"
        item.error = f"{type(exc).__name__}: {exc}"
        return
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
