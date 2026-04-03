# SignalScope

A lightweight, Python-based CLI application that monitors system processes in real time and provides intelligent insights — including zombie process detection, high-CPU anomaly flagging, and daemon identification.

---

## Features

| Feature | Description |
|---|---|
| **Real-time table** | Refreshes every 2 seconds (configurable) with a clean, colour-coded terminal UI |
| **Zombie detection** | Automatically flags zombie processes in bold red |
| **High-CPU anomaly** | Highlights processes exceeding a configurable CPU% threshold in yellow |
| **Daemon detection** | Identifies processes with no controlling terminal or very long uptime |
| **Colour-coded output** | Green → normal, Yellow → high CPU, Red → zombie |
| **Modular architecture** | Clean separation of collector, models, insights, and UI layers |
| **Logging support** | Configurable log level for debugging |

---

## Example Output

```
╭──────────────────────────────── SignalScope — Process Monitor ────────────────────────────────────╮
│  PID  Name                CPU %   Mem %   Status      Insight                                     │
│─────────────────────────────────────────────────────────────────────────────────────────────────  │
│  1234  python3              82.3    1.50   running     🔥 High CPU                                  │
│   999  defunct               0.0    0.00   zombie      ⚠ Zombie process                            │
│     1  systemd               0.0    0.10   sleeping    🤖 Daemon (no tty)                           │
│   456  bash                  0.2    0.30   sleeping    —                                           │
╰───────────────────────────────────────────────────────────────────────────────────────────────────╯
```

*(Rows are colour-coded: red = zombie, yellow = high CPU, green = normal.)*

---

## Project Structure

```
signalScope/
├── src/
│   ├── main.py                      # CLI entry point
│   ├── collector/
│   │   └── process_collector.py     # Gathers process data via psutil
│   ├── models/
│   │   └── process.py               # ProcessInfo data model
│   ├── insights/
│   │   ├── zombie_detector.py       # Detects zombie processes
│   │   ├── anomaly_detector.py      # Flags high CPU usage
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
| `--cpu-threshold PCT` | `50.0` | CPU % above which a process is flagged |
| `--no-daemon` | `false` | Disable daemon detection (faster on large systems) |
| `--log-level LEVEL` | `WARNING` | Logging verbosity: DEBUG / INFO / WARNING / ERROR |

### Examples

```bash
# Default view — refresh every 2 s
python -m src.main

# Show only top 20 processes, refresh every second
python -m src.main --top 20 --interval 1

# Lower CPU anomaly threshold to 25 %, enable debug logging
python -m src.main --cpu-threshold 25 --log-level DEBUG

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

1. **Collector** (`src/collector/process_collector.py`) — uses `psutil.process_iter` to take a snapshot of all running processes each refresh cycle.
2. **Models** (`src/models/process.py`) — each process is stored as a `ProcessInfo` dataclass containing PID, name, CPU %, memory %, status, and parent PID.
3. **Insight Engine** (`src/insights/`) — three independent detectors annotate each `ProcessInfo` in-place:
   - `ZombieDetector` → status == "zombie"
   - `AnomalyDetector` → cpu_percent > threshold
   - `DaemonDetector` → no controlling terminal or uptime > 1 hour
4. **Dashboard** (`src/ui/dashboard.py`) — renders a live `rich` table, applying colour styles per row based on the process state and annotations.

---

## License

MIT
