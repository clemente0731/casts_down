```
   ____          _         ____
  / ___|__ _ ___| |_ ___  |  _ \  _____      ___ __
 | |   / _` / __| __/ __| | | | |/ _ \ \ /\ / / '_ \
 | |__| (_| \__ \ |_\__ \ | |_| | (_) \ V  V /| | | |
  \____\__,_|___/\__|___/ |____/ \___/ \_/\_/ |_| |_|

      Intelligent Podcast Downloader & Transcriber
```

A cross-platform CLI tool for downloading and transcribing podcasts. Supports Apple Podcasts, Xiaoyuzhou, and RSS feeds with built-in local speech-to-text powered by Whisper.

---

## Disclaimer

> **This tool is for EDUCATIONAL and PERSONAL USE ONLY.**
>
> By using this software, you agree to: use for personal learning and research only; respect copyright laws and intellectual property; support content creators through official channels; comply with platform terms of service.
>
> **Prohibited:** commercial redistribution, mass downloading for public sharing, bypassing paid subscriptions, any activity that harms content creators or platforms. The developers fully support and uphold the rights of content creators and platforms.

> **本工具仅供学习和个人使用。**
>
> 使用本软件即表示您同意：仅用于个人学习和研究；尊重版权法律和知识产权；通过官方渠道支持内容创作者；遵守平台服务条款。
>
> **禁止：** 商业性再分发、大规模下载用于公开传播、绕过付费订阅服务、任何损害创作者或平台的行为。开发者拥护并尊重内容创作者和平台的所有权利。

---

## Features

- **Smart URL Detection** - Automatically identifies platform from URL, no need to specify downloader
- **Multi-Platform Support**
  - Apple Podcasts (single episodes and podcast pages)
  - Xiaoyuzhou / 小宇宙 (single episodes and podcast feeds)
  - Standard RSS 2.0 feeds
- **Pipeline Concurrency** - `--concurrent` caps active download/transcription work
- **Auto Transcription** - Downloads are automatically transcribed as files finish
- **Built-in Speech-to-Text** - Local transcription via faster-whisper (CUDA/CPU), with optional mlx-whisper (Metal) for Mac
- **Subtitle Output** - Generates SRT (millisecond precision), timestamped TXT, and English word-frequency JSON files
- **Progress Display** - Episode/byte download progress, transcription ETA, and final task timing summary
- **Episode Selection** - Download all, latest N, or specific episodes from Apple Podcasts links
- **Smart File Management** - Auto-naming, skip existing files, resume-safe temp files

## Installation

### Install via pip

```bash
pip install casts_down
```

Includes Python dependencies for download and faster-whisper transcription. Transcription also requires `ffmpeg` on `PATH`; the Whisper model downloads on first transcription or during `casts-down setup-transcribe`.

### macOS Apple Silicon (Metal acceleration)

```bash
pip install "casts_down[metal]"
```

Adds mlx-whisper for Metal GPU acceleration. Falls back to faster-whisper CPU if unavailable.

### Install from GitHub

```bash
# Latest release
pip install git+https://github.com/host452b/casts_down.git@v2.3.5

# Latest main branch
pip install git+https://github.com/host452b/casts_down.git

# SSH
pip install git+ssh://git@github.com/host452b/casts_down.git@v2.3.5
```

### Install from source

```bash
git clone https://github.com/host452b/casts_down.git
cd casts_down
pip install -e ".[dev]"
```

### Build & Publish

```bash
git clone https://github.com/host452b/casts_down.git
cd casts_down

make build          # .pyz standalone executable (<1s)
make dist           # wheel + sdist for PyPI
make publish        # build + upload to PyPI
make publish-test   # build + upload to TestPyPI
make release        # clean + build all (.pyz + wheel + sdist)
```

See [BUILD.md](BUILD.md) for details.

## Quick Start

```bash
# Download and transcribe (transcription is automatic)
casts-down "https://podcasts.apple.com/podcast/id123"

# Download all episodes
casts-down "https://feeds.example.com/podcast.rss" --all

# Download without transcription
casts-down "https://feeds.example.com/podcast.rss" --no-transcribe

