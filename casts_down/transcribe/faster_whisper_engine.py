"""faster-whisper transcription engine."""
import os
import platform
import site
import time
from pathlib import Path
import click
from casts_down.transcribe.engine import Segment, TranscribeEngine

_WINDOWS_CUDA_DLL_HANDLES = []


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def _prepare_windows_cuda_dll_paths() -> list[str]:
    """Add pip-installed NVIDIA runtime DLL directories to Windows search paths."""
    if platform.system().lower() != "windows":
        return []

    candidates = []
    for site_path in site.getsitepackages():
        base = Path(site_path) / "nvidia"
        candidates.extend([
            base / "cublas" / "bin",
            base / "cudnn" / "bin",
            base / "cuda_runtime" / "bin",
        ])

    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    normalized_path_parts = {p.lower() for p in path_parts if p}
    added: list[str] = []

    for candidate in candidates:
        if not candidate.exists():
            continue
        candidate_str = str(candidate)
        if candidate_str.lower() not in normalized_path_parts:
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + candidate_str
            normalized_path_parts.add(candidate_str.lower())
        if hasattr(os, "add_dll_directory"):
            try:
                _WINDOWS_CUDA_DLL_HANDLES.append(os.add_dll_directory(candidate_str))
            except OSError:
                pass
        added.append(candidate_str)

    if added:
        click.echo("[*] Windows CUDA DLL search paths prepared")
    return added


class FasterWhisperEngine(TranscribeEngine):
    def __init__(self, model: str = "small"):
        self._model_name = model
        self._model = None
        self._device = None
        self._compute_type = None

    def _load_model(self, device: str | None = None):
        """Load model with specified device."""
        if device == "cuda":
            _prepare_windows_cuda_dll_paths()

        from faster_whisper import WhisperModel

        t0 = time.monotonic()
        if device:
            self._model = WhisperModel(self._model_name, device=device)
            self._device = device
        else:
            self._model = WhisperModel(self._model_name)
            self._device = "auto"
        elapsed = time.monotonic() - t0
        click.echo(f"[*] Model '{self._model_name}' loaded on {self._device} ({elapsed:.1f}s)")

    def _ensure_model(self):
        """Lazy load model: try cuda -> fallback cpu."""
        if self._model is not None:
            return

        # Try CUDA first
        try:
            self._load_model("cuda")
            _ = self._model.model  # force CUDA lib check
            click.echo(f"[*] Transcription engine: faster-whisper (cuda)")
            return
        except Exception as e:
            click.echo(click.style(
                f"[!] CUDA device fallback: {type(e).__name__}: {e}",
                fg="yellow",
            ))
            click.echo(click.style("[!] Falling back to CPU device.", fg="yellow"))

        # Fallback to CPU
        self._load_model("cpu")
        click.echo(f"[*] Transcription engine: faster-whisper (cpu)")

    def transcribe(self, audio_path: Path, language: str | None = None) -> list[Segment]:
        self._ensure_model()

        file_size_mb = audio_path.stat().st_size / (1024 * 1024)
        click.echo(f"[*] Transcribing: {audio_path.name} ({file_size_mb:.1f} MB)")

        try:
            segments = self._do_transcribe(audio_path, language)
        except RuntimeError as e:
            if "libcublas" in str(e) or "CUDA" in str(e) or "cuda" in str(e):
                click.echo(click.style(f"[!] CUDA error: {e}", fg="yellow"))
                click.echo(click.style("[!] Hint: CUDA libraries may be missing or version incompatible.", fg="yellow"))
                click.echo(click.style("[!]   Check with: find /usr/local/ -name '*libcublas.so*'", fg="yellow"))
                click.echo(click.style("[!]   Fix with:   pip install nvidia-cublas-cu12 nvidia-cudnn-cu12", fg="yellow"))
                click.echo("[*] Falling back to CPU...")
                self._load_model("cpu")
                segments = self._do_transcribe(audio_path, language)
            else:
                raise

        return segments

    def _do_transcribe(self, audio_path: Path, language: str | None) -> list[Segment]:
        t0 = time.monotonic()
        segments_iter, info = self._model.transcribe(
            str(audio_path), language=language, word_timestamps=False,
        )

        audio_duration = info.duration
        audio_mins = int(audio_duration // 60)
        audio_secs = int(audio_duration % 60)
        click.echo(f"[*] Audio duration: {audio_mins}m{audio_secs:02d}s, lang={info.language} prob={info.language_probability:.2f}")

        # Iterate segments with live progress
        results = []
        last_progress_pct = -1
        for s in segments_iter:
            results.append(Segment(start=s.start, end=s.end, text=s.text.strip()))

            # Print progress every 10%
            if audio_duration > 0:
                pct = int(s.end / audio_duration * 100)
                pct = min(pct, 100)
                progress_step = pct // 10 * 10
                if progress_step > last_progress_pct:
                    last_progress_pct = progress_step
                    elapsed = time.monotonic() - t0
                    end_mins = int(s.end // 60)
                    end_secs = int(s.end % 60)
                    if pct >= 1 and s.end >= 60:
                        eta = elapsed / s.end * max(audio_duration - s.end, 0)
                        eta_text = f"ETA {_format_duration(eta)}"
                    else:
                        eta_text = "ETA warming up"
                    click.echo(
                        f"[*] {pct:3d}% | {end_mins}m{end_secs:02d}s / "
                        f"{audio_mins}m{audio_secs:02d}s | {len(results)} segments | "
                        f"{_format_duration(elapsed)} elapsed | {eta_text}"
                    )

        elapsed = time.monotonic() - t0
        speed_ratio = audio_duration / elapsed if elapsed > 0 else 0
        click.echo(
            f"[+] Transcription complete: {len(results)} segments, "
            f"{elapsed:.1f}s ({speed_ratio:.1f}x realtime)"
        )
        return results
