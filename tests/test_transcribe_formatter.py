"""Tests for transcription output formatting."""
from pathlib import Path
from casts_down.transcribe.engine import Segment
from casts_down.transcribe.formatter import format_srt, format_txt, write_outputs

class TestSegmentDataclass:
    def test_segment_fields(self):
        s = Segment(start=1.5, end=3.0, text="hello")
        assert s.start == 1.5
        assert s.end == 3.0
        assert s.text == "hello"

class TestFormatSrt:
    def test_basic_srt(self, sample_segments):
        result = format_srt(sample_segments)
        lines = result.strip().split("\n")
        assert lines[0] == "1"
        assert lines[1] == "00:00:00,000 --> 00:00:03,500"
        assert lines[2] == "Hello and welcome to the show."
        assert lines[4] == "2"

    def test_srt_millisecond_precision(self):
        segments = [Segment(start=61.123, end=125.456, text="test")]
        result = format_srt(segments)
        assert "00:01:01,123 --> 00:02:05,456" in result

    def test_srt_millisecond_rounding_carries(self):
        segments = [Segment(start=1.9996, end=62.9996, text="rounded")]
        result = format_srt(segments)
        assert "00:00:02,000 --> 00:01:03,000" in result

    def test_srt_hour_overflow(self):
        segments = [Segment(start=3661.0, end=3662.0, text="over an hour")]
        result = format_srt(segments)
        assert "01:01:01,000 --> 01:01:02,000" in result

    def test_empty_segments(self, empty_segments):
        result = format_srt(empty_segments)
        assert result == ""

    def test_chinese_content(self, sample_segments):
        result = format_srt(sample_segments)
        assert "这是一段中文测试内容。" in result

class TestFormatTxt:
    def test_basic_txt(self, sample_segments):
        result = format_txt(sample_segments)
        lines = result.strip().split("\n")
        assert lines[0] == "[00:00:00] Hello and welcome to the show."
        assert lines[1] == "[00:00:03] Today we're going to talk about..."

    def test_txt_second_precision(self):
        segments = [Segment(start=61.9, end=125.0, text="test")]
        result = format_txt(segments)
        assert "[00:01:01]" in result

    def test_empty_segments(self, empty_segments):
        result = format_txt(empty_segments)
        assert result == ""

class TestWriteOutputs:
    def test_writes_srt_txt_and_words_json(self, tmp_path, sample_segments):
        audio_path = tmp_path / "episode.mp3"
        audio_path.touch()
        write_outputs(audio_path, sample_segments)
        assert (tmp_path / "episode.srt").exists()
        assert (tmp_path / "episode.txt").exists()
        assert (tmp_path / "episode.words.json").exists()

    def test_utf8_encoding(self, tmp_path, sample_segments):
        audio_path = tmp_path / "episode.mp3"
        audio_path.touch()
        write_outputs(audio_path, sample_segments)
        content = (tmp_path / "episode.srt").read_text(encoding="utf-8")
        assert "这是一段中文测试内容。" in content

    def test_no_bom(self, tmp_path, single_segment):
        audio_path = tmp_path / "episode.mp3"
        audio_path.touch()
        write_outputs(audio_path, single_segment)
        raw = (tmp_path / "episode.srt").read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")

    def test_writes_to_temp_then_renames(self, tmp_path, sample_segments):
        audio_path = tmp_path / "episode.mp3"
        audio_path.touch()
        write_outputs(audio_path, sample_segments)
        assert list(tmp_path.glob("*.tmp")) == []

    def test_tmp_files_use_safe_naming(self):
        """Temp file naming works on Python 3.10 (no compound suffix)."""
        import tempfile
        from casts_down.transcribe.engine import Segment
        from casts_down.transcribe.formatter import write_outputs

        segments = [Segment(start=0.0, end=1.0, text="Test")]
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "test.mp3"
            audio_path.write_bytes(b"fake")
            srt, txt, words_json = write_outputs(audio_path, segments)
            assert srt.exists()
            assert txt.exists()
            assert words_json.exists()
            assert srt.suffix == ".srt"
            assert txt.suffix == ".txt"
            assert words_json.name == "test.words.json"
