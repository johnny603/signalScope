"""Tests for the UI dashboard helpers."""

from src.models.process import ProcessInfo
from src.ui.dashboard import build_table, _row_style, _anomaly_summary


def make_proc(**kwargs) -> ProcessInfo:
    defaults = dict(
        pid=1,
        name="proc",
        cpu_percent=0.0,
        memory_percent=0.0,
        status="running",
        ppid=0,
    )
    defaults.update(kwargs)
    return ProcessInfo(**defaults)


class TestRowStyle:
    def test_zombie_is_red(self):
        proc = make_proc(status="zombie")
        assert _row_style(proc) == "bold red"

    def test_high_cpu_is_yellow(self):
        proc = make_proc(cpu_percent=80.0)
        assert _row_style(proc) == "yellow"

    def test_normal_has_no_style(self):
        proc = make_proc(cpu_percent=5.0)
        assert _row_style(proc) == ""

    def test_idle_is_dim(self):
        proc = make_proc(cpu_percent=0.0)
        assert _row_style(proc) == "dim"

    def test_zombie_takes_priority_over_high_cpu(self):
        proc = make_proc(status="zombie", cpu_percent=99.0)
        assert _row_style(proc) == "bold red"

    def test_high_memory_is_magenta(self):
        proc = make_proc(cpu_percent=2.0)
        proc.add_insight("🧠 High Memory: 15.0% (above 10% threshold)")
        assert _row_style(proc) == "magenta"

    def test_high_cpu_takes_priority_over_high_memory(self):
        proc = make_proc(cpu_percent=80.0)
        proc.add_insight("🧠 High Memory: 15.0% (above 10% threshold)")
        assert _row_style(proc) == "yellow"


class TestBuildTable:
    def test_table_has_expected_columns(self):
        table = build_table([make_proc()])
        col_names = [col.header for col in table.columns]
        assert "PID" in col_names
        assert "Name" in col_names
        assert "CPU % ↓" in col_names
        assert "Mem %" in col_names
        assert "Status" in col_names
        assert "Insight" in col_names

    def test_table_has_correct_row_count(self):
        procs = [make_proc(pid=i) for i in range(5)]
        table = build_table(procs)
        assert table.row_count == 5

    def test_empty_process_list(self):
        table = build_table([])
        assert table.row_count == 0


class TestAnomalySummary:
    def test_shows_total_process_count(self):
        procs = [make_proc(pid=i) for i in range(3)]
        summary = _anomaly_summary(procs)
        assert "Processes: 3" in summary

    def test_shows_zombie_count(self):
        procs = [make_proc(status="zombie"), make_proc(status="running")]
        summary = _anomaly_summary(procs)
        assert "👻 Zombies: 1" in summary

    def test_shows_high_cpu_count(self):
        proc = make_proc()
        proc.add_insight("🔥 High CPU: 90.0% (above 50% threshold)")
        summary = _anomaly_summary([proc, make_proc(pid=2)])
        assert "🔥 High CPU: 1" in summary

    def test_shows_high_mem_count(self):
        proc = make_proc()
        proc.add_insight("🧠 High Memory: 15.0% (above 10% threshold)")
        summary = _anomaly_summary([proc])
        assert "🧠 High Mem: 1" in summary

    def test_shows_trend_count(self):
        proc = make_proc()
        proc.add_insight("📈 CPU Spike Trend: 3/4 samples exceeded 50%")
        summary = _anomaly_summary([proc])
        assert "📈 Trends: 1" in summary

    def test_no_anomaly_labels_when_clean(self):
        procs = [make_proc(pid=i, cpu_percent=5.0) for i in range(2)]
        summary = _anomaly_summary(procs)
        assert "Zombies" not in summary
        assert "High CPU" not in summary

