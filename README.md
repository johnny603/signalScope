# ⚡ SignalScope

> **Real-time process monitor with intelligent insights — runs anywhere.**

SignalScope is a lightweight, Python-based tool that monitors system processes in real time and provides actionable insights: zombie detection, high-CPU / high-memory anomaly flagging, CPU spike trend tracking, daemon identification, alert logging, and one-shot process snapshots.

It ships as both a **beautiful terminal (CLI) dashboard** and an optional **browser-based web dashboard**, and can be run directly with Python or as a **Docker container** on any platform — no Python setup required.

**New in this release:** process kill / signal actions, SQLite metrics persistence, Slack/webhook notifications, web dashboard authentication, and multi-host agent mode.

---

## Why signalScope?
Any application running on a server — whether a cloud VM, a local machine, or a container — accumulates processes over time. These processes don't announce when they go wrong. They silently degrade your system until something breaks. Here's why that matters.

Zombie processes:
A zombie is a process that has finished executing but whose parent never collected its exit code. They seem harmless — using almost no CPU or memory — but they hold slots in the OS process table. Linux has a hard limit of ~32,768 processes. Accumulate enough zombies and your system can no longer spawn new processes: no new logins, no new server threads, nothing.

Undetected memory leaks:
A process that grabs a little more memory each hour is harmless for a day. Left for weeks, it slowly exhausts available RAM. Once RAM is full and swap is consumed, the kernel's OOM Killer begins terminating processes — often critical services — seemingly at random, with no warning other than a gradual slowdown nobody caught.

CPU spike trends:
A one-time CPU spike is noise. A process that spikes repeatedly across cycles is entering a runaway loop. Most monitors only see the snapshot — not the pattern. Without trend tracking, a process stuck in an infinite loop can peg a CPU core at 100% indefinitely, starving every other process of compute time until the system becomes unresponsive.

Daemon accumulation:
Background services that crash and auto-restart can silently multiply over time. Each new instance may hold open file descriptors or leak memory. Linux enforces a per-process and system-wide file descriptor limit — when it's hit, applications begin throwing cryptic errors like "too many open files," a problem that is invisible until it's already impacting users.

Silent, slow failure:
The OS does not clean these up for you. Its job is to run processes, not judge whether they should still be running. Without active monitoring, systems can degrade for weeks while appearing healthy — no crash, no alert, no obvious signal — until a cascading failure takes down something critical at the worst possible moment.

This is where SignalScope comes in. We surface these signals before they become failures — with real-time zombie detection, memory anomaly flagging, CPU trend tracking, and daemon identification. No complex setup. No enterprise pricing. Just the intelligence your system already needs.

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
| **Process kill / signal** ⚡ | Send SIGTERM or SIGKILL to processes from web UI or CLI (press `k`) |
| **Metrics persistence** 🗄️ | SQLite time-series storage; query history, anomalies, top offenders |
| **Slack / Webhook alerts** 🔔 | Push anomaly events to Slack or any HTTP endpoint with cooldown dedup |
| **Web auth** 🔒 | HTTP Basic Auth with auto-generated password; timing-safe comparison |
| **Multi-host agent mode** 🌐 | `--mode agent` posts snapshots to a central `--mode collector` server |

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
| `SIGNALSCOPE_MODE` | `cli` | `cli`/`dashboard` = terminal, `web` = web server, `agent` = push to collector, `collector` = receive from agents |
| `SIGNALSCOPE_INTERVAL` | `2.0` | Refresh interval in seconds |
| `SIGNALSCOPE_TOP` | *(all)* | Show only top-N processes by CPU usage |
| `SIGNALSCOPE_CPU_THRESHOLD` | `50.0` | CPU % above which a process is flagged |
| `SIGNALSCOPE_MEM_THRESHOLD` | `10.0` | Memory % above which a process is flagged |
| `SIGNALSCOPE_NO_DAEMON` | `false` | Set `true` to disable daemon detection |
| `SIGNALSCOPE_USER` | *(all)* | Restrict to processes owned by this user |
| `SIGNALSCOPE_ALERT_LOG` | *(none)* | Path to write alert events |
| `SIGNALSCOPE_LOG_LEVEL` | `WARNING` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `SIGNALSCOPE_WEB_HOST` | `0.0.0.0` | Bind address for the web server |
| `SIGNALSCOPE_WEB_PORT` | `8000` | Port for the web server |
| `SIGNALSCOPE_DB_PATH` | `~/.signalscope/metrics.db` | SQLite database path |
| `SIGNALSCOPE_SLACK_WEBHOOK_URL` | *(none)* | Slack Incoming Webhook URL |
| `SIGNALSCOPE_WEBHOOK_URL` | *(none)* | Generic webhook URL |
| `SIGNALSCOPE_NOTIFY_COOLDOWN` | `300` | Notification cooldown in seconds |
| `SIGNALSCOPE_WEB_USER` | `admin` | Web dashboard username |
| `SIGNALSCOPE_WEB_PASSWORD` | *(auto-generated)* | Web dashboard password |
| `SIGNALSCOPE_NO_AUTH` | `false` | Set `true` to disable web auth |
| `SIGNALSCOPE_COLLECTOR_URL` | *(none)* | Collector URL for agent mode |
| `SIGNALSCOPE_AGENT_SECRET` | *(none)* | Shared secret for agent↔collector auth |

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
| `--db PATH` | `~/.signalscope/metrics.db` | SQLite database path for metrics persistence |
| `--retention-days N` | `7` | Delete records older than N days on startup |
| `--slack-webhook URL` | *(none)* | Slack Incoming Webhook URL for anomaly alerts |
| `--webhook-url URL` | *(none)* | Generic HTTP webhook URL for anomaly alerts |
| `--notify-cooldown N` | `300` | Seconds between repeated notifications for the same (PID, event) |
| `--mode MODE` | `dashboard` | Run mode: `dashboard` (default), `agent`, or `collector` |
| `--collector-url URL` | *(none)* | Collector URL for agent mode (e.g. `http://collector:8000`) |
| `--agent-secret STR` | *(none)* | Shared secret for agent↔collector authentication |

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

