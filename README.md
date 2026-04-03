# SignalScope

A lightweight, Python-based CLI application that monitors system processes in real time and provides intelligent insights — including zombie process detection, high-CPU and high-memory anomaly flagging, CPU spike trend tracking, daemon identification, alert logging, and one-shot process snapshots.

---

## Features

| Feature | Description |
|---|---|
| **Real-time table** | Refreshes every 2 seconds (configurable) with a clean, colour-coded terminal UI |
| **Zombie detection** | Automatically flags zombie processes in bold red |
| **High-CPU anomaly** | Highlights processes exceeding a configurable CPU% threshold in yellow (`🔥`) |
| **High-memory anomaly** | Highlights processes exceeding a configurable memory% threshold in magenta (`🧠`) |
| **CPU spike trend tracking** | Flags processes with recurring high-CPU across refresh cycles (`📈`) |
| **Daemon detection** | Identifies processes with no controlling terminal or very long uptime (`🤖`) |
| **Dashboard summary banner** | Shows total processes, zombie count, and per-category anomaly counts at a glance |
| **Alert logging** | Appends new anomaly events to a file — each (PID, insight) pair is logged only once |
| **Process snapshot export** | Saves a one-time snapshot of the top-N processes to CSV or JSON and exits |
| **User filter** | Limits monitoring to processes owned by a specific username |
| **Colour-coded output** | Yellow → high CPU, Magenta → high memory, Red → zombie, Dim → idle |
| **Modular architecture** | Clean separation of collector, models, insights, and UI layers |
| **Logging support** | Configurable log level for debugging |

---

## Example Output

```
╭──────────────────────────────────────── SignalScope — Process Monitor ────────────────────────────────────────╮
│  System  CPU: 12.3%  |  RAM: 41.5% used (6,720 / 16,384 MB)  |  Processes: 142  |  🔥 High CPU: 2  |  👻 Zombies: 1  │
│─────────────────────────────────────────────────────────────────────────────────────────────────────────────  │
│  PID   Name                CPU %   Mem %   Status      Insight                                                │
│─────────────────────────────────────────────────────────────────────────────────────────────────────────────  │
│  1234  python3              82.3    1.50   running     🔥 High CPU: 82.3% (above 50% threshold)               │
│  5678  java                 61.0    18.20  running     🔥 High CPU: 61.0%, 🧠 High Memory: 18.2%, 📈 CPU Spike Trend: 6/10 samples  │
│   999  defunct               0.0    0.00  zombie      👻 Zombie: Process finished but parent has not called wait()  │
│     1  systemd               0.0    0.10  sleeping    🤖 Daemon (no tty)                                      │
│   456  bash                  0.2    0.30  sleeping    —                                                       │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

*(Rows are colour-coded: bold red = zombie, yellow = high CPU, magenta = high memory, dim = idle.)*

---

## Project Structure

```
signalScope/
├── src/
│   ├── main.py                      # CLI entry point
│   ├── alert_logger.py              # Appends anomaly events to a log file
│   ├── exporter.py                  # Exports process snapshots to CSV / JSON
│   ├── collector/
│   │   └── process_collector.py     # Gathers process data via psutil
│   ├── models/
│   │   └── process.py               # ProcessInfo data model
│   ├── insights/
│   │   ├── zombie_detector.py       # Detects zombie processes
│   │   ├── anomaly_detector.py      # Flags high CPU usage
│   │   ├── memory_detector.py       # Flags high memory usage
│   │   ├── trend_tracker.py         # Detects recurring CPU spikes over time
│   │   └── daemon_detector.py       # Identifies daemon processes
│   └── ui/
│       └── dashboard.py             # Rich-based live terminal dashboard
├── tests/                           # pytest test suite
├── requirements.txt
├── requirements-dev.txt
└── pyproject.toml
```

---

## Setup

### Prerequisites

- Python 3.9+
- pip

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/johnny603/signalScope.git
cd signalScope

# 2. (Recommended) Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install runtime dependencies
pip install -r requirements.txt
```

---

## Running SignalScope

```bash
python -m src.main
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--interval SECONDS` | `2.0` | Refresh interval in seconds |
| `--top N` | *(all)* | Show only the top N processes by CPU usage |
| `--cpu-threshold PCT` | `50.0` | CPU % above which a process is flagged as high-CPU |
| `--mem-threshold PCT` | `10.0` | Memory % above which a process is flagged as high-memory |
| `--no-daemon` | `false` | Disable daemon detection (faster on large systems) |
| `--user USERNAME` | *(all users)* | Show only processes owned by this username |
| `--alert-log FILE` | *(none)* | Append new anomaly events to FILE (one line per event) |
| `--snapshot FILE` | *(none)* | Save a one-time snapshot to FILE (.csv or .json) and exit |
| `--log-level LEVEL` | `WARNING` | Logging verbosity: DEBUG / INFO / WARNING / ERROR |

### Examples

```bash
# Default view — refresh every 2 s
python -m src.main

# Show only top 20 processes, refresh every second
python -m src.main --top 20 --interval 1

# Lower CPU anomaly threshold to 25 %, enable debug logging
python -m src.main --cpu-threshold 25 --log-level DEBUG

# Watch only processes owned by a specific user
python -m src.main --user alice

# Log new anomalies to a file while monitoring
python -m src.main --alert-log /var/log/signalscope-alerts.log

# Save a one-shot JSON snapshot of the top 10 processes then exit
python -m src.main --top 10 --snapshot /tmp/snapshot.json

# Save a CSV snapshot
python -m src.main --snapshot /tmp/snapshot.csv

# Skip daemon detection for faster startup
python -m src.main --no-daemon
```

Press **Ctrl + C** to exit.

---

## Running Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

---

## How It Works

1. **Collector** (`src/collector/process_collector.py`) — uses `psutil.process_iter` to take a snapshot of all running processes each refresh cycle.  Optionally filters by username (`--user`).
2. **Models** (`src/models/process.py`) — each process is stored as a `ProcessInfo` dataclass containing PID, name, CPU %, memory %, status, and parent PID.
3. **Insight Engine** (`src/insights/`) — five independent detectors annotate each `ProcessInfo` in-place:
   - `ZombieDetector` → status == "zombie"
   - `AnomalyDetector` → cpu_percent > threshold
   - `MemoryAnomalyDetector` → memory_percent > threshold
   - `TrendTracker` → recurring CPU spikes across rolling window of samples
   - `DaemonDetector` → no controlling terminal or uptime > 1 hour
4. **Alert Logger** (`src/alert_logger.py`) — after each analysis cycle, writes new `(pid, insight)` events to a log file; duplicates are suppressed.
5. **Exporter** (`src/exporter.py`) — serialises the process list to CSV or JSON (format inferred from file extension).
6. **Dashboard** (`src/ui/dashboard.py`) — renders a live `rich` table, applying colour styles per row and displaying a summary banner with anomaly counts.

---

## License

MIT
