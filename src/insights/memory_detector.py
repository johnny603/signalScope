"""Detects processes with abnormally high memory usage."""

import logging
from typing import List

from src.models.process import ProcessInfo

logger = logging.getLogger(__name__)

DEFAULT_MEM_THRESHOLD = 10.0


class MemoryAnomalyDetector:
    """Flags processes whose memory usage exceeds a configurable threshold."""

    INSIGHT_PREFIX = "🧠 High Memory"

    def __init__(self, mem_threshold: float = DEFAULT_MEM_THRESHOLD) -> None:
        self.mem_threshold = mem_threshold

    def analyze(self, processes: List[ProcessInfo]) -> None:
        """Annotate high-memory processes in-place with contextual memory% info."""
        for proc in processes:
            if proc.memory_percent > self.mem_threshold:
                insight = (
                    f"{self.INSIGHT_PREFIX}: {proc.memory_percent:.1f}%"
                    f" (above {self.mem_threshold:.0f}% threshold)"
                )
                proc.add_insight(insight)
                logger.debug(
                    "High memory detected: PID %d (%s) at %.1f%%",
                    proc.pid,
                    proc.name,
                    proc.memory_percent,
                )
