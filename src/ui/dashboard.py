"""Rich-based terminal dashboard for SignalScope."""

import logging
import time
from typing import Callable, List, Optional

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich import box

from src.models.process import ProcessInfo

logger = logging.getLogger(__name__)

# CPU % above this value is highlighted red.
HIGH_CPU_THRESHOLD = 50.0


def _row_style(proc: ProcessInfo) -> str:
    """Return the Rich style string for a process row."""
    if proc.is_zombie():
        return "bold red"
    if proc.is_high_cpu(HIGH_CPU_THRESHOLD):
        return "yellow"
    return "green"


def build_table(processes: List[ProcessInfo], title: str = "SignalScope — Process Monitor") -> Table:
    """Build and return a Rich :class:`Table` from a list of processes."""
    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )

    table.add_column("PID", style="dim", width=8, justify="right")
    table.add_column("Name", min_width=16)
    table.add_column("CPU %", width=8, justify="right")
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
