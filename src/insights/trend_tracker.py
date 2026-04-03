"""Tracks CPU usage trends over time and flags recurring high-CPU processes."""

import logging
from collections import defaultdict, deque
from typing import Deque, Dict, List

from src.models.process import ProcessInfo

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SIZE = 10
DEFAULT_SPIKE_RATIO = 0.5  # flag when ≥50 % of window samples exceed the threshold


class TrendTracker:
    """Detects recurring CPU spikes by maintaining a per-PID rolling history.

    A process is flagged when at least *spike_ratio* of the samples in the
    rolling window exceed *cpu_threshold*, indicating a sustained or recurring
    burst rather than a momentary spike.
    """

    INSIGHT_PREFIX = "📈 CPU Spike Trend"

    def __init__(
        self,
        cpu_threshold: float = 50.0,
        window_size: int = DEFAULT_WINDOW_SIZE,
        spike_ratio: float = DEFAULT_SPIKE_RATIO,
    ) -> None:
        self.cpu_threshold = cpu_threshold
        self.window_size = window_size
        self.spike_ratio = spike_ratio
        self._history: Dict[int, Deque[float]] = defaultdict(
            lambda: deque(maxlen=self.window_size)
        )

    def analyze(self, processes: List[ProcessInfo]) -> None:
        """Annotate processes that show a recurring CPU spike trend in-place."""
        for proc in processes:
            history = self._history[proc.pid]
            history.append(proc.cpu_percent)
            # Need at least 2 samples before drawing conclusions.
            if len(history) < 2:
                continue
            spikes = sum(1 for c in history if c > self.cpu_threshold)
            if spikes / len(history) >= self.spike_ratio:
                insight = (
                    f"{self.INSIGHT_PREFIX}: {spikes}/{len(history)} samples"
                    f" exceeded {self.cpu_threshold:.0f}%"
                )
                proc.add_insight(insight)
                logger.debug(
                    "CPU trend detected: PID %d (%s) — %d/%d samples > %.0f%%",
                    proc.pid,
                    proc.name,
                    spikes,
                    len(history),
                    self.cpu_threshold,
                )
