"""Tests for the insight detectors."""

import pytest

from src.models.process import ProcessInfo
from src.insights.zombie_detector import ZombieDetector
from src.insights.anomaly_detector import AnomalyDetector


def make_proc(**kwargs) -> ProcessInfo:
    defaults = dict(
        pid=100,
        name="proc",
        cpu_percent=0.0,
        memory_percent=0.1,
        status="running",
        ppid=1,
    )
    defaults.update(kwargs)
    return ProcessInfo(**defaults)


class TestZombieDetector:
    def test_annotates_zombie(self):
        proc = make_proc(status="zombie")
        detector = ZombieDetector()
        detector.analyze([proc])
        assert ZombieDetector.INSIGHT in proc.insights

    def test_ignores_running(self):
        proc = make_proc(status="running")
        ZombieDetector().analyze([proc])
        assert proc.insights == []

    def test_multiple_processes(self):
        procs = [
            make_proc(pid=1, status="zombie"),
            make_proc(pid=2, status="running"),
            make_proc(pid=3, status="zombie"),
        ]
        ZombieDetector().analyze(procs)
        assert ZombieDetector.INSIGHT in procs[0].insights
        assert procs[1].insights == []
        assert ZombieDetector.INSIGHT in procs[2].insights


class TestAnomalyDetector:
    def test_annotates_high_cpu(self):
        proc = make_proc(cpu_percent=90.0)
        AnomalyDetector(cpu_threshold=50.0).analyze([proc])
        assert AnomalyDetector.INSIGHT in proc.insights

    def test_ignores_normal_cpu(self):
        proc = make_proc(cpu_percent=20.0)
        AnomalyDetector(cpu_threshold=50.0).analyze([proc])
        assert proc.insights == []

    def test_custom_threshold(self):
        proc = make_proc(cpu_percent=30.0)
        # Threshold lower than cpu_percent → should flag
        AnomalyDetector(cpu_threshold=25.0).analyze([proc])
        assert AnomalyDetector.INSIGHT in proc.insights

    def test_no_duplicate_insight(self):
        proc = make_proc(cpu_percent=99.0)
        detector = AnomalyDetector(cpu_threshold=50.0)
        detector.analyze([proc])
        detector.analyze([proc])
        assert proc.insights.count(AnomalyDetector.INSIGHT) == 1
