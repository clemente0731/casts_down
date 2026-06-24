"""Transcription support for casts_down."""
import platform
import time
from pathlib import Path
import click
from casts_down.transcribe.engine import TranscribeEngine
from casts_down.transcribe.formatter import write_outputs
from casts_down.transcribe.word_stats import write_word_stats_from_txt, word_stats_path

def detect_engine(model: str = "small"):
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            import mlx_whisper  # noqa: F401
            from casts_down.transcribe.mlx_whisper_engine import MLXWhisperEngine
            return MLXWhisperEngine(model=model)
        except ImportError:
            click.echo("[*] mlx-whisper not available, falling back to faster-whisper")
    try:
        import faster_whisper  # noqa: F401
        from casts_down.transcribe.faster_whisper_engine import FasterWhisperEngine
        return FasterWhisperEngine(model=model)
    except ImportError:
        pass
    raise RuntimeError("No transcription engine found. Run: casts-down setup-transcribe")


AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".wma", ".aac", ".opus"}


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def collect_audio_files(directory: Path) -> list[Path]:
    return sorted(f for f in directory.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS)


def _is_transcribed(audio_path: Path) -> bool:
    return (
        audio_path.with_suffix(".srt").exists()
        and audio_path.with_suffix(".txt").exists()
        and word_stats_path(audio_path).exists()
    )


def _has_transcript(audio_path: Path) -> bool:
    return audio_path.with_suffix(".srt").exists() and audio_path.with_suffix(".txt").exists()


def transcribe_batch(
    files: list[Path],
    engine: TranscribeEngine | None = None,
    model: str = "small",
    language: str | None = None,
    skip_transcribed: bool = True,
    overwrite: bool = False,
) -> list[dict]:
    if engine is None:
        engine = detect_engine(model=model)
    results = []
    batch_start_time = time.monotonic()

    def _print_progress() -> None:
        completed = len(results)
        total = len(files)
        if total == 0 or completed == 0:
            return
        elapsed = time.monotonic() - batch_start_time
        eta = elapsed / completed * (total - completed)
        click.echo(
            f"[*] Transcription Progress: {completed}/{total} files | "
            f"elapsed {_format_duration(elapsed)} | ETA {_format_duration(eta)}"
        )

    for audio_path in files:
        if not overwrite and skip_transcribed and _has_transcript(audio_path):
            start_time = time.monotonic()
            try:
                if not word_stats_path(audio_path).exists():
                    write_word_stats_from_txt(audio_path)
                    click.echo(f"[*] Backfilled .words.json for {audio_path.name}")
                results.append({"file": audio_path, "success": True, "skipped": True, "duration": 0, "error": None})
                click.echo(f"[~] Skipped (already transcribed): {audio_path.name}")
            except Exception as e:
                elapsed = time.monotonic() - start_time
                results.append({"file": audio_path, "success": False, "skipped": False, "duration": elapsed, "error": f"{type(e).__name__}: {e}"})
                click.echo(f"[-] {audio_path.name} -> FAILED: {type(e).__name__}")
            _print_progress()
            continue
        start_time = time.monotonic()
        try:
            segments = engine.transcribe(audio_path, language=language)
            click.echo(f"[*] Writing .srt + .txt + .words.json for {audio_path.name} ...")
            write_outputs(audio_path, segments)
            elapsed = time.monotonic() - start_time
            srt_path = audio_path.with_suffix(".srt").resolve()
            txt_path = audio_path.with_suffix(".txt").resolve()
            words_path = word_stats_path(audio_path).resolve()
            results.append({"file": audio_path, "success": True, "skipped": False, "duration": elapsed, "error": None})
            click.echo(f"[+] {audio_path.name} -> .srt + .txt + .words.json ({elapsed:.0f}s)")
            click.echo(f"    {srt_path}")
            click.echo(f"    {txt_path}")
            click.echo(f"    {words_path}")
            _print_progress()
        except KeyboardInterrupt:
            for suffix in (".srt.tmp", ".txt.tmp", ".words.json.tmp"):
                tmp = audio_path.with_suffix(suffix)
                if tmp.exists():
                    tmp.unlink()
            click.echo(f"\n[!] Interrupted during: {audio_path.name}")
            break
        except Exception as e:
            elapsed = time.monotonic() - start_time
            results.append({"file": audio_path, "success": False, "skipped": False, "duration": elapsed, "error": f"{type(e).__name__}: {e}"})
            click.echo(f"[-] {audio_path.name} -> FAILED: {type(e).__name__}")
            _print_progress()
    return results


def print_report(results: list[dict]) -> None:
    if not results:
        click.echo("[*] No files to report.")
        return
    click.echo("\n=== Transcription Report ===")
    for r in results:
        audio_path = r["file"]
        name = audio_path.name
        if r["skipped"]:
            click.echo(f"[~] {name} -> skipped")
        elif r["success"]:
            mins = int(r["duration"] // 60)
            secs = int(r["duration"] % 60)
            srt_path = audio_path.with_suffix(".srt").resolve()
            txt_path = audio_path.with_suffix(".txt").resolve()
            words_path = word_stats_path(audio_path).resolve()
            click.echo(f"[+] {name} -> .srt + .txt + .words.json ({mins}m{secs:02d}s)")
            click.echo(f"    {srt_path}")
            click.echo(f"    {txt_path}")
            click.echo(f"    {words_path}")
        else:
            click.echo(f"[-] {name} -> FAILED: {r['error']}")
    succeeded = sum(1 for r in results if r["success"])
    total_time = sum(r["duration"] for r in results)
    total_mins = int(total_time // 60)
    total_secs = int(total_time % 60)
    click.echo(f"Summary: {succeeded}/{len(results)} succeeded, total time {total_mins}m{total_secs:02d}s")
