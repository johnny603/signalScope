"""Detects processes with abnormally high CPU usage."""

import logging
from typing import List

from src.models.process import ProcessInfo

logger = logging.getLogger(__name__)

DEFAULT_CPU_THRESHOLD = 50.0


class AnomalyDetector:
    """Flags processes whose CPU usage exceeds a configurable threshold."""

    INSIGHT_PREFIX = "🔥 High CPU"

    def __init__(self, cpu_threshold: float = DEFAULT_CPU_THRESHOLD) -> None:
        self.cpu_threshold = cpu_threshold

    def analyze(self, processes: List[ProcessInfo]) -> None:
        """Annotate high-CPU processes in-place with contextual CPU% info."""
        for proc in processes:
            if proc.is_high_cpu(self.cpu_threshold):
                insight = (
                    f"{self.INSIGHT_PREFIX}: {proc.cpu_percent:.1f}%"
                    f" (above {self.cpu_threshold:.0f}% threshold)"
                )
                proc.add_insight(insight)
                logger.debug(
                    "High CPU detected: PID %d (%s) at %.1f%%",
                    proc.pid,
                    proc.name,
                    proc.cpu_percent,
                )
