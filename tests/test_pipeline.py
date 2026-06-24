"""Tests for the download/transcribe pipeline."""

from __future__ import annotations

import asyncio

import pytest

from casts_down.pipeline import (
    PipelineItem,
    allocate_pipeline_workers,
    run_file_pipeline,
)


def test_allocate_pipeline_workers_handles_empty_selection():
    assert allocate_pipeline_workers(3, 0, transcribe=True) == (0, 0)
    assert allocate_pipeline_workers(3, -1, transcribe=True) == (0, 0)


def test_allocate_pipeline_workers_download_only_uses_effective_concurrency():
    assert allocate_pipeline_workers(0, 3, transcribe=False) == (1, 0)
    assert allocate_pipeline_workers(10, 3, transcribe=False) == (3, 0)


def test_allocate_pipeline_workers_reserves_one_worker_for_transcription():
    assert allocate_pipeline_workers(1, 3, transcribe=True) == (1, 0)
    assert allocate_pipeline_workers(2, 3, transcribe=True) == (1, 1)
    assert allocate_pipeline_workers(4, 3, transcribe=True) == (2, 1)


@pytest.mark.asyncio
async def test_single_selected_item_still_transcribes_without_overlap(tmp_path, monkeypatch):
    event_log = []
    items = [PipelineItem(1, "https://example.test/only.mp3", "only")]

    async def download_one(item, on_done):
        path = tmp_path / "only.mp3"
        path.touch()
        on_done(item, path, "downloaded only")
        event_log.append("download end only")

    def fake_transcribe_one(audio_path, engine, language=None):
        return {
            "status": "succeeded",
            "outputs": [audio_path.with_suffix(".txt")],
            "error": None,
            "duration": 0.01,
        }

    monkeypatch.setattr("casts_down.pipeline.transcribe_one", fake_transcribe_one)

    result = await run_file_pipeline(
        items,
        download_one=download_one,
        engine=object(),
        user_concurrent=3,
        transcribe=True,
        event_log=event_log,
    )

    assert allocate_pipeline_workers(3, 1, transcribe=True) == (1, 0)
    assert result.failed_count == 0
    assert items[0].download_status == "succeeded"
    assert items[0].transcribe_status == "succeeded"
    assert event_log == ["download end only", "transcribe only.mp3"]


@pytest.mark.asyncio
async def test_single_worker_transcribes_items_sequentially(tmp_path, monkeypatch):
    event_log = []
    items = [
        PipelineItem(1, "https://example.test/first.mp3", "first"),
        PipelineItem(2, "https://example.test/second.mp3", "second"),
    ]

    async def download_one(item, on_done):
        event_log.append(f"download start {item.title}")
        path = tmp_path / f"{item.title}.mp3"
        path.touch()
        on_done(item, path, f"downloaded {item.title}")
        event_log.append(f"download end {item.title}")

    def fake_transcribe_one(audio_path, engine, language=None):
        return {
            "status": "succeeded",
            "outputs": [audio_path.with_suffix(".txt")],
            "error": None,
            "duration": 0.01,
        }

    monkeypatch.setattr("casts_down.pipeline.transcribe_one", fake_transcribe_one)

    result = await run_file_pipeline(
        items,
        download_one=download_one,
        engine=object(),
        user_concurrent=1,
        transcribe=True,
        event_log=event_log,
    )

    assert result.failed_count == 0
    assert [item.transcribe_status for item in items] == ["succeeded", "succeeded"]
    assert event_log.index("download end first") < event_log.index("transcribe first.mp3")
    assert event_log.index("transcribe first.mp3") < event_log.index("download start second")


@pytest.mark.asyncio
async def test_transcribe_false_skips_transcription(tmp_path, monkeypatch):
    event_log = []
    items = [PipelineItem(1, "https://example.test/only.mp3", "only")]

    async def download_one(item, on_done):
        path = tmp_path / "only.mp3"
        path.touch()
        on_done(item, path, "downloaded only")
        event_log.append("download end only")

    def fake_transcribe_one(audio_path, engine, language=None):
        raise AssertionError("transcribe_one should not be called")

    monkeypatch.setattr("casts_down.pipeline.transcribe_one", fake_transcribe_one)

    result = await run_file_pipeline(
        items,
        download_one=download_one,
        engine=object(),
        user_concurrent=1,
        transcribe=False,
        event_log=event_log,
    )

    assert result.failed_count == 0
    assert items[0].download_status == "succeeded"
    assert items[0].transcribe_status == "skipped"
    assert event_log == ["download end only"]


