# Pipeline Download And Transcribe Design

## Goal

Improve multi-episode throughput by overlapping network IO with local transcription while keeping GPU/CPU use predictable and preserving stable final reporting.

Current behavior downloads all selected files first, then transcribes them as a batch. The new pipeline should start transcribing a completed audio file while the next audio files are still downloading.

## User-Facing Behavior

The default download command should keep the existing behavior contract: downloads selected podcast episodes and transcribes them unless `--no-transcribe` is set.

When transcription is enabled, the command should run as a pipeline:

1. Resolve and select episodes from each URL.
2. Download selected episodes with bounded concurrency.
3. As soon as one file finishes safely, enqueue it for transcription.
4. Run one transcription worker so the Whisper model loads once and CUDA/CPU resources are not oversubscribed.
5. Continue downloading while transcription is active.
6. Wait for the transcription queue to drain.
7. Print a color-coded final report and structured timing summary.

`--no-transcribe` should keep a download-only path.

## Concurrency Semantics

`--concurrent N` should no longer be documented as only "Parallel downloads".

New meaning:

```text
Max active pipeline tasks. With transcription enabled, this budget is shared by downloads and transcription. With --no-transcribe, it controls parallel downloads. Capped by selected episode count. Default: 3.
```

Effective concurrency:

```text
effective_concurrency = min(user_concurrent, selected_episode_count)
```

Pipeline allocation when transcription is enabled:

```text
transcribe_workers = 1
download_workers = max(1, effective_concurrency - transcribe_workers)
```

Examples:

```text
1 selected episode, --concurrent 3 -> 1 active task
2 selected episodes, --concurrent 3 -> 1 download + 1 transcribe
50 selected episodes, --concurrent 3 -> up to 2 downloads + 1 transcribe
50 selected episodes, --concurrent 1 -> no overlap; one file downloads, then transcribes
```

This keeps the total active work bounded by the user-facing number and prevents hidden extra load such as 3 downloads plus 1 transcription.

## Progress Display

Runtime progress should have two levels.

Overall progress:

```text
=== Overall Progress ===
Total: 50 | Done: 12 | Running: 3 | Queued: 35 | Failed: 1
Download: 14/50 ok, 1 failed, 2 active | 4.2 GB / 15.8 GB | ETA 28m10s
Transcribe: 12/49 ok, 1 active, 1 queued | audio 9h12m / 41h30m | ETA 1h45m
Elapsed: 32m14s | Active budget: 3/3
```

Per-task progress:

```text
=== Task Progress ===
Status   #   File                 Download          Transcribe         Size     Error
GREEN    01  episode-a.mp3         done              done               75 MB    -
YELLOW   02  episode-b.mp3         done              42% ETA 12m        80 MB    -
YELLOW   03  episode-c.mp3         68% ETA 3m        queued             64 MB    -
RED      04  episode-d.mp3         failed            skipped            -        HTTP 403
```

Color rules:

- Green: whole task succeeded, or a completed stage succeeded.
- Yellow: queued, running, skipped, already exists, `.words.json` backfilled, or degraded fallback.
- Red: download failed, transcription failed, output write failed, or task could not continue.

ETA fields for running work should use a yellow background in TTY output, for example `ETA 1h45m`. In non-TTY output, keep the same text and avoid terminal control codes.

TTY output may refresh the tables in place. Non-TTY output should fall back to periodic textual summaries and always print the final report.

## Internal Architecture

Add a pipeline layer instead of expanding `cli.py`.

Suggested modules:

- `casts_down/pipeline.py`: orchestration, queueing, task records, final report.
- `casts_down/progress.py`: color-coded overall and per-task progress rendering.
- `casts_down/transcribe/__init__.py`: expose or add a single-file transcription helper that returns the same result shape as batch transcription.

The pipeline should use event-style updates:

```text
download_started
download_progress
download_done
download_failed
transcribe_queued
transcribe_started
transcribe_progress
transcribe_done
transcribe_failed
```

Downloaders should report completed files through a callback such as `on_file_done(path, metadata)` only after the final audio path exists and any `.tmp` file has been renamed.

The transcription worker should consume completed file paths from an `asyncio.Queue`. Since the current Whisper engines are synchronous, the worker can run transcription through a bounded executor or a dedicated thread. There should be only one transcription worker in the first version.

## Stability Rules

- Never enqueue a `.tmp` file.
- Keep one transcription worker by default.
- Load the transcription engine once per command.
- If one download fails, continue other downloads.
- If one transcription fails, continue processing later completed downloads.
- If the user interrupts the command, cancel pending downloads, finish no new transcriptions, clean temp files best-effort, and print a partial report.
- Existing skip/backfill behavior for `.srt`, `.txt`, and `.words.json` must remain.
- Final exit code should be non-zero if any selected task has a red status.

## Final Report Fields

Each task row should include:

- status color
- source URL or podcast identifier
- episode title or final filename
- output audio path
- download status
- transcription status
- file size when available
- audio duration when available
- elapsed download time
- elapsed transcription time
- generated output paths when transcription succeeds
- error message when failed

The report should also include totals:

- selected episodes
- download succeeded / skipped / failed
- transcription succeeded / skipped / failed / backfilled
- total bytes downloaded
- total elapsed time
- download stage elapsed time
- transcription stage elapsed time

## CLI And Documentation Changes

Update help and README wording for `--concurrent`:

```text
--concurrent, -c N
  Max active pipeline tasks. With transcription enabled, this budget is shared by downloads and transcription. With --no-transcribe, it controls parallel downloads. Capped by selected episode count. Default: 3.
```

Add README examples:

```text
casts-down "https://feeds.example.com/podcast.rss" --latest 50 --concurrent 3
casts-down "https://feeds.example.com/podcast.rss" --latest 50 --concurrent 1
casts-down "https://feeds.example.com/podcast.rss" --latest 50 --no-transcribe --concurrent 5
```

## Testing

Unit tests should cover:

- `effective_concurrency = min(user_concurrent, selected_episode_count)`.
- Pipeline allocation keeps total active work within `--concurrent`.
- A completed download is enqueued for transcription before later downloads finish.
- Failed downloads do not enqueue transcription.
- Failed transcriptions do not stop later completed downloads from being processed.
- Existing transcript skip/backfill behavior still works inside the pipeline.
- Final report color/status classification for green, yellow, and red rows.
- Non-TTY output uses summary logs instead of dynamic table refresh.

CLI tests should cover:

- `--concurrent` help text and README-aligned semantics.
- `--no-transcribe` still uses download-only concurrency.
- Pipeline command prints both overall progress and per-task progress.
- Final exit code is non-zero when any selected task fails.

## Non-Goals For First Version

- Multiple simultaneous transcription workers.
- Per-GPU scheduling.
- Persisted resume database.
- Real-time transcription before a file finishes downloading.
- Replacing `tqdm` everywhere in one large refactor.
