"""Tests for setup-transcribe environment detection and installation."""
from unittest.mock import patch
import pytest
from casts_down.transcribe.installer import detect_platform, get_install_packages

class TestDetectPlatform:
    @patch("casts_down.transcribe.installer.platform")
    def test_mac_arm64(self, mock_platform):
        mock_platform.system.return_value = "Darwin"
        mock_platform.machine.return_value = "arm64"
        assert detect_platform() == "mac_arm64"

    @patch("casts_down.transcribe.installer.platform")
    def test_mac_intel(self, mock_platform):
        mock_platform.system.return_value = "Darwin"
        mock_platform.machine.return_value = "x86_64"
        assert detect_platform() == "mac_intel"

    @patch("casts_down.transcribe.installer.platform")
    def test_linux(self, mock_platform):
        mock_platform.system.return_value = "Linux"
        mock_platform.machine.return_value = "x86_64"
        assert detect_platform() == "linux"

    @patch("casts_down.transcribe.installer.platform")
    def test_windows(self, mock_platform):
        mock_platform.system.return_value = "Windows"
        mock_platform.machine.return_value = "AMD64"
        assert detect_platform() == "windows"

    @patch("casts_down.transcribe.installer.platform")
    def test_unknown_platform(self, mock_platform):
        mock_platform.system.return_value = "FreeBSD"
        mock_platform.machine.return_value = "x86_64"
        assert detect_platform() == "unknown"

class TestGetInstallPackages:
    def test_mac_arm64_packages(self):
        pkgs = get_install_packages("mac_arm64")
        assert "mlx-whisper>=0.4.0,<1.0.0" in pkgs
        assert "faster-whisper>=1.0.0,<2.0.0" in pkgs

    def test_mac_intel_packages(self):
        pkgs = get_install_packages("mac_intel")
        assert "faster-whisper>=1.0.0,<2.0.0" in pkgs
        assert not any("mlx" in p for p in pkgs)

    def test_linux_packages(self):
        pkgs = get_install_packages("linux")
        assert "faster-whisper>=1.0.0,<2.0.0" in pkgs
        assert not any("mlx" in p for p in pkgs)

    def test_windows_packages(self):
        pkgs = get_install_packages("windows")
        assert "faster-whisper>=1.0.0,<2.0.0" in pkgs
        assert not any("mlx" in p for p in pkgs)

class TestRunSetup:
    def test_prompts_before_install(self):
        from unittest.mock import patch
        with patch("casts_down.transcribe.installer._pip_install") as mock_pip, \
             patch("casts_down.transcribe.installer._predownload_model"), \
             patch("casts_down.transcribe.installer.click.confirm"):
            from casts_down.transcribe.installer import run_setup
            run_setup()
        mock_pip.assert_called()

    def test_backend_faster_whisper_only(self):
        from casts_down.transcribe.installer import get_install_packages
        pkgs = get_install_packages("mac_arm64", backend="faster-whisper")
        assert len(pkgs) == 1
        assert "faster-whisper" in pkgs[0]

    def test_backend_mlx_whisper(self):
        from casts_down.transcribe.installer import get_install_packages
        pkgs = get_install_packages("linux", backend="mlx-whisper")
        assert any("mlx-whisper" in p for p in pkgs)

    def test_run_setup_reports_windows_label(self, capsys):
        from casts_down.transcribe.installer import run_setup
        with patch("casts_down.transcribe.installer.detect_platform", return_value="windows"), \
             patch("casts_down.transcribe.installer._pip_install", return_value=True), \
             patch("casts_down.transcribe.installer._predownload_model"), \
             patch("casts_down.transcribe.installer.click.confirm"):
            run_setup()
        out = capsys.readouterr().out
        assert "Windows" in out
