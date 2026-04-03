"""Tests for the CLI argument parser and main entry point."""

import pytest

from src.main import parse_args


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.interval == 2.0
        assert args.top is None
        assert args.cpu_threshold == 50.0
        assert args.no_daemon is False
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

    def test_no_daemon_flag(self):
        args = parse_args(["--no-daemon"])
        assert args.no_daemon is True

    def test_log_level_debug(self):
        args = parse_args(["--log-level", "DEBUG"])
        assert args.log_level == "DEBUG"