# Xiaoyuzhou
casts-down "https://www.xiaoyuzhoufm.com/episode/xxx"

# Transcribe existing audio files
casts-down transcribe ./podcasts/episode.mp3
casts-down transcribe ./podcasts/          # entire directory
```

## Usage

### Download (+ Auto Transcribe)

```bash
casts-down <URL> [URL ...] [OPTIONS]
```

With no episode-selection flags, Casts Down downloads the latest episode and transcribes it with the default model. For example, this command:

```bash
casts-down "https://podcasts.apple.com/us/podcast/example-show/id1234567890"
```

is equivalent to:

```bash
casts-down "https://podcasts.apple.com/us/podcast/example-show/id1234567890" --latest 1 --transcribe --model small
```

Download options can appear before or after the URL. Invalid combinations fail before any network request:

- Multiple URLs are allowed; options apply to every URL in the command.
- Use either `--all` or `--latest N`, not both.
- `--model NAME` is only valid when transcription is enabled.
- Download options require a URL; run `casts-down -h` for help.

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--all` | `-a` | Download all episodes | latest 1 |
| `--latest N` | `-l N` | Download latest N episodes | 1 |
| `--output DIR` | `-o DIR` | Output directory | `./podcasts` |
| `--concurrent N` | `-c N` | Max active pipeline tasks. With transcription enabled, this budget is shared by downloads and transcription. With `--no-transcribe`, it controls parallel downloads. Capped by selected episode count. | 3 |
| `--skip-existing` | `-s` | Skip already downloaded files | off |
| `--transcribe/--no-transcribe` | `-t` | Transcribe after download | **on** |
| `--model NAME` | `-m` | Whisper model for transcription | `small` |

### Transcribe

```bash
casts-down transcribe <FILE>... [OPTIONS]
```

Transcribe audio files or directories. Outputs `.srt` (subtitle), `.txt` (timestamped text), and `.words.json` (English word frequencies) alongside each audio file.

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--model NAME` | `-m` | Whisper model (`tiny`, `base`, `small`, `medium`, `large-v3`) | `small` |
| `--language CODE` | | Language code (`zh`, `en`, etc.) | auto-detect |
| `--skip-transcribed` | | Skip files already transcribed | on |
| `--overwrite` | | Force re-transcribe existing outputs | off |

### Model Selection

`--model` is passed directly to the active Whisper backend. For predictable cross-platform behavior, use these stable model names:

| Model | Quality | Speed | Approx. memory / VRAM | Best for |
|-------|---------|-------|------------------------|----------|
| `tiny` | Low | Fastest | ~1 GB class | Quick checks, smoke tests |
| `base` | Basic | Very fast | 1-2 GB | Low-spec CPU machines |
| `small` | Good | Fast | ~2 GB VRAM; 2-4 GB RAM | Default choice for podcasts |
| `medium` | Better | Medium | ~5 GB VRAM; 8 GB+ RAM | Chinese, noisy audio, accents |
| `large-v3` | Best | Slow | ~10 GB VRAM; 16 GB+ RAM | Quality-first transcription |

English-only variants are also useful for English audio: `tiny.en`, `base.en`, `small.en`, and `medium.en`. They are usually most helpful on smaller models.

Recommended choices:

```bash
# Balanced default
casts-down transcribe audio.mp3 --model small

# Low-spec CPU or quick preview
casts-down transcribe audio.mp3 --model base

# Better Chinese or noisy-audio quality
casts-down transcribe audio.mp3 --model medium --language zh

