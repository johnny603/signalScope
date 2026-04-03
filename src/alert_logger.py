"""Logs process anomaly alerts to a file."""

import logging
from typing import List, Set, Tuple

from src.models.process import ProcessInfo

logger = logging.getLogger(__name__)


class AlertLogger:
    """Appends anomaly alerts to a file whenever new insights are detected.

    Deduplication is based on ``(pid, insight)`` pairs so that the log is not
    flooded with identical lines on every refresh cycle.  Each unique anomaly
    is written exactly once per process lifetime.
    """

    def __init__(self, log_file: str) -> None:
        self._log_file = log_file
        self._seen: Set[Tuple[int, str]] = set()

        self._file_logger = logging.getLogger("signalscope.alerts")
        self._file_logger.propagate = False
        handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
        )
        self._file_logger.addHandler(handler)
        self._file_logger.setLevel(logging.INFO)

    def log_anomalies(self, processes: List[ProcessInfo]) -> None:
        """Write a log line for every new (pid, insight) pair not yet recorded."""
        for proc in processes:
            for insight in proc.insights:
                key: Tuple[int, str] = (proc.pid, insight)
                if key not in self._seen:
                    self._seen.add(key)
                    self._file_logger.info(
                        "⚠️  PID=%-6d  %-20s  CPU=%5.1f%%  Mem=%5.2f%%  %s",
                        proc.pid,
                        proc.name[:20],
                        proc.cpu_percent,
                        proc.memory_percent,
                        insight,
                    )