@pytest.mark.asyncio
async def test_first_completed_download_is_transcribed_before_later_download_finishes(
    tmp_path, monkeypatch
):
    event_log = []
    items = [
        PipelineItem(1, "https://example.test/slow.mp3", "slow"),
        PipelineItem(2, "https://example.test/fast.mp3", "fast"),
        PipelineItem(3, "https://example.test/last.mp3", "last"),
    ]

    async def download_one(item, on_done):
        event_log.append(f"download start {item.title}")
        if item.title == "slow":
            await asyncio.sleep(0.05)
        path = tmp_path / f"{item.title}.mp3"
        path.touch()
        on_done(item, path, f"downloaded {item.title}")
        event_log.append(f"download end {item.title}")

    def fake_transcribe_one(audio_path, engine, language=None):
        return {
            "status": "succeeded",
            "outputs": [audio_path.with_suffix(".txt")],
            "error": None,
            "duration": 0.01,
        }

    monkeypatch.setattr("casts_down.pipeline.transcribe_one", fake_transcribe_one)

    result = await run_file_pipeline(
        items,
        download_one=download_one,
        engine=object(),
        user_concurrent=3,
        transcribe=True,
        event_log=event_log,
    )

    assert result.failed_count == 0
    assert event_log.index("download end fast") < event_log.index("transcribe fast.mp3")
    assert event_log.index("transcribe fast.mp3") < event_log.index("download end slow")
    assert items[1].transcribe_status == "succeeded"


@pytest.mark.asyncio
async def test_unexpected_transcription_exception_does_not_stop_pipeline(
    tmp_path, monkeypatch
):
    items = [
        PipelineItem(1, "https://example.test/bad.mp3", "bad"),
        PipelineItem(2, "https://example.test/good.mp3", "good"),
    ]

    async def download_one(item, on_done):
        path = tmp_path / f"{item.title}.mp3"
        path.touch()
        on_done(item, path, f"downloaded {item.title}")

    def fake_transcribe_one(audio_path, engine, language=None):
        if audio_path.name == "bad.mp3":
            raise RuntimeError("thread exploded")
        return {
            "status": "succeeded",
            "outputs": [audio_path.with_suffix(".txt")],
            "error": None,
            "duration": 0.01,
        }

    monkeypatch.setattr("casts_down.pipeline.transcribe_one", fake_transcribe_one)

    result = await asyncio.wait_for(
        run_file_pipeline(
            items,
            download_one=download_one,
            engine=object(),
            user_concurrent=2,
            transcribe=True,
        ),
        timeout=1,
    )

    assert result.failed_count == 1
    assert items[0].transcribe_status == "failed"
    assert items[0].error == "RuntimeError: thread exploded"
    assert items[0].transcribe_elapsed > 0
    assert items[1].transcribe_status == "succeeded"


@pytest.mark.asyncio
async def test_duplicate_on_done_transcribes_item_once(tmp_path, monkeypatch):
    event_log = []
    items = [
        PipelineItem(1, "https://example.test/dup.mp3", "dup"),
        PipelineItem(2, "https://example.test/other.mp3", "other"),
    ]

    async def download_one(item, on_done):
        path = tmp_path / f"{item.title}.mp3"
        path.touch()
        on_done(item, path, f"downloaded {item.title}")
        if item.title == "dup":
            on_done(item, path, f"downloaded {item.title} again")

    def fake_transcribe_one(audio_path, engine, language=None):
        return {
            "status": "succeeded",
            "outputs": [audio_path.with_suffix(".txt")],
            "error": None,
            "duration": 0.01,
        }

    monkeypatch.setattr("casts_down.pipeline.transcribe_one", fake_transcribe_one)

    result = await run_file_pipeline(
        items,
        download_one=download_one,
        engine=object(),
        user_concurrent=2,
        transcribe=True,
        event_log=event_log,
    )

    assert result.failed_count == 0
    assert event_log.count("transcribe dup.mp3") == 1
    assert event_log.count("transcribe other.mp3") == 1


