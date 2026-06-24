"""Tests for batch transcription and reporting."""
from pathlib import Path
import pytest
from casts_down.transcribe.engine import Segment, TranscribeEngine

class DummyEngine(TranscribeEngine):
    def transcribe(self, audio_path, language=None):
        return [Segment(0.0, 1.0, "Hello"), Segment(1.0, 2.0, "World")]

class FailingEngine(TranscribeEngine):
    def transcribe(self, audio_path, language=None):
        raise RuntimeError("Simulated OOM")

class TestCollectAudioFiles:
    def test_finds_mp3_and_m4a(self, tmp_path):
        (tmp_path / "a.mp3").touch()
        (tmp_path / "b.m4a").touch()
        (tmp_path / "c.txt").touch()
        from casts_down.transcribe import collect_audio_files
        files = collect_audio_files(tmp_path)
        names = {f.name for f in files}
        assert names == {"a.mp3", "b.m4a"}

    def test_empty_directory(self, tmp_path):
        from casts_down.transcribe import collect_audio_files
        assert collect_audio_files(tmp_path) == []

    def test_finds_opus(self, tmp_path):
        (tmp_path / "a.opus").touch()
        from casts_down.transcribe import collect_audio_files
        assert len(collect_audio_files(tmp_path)) == 1

class TestTranscribeBatch:
    def test_success(self, tmp_path):
        audio = tmp_path / "test.mp3"
        audio.touch()
        from casts_down.transcribe import transcribe_batch
        results = transcribe_batch([audio], engine=DummyEngine())
        assert len(results) == 1
        assert results[0]["success"] is True
        assert (tmp_path / "test.srt").exists()
        assert (tmp_path / "test.txt").exists()

    def test_batch_prints_progress_eta(self, tmp_path, capsys):
        a = tmp_path / "a.mp3"
        b = tmp_path / "b.mp3"
        a.touch()
        b.touch()
        from casts_down.transcribe import transcribe_batch
        transcribe_batch([a, b], engine=DummyEngine())
        out = capsys.readouterr().out
        assert "Transcription Progress" in out
        assert "ETA" in out

    def test_failure_does_not_block(self, tmp_path):
        a = tmp_path / "a.mp3"
        b = tmp_path / "b.mp3"
        a.touch()
        b.touch()
        class MixedEngine(TranscribeEngine):
            def __init__(self):
                self.call_count = 0
            def transcribe(self, audio_path, language=None):
                self.call_count += 1
                if self.call_count == 1:
                    raise RuntimeError("fail first")
                return [Segment(0.0, 1.0, "ok")]
        from casts_down.transcribe import transcribe_batch
        results = transcribe_batch([a, b], engine=MixedEngine())
        assert len(results) == 2
        assert results[0]["success"] is False
        assert results[1]["success"] is True

    def test_skip_already_transcribed(self, tmp_path):
        audio = tmp_path / "done.mp3"
        audio.touch()
        (tmp_path / "done.srt").write_text("existing", encoding="utf-8")
        (tmp_path / "done.txt").write_text("existing", encoding="utf-8")
        from casts_down.transcribe import transcribe_batch
        results = transcribe_batch([audio], engine=DummyEngine(), skip_transcribed=True)
        assert results[0]["success"] is True
        assert results[0]["skipped"] is True

    def test_re_transcribe_if_only_srt_exists(self, tmp_path):
        audio = tmp_path / "partial.mp3"
        audio.touch()
        (tmp_path / "partial.srt").write_text("old", encoding="utf-8")
        from casts_down.transcribe import transcribe_batch
        results = transcribe_batch([audio], engine=DummyEngine(), skip_transcribed=True)
        assert results[0]["skipped"] is False
        assert (tmp_path / "partial.txt").exists()

    def test_overwrite_existing(self, tmp_path):
        audio = tmp_path / "redo.mp3"
        audio.touch()
        (tmp_path / "redo.srt").write_text("old", encoding="utf-8")
        (tmp_path / "redo.txt").write_text("old", encoding="utf-8")
        from casts_down.transcribe import transcribe_batch
        results = transcribe_batch([audio], engine=DummyEngine(), overwrite=True)
        assert results[0]["skipped"] is False
        content = (tmp_path / "redo.srt").read_text(encoding="utf-8")
        assert "Hello" in content

    def test_empty_file_list(self):
        from casts_down.transcribe import transcribe_batch
        results = transcribe_batch([], engine=DummyEngine())
        assert results == []

    def test_keyboard_interrupt_cleans_up(self, tmp_path):
        a = tmp_path / "a.mp3"
        b = tmp_path / "b.mp3"
        a.touch()
        b.touch()
        class InterruptEngine(TranscribeEngine):
            def __init__(self):
                self.call_count = 0
            def transcribe(self, audio_path, language=None):
                self.call_count += 1
                if self.call_count == 2:
                    raise KeyboardInterrupt()
                return [Segment(0.0, 1.0, "ok")]
        from casts_down.transcribe import transcribe_batch
        results = transcribe_batch([a, b], engine=InterruptEngine())
        assert len(results) == 1
        assert results[0]["success"] is True
        assert list(tmp_path.glob("*.tmp")) == []

class TestPrintReport:
    def test_report_format(self, capsys):
        from casts_down.transcribe import print_report
        results = [
            {"file": Path("a.mp3"), "success": True, "skipped": False, "duration": 3.5, "error": None},
            {"file": Path("b.mp3"), "success": False, "skipped": False, "duration": 0, "error": "OOM"},
        ]
        print_report(results)
        out = capsys.readouterr().out
        assert "1/2 succeeded" in out
        assert "FAILED" in out

    def test_empty_report(self, capsys):
        from casts_down.transcribe import print_report
        print_report([])
        out = capsys.readouterr().out
        assert "No files" in out
