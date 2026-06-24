"""English word-frequency statistics for transcript text."""

from collections import Counter
from pathlib import Path
import json
import re
import unicodedata


TIMESTAMP_RE = re.compile(r"\[\d{1,2}:\d{2}:\d{2}(?:[,.]\d+)?\]")
WORD_RE = re.compile(r"[a-z]+")
MIN_WORD_LENGTH = 4
WORD_STATS_VERSION = 2

CONTRACTIONS = {
    "can't": "can not",
    "cannot": "can not",
    "won't": "will not",
    "shan't": "shall not",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "haven't": "have not",
    "hasn't": "has not",
    "hadn't": "had not",
    "wouldn't": "would not",
    "shouldn't": "should not",
    "couldn't": "could not",
    "mustn't": "must not",
}

APOSTROPHES = str.maketrans({
    "‘": "'",
    "’": "'",
    "‛": "'",
    "＇": "'",
    "`": "'",
    "´": "'",
})

DASHES = str.maketrans({
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "―": "-",
})


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.translate(APOSTROPHES).translate(DASHES)
    normalized = TIMESTAMP_RE.sub(" ", normalized)
    normalized = normalized.lower()

    for contraction, replacement in CONTRACTIONS.items():
        normalized = re.sub(rf"\b{re.escape(contraction)}\b", replacement, normalized)

    normalized = re.sub(r"\b([a-z]+)'m\b", r"\1 am", normalized)
    normalized = re.sub(r"\b([a-z]+)'re\b", r"\1 are", normalized)
    normalized = re.sub(r"\b([a-z]+)'ve\b", r"\1 have", normalized)
    normalized = re.sub(r"\b([a-z]+)'ll\b", r"\1 will", normalized)
    normalized = re.sub(r"\b([a-z]+)'d\b", r"\1 would", normalized)

    # For this feature, possessive/'s forms should not create a separate "s".
    normalized = re.sub(r"\b([a-z]+)'s\b", r"\1", normalized)
    normalized = re.sub(r"\b([a-z]+)'\b", r"\1", normalized)
    return normalized


def extract_english_words(text: str) -> list[str]:
    """Extract normalized English words from timestamped transcript text."""
    normalized = _normalize_text(text)
    return [word for word in WORD_RE.findall(normalized) if len(word) >= MIN_WORD_LENGTH]


def build_word_stats(text: str, audio_name: str) -> dict:
    """Build a stable, full word-frequency payload."""
    counts = Counter(extract_english_words(text))
    words = [
        {"word": word, "count": count}
        for word, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "version": WORD_STATS_VERSION,
        "audio": audio_name,
        "total_words": sum(counts.values()),
        "unique_words": len(counts),
        "normalization": {
            "case": "lowercase",
            "timestamps": "removed",
            "numbers": "ignored",
            "apostrophe_s": "removed",
            "contractions": "expanded",
            "hyphen": "separator",
            "token_pattern": "[a-z]+",
            "min_word_length": MIN_WORD_LENGTH,
        },
        "words": words,
    }


def word_stats_path(audio_path: Path) -> Path:
    return audio_path.with_suffix(".words.json")


def word_stats_is_current(audio_path: Path) -> bool:
    output_path = word_stats_path(audio_path)
    if not output_path.exists():
        return False
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    normalization = payload.get("normalization", {})
    return (
        payload.get("version") == WORD_STATS_VERSION
        and normalization.get("min_word_length") == MIN_WORD_LENGTH
    )


def write_word_stats_json(audio_path: Path, transcript_text: str) -> Path:
    """Write transcript word stats through a temporary file and atomic rename."""
    output_path = word_stats_path(audio_path)
    tmp_path = output_path.parent / (output_path.name + ".tmp")
    payload = build_word_stats(transcript_text, audio_name=audio_path.name)
    try:
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.rename(output_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return output_path


def write_word_stats_from_txt(audio_path: Path) -> Path:
    transcript_text = audio_path.with_suffix(".txt").read_text(encoding="utf-8")
    return write_word_stats_json(audio_path, transcript_text)
