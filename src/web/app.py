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
import secrets
import sys
from pathlib import Path
from typing import List, Optional

import psutil
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from src.actions.process_killer import ProcessKiller
from src.collector.process_collector import ProcessCollector
from src.insights.anomaly_detector import AnomalyDetector
from src.insights.daemon_detector import DaemonDetector
from src.insights.memory_detector import MemoryAnomalyDetector
from src.insights.trend_tracker import TrendTracker
from src.insights.zombie_detector import ZombieDetector
from src.models.process import ProcessInfo
from src.storage.metrics_store import MetricsStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(title="SignalScope", docs_url=None, redoc_url=None)

# Global configuration injected at startup
_config: dict = {}

# Metrics store (lazily initialised)
_metrics_store: Optional[MetricsStore] = None
_seen_anomalies: set = set()

# Notifier (lazily initialised)
_notifier = None
_seen_notify: set = set()

# HTTP Basic Auth
_security = HTTPBasic(auto_error=False)


def _get_metrics_store() -> MetricsStore:
    global _metrics_store
    if _metrics_store is None:
        db_path = _config.get(
            "db",
            str(Path.home() / ".signalscope" / "metrics.db"),
        )
        retention_days = _config.get("retention_days", 7)
        _metrics_store = MetricsStore(db_path=db_path, retention_days=retention_days)
    return _metrics_store


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


def _get_notifier():
    global _notifier
    if _notifier is None:
        from src.notifications.notifier import Notifier, SlackNotifier, GenericWebhookNotifier
        cooldown = _config.get("notify_cooldown", 300)
        n = Notifier(cooldown_seconds=cooldown)
        slack_url = _config.get("slack_webhook", "")
        webhook_url = _config.get("webhook_url", "")
        if slack_url:
            n.add_channel(SlackNotifier(slack_url))
        if webhook_url:
            n.add_channel(GenericWebhookNotifier(webhook_url))
        _notifier = n
    return _notifier