@pytest.mark.asyncio
async def test_on_done_then_download_exception_preserves_success_and_transcribes_once(
    tmp_path, monkeypatch
):
    event_log = []
    items = [
        PipelineItem(1, "https://example.test/fragile.mp3", "fragile"),
        PipelineItem(2, "https://example.test/other.mp3", "other"),
    ]

    async def download_one(item, on_done):
        path = tmp_path / f"{item.title}.mp3"
        path.touch()
        on_done(item, path, f"downloaded {item.title}")
        if item.title == "fragile":
            raise RuntimeError("late download failure")

    def fake_transcribe_one(audio_path, engine, language=None):
        return {
            "status": "succeeded",
            "outputs": [audio_path.with_suffix(".txt")],
            "error": None,
            "duration": 0.01,
        }

    monkeypatch.setattr("casts_down.pipeline.transcribe_one", fake_transcribe_one)

    result = await run_file_pipeline(
        items,
        download_one=download_one,
        engine=object(),
        user_concurrent=2,
        transcribe=True,
        event_log=event_log,
    )

    assert result.failed_count == 0
    assert items[0].download_status == "succeeded"
    assert items[0].transcribe_status == "succeeded"
    assert items[0].error is None
    assert event_log.count("transcribe fragile.mp3") == 1
    assert items[1].transcribe_status == "succeeded"


@pytest.mark.asyncio
async def test_download_failure_does_not_enqueue_transcription_and_later_items_succeed(
    tmp_path, monkeypatch
):
    event_log = []
    items = [
        PipelineItem(1, "https://example.test/bad.mp3", "bad"),
        PipelineItem(2, "https://example.test/good.mp3", "good"),
    ]

    async def download_one(item, on_done):
        if item.title == "bad":
            raise RuntimeError("download exploded")
        path = tmp_path / "good.mp3"
        path.touch()
        on_done(item, path, "downloaded good")

    def fake_transcribe_one(audio_path, engine, language=None):
        return {
            "status": "succeeded",
            "outputs": [audio_path.with_suffix(".txt")],
            "error": None,
            "duration": 0.01,
        }

    monkeypatch.setattr("casts_down.pipeline.transcribe_one", fake_transcribe_one)

    result = await run_file_pipeline(
        items,
        download_one=download_one,
        engine=object(),
        user_concurrent=2,
        transcribe=True,
        event_log=event_log,
    )

    assert result.failed_count == 1
    assert items[0].download_status == "failed"
    assert items[0].transcribe_status == "skipped"
    assert "RuntimeError: download exploded" in items[0].error
    assert "transcribe bad.mp3" not in event_log
    assert items[1].download_status == "succeeded"
    assert items[1].transcribe_status == "succeeded"


@pytest.mark.asyncio
async def test_transcription_failure_does_not_stop_later_items(tmp_path, monkeypatch):
    items = [
        PipelineItem(1, "https://example.test/bad.mp3", "bad"),
        PipelineItem(2, "https://example.test/good.mp3", "good"),
    ]

    async def download_one(item, on_done):
        path = tmp_path / f"{item.title}.mp3"
        path.touch()
        on_done(item, path, f"downloaded {item.title}")

    def fake_transcribe_one(audio_path, engine, language=None):
        if audio_path.name == "bad.mp3":
            return {
                "status": "failed",
                "outputs": [],
                "error": "RuntimeError: transcription exploded",
                "duration": 0.02,
            }
        return {
            "status": "succeeded",
            "outputs": [audio_path.with_suffix(".txt")],
            "error": None,
            "duration": 0.01,
        }

    monkeypatch.setattr("casts_down.pipeline.transcribe_one", fake_transcribe_one)

    result = await run_file_pipeline(
        items,
        download_one=download_one,
        engine=object(),
        user_concurrent=2,
        transcribe=True,
    )

    assert result.failed_count == 1
    assert items[0].download_status == "succeeded"
    assert items[0].transcribe_status == "failed"
    assert items[0].error == "RuntimeError: transcription exploded"
    assert items[1].download_status == "succeeded"
    assert items[1].transcribe_status == "succeeded"
