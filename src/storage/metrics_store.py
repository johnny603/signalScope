"""Metrics persistence layer using SQLite."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from src.models.process import ProcessInfo


class MetricsStore:
    """Persist process snapshots, anomaly events, and kill events to SQLite."""

    def __init__(
        self,
        db_path: str = "~/.signalscope/metrics.db",
        retention_days: int = 7,
    ) -> None:
        path = Path(db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(path)
        self._ensure_schema()
        self._apply_retention(retention_days)

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS process_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    captured_at DATETIME NOT NULL,
                    pid INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    cpu_percent REAL,
                    memory_percent REAL,
                    status TEXT,
                    insights TEXT
                );

                CREATE TABLE IF NOT EXISTS anomaly_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at DATETIME NOT NULL,
                    pid INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    detail TEXT
                );

                CREATE TABLE IF NOT EXISTS kill_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at DATETIME NOT NULL,
                    pid INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    message TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_pid_time
                    ON process_snapshots(pid, captured_at);
                CREATE INDEX IF NOT EXISTS idx_anomaly_time
                    ON anomaly_events(occurred_at);
                CREATE INDEX IF NOT EXISTS idx_kill_time
                    ON kill_events(occurred_at);
            """)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def record_snapshot(self, processes: List[ProcessInfo]) -> None:
        """Insert all processes as a batch for the current timestamp."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO process_snapshots "
                "(captured_at, pid, name, cpu_percent, memory_percent, status, insights) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        now,
                        p.pid,
                        p.name,
                        p.cpu_percent,
                        p.memory_percent,
                        p.status,
                        json.dumps(p.insights),
                    )
                    for p in processes
                ],
            )

    def record_anomaly(
        self, pid: int, name: str, event_type: str, detail: str = ""
    ) -> None:
        """Insert a single anomaly event."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO anomaly_events (occurred_at, pid, name, event_type, detail) "
                "VALUES (?, ?, ?, ?, ?)",
                (now, pid, name, event_type, detail),
            )

    def record_kill(self, result) -> None:
        """Insert a kill event from an ActionResult."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO kill_events (occurred_at, pid, name, signal, success, message) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    result.timestamp,
                    result.pid,
                    result.process_name,
                    result.signal_sent,
                    int(result.success),
                    result.message,
                ),
            )

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def get_process_history(
        self, pid: int, hours: float = 1.0
    ) -> List[Dict[str, Any]]:
        """Return CPU/memory timeseries for a PID over the last N hours."""
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT captured_at, pid, name, cpu_percent, memory_percent, status, insights "
                "FROM process_snapshots "
                "WHERE pid = ? AND captured_at >= ? "
                "ORDER BY captured_at ASC",
                (pid, since),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_anomalies(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent anomaly events."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM anomaly_events ORDER BY occurred_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_top_offenders(
        self, hours: float = 24.0, metric: str = "cpu"
    ) -> List[Dict[str, Any]]:
        """Return processes ranked by average CPU or memory over the time window."""
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        col = "cpu_percent" if metric == "cpu" else "memory_percent"
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT pid, name, AVG({col}) as avg_metric, MAX({col}) as max_metric, "
                f"COUNT(*) as samples "
                f"FROM process_snapshots WHERE captured_at >= ? "
                f"GROUP BY pid, name ORDER BY avg_metric DESC LIMIT 20",
                (since,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def _apply_retention(self, retention_days: int = 7) -> None:
        """Delete records older than retention_days."""
        cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM process_snapshots WHERE captured_at < ?", (cutoff,)
            )
            conn.execute(
                "DELETE FROM anomaly_events WHERE occurred_at < ?", (cutoff,)
            )
            conn.execute(
                "DELETE FROM kill_events WHERE occurred_at < ?", (cutoff,)
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)