def _check_auth(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    """HTTP Basic Auth dependency. Returns username on success."""
    if _config.get("no_auth"):
        return ""
    expected_user = _config.get("web_user", "admin")
    expected_pass = _config.get("web_password", "")
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"},
        )
    user_ok = secrets.compare_digest(
        credentials.username.encode(), expected_user.encode()
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode(), expected_pass.encode()
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ---------------------------------------------------------------------------
# Signal request model
# ---------------------------------------------------------------------------


class SignalRequest(BaseModel):
    signal: str  # "SIGTERM" or "SIGKILL"


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

    /* Kill button */
    .kill-btn {{
      background: none;
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--muted);
      cursor: pointer;
      font-size: 1rem;
      padding: 1px 6px;
      transition: border-color 0.15s, color 0.15s;
    }}
    .kill-btn:hover {{ border-color: var(--red); color: var(--red); }}

    /* Modal overlay */
    #kill-modal {{
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.7);
      z-index: 100;
      align-items: center;
      justify-content: center;
    }}
    #kill-modal.open {{ display: flex; }}
    .modal-box {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 24px 28px;
      min-width: 360px;
      max-width: 480px;
      width: 100%;
    }}
    .modal-box h2 {{ color: var(--accent); margin-bottom: 4px; }}
    .modal-box .meta {{ color: var(--muted); font-size: 0.8rem; margin-bottom: 12px; }}
    .modal-box .banner {{
      border-radius: 4px;
      padding: 8px 12px;
      margin-bottom: 12px;
      font-size: 0.82rem;
      font-weight: 600;
    }}
    .banner.danger {{ background: rgba(248,81,73,0.15); border: 1px solid var(--red); color: var(--red); }}
    .banner.warn   {{ background: rgba(227,179,65,0.15); border: 1px solid var(--yellow); color: var(--yellow); }}
    .modal-actions {{ display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap; }}
    .btn {{
      border: none; border-radius: 4px; cursor: pointer;
      font-family: inherit; font-size: 0.82rem;
      padding: 6px 14px; font-weight: 600;
    }}
    .btn-term  {{ background: var(--green);  color: #000; }}
    .btn-kill  {{ background: var(--red);    color: #fff; }}
    .btn-cancel{{ background: var(--surface); border: 1px solid var(--border); color: var(--muted); }}
    .confirm-wrap {{ margin-top: 12px; display: none; }}
    .confirm-wrap label {{ display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 4px; }}
    .confirm-wrap input {{
      width: 100%; background: var(--bg); border: 1px solid var(--border);
      border-radius: 4px; color: var(--text); font-family: inherit;
      font-size: 0.82rem; padding: 5px 8px;
    }}

    /* Toast */
    #toast {{
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px 18px;
      font-size: 0.82rem;
      z-index: 200;
      opacity: 0;
      transition: opacity 0.3s;
      pointer-events: none;
    }}
    #toast.show {{ opacity: 1; }}
    #toast.success {{ border-color: var(--green); color: var(--green); }}
    #toast.error   {{ border-color: var(--red);   color: var(--red);   }}

    footer {{
      text-align: center;
      padding: 10px;
      color: var(--dim);
      font-size: 0.72rem;
    }}

    /* Main layout */
    .main-layout {{
      display: flex;
      min-height: 0;
    }}
    .main-content {{
      flex: 1;
      min-width: 0;
      overflow-x: auto;
    }}

    /* Anomaly sidebar */
    .anomaly-sidebar {{
      width: 300px;
      min-width: 300px;
      border-left: 1px solid var(--border);
      background: var(--surface);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}
    .sidebar-header {{
      padding: 8px 12px;
      border-bottom: 1px solid var(--border);
      font-size: 0.78rem;
      font-weight: 600;
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      flex-shrink: 0;
    }}
    #anomaly-list {{
      overflow-y: auto;
      flex: 1;
    }}
    .anomaly-item {{
      padding: 6px 12px;
      border-bottom: 1px solid var(--border);
      font-size: 0.78rem;
      cursor: default;
    }}
    .anomaly-item .a-time {{ color: var(--muted); font-size: 0.7rem; display: block; }}
    .anomaly-item .a-name {{ color: var(--text); font-weight: 600; }}
    .anomaly-item .a-detail {{ color: var(--muted); display: block; white-space: normal; word-break: break-word; }}

    /* Row clickable */
    tbody tr {{ cursor: pointer; }}

    /* Detail drawer */
    #detail-drawer {{
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.72);
      z-index: 90;
      align-items: flex-end;
      justify-content: center;
    }}
    #detail-drawer.open {{ display: flex; }}
    .drawer-box {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px 8px 0 0;
      width: 100%;
      max-width: 820px;
      max-height: 72vh;
      display: flex;
      flex-direction: column;
    }}
    .drawer-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      border-bottom: 1px solid var(--border);
      flex-shrink: 0;
    }}
    .drawer-header h3 {{ color: var(--accent); font-size: 1rem; }}
    .drawer-close {{
      background: none; border: none; color: var(--muted);
      cursor: pointer; font-size: 1.2rem; padding: 2px 6px;
    }}
    .drawer-close:hover {{ color: var(--text); }}
    .drawer-body {{
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .drawer-chart-wrap {{
      height: 200px;
      position: relative;
    }}
    .drawer-section-title {{
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 6px;
    }}
    .d-anomaly-item {{
      font-size: 0.78rem;
      padding: 4px 0;
      border-bottom: 1px solid var(--border);
      color: var(--muted);
    }}
    .d-anomaly-item .da-time {{ color: var(--dim); margin-right: 6px; }}
    .drawer-kill-actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
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

  <div class="main-layout">
    <div class="main-content">
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
              <th>Action</th>
            </tr>
          </thead>
          <tbody id="proc-body">
            <tr><td colspan="7" style="color:var(--muted);text-align:center;padding:20px">Loading…</td></tr>
          </tbody>
        </table>
      </div>
    </div>
    <aside class="anomaly-sidebar">
      <div class="sidebar-header">Recent Anomalies</div>
      <div id="anomaly-list">
        <div style="padding:12px;color:var(--muted);font-size:0.8rem">Loading…</div>
      </div>
    </aside>
  </div>

  <!-- Detail drawer -->
  <div id="detail-drawer">
    <div class="drawer-box">
      <div class="drawer-header">
        <h3 id="d-title">Process Details</h3>
        <button class="drawer-close" onclick="closeDrawer()">✕</button>
      </div>
      <div class="drawer-body">
        <div>
          <div class="drawer-section-title">CPU &amp; Memory — Last 60 min</div>
          <div class="drawer-chart-wrap">
            <canvas id="sparkline-canvas"></canvas>
          </div>
        </div>
        <div>
          <div class="drawer-section-title">Anomaly Events</div>
          <div id="d-anomaly-list" style="font-size:0.8rem;color:var(--muted)">Loading…</div>
        </div>
        <div class="drawer-kill-actions">
          <button class="btn btn-term"   onclick="drawerDoSignal('SIGTERM')">Send SIGTERM</button>
          <button class="btn btn-kill"   onclick="drawerInitKill()">Force Kill (SIGKILL)</button>
          <button class="btn btn-cancel" onclick="closeDrawer()">Close</button>
        </div>
        <div class="confirm-wrap" id="drawer-confirm-wrap">
          <label id="drawer-confirm-label">Type process name to confirm:</label>
          <input id="drawer-confirm-input" type="text" placeholder="" />
          <div class="modal-actions" style="margin-top:8px">
            <button class="btn btn-kill"   onclick="drawerDoSignal('SIGKILL')">Confirm SIGKILL</button>
            <button class="btn btn-cancel" onclick="drawerCancelKill()">Cancel</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Kill modal -->
  <div id="kill-modal">
    <div class="modal-box">
      <h2 id="m-name">—</h2>
      <div class="meta" id="m-meta">—</div>
      <div id="m-banner-risk"  class="banner danger" style="display:none">⚠ WARNING: This appears to be a system/privileged process. Killing it may destabilise your system.</div>
      <div id="m-banner-zombie" class="banner warn"  style="display:none">⚠ Zombie process — signal the parent instead.</div>
      <div class="modal-actions">
        <button class="btn btn-term"   id="btn-sigterm"  onclick="doSignal('SIGTERM')">Send SIGTERM</button>
        <button class="btn btn-kill"   id="btn-sigkill"  onclick="initKill()">Force Kill SIGKILL</button>
        <button class="btn btn-cancel" onclick="closeModal()">Cancel</button>
      </div>
      <div class="confirm-wrap" id="confirm-wrap">
        <label id="confirm-label">Type process name to confirm:</label>
        <input id="confirm-input" type="text" placeholder="" />
        <div class="modal-actions" style="margin-top:8px">
          <button class="btn btn-kill" onclick="doSignal('SIGKILL')">Confirm SIGKILL</button>
          <button class="btn btn-cancel" onclick="cancelKill()">Cancel</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Toast -->
  <div id="toast"></div>

  <footer>SignalScope — real-time process monitor &nbsp;|&nbsp; Press Ctrl+C in terminal to stop the server</footer>

  <script>
    const wsProto = location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl   = `${{wsProto}}://${{location.host}}/ws`;
    let ws, retryDelay = 1000;
    let _modalPid = null, _modalName = null;

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
        tbody.innerHTML = '<tr><td colspan="7" style="color:var(--muted);text-align:center;padding:20px">No processes found</td></tr>';
        return;
      }}
      tbody.innerHTML = procs.map(p => {{
        const cls = rowClass(p);
        return `<tr class="${{cls}}" id="row-${{p.pid}}" onclick="openDrawer(event,${{p.pid}},'${{esc(p.name)}}')">
          <td style="text-align:right">${{p.pid}}</td>
          <td>${{esc(p.name)}}</td>
          <td style="text-align:right">${{p.cpu_percent.toFixed(1)}}</td>
          <td style="text-align:right">${{p.memory_percent.toFixed(2)}}</td>
          <td>${{esc(p.status)}}</td>
          <td class="insight">${{esc(p.insight_text)}}</td>
          <td><button class="kill-btn" data-pid="${{p.pid}}" data-name="${{esc(p.name)}}" onclick="event.stopPropagation();openModal(this)">⚡</button></td>
        </tr>`;
      }}).join('');
    }}

    function esc(s) {{
      return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }}

    async function openModal(btn) {{
      const pid  = btn.getAttribute('data-pid');
      const name = btn.getAttribute('data-name');
      _modalPid  = pid;
      _modalName = name;

      document.getElementById('m-name').textContent = name;
      document.getElementById('m-meta').textContent = 'PID ' + pid + ' — loading…';
      document.getElementById('m-banner-risk').style.display  = 'none';
      document.getElementById('m-banner-zombie').style.display = 'none';
      document.getElementById('confirm-wrap').style.display   = 'none';
      document.getElementById('confirm-input').value = '';
      document.getElementById('kill-modal').className = 'open';

      try {{
        const resp = await fetch('/api/process/' + pid + '/info');
        if (!resp.ok) {{
          document.getElementById('m-meta').textContent = 'PID ' + pid + ' (process gone)';
          return;
        }}
        const info = await resp.json();
        document.getElementById('m-meta').textContent =
          'PID ' + pid +
          ' | CPU: ' + (info.cpu_percent || 0).toFixed(1) + '%' +
          ' | Mem: ' + (info.memory_percent || 0).toFixed(2) + '%' +
          (info.insight_text && info.insight_text !== '—' ? ' | ' + info.insight_text : '');
        if (info.is_zombie) {{
          document.getElementById('m-banner-zombie').style.display = 'block';
        }}
        if (info.high_risk) {{
          document.getElementById('m-banner-risk').style.display = 'block';
        }}
      }} catch(e) {{
        document.getElementById('m-meta').textContent = 'PID ' + pid;
      }}
    }}

    function closeModal() {{
      document.getElementById('kill-modal').className = '';
      _modalPid = null; _modalName = null;
    }}

    function initKill() {{
      const wrap = document.getElementById('confirm-wrap');
      wrap.style.display = 'block';
      document.getElementById('confirm-label').textContent = "Type process name '" + _modalName + "' to confirm:";
      document.getElementById('confirm-input').placeholder = _modalName;
      document.getElementById('confirm-input').focus();
    }}

    function cancelKill() {{
      document.getElementById('confirm-wrap').style.display = 'none';
      document.getElementById('confirm-input').value = '';
    }}

    async function doSignal(sig) {{
      if (sig === 'SIGKILL') {{
        const typed = document.getElementById('confirm-input').value.trim();
        if (typed !== _modalName) {{
          showToast('Confirmation failed — action cancelled.', 'error');
          closeModal();
          return;
        }}
      }}
      const pid = _modalPid, name = _modalName;
      closeModal();
      try {{
        const resp = await fetch('/api/process/' + pid + '/signal', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{signal: sig}})
        }});
        const data = await resp.json();
        if (resp.ok && data.success) {{
          showToast('PID ' + pid + ' (' + name + ') terminated successfully.', 'success');
          const row = document.getElementById('row-' + pid);
          if (row) row.style.opacity = '0.3';
        }} else {{
          showToast(data.message || 'Signal failed.', 'error');
        }}
      }} catch(e) {{
        showToast('Request failed: ' + e, 'error');
      }}
    }}

    let _toastTimer = null;
    function showToast(msg, type) {{
      const el = document.getElementById('toast');
      el.textContent = msg;
      el.className = 'show ' + (type || '');
      if (_toastTimer) clearTimeout(_toastTimer);
      _toastTimer = setTimeout(() => {{ el.className = ''; }}, 3000);
    }}

    // ------------------------------------------------------------------
    // Anomaly sidebar
    // ------------------------------------------------------------------
    async function fetchAnomalies() {{
      try {{
        const resp = await fetch('/api/anomalies?limit=20');
        if (!resp.ok) return;
        const items = await resp.json();
        const el = document.getElementById('anomaly-list');
        if (!items.length) {{
          el.innerHTML = '<div style="padding:12px;color:var(--muted);font-size:0.8rem">No anomalies recorded yet.</div>';
          return;
        }}
        el.innerHTML = items.map(a => {{
          const t = (a.occurred_at || '').replace('T', ' ').substring(0, 19);
          return `<div class="anomaly-item">
            <span class="a-time">${{esc(t)}} UTC</span>
            <span class="a-name">${{esc(a.name)}} <span style="color:var(--muted)">(PID ${{a.pid}})</span></span>
            <span class="a-detail">${{esc(a.detail || a.event_type)}}</span>
          </div>`;
        }}).join('');
      }} catch(e) {{
        /* silent */
      }}
    }}

    // ------------------------------------------------------------------
    // Detail drawer
    // ------------------------------------------------------------------
    let _drawerPid = null, _drawerName = null;
    let _sparkChart = null;

    async function openDrawer(event, pid, name) {{
      _drawerPid = pid; _drawerName = name;
      document.getElementById('d-title').textContent = name + ' (PID ' + pid + ')';
      document.getElementById('d-anomaly-list').textContent = 'Loading…';
      document.getElementById('drawer-confirm-wrap').style.display = 'none';
      document.getElementById('drawer-confirm-input').value = '';
      document.getElementById('detail-drawer').className = 'open';

      // Fetch history for sparkline
      try {{
        const resp = await fetch('/api/history/' + pid + '?hours=1');
        const rows = resp.ok ? await resp.json() : [];
        renderSparkline(rows);
      }} catch(e) {{ renderSparkline([]); }}

      // Fetch anomalies for this pid
      try {{
        const resp = await fetch('/api/anomalies?limit=100');
        const all  = resp.ok ? await resp.json() : [];
        const mine = all.filter(a => a.pid === pid);
        const el   = document.getElementById('d-anomaly-list');
        if (!mine.length) {{
          el.textContent = 'No anomaly events recorded for this process.';
        }} else {{
          el.innerHTML = mine.map(a => {{
            const t = (a.occurred_at || '').replace('T',' ').substring(0,19);
            return `<div class="d-anomaly-item"><span class="da-time">${{esc(t)}}</span>${{esc(a.detail || a.event_type)}}</div>`;
          }}).join('');
        }}
      }} catch(e) {{
        document.getElementById('d-anomaly-list').textContent = 'Could not load anomalies.';
      }}
    }}

    function renderSparkline(rows) {{
      const canvas = document.getElementById('sparkline-canvas');
      if (_sparkChart) {{ _sparkChart.destroy(); _sparkChart = null; }}
      const labels = rows.map(r => (r.captured_at || '').substring(11,19));
      const cpuData = rows.map(r => r.cpu_percent ?? null);
      const memData = rows.map(r => r.memory_percent ?? null);
      _sparkChart = new Chart(canvas, {{
        type: 'line',
        data: {{
          labels,
          datasets: [
            {{
              label: 'CPU %',
              data: cpuData,
              borderColor: '#e3b341',
              backgroundColor: 'rgba(227,179,65,0.1)',
              tension: 0.3,
              pointRadius: 0,
              borderWidth: 2,
            }},
            {{
              label: 'Mem %',
              data: memData,
              borderColor: '#bc8cff',
              backgroundColor: 'rgba(188,140,255,0.1)',
              tension: 0.3,
              pointRadius: 0,
              borderWidth: 2,
            }},
          ],
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{ legend: {{ labels: {{ color: '#c9d1d9', font: {{ size: 11 }} }} }} }},
          scales: {{
            x: {{ ticks: {{ color: '#8b949e', maxTicksLimit: 8, font: {{ size: 10 }} }}, grid: {{ color: '#30363d' }} }},
            y: {{ ticks: {{ color: '#8b949e', font: {{ size: 10 }} }}, grid: {{ color: '#30363d' }} }},
          }},
        }},
      }});
    }}

    function closeDrawer() {{
      document.getElementById('detail-drawer').className = '';
      _drawerPid = null; _drawerName = null;
      if (_sparkChart) {{ _sparkChart.destroy(); _sparkChart = null; }}
    }}

    async function drawerDoSignal(sig) {{
      if (sig === 'SIGKILL') {{
        const typed = document.getElementById('drawer-confirm-input').value.trim();
        if (typed !== _drawerName) {{
          showToast('Confirmation failed — action cancelled.', 'error');
          closeDrawer();
          return;
        }}
      }}
      const pid = _drawerPid, name = _drawerName;
      closeDrawer();
      try {{
        const resp = await fetch('/api/process/' + pid + '/signal', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{signal: sig}}),
        }});
        const data = await resp.json();
        if (resp.ok && data.success) {{
          showToast('PID ' + pid + ' (' + name + ') terminated successfully.', 'success');
          const row = document.getElementById('row-' + pid);
          if (row) row.style.opacity = '0.3';
        }} else {{
          showToast(data.message || 'Signal failed.', 'error');
        }}
      }} catch(e) {{
        showToast('Request failed: ' + e, 'error');
      }}
    }}

    function drawerInitKill() {{
      const wrap = document.getElementById('drawer-confirm-wrap');
      wrap.style.display = 'block';
      document.getElementById('drawer-confirm-label').textContent = "Type process name '" + _drawerName + "' to confirm:";
      document.getElementById('drawer-confirm-input').placeholder = _drawerName;
      document.getElementById('drawer-confirm-input').focus();
    }}

    function drawerCancelKill() {{
      document.getElementById('drawer-confirm-wrap').style.display = 'none';
      document.getElementById('drawer-confirm-input').value = '';
    }}

    connect();
    fetchAnomalies();
    setInterval(fetchAnomalies, 10000);
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, dependencies=[Depends(_check_auth)])
async def index():
    """Serve the dashboard HTML."""
    interval = _config.get("interval", 2.0)
    return HTMLResponse(_HTML_TEMPLATE.format(interval=interval))


