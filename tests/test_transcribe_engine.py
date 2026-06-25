"""Tests for engine detection and fallback logic."""
import os
from unittest.mock import patch, MagicMock
import importlib
import pytest

from casts_down.transcribe.engine import TranscribeEngine, Segment


class TestTranscribeEngineABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            TranscribeEngine()

    def test_concrete_engine_must_implement_transcribe(self):
        class BadEngine(TranscribeEngine):
            pass
        with pytest.raises(TypeError):
            BadEngine()

    def test_concrete_engine_works(self):
        class GoodEngine(TranscribeEngine):
            def transcribe(self, audio_path, language=None):
                return [Segment(0.0, 1.0, "test")]
        engine = GoodEngine()
        assert len(engine.transcribe("dummy")) == 1


class TestDetectEngine:
    def test_mac_arm64_prefers_mlx(self):
        mock_mlx = MagicMock()
        with patch.dict("sys.modules", {"mlx_whisper": mock_mlx}):
            import casts_down.transcribe as t
            t = importlib.reload(t)
            with patch.object(t.platform, "system", return_value="Darwin"), \
                 patch.object(t.platform, "machine", return_value="arm64"):
                engine = t.detect_engine(model="small")
                assert type(engine).__name__ == "MLXWhisperEngine"

    def test_mac_arm64_falls_back_to_faster_whisper(self):
        mock_fw = MagicMock()
        with patch.dict("sys.modules", {"mlx_whisper": None, "faster_whisper": mock_fw}):
            import casts_down.transcribe as t
            t = importlib.reload(t)
            with patch.object(t.platform, "system", return_value="Darwin"), \
                 patch.object(t.platform, "machine", return_value="arm64"):
                engine = t.detect_engine(model="small")
                assert type(engine).__name__ == "FasterWhisperEngine"

    def test_linux_uses_faster_whisper(self):
        mock_fw = MagicMock()
        with patch.dict("sys.modules", {"faster_whisper": mock_fw, "mlx_whisper": None}):
            import casts_down.transcribe as t
            t = importlib.reload(t)
            with patch.object(t.platform, "system", return_value="Linux"), \
                 patch.object(t.platform, "machine", return_value="x86_64"):
                engine = t.detect_engine(model="small")
                assert type(engine).__name__ == "FasterWhisperEngine"

    def test_no_engine_raises_error(self):
        with patch.dict("sys.modules", {"faster_whisper": None, "mlx_whisper": None}):
            import casts_down.transcribe as t
            t = importlib.reload(t)
            with patch.object(t.platform, "system", return_value="Linux"), \
                 patch.object(t.platform, "machine", return_value="x86_64"):
                with pytest.raises(RuntimeError, match="setup-transcribe"):
                    t.detect_engine(model="small")


class TestWindowsCudaDllPaths:
    def test_non_windows_cuda_dll_path_setup_is_noop(self):
        from casts_down.transcribe.faster_whisper_engine import _prepare_windows_cuda_dll_paths

        with patch("casts_down.transcribe.faster_whisper_engine.platform.system", return_value="Linux"):
            assert _prepare_windows_cuda_dll_paths() == []

    def test_windows_cuda_dll_path_setup_adds_nvidia_bins(self, tmp_path, monkeypatch):
        from casts_down.transcribe.faster_whisper_engine import _prepare_windows_cuda_dll_paths

        site_dir = tmp_path / "site-packages"
        cublas_bin = site_dir / "nvidia" / "cublas" / "bin"
        cudnn_bin = site_dir / "nvidia" / "cudnn" / "bin"
        cublas_bin.mkdir(parents=True)
        cudnn_bin.mkdir(parents=True)
        monkeypatch.setenv("PATH", "C:\\Windows")

        added_handles = []

        def fake_add_dll_directory(path):
            added_handles.append(path)
            return object()

        with patch("casts_down.transcribe.faster_whisper_engine.platform.system", return_value="Windows"), \
             patch("casts_down.transcribe.faster_whisper_engine.site.getsitepackages", return_value=[str(site_dir)]), \
             patch("casts_down.transcribe.faster_whisper_engine.os.add_dll_directory", side_effect=fake_add_dll_directory, create=True):
            added = _prepare_windows_cuda_dll_paths()

        assert str(cublas_bin) in added
        assert str(cudnn_bin) in added
        assert str(cublas_bin) in os.environ["PATH"]
        assert str(cudnn_bin) in os.environ["PATH"]
        assert added_handles == [str(cublas_bin), str(cudnn_bin)]


class TestFasterWhisperFallbackLogging:
    def test_cuda_init_failure_logs_device_fallback(self, capsys):
        from casts_down.transcribe.faster_whisper_engine import FasterWhisperEngine

        engine = FasterWhisperEngine(model="tiny")
        with patch.object(engine, "_load_model", side_effect=[RuntimeError("CUDA missing"), None]):
            engine._ensure_model()

        out = capsys.readouterr().out
        assert "CUDA device fallback" in out
        assert "CPU" in out
