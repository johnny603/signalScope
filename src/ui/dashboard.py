"""Rich-based terminal dashboard for SignalScope."""

import logging
import time
from typing import Callable, List, Optional

import psutil
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich import box

from src.models.process import ProcessInfo

logger = logging.getLogger(__name__)

# CPU % above this value is highlighted yellow; zombie rows are bold red.
HIGH_CPU_THRESHOLD = 50.0
# CPU % below this value gets a dim style to reduce visual noise.
DIM_CPU_THRESHOLD = 0.1


def _row_style(proc: ProcessInfo) -> str:
    """Return the Rich style string for a process row.

    Only anomalies receive a colour; idle processes are dimmed; normal
    processes carry no style so they blend into the terminal's default look.
    """
    if proc.is_zombie():
        return "bold red"
    if proc.is_high_cpu(HIGH_CPU_THRESHOLD):
        return "yellow"
    if any("🧠 High Memory" in i for i in proc.insights):
        return "magenta"
    if proc.cpu_percent < DIM_CPU_THRESHOLD:
        return "dim"
    return ""


def _system_summary() -> str:
    """Return a one-line string with overall CPU and memory usage."""
    try:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        return (
            f"System  CPU: {cpu:.1f}%  |  "
            f"RAM: {mem.percent:.1f}% used ({mem.used // (1024 ** 2):,} / {mem.total // (1024 ** 2):,} MB)"
        )
    except Exception:
        return ""


def _anomaly_summary(processes: List[ProcessInfo]) -> str:
    """Return a compact count of notable process categories."""
    total = len(processes)
    zombies = sum(1 for p in processes if p.is_zombie())
    high_cpu = sum(1 for p in processes if any("🔥" in i for i in p.insights))
    high_mem = sum(1 for p in processes if any("🧠" in i for i in p.insights))
    trends = sum(1 for p in processes if any("📈" in i for i in p.insights))

    parts = [f"Processes: {total}"]
    if zombies:
        parts.append(f"👻 Zombies: {zombies}")
    if high_cpu:
        parts.append(f"🔥 High CPU: {high_cpu}")
    if high_mem:
        parts.append(f"🧠 High Mem: {high_mem}")
    if trends:
        parts.append(f"📈 Trends: {trends}")
    return "  |  ".join(parts)


def build_table(processes: List[ProcessInfo], title: str = "SignalScope — Process Monitor") -> Table:
    """Build and return a Rich :class:`Table` from a list of processes."""
    summary = _system_summary()
    anomaly_line = _anomaly_summary(processes)
    subtitle_parts = []
    if summary:
        subtitle_parts.append(summary)
    if anomaly_line:
        subtitle_parts.append(anomaly_line)
    full_title = title
    if subtitle_parts:
        full_title = title + "\n" + "  |  ".join(f"[dim]{p}[/dim]" for p in subtitle_parts)

    table = Table(
        title=full_title,
        caption="[dim]Press Ctrl+C to exit[/dim]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )

    table.add_column("PID", style="dim", width=8, justify="right")
    table.add_column("Name", min_width=16)
    table.add_column("CPU % ↓", width=9, justify="right")
    table.add_column("Mem %", width=8, justify="right")
    table.add_column("Status", width=12)
    table.add_column("Insight", min_width=20)

    for proc in processes:
        style = _row_style(proc)
        table.add_row(
            str(proc.pid),
            proc.name,
            f"{proc.cpu_percent:.1f}",
            f"{proc.memory_percent:.2f}",
            proc.status,
            proc.insight_text,
            style=style,
        )

    return table


class Dashboard:
    """Renders the SignalScope live dashboard in the terminal.

    Parameters
    ----------
    refresh_interval:
        Seconds between data refreshes (default: 2).
    max_processes:
        If set, only the top *n* processes by CPU usage are displayed.
    """

    def __init__(
        self,
        refresh_interval: float = 2.0,
        max_processes: Optional[int] = None,
    ) -> None:
        self.refresh_interval = refresh_interval
        self.max_processes = max_processes
        self._console = Console()

    def _prepare(self, processes: List[ProcessInfo]) -> List[ProcessInfo]:
        """Sort and optionally truncate the process list."""
        sorted_procs = sorted(processes, key=lambda p: p.cpu_percent, reverse=True)
        if self.max_processes is not None:
            sorted_procs = sorted_procs[: self.max_processes]
        return sorted_procs

    def run(self, collect_fn: "Callable[[], List[ProcessInfo]]", analyze_fn: "Callable[[List[ProcessInfo]], None]") -> None:
        """Start the live-updating dashboard loop.

        Parameters
        ----------
        collect_fn:
            Callable that returns a fresh list of :class:`ProcessInfo` objects.
        analyze_fn:
            Callable that accepts a list of :class:`ProcessInfo` and annotates
            them with insights in-place.
        """
        logger.info("Dashboard started (refresh=%.1fs)", self.refresh_interval)

        with Live(console=self._console, refresh_per_second=4, screen=True) as live:
            while True:
                try:
                    processes = collect_fn()
                    analyze_fn(processes)
                    display = self._prepare(processes)
                    live.update(build_table(display))
                    time.sleep(self.refresh_interval)
                except KeyboardInterrupt:
                    break

        logger.info("Dashboard stopped.")


