"""Collects live process data using psutil."""

import logging
from typing import List, Optional

import psutil

from src.models.process import ProcessInfo

logger = logging.getLogger(__name__)


class ProcessCollector:
    """Gathers a snapshot of all running processes via psutil."""

    #: Fields requested from psutil for efficiency
    _ATTRS = ["pid", "name", "cpu_percent", "memory_percent", "status", "ppid", "username"]

    def __init__(self, user: Optional[str] = None) -> None:
        """
        Parameters
        ----------
        user:
            If set, only processes owned by this username are returned.
        """
        self.user = user

    def collect(self) -> List[ProcessInfo]:
        """Return a list of :class:`ProcessInfo` for every accessible process.

        Processes that disappear between enumeration and attribute access are
        silently skipped.
        """
        processes: List[ProcessInfo] = []

        # First pass: kick off cpu_percent measurement (non-blocking, returns 0.0)
        try:
            procs = list(psutil.process_iter(self._ATTRS))
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to enumerate processes: %s", exc)
            return processes

        for proc in procs:
            try:
                info = proc.info  # type: ignore[attr-defined]
                if self.user is not None and info.get("username") != self.user:
                    continue
                processes.append(
                    ProcessInfo(
                        pid=info["pid"],
                        name=info["name"] or "<unknown>",
                        cpu_percent=info.get("cpu_percent") or 0.0,
                        memory_percent=info.get("memory_percent") or 0.0,
                        status=info.get("status") or "unknown",
                        ppid=info.get("ppid"),
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # Process vanished or is inaccessible; skip it.
                pass
            except Exception as exc:  # pragma: no cover
                logger.debug("Unexpected error reading process %s: %s", proc, exc)

        return processes
