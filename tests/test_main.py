"""Tests for the CLI argument parser and main entry point."""

import pytest

from src.main import parse_args


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.interval == 2.0
        assert args.top is None
        assert args.cpu_threshold == 50.0
        assert args.mem_threshold == 10.0
        assert args.no_daemon is False
        assert args.user is None
        assert args.alert_log is None
        assert args.snapshot is None
        assert args.log_level == "WARNING"

    def test_custom_interval(self):
        args = parse_args(["--interval", "1.5"])
        assert args.interval == 1.5

    def test_top_processes(self):
        args = parse_args(["--top", "10"])
        assert args.top == 10

    def test_cpu_threshold(self):
        args = parse_args(["--cpu-threshold", "75.0"])
        assert args.cpu_threshold == 75.0

    def test_mem_threshold(self):
        args = parse_args(["--mem-threshold", "20.0"])
        assert args.mem_threshold == 20.0

    def test_no_daemon_flag(self):
        args = parse_args(["--no-daemon"])
        assert args.no_daemon is True

    def test_user_filter(self):
        args = parse_args(["--user", "alice"])
        assert args.user == "alice"

    def test_alert_log(self):
        args = parse_args(["--alert-log", "/tmp/alerts.log"])
        assert args.alert_log == "/tmp/alerts.log"

    def test_snapshot(self):
        args = parse_args(["--snapshot", "/tmp/snap.json"])
        assert args.snapshot == "/tmp/snap.json"

    def test_log_level_debug(self):
        args = parse_args(["--log-level", "DEBUG"])
        assert args.log_level == "DEBUG"

