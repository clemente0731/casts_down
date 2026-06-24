# Pipeline Progress Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a stable download/transcribe pipeline that overlaps network IO with one transcription worker and prints overall, per-task, and final color-coded reports.

**Architecture:** Keep downloaders responsible for retrieving files and final `.tmp` rename safety, but let them emit completion events. Add a small pipeline layer that owns task state, bounded concurrency, completed-file queueing, transcription execution, progress rendering, and final reporting. Keep one transcription worker in the first version so CUDA/CPU resources are predictable and the Whisper model loads once.

**Tech Stack:** Python 3.10+, asyncio, click, tqdm, pytest, pytest-asyncio, existing casts_down downloaders and transcription engines

**Spec:** `docs/superpowers/specs/2026-06-24-pipeline-progress-design.md`

---

## File Map

### Files to create

```text
casts_down/progress.py
  Owns color/status formatting, ETA highlighting, overall progress rendering,
  per-task progress rendering, and final report rendering.

casts_down/pipeline.py
  Owns pipeline task records, concurrency allocation, completed-file queue,
  download event collection, transcription worker, and final pipeline result.

tests/test_progress.py
  Unit tests for color classification, yellow ETA background, TTY vs non-TTY
  rendering, overall progress, per-task progress, and final report fields.

tests/test_pipeline.py
  Unit tests for concurrency allocation, queueing order, failure isolation,
  skip/backfill preservation, and pipeline result status.
```

### Files to modify

```text
casts_down/downloaders/base.py
  Add optional on_file_done callback and richer download result records while
  preserving existing return list behavior.

casts_down/downloaders/xiaoyuzhou.py
  Add the same optional callback path used by the generic podcast downloader.

casts_down/transcribe/__init__.py
  Extract a reusable transcribe_one() helper so pipeline and batch share behavior.

casts_down/cli.py
  Route default download+transcribe flow through pipeline. Keep --no-transcribe
  as download-only. Update --concurrent help text and final exit-code handling.

README.md
  Update --concurrent semantics and add pipeline progress examples.

Makefile
  Include new modules in py_compile lint.

tests/test_cli.py
  Add CLI coverage for new --concurrent help text, pipeline progress output,
  --no-transcribe behavior, and non-zero exit on red task status.

tests/test_downloaders.py
  Add callback coverage for successful downloads and failed downloads.

tests/test_transcribe_batch.py
  Add/adjust tests around transcribe_one() reuse and skip/backfill behavior.
```

---

## Task 1: Progress Rendering And Status Model

**Files:**
- Create: `casts_down/progress.py`
- Create: `tests/test_progress.py`
- Modify: `Makefile`

- [ ] **Step 1: Write failing tests for status colors and ETA background**

Create `tests/test_progress.py`:

```python
"""Tests for pipeline progress rendering."""

from casts_down.progress import (
    PipelineTaskView,
    ProgressTotals,
    color_status,
    render_eta,
    render_overall_progress,
    render_task_progress,
)


def test_color_status_maps_terminal_states():
    assert color_status("succeeded") == "green"
    assert color_status("running") == "yellow"
    assert color_status("queued") == "yellow"
    assert color_status("skipped") == "yellow"
    assert color_status("backfilled") == "yellow"
    assert color_status("failed") == "red"


def test_render_eta_uses_yellow_background_for_tty():
    text = render_eta("1h45m", tty=True)

    assert "ETA 1h45m" in text
    assert "\x1b[" in text


def test_render_eta_has_no_control_codes_for_non_tty():
    text = render_eta("1h45m", tty=False)

    assert text == "ETA 1h45m"
    assert "\x1b[" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_progress.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'casts_down.progress'`.

- [ ] **Step 3: Implement minimal progress model and color helpers**

Create `casts_down/progress.py`:

```python
"""Progress and report rendering for download/transcribe pipeline."""

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
    elapsed: str = "0m00s"
    active_budget: str = "0/0"
    download_eta: str = "-"
    transcribe_eta: str = "-"


def color_status(status: str) -> str:
    if status in {"succeeded", "done", "ok"}:
        return "green"
    if status in {"failed", "error"}:
        return "red"
    return "yellow"


def render_eta(value: str, tty: bool) -> str:
    text = f"ETA {value}"
    if not tty:
        return text
    return click.style(text, fg="black", bg="yellow")
```

- [ ] **Step 4: Run tests to verify color helpers pass and table tests still absent**

Run:

```bash
python -m pytest tests/test_progress.py::test_color_status_maps_terminal_states tests/test_progress.py::test_render_eta_uses_yellow_background_for_tty tests/test_progress.py::test_render_eta_has_no_control_codes_for_non_tty -q
```

Expected: PASS for these three tests.

- [ ] **Step 5: Write failing tests for overall and per-task table rendering**

Append to `tests/test_progress.py`:

