# ⚡ SignalScope

> **Real-time process monitor with intelligent insights — runs anywhere.**

SignalScope is a lightweight, Python-based tool that monitors system processes in real time and provides actionable insights: zombie detection, high-CPU / high-memory anomaly flagging, CPU spike trend tracking, daemon identification, alert logging, and one-shot process snapshots.

It ships as both a **beautiful terminal (CLI) dashboard** and an optional **browser-based web dashboard**, and can be run directly with Python or as a **Docker container** on any platform — no Python setup required.

---

## ✨ Features

| Feature | Description |
|---|---|
| **Real-time table** | Refreshes every 2 s (configurable) with a colour-coded terminal UI |
| **Web dashboard** | Browser-based live dashboard with WebSocket streaming |
| **Zombie detection** | Automatically flags zombie processes in bold red 👻 |
| **High-CPU anomaly** | Highlights processes exceeding a configurable CPU % threshold 🔥 |
| **High-memory anomaly** | Highlights processes exceeding a configurable memory % threshold 🧠 |
| **CPU spike trend tracking** | Flags processes with recurring high-CPU across refresh cycles 📈 |
| **Daemon detection** | Identifies processes with no controlling terminal or very long uptime 🤖 |
| **Dashboard summary banner** | Shows total processes, zombie count, and per-category anomaly counts |
| **Alert logging** | Appends new anomaly events to a file — each (PID, insight) pair logged only once |
| **Process snapshot export** | Saves a one-time snapshot of the top-N processes to CSV or JSON |
| **User filter** | Limits monitoring to processes owned by a specific username |
| **Docker ready** | Single-command Docker run; configurable via environment variables |
| **Cross-platform** | Works on Linux, macOS, and Windows (CLI) |

---

## 🖥️ Example Output

### Terminal dashboard

```
╭──────────────────────────────────────── SignalScope — Process Monitor ─────────────────────────────────────╮
│  System  CPU: 12.3%  |  RAM: 41.5% used (6,720 / 16,384 MB)  |  Processes: 142  |  🔥 High CPU: 2  |  👻 Zombies: 1  │
│─────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│  PID    Name              CPU %   Mem %   Status    Insight                                                  │
│  1234   python3            82.3    1.50   running   🔥 High CPU: 82.3% (above 50% threshold)                │
│  5678   java               61.0   18.20   running   🔥 High CPU: 61.0%, 🧠 High Memory: 18.2%, 📈 Trend: 6/10  │
│   999   defunct             0.0    0.00   zombie    👻 Zombie: parent has not called wait()                  │
│     1   systemd             0.0    0.10   sleeping  🤖 Daemon (no tty)                                      │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

*Rows are colour-coded: bold red = zombie, yellow = high CPU, magenta = high memory, dim = idle.*

### Web dashboard

Open `http://localhost:8000` after starting the web server to get a live, auto-updating browser dashboard with the same insights.

---

## 🚀 Quick Start

### Option A — Python (recommended for developers)

```bash
# 1. Clone & enter the repo
git clone https://github.com/johnny603/signalScope.git
cd signalScope

# 2. Create a virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install core dependencies
pip install -r requirements.txt

# 4. Launch the terminal dashboard
python -m src.main
```

**Web dashboard (extra install):**

```bash
pip install -r requirements-web.txt
python -m src.web.app          # open http://localhost:8000
```

---

### Option B — Docker (zero Python setup)

#### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed and running.

#### Build the image

```bash
docker build -t signalscope .
```

#### Run the terminal (CLI) dashboard

```bash
docker run --rm -it \
  --pid=host --privileged \
  signalscope
```

> `--pid=host` lets SignalScope see the *host* process tree instead of just the container's processes.  
> `--privileged` is required on some systems to read all process attributes.

#### Run the web dashboard

```bash
docker run --rm \
  --pid=host --privileged \
  -p 8000:8000 \
  -e SIGNALSCOPE_MODE=web \
  signalscope
```

Then open **http://localhost:8000** in your browser.

#### Configuration via environment variables

All CLI flags are available as `SIGNALSCOPE_*` environment variables:

| Variable | Default | Description |
|---|---|---|
| `SIGNALSCOPE_MODE` | `cli` | `cli` = terminal dashboard, `web` = browser dashboard |
| `SIGNALSCOPE_INTERVAL` | `2.0` | Refresh interval in seconds |
| `SIGNALSCOPE_TOP` | *(all)* | Show only top-N processes by CPU usage |
| `SIGNALSCOPE_CPU_THRESHOLD` | `50.0` | CPU % above which a process is flagged |
| `SIGNALSCOPE_MEM_THRESHOLD` | `10.0` | Memory % above which a process is flagged |
| `SIGNALSCOPE_NO_DAEMON` | `false` | Set `true` to disable daemon detection |
| `SIGNALSCOPE_USER` | *(all)* | Restrict to processes owned by this user |
| `SIGNALSCOPE_ALERT_LOG` | *(none)* | Path inside container to write alert events |
| `SIGNALSCOPE_LOG_LEVEL` | `WARNING` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `SIGNALSCOPE_WEB_HOST` | `0.0.0.0` | Bind address for the web server |
| `SIGNALSCOPE_WEB_PORT` | `8000` | Port for the web server |

**Example — custom thresholds, top-20 processes, 1-second refresh:**

```bash
docker run --rm -it --pid=host --privileged \
  -e SIGNALSCOPE_INTERVAL=1 \
  -e SIGNALSCOPE_TOP=20 \
  -e SIGNALSCOPE_CPU_THRESHOLD=25 \
  signalscope
```