@app.get("/health", dependencies=[Depends(_check_auth)])
async def health():
    """Simple health-check endpoint."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Process action endpoints
# ---------------------------------------------------------------------------

@app.post("/api/process/{pid}/signal", dependencies=[Depends(_check_auth)])
async def signal_process(pid: int, req: SignalRequest):
    """Send SIGTERM or SIGKILL to a process and return the ActionResult."""
    if req.signal not in ("SIGTERM", "SIGKILL"):
        raise HTTPException(status_code=422, detail="signal must be 'SIGTERM' or 'SIGKILL'")
    killer = ProcessKiller()
    if req.signal == "SIGTERM":
        result = await asyncio.get_event_loop().run_in_executor(None, killer.send_sigterm, pid)
    else:
        result = await asyncio.get_event_loop().run_in_executor(None, killer.send_sigkill, pid)
    return {
        "pid": result.pid,
        "signal_sent": result.signal_sent,
        "success": result.success,
        "message": result.message,
        "timestamp": result.timestamp,
        "high_risk": result.high_risk,
        "process_name": result.process_name,
    }


@app.get("/api/process/{pid}/info", dependencies=[Depends(_check_auth)])
async def process_info(pid: int):
    """Return current snapshot info for a single PID."""
    if not psutil.pid_exists(pid):
        raise HTTPException(status_code=404, detail=f"PID {pid} not found")
    try:
        p = psutil.Process(pid)
        info = p.as_dict(attrs=["pid", "name", "cpu_percent", "memory_percent",
                                 "status", "ppid"])
        is_zombie = info.get("status") == "zombie"
        high_risk = ProcessKiller._is_high_risk(p)
        return {
            "pid": info.get("pid"),
            "name": info.get("name", ""),
            "cpu_percent": info.get("cpu_percent", 0.0),
            "memory_percent": info.get("memory_percent", 0.0),
            "status": info.get("status", ""),
            "ppid": info.get("ppid"),
            "is_zombie": is_zombie,
            "high_risk": high_risk,
            "insight_text": "—",
        }
    except psutil.NoSuchProcess:
        raise HTTPException(status_code=404, detail=f"PID {pid} not found")


# ---------------------------------------------------------------------------
# Metrics persistence endpoints
# ---------------------------------------------------------------------------

@app.get("/api/history/{pid}", dependencies=[Depends(_check_auth)])
async def get_history(pid: int, hours: float = 1.0):
    """Return CPU/memory timeseries for a PID over the last N hours."""
    store = _get_metrics_store()
    return store.get_process_history(pid, hours=hours)


@app.get("/api/anomalies", dependencies=[Depends(_check_auth)])
async def get_anomalies(limit: int = 50):
    """Return the most recent anomaly events."""
    store = _get_metrics_store()
    return store.get_recent_anomalies(limit=limit)


@app.get("/api/top-offenders", dependencies=[Depends(_check_auth)])
async def get_top_offenders(hours: float = 24.0, metric: str = "cpu"):
    """Return processes ranked by average CPU or memory over the time window."""
    store = _get_metrics_store()
    return store.get_top_offenders(hours=hours, metric=metric)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Stream process snapshots to the browser."""
    await websocket.accept()
    pipeline = _get_pipeline()
    interval = _config.get("interval", 2.0)

    try:
        while True:
            processes = await asyncio.get_event_loop().run_in_executor(None, pipeline)

            # Persist snapshot and new anomaly insights
            try:
                store = _get_metrics_store()
                store.record_snapshot(processes)
                for p in processes:
                    for insight in p.insights:
                        key = (p.pid, insight)
                        if key not in _seen_anomalies:
                            _seen_anomalies.add(key)
                            store.record_anomaly(p.pid, p.name, "insight", insight)
            except Exception as _exc:
                logger.debug("MetricsStore error: %s", _exc)

            # Dispatch notifications for new anomalies
            try:
                from src.notifications.notifier import AnomalyEvent
                notifier = _get_notifier()
                for p in processes:
                    for insight in p.insights:
                        key = (p.pid, insight)
                        if key not in _seen_notify:
                            _seen_notify.add(key)
                            from src.main import _insight_to_event_type
                            notifier.notify(AnomalyEvent(
                                pid=p.pid, name=p.name,
                                event_type=_insight_to_event_type(insight),
                                detail=insight,
                            ))
            except Exception as _exc:
                logger.debug("Notifier error: %s", _exc)

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
# Agent signal endpoint (accepts commands from collector)
# ---------------------------------------------------------------------------

