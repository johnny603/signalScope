"""Exports process snapshots to CSV or JSON files."""

import csv
import json
import os
from datetime import datetime, timezone
from typing import List

import psutil

from src.models.process import ProcessInfo

_FIELDS = ["pid", "name", "cpu_percent", "memory_percent", "status", "ppid", "insights"]


def _system_info() -> dict:
    """Return a snapshot of system-wide CPU and memory metrics."""
    try:
        mem = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": mem.percent,
            "memory_used_mb": mem.used // (1024 ** 2),
            "memory_total_mb": mem.total // (1024 ** 2),
        }
    except Exception:
        return {}


def _row(p: ProcessInfo) -> dict:
    return {
        "pid": p.pid,
        "name": p.name,
        "cpu_percent": p.cpu_percent,
        "memory_percent": p.memory_percent,
        "status": p.status,
        "ppid": p.ppid,
        "insights": p.insight_text,
    }


class ProcessExporter:
    """Serialises a process list to CSV or JSON.

    The output format is inferred from the file extension:

    * ``.json`` → JSON (includes timestamp and system summary)
    * anything else → CSV
    """

    def export(self, processes: List[ProcessInfo], path: str) -> None:
        """Write *processes* to *path*, creating or overwriting the file."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".json":
            self._export_json(processes, path)
        else:
            self._export_csv(processes, path)

    def _export_csv(self, processes: List[ProcessInfo], path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writeheader()
            for p in processes:
                writer.writerow(_row(p))

    def _export_json(self, processes: List[ProcessInfo], path: str) -> None:
        data = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "system": _system_info(),
            "processes": [_row(p) for p in processes],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
