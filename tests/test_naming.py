"""Tests for downloader filename generation."""

from pathlib import Path

from casts_down.downloaders.naming import (
    build_media_filename,
    dedupe_filename,
    is_valid_media_filename,
)


def test_generated_filename_is_cross_platform_valid():
    filename = build_media_filename(
        episode_title='Dr Rachel Rubin: Women’s Sexual Health, Menopause, "HRT" & Orgasms!',
        audio_url="https://example.com/audio.MP3?token=abc",
        podcast_name="The Diary Of A CEO / Steven Bartlett?",
    )

    assert filename == (
        "the-diary-of-a-ceo-steven-bartlett--"
        "dr-rachel-rubin-womens-sexual-health-menopause-hrt-and-orgasms.mp3"
    )
    assert is_valid_media_filename(filename)


def test_reserved_windows_device_name_is_made_safe():
    filename = build_media_filename(
        episode_title="CON",
        audio_url="https://example.com/audio.mp3",
    )

    assert filename == "con-episode.mp3"
    assert is_valid_media_filename(filename)


def test_punctuation_only_title_uses_valid_fallback():
    filename = build_media_filename(
        episode_title="?!...///",
        audio_url="https://example.com/audio",
    )

    assert filename == "episode.mp3"
    assert is_valid_media_filename(filename)


def test_dedupe_filename_adds_number_before_extension_case_insensitively():
    used = {"podcast--episode.mp3", "Podcast--Episode-2.mp3"}

    filename = dedupe_filename("podcast--episode.mp3", used)

    assert filename == "podcast--episode-3.mp3"
    assert is_valid_media_filename(filename)


def test_long_deduped_filename_remains_within_byte_limit():
    filename = "a" * 235 + ".mp3"
    used = {filename}

    deduped = dedupe_filename(filename, used)

    assert deduped.endswith("-2.mp3")
    assert len(deduped.encode("utf-8")) <= 240
    assert is_valid_media_filename(deduped)


def test_transcript_outputs_share_downloaded_audio_basename(tmp_path):
    from casts_down.transcribe.engine import Segment
    from casts_down.transcribe.formatter import write_outputs

    audio_name = build_media_filename(
        episode_title="Episode: One/Two?",
        audio_url="https://example.com/audio.mp3",
        podcast_name="My Podcast",
    )
    audio_path = tmp_path / audio_name
    audio_path.write_bytes(b"audio")

    write_outputs(audio_path, [Segment(start=0, end=1, text="hello")])

    assert (tmp_path / "my-podcast--episode-one-two.srt").exists()
    assert (tmp_path / "my-podcast--episode-one-two.txt").exists()
    assert is_valid_media_filename(Path(audio_name).name)
