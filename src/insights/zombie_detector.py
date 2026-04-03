"""Detects zombie processes."""

import logging
from typing import List

from src.models.process import ProcessInfo

logger = logging.getLogger(__name__)


class ZombieDetector:
    """Identifies processes whose status is 'zombie'."""

    INSIGHT = "👻 Zombie: Process finished but parent has not called wait()"

    def analyze(self, processes: List[ProcessInfo]) -> None:
        """Annotate zombie processes in-place."""
        for proc in processes:
            if proc.is_zombie():
                proc.add_insight(self.INSIGHT)
                logger.debug("Zombie detected: PID %d (%s)", proc.pid, proc.name)
