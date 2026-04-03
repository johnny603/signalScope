"""Tests for the ProcessExporter (CSV and JSON snapshot export)."""

import csv
import json
import os
import tempfile

import pytest

from src.exporter import ProcessExporter
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


class TestProcessExporterCSV:
    def test_creates_csv_file(self, tmp_path):
        path = str(tmp_path / "snap.csv")
        ProcessExporter().export([make_proc()], path)
        assert os.path.exists(path)

    def test_csv_has_header_row(self, tmp_path):
        path = str(tmp_path / "snap.csv")
        ProcessExporter().export([make_proc()], path)
        with open(path) as f:
            reader = csv.DictReader(f)
            assert set(reader.fieldnames) >= {"pid", "name", "cpu_percent", "memory_percent", "status"}

    def test_csv_row_values(self, tmp_path):
        path = str(tmp_path / "snap.csv")
        proc = make_proc(pid=42, name="myapp", cpu_percent=12.5, memory_percent=3.0, status="running")
        ProcessExporter().export([proc], path)
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["pid"] == "42"
        assert rows[0]["name"] == "myapp"
        assert rows[0]["cpu_percent"] == "12.5"

    def test_csv_exports_all_processes(self, tmp_path):
        path = str(tmp_path / "snap.csv")
        procs = [make_proc(pid=i) for i in range(5)]
        ProcessExporter().export(procs, path)
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 5

    def test_csv_insight_text(self, tmp_path):
        path = str(tmp_path / "snap.csv")
        proc = make_proc()
        proc.add_insight("🔥 High CPU: 90.0%")
        ProcessExporter().export([proc], path)
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert "🔥 High CPU" in rows[0]["insights"]

    def test_unknown_extension_defaults_to_csv(self, tmp_path):
        path = str(tmp_path / "snap.txt")
        ProcessExporter().export([make_proc()], path)
        with open(path) as f:
            reader = csv.DictReader(f)
            assert "pid" in (reader.fieldnames or [])


class TestProcessExporterJSON:
    def test_creates_json_file(self, tmp_path):
        path = str(tmp_path / "snap.json")
        ProcessExporter().export([make_proc()], path)
        assert os.path.exists(path)

    def test_json_has_timestamp(self, tmp_path):
        path = str(tmp_path / "snap.json")
        ProcessExporter().export([make_proc()], path)
        with open(path) as f:
            data = json.load(f)
        assert "timestamp" in data

    def test_json_has_processes_list(self, tmp_path):
        path = str(tmp_path / "snap.json")
        procs = [make_proc(pid=i) for i in range(3)]
        ProcessExporter().export(procs, path)
        with open(path) as f:
            data = json.load(f)
        assert len(data["processes"]) == 3

    def test_json_process_fields(self, tmp_path):
        path = str(tmp_path / "snap.json")
        proc = make_proc(pid=99, name="test", cpu_percent=7.5)
        ProcessExporter().export([proc], path)
        with open(path) as f:
            data = json.load(f)
        row = data["processes"][0]
        assert row["pid"] == 99
        assert row["name"] == "test"
        assert row["cpu_percent"] == 7.5
