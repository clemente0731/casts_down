"""Tests for pipeline progress rendering."""

from casts_down.progress import (
    PipelineTaskView,
    ProgressTotals,
    color_status,
    render_eta,
    render_overall_progress,
    render_task_progress,
)


def test_color_status_maps_terminal_states():
    assert color_status("succeeded") == "green"
    assert color_status("done") == "green"
    assert color_status("ok") == "green"
    assert color_status("failed") == "red"
    assert color_status("error") == "red"
    assert color_status("queued") == "yellow"
    assert color_status("running") == "yellow"
    assert color_status("skipped") == "yellow"
    assert color_status("backfilled") == "yellow"
    assert color_status("pending") == "yellow"


def test_render_eta_uses_yellow_background_for_tty():
    text = render_eta("1h45m", tty=True)

    assert "ETA 1h45m" in text
    assert "\x1b[" in text


def test_render_eta_has_no_control_codes_for_non_tty():
    text = render_eta("1h45m", tty=False)

    assert text == "ETA 1h45m"
    assert "\x1b[" not in text


def test_render_overall_progress_includes_required_sections():
    totals = ProgressTotals(
        total=50,
        done=12,
        running=3,
        queued=35,
        failed=1,
        download_ok=14,
        download_failed=1,
        download_active=2,
        transcribe_ok=12,
        transcribe_active=1,
        transcribe_queued=1,
        elapsed="32m14s",
        active_budget="3/3",
        download_eta="28m10s",
        transcribe_eta="1h45m",
    )

    text = render_overall_progress(totals, tty=False)

    assert "=== Overall Progress ===" in text
    assert "Total: 50 | Done: 12 | Running: 3 | Queued: 35 | Failed: 1" in text
    assert "Download: 14/50 ok, 1 failed, 2 active" in text
    assert "Transcribe: 12/49 ok, 1 active, 1 queued" in text
    assert "Elapsed: 32m14s | Active budget: 3/3" in text
    assert "ETA 28m10s" in text
    assert "ETA 1h45m" in text
    assert "\x1b[" not in text


def test_render_task_progress_includes_green_yellow_red_rows():
    rows = [
        PipelineTaskView(1, "episode-a.mp3", "done", "done", "succeeded", "75 MB"),
        PipelineTaskView(
            2,
            "episode-b.mp3",
            "done",
            "42% ETA 12m",
            "running",
            "80 MB",
        ),
        PipelineTaskView(
            3,
            "episode-c.mp3",
            "failed",
            "skipped",
            "failed",
            "-",
            error="HTTP 403",
        ),
    ]

    text = render_task_progress(rows, tty=False)

    assert "=== Task Progress ===" in text
    assert "GREEN" in text
    assert "YELLOW" in text
    assert "RED" in text
    assert "episode-a.mp3" in text
    assert "episode-b.mp3" in text
    assert "episode-c.mp3" in text
    assert "HTTP 403" in text
    assert "\x1b[" not in text


def test_render_task_progress_aligns_wide_filenames():
    rows = [
        PipelineTaskView(
            1,
            "ascii-podcast-episode-long-title.mp3",
            "done",
            "queued",
            "running",
            "75 MB",
        ),
        PipelineTaskView(
            2,
            "科技播客-episode-long-title.mp3",
            "done",
            "queued",
            "running",
            "75 MB",
        ),
    ]

    text = render_task_progress(rows, tty=False)
    ascii_row, cjk_row = text.splitlines()[2:4]

    assert _display_width(ascii_row[: ascii_row.index("done")]) == _display_width(
        cjk_row[: cjk_row.index("done")]
    )
    assert "\x1b[" not in text


def _display_width(value):
    import unicodedata

    total = 0
    for char in value:
        if unicodedata.combining(char):
            continue
        if unicodedata.east_asian_width(char) in {"F", "W"}:
            total += 2
        else:
            total += 1
    return total
