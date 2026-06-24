"""Helpers for human-friendly media filenames."""

from pathlib import Path
from urllib.parse import unquote, urlparse
import unicodedata

MAX_FILENAME_BYTES = 240
_INVALID_FILENAME_CHARS = set('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

_REMOVE_CHARS = {
    ord("'"): None,
    ord("`"): None,
    ord("´"): None,
    ord("‘"): None,
    ord("’"): None,
}

_WORD_CHARS = {
    "&": " and ",
    "+": " plus ",
    "@": " at ",
}


def slugify_filename_part(value: str, fallback: str = "episode") -> str:
    """Convert a title fragment into readable kebab-case while preserving CJK."""
    text = unicodedata.normalize("NFKC", value or "")
    for source, replacement in _WORD_CHARS.items():
        text = text.replace(source, replacement)
    text = text.translate(_REMOVE_CHARS)

    chars: list[str] = []
    previous_separator = False
    for char in text:
        if char.isalnum():
            chars.append(char.lower())
            previous_separator = False
            continue

        if unicodedata.category(char).startswith("M"):
            continue

        if not previous_separator:
            chars.append("-")
            previous_separator = True

    slug = "".join(chars).strip("-")
    return slug or fallback


def extension_from_url(audio_url: str, default: str = ".mp3") -> str:
    """Extract a conservative lowercase file extension from an audio URL."""
    path = unquote(urlparse(audio_url).path)
    ext = Path(path).suffix.lower()
    if not ext or len(ext) > 10:
        return default
    if not ext.startswith(".") or not ext[1:].isalnum():
        return default
    return ext


def _trim_to_bytes(value: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""

    trimmed = value
    while len(trimmed.encode("utf-8")) > max_bytes:
        trimmed = trimmed[:-1].rstrip("-")
    return trimmed


def _ensure_valid_stem(stem: str, max_bytes: int) -> str:
    stem = _trim_to_bytes(stem.strip(" .-"), max_bytes) or "episode"
    if stem.casefold() in _WINDOWS_RESERVED_NAMES:
        suffix = "-episode"
        stem = _trim_to_bytes(stem, max_bytes - len(suffix)) + suffix
    return stem or "episode"


def build_media_filename(
    episode_title: str,
    audio_url: str,
    podcast_name: str | None = None,
    default_ext: str = ".mp3",
) -> str:
    """Build a stable podcast--episode.ext filename."""
    ext = extension_from_url(audio_url, default=default_ext)
    max_base_bytes = MAX_FILENAME_BYTES - len(ext.encode("utf-8"))

    episode_slug = slugify_filename_part(episode_title, fallback="episode")
    podcast_slug = slugify_filename_part(podcast_name or "", fallback="") if podcast_name else ""

    if podcast_slug:
        delimiter = "--"
        podcast_budget = min(80, max_base_bytes // 2)
        podcast_slug = _trim_to_bytes(podcast_slug, podcast_budget)
        episode_budget = max_base_bytes - len(podcast_slug.encode("utf-8")) - len(delimiter)
        episode_slug = _trim_to_bytes(episode_slug, episode_budget) or "episode"
        base = f"{podcast_slug}{delimiter}{episode_slug}"
    else:
        base = _trim_to_bytes(episode_slug, max_base_bytes) or "episode"

    base = _ensure_valid_stem(base, max_base_bytes)
    return f"{base}{ext}"


def is_valid_media_filename(filename: str) -> bool:
    """Return whether filename is safe for common local filesystems."""
    if not filename or filename != Path(filename).name:
        return False
    if len(filename.encode("utf-8")) > MAX_FILENAME_BYTES:
        return False
    if filename.endswith((" ", ".")):
        return False
    if any(char in _INVALID_FILENAME_CHARS or ord(char) < 32 for char in filename):
        return False

    path = Path(filename)
    stem = path.stem
    if not stem or stem in {".", ".."}:
        return False
    if stem.casefold() in _WINDOWS_RESERVED_NAMES:
        return False
    if path.suffix and not path.suffix[1:].isalnum():
        return False
    return True


def dedupe_filename(filename: str, used_names: set[str]) -> str:
    """Return filename or a numbered variant that is unique within used_names."""
    used_keys = {name.casefold() for name in used_names}
    if filename.casefold() not in used_keys:
        return filename

    path = Path(filename)
    suffix = path.suffix
    stem = path.stem

    index = 2
    while True:
        marker = f"-{index}"
        max_stem_bytes = MAX_FILENAME_BYTES - len(suffix.encode("utf-8")) - len(marker.encode("utf-8"))
        candidate_stem = _ensure_valid_stem(stem, max_stem_bytes)
        candidate = f"{candidate_stem}{marker}{suffix}"
        if candidate.casefold() not in used_keys:
            return candidate
        index += 1
