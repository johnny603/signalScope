"""Tests for data models."""

import pytest

from src.models.process import ProcessInfo


def make_proc(**kwargs) -> ProcessInfo:
    defaults = dict(
        pid=1234,
        name="test_proc",
        cpu_percent=0.0,
        memory_percent=0.5,
        status="running",
        ppid=1,
    )
    defaults.update(kwargs)
    return ProcessInfo(**defaults)


class TestProcessInfo:
    def test_is_zombie_true(self):
        proc = make_proc(status="zombie")
        assert proc.is_zombie() is True

    def test_is_zombie_false(self):
        proc = make_proc(status="sleeping")
        assert proc.is_zombie() is False

    def test_is_high_cpu_above_threshold(self):
        proc = make_proc(cpu_percent=75.0)
        assert proc.is_high_cpu(50.0) is True

    def test_is_high_cpu_at_threshold(self):
        proc = make_proc(cpu_percent=50.0)
        assert proc.is_high_cpu(50.0) is False

    def test_is_high_cpu_below_threshold(self):
        proc = make_proc(cpu_percent=10.0)
        assert proc.is_high_cpu(50.0) is False

    def test_add_insight_deduplication(self):
        proc = make_proc()
        proc.add_insight("foo")
        proc.add_insight("foo")
        assert proc.insights == ["foo"]

    def test_insight_text_empty(self):
        proc = make_proc()
        assert proc.insight_text == "—"

    def test_insight_text_multiple(self):
        proc = make_proc()
        proc.add_insight("A")
        proc.add_insight("B")
        assert proc.insight_text == "A, B"