#### Using Docker Compose

```bash
# Terminal dashboard
docker compose --profile cli up

# Web dashboard (visit http://localhost:8000)
docker compose --profile web up
```

---

## 🐍 CLI Reference

```bash
python -m src.main [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--interval SECONDS` | `2.0` | Refresh interval in seconds |
| `--top N` | *(all)* | Show only the top N processes by CPU usage |
| `--cpu-threshold PCT` | `50.0` | CPU % above which a process is flagged as high-CPU |
| `--mem-threshold PCT` | `10.0` | Memory % above which a process is flagged as high-memory |
| `--no-daemon` | `false` | Disable daemon detection (faster on large systems) |
| `--user USERNAME` | *(all users)* | Show only processes owned by this username |
| `--alert-log FILE` | *(none)* | Append new anomaly events to FILE |
| `--snapshot FILE` | *(none)* | Save a one-time snapshot to FILE (.csv or .json) and exit |
| `--log-level LEVEL` | `WARNING` | Logging verbosity: DEBUG / INFO / WARNING / ERROR |

### Usage examples

```bash
# Default view — refresh every 2 s
python -m src.main

# Show only top 20 processes, refresh every second
python -m src.main --top 20 --interval 1

# Lower CPU anomaly threshold to 25 %, enable debug logging
python -m src.main --cpu-threshold 25 --log-level DEBUG

# Watch only processes owned by alice
python -m src.main --user alice

# Log anomalies to a file while monitoring
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

## 🌐 Web Dashboard

```bash
# Start web server (Python)
python -m src.web.app

# Custom host / port
python -m src.web.app --host 127.0.0.1 --port 9000

# All flags from the CLI are also available
python -m src.web.app --interval 1 --top 50 --cpu-threshold 30
```

Then open **http://localhost:8000** in any modern browser.

The web dashboard:
- Auto-refreshes at the configured interval via a persistent WebSocket connection.
- Reconnects automatically if the connection drops.
- Colour-codes rows the same way as the terminal: red = zombie, yellow = high CPU, magenta = high memory, dim = idle.
- Shows the same summary banner (total processes, anomaly counts) as the terminal.

---

## 📊 Understanding the Columns

| Column | Description |
|---|---|
| **PID** | Process identifier |
| **Name** | Executable name |
| **CPU % ↓** | CPU usage sorted highest-first; measured since last refresh |
| **Mem %** | Percentage of total physical RAM in use |
| **Status** | Process state: `running`, `sleeping`, `zombie`, etc. |
| **Insight** | Detected anomalies (see key below) |

### Insight key

| Icon | Meaning |
|---|---|
| 🔥 | **High CPU** — CPU % above `--cpu-threshold` (default 50 %) |
| 🧠 | **High Memory** — Memory % above `--mem-threshold` (default 10 %) |
| 📈 | **CPU Spike Trend** — Repeated high-CPU detections across rolling window |
| 👻 | **Zombie** — Process has exited but parent has not collected its exit status |
| 🤖 | **Daemon** — No controlling terminal, or uptime > 1 hour |
| — | No notable insight |

### Filtering tips

- Use `--top 20` to focus on the 20 busiest processes — great for busy servers.
- Lower `--cpu-threshold` to `10` on a lightly loaded system to catch subtle spikes.
- Combine `--user www-data` with `--alert-log` to monitor a specific service and persist alerts.
- Use `--snapshot` to capture a point-in-time CSV/JSON for offline analysis or reporting.

---

## 🗂️ Project Structure

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
│   └── web/
│       └── app.py                   # FastAPI web dashboard (WebSocket streaming)
├── tests/                           # pytest test suite
├── Dockerfile                       # Multi-stage Docker image
├── docker-compose.yml               # Compose profiles: cli / web
├── docker-entrypoint.sh             # Maps ENV vars to CLI flags
├── requirements.txt                 # Core runtime dependencies
├── requirements-web.txt             # Web dashboard extras (FastAPI, uvicorn)
├── requirements-dev.txt             # Development / test dependencies
└── pyproject.toml
```

---

## 🔧 How It Works

1. **Collector** (`src/collector/process_collector.py`) — uses `psutil.process_iter` to take a snapshot of all running processes each refresh cycle. Optionally filters by username.
2. **Models** (`src/models/process.py`) — each process is stored as a `ProcessInfo` dataclass containing PID, name, CPU %, memory %, status, and parent PID.
3. **Insight Engine** (`src/insights/`) — five independent detectors annotate each `ProcessInfo` in-place:
   - `ZombieDetector` → status == "zombie"
   - `AnomalyDetector` → cpu_percent > threshold
   - `MemoryAnomalyDetector` → memory_percent > threshold
   - `TrendTracker` → recurring CPU spikes across rolling window of samples
   - `DaemonDetector` → no controlling terminal or uptime > 1 hour
4. **Alert Logger** (`src/alert_logger.py`) — after each analysis cycle, writes new `(pid, insight)` events to a log file; duplicates are suppressed.
5. **Exporter** (`src/exporter.py`) — serialises the process list to CSV or JSON.
6. **CLI Dashboard** (`src/ui/dashboard.py`) — renders a live `rich` table with colour styles and a summary banner.
7. **Web Dashboard** (`src/web/app.py`) — FastAPI app serving an HTML page; a WebSocket endpoint pushes fresh JSON snapshots to the browser at each refresh interval.

---

## 🧪 Running Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

---

## 📄 License

MIT
