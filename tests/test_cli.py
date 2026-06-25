"""Tests for CLI command routing and arguments."""
import pytest
from unittest.mock import patch
from click.testing import CliRunner
from casts_down.cli import main, check_system_deps
from casts_down.pipeline import PipelineItem, PipelineResult

@pytest.fixture
def runner():
    return CliRunner()

class TestMainGroup:
    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Casts Down" in result.output

    def test_help_describes_pipeline_concurrency(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Max active pipeline tasks" in result.output

    def test_short_help(self, runner):
        result = runner.invoke(main, ["-h"])
        assert result.exit_code == 0
        assert "Casts Down" in result.output

    def test_no_args_shows_help(self, runner):
        result = runner.invoke(main, [])
        assert result.exit_code == 0

    @patch("casts_down.cli._download_podcast")
    def test_download_options_can_follow_url(self, mock_dl, runner):
        mock_dl.return_value = []
        result = runner.invoke(main, [
            "https://example.com/feed.rss",
            "--latest", "3",
            "--no-transcribe",
        ])
        assert result.exit_code == 0
        mock_dl.assert_called_once()
        assert mock_dl.call_args.kwargs["latest"] == 3

    def test_download_options_without_url_error(self, runner):
        result = runner.invoke(main, ["--latest", "2"])
        assert result.exit_code != 0
        assert "Missing URL" in result.output

    def test_version_matches_pyproject(self):
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        from casts_down import __version__
        with open("pyproject.toml", "rb") as f:
            pyproject = tomllib.load(f)
        assert pyproject["project"]["version"] == __version__

class TestTranscribeFlag:
    @patch("casts_down.cli.run_download_transcribe_pipeline")
    def test_transcribe_flag_uses_pipeline(self, mock_pipeline, runner):
        mock_pipeline.return_value = PipelineResult(
            items=[PipelineItem(1, "https://example.com/feed.rss", "episode", transcribe_status="succeeded")],
            elapsed=0.01,
        )
        # Options must precede the URL positional argument in Click's parsing
        result = runner.invoke(main, ["--transcribe", "https://example.com/feed.rss"])
        assert result.exit_code == 0
        mock_pipeline.assert_called_once()

    @patch("casts_down.cli._download_podcast")
    def test_default_empty_download_has_no_batch_transcription(self, mock_dl, runner):
        mock_dl.return_value = []
        with patch("casts_down.cli._run_transcription") as mock_tr:
            result = runner.invoke(main, ["--no-transcribe", "https://example.com/feed.rss"])
            mock_tr.assert_not_called()

class TestTranscribeSubcommand:
    def test_transcribe_help(self, runner):
        result = runner.invoke(main, ["transcribe", "--help"])
        assert result.exit_code == 0
        assert "--model" in result.output

    def test_transcribe_short_help(self, runner):
        result = runner.invoke(main, ["transcribe", "-h"])
        assert result.exit_code == 0
        assert "--model" in result.output

    def test_transcribe_single_file(self, runner, tmp_path):
        audio = tmp_path / "test.mp3"
        audio.touch()
        with patch("casts_down.cli._run_transcription") as mock_run:
            result = runner.invoke(main, ["transcribe", str(audio)])
        assert result.exit_code == 0
        mock_run.assert_called_once()
        assert "Task Timing" in result.output
        assert "Transcription:" in result.output
        assert "Total:" in result.output

    def test_transcribe_no_files_exits_nonzero(self, runner):
        result = runner.invoke(main, ["transcribe"])
        assert result.exit_code != 0


class TestURLValidation:
    def test_rejects_file_scheme(self, runner):
        result = runner.invoke(main, ["file:///etc/passwd"])
        assert result.exit_code != 0
        assert "http" in result.output.lower() or "https" in result.output.lower()

    def test_rejects_no_scheme(self, runner):
        result = runner.invoke(main, ["/etc/passwd"])
        assert result.exit_code != 0

    def test_accepts_https(self, runner):
        with patch("casts_down.cli._download_podcast", return_value=[]):
            result = runner.invoke(main, ["--no-transcribe", "https://example.com/feed.rss"])
        assert result.exit_code == 0

    def test_accepts_http(self, runner):
        with patch("casts_down.cli._download_podcast", return_value=[]):
            result = runner.invoke(main, ["--no-transcribe", "http://example.com/feed.rss"])
        assert result.exit_code == 0


class TestTaskTiming:
    @patch("casts_down.cli._download_podcast")
    def test_download_only_prints_timing_summary(self, mock_dl, runner):
        mock_dl.return_value = []
        result = runner.invoke(main, ["--no-transcribe", "https://example.com/feed.rss"])
        assert result.exit_code == 0
        assert "Task Timing" in result.output
        assert "Download:" in result.output
        assert "Total:" in result.output

    @patch("casts_down.cli.run_download_transcribe_pipeline")
    def test_download_and_transcribe_prints_pipeline_progress(self, mock_pipeline, runner):
        item = PipelineItem(
            1,
            "https://example.com/feed.rss",
            "episode",
            download_status="succeeded",
            transcribe_status="succeeded",
        )
        mock_pipeline.return_value = PipelineResult(items=[item], elapsed=0.01)

        result = runner.invoke(main, ["https://example.com/feed.rss"])
        assert result.exit_code == 0
        assert "=== Overall Progress ===" in result.output
        assert "=== Task Progress ===" in result.output
        assert "Task Timing" in result.output
        assert "Pipeline:" in result.output
        assert "Total:" in result.output

    @patch("casts_down.pipeline.transcribe_one")
    @patch("casts_down.cli.detect_engine")
    @patch("casts_down.cli._download_podcast")
    def test_download_pipeline_partial_episode_failure_exits_nonzero(
        self, mock_download, mock_detect_engine, mock_transcribe_one, runner, tmp_path
    ):
        good = tmp_path / "good.mp3"

        async def fake_download(**kwargs):
            good.touch()
            kwargs["on_file_done"](good, {"title": "good"}, "downloaded good")
            kwargs["on_file_failed"](tmp_path / "bad.mp3", {"title": "bad"}, "HTTP 403")
            return [good]

        mock_download.side_effect = fake_download
        mock_detect_engine.return_value = object()
        mock_transcribe_one.return_value = {
            "status": "succeeded",
            "outputs": [good.with_suffix(".txt")],
            "error": None,
            "duration": 0.01,
        }

        result = runner.invoke(main, ["https://example.com/feed.rss", "--latest", "2"])

        assert result.exit_code == 1
        assert "RED" in result.output
        assert "bad" in result.output
        assert "HTTP 403" in result.output
        mock_transcribe_one.assert_called_once()


class TestMultipleDownloadURLs:
    @patch("casts_down.cli._download_podcast")
    def test_multiple_urls_download_with_shared_options(self, mock_dl, runner):
        mock_dl.return_value = []

        result = runner.invoke(main, [
            "https://example.com/feed-a.rss",
            "https://example.com/feed-b.rss",
            "--latest", "50",
            "--no-transcribe",
        ])

        assert result.exit_code == 0
        assert mock_dl.call_count == 2
        assert [call.kwargs["url"] for call in mock_dl.call_args_list] == [
            "https://example.com/feed-a.rss",
            "https://example.com/feed-b.rss",
        ]
        assert all(call.kwargs["latest"] == 50 for call in mock_dl.call_args_list)

    @patch("casts_down.cli._download_podcast")
    def test_options_can_be_between_multiple_urls(self, mock_dl, runner):
        mock_dl.return_value = []

        result = runner.invoke(main, [
            "https://example.com/feed-a.rss",
            "--latest", "2",
            "https://example.com/feed-b.rss",
            "--no-transcribe",
        ])

        assert result.exit_code == 0
        assert mock_dl.call_count == 2
        assert all(call.kwargs["latest"] == 2 for call in mock_dl.call_args_list)

    @patch("casts_down.cli.run_download_transcribe_pipeline")
    def test_multiple_urls_transcribe_through_pipeline(self, mock_pipeline, runner):
        mock_pipeline.return_value = PipelineResult(
            items=[
                PipelineItem(1, "https://example.com/feed-a.rss", "a", transcribe_status="succeeded"),
                PipelineItem(2, "https://example.com/feed-b.rss", "b", transcribe_status="succeeded"),
            ],
            elapsed=0.01,
        )

        result = runner.invoke(main, [
            "https://example.com/feed-a.rss",
            "https://example.com/feed-b.rss",
            "--model", "medium",
        ])

        assert result.exit_code == 0
        mock_pipeline.assert_called_once()
        assert mock_pipeline.call_args.kwargs["urls"] == [
            "https://example.com/feed-a.rss",
            "https://example.com/feed-b.rss",
        ]
        assert mock_pipeline.call_args.kwargs["model"] == "medium"

    @patch("casts_down.cli.run_download_transcribe_pipeline")
    @patch("casts_down.cli._download_podcast")
    def test_no_transcribe_multiple_urls_continue_after_one_failure_and_exit_nonzero(
        self, mock_dl, mock_pipeline, runner, tmp_path
    ):
        audio = tmp_path / "ok.mp3"
        audio.touch()

        async def fake_download(**kwargs):
            if "bad" in kwargs["url"]:
                raise RuntimeError("feed failed")
            return [audio]

        mock_dl.side_effect = fake_download

        result = runner.invoke(main, [
            "https://example.com/bad.rss",
            "https://example.com/good.rss",
            "--no-transcribe",
        ])

        assert result.exit_code == 1
        assert mock_dl.call_count == 2
        mock_pipeline.assert_not_called()
        assert "Download Failures" in result.output
        assert "feed failed" in result.output

    @patch("casts_down.cli.run_download_transcribe_pipeline")
    def test_pipeline_failure_exits_nonzero(self, mock_pipeline, runner):
        item = PipelineItem(
            1,
            "https://example.com/feed.rss",
            "episode",
            download_status="succeeded",
            transcribe_status="failed",
            error="boom",
        )
        mock_pipeline.return_value = PipelineResult(items=[item], elapsed=0.01)

        result = runner.invoke(main, ["https://example.com/feed.rss"])

        assert result.exit_code == 1
        assert "RED" in result.output
        assert "boom" in result.output


class TestOptionValidation:
    @patch("casts_down.cli._download_podcast")
    def test_all_and_latest_are_mutually_exclusive(self, mock_dl, runner):
        result = runner.invoke(main, [
            "--all", "--latest", "2",
            "https://example.com/feed.rss",
        ])
        assert result.exit_code != 0
        assert "cannot be used with" in result.output
        mock_dl.assert_not_called()

    @patch("casts_down.cli._download_podcast")
    def test_model_rejected_when_transcription_disabled(self, mock_dl, runner):
        result = runner.invoke(main, [
            "--no-transcribe", "--model", "medium",
            "https://example.com/feed.rss",
        ])
        assert result.exit_code != 0
        assert "--model" in result.output
        assert "--no-transcribe" in result.output
        mock_dl.assert_not_called()

    def test_concurrent_zero_rejected(self, runner):
        result = runner.invoke(main, ["--concurrent", "0", "https://example.com/feed.rss"])
        assert result.exit_code != 0

    def test_concurrent_negative_rejected(self, runner):
        result = runner.invoke(main, ["-c", "-1", "https://example.com/feed.rss"])
        assert result.exit_code != 0

    def test_latest_zero_rejected(self, runner):
        result = runner.invoke(main, ["--latest", "0", "https://example.com/feed.rss"])
        assert result.exit_code != 0

    def test_latest_negative_rejected(self, runner):
        result = runner.invoke(main, ["-l", "-1", "https://example.com/feed.rss"])
        assert result.exit_code != 0


class TestReadmeDocs:
    def test_readme_documents_pipeline_concurrency(self):
        text = open("README.md", encoding="utf-8").read()

        assert "Max active pipeline tasks" in text
        assert "shared by downloads and transcription" in text
        assert '--latest 50 --concurrent 3' in text


class TestCheckSystemDeps:
    """Unit tests for check_system_deps()."""

    def test_no_warning_when_ffmpeg_present(self, runner, capsys):
        with patch("casts_down.cli.shutil.which", return_value="/usr/local/bin/ffmpeg"):
            check_system_deps()
        captured = capsys.readouterr()
        assert "ffmpeg" not in captured.out

    def test_warning_when_ffmpeg_missing_macos(self, runner, capsys):
        with patch("casts_down.cli.shutil.which", return_value=None), \
             patch("casts_down.cli.platform.system", return_value="Darwin"):
            check_system_deps()
        captured = capsys.readouterr()
        assert "ffmpeg" in captured.out
        assert "brew install ffmpeg" in captured.out

    def test_warning_when_ffmpeg_missing_linux_apt(self, capsys):
        def fake_which(name):
            if name == "ffmpeg":
                return None
            if name == "apt":
                return "/usr/bin/apt"
            return None
        with patch("casts_down.cli.shutil.which", side_effect=fake_which), \
             patch("casts_down.cli.platform.system", return_value="Linux"):
            check_system_deps()
        captured = capsys.readouterr()
        assert "sudo apt install ffmpeg" in captured.out

    def test_warning_when_ffmpeg_missing_linux_dnf(self, capsys):
        def fake_which(name):
            if name == "ffmpeg":
                return None
            if name == "apt":
                return None
            if name == "dnf":
                return "/usr/bin/dnf"
            return None
        with patch("casts_down.cli.shutil.which", side_effect=fake_which), \
             patch("casts_down.cli.platform.system", return_value="Linux"):
            check_system_deps()
        captured = capsys.readouterr()
        assert "sudo dnf install ffmpeg" in captured.out

    def test_warning_shown_in_cli_output(self, runner):
        with patch("casts_down.cli.shutil.which", return_value=None), \
             patch("casts_down.cli.platform.system", return_value="Darwin"), \
             patch("casts_down.cli._download_podcast", return_value=[]):
            result = runner.invoke(main, ["--no-transcribe", "https://example.com/feed.rss"])
        assert "ffmpeg" in result.output
        assert "brew install ffmpeg" in result.output


class TestSetupTranscribe:
    def test_setup_help(self, runner):
        result = runner.invoke(main, ["setup-transcribe", "--help"])
        assert result.exit_code == 0

    def test_setup_short_help(self, runner):
        result = runner.invoke(main, ["setup-transcribe", "-h"])
        assert result.exit_code == 0
        assert "--backend" in result.output

    def test_setup_runs_without_error(self, runner):
        with patch("casts_down.transcribe.installer.run_setup") as mock_setup:
            result = runner.invoke(main, ["setup-transcribe"])
        assert result.exit_code == 0
        mock_setup.assert_called_once_with(backend="auto")

    def test_backend_option_passed_through(self, runner):
        with patch("casts_down.transcribe.installer.run_setup") as mock_setup:
            result = runner.invoke(main, ["setup-transcribe", "--backend", "faster-whisper"])
        mock_setup.assert_called_once_with(backend="faster-whisper")
