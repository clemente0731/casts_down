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