@app.post("/signal")
async def agent_signal_endpoint(request: Request):
    """Accept signal commands from a collector (agent mode)."""
    agent_secret = _config.get("agent_secret", "")
    if agent_secret:
        incoming = request.headers.get("X-Agent-Secret", "")
        if not incoming or not secrets.compare_digest(agent_secret.encode(), incoming.encode()):
            raise HTTPException(status_code=403, detail="Invalid agent secret")
    body = await request.json()
    pid = body.get("pid")
    sig = body.get("signal", "SIGTERM")
    if not pid:
        raise HTTPException(status_code=400, detail="pid required")
    from src.actions.process_killer import ProcessKiller
    killer = ProcessKiller()
    if sig == "SIGKILL":
        result = killer.send_sigkill(int(pid))
    else:
        result = killer.send_sigterm(int(pid))
    return result.__dict__


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
        "--no-auth",
        action="store_true",
        default=os.environ.get("SIGNALSCOPE_NO_AUTH", "").lower() in ("true", "1"),
        help="Disable HTTP Basic Auth for the web dashboard",
    )
    parser.add_argument(
        "--web-user",
        default=os.environ.get("SIGNALSCOPE_WEB_USER", "admin"),
        help="Web dashboard username (default: admin)",
    )
    parser.add_argument(
        "--web-password",
        default=os.environ.get("SIGNALSCOPE_WEB_PASSWORD", ""),
        help="Web dashboard password",
    )
    parser.add_argument(
        "--agent-secret",
        default=os.environ.get("SIGNALSCOPE_AGENT_SECRET", ""),
        metavar="STR",
        help="Shared secret for agent/collector authentication",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Password generation logic
    web_password = args.web_password
    if not web_password and not args.no_auth:
        creds_file = Path.home() / ".signalscope" / "web_credentials"
        creds_file.parent.mkdir(parents=True, exist_ok=True)
        if creds_file.exists():
            stored = creds_file.read_text().strip().splitlines()
            for line in stored:
                if ":" in line:
                    _, web_password = line.split(":", 1)
                    break
        if not web_password:
            import string
            alphabet = string.ascii_letters + string.digits
            web_password = "".join(secrets.choice(alphabet) for _ in range(16))
            creds_file.write_text(f"{args.web_user}:{web_password}\n")
            print("┌─────────────────────────────────────────┐")
            print("│  Web dashboard password (one-time):     │")
            print(f"│  user: {args.web_user:<8}  password: {web_password:<16} │")
            print("│  Set SIGNALSCOPE_WEB_PASSWORD to fix.  │")
            print("└─────────────────────────────────────────┘")

    # Populate global config
    _config.update({
        "interval": args.interval,
        "top": args.top,
        "cpu_threshold": args.cpu_threshold,
        "mem_threshold": args.mem_threshold,
        "no_daemon": args.no_daemon,
        "user": args.user,
        "db": args.db,
        "retention_days": args.retention_days,
        "slack_webhook": args.slack_webhook,
        "webhook_url": args.webhook_url,
        "notify_cooldown": args.notify_cooldown,
        "web_user": args.web_user,
        "web_password": web_password,
        "no_auth": args.no_auth,
        "agent_secret": args.agent_secret,
    })

    print(f"SignalScope web dashboard → http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())
