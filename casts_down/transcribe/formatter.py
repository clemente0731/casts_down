"""Output formatters for transcription segments."""
from pathlib import Path
from casts_down.transcribe.engine import Segment

def _format_srt_time(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    total_seconds, ms = divmod(total_ms, 1000)
    h, remainder = divmod(total_seconds, 3600)
    m, s = divmod(remainder, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def _format_txt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"[{h:02d}:{m:02d}:{s:02d}]"

def format_srt(segments: list[Segment]) -> str:
    if not segments:
        return ""
    parts = []
    for i, seg in enumerate(segments, 1):
        parts.append(f"{i}")
        parts.append(f"{_format_srt_time(seg.start)} --> {_format_srt_time(seg.end)}")
        parts.append(seg.text)
        parts.append("")
    return "\n".join(parts)

def format_txt(segments: list[Segment]) -> str:
    if not segments:
        return ""
    return "\n".join(f"{_format_txt_time(seg.start)} {seg.text}" for seg in segments)

def write_outputs(audio_path: Path, segments: list[Segment]) -> tuple[Path, Path]:
    srt_path = audio_path.with_suffix(".srt")
    txt_path = audio_path.with_suffix(".txt")
    srt_tmp = srt_path.parent / (srt_path.name + ".tmp")
    txt_tmp = txt_path.parent / (txt_path.name + ".tmp")
    try:
        srt_tmp.write_text(format_srt(segments), encoding="utf-8")
        txt_tmp.write_text(format_txt(segments), encoding="utf-8")
        srt_tmp.rename(srt_path)
        txt_tmp.rename(txt_path)
    finally:
        for tmp in (srt_tmp, txt_tmp):
            if tmp.exists():
                tmp.unlink()
    return srt_path, txt_path
