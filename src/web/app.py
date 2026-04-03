"""SignalScope Web Dashboard.

Launches a FastAPI server that streams live process data over a WebSocket and
serves a browser-based dashboard.

Usage (direct)
--------------
    python -m src.web.app [--host HOST] [--port PORT] [OPTIONS]

Environment variables (all optional)
-------------------------------------
    SIGNALSCOPE_INTERVAL        Refresh interval in seconds (default: 2.0)
    SIGNALSCOPE_TOP             Show only top-N processes (default: all)
    SIGNALSCOPE_CPU_THRESHOLD   CPU % threshold (default: 50.0)
    SIGNALSCOPE_MEM_THRESHOLD   Memory % threshold (default: 10.0)
    SIGNALSCOPE_NO_DAEMON       Disable daemon detection ("true"/"1")
    SIGNALSCOPE_USER            Filter by username
    SIGNALSCOPE_LOG_LEVEL       Logging level (default: WARNING)
    SIGNALSCOPE_WEB_HOST        Bind host (default: 0.0.0.0)
    SIGNALSCOPE_WEB_PORT        Bind port (default: 8000)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

import psutil
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from src.collector.process_collector import ProcessCollector
from src.insights.anomaly_detector import AnomalyDetector
from src.insights.daemon_detector import DaemonDetector
from src.insights.memory_detector import MemoryAnomalyDetector
from src.insights.trend_tracker import TrendTracker
from src.insights.zombie_detector import ZombieDetector
from src.models.process import ProcessInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(title="SignalScope", docs_url=None, redoc_url=None)

# Global configuration injected at startup
_config: dict = {}


def _build_pipeline(cfg: dict):
    """Build the collector + analysis pipeline from *cfg*."""
    collector = ProcessCollector(user=cfg.get("user"))
    zombie = ZombieDetector()
    anomaly = AnomalyDetector(cpu_threshold=cfg["cpu_threshold"])
    memory = MemoryAnomalyDetector(mem_threshold=cfg["mem_threshold"])
    trend = TrendTracker(cpu_threshold=cfg["cpu_threshold"])
    daemon = DaemonDetector() if not cfg.get("no_daemon") else None

    def collect_and_analyze() -> List[ProcessInfo]:
        processes = collector.collect()
        zombie.analyze(processes)
        anomaly.analyze(processes)
        memory.analyze(processes)
        trend.analyze(processes)
        if daemon is not None:
            daemon.analyze(processes)
        # Sort by CPU descending and optionally cap
        processes = sorted(processes, key=lambda p: p.cpu_percent, reverse=True)
        top = cfg.get("top")
        if top:
            processes = processes[:top]
        return processes

    return collect_and_analyze


# Lazily initialised pipeline (set up once at first request)
_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = _build_pipeline(_config)
    return _pipeline


# ---------------------------------------------------------------------------
# HTML template (inline — no Jinja2 dependency)
# ---------------------------------------------------------------------------
_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SignalScope — Live Process Monitor</title>
  <style>
    :root {{
      --bg:        #0d1117;
      --surface:   #161b22;
      --border:    #30363d;
      --text:      #c9d1d9;
      --muted:     #8b949e;
      --accent:    #58a6ff;
      --yellow:    #e3b341;
      --magenta:   #bc8cff;
      --red:       #f85149;
      --green:     #3fb950;
      --dim:       #484f58;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
      font-size: 13px;
      min-height: 100vh;
    }}
    header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 12px 20px;
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }}
    header h1 {{
      font-size: 1.1rem;
      color: var(--accent);
      letter-spacing: 0.05em;
    }}
    .badge {{
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 2px 8px;
      font-size: 0.8rem;
      color: var(--muted);
    }}
    .badge span {{ color: var(--text); font-weight: 600; }}
    #status {{
      margin-left: auto;
      font-size: 0.75rem;
    }}
    #status.connected {{ color: var(--green); }}
    #status.disconnected {{ color: var(--red); }}
    .summary {{
      padding: 8px 20px;
      background: var(--bg);
      border-bottom: 1px solid var(--border);
      display: flex;
      gap: 20px;
      flex-wrap: wrap;
      font-size: 0.8rem;
      color: var(--muted);
    }}
    .summary .pill {{
      display: flex;
      align-items: center;
      gap: 4px;
    }}
    .summary .pill .val {{ color: var(--text); font-weight: 600; }}
    .table-wrap {{
      overflow-x: auto;
      padding: 12px 20px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    thead th {{
      text-align: left;
      color: var(--accent);
      border-bottom: 1px solid var(--border);
      padding: 6px 10px;
      white-space: nowrap;
      font-weight: 600;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    tbody tr {{
      border-bottom: 1px solid var(--border);
      transition: background 0.1s;
    }}
    tbody tr:hover {{ background: var(--surface); }}
    td {{
      padding: 5px 10px;
      white-space: nowrap;
      color: var(--text);
    }}
    /* Row colour classes */
    tr.zombie td {{ color: var(--red); font-weight: 700; }}
    tr.high-cpu td {{ color: var(--yellow); }}
    tr.high-mem td {{ color: var(--magenta); }}
    tr.idle td {{ color: var(--dim); }}
    td.insight {{ white-space: normal; max-width: 420px; color: var(--muted); }}
    tr.zombie td.insight, tr.high-cpu td.insight,
    tr.high-mem td.insight {{ color: inherit; }}

    footer {{
      text-align: center;
      padding: 10px;
      color: var(--dim);
      font-size: 0.72rem;
    }}
  </style>
</head>
<body>
  <header>
    <h1>⚡ SignalScope</h1>
    <div class="badge">System CPU: <span id="sys-cpu">—</span></div>
    <div class="badge">RAM: <span id="sys-ram">—</span></div>
    <div class="badge">Refresh: <span>{interval}s</span></div>
    <div id="status" class="disconnected">● Connecting…</div>
  </header>

  <div class="summary">
    <div class="pill">Processes <span class="val" id="cnt-total">—</span></div>
    <div class="pill">🔥 High CPU <span class="val" id="cnt-cpu">0</span></div>
    <div class="pill">🧠 High Mem <span class="val" id="cnt-mem">0</span></div>
    <div class="pill">👻 Zombies <span class="val" id="cnt-zombie">0</span></div>
    <div class="pill">📈 Trends <span class="val" id="cnt-trend">0</span></div>
    <div class="pill">🤖 Daemons <span class="val" id="cnt-daemon">0</span></div>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th style="text-align:right">PID</th>
          <th>Name</th>
          <th style="text-align:right">CPU %&nbsp;↓</th>
          <th style="text-align:right">Mem %</th>
          <th>Status</th>
          <th>Insight</th>
        </tr>
      </thead>
      <tbody id="proc-body">
        <tr><td colspan="6" style="color:var(--muted);text-align:center;padding:20px">Loading…</td></tr>
      </tbody>
    </table>
  </div>

  <footer>SignalScope — real-time process monitor &nbsp;|&nbsp; Press Ctrl+C in terminal to stop the server</footer>

  <script>
    const wsProto = location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl   = `${{wsProto}}://${{location.host}}/ws`;
    let ws, retryDelay = 1000;

    function connect() {{
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {{
        document.getElementById('status').textContent = '● Live';
        document.getElementById('status').className = 'connected';
        retryDelay = 1000;
      }};

      ws.onclose = () => {{
        document.getElementById('status').textContent = '● Reconnecting…';
        document.getElementById('status').className = 'disconnected';
        setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 15000);
      }};

      ws.onerror = () => ws.close();

      ws.onmessage = (ev) => {{
        const data = JSON.parse(ev.data);
        renderSystem(data.system);
        renderSummary(data.summary);
        renderTable(data.processes);
      }};
    }}

    function renderSystem(sys) {{
      document.getElementById('sys-cpu').textContent = sys.cpu + '%';
      document.getElementById('sys-ram').textContent =
        sys.ram_pct + '% (' + sys.ram_used_mb.toLocaleString() + ' / ' + sys.ram_total_mb.toLocaleString() + ' MB)';
    }}

    function renderSummary(s) {{
      document.getElementById('cnt-total').textContent  = s.total;
      document.getElementById('cnt-cpu').textContent    = s.high_cpu;
      document.getElementById('cnt-mem').textContent    = s.high_mem;
      document.getElementById('cnt-zombie').textContent = s.zombies;
      document.getElementById('cnt-trend').textContent  = s.trends;
      document.getElementById('cnt-daemon').textContent = s.daemons;
    }}

    function rowClass(p) {{
      if (p.is_zombie)   return 'zombie';
      if (p.is_high_cpu) return 'high-cpu';
      if (p.is_high_mem) return 'high-mem';
      if (p.cpu_percent < 0.1) return 'idle';
      return '';
    }}

    function renderTable(procs) {{
      const tbody = document.getElementById('proc-body');
      if (!procs.length) {{
        tbody.innerHTML = '<tr><td colspan="6" style="color:var(--muted);text-align:center;padding:20px">No processes found</td></tr>';
        return;
      }}
      tbody.innerHTML = procs.map(p => {{
        const cls = rowClass(p);
        return `<tr class="${{cls}}">
          <td style="text-align:right">${{p.pid}}</td>
          <td>${{esc(p.name)}}</td>
          <td style="text-align:right">${{p.cpu_percent.toFixed(1)}}</td>
          <td style="text-align:right">${{p.memory_percent.toFixed(2)}}</td>
          <td>${{esc(p.status)}}</td>
          <td class="insight">${{esc(p.insight_text)}}</td>
        </tr>`;
      }}).join('');
    }}

    function esc(s) {{
      return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }}

    connect();
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the dashboard HTML."""
    interval = _config.get("interval", 2.0)
    return HTMLResponse(_HTML_TEMPLATE.format(interval=interval))


