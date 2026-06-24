"""Tests for transcript word-frequency JSON generation."""

import json

from casts_down.transcribe.word_stats import (
    build_word_stats,
    extract_english_words,
    write_word_stats_json,
)


def test_extract_english_words_removes_timestamps_numbers_and_possessive_s():
    text = """
    [00:00:44] Already over 43,000 businesses chose NetSuite's guide.
    [00:01:11] So you said there's four personalities in everybody's brain.
    [00:01:47] It's state-of-the-art, and you don't want 2026 numbers.
    """

    words = extract_english_words(text)

    assert "00" not in words
    assert "43" not in words
    assert "000" not in words
    assert "s" not in words
    assert "netsuite" in words
    assert "everybody" in words
    assert "there" in words
    assert "state" in words
    assert "it" not in words
    assert "art" not in words
    assert "do" not in words
    assert "not" not in words


def test_extract_english_words_expands_common_contractions():
    text = "I'm here, we're calm, you've heard, you'd know, can't stop, doesn't fail."

    words = extract_english_words(text)

    assert words == ["here", "calm", "have", "heard", "would", "know", "stop", "does", "fail"]


def test_extract_english_words_filters_words_with_three_or_fewer_letters():
    text = "[00:00:01] I am the CEO, and you can see a safe brain learning."

    words = extract_english_words(text)

    assert words == ["safe", "brain", "learning"]


def test_build_word_stats_counts_all_words_sorted_by_count_then_word():
    stats = build_word_stats(
        "Brain brain safe. Am I safe? 123 safe learning!",
        audio_name="episode.mp3",
    )

    assert stats["audio"] == "episode.mp3"
    assert stats["total_words"] == 6
    assert stats["unique_words"] == 3
    assert stats["words"] == [
        {"word": "safe", "count": 3},
        {"word": "brain", "count": 2},
        {"word": "learning", "count": 1},
    ]


def test_build_word_stats_handles_empty_or_non_english_text():
    stats = build_word_stats("[00:00:01] 12345 你好 !!!", audio_name="episode.mp3")

    assert stats["total_words"] == 0
    assert stats["unique_words"] == 0
    assert stats["words"] == []


def test_write_word_stats_json_uses_atomic_temp_file(tmp_path):
    audio_path = tmp_path / "episode.mp3"
    audio_path.write_bytes(b"audio")

    json_path = write_word_stats_json(audio_path, "[00:00:01] That's safe. Safe!")

    assert json_path == tmp_path / "episode.words.json"
    assert not list(tmp_path.glob("*.tmp"))
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["audio"] == "episode.mp3"
    assert payload["words"] == [
        {"word": "safe", "count": 2},
        {"word": "that", "count": 1},
    ]
