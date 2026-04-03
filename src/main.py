"""SignalScope — entry point.

Usage
-----
    python -m src.main [OPTIONS]

Options
-------
  --interval FLOAT     Refresh interval in seconds (default: 2.0)
  --top INT            Show only the top N processes by CPU usage
  --cpu-threshold FLOAT  CPU % threshold for anomaly detection (default: 50.0)
  --no-daemon          Disable daemon detection (faster startup)
  --log-level TEXT     Logging level: DEBUG, INFO, WARNING, ERROR (default: WARNING)
  --help               Show this help message and exit.
"""

import argparse
import logging
import sys
from typing import List

from src.collector.process_collector import ProcessCollector
from src.insights.anomaly_detector import AnomalyDetector
from src.insights.daemon_detector import DaemonDetector
from src.insights.zombie_detector import ZombieDetector
from src.models.process import ProcessInfo
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
        "--no-daemon",
        action="store_true",
        default=False,
        help="Disable daemon detection",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: WARNING)",
    )
    return parser.parse_args(argv)


def build_analyze_fn(args: argparse.Namespace):
    """Create a composite analysis function from the configured detectors."""
    zombie_detector = ZombieDetector()
    anomaly_detector = AnomalyDetector(cpu_threshold=args.cpu_threshold)
    daemon_detector = DaemonDetector() if not args.no_daemon else None

    def analyze(processes: List[ProcessInfo]) -> None:
        zombie_detector.analyze(processes)
        anomaly_detector.analyze(processes)
        if daemon_detector is not None:
            daemon_detector.analyze(processes)

    return analyze


def main(argv=None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    collector = ProcessCollector()
    dashboard = Dashboard(
        refresh_interval=args.interval,
        max_processes=args.top,
    )
    analyze_fn = build_analyze_fn(args)

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
