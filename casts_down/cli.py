"""
Casts Down - Unified podcast download CLI.

Provides a click.group with backward-compatible default invocation
and subcommands for transcription.
"""

import asyncio
import platform
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import aiohttp
import click

from casts_down import __version__
from casts_down.downloaders.base import PodcastDownloader
from casts_down.downloaders.podcast import ApplePodcastsParser, RSSParser
from casts_down.downloaders.xiaoyuzhou import XiaoyuzhouDownloader
from casts_down.pipeline import DownloadJob, PipelineItem, PipelineResult, run_download_jobs_pipeline
from casts_down.progress import PipelineTaskView, ProgressTotals, render_overall_progress, render_task_progress
from casts_down.timing import TaskTimer, format_duration
from casts_down.transcribe import detect_engine


HELP_CONTEXT = {"help_option_names": ["-h", "--help"]}

_MAIN_VALUE_OPTIONS = {
    "--latest", "-l",
    "--output", "-o",
    "--concurrent", "-c",
    "--model", "-m",
}
_MAIN_FLAG_OPTIONS = {
    "--all", "-a",
    "--skip-existing", "-s",
    "--transcribe", "-t",
    "--no-transcribe",
    "--version",
    "--help", "-h",
}


def _consume_main_option(args: list[str], index: int) -> tuple[list[str], int] | None:
    """Return the main-command option tokens starting at index, if recognized."""
    token = args[index]
    option_name = token.split("=", 1)[0] if token.startswith("--") else token

    if option_name in _MAIN_VALUE_OPTIONS:
        if "=" in token:
            return [token], index + 1
        if index + 1 < len(args):
            return args[index:index + 2], index + 2
        return [token], index + 1

    if token in _MAIN_FLAG_OPTIONS:
        return [token], index + 1

    return None


def _first_non_option_index(args: list[str]) -> int | None:
    index = 0
    while index < len(args):
        consumed = _consume_main_option(args, index)
        if consumed is None:
            return index
        _, index = consumed
    return None


def _option_was_provided(ctx: click.Context, name: str) -> bool:
    return ctx.get_parameter_source(name) == click.core.ParameterSource.COMMANDLINE


def _print_task_timing(timer: TaskTimer) -> None:
    click.echo("\n=== Task Timing ===")
    for name, elapsed in timer.stages.items():
        click.echo(f"{name}: {format_duration(elapsed)}")
    click.echo(f"Total: {format_duration(timer.total_elapsed())}")


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

def check_system_deps() -> None:
    """Check for required system-level tools and warn if missing."""
    missing: list[tuple[str, str]] = []

    if not shutil.which("ffmpeg"):
        system = platform.system()
        if system == "Darwin":
            hint = "brew install ffmpeg"
        elif shutil.which("apt"):
            hint = "sudo apt install ffmpeg"
        elif shutil.which("dnf"):
            hint = "sudo dnf install ffmpeg"
        else:
            hint = "请参考 https://ffmpeg.org/download.html 安装"
        missing.append(("ffmpeg", hint))

    for tool, hint in missing:
        click.echo(click.style(
            f"[!] {tool} 未安装，转录功能将不可用。运行 {hint} 安装",
            fg="yellow",
        ))


# ---------------------------------------------------------------------------
# URL detection
# ---------------------------------------------------------------------------