```python
def test_render_overall_progress_includes_required_sections():
    totals = ProgressTotals(
        total=50,
        done=12,
        running=3,
        queued=35,
        failed=1,
        download_ok=14,
        download_failed=1,
        download_active=2,
        transcribe_ok=12,
        transcribe_active=1,
        transcribe_queued=1,
        elapsed="32m14s",
        active_budget="3/3",
        download_eta="28m10s",
        transcribe_eta="1h45m",
    )

    text = render_overall_progress(totals, tty=False)

    assert "=== Overall Progress ===" in text
    assert "Total: 50 | Done: 12 | Running: 3 | Queued: 35 | Failed: 1" in text
    assert "Download: 14/50 ok, 1 failed, 2 active" in text
    assert "Transcribe: 12/49 ok, 1 active, 1 queued" in text
    assert "Elapsed: 32m14s | Active budget: 3/3" in text
    assert "ETA 1h45m" in text


def test_render_task_progress_includes_green_yellow_red_rows():
    rows = [
        PipelineTaskView(1, "episode-a.mp3", "done", "done", "succeeded", "75 MB"),
        PipelineTaskView(2, "episode-b.mp3", "done", "42% ETA 12m", "running", "80 MB"),
        PipelineTaskView(3, "episode-c.mp3", "failed", "skipped", "failed", "-", error="HTTP 403"),
    ]

    text = render_task_progress(rows, tty=False)

    assert "=== Task Progress ===" in text
    assert "GREEN" in text
    assert "YELLOW" in text
    assert "RED" in text
    assert "episode-a.mp3" in text
    assert "episode-b.mp3" in text
    assert "HTTP 403" in text
```

- [ ] **Step 6: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_progress.py -q
```

Expected: FAIL with import errors for `render_overall_progress` and `render_task_progress`.

- [ ] **Step 7: Implement table renderers**

Add to `casts_down/progress.py`:

```python
def _status_label(status: str, tty: bool) -> str:
    color = color_status(status)
    label = color.upper()
    if not tty:
        return label
    return click.style(label, fg=color)


def _bytes_label(done: int, total: int) -> str:
    def _mb(value: int) -> str:
        return f"{value / 1024 / 1024:.1f} MB"

    if total:
        return f"{_mb(done)} / {_mb(total)}"
    if done:
        return _mb(done)
    return "-"


