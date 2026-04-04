import json
import sqlite3
from datetime import datetime, timedelta

import pytest

from src.models.process import ProcessInfo
from src.storage.metrics_store import MetricsStore


def make_proc(**kwargs) -> ProcessInfo:
    defaults = dict(
        pid=100,
        name="proc",
        cpu_percent=10.0,
        memory_percent=1.0,
        status="running",
        ppid=1,
        insights=[],
    )
    defaults.update(kwargs)
    return ProcessInfo(**defaults)


@pytest.fixture
def store(tmp_path):
    db = str(tmp_path / "test.db")
    return MetricsStore(db_path=db)


class TestMetricsStore:
    def test_record_snapshot(self, store):
        procs = [make_proc(pid=1, name="a"), make_proc(pid=2, name="b")]
        store.record_snapshot(procs)
        history = store.get_process_history(1, hours=1)
        assert len(history) == 1
        assert history[0]["pid"] == 1

    def test_record_anomaly(self, store):
        store.record_anomaly(1, "proc", "high_cpu", "CPU at 90%")
        anomalies = store.get_recent_anomalies(limit=10)
        assert len(anomalies) == 1
        assert anomalies[0]["event_type"] == "high_cpu"

    def test_get_top_offenders_cpu(self, store):
        store.record_snapshot([make_proc(pid=1, name="heavy", cpu_percent=80.0)])
        store.record_snapshot([make_proc(pid=1, name="heavy", cpu_percent=90.0)])
        store.record_snapshot([make_proc(pid=2, name="light", cpu_percent=5.0)])
        top = store.get_top_offenders(hours=1, metric="cpu")
        assert top[0]["name"] == "heavy"

    def test_record_kill(self, store):
        from src.actions.process_killer import ActionResult

        result = ActionResult(
            pid=123,
            signal_sent="SIGTERM",
            success=True,
            message="ok",
            timestamp=datetime.utcnow().isoformat(),
            process_name="testproc",
        )
        store.record_kill(result)
        # Verify no exception; kill_events not exposed as API yet

    def test_retention_policy(self, store, tmp_path):
        old_time = (datetime.utcnow() - timedelta(days=10)).isoformat()
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute(
            "INSERT INTO process_snapshots "
            "(captured_at, pid, name, cpu_percent, memory_percent, status, insights) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (old_time, 999, "old_proc", 1.0, 0.1, "running", "[]"),
        )
        conn.commit()
        conn.close()
        store._apply_retention(retention_days=7)
        history = store.get_process_history(999, hours=24 * 365)
        assert len(history) == 0

    def test_empty_history(self, store):
        assert store.get_process_history(99999, hours=1) == []

    def test_get_recent_anomalies_empty(self, store):
        assert store.get_recent_anomalies() == []