def detect_downloader(url: str) -> str:
    """
    Detect which downloader to use based on URL.

    Returns: 'podcast' or 'xiaoyuzhou'
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    if 'xiaoyuzhoufm.com' in domain:
        return 'xiaoyuzhou'

    if 'podcasts.apple.com' in domain or url.endswith('.rss') or url.endswith('.xml'):
        return 'podcast'

    # Default to generic podcast downloader (supports RSS)
    return 'podcast'


# ---------------------------------------------------------------------------
# Download helpers (fully functional, adapted from the original CLIs)
# ---------------------------------------------------------------------------

async def _download_podcast(
    url: str,
    download_all: bool,
    latest: int,
    output: str,
    concurrent: int,
    skip_existing: bool,
    on_file_done: Callable[[Path, Any, str], None] | None = None,
    on_file_failed: Callable[[Path, Any, str], None] | None = None,
) -> list[Path]:
    """
    Full podcast download logic (RSS / Apple Podcasts).

    Adapted from podcast_dl.py main().
    Returns list of successfully downloaded file paths.
    """
    downloaded_files: list[Path] = []

    click.echo(f"[*] Parsing: {url}\n")

    # Determine URL type and extract episode info
    rss_url = url
    episode_title = None
    is_single_episode = False

    if 'podcasts.apple.com' in url:
        click.echo("[*] Detected Apple Podcasts URL, extracting info...")

        # Check if this is a single-episode link
        episode_id = ApplePodcastsParser.extract_episode_id(url)
        if episode_id:
            is_single_episode = True
            click.echo(f"[*] Detected episode link")

        # Fetch RSS URL and title
        async with aiohttp.ClientSession() as session:
            rss_url, episode_title = await ApplePodcastsParser.extract_metadata_async(session, url)

        if not rss_url:
            click.echo("[!] Failed to extract RSS URL from Apple Podcasts", err=True)
            sys.exit(1)

        if episode_title:
            click.echo(f"[*] Episode title: {episode_title}")

        click.echo(f"[+] RSS URL: {rss_url}\n")

    # Parse RSS
    podcast_name, episodes = RSSParser.parse(rss_url, episode_title=episode_title)

    if not episodes:
        click.echo("[!] No episodes found", err=True)
        sys.exit(1)

    # Single-episode link with a match
    if is_single_episode and len(episodes) == 1:
        click.echo(f"[*] Podcast: {podcast_name}")
        click.echo(f"[+] Found matching episode: {episodes[0].title}\n")
        selected_episodes = episodes
    else:
        # Normal podcast-link logic
        if is_single_episode:
            click.echo(f"[!] Could not match episode ID, will download latest episode\n")

        click.echo(f"[*] Podcast: {podcast_name}")
        click.echo(f"[*] Total episodes: {len(episodes)}\n")

        # Select episodes
        if download_all:
            selected_episodes = episodes
        else:
            selected_episodes = episodes[:latest]

    click.echo(f"[*] Preparing to download {len(selected_episodes)} episode(s)\n")

    # Download
    output_dir = Path(output)
    downloader = PodcastDownloader(concurrent=concurrent)

    downloaded_files = await downloader.download_all(
        selected_episodes,
        podcast_name,
        output_dir,
        skip_existing,
        on_file_done=on_file_done,
        on_file_failed=on_file_failed,
    )

    return downloaded_files


async def _download_xiaoyuzhou(
    url: str,
    output: str,
    concurrent: int,
    skip_existing: bool,
    latest: int | None,
    on_file_done: Callable[[Path, Any, str], None] | None = None,
    on_file_failed: Callable[[Path, Any, str], None] | None = None,
) -> list[Path]:
    """
    Full Xiaoyuzhou download logic.

    Adapted from xiaoyuzhou_dl.py main().
    Returns list of successfully downloaded file paths.
    """
    downloaded_files: list[Path] = []

    downloader = XiaoyuzhouDownloader(concurrent=concurrent)
    output_dir = Path(output)

    # Determine link type
    if '/episode/' in url:
        downloaded_files = await downloader.download_episode_by_url(
            url,
            output_dir,
            skip_existing,
            on_file_done=on_file_done,
            on_file_failed=on_file_failed,
        )
    elif '/podcast/' in url:
        downloaded_files = await downloader.download_podcast(
            url,
            output_dir,
            skip_existing,
            latest,
            on_file_done=on_file_done,
            on_file_failed=on_file_failed,
        )
    else:
        click.echo("[!] Unrecognized URL format", err=True)
        click.echo("Supported formats:", err=True)
        click.echo("  - https://www.xiaoyuzhoufm.com/episode/{eid}", err=True)
        click.echo("  - https://www.xiaoyuzhoufm.com/podcast/{pid}", err=True)
        sys.exit(1)

    return downloaded_files


# ---------------------------------------------------------------------------
# Pipeline and transcription helpers
# ---------------------------------------------------------------------------

def _item_status(item: PipelineItem) -> str:
    if item.download_status == "failed" or item.transcribe_status == "failed":
        return "failed"
    if item.transcribe_status in {"succeeded", "skipped", "backfilled"}:
        return item.transcribe_status
    if item.download_status == "running" or item.transcribe_status == "running":
        return "running"
    if item.transcribe_status == "queued":
        return "queued"
    return "pending"


def _format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(size)
    unit = units[0]
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            break
        amount /= 1024
    if unit == "B":
        return f"{int(amount)} {unit}"
    return f"{amount:.1f} {unit}"


def _pipeline_task_views(items: list[PipelineItem]) -> list[PipelineTaskView]:
    rows = []
    for item in items:
        file_name = item.audio_path.name if item.audio_path else item.title
        size_label = "-"
        if item.audio_path and item.audio_path.exists():
            size_label = _format_size(item.audio_path.stat().st_size)
        rows.append(
            PipelineTaskView(
                index=item.index,
                file_name=file_name,
                download_status=item.download_status,
                transcribe_status=item.transcribe_status,
                status=_item_status(item),
                size_label=size_label,
                error=item.error or "-",
                audio_path=item.audio_path,
                output_paths=item.outputs,
            )
        )
    return rows


def _pipeline_totals(items: list[PipelineItem], elapsed: float, concurrent: int) -> ProgressTotals:
    total = len(items)
    failed = sum(1 for item in items if _item_status(item) == "failed")
    running = sum(1 for item in items if _item_status(item) == "running")
    queued = sum(1 for item in items if _item_status(item) in {"pending", "queued"})
    done = total - failed - running - queued
    known_budget = min(concurrent, max(1, total or concurrent))
    return ProgressTotals(
        total=total,
        done=done,
        running=running,
        queued=queued,
        failed=failed,
        download_ok=sum(1 for item in items if item.download_status == "succeeded"),
        download_failed=sum(1 for item in items if item.download_status == "failed"),
        download_active=sum(1 for item in items if item.download_status == "running"),
        transcribe_ok=sum(
            1
            for item in items
            if item.transcribe_status in {"succeeded", "skipped", "backfilled"}
        ),
        transcribe_failed=sum(1 for item in items if item.transcribe_status == "failed"),
        transcribe_active=sum(1 for item in items if item.transcribe_status == "running"),
        transcribe_queued=sum(1 for item in items if item.transcribe_status == "queued"),
        bytes_done=sum(
            item.audio_path.stat().st_size
            for item in items
            if item.audio_path and item.audio_path.exists()
        ),
        bytes_total=0,
        elapsed=format_duration(elapsed),
        active_budget=f"{known_budget}/{concurrent}",
    )


def _stdout_is_tty() -> bool:
    stream = click.get_text_stream("stdout")
    return bool(getattr(stream, "isatty", lambda: False)())


def _print_pipeline_progress(items: list[PipelineItem], elapsed: float, concurrent: int) -> None:
    click.echo(render_overall_progress(_pipeline_totals(items, elapsed, concurrent), tty=_stdout_is_tty()))
    click.echo(render_task_progress(_pipeline_task_views(items), tty=_stdout_is_tty()))


def _print_pipeline_result(result: PipelineResult, concurrent: int) -> None:
    click.echo(render_overall_progress(_pipeline_totals(result.items, result.elapsed, concurrent), tty=_stdout_is_tty()))
    click.echo(render_task_progress(_pipeline_task_views(result.items), tty=_stdout_is_tty()))


def run_download_transcribe_pipeline(
    *,
    urls: list[str],
    download_all: bool,
    latest: int,
    output: str,
    concurrent: int,
    skip_existing: bool,
    model: str,
) -> PipelineResult:
    return asyncio.run(
        _run_download_transcribe_pipeline_async(
            urls=urls,
            download_all=download_all,
            latest=latest,
            output=output,
            concurrent=concurrent,
            skip_existing=skip_existing,
            model=model,
        )
    )


async def _run_download_transcribe_pipeline_async(
    *,
    urls: list[str],
    download_all: bool,
    latest: int,
    output: str,
    concurrent: int,
    skip_existing: bool,
    model: str,
) -> PipelineResult:
    jobs: list[DownloadJob] = []

    for index, current_url in enumerate(urls, start=1):
        parsed_url = urlparse(current_url)
        if parsed_url.scheme not in ('http', 'https'):
            raise ValueError("only http:// and https:// URLs are supported")

        downloader_type = detect_downloader(current_url)

        async def download_job(
            download_concurrent: int,
            on_file_done: Callable[[Path, Any, str], None],
            on_file_failed: Callable[[Path | None, Any, str], None],
            *,
            link_index: int = index,
            source_url: str = current_url,
            source_downloader_type: str = downloader_type,
        ) -> None:
            if len(urls) > 1:
                click.echo(f"\n[*] Processing link {link_index}/{len(urls)}: {source_url}")

            click.echo(f"[*] Detected: ", nl=False)

            if source_downloader_type == 'xiaoyuzhou':
                click.echo("Xiaoyuzhou Podcast\n")
                await _download_xiaoyuzhou(
                    url=source_url,
                    output=output,
                    concurrent=download_concurrent,
                    skip_existing=skip_existing,
                    latest=latest if not download_all else None,
                    on_file_done=on_file_done,
                    on_file_failed=on_file_failed,
                )
            else:
                if 'podcasts.apple.com' in source_url:
                    click.echo("Apple Podcasts\n")
                elif source_url.endswith(('.rss', '.xml')):
                    click.echo("RSS Feed\n")
                else:
                    click.echo("Podcast RSS Feed\n")

                await _download_podcast(
                    url=source_url,
                    download_all=download_all,
                    latest=latest,
                    output=output,
                    concurrent=download_concurrent,
                    skip_existing=skip_existing,
                    on_file_done=on_file_done,
                    on_file_failed=on_file_failed,
                )

        jobs.append(
            DownloadJob(
                source_url=current_url,
                download=download_job,
                selected_count=None if download_all else latest,
            )
        )

    return await run_download_jobs_pipeline(
        jobs,
        engine_factory=lambda: detect_engine(model),
        user_concurrent=concurrent,
        progress_callback=lambda items, elapsed: _print_pipeline_progress(items, elapsed, concurrent),
    )

def _run_transcription(files: list[Path], model: str, language: str | None = None,
                       skip_transcribed: bool = True, overwrite: bool = False) -> None:
    """Run transcription on a list of audio files."""
    try:
        from casts_down.transcribe import transcribe_batch, print_report, collect_audio_files

        # Expand directories to audio files
        expanded: list[Path] = []
        for f in files:
            if f.is_dir():
                expanded.extend(collect_audio_files(f))
            else:
                expanded.append(f)

        if not expanded:
            click.echo("[!] No audio files found")
            return

        click.echo(f"\n[*] Transcribing {len(expanded)} file(s) with model '{model}'\n")
        results = transcribe_batch(
            expanded, model=model, language=language,
            skip_transcribed=skip_transcribed, overwrite=overwrite,
        )
        print_report(results)
    except RuntimeError as e:
        click.echo(f"\n[!] {e}", err=True)
        click.echo("\n    To install transcription support, run:\n", err=True)
        click.echo("      casts-down setup-transcribe\n", err=True)
        click.echo("    Or manually:", err=True)
        click.echo('      pip install "faster-whisper>=1.0.0,<2.0.0"', err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n[!] Transcription interrupted by user")
        sys.exit(130)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

class _CastsDownGroup(click.Group):
    """Custom group that allows optional URL arguments alongside subcommands.

    Click normally consumes the first positional token as a URL argument,
    even when it matches a subcommand name.  This override peeks at the
    first non-option token and, if it is a registered subcommand, removes
    the URL arguments from the params so Click can route to the subcommand.
    """

    def parse_args(self, ctx, args):
        args = self._normalize_download_args(list(args))

        # Check if first non-option arg looks like a subcommand
        first_non_option = _first_non_option_index(args)
        if first_non_option is not None and args[first_non_option] in self.commands:
            # Temporarily remove the 'urls' argument so Click routes to subcommand
            saved_params = self.params
            self.params = [p for p in self.params if p.name != 'urls']
            try:
                result = super().parse_args(ctx, args)
                # Ensure 'urls' has a default value in ctx.params so the group
                # callback can be called without a TypeError on the 'urls' arg.
                ctx.params.setdefault('urls', ())
                return result
            finally:
                self.params = saved_params
        return super().parse_args(ctx, args)

    def _normalize_download_args(self, args: list[str]) -> list[str]:
        """Allow download options before, after, or between URL arguments."""
        first_non_option = _first_non_option_index(args)
        if first_non_option is None or args[first_non_option] in self.commands:
            return args

        option_tokens: list[str] = []
        positional_tokens: list[str] = []
        index = 0
        while index < len(args):
            consumed = _consume_main_option(args, index)
            if consumed is None:
                positional_tokens.append(args[index])
                index += 1
                continue
            tokens, index = consumed
            option_tokens.extend(tokens)

        return option_tokens + positional_tokens


@click.group(
    name="casts-down",
    cls=_CastsDownGroup,
    invoke_without_command=True,
    context_settings=HELP_CONTEXT,
    subcommand_metavar="[COMMAND] [ARGS]...",
)
@click.argument('urls', nargs=-1, metavar='[URL]...')
@click.option('--all', '-a', 'download_all', is_flag=True, help='Download all episodes (cannot be combined with --latest)')
@click.option('--latest', '-l', type=click.IntRange(min=1), default=1, help='Download latest N episodes (default: 1)')
@click.option('--output', '-o', type=click.Path(), default='./podcasts', help='Output directory')
@click.option(
    '--concurrent',
    '-c',
    type=click.IntRange(min=1, max=20),
    default=3,
    help=(
        'Max active pipeline tasks. With transcription enabled, this budget is shared by '
        'downloads and transcription. With --no-transcribe, it controls parallel downloads. '
        'Capped by selected episode count. Default: 3.'
    ),
)
@click.option('--skip-existing', '-s', is_flag=True, help='Skip existing files')
@click.option('--transcribe/--no-transcribe', '-t/', default=True, help='Transcribe after downloading (default: on)')
@click.option('--model', '-m', type=str, default='small', help='Whisper model for transcription (default: small; requires transcription)')
@click.option('--version', is_flag=True, help='Show version')
@click.pass_context
def main(ctx, urls, download_all, latest, output, concurrent, skip_existing, transcribe, model, version):
    """
    Casts Down - Intelligent Podcast Downloader

    Automatically detects each URL type and uses the appropriate downloader.

    \b
    Supported platforms:
      - Apple Podcasts (podcasts.apple.com)
      - Xiaoyuzhou (xiaoyuzhoufm.com)
      - Generic RSS feeds

    \b
    Examples:
      # Download latest episode from Apple Podcasts
      casts-down "https://podcasts.apple.com/podcast/id123?i=456"

    \b
      # Download latest 3 episodes
      casts-down "https://podcasts.apple.com/podcast/id123" --latest 3

    \b
      # Download latest 3 episodes from multiple feeds
      casts-down "https://feeds.example.com/a.rss" "https://feeds.example.com/b.rss" --latest 3

    \b
      # Download from Xiaoyuzhou
      casts-down "https://www.xiaoyuzhoufm.com/episode/xxx"

    \b
      # Download and transcribe
      casts-down "https://feeds.example.com/podcast.rss" --transcribe

    \b
    Rules:
      - Multiple URLs are allowed; options apply to every URL
      - Download options may appear before or after the URL
      - Use either --all or --latest, not both
      - --model is only valid when transcription is enabled

    \b
    Subcommands:
      transcribe        Transcribe local audio files
      setup-transcribe  Install transcription dependencies
    """
    if version:
        click.echo(f"casts-down {__version__}")
        return

    # If a subcommand was invoked, skip the default download behavior
    if ctx.invoked_subcommand is not None:
        return

    explicit_latest = _option_was_provided(ctx, "latest")
    explicit_model = _option_was_provided(ctx, "model")

    if download_all and explicit_latest:
        raise click.UsageError("--all cannot be used with --latest. Choose one episode selection option.")

    if not transcribe and explicit_model:
        raise click.UsageError("--model is ignored with --no-transcribe. Remove --model or enable transcription.")

    # No URL and no subcommand => show help
    urls = list(urls)

    if not urls:
        explicit_download_options = [
            "download_all", "latest", "output", "concurrent",
            "skip_existing", "transcribe", "model",
        ]
        if any(_option_was_provided(ctx, name) for name in explicit_download_options):
            raise click.UsageError("Missing URL. Run 'casts-down -h' for usage.")
        click.echo(ctx.get_help())
        return

    task_timer = TaskTimer()

    try:
        banner = f"\nCasts Down - Intelligent Podcast Downloader v{__version__}\n"
        click.echo(banner)

        check_system_deps()

        disclaimer = (
            "DISCLAIMER: For educational purposes only. Respect copyrights.\n"
        )
        click.echo(disclaimer)

        async def _run_downloads():
            downloaded: list[Path] = []
            failures: list[tuple[str, str]] = []

            for index, current_url in enumerate(urls, start=1):
                if len(urls) > 1:
                    click.echo(f"\n[*] Processing link {index}/{len(urls)}: {current_url}")

                try:
                    parsed_url = urlparse(current_url)
                    if parsed_url.scheme not in ('http', 'https'):
                        raise ValueError("only http:// and https:// URLs are supported")

                    downloader_type = detect_downloader(current_url)

                    click.echo(f"[*] Detected: ", nl=False)

                    if downloader_type == 'xiaoyuzhou':
                        click.echo("Xiaoyuzhou Podcast\n")
                        files = await _download_xiaoyuzhou(
                            url=current_url,
                            output=output,
                            concurrent=concurrent,
                            skip_existing=skip_existing,
                            latest=latest if not download_all else None,
                        )
                    else:  # podcast
                        if 'podcasts.apple.com' in current_url:
                            click.echo("Apple Podcasts\n")
                        elif current_url.endswith(('.rss', '.xml')):
                            click.echo("RSS Feed\n")
                        else:
                            click.echo("Podcast RSS Feed\n")

                        files = await _download_podcast(
                            url=current_url,
                            download_all=download_all,
                            latest=latest,
                            output=output,
                            concurrent=concurrent,
                            skip_existing=skip_existing,
                        )
                    downloaded.extend(files)
                except SystemExit as e:
                    code = e.code if isinstance(e.code, int) else 1
                    failures.append((current_url, f"exited with status {code}"))
                    if len(urls) == 1:
                        raise
                    click.echo(f"[!] Failed: {current_url} (exit {code})", err=True)
                except Exception as e:
                    failures.append((current_url, f"{type(e).__name__}: {e}"))
                    click.echo(f"[!] Failed: {current_url} - {type(e).__name__}: {e}", err=True)

            return downloaded, failures

        if transcribe:
            pipeline_started = time.monotonic()
            pipeline_result = run_download_transcribe_pipeline(
                urls=urls,
                download_all=download_all,
                latest=latest,
                output=output,
                concurrent=concurrent,
                skip_existing=skip_existing,
                model=model,
            )
            task_timer.record("Pipeline", time.monotonic() - pipeline_started)
            _print_pipeline_result(pipeline_result, concurrent)
            _print_task_timing(task_timer)
            if pipeline_result.failed_count:
                sys.exit(1)
        else:
            download_started = time.monotonic()
            downloaded_files, download_failures = asyncio.run(_run_downloads())
            task_timer.record("Download", time.monotonic() - download_started)

            _print_task_timing(task_timer)

            if download_failures:
                click.echo("\n=== Download Failures ===", err=True)
                for failed_url, reason in download_failures:
                    click.echo(f"[-] {failed_url} -> {reason}", err=True)
                sys.exit(1)

    except ValueError as e:
        click.echo(f"[!] Error: {str(e)}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n\n[!] Download interrupted by user", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"[!] Unexpected error: {str(e)}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

@main.command(context_settings=HELP_CONTEXT)
@click.argument('files', nargs=-1, type=click.Path(exists=True))
@click.option('--model', '-m', type=str, default='small', help='Whisper model (default: small)')
@click.option('--language', type=str, default=None, help='Language code (zh, en, etc.)')
@click.option('--skip-transcribed', is_flag=True, default=True, help='Skip already transcribed files')
@click.option('--overwrite', is_flag=True, help='Force re-transcribe existing outputs')
def transcribe(files, model, language, skip_transcribed, overwrite):
    """Transcribe local audio files.

    \b
    Examples:
      casts-down transcribe recording.mp3
      casts-down transcribe *.mp3 --model medium
      casts-down transcribe ./podcasts/ --language zh
    """
    if not files:
        click.echo("[!] No files specified. Usage: casts-down transcribe <file> [file ...]", err=True)
        sys.exit(1)

    file_paths = [Path(f) for f in files]
    task_timer = TaskTimer()
    transcription_started = time.monotonic()
    _run_transcription(file_paths, model, language=language,
                       skip_transcribed=not overwrite and skip_transcribed,
                       overwrite=overwrite)
    task_timer.record("Transcription", time.monotonic() - transcription_started)
    _print_task_timing(task_timer)


@main.command('setup-transcribe', context_settings=HELP_CONTEXT)
@click.option('--backend', type=click.Choice(['auto', 'faster-whisper', 'mlx-whisper']),
              default='auto', help='Transcription backend (default: auto-detect)')
def setup_transcribe(backend):
    """Install transcription dependencies.

    \b
    Detects your platform and installs the best transcription backend:
      - macOS Apple Silicon: mlx-whisper (Metal GPU acceleration)
      - Other platforms: faster-whisper (CPU/CUDA)

    \b
    Examples:
      casts-down setup-transcribe
      casts-down setup-transcribe --backend faster-whisper
    """
    from casts_down.transcribe.installer import run_setup
    run_setup(backend=backend)