def render_overall_progress(totals: ProgressTotals, tty: bool) -> str:
    transcribe_total = max(totals.transcribe_ok + totals.transcribe_failed + totals.transcribe_active + totals.transcribe_queued, totals.total - totals.download_failed)
    lines = [
        "=== Overall Progress ===",
        f"Total: {totals.total} | Done: {totals.done} | Running: {totals.running} | Queued: {totals.queued} | Failed: {totals.failed}",
        (
            f"Download: {totals.download_ok}/{totals.total} ok, {totals.download_failed} failed, "
            f"{totals.download_active} active | {_bytes_label(totals.bytes_done, totals.bytes_total)} | "
            f"{render_eta(totals.download_eta, tty) if totals.download_eta != '-' else 'ETA -'}"
        ),
        (
            f"Transcribe: {totals.transcribe_ok}/{transcribe_total} ok, {totals.transcribe_active} active, "
            f"{totals.transcribe_queued} queued | {render_eta(totals.transcribe_eta, tty) if totals.transcribe_eta != '-' else 'ETA -'}"
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
        status = _status_label(row.status, tty)
        lines.append(
            f"{status:<8} {row.index:02d}  {row.file_name[:20]:<20} "
            f"{row.download_status[:16]:<16} {row.transcribe_status[:18]:<18} "
            f"{row.size_label:<8} {row.error}"
        )
    return "\n".join(lines)
```

- [ ] **Step 8: Run progress tests**

Run:

```bash
python -m pytest tests/test_progress.py -q
```

Expected: PASS.

- [ ] **Step 9: Add module to lint**

Modify `Makefile` under `lint`:

```make
	python -m py_compile casts_down/progress.py
```

- [ ] **Step 10: Run lint and commit**

Run:

```bash
make lint
python -m pytest tests/test_progress.py -q
git add Makefile casts_down/progress.py tests/test_progress.py
git commit -m "feat: add pipeline progress rendering"
```

Expected: lint passes and progress tests pass.

---

## Task 2: Single-File Transcription Helper

**Files:**
- Modify: `casts_down/transcribe/__init__.py`
- Modify: `tests/test_transcribe_batch.py`

- [ ] **Step 1: Write failing tests for `transcribe_one()`**

Append to `tests/test_transcribe_batch.py`:

```python
def test_transcribe_one_writes_all_outputs(tmp_path):
    audio = tmp_path / "single.mp3"
    audio.touch()

    from casts_down.transcribe import transcribe_one

    result = transcribe_one(audio, engine=DummyEngine())

    assert result["success"] is True
    assert result["skipped"] is False
    assert (tmp_path / "single.srt").exists()
    assert (tmp_path / "single.txt").exists()
    assert (tmp_path / "single.words.json").exists()
    assert str(tmp_path / "single.srt") in [str(p) for p in result["outputs"]]


def test_transcribe_one_backfills_stale_words_json_without_engine_call(tmp_path):
    audio = tmp_path / "done.mp3"
    audio.touch()
    (tmp_path / "done.srt").write_text("existing", encoding="utf-8")
    (tmp_path / "done.txt").write_text("[00:00:01] I am safe. Safe brain.", encoding="utf-8")
    (tmp_path / "done.words.json").write_text('{"version": 1, "normalization": {}, "words": [{"word": "i", "count": 1}]}', encoding="utf-8")

    class CountingEngine(TranscribeEngine):
        def __init__(self):
            self.calls = 0

        def transcribe(self, audio_path, language=None):
            self.calls += 1
            return [Segment(0.0, 1.0, "new")]

    engine = CountingEngine()

    from casts_down.transcribe import transcribe_one

    result = transcribe_one(audio, engine=engine, skip_transcribed=True)

    assert result["success"] is True
    assert result["skipped"] is True
    assert result["status"] == "backfilled"
    assert engine.calls == 0
    assert '"word": "i"' not in (tmp_path / "done.words.json").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_transcribe_batch.py::test_transcribe_one_writes_all_outputs tests/test_transcribe_batch.py::test_transcribe_one_backfills_stale_words_json_without_engine_call -q
```

Expected: FAIL with `ImportError` for `transcribe_one`.

- [ ] **Step 3: Implement `transcribe_one()` and make `transcribe_batch()` reuse it**

Modify `casts_down/transcribe/__init__.py`:

```python
def transcribe_one(
    audio_path: Path,
    engine: TranscribeEngine,
    language: str | None = None,
    skip_transcribed: bool = True,
    overwrite: bool = False,
) -> dict:
    start_time = time.monotonic()
    try:
        if not overwrite and skip_transcribed and _has_transcript(audio_path):
            status = "skipped"
            if not word_stats_is_current(audio_path):
                write_word_stats_from_txt(audio_path)
                status = "backfilled"
            return {
                "file": audio_path,
                "success": True,
                "skipped": True,
                "status": status,
                "duration": time.monotonic() - start_time,
                "error": None,
                "outputs": [audio_path.with_suffix(".srt"), audio_path.with_suffix(".txt"), word_stats_path(audio_path)],
            }

        segments = engine.transcribe(audio_path, language=language)
        srt_path, txt_path, words_path = write_outputs(audio_path, segments)
        return {
            "file": audio_path,
            "success": True,
            "skipped": False,
            "status": "succeeded",
            "duration": time.monotonic() - start_time,
            "error": None,
            "outputs": [srt_path, txt_path, words_path],
        }
    except Exception as e:
        return {
            "file": audio_path,
            "success": False,
            "skipped": False,
            "status": "failed",
            "duration": time.monotonic() - start_time,
            "error": f"{type(e).__name__}: {e}",
            "outputs": [],
        }
```

Then simplify the body of the `for audio_path in files:` loop in `transcribe_batch()` so it calls `transcribe_one(...)`, prints the same existing messages from the returned dict, and preserves current KeyboardInterrupt cleanup behavior.

- [ ] **Step 4: Run targeted tests**

Run:

```bash
python -m pytest tests/test_transcribe_batch.py tests/test_transcribe_formatter.py tests/test_word_stats.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add casts_down/transcribe/__init__.py tests/test_transcribe_batch.py
git commit -m "feat: add single file transcription helper"
```

---

## Task 3: Downloader Completion Callbacks

**Files:**
- Modify: `casts_down/downloaders/base.py`
- Modify: `casts_down/downloaders/xiaoyuzhou.py`
- Modify: `tests/test_downloaders.py`

- [ ] **Step 1: Write failing tests for callback after final rename**

Append to `tests/test_downloaders.py`:

```python
@pytest.mark.asyncio
async def test_podcast_download_all_calls_on_file_done_after_success(tmp_path):
    from casts_down.downloaders.base import PodcastDownloader, PodcastEpisode

    episode = PodcastEpisode("Done Episode", "https://example.com/done.mp3")
    downloader = PodcastDownloader(concurrent=1)
    events = []

    async def fake_download(session, ep, path, skip, progress_callback=None):
        path.write_bytes(b"audio")
        return True, f"完成: {path.name} (0.0 MB)"

    downloader.download_episode = fake_download

    with patch("casts_down.downloaders.base.aiohttp.ClientSession") as mock_cs:
        mock_cs.return_value.__aenter__.return_value = object()
        files = await downloader.download_all(
            [episode],
            "Podcast",
            tmp_path,
            on_file_done=lambda path, episode, message: events.append((path, episode.title, message)),
        )

    assert len(files) == 1
    assert events == [(files[0], "Done Episode", f"完成: {files[0].name} (0.0 MB)")]


@pytest.mark.asyncio
async def test_podcast_download_all_does_not_call_on_file_done_for_failure(tmp_path):
    from casts_down.downloaders.base import PodcastDownloader, PodcastEpisode

    episode = PodcastEpisode("Bad Episode", "https://example.com/bad.mp3")
    downloader = PodcastDownloader(concurrent=1)
    events = []

    async def fake_download(session, ep, path, skip, progress_callback=None):
        return False, "HTTP 403"

    downloader.download_episode = fake_download

    with patch("casts_down.downloaders.base.aiohttp.ClientSession") as mock_cs:
        mock_cs.return_value.__aenter__.return_value = object()
        files = await downloader.download_all(
            [episode],
            "Podcast",
            tmp_path,
            on_file_done=lambda path, episode, message: events.append((path, episode.title, message)),
        )

    assert files == []
    assert events == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_downloaders.py::test_podcast_download_all_calls_on_file_done_after_success tests/test_downloaders.py::test_podcast_download_all_does_not_call_on_file_done_for_failure -q
```

Expected: FAIL with `TypeError: download_all() got an unexpected keyword argument 'on_file_done'`.

- [ ] **Step 3: Add callback support to `PodcastDownloader.download_all()`**

Modify signature in `casts_down/downloaders/base.py`:

```python
async def download_all(
    self,
    episodes: list[PodcastEpisode],
    podcast_name: str,
    output_dir: Path,
    skip_existing: bool = False,
    on_file_done: Callable[[Path, PodcastEpisode, str], None] | None = None,
) -> list[Path]:
```

Inside the success block:

```python
if success:
    tqdm.write(f"[+] {message}")
    path = path_map[idx]
    downloaded_files.append(path)
    if on_file_done:
        on_file_done(path, episodes[idx], message)
else:
    tqdm.write(f"[-] {message}")
```

- [ ] **Step 4: Add matching callback support to Xiaoyuzhou**

Modify `XiaoyuzhouDownloader.download_episode_by_url()` and `download_podcast()` signatures:

```python
on_file_done: Callable[[Path, dict, str], None] | None = None
```

Call it after success:

```python
if success:
    click.echo(f"[+] {message}")
    downloaded_files.append(output_path)
    if on_file_done:
        on_file_done(output_path, episode_info, message)
```

For podcast list downloads, use the selected `episode` dict:

```python
if success:
    path = path_map[idx]
    tqdm.write(f"[+] {message}")
    downloaded_files.append(path)
    if on_file_done:
        on_file_done(path, episodes[idx], message)
```

Ensure `Callable` is imported in `casts_down/downloaders/xiaoyuzhou.py`:

```python
from typing import Callable
```

- [ ] **Step 5: Run downloader tests**

Run:

```bash
python -m pytest tests/test_downloaders.py -q -k 'not DryRunItunesApiToRss and not DryRunCliPipeline and not DryRunDepCheck'
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add casts_down/downloaders/base.py casts_down/downloaders/xiaoyuzhou.py tests/test_downloaders.py
git commit -m "feat: emit download completion callbacks"
```

---

## Task 4: Pipeline Orchestrator

**Files:**
- Create: `casts_down/pipeline.py`
- Create: `tests/test_pipeline.py`
- Modify: `Makefile`

- [ ] **Step 1: Write failing tests for concurrency allocation**

Create `tests/test_pipeline.py`:

```python
"""Tests for download/transcribe pipeline orchestration."""

import asyncio
from pathlib import Path

import pytest

from casts_down.transcribe.engine import Segment, TranscribeEngine


def test_effective_concurrency_is_capped_by_selected_count():
    from casts_down.pipeline import allocate_pipeline_workers

    assert allocate_pipeline_workers(user_concurrent=3, selected_count=1, transcribe=True) == (1, 0)
    assert allocate_pipeline_workers(user_concurrent=3, selected_count=2, transcribe=True) == (1, 1)
    assert allocate_pipeline_workers(user_concurrent=3, selected_count=50, transcribe=True) == (2, 1)
    assert allocate_pipeline_workers(user_concurrent=5, selected_count=50, transcribe=False) == (5, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_pipeline.py::test_effective_concurrency_is_capped_by_selected_count -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'casts_down.pipeline'`.

- [ ] **Step 3: Implement worker allocation**

Create `casts_down/pipeline.py`:

```python
"""Pipeline orchestration for overlapping podcast download and transcription."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from casts_down.progress import PipelineTaskView
from casts_down.transcribe import transcribe_one
from casts_down.transcribe.engine import TranscribeEngine


def allocate_pipeline_workers(user_concurrent: int, selected_count: int, transcribe: bool) -> tuple[int, int]:
    if selected_count <= 0:
        return 0, 0
    effective = min(max(1, user_concurrent), selected_count)
    if not transcribe:
        return effective, 0
    if effective == 1:
        return 1, 0
    return max(1, effective - 1), 1
```

- [ ] **Step 4: Run allocation test**

Run:

```bash
python -m pytest tests/test_pipeline.py::test_effective_concurrency_is_capped_by_selected_count -q
```

Expected: PASS.

- [ ] **Step 5: Write failing async pipeline queue test**

Append to `tests/test_pipeline.py`:

```python
class DummyPipelineEngine(TranscribeEngine):
    def transcribe(self, audio_path, language=None):
        return [Segment(0.0, 1.0, f"text for {Path(audio_path).stem}")]


@pytest.mark.asyncio
async def test_pipeline_transcribes_first_completed_download_before_later_download_finishes(tmp_path):
    from casts_down.pipeline import PipelineItem, run_file_pipeline

    first = tmp_path / "first.mp3"
    second = tmp_path / "second.mp3"
    events = []

    async def fake_download(item, on_done):
        if item.index == 1:
            first.write_bytes(b"first")
            await on_done(item, first, "done first")
            events.append("download first")
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.10)
            second.write_bytes(b"second")
            await on_done(item, second, "done second")
            events.append("download second")

    result = await run_file_pipeline(
        items=[
            PipelineItem(index=1, source_url="url1", title="first"),
            PipelineItem(index=2, source_url="url2", title="second"),
        ],
        download_one=fake_download,
        engine=DummyPipelineEngine(),
        user_concurrent=3,
        transcribe=True,
        event_log=events,
    )

    assert result.failed_count == 0
    assert "transcribe first.mp3" in events
    assert events.index("transcribe first.mp3") < events.index("download second")
```

- [ ] **Step 6: Run queue test to verify it fails**

Run:

```bash
python -m pytest tests/test_pipeline.py::test_pipeline_transcribes_first_completed_download_before_later_download_finishes -q
```

Expected: FAIL with `ImportError` for `PipelineItem` or `run_file_pipeline`.

- [ ] **Step 7: Implement minimal pipeline item/result and queue worker**

Add to `casts_down/pipeline.py`:

```python
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
        return sum(1 for item in self.items if item.download_status == "failed" or item.transcribe_status == "failed")


DownloadDoneCallback = Callable[[PipelineItem, Path, str], Awaitable[None]]
DownloadOne = Callable[[PipelineItem, DownloadDoneCallback], Awaitable[None]]


async def run_file_pipeline(
    items: list[PipelineItem],
    download_one: DownloadOne,
    engine: TranscribeEngine,
    user_concurrent: int,
    transcribe: bool = True,
    language: str | None = None,
    event_log: list[str] | None = None,
) -> PipelineResult:
    started = time.monotonic()
    download_workers, transcribe_workers = allocate_pipeline_workers(user_concurrent, len(items), transcribe)
    queue: asyncio.Queue[PipelineItem | None] = asyncio.Queue()
    download_sem = asyncio.Semaphore(download_workers or 1)

    async def on_done(item: PipelineItem, path: Path, message: str) -> None:
        item.audio_path = path
        item.download_status = "succeeded"
        if transcribe and transcribe_workers:
            item.transcribe_status = "queued"
            await queue.put(item)

    async def download_task(item: PipelineItem) -> None:
        start = time.monotonic()
        async with download_sem:
            item.download_status = "running"
            try:
                await download_one(item, on_done)
                if item.download_status == "pending" or item.download_status == "running":
                    item.download_status = "skipped" if item.audio_path is None else "succeeded"
            except Exception as e:
                item.download_status = "failed"
                item.transcribe_status = "skipped"
                item.error = f"{type(e).__name__}: {e}"
            finally:
                item.download_elapsed = time.monotonic() - start

    async def transcribe_worker() -> None:
        while True:
            item = await queue.get()
            try:
                if item is None:
                    return
                if item.audio_path is None:
                    item.transcribe_status = "skipped"
                    continue
                item.transcribe_status = "running"
                if event_log is not None:
                    event_log.append(f"transcribe {item.audio_path.name}")
                start = time.monotonic()
                result = await asyncio.to_thread(
                    transcribe_one,
                    item.audio_path,
                    engine,
                    language,
                    True,
                    False,
                )
                item.transcribe_elapsed = time.monotonic() - start
                item.transcribe_status = result["status"] if result["success"] else "failed"
                item.outputs = result.get("outputs", [])
                if result.get("error"):
                    item.error = result["error"]
            finally:
                queue.task_done()

    worker_tasks = [asyncio.create_task(transcribe_worker()) for _ in range(transcribe_workers)]
    download_tasks = [asyncio.create_task(download_task(item)) for item in items]
    await asyncio.gather(*download_tasks)
    if transcribe_workers:
        await queue.join()
        for _ in worker_tasks:
            await queue.put(None)
        await asyncio.gather(*worker_tasks)
    return PipelineResult(items=items, elapsed=time.monotonic() - started)
```

- [ ] **Step 8: Run pipeline tests**

Run:

```bash
python -m pytest tests/test_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 9: Add failure isolation tests**

Append to `tests/test_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_pipeline_download_failure_does_not_enqueue_transcription(tmp_path):
    from casts_down.pipeline import PipelineItem, run_file_pipeline

    ok = tmp_path / "ok.mp3"

    async def fake_download(item, on_done):
        if item.index == 1:
            raise RuntimeError("HTTP 403")
        ok.write_bytes(b"ok")
        await on_done(item, ok, "done ok")

    result = await run_file_pipeline(
        items=[PipelineItem(1, "bad", "bad"), PipelineItem(2, "ok", "ok")],
        download_one=fake_download,
        engine=DummyPipelineEngine(),
        user_concurrent=3,
        transcribe=True,
    )

    assert result.items[0].download_status == "failed"
    assert result.items[0].transcribe_status == "skipped"
    assert result.items[1].transcribe_status == "succeeded"
    assert result.failed_count == 1


@pytest.mark.asyncio
async def test_pipeline_transcription_failure_does_not_stop_later_items(tmp_path):
    from casts_down.pipeline import PipelineItem, run_file_pipeline

    class MixedEngine(TranscribeEngine):
        def transcribe(self, audio_path, language=None):
            if Path(audio_path).name == "bad.mp3":
                raise RuntimeError("CUDA OOM")
            return [Segment(0.0, 1.0, "ok text")]

    async def fake_download(item, on_done):
        path = tmp_path / f"{item.title}.mp3"
        path.write_bytes(b"audio")
        await on_done(item, path, f"done {path.name}")

    result = await run_file_pipeline(
        items=[PipelineItem(1, "bad", "bad"), PipelineItem(2, "ok", "ok")],
        download_one=fake_download,
        engine=MixedEngine(),
        user_concurrent=3,
        transcribe=True,
    )

    assert result.items[0].transcribe_status == "failed"
    assert result.items[1].transcribe_status == "succeeded"
    assert result.failed_count == 1
```

- [ ] **Step 10: Run failure isolation tests**

Run:

```bash
python -m pytest tests/test_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 11: Add module to lint and commit**

Modify `Makefile`:

```make
	python -m py_compile casts_down/pipeline.py
```

Run:

```bash
make lint
python -m pytest tests/test_pipeline.py tests/test_progress.py -q
git add Makefile casts_down/pipeline.py tests/test_pipeline.py
git commit -m "feat: add download transcribe pipeline"
```

Expected: lint passes and pipeline/progress tests pass.

---

## Task 5: CLI Integration And Report Output

**Files:**
- Modify: `casts_down/cli.py`
- Modify: `casts_down/pipeline.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI help test for new `--concurrent` meaning**

Modify `tests/test_cli.py`:

```python
def test_help_describes_concurrent_as_pipeline_budget(runner):
    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "Max active pipeline tasks" in result.output
```

- [ ] **Step 2: Run help test to verify it fails**

Run:

```bash
python -m pytest tests/test_cli.py::test_help_describes_concurrent_as_pipeline_budget -q
```

Expected: FAIL because current help says `Concurrent downloads`.

- [ ] **Step 3: Update click option help text**

Modify `casts_down/cli.py` option:

```python
@click.option(
    '--concurrent', '-c',
    type=click.IntRange(min=1, max=20),
    default=3,
    help='Max active pipeline tasks. With transcription enabled, shared by downloads and transcription; with --no-transcribe, parallel downloads. Capped by selected episode count. Default: 3',
)
```

- [ ] **Step 4: Run help test**

Run:

```bash
python -m pytest tests/test_cli.py::test_help_describes_concurrent_as_pipeline_budget -q
```

Expected: PASS.

- [ ] **Step 5: Add pipeline report rendering helper**

Add to `casts_down/pipeline.py`:

```python
def build_task_views(items: list[PipelineItem]) -> list[PipelineTaskView]:
    views = []
    for item in items:
        if item.download_status == "failed" or item.transcribe_status == "failed":
            status = "failed"
        elif item.transcribe_status in {"succeeded", "skipped", "backfilled"} or item.download_status in {"succeeded", "skipped"}:
            status = "succeeded" if item.transcribe_status == "succeeded" else "skipped"
        else:
            status = "running"
        path = item.audio_path
        views.append(PipelineTaskView(
            index=item.index,
            file_name=path.name if path else item.title,
            download_status=item.download_status,
            transcribe_status=item.transcribe_status,
            status=status,
            size_label=f"{path.stat().st_size / 1024 / 1024:.1f} MB" if path and path.exists() else "-",
            error=item.error or "-",
            audio_path=path,
            output_paths=item.outputs,
        ))
    return views
```

- [ ] **Step 6: Write failing CLI test for pipeline progress and non-zero failure exit**

Append to `tests/test_cli.py`:

```python
@patch("casts_down.cli.run_download_transcribe_pipeline")
def test_download_and_transcribe_uses_pipeline_and_prints_progress(mock_pipeline, runner):
    from casts_down.pipeline import PipelineItem, PipelineResult

    item = PipelineItem(index=1, source_url="https://feeds.example.com/feed.rss", title="episode")
    item.download_status = "succeeded"
    item.transcribe_status = "succeeded"
    mock_pipeline.return_value = PipelineResult(items=[item], elapsed=1.0)

    result = runner.invoke(main, ["https://feeds.example.com/feed.rss"])

    assert result.exit_code == 0
    assert mock_pipeline.called
    assert "Overall Progress" in result.output
    assert "Task Progress" in result.output


@patch("casts_down.cli.run_download_transcribe_pipeline")
def test_pipeline_red_task_returns_nonzero_exit(mock_pipeline, runner):
    from casts_down.pipeline import PipelineItem, PipelineResult

    item = PipelineItem(index=1, source_url="https://feeds.example.com/feed.rss", title="episode")
    item.download_status = "failed"
    item.transcribe_status = "skipped"
    item.error = "HTTP 403"
    mock_pipeline.return_value = PipelineResult(items=[item], elapsed=1.0)

    result = runner.invoke(main, ["https://feeds.example.com/feed.rss"])

    assert result.exit_code == 1
    assert "HTTP 403" in result.output
```

- [ ] **Step 7: Run CLI tests to verify they fail**

Run:

```bash
python -m pytest tests/test_cli.py::test_download_and_transcribe_uses_pipeline_and_prints_progress tests/test_cli.py::test_pipeline_red_task_returns_nonzero_exit -q
```

Expected: FAIL because `run_download_transcribe_pipeline` is not imported/used by CLI.

- [ ] **Step 8: Add CLI pipeline entry point**

Modify `casts_down/cli.py` imports:

```python
from casts_down.pipeline import build_task_views, run_download_transcribe_pipeline
from casts_down.progress import render_overall_progress, render_task_progress, ProgressTotals
```

In the default command body, replace the post-download transcription branch with:

```python
if transcribe:
    pipeline_started = time.monotonic()
    result = asyncio.run(run_download_transcribe_pipeline(
        urls=urls,
        download_all=download_all,
        latest=latest,
        output=output,
        concurrent=concurrent,
        skip_existing=skip_existing,
        model=model,
    ))
    task_timer.record("Pipeline", time.monotonic() - pipeline_started)
    views = build_task_views(result.items)
    totals = ProgressTotals(
        total=len(result.items),
        done=sum(1 for item in result.items if item.download_status != "running" and item.transcribe_status != "running"),
        failed=result.failed_count,
        elapsed=format_duration(result.elapsed),
        active_budget=f"0/{min(concurrent, max(1, len(result.items)))}",
    )
    click.echo(render_overall_progress(totals, tty=sys.stdout.isatty()))
    click.echo(render_task_progress(views, tty=sys.stdout.isatty()))
    _print_task_timing(task_timer)
    if result.failed_count:
        sys.exit(1)
    return
```

Keep the existing `_run_downloads()` path for `--no-transcribe`.

- [ ] **Step 9: Implement `run_download_transcribe_pipeline()` wrapper**

Add to `casts_down/pipeline.py`:

```python
async def run_download_transcribe_pipeline(
    urls: list[str],
    download_all: bool,
    latest: int,
    output: str,
    concurrent: int,
    skip_existing: bool,
    model: str,
) -> PipelineResult:
    from casts_down.cli import detect_downloader, _download_podcast, _download_xiaoyuzhou
    from casts_down.transcribe import detect_engine

    items: list[PipelineItem] = []
    async def integration_shell_download(item: PipelineItem, on_done: DownloadDoneCallback) -> None:
        raise RuntimeError("run_download_transcribe_pipeline requires Task 6 platform downloader integration")

    # This shell exists only so CLI tests can patch the symbol in Task 5.
    # Task 6 replaces it with real download job scheduling before the feature is usable.
    engine = detect_engine(model=model)
    return await run_file_pipeline(items, integration_shell_download, engine, concurrent, transcribe=True)
```

This temporary shell should make the test with mocked `run_download_transcribe_pipeline` pass without enabling the real pipeline before Task 6.

- [ ] **Step 10: Run CLI tests**

Run:

```bash
python -m pytest tests/test_cli.py -q -k 'not DryRunItunesApiToRss and not DryRunCliPipeline and not DryRunDepCheck'
```

Expected: PASS for mocked CLI integration tests.

- [ ] **Step 11: Commit CLI integration shell**

Run:

```bash
git add casts_down/cli.py casts_down/pipeline.py tests/test_cli.py
git commit -m "feat: route transcription downloads through pipeline shell"
```

---

## Task 6: Real Podcast Pipeline Scheduling

**Files:**
- Modify: `casts_down/cli.py`
- Modify: `casts_down/pipeline.py`
- Modify: `casts_down/downloaders/base.py`
- Modify: `casts_down/downloaders/xiaoyuzhou.py`
- Modify: `tests/test_pipeline.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing test for real pipeline scheduling with fake downloader**

Append to `tests/test_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_run_download_transcribe_pipeline_accepts_preselected_download_jobs(tmp_path):
    from casts_down.pipeline import DownloadJob, run_download_jobs_pipeline

    paths = [tmp_path / "a.mp3", tmp_path / "b.mp3"]
    events = []

    async def download_a(on_done):
        paths[0].write_bytes(b"a")
        await on_done(paths[0], "download a")
        events.append("download a")

    async def download_b(on_done):
        await asyncio.sleep(0.05)
        paths[1].write_bytes(b"b")
        await on_done(paths[1], "download b")
        events.append("download b")

    result = await run_download_jobs_pipeline(
        jobs=[
            DownloadJob(index=1, source_url="url-a", title="a", run=download_a),
            DownloadJob(index=2, source_url="url-b", title="b", run=download_b),
        ],
        engine=DummyPipelineEngine(),
        user_concurrent=3,
        event_log=events,
    )

    assert result.failed_count == 0
    assert events.index("transcribe a.mp3") < events.index("download b")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_pipeline.py::test_run_download_transcribe_pipeline_accepts_preselected_download_jobs -q
```

Expected: FAIL with missing `DownloadJob` or `run_download_jobs_pipeline`.

- [ ] **Step 3: Implement `DownloadJob` and job pipeline adapter**

Add to `casts_down/pipeline.py`:

```python
JobDoneCallback = Callable[[Path, str], Awaitable[None]]
JobRun = Callable[[JobDoneCallback], Awaitable[None]]


@dataclass
class DownloadJob:
    index: int
    source_url: str
    title: str
    run: JobRun


async def run_download_jobs_pipeline(
    jobs: list[DownloadJob],
    engine: TranscribeEngine,
    user_concurrent: int,
    language: str | None = None,
    event_log: list[str] | None = None,
) -> PipelineResult:
    item_by_index = {
        job.index: PipelineItem(index=job.index, source_url=job.source_url, title=job.title)
        for job in jobs
    }

    async def download_one(item: PipelineItem, on_done: DownloadDoneCallback) -> None:
        job = next(job for job in jobs if job.index == item.index)

        async def done(path: Path, message: str) -> None:
            await on_done(item, path, message)

        await job.run(done)

    return await run_file_pipeline(
        list(item_by_index.values()),
        download_one,
        engine,
        user_concurrent=user_concurrent,
        transcribe=True,
        language=language,
        event_log=event_log,
    )
```

- [ ] **Step 4: Run pipeline tests**

Run:

```bash
python -m pytest tests/test_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 5: Refactor CLI download preparation into job generation**

Modify `casts_down/cli.py` to add a helper that resolves URLs and builds `DownloadJob` objects without starting all downloads immediately:

```python
async def _build_download_jobs(
    urls: list[str],
    download_all: bool,
    latest: int,
    output: str,
    concurrent: int,
    skip_existing: bool,
) -> tuple[list["DownloadJob"], list[tuple[str, str]]]:
    from casts_down.pipeline import DownloadJob

    jobs: list[DownloadJob] = []
    failures: list[tuple[str, str]] = []
    next_index = 1

    # For the first implementation, use existing platform download methods per
    # URL and enqueue each returned file as it is reported through on_file_done.
    # Later refactors can split into one job per episode before network download.
    for current_url in urls:
        async def run_url(on_done, current_url=current_url):
            files = []

            def _on_file_done(path, episode, message):
                asyncio.create_task(on_done(path, message))

            downloader_type = detect_downloader(current_url)
            if downloader_type == "xiaoyuzhou":
                files.extend(await _download_xiaoyuzhou(
                    url=current_url,
                    output=output,
                    concurrent=concurrent,
                    skip_existing=skip_existing,
                    latest=latest if not download_all else None,
                ))
            else:
                files.extend(await _download_podcast(
                    url=current_url,
                    download_all=download_all,
                    latest=latest,
                    output=output,
                    concurrent=concurrent,
                    skip_existing=skip_existing,
                ))
            for path in files:
                await on_done(path, f"done {path.name}")

        jobs.append(DownloadJob(index=next_index, source_url=current_url, title=current_url, run=run_url))
        next_index += 1

    return jobs, failures
```

This keeps the first real integration conservative and does not yet require a large downloader split.

- [ ] **Step 6: Wire `run_download_transcribe_pipeline()` to generated jobs**

Modify `casts_down/pipeline.py` or move the wrapper to `cli.py` so it:

```python
jobs, failures = await _build_download_jobs(...)
engine = detect_engine(model=model)
result = await run_download_jobs_pipeline(jobs, engine=engine, user_concurrent=concurrent)
```

For any URL-level failures, append red `PipelineItem` rows with `download_status="failed"`, `transcribe_status="skipped"`, and the failure reason.

- [ ] **Step 7: Run CLI and pipeline tests**

Run:

```bash
python -m pytest tests/test_pipeline.py tests/test_cli.py -q -k 'not DryRunItunesApiToRss and not DryRunCliPipeline and not DryRunDepCheck'
```

Expected: PASS.

- [ ] **Step 8: Commit real pipeline scheduling**

Run:

```bash
git add casts_down/cli.py casts_down/pipeline.py tests/test_pipeline.py tests/test_cli.py
git commit -m "feat: run download transcription pipeline"
```

---

## Task 7: Documentation And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing README/help alignment test**

Add to `tests/test_cli.py`:

```python
def test_readme_documents_pipeline_concurrent_semantics():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "Max active pipeline tasks" in readme
    assert "shared by downloads and transcription" in readme
    assert "--latest 50 --concurrent 3" in readme
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_cli.py::test_readme_documents_pipeline_concurrent_semantics -q
```

Expected: FAIL until README is updated.

- [ ] **Step 3: Update README concurrent and pipeline examples**

Modify README option table:

```markdown
| `--concurrent N` | `-c N` | Max active pipeline tasks. With transcription enabled, shared by downloads and transcription; with `--no-transcribe`, parallel downloads. Capped by selected episode count. | 3 |
```

Add examples:

```markdown
### Pipeline download and transcribe latest 50 episodes

```bash
casts-down "https://feeds.example.com/podcast.rss" --latest 50 --concurrent 3
```

With transcription enabled, `--concurrent 3` means at most three active pipeline tasks, typically two downloads plus one transcription. If only one episode is selected, the effective concurrency is one.

```bash
casts-down "https://feeds.example.com/podcast.rss" --latest 50 --concurrent 1
```

This disables overlap and runs one active task at a time.

```bash
casts-down "https://feeds.example.com/podcast.rss" --latest 50 --no-transcribe --concurrent 5
```

With `--no-transcribe`, the same option controls parallel downloads only.
```

- [ ] **Step 4: Run documentation test**

Run:

```bash
python -m pytest tests/test_cli.py::test_readme_documents_pipeline_concurrent_semantics -q
```

Expected: PASS.

- [ ] **Step 5: Run full project verification**

Run:

```bash
make lint
python -m pytest tests/test_cli.py tests/test_downloaders.py tests/test_naming.py tests/test_transcribe_formatter.py tests/test_transcribe_batch.py tests/test_transcribe_installer.py tests/test_transcribe_engine.py tests/test_word_stats.py tests/test_progress.py tests/test_pipeline.py -q -k 'not DryRunItunesApiToRss and not DryRunCliPipeline and not DryRunDepCheck'
git diff --check
```

Expected:

```text
All files compile OK
all selected tests pass
git diff --check prints nothing
```

- [ ] **Step 6: Build package**

Run:

```bash
make dist
```

Expected:

```text
Successfully built casts_down-<version>.tar.gz and casts_down-<version>-py3-none-any.whl
```

- [ ] **Step 7: Commit docs and final verification adjustments**

Run:

```bash
git add README.md tests/test_cli.py
git commit -m "docs: describe pipeline concurrency"
```

- [ ] **Step 8: Final pre-push status check**

Run:

```bash
git status -sb
git log --oneline --decorate -n 8
```

Expected: working tree clean, local branch contains the task commits.

---

## Self-Review

Spec coverage:

- Pipeline overlap is covered by Task 4 and Task 6.
- Shared `--concurrent` semantics are covered by Task 4, Task 5, and Task 7.
- Overall and per-task progress tables are covered by Task 1 and Task 5.
- Yellow ETA background is covered by Task 1.
- Final color-coded report fields are covered by Task 1 and Task 5.
- Stability and failure isolation are covered by Task 2, Task 3, Task 4, and Task 6.
- README/help updates are covered by Task 5 and Task 7.
- Testing requirements are covered across Tasks 1-7.

Red-flag scan:

- No unfinished-marker red flags remain.
- The plan includes explicit commands and expected outcomes for each task.

Type consistency:

- `PipelineItem`, `PipelineResult`, `DownloadJob`, `PipelineTaskView`, and `ProgressTotals` are defined before later tasks use them.
- The plan keeps the first implementation to one transcription worker and does not introduce multiple-GPU scheduling.
