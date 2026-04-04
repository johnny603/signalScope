"""Tests for src.actions.process_killer."""

import signal
import time
from unittest.mock import MagicMock, patch

import pytest

from src.actions.process_killer import ActionResult, ProcessKiller


class TestProcessKiller:
    def test_sigterm_nonexistent_pid(self):
        with patch("psutil.pid_exists", return_value=False):
            result = ProcessKiller().send_sigterm(99999)
        assert not result.success
        assert "does not exist" in result.message.lower() or "not found" in result.message.lower()

    def test_sigterm_zombie(self):
        mock_proc = MagicMock()
        mock_proc.status.return_value = "zombie"
        mock_proc.ppid.return_value = 100
        mock_proc.name.return_value = "defunct"
        with patch("psutil.pid_exists", return_value=True), \
             patch("psutil.Process", return_value=mock_proc):
            result = ProcessKiller().send_sigterm(200)
        assert not result.success
        assert "zombie" in result.message.lower()
        assert "100" in result.message

    def test_sigterm_success(self):
        mock_proc = MagicMock()
        mock_proc.status.return_value = "running"
        mock_proc.name.return_value = "myproc"
        mock_proc.ppid.return_value = 1
        mock_proc.uids.return_value = MagicMock(real=1000)
        mock_proc.terminal.return_value = "/dev/pts/0"
        mock_proc.create_time.return_value = time.time()
        with patch("psutil.pid_exists", return_value=True), \
             patch("psutil.Process", return_value=mock_proc), \
             patch("os.kill") as mock_kill:
            result = ProcessKiller().send_sigterm(123)
        mock_kill.assert_called_once_with(123, signal.SIGTERM)
        assert result.success
        assert result.signal_sent == "SIGTERM"
        assert result.process_name == "myproc"

    def test_sigkill_success(self):
        mock_proc = MagicMock()
        mock_proc.status.return_value = "running"
        mock_proc.name.return_value = "myproc"
        mock_proc.ppid.return_value = 1
        mock_proc.uids.return_value = MagicMock(real=1000)
        mock_proc.terminal.return_value = "/dev/pts/0"
        mock_proc.create_time.return_value = time.time()
        with patch("psutil.pid_exists", return_value=True), \
             patch("psutil.Process", return_value=mock_proc), \
             patch("os.kill") as mock_kill:
            result = ProcessKiller().send_sigkill(123)
        mock_kill.assert_called_once_with(123, signal.SIGKILL)
        assert result.success
        assert result.signal_sent == "SIGKILL"

    def test_sigkill_permission_denied(self):
        mock_proc = MagicMock()
        mock_proc.status.return_value = "running"
        mock_proc.name.return_value = "root_proc"
        mock_proc.ppid.return_value = 1
        mock_proc.uids.return_value = MagicMock(real=0)
        mock_proc.terminal.return_value = None
        mock_proc.create_time.return_value = time.time() - 7200
        with patch("psutil.pid_exists", return_value=True), \
             patch("psutil.Process", return_value=mock_proc), \
             patch("os.kill", side_effect=PermissionError()):
            result = ProcessKiller().send_sigkill(1)
        assert not result.success
        assert "permission" in result.message.lower()

    def test_process_lookup_error(self):
        mock_proc = MagicMock()
        mock_proc.status.return_value = "running"
        mock_proc.name.return_value = "gone"
        mock_proc.ppid.return_value = 1
        mock_proc.uids.return_value = MagicMock(real=1000)
        mock_proc.terminal.return_value = "/dev/pts/0"
        mock_proc.create_time.return_value = time.time()
        with patch("psutil.pid_exists", return_value=True), \
             patch("psutil.Process", return_value=mock_proc), \
             patch("os.kill", side_effect=ProcessLookupError()):
            result = ProcessKiller().send_sigterm(999)
        assert not result.success
        assert "no longer exists" in result.message.lower()

    def test_high_risk_detection_uid_zero(self):
        mock_proc = MagicMock()
        mock_proc.status.return_value = "running"
        mock_proc.name.return_value = "daemon"
        mock_proc.ppid.return_value = 1
        mock_proc.uids.return_value = MagicMock(real=0)
        mock_proc.terminal.return_value = None
        mock_proc.create_time.return_value = time.time() - 7200
        with patch("psutil.pid_exists", return_value=True), \
             patch("psutil.Process", return_value=mock_proc), \
             patch("os.kill"):
            result = ProcessKiller().send_sigterm(1)
        assert result.high_risk is True

    def test_high_risk_detection_no_tty_long_running(self):
        mock_proc = MagicMock()
        mock_proc.status.return_value = "running"
        mock_proc.name.return_value = "longdaemon"
        mock_proc.ppid.return_value = 1
        mock_proc.uids.return_value = MagicMock(real=1000)
        mock_proc.terminal.return_value = None
        mock_proc.create_time.return_value = time.time() - 7200  # 2 hours old, no tty
        with patch("psutil.pid_exists", return_value=True), \
             patch("psutil.Process", return_value=mock_proc), \
             patch("os.kill"):
            result = ProcessKiller().send_sigterm(500)
        assert result.high_risk is True

    def test_not_high_risk_with_tty(self):
        mock_proc = MagicMock()
        mock_proc.status.return_value = "running"
        mock_proc.name.return_value = "shell"
        mock_proc.ppid.return_value = 1
        mock_proc.uids.return_value = MagicMock(real=1000)
        mock_proc.terminal.return_value = "/dev/pts/1"
        mock_proc.create_time.return_value = time.time() - 7200
        with patch("psutil.pid_exists", return_value=True), \
             patch("psutil.Process", return_value=mock_proc), \
             patch("os.kill"):
            result = ProcessKiller().send_sigterm(600)
        assert result.high_risk is False

    def test_action_result_fields(self):
        mock_proc = MagicMock()
        mock_proc.status.return_value = "running"
        mock_proc.name.return_value = "testproc"
        mock_proc.ppid.return_value = 1
        mock_proc.uids.return_value = MagicMock(real=1000)
        mock_proc.terminal.return_value = "/dev/pts/0"
        mock_proc.create_time.return_value = time.time()
        with patch("psutil.pid_exists", return_value=True), \
             patch("psutil.Process", return_value=mock_proc), \
             patch("os.kill"):
            result = ProcessKiller().send_sigterm(42)
        assert isinstance(result, ActionResult)
        assert result.pid == 42
        assert result.signal_sent == "SIGTERM"
        assert result.timestamp  # ISO string present
        assert result.process_name == "testproc"

    def test_audit_log_written(self, tmp_path):
        log_file = str(tmp_path / "test_audit.log")
        mock_proc = MagicMock()
        mock_proc.status.return_value = "running"
        mock_proc.name.return_value = "auditproc"
        mock_proc.ppid.return_value = 1
        mock_proc.uids.return_value = MagicMock(real=1000)
        mock_proc.terminal.return_value = "/dev/pts/0"
        mock_proc.create_time.return_value = time.time()
        with patch("psutil.pid_exists", return_value=True), \
             patch("psutil.Process", return_value=mock_proc), \
             patch("os.kill"):
            ProcessKiller(audit_log_path=log_file).send_sigterm(77)
        with open(log_file) as f:
            content = f.read()
        assert "77" in content
        assert "SIGTERM" in content
        assert "auditproc" in content
