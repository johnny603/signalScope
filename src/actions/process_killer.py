"""Process kill / signal action layer for SignalScope."""

import getpass
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import psutil

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ActionResult:
    pid: int
    signal_sent: str
    success: bool
    message: str
    timestamp: str  # ISO format
    high_risk: bool = False
    process_name: str = ""


# ---------------------------------------------------------------------------
# ProcessKiller
# ---------------------------------------------------------------------------


class ProcessKiller:
    """Send SIGTERM or SIGKILL to a process with safety checks and audit logging."""

    def __init__(self, audit_log_path: str = "kill_audit.log") -> None:
        self._audit_log_path = audit_log_path
        self._audit_logger = self._setup_audit_logger(audit_log_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_sigterm(self, pid: int) -> ActionResult:
        """Send SIGTERM to *pid*."""
        return self._send_signal(pid, signal.SIGTERM, "SIGTERM")

    def send_sigkill(self, pid: int) -> ActionResult:
        """Send SIGKILL to *pid*."""
        return self._send_signal(pid, signal.SIGKILL, "SIGKILL")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send_signal(self, pid: int, sig: signal.Signals, sig_name: str) -> ActionResult:
        ts = datetime.now(timezone.utc).isoformat()

        # 1. Check the PID exists at all.
        if not psutil.pid_exists(pid):
            result = ActionResult(
                pid=pid,
                signal_sent=sig_name,
                success=False,
                message=f"PID {pid} does not exist",
                timestamp=ts,
            )
            self._audit(result)
            return result

        # 2. Inspect the process.
        try:
            proc = psutil.Process(pid)
            status = proc.status()
            ppid = proc.ppid()
            name = proc.name()
        except psutil.NoSuchProcess:
            result = ActionResult(
                pid=pid,
                signal_sent=sig_name,
                success=False,
                message=f"Process {pid} no longer exists",
                timestamp=ts,
            )
            self._audit(result)
            return result

        # Zombie check — do NOT send the signal.
        if status == "zombie":
            result = ActionResult(
                pid=pid,
                signal_sent=sig_name,
                success=False,
                message=f"This is a zombie process. Kill parent PID {ppid} instead.",
                timestamp=ts,
                process_name=name,
            )
            self._audit(result)
            return result

        # 3. High-risk detection.
        high_risk = self._is_high_risk(proc)

        # 4. Send the signal.
        try:
            os.kill(pid, sig)
        except PermissionError:
            result = ActionResult(
                pid=pid,
                signal_sent=sig_name,
                success=False,
                message=f"Permission denied: cannot signal PID {pid}",
                timestamp=ts,
                high_risk=high_risk,
                process_name=name,
            )
            self._audit(result)
            return result
        except ProcessLookupError:
            result = ActionResult(
                pid=pid,
                signal_sent=sig_name,
                success=False,
                message=f"Process {pid} no longer exists",
                timestamp=ts,
                high_risk=high_risk,
                process_name=name,
            )
            self._audit(result)
            return result
        except Exception as exc:  # noqa: BLE001
            result = ActionResult(
                pid=pid,
                signal_sent=sig_name,
                success=False,
                message=f"Unexpected error signalling PID {pid}: {exc}",
                timestamp=ts,
                high_risk=high_risk,
                process_name=name,
            )
            self._audit(result)
            return result

        result = ActionResult(
            pid=pid,
            signal_sent=sig_name,
            success=True,
            message=f"Signal {sig_name} sent to PID {pid} ({name})",
            timestamp=ts,
            high_risk=high_risk,
            process_name=name,
        )
        self._audit(result)
        return result

    # ------------------------------------------------------------------

    @staticmethod
    def _is_high_risk(proc: psutil.Process) -> bool:
        """Return True if the process looks like a privileged / long-running daemon."""
        try:
            if proc.uids().real == 0:
                return True
            terminal = proc.terminal()
            create_time = proc.create_time()
            if terminal is None and (time.time() - create_time) > 3600:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return False

    # ------------------------------------------------------------------

    @staticmethod
    def _setup_audit_logger(path: str) -> logging.Logger:
        """Return a logger that writes to *path* (file handler added once)."""
        audit_logger = logging.getLogger(f"signalscope.kill_audit.{path}")
        audit_logger.setLevel(logging.INFO)
        # Only add a handler if none exist yet (avoid duplicate lines).
        if not audit_logger.handlers:
            fh = logging.FileHandler(path, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(message)s"))
            audit_logger.addHandler(fh)
            audit_logger.propagate = False
        return audit_logger

    def _audit(self, result: ActionResult) -> None:
        """Write one line to the kill audit log."""
        try:
            user = getpass.getuser()
        except Exception:
            user = "unknown"
        self._audit_logger.info(
            "%s | %s | %s | %s | %s | %s",
            result.timestamp,
            result.pid,
            result.process_name,
            result.signal_sent,
            result.success,
            user,
        )
