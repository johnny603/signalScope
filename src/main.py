"""SignalScope — entry point.

Usage
-----
    python -m src.main [OPTIONS]

Options
-------
  --interval FLOAT       Refresh interval in seconds (default: 2.0)
  --top INT              Show only the top N processes by CPU usage
  --cpu-threshold FLOAT  CPU % threshold for high-CPU anomaly detection (default: 50.0)
  --mem-threshold FLOAT  Memory % threshold for high-memory anomaly detection (default: 10.0)
  --no-daemon            Disable daemon detection (faster startup)
  --user TEXT            Show only processes owned by this username
  --alert-log FILE       Append anomaly alerts to FILE (CSV-style log)
  --snapshot FILE        Collect once, save top-N processes to FILE (.csv or .json), then exit
  --log-level TEXT       Logging level: DEBUG, INFO, WARNING, ERROR (default: WARNING)
  --db PATH              SQLite database path for metrics persistence
  --retention-days N     Days of metrics history to retain (default: 7)
  --help                 Show this help message and exit.
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List

from src.alert_logger import AlertLogger
from src.collector.process_collector import ProcessCollector
from src.exporter import ProcessExporter
from src.insights.anomaly_detector import AnomalyDetector
from src.insights.daemon_detector import DaemonDetector
from src.insights.memory_detector import MemoryAnomalyDetector
from src.insights.trend_tracker import TrendTracker
from src.insights.zombie_detector import ZombieDetector
from src.models.process import ProcessInfo
from src.storage.metrics_store import MetricsStore
from src.ui.dashboard import Dashboard


def configure_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.WARNING)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="signalscope",
        description="SignalScope — real-time process monitor with intelligent insights",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="Refresh interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        metavar="N",
        help="Display only the top N processes by CPU usage",
    )
    parser.add_argument(
        "--cpu-threshold",
        type=float,
        default=50.0,
        metavar="PCT",
        help="CPU %% threshold for high-CPU anomaly detection (default: 50.0)",
    )
    parser.add_argument(
        "--mem-threshold",
        type=float,
        default=10.0,
        metavar="PCT",
        help="Memory %% threshold for high-memory anomaly detection (default: 10.0)",
    )
    parser.add_argument(
        "--no-daemon",
        action="store_true",
        default=False,
        help="Disable daemon detection",
    )
    parser.add_argument(
        "--user",
        default=None,
        metavar="USERNAME",
        help="Show only processes owned by this username",
    )
    parser.add_argument(
        "--alert-log",
        default=None,
        metavar="FILE",
        help="Append anomaly alerts to FILE (one line per new anomaly)",
    )
    parser.add_argument(
        "--snapshot",
        default=None,
        metavar="FILE",
        help="Save a one-time snapshot of top-N processes to FILE (.csv or .json) and exit",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: WARNING)",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get(
            "SIGNALSCOPE_DB_PATH",
            str(Path.home() / ".signalscope" / "metrics.db"),
        ),
        metavar="PATH",
        help="SQLite database path for metrics persistence",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=7,
        metavar="N",
        help="Days of metrics history to retain (default: 7)",
    )
    return parser.parse_args(argv)


def build_analyze_fn(args: argparse.Namespace):
    """Create a composite analysis function from the configured detectors."""
    zombie_detector = ZombieDetector()
    anomaly_detector = AnomalyDetector(cpu_threshold=args.cpu_threshold)
    memory_detector = MemoryAnomalyDetector(mem_threshold=args.mem_threshold)
    trend_tracker = TrendTracker(cpu_threshold=args.cpu_threshold)
    daemon_detector = DaemonDetector() if not args.no_daemon else None

    def analyze(processes: List[ProcessInfo]) -> None:
        zombie_detector.analyze(processes)
        anomaly_detector.analyze(processes)
        memory_detector.analyze(processes)
        trend_tracker.analyze(processes)
        if daemon_detector is not None:
            daemon_detector.analyze(processes)

    return analyze


def main(argv=None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    collector = ProcessCollector(user=args.user)
    analyze_fn = build_analyze_fn(args)

    # Optionally wrap analyze_fn with alert logging.
    if args.alert_log:
        alert_logger = AlertLogger(args.alert_log)
        _base_analyze = analyze_fn

        def analyze_fn(processes: List[ProcessInfo]) -> None:  # type: ignore[misc]
            _base_analyze(processes)
            alert_logger.log_anomalies(processes)

    # Wrap analyze_fn with MetricsStore persistence.
    if args.db:
        store = MetricsStore(db_path=args.db, retention_days=args.retention_days)
        _prev_analyze = analyze_fn
        _seen_anomalies: set = set()

        def analyze_fn(processes: List[ProcessInfo]) -> None:  # type: ignore[misc]
            _prev_analyze(processes)
            try:
                store.record_snapshot(processes)
                for p in processes:
                    for insight in p.insights:
                        key = (p.pid, insight)
                        if key not in _seen_anomalies:
                            _seen_anomalies.add(key)
                            store.record_anomaly(p.pid, p.name, "insight", insight)
            except Exception as exc:
                logging.getLogger(__name__).debug("MetricsStore error: %s", exc)

    # Snapshot mode: collect once, export, and exit.
    if args.snapshot:
        exporter = ProcessExporter()
        try:
            processes = collector.collect()
            analyze_fn(processes)
            processes = sorted(processes, key=lambda p: p.cpu_percent, reverse=True)
            if args.top is not None:
                processes = processes[: args.top]
            exporter.export(processes, args.snapshot)
        except Exception as exc:
            logging.getLogger(__name__).exception("Snapshot failed: %s", exc)
            return 1
        return 0

    dashboard = Dashboard(
        refresh_interval=args.interval,
        max_processes=args.top,
    )

    try:
        dashboard.run(
            collect_fn=collector.collect,
            analyze_fn=analyze_fn,
        )
    except Exception as exc:
        logging.getLogger(__name__).exception("Fatal error: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

