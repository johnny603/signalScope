"""Tests for the process collector."""

from unittest.mock import MagicMock, patch

import pytest

from src.collector.process_collector import ProcessCollector


def _make_mock_proc(pid, name, cpu_percent, memory_percent, status, ppid=1, username="root"):
    proc = MagicMock()
    proc.info = {
        "pid": pid,
        "name": name,
        "cpu_percent": cpu_percent,
        "memory_percent": memory_percent,
        "status": status,
        "ppid": ppid,
        "username": username,
    }
    return proc


class TestProcessCollector:
    def test_returns_list_of_process_info(self):
        mock_procs = [
            _make_mock_proc(1, "init", 0.0, 0.1, "sleeping"),
            _make_mock_proc(42, "python", 15.3, 2.0, "running"),
        ]
        with patch("src.collector.process_collector.psutil.process_iter", return_value=mock_procs):
            collector = ProcessCollector()
            result = collector.collect()

        assert len(result) == 2
        assert result[0].pid == 1
        assert result[0].name == "init"
        assert result[1].cpu_percent == 15.3

    def test_skips_vanished_processes(self):
        import psutil
        from unittest.mock import PropertyMock

        bad_proc = MagicMock()
        type(bad_proc).info = PropertyMock(side_effect=psutil.NoSuchProcess(pid=999))

        good_proc = _make_mock_proc(2, "good", 1.0, 0.5, "running")

        with patch("src.collector.process_collector.psutil.process_iter", return_value=[bad_proc, good_proc]):
            collector = ProcessCollector()
            result = collector.collect()

        assert len(result) == 1
        assert result[0].pid == 2

    def test_empty_when_no_processes(self):
        with patch("src.collector.process_collector.psutil.process_iter", return_value=[]):
            collector = ProcessCollector()
            result = collector.collect()
        assert result == []

    def test_user_filter_returns_only_matching_user(self):
        mock_procs = [
            _make_mock_proc(1, "init", 0.0, 0.1, "sleeping", username="root"),
            _make_mock_proc(2, "myapp", 5.0, 1.0, "running", username="alice"),
            _make_mock_proc(3, "other", 1.0, 0.5, "sleeping", username="bob"),
        ]
        with patch("src.collector.process_collector.psutil.process_iter", return_value=mock_procs):
            collector = ProcessCollector(user="alice")
            result = collector.collect()

        assert len(result) == 1
        assert result[0].pid == 2

    def test_user_filter_none_returns_all(self):
        mock_procs = [
            _make_mock_proc(1, "init", 0.0, 0.1, "sleeping", username="root"),
            _make_mock_proc(2, "myapp", 5.0, 1.0, "running", username="alice"),
        ]
        with patch("src.collector.process_collector.psutil.process_iter", return_value=mock_procs):
            collector = ProcessCollector(user=None)
            result = collector.collect()

        assert len(result) == 2