# Best quality when GPU/RAM is available
casts-down transcribe audio.mp3 --model large-v3
```

Notes:

- Larger models improve recognition quality but increase model download size, memory use, startup time, and transcription time.
- `small` is the recommended default for most podcast workflows.
- `medium` is the practical upgrade when `small` misses words, names, accents, or Chinese content.
- `large-v3` is best reserved for quality-sensitive runs on machines with enough GPU/RAM.
- Advanced model names such as `turbo` or `distil-large-v3` may work on some backends, but they are not listed as the main path because availability differs between `faster-whisper` and `mlx-whisper`.

### Setup (Optional)

```bash
casts-down setup-transcribe
casts-down setup-transcribe --backend faster-whisper
casts-down setup-transcribe --backend mlx-whisper
```

Pre-downloads the Whisper model so the first transcription has zero wait. Also installs mlx-whisper on Mac Apple Silicon for Metal GPU acceleration.

| Platform | Engine | Acceleration |
|----------|--------|-------------|
| macOS Apple Silicon | mlx-whisper + faster-whisper | Metal GPU |
| macOS Intel | faster-whisper | CPU |
| Linux + NVIDIA | faster-whisper | CUDA |
| Linux (no GPU) | faster-whisper | CPU |
| Windows + NVIDIA | faster-whisper | CUDA, then CPU fallback |
| Windows (no GPU) | faster-whisper | CPU |

### How subtitle generation works

Casts Down does not download existing subtitle files. It generates subtitles and text artifacts from the audio:

1. The audio file is passed to a local Whisper engine.
2. On Apple Silicon, `mlx-whisper` is preferred when installed; otherwise `faster-whisper` is used.
3. Whisper returns ordered text segments with start and end timestamps in seconds.
4. Casts Down writes those segments as `.srt` subtitles, a timestamped `.txt` transcript, and a `.words.json` English word-frequency report next to the audio file.
5. If `.srt` and `.txt` already exist but `.words.json` is missing or uses an older normalization rule, Casts Down backfills `.words.json` from the existing `.txt` without rerunning Whisper.
6. If all three outputs already exist, transcription is skipped unless `--overwrite` is used.

The `.srt` file uses the standard subtitle shape: segment number, `HH:MM:SS,mmm --> HH:MM:SS,mmm`, then text.

The `.words.json` file is built from the timestamped `.txt` transcript. Timestamps and numbers are ignored, text is lowercased, punctuation and whitespace are normalized, possessive `'s` is removed, common contractions are expanded, hyphenated words are split, and only English `[a-z]+` tokens longer than 3 letters are counted. The output includes `total_words`, `unique_words`, and the full word list sorted by count descending, then alphabetically.

For `faster-whisper`, progress is based on decoded segment timestamps. The first few seconds can include CUDA/model warmup, so ETA is treated as warming up until enough audio has been processed.

At the end of a download or transcription command, Casts Down prints a structured timing summary:

```text
=== Task Timing ===
Download: 1m23s
Transcription: 12m04s
Total: 13m27s
```

## Platform Support

### Fully Supported

**Apple Podcasts**
- [x] Podcast homepage (download all or latest N episodes)
- [x] Single episode links (smart matching and download)
- [x] Automatic RSS extraction via iTunes API

**Xiaoyuzhou / 小宇宙**
- [x] Single episode links
- [x] Podcast links (first 15 episodes)
- [ ] Full podcast list (requires additional reverse engineering)

**RSS Feeds**
- [x] Standard RSS 2.0 podcast feeds (most reliable method)

### Not Supported

**Pocket Casts** - Client application, does not host audio files. Use the original podcast RSS feed instead.

## Output Example

```
podcasts/
  my-podcast--episode-1.mp3
  my-podcast--episode-1.srt     # SRT subtitle (00:01:23,456 --> 00:01:27,890)
  my-podcast--episode-1.txt     # [00:01:23] Timestamped plain text
  my-podcast--episode-1.words.json
```

Downloaded filenames are normalized to readable kebab-case. Smart quotes, commas, brackets, and other punctuation are removed or converted to separators, while CJK text is preserved. If two episodes normalize to the same name, Casts Down adds a numeric suffix before the extension to avoid overwriting output files.

## Examples

### Download NPR's "Up First" podcast

```bash
casts-down "https://feeds.npr.org/510318/podcast.xml" --latest 3
```

### Download from Apple Podcasts

```bash
casts-down "https://podcasts.apple.com/us/podcast/example-show/id1234567890" --all
```

Concurrency examples:

```bash
casts-down "https://feeds.example.com/podcast.rss" --latest 50 --concurrent 3
casts-down "https://feeds.example.com/podcast.rss" --latest 50 --concurrent 1
casts-down "https://feeds.example.com/podcast.rss" --latest 50 --no-transcribe --concurrent 5
```

