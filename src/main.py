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
  --slack-webhook URL    Slack Incoming Webhook URL for anomaly notifications
  --webhook-url URL      Generic webhook URL for anomaly notifications
  --notify-cooldown N    Seconds between repeat notifications for same (pid, event) (default: 300)
  --mode MODE            Run mode: dashboard, agent, collector (default: dashboard)
  --collector-url URL    Collector URL for agent mode
  --agent-id UUID        Agent ID (auto-generated if not set)
  --agent-secret STR     Shared secret for agent/collector authentication
  --help                 Show this help message and exit.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
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
    parser.add_argument(
        "--slack-webhook",
        default=os.environ.get("SIGNALSCOPE_SLACK_WEBHOOK_URL", ""),
        metavar="URL",
        help="Slack Incoming Webhook URL for anomaly notifications",
    )
    parser.add_argument(
        "--webhook-url",
        default=os.environ.get("SIGNALSCOPE_WEBHOOK_URL", ""),
        metavar="URL",
        help="Generic webhook URL for anomaly notifications",
    )
    parser.add_argument(
        "--notify-cooldown",
        type=int,
        default=int(os.environ.get("SIGNALSCOPE_NOTIFY_COOLDOWN", "300")),
        metavar="N",
        help="Seconds between repeat notifications per (pid, event) (default: 300)",
    )
    parser.add_argument(
        "--mode",
        default=os.environ.get("SIGNALSCOPE_MODE", "dashboard"),
        choices=["dashboard", "agent", "collector", "cli", "web"],
        help="Run mode: dashboard, agent, collector (default: dashboard)",
    )
    parser.add_argument(
        "--collector-url",
        default=os.environ.get("SIGNALSCOPE_COLLECTOR_URL", ""),
        metavar="URL",
        help="Collector URL for agent mode",
    )
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("SIGNALSCOPE_AGENT_ID", ""),
        metavar="UUID",
        help="Agent ID (auto-generated if not set)",
    )
    parser.add_argument(
        "--agent-secret",
        default=os.environ.get("SIGNALSCOPE_AGENT_SECRET", ""),
        metavar="STR",
        help="Shared secret for agent/collector authentication",
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


def _insight_to_event_type(insight: str) -> str:
    if "🔥" in insight:
        return "high_cpu"
    if "🧠" in insight:
        return "high_mem"
    if "👻" in insight:
        return "zombie"
    if "📈" in insight:
        return "trend"
    if "🤖" in insight:
        return "daemon"
    return "anomaly"


def _get_or_create_agent_id() -> str:
    import uuid
    id_file = Path.home() / ".signalscope" / "agent_id"
    id_file.parent.mkdir(parents=True, exist_ok=True)
    if id_file.exists():
        stored = id_file.read_text().strip()
        if stored:
            return stored
    new_id = str(uuid.uuid4())
    id_file.write_text(new_id + "\n")
    return new_id


def _run_agent_mode(args) -> int:
    """Post process snapshots to a central collector URL."""
    import socket
    import urllib.request
    import time

    if not args.collector_url:
        print("ERROR: --collector-url is required in agent mode", file=sys.stderr)
        return 1

    collector = ProcessCollector(user=args.user)
    analyze_fn = build_analyze_fn(args)
    agent_id = _get_or_create_agent_id()
    hostname = socket.gethostname()

    print(f"SignalScope agent mode — posting to {args.collector_url} every {args.interval}s")

    while True:
        try:
            processes = collector.collect()
            analyze_fn(processes)
            processes_sorted = sorted(processes, key=lambda p: p.cpu_percent, reverse=True)
            if args.top:
                processes_sorted = processes_sorted[:args.top]

            payload = json.dumps({
                "host": hostname,
                "agent_id": agent_id,
                "captured_at": datetime.utcnow().isoformat(),
                "processes": [
                    {
                        "pid": p.pid,
                        "name": p.name,
                        "cpu_percent": p.cpu_percent,
                        "memory_percent": p.memory_percent,
                        "status": p.status,
                        "ppid": p.ppid,
                        "insights": p.insights,
                    }
                    for p in processes_sorted
                ],
            }).encode()

            headers = {"Content-Type": "application/json"}
            if args.agent_secret:
                headers["X-Agent-Secret"] = args.agent_secret

            req = urllib.request.Request(
                f"{args.collector_url.rstrip('/')}/ingest",
                data=payload,
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    pass  # success
            except Exception as exc:
                logging.getLogger(__name__).warning("Agent POST failed: %s", exc)

            time.sleep(args.interval)
        except KeyboardInterrupt:
            break

    return 0


def _run_collector_mode(args) -> int:
    """Run a FastAPI collector server that accepts agent snapshots."""
    try:
        import uvicorn
        from src.web.collector_app import create_collector_app
    except ImportError:
        print("ERROR: collector mode requires fastapi+uvicorn. pip install -r requirements-web.txt", file=sys.stderr)
        return 1

    app = create_collector_app(args)
    host = os.environ.get("SIGNALSCOPE_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("SIGNALSCOPE_WEB_PORT", "8000"))
    print(f"SignalScope collector → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
    return 0

def main(argv=None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    # Mode routing (backward compat: "cli" -> "dashboard", "web" -> ignored here)
    mode = args.mode
    if mode == "cli":
        mode = "dashboard"

    if mode == "agent":
        return _run_agent_mode(args)
    elif mode == "collector":
        return _run_collector_mode(args)
    # else: dashboard / snapshot logic below

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

    # Wrap analyze_fn with notification dispatch (last in chain).
    from src.notifications.notifier import Notifier, AnomalyEvent
    notifier = Notifier(cooldown_seconds=args.notify_cooldown)
    if args.slack_webhook:
        from src.notifications.notifier import SlackNotifier
        notifier.add_channel(SlackNotifier(args.slack_webhook))
    if args.webhook_url:
        from src.notifications.notifier import GenericWebhookNotifier
        notifier.add_channel(GenericWebhookNotifier(args.webhook_url))

    _prev_notify_analyze = analyze_fn
    _notify_seen: set = set()

    def analyze_fn(processes: List[ProcessInfo]) -> None:  # type: ignore[misc]
        _prev_notify_analyze(processes)
        for p in processes:
            for insight in p.insights:
                key = (p.pid, insight)
                if key not in _notify_seen:
                    _notify_seen.add(key)
                    event_type = _insight_to_event_type(insight)
                    notifier.notify(AnomalyEvent(
                        pid=p.pid, name=p.name, event_type=event_type, detail=insight
                    ))

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

