"""Tests for the UI dashboard helpers."""

from src.models.process import ProcessInfo
from src.ui.dashboard import build_table, _row_style


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

    def test_normal_is_green(self):
        proc = make_proc(cpu_percent=5.0)
        assert _row_style(proc) == "green"

    def test_zombie_takes_priority_over_high_cpu(self):
        proc = make_proc(status="zombie", cpu_percent=99.0)
        assert _row_style(proc) == "bold red"


class TestBuildTable:
    def test_table_has_expected_columns(self):
        table = build_table([make_proc()])
        col_names = [col.header for col in table.columns]
        assert "PID" in col_names
        assert "Name" in col_names
        assert "CPU %" in col_names
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
