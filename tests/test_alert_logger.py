"""Tests for the AlertLogger anomaly event logger."""

import logging
import os

import pytest

from src.alert_logger import AlertLogger
from src.models.process import ProcessInfo


def make_proc(**kwargs) -> ProcessInfo:
    defaults = dict(
        pid=1,
        name="proc",
        cpu_percent=5.0,
        memory_percent=1.0,
        status="running",
        ppid=0,
    )
    defaults.update(kwargs)
    return ProcessInfo(**defaults)


class TestAlertLogger:
    def test_creates_log_file(self, tmp_path):
        path = str(tmp_path / "alerts.log")
        alert_logger = AlertLogger(path)
        proc = make_proc()
        proc.add_insight("🔥 High CPU: 90.0%")
        alert_logger.log_anomalies([proc])
        assert os.path.exists(path)

    def test_logs_insight_to_file(self, tmp_path):
        path = str(tmp_path / "alerts.log")
        alert_logger = AlertLogger(path)
        proc = make_proc(pid=42, name="myapp", cpu_percent=90.0)
        proc.add_insight("🔥 High CPU: 90.0% (above 50% threshold)")
        alert_logger.log_anomalies([proc])
        content = open(path).read()
        assert "42" in content
        assert "myapp" in content
        assert "🔥 High CPU" in content

    def test_no_log_when_no_insights(self, tmp_path):
        path = str(tmp_path / "alerts.log")
        alert_logger = AlertLogger(path)
        proc = make_proc()
        alert_logger.log_anomalies([proc])
        # File may not exist or be empty
        if os.path.exists(path):
            assert open(path).read().strip() == ""

    def test_deduplication_same_insight_not_logged_twice(self, tmp_path):
        path = str(tmp_path / "alerts.log")
        alert_logger = AlertLogger(path)
        proc = make_proc(pid=1)
        proc.add_insight("🔥 High CPU: 90.0%")
        alert_logger.log_anomalies([proc])
        alert_logger.log_anomalies([proc])
        content = open(path).read()
        assert content.count("🔥 High CPU") == 1

    def test_different_insights_both_logged(self, tmp_path):
        path = str(tmp_path / "alerts.log")
        alert_logger = AlertLogger(path)
        proc = make_proc(pid=1)
        proc.add_insight("🔥 High CPU: 90.0%")
        proc.add_insight("🧠 High Memory: 15.0%")
        alert_logger.log_anomalies([proc])
        content = open(path).read()
        assert "🔥 High CPU" in content
        assert "🧠 High Memory" in content

    def test_different_pids_same_insight_both_logged(self, tmp_path):
        path = str(tmp_path / "alerts.log")
        alert_logger = AlertLogger(path)
        proc1 = make_proc(pid=1)
        proc1.add_insight("🔥 High CPU: 90.0%")
        proc2 = make_proc(pid=2)
        proc2.add_insight("🔥 High CPU: 90.0%")
        alert_logger.log_anomalies([proc1, proc2])
        content = open(path).read()
        assert content.count("🔥 High CPU") == 2
