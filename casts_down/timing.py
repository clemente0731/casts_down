"""Small timing helpers for CLI task summaries."""
import time
from dataclasses import dataclass, field


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    return f"{minutes}m{secs:02d}s"


@dataclass
class TaskTimer:
    started_at: float = field(default_factory=time.monotonic)
    stages: dict[str, float] = field(default_factory=dict)

    def record(self, name: str, elapsed: float) -> None:
        self.stages[name] = elapsed

    def total_elapsed(self) -> float:
        return time.monotonic() - self.started_at