## ⚡ Process Kill / Signal Actions

Press **`k`** in the terminal dashboard to send a signal to any process.

You will be prompted for the PID, then `[T]SIGTERM` or `[K]SIGKILL`.
- SIGTERM is graceful; SIGKILL requires you to type the process name to confirm.
- Zombie processes are blocked (killing the parent is suggested instead).
- System / daemon processes (uid 0 or no-tty + uptime > 1 h) are flagged as **high-risk**.
- All kill actions are appended to `kill_audit.log`.

In the **web dashboard**, each row has an ⚡ button that opens a confirmation modal with the same safeguards.

---

## 🗄️ Metrics Persistence

SignalScope persists process snapshots and anomaly events to a SQLite database.

```bash
# Default DB at ~/.signalscope/metrics.db
python -m src.main

# Custom path
python -m src.main --db /var/lib/signalscope/metrics.db

# Keep 30 days of history
python -m src.main --retention-days 30
```

**REST API (web dashboard):**

| Endpoint | Description |
|---|---|
| `GET /api/history/{pid}?hours=1` | CPU / memory timeseries for a PID |
| `GET /api/anomalies?limit=50` | Recent anomaly events |
| `GET /api/top-offenders?hours=24&metric=cpu` | Processes ranked by average CPU or memory |

The web UI shows a sparkline chart (Chart.js) and a live "Recent Anomalies" sidebar.

---

## 🔔 Notification Hooks

Send alerts to Slack or any HTTP endpoint when anomalies are detected.

```bash
# Slack
python -m src.main --slack-webhook https://hooks.slack.com/services/...

# Generic webhook
python -m src.main --webhook-url https://my-alert-system/endpoint

# Reduce noise: 10-minute cooldown per (PID, event_type) pair
python -m src.main --slack-webhook $URL --notify-cooldown 600
```

Or via environment variables: `SIGNALSCOPE_SLACK_WEBHOOK_URL`, `SIGNALSCOPE_WEBHOOK_URL`, `SIGNALSCOPE_NOTIFY_COOLDOWN`.

Slack message format:
```
[SignalScope Alert]
Process: {name} (PID {pid})
Event: {event_type}
Detail: {detail}
Host: {hostname}
Time: {timestamp}
```

Uses Python's built-in `urllib.request` — no extra dependencies. Retries once on failure.

---

## 🔒 Web Dashboard Authentication

The web dashboard is protected by HTTP Basic Auth by default.

```bash
# Auto-generate a random password (printed once, saved to ~/.signalscope/web_credentials)
python -m src.web.app

# Set a fixed password
SIGNALSCOPE_WEB_USER=admin SIGNALSCOPE_WEB_PASSWORD=mysecret python -m src.web.app

# Disable auth (trusted local use only)
python -m src.web.app --no-auth
```

> ⚠️ **Never expose port 8000 directly to the public internet.**
> Always place SignalScope behind a reverse proxy (nginx, Caddy) with TLS when exposing it externally.

---

## 🌐 Multi-Host Agent Mode

