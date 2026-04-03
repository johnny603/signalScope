"""Tests for the insight detectors."""

import pytest

from src.models.process import ProcessInfo
from src.insights.zombie_detector import ZombieDetector
from src.insights.anomaly_detector import AnomalyDetector
from src.insights.memory_detector import MemoryAnomalyDetector
from src.insights.trend_tracker import TrendTracker


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
        assert any(AnomalyDetector.INSIGHT_PREFIX in i for i in proc.insights)

    def test_insight_includes_cpu_and_threshold(self):
        proc = make_proc(cpu_percent=78.5)
        AnomalyDetector(cpu_threshold=50.0).analyze([proc])
        assert len(proc.insights) == 1
        assert "78.5%" in proc.insights[0]
        assert "50%" in proc.insights[0]

    def test_ignores_normal_cpu(self):
        proc = make_proc(cpu_percent=20.0)
        AnomalyDetector(cpu_threshold=50.0).analyze([proc])
        assert proc.insights == []

    def test_custom_threshold(self):
        proc = make_proc(cpu_percent=30.0)
        # Threshold lower than cpu_percent → should flag
        AnomalyDetector(cpu_threshold=25.0).analyze([proc])
        assert any(AnomalyDetector.INSIGHT_PREFIX in i for i in proc.insights)

    def test_no_duplicate_insight(self):
        proc = make_proc(cpu_percent=99.0)
        detector = AnomalyDetector(cpu_threshold=50.0)
        detector.analyze([proc])
        detector.analyze([proc])
        assert len(proc.insights) == 1


class TestMemoryAnomalyDetector:
    def test_annotates_high_memory(self):
        proc = make_proc(memory_percent=25.0)
        MemoryAnomalyDetector(mem_threshold=10.0).analyze([proc])
        assert any(MemoryAnomalyDetector.INSIGHT_PREFIX in i for i in proc.insights)

    def test_insight_includes_mem_and_threshold(self):
        proc = make_proc(memory_percent=18.5)
        MemoryAnomalyDetector(mem_threshold=10.0).analyze([proc])
        assert len(proc.insights) == 1
        assert "18.5%" in proc.insights[0]
        assert "10%" in proc.insights[0]

    def test_ignores_normal_memory(self):
        proc = make_proc(memory_percent=5.0)
        MemoryAnomalyDetector(mem_threshold=10.0).analyze([proc])
        assert proc.insights == []

    def test_custom_threshold(self):
        proc = make_proc(memory_percent=8.0)
        MemoryAnomalyDetector(mem_threshold=5.0).analyze([proc])
        assert any(MemoryAnomalyDetector.INSIGHT_PREFIX in i for i in proc.insights)

    def test_no_duplicate_insight(self):
        proc = make_proc(memory_percent=50.0)
        detector = MemoryAnomalyDetector(mem_threshold=10.0)
        detector.analyze([proc])
        detector.analyze([proc])
        assert len(proc.insights) == 1


class TestTrendTracker:
    def test_no_insight_on_first_sample(self):
        proc = make_proc(cpu_percent=90.0)
        tracker = TrendTracker(cpu_threshold=50.0, window_size=4, spike_ratio=0.5)
        tracker.analyze([proc])
        assert proc.insights == []

    def test_flags_recurring_spikes(self):
        # Feed enough high-CPU samples to exceed spike_ratio
        tracker = TrendTracker(cpu_threshold=50.0, window_size=4, spike_ratio=0.5)
        for _ in range(3):
            proc = make_proc(pid=1, cpu_percent=90.0)
            tracker.analyze([proc])
        assert any(TrendTracker.INSIGHT_PREFIX in i for i in proc.insights)

    def test_no_flag_below_spike_ratio(self):
        # Only 1 out of 4 samples is a spike → ratio=0.25 < 0.5 → no flag
        tracker = TrendTracker(cpu_threshold=50.0, window_size=4, spike_ratio=0.5)
        cpus = [90.0, 5.0, 5.0, 5.0]
        for cpu in cpus:
            proc = make_proc(pid=1, cpu_percent=cpu)
            tracker.analyze([proc])
        assert proc.insights == []

    def test_insight_includes_sample_counts(self):
        tracker = TrendTracker(cpu_threshold=50.0, window_size=4, spike_ratio=0.5)
        for _ in range(4):
            proc = make_proc(pid=1, cpu_percent=90.0)
            tracker.analyze([proc])
        insight = next(i for i in proc.insights if TrendTracker.INSIGHT_PREFIX in i)
        assert "4/4" in insight
        assert "50%" in insight

    def test_tracks_separate_pids_independently(self):
        tracker = TrendTracker(cpu_threshold=50.0, window_size=4, spike_ratio=0.5)
        for _ in range(4):
            high = make_proc(pid=1, cpu_percent=90.0)
            low = make_proc(pid=2, cpu_percent=5.0)
            tracker.analyze([high, low])
        assert any(TrendTracker.INSIGHT_PREFIX in i for i in high.insights)
        assert low.insights == []