@app.get("/health")
async def health():
    """Simple health-check endpoint."""
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Stream process snapshots to the browser."""
    await websocket.accept()
    pipeline = _get_pipeline()
    interval = _config.get("interval", 2.0)

    try:
        while True:
            processes = await asyncio.get_event_loop().run_in_executor(None, pipeline)

            # System-level stats
            try:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory()
                system = {
                    "cpu": round(cpu, 1),
                    "ram_pct": round(mem.percent, 1),
                    "ram_used_mb": mem.used // (1024 ** 2),
                    "ram_total_mb": mem.total // (1024 ** 2),
                }
            except Exception:
                system = {"cpu": 0, "ram_pct": 0, "ram_used_mb": 0, "ram_total_mb": 0}

            # Summary counts
            summary = {
                "total": len(processes),
                "zombies": sum(1 for p in processes if p.is_zombie()),
                "high_cpu": sum(1 for p in processes if any("🔥" in i for i in p.insights)),
                "high_mem": sum(1 for p in processes if any("🧠" in i for i in p.insights)),
                "trends": sum(1 for p in processes if any("📈" in i for i in p.insights)),
                "daemons": sum(1 for p in processes if any("🤖" in i for i in p.insights)),
            }

            # Per-process rows
            rows = [
                {
                    "pid": p.pid,
                    "name": p.name,
                    "cpu_percent": p.cpu_percent,
                    "memory_percent": p.memory_percent,
                    "status": p.status,
                    "insight_text": p.insight_text,
                    "is_zombie": p.is_zombie(),
                    "is_high_cpu": any("🔥" in i for i in p.insights),
                    "is_high_mem": any("🧠" in i for i in p.insights),
                }
                for p in processes
            ]

            payload = json.dumps({"system": system, "summary": summary, "processes": rows})
            await websocket.send_text(payload)
            await asyncio.sleep(interval)

    except WebSocketDisconnect:
        logger.debug("WebSocket client disconnected")
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.web.app",
        description="SignalScope web dashboard",
    )
    parser.add_argument("--host", default=os.environ.get("SIGNALSCOPE_WEB_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SIGNALSCOPE_WEB_PORT", "8000")))
    parser.add_argument("--interval", type=float,
                        default=float(os.environ.get("SIGNALSCOPE_INTERVAL", "2.0")))
    parser.add_argument("--top", type=int,
                        default=int(os.environ["SIGNALSCOPE_TOP"]) if os.environ.get("SIGNALSCOPE_TOP") else None)
    parser.add_argument("--cpu-threshold", type=float,
                        default=float(os.environ.get("SIGNALSCOPE_CPU_THRESHOLD", "50.0")))
    parser.add_argument("--mem-threshold", type=float,
                        default=float(os.environ.get("SIGNALSCOPE_MEM_THRESHOLD", "10.0")))
    parser.add_argument("--no-daemon", action="store_true",
                        default=os.environ.get("SIGNALSCOPE_NO_DAEMON", "").lower() in ("true", "1"))
    parser.add_argument("--user", default=os.environ.get("SIGNALSCOPE_USER") or None)
    parser.add_argument("--log-level", default=os.environ.get("SIGNALSCOPE_LOG_LEVEL", "WARNING"),
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Populate global config
    _config.update({
        "interval": args.interval,
        "top": args.top,
        "cpu_threshold": args.cpu_threshold,
        "mem_threshold": args.mem_threshold,
        "no_daemon": args.no_daemon,
        "user": args.user,
    })

    print(f"SignalScope web dashboard → http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())