Monitor multiple machines from a single dashboard.

**On each machine (agent):**
```bash
python -m src.main --mode agent --collector-url http://collector-host:8000 \
  --agent-secret mysecret --interval 5
```

**On the central collector:**
```bash
python -m src.main --mode collector --agent-secret mysecret
# or
python -m src.web.app  # (collector mode is built-in)
```

Then open `http://collector-host:8000` for a unified view of all agents.

**Docker Compose:**
```bash
# Start collector
docker compose --profile collector up

# Start agent on each host
SIGNALSCOPE_MODE=agent SIGNALSCOPE_COLLECTOR_URL=http://collector:8000 \
  docker compose --profile cli up
```

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
│   ├── actions/
│   │   └── process_killer.py        # Send SIGTERM/SIGKILL; ActionResult + audit log
│   ├── storage/
│   │   └── metrics_store.py         # SQLite persistence (snapshots, anomalies, kills)
│   ├── notifications/
│   │   └── notifier.py              # Slack + generic webhook notification hooks
│   └── web/
│       ├── app.py                   # FastAPI web dashboard (WebSocket + REST API)
│       └── collector_app.py         # Multi-host collector server
├── tests/                           # pytest test suite (111 tests)
├── Dockerfile                       # Multi-stage Docker image
├── docker-compose.yml               # Compose profiles: cli / web / collector
├── docker-entrypoint.sh             # Maps ENV vars to CLI flags
├── requirements.txt                 # Core runtime dependencies
├── requirements-web.txt             # Web dashboard extras (FastAPI, uvicorn)
├── requirements-dev.txt             # Development / test dependencies
└── pyproject.toml
```

### Architecture (text diagram)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SignalScope Architecture                           │
│                                                                             │
│  psutil ──► ProcessCollector ──► [ProcessInfo list]                         │
│                                         │                                  │
│                               ┌─────────▼──────────┐                       │
│                               │   Insight Engine    │                       │
│                               │  ZombieDetector     │                       │
│                               │  AnomalyDetector    │                       │
│                               │  MemoryDetector     │                       │
│                               │  TrendTracker       │                       │
│                               │  DaemonDetector     │                       │
│                               └─────────┬──────────┘                       │
│                                         │                                  │
│              ┌──────────────────────────┼────────────────────────┐         │
│              ▼                          ▼                         ▼         │
│        AlertLogger             MetricsStore (SQLite)          Notifier       │
│        (CSV log)          snapshots/anomalies/kills      Slack/Webhook       │
│              │                          │                         │         │
│              ▼                          ▼                         │         │
│     ┌────────────────┐    ┌─────────────────────────┐             │         │
│     │ CLI Dashboard  │    │    Web Dashboard (FA)    │◄────────────┘         │
│     │  rich.Live     │    │  WebSocket + REST API   │                       │
│     │  press 'k'     │    │  Auth (HTTP Basic)      │                       │
│     └────────────────┘    │  Kill modal + sparkline │                       │
│                           └──────────┬──────────────┘                       │
│                                      │                                      │
│                            ProcessKiller (actions)                          │
│                            SIGTERM / SIGKILL + audit                        │
│                                                                             │
│  ── Agent Mode ─────────────────────────────────────────────────────────── │
│  Agent 1 (host-A)  ──POST /ingest──►  Collector (central)                  │
│  Agent 2 (host-B)  ──POST /ingest──►  http://<collector>:8000/             │
│  Agent N (host-N)  ──POST /ingest──►  unified multi-host dashboard          │
└─────────────────────────────────────────────────────────────────────────────┘
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
6. **CLI Dashboard** (`src/ui/dashboard.py`) — renders a live `rich` table with colour styles and a summary banner. Press `k` to kill/signal a process.
7. **Web Dashboard** (`src/web/app.py`) — FastAPI app serving an HTML page; a WebSocket endpoint pushes fresh JSON snapshots to the browser at each refresh interval. REST API for history, anomalies, and signal actions.
8. **Process Killer** (`src/actions/process_killer.py`) — sends SIGTERM/SIGKILL with zombie/high-risk checks and kill audit logging.
9. **Metrics Store** (`src/storage/metrics_store.py`) — persists snapshots, anomaly events, and kill events to SQLite with configurable retention.
10. **Notifier** (`src/notifications/notifier.py`) — dispatches anomaly events to Slack and/or generic HTTP webhooks with cooldown deduplication.
11. **Collector App** (`src/web/collector_app.py`) — multi-host collector server accepting JSON snapshots from remote agents.

---

## 🧪 Running Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

---

## 📄 License

MIT
