"""Detects daemon-like processes (no controlling terminal or very long uptime)."""

import logging
import time
from typing import List

import psutil

from src.models.process import ProcessInfo

logger = logging.getLogger(__name__)

# Processes running longer than this (seconds) are considered long-lived daemons.
LONG_UPTIME_SECONDS = 3600  # 1 hour


class DaemonDetector:
    """Identifies processes that appear to be daemons.

    A process is considered a daemon if *either* of the following is true:
    - It has no controlling terminal (``terminal`` attribute is ``None``).
    - Its uptime exceeds :data:`LONG_UPTIME_SECONDS`.
    """

    INSIGHT_NO_TTY = "🤖 Daemon (no tty)"
    INSIGHT_LONG_UPTIME = "🤖 Daemon (long uptime)"

    def analyze(self, processes: List[ProcessInfo]) -> None:
        """Annotate daemon-like processes in-place."""
        now = time.time()
        for proc in processes:
            try:
                p = psutil.Process(proc.pid)
                terminal = p.terminal()
                create_time = p.create_time()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as exc:
                logger.debug("DaemonDetector skip PID %d: %s", proc.pid, exc)
                continue

            if terminal is None:
                proc.add_insight(self.INSIGHT_NO_TTY)
            elif (now - create_time) > LONG_UPTIME_SECONDS:
                proc.add_insight(self.INSIGHT_LONG_UPTIME)