### Download latest 50 episodes

```bash
casts-down "https://podcasts.apple.com/us/podcast/example-show/id1234567890" \
  --latest 50 \
  --output ./podcasts/example-show \
  --skip-existing \
  --concurrent 3
```

### Download latest 50 episodes from multiple podcasts

```bash
casts-down \
  "https://podcasts.apple.com/us/podcast/example-a/id1111111111" \
  "https://podcasts.apple.com/us/podcast/example-b/id2222222222" \
  --latest 50 \
  --output ./podcasts \
  --skip-existing \
  --concurrent 3
```

All download options are global in multi-URL mode. If different podcasts need different `--latest`, `--all`, `--output`, or transcription settings, run separate commands.

### Download all available episodes

```bash
casts-down "https://podcasts.apple.com/us/podcast/example-show/id1234567890" \
  --all \
  --output ./podcasts/example-show \
  --skip-existing \
  --no-transcribe
```

### Download and transcribe latest 50 episodes

```bash
casts-down "https://podcasts.apple.com/us/podcast/example-show/id1234567890" \
  --latest 50 \
  --output ./podcasts/example-show \
  --skip-existing \
  --concurrent 3 \
  --model small
```

### Download from RSS only

```bash
casts-down "https://feeds.example.com/podcast.rss" --latest 5 --no-transcribe
```

### Transcribe a directory of audio files

```bash
casts-down transcribe ./podcasts/ --model medium --language zh
```

## Technical Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.10+ |
| CLI Framework | click |
| HTTP Client | aiohttp (async concurrent) |
| RSS Parsing | feedparser |
| HTML Parsing | BeautifulSoup4 |
| Progress Display | tqdm |
| ASR Engine | faster-whisper (built-in) / mlx-whisper (optional Metal) |

## Notes

> **Important considerations:**
> 1. **RSS Feed Expiration** - Some feeds may require authentication or contain expired URLs
> 2. **Audio URL Validity** - Some audio URLs contain time-limited tokens that may expire
> 3. **Rate Limiting** - Frequent requests may trigger platform restrictions
> 4. **Copyright** - Ensure all downloads are for personal use only
> 5. **Model Download** - First transcription auto-downloads the Whisper model (~466 MB for `small`). Run `casts-down setup-transcribe` to pre-download.

## Troubleshooting

### Cannot extract Apple Podcasts RSS

- Ensure URL format is correct (must contain podcast ID, e.g. `/id1234567`)
- Check network connection
- Try using the RSS feed URL directly if available

### Download timeout

- Reduce concurrency: `--concurrent 1`
- Check network connection and proxy settings
- Some servers may have rate limiting
- Downloads show both episode progress and byte progress when the server provides `Content-Length`

### Transcription fails

- Try a smaller model: `--model base` or `--model tiny`
- Check available disk space (models are 75MB - 3GB)
- For Chinese content, specify language: `--language zh`
- On Mac Apple Silicon, install Metal support: `pip install "casts_down[metal]"`
- On Windows + NVIDIA, CUDA DLL paths from pip-installed NVIDIA packages are prepared automatically before CUDA initialization. If CUDA still fails, the tool logs a CUDA device fallback and uses CPU.

### Abnormal file names

- Tool automatically cleans illegal characters from filenames
- If issues persist, please submit an [Issue](https://github.com/host452b/casts_down/issues)

## Quick Test

```bash
# Test download + transcription
casts-down "https://feeds.npr.org/510318/podcast.xml" --latest 1

# Test download only
casts-down "https://podcasts.apple.com/us/podcast/the-daily/id1200361736" --latest 1 --no-transcribe

# Test standalone transcription
casts-down transcribe ./podcasts/episode.mp3 --model tiny
```

## License

MIT License. Copyright (c) 2024 Casts Down Contributors.

## Contributing

Contributions are welcome! Please submit [Issues](https://github.com/host452b/casts_down/issues) and Pull Requests.

---

```
Made with <3 by open source contributors
```
