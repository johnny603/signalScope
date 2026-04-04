"""SignalScope multi-host collector server."""

import json
import logging
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)

# In-memory store: agent_id -> list of snapshot dicts (last N)
_agent_snapshots: Dict[str, List[Dict]] = {}
_MAX_SNAPSHOTS_PER_AGENT = 300  # ~10 min at 2s interval


def create_collector_app(args=None) -> FastAPI:
    agent_secret = (args.agent_secret if args and hasattr(args, 'agent_secret') else None) or os.environ.get("SIGNALSCOPE_AGENT_SECRET", "")
    app = FastAPI(title="SignalScope Collector", docs_url=None, redoc_url=None)

    @app.post("/ingest")
    async def ingest(request: Request, x_agent_secret: str = Header(default="")):
        if agent_secret and (not x_agent_secret or not secrets.compare_digest(agent_secret.encode(), x_agent_secret.encode())):
            raise HTTPException(status_code=403, detail="Invalid agent secret")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        agent_id = body.get("agent_id", "unknown")
        if agent_id not in _agent_snapshots:
            _agent_snapshots[agent_id] = []
        _agent_snapshots[agent_id].append(body)
        # Keep only last N
        if len(_agent_snapshots[agent_id]) > _MAX_SNAPSHOTS_PER_AGENT:
            _agent_snapshots[agent_id] = _agent_snapshots[agent_id][-_MAX_SNAPSHOTS_PER_AGENT:]

        logger.debug("Received snapshot from agent %s (host=%s, processes=%d)",
                     agent_id, body.get("host"), len(body.get("processes", [])))
        return {"status": "ok"}

    @app.get("/agents")
    async def list_agents():
        """List all known agents with their last snapshot metadata."""
        return [
            {
                "agent_id": aid,
                "host": snaps[-1].get("host"),
                "last_seen": snaps[-1].get("captured_at"),
                "process_count": len(snaps[-1].get("processes", [])),
                "snapshots": len(snaps),
            }
            for aid, snaps in _agent_snapshots.items()
            if snaps
        ]

    @app.get("/agents/{agent_id}/processes")
    async def agent_processes(agent_id: str):
        if agent_id not in _agent_snapshots or not _agent_snapshots[agent_id]:
            raise HTTPException(status_code=404, detail="Agent not found")
        latest = _agent_snapshots[agent_id][-1]
        return latest

    @app.post("/agents/{agent_id}/signal")
    async def agent_signal(agent_id: str, request: Request, x_agent_secret: str = Header(default="")):
        """Forward a signal request to the agent's /signal endpoint (if configured)."""
        if agent_secret and (not x_agent_secret or not secrets.compare_digest(agent_secret.encode(), x_agent_secret.encode())):
            raise HTTPException(status_code=403, detail="Invalid agent secret")
        # Full proxy requires knowing the agent's address.
        raise HTTPException(status_code=501, detail="Signal forwarding not yet configured")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        """Unified multi-host dashboard."""
        agents_data = json.dumps([
            {
                "agent_id": aid,
                "host": snaps[-1].get("host", aid),
                "last_seen": snaps[-1].get("captured_at", ""),
                "processes": snaps[-1].get("processes", []),
            }
            for aid, snaps in _agent_snapshots.items()
            if snaps
        ])
        return HTMLResponse(_COLLECTOR_HTML.replace("__AGENTS_DATA__", agents_data))

    @app.get("/health")
    async def health():
        return {"status": "ok", "agents": len(_agent_snapshots)}

    return app


_COLLECTOR_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>SignalScope Collector</title>
  <meta http-equiv="refresh" content="5">
  <style>
    body { background:#0d1117; color:#c9d1d9; font-family:monospace; padding:20px; }
    h1 { color:#58a6ff; }
    h2 { color:#e3b341; margin-top:20px; }
    table { border-collapse:collapse; width:100%; margin-bottom:20px; }
    th { color:#58a6ff; border-bottom:1px solid #30363d; padding:6px 10px; text-align:left; }
    td { padding:5px 10px; border-bottom:1px solid #21262d; }
    .agent-card { background:#161b22; border:1px solid #30363d; border-radius:6px; padding:12px; margin-bottom:16px; }
  </style>
</head>
<body>
  <h1>⚡ SignalScope — Multi-Host Collector</h1>
  <p style="color:#8b949e">Auto-refreshes every 5 seconds.</p>
  <div id="content">Loading…</div>
  <script>
    const agents = __AGENTS_DATA__;
    const content = document.getElementById('content');
    if (!agents.length) {
      content.innerHTML = '<p style="color:#8b949e">No agents connected yet.</p>';
    } else {
      content.innerHTML = agents.map(a => `
        <div class="agent-card">
          <h2>${a.host} <small style="color:#8b949e;font-size:0.8em">(${a.agent_id})</small></h2>
          <p style="color:#8b949e">Last seen: ${a.last_seen}</p>
          <table>
            <tr><th>PID</th><th>Name</th><th>CPU%</th><th>Mem%</th><th>Status</th><th>Insights</th></tr>
            ${a.processes.slice(0, 30).map(p => `
              <tr>
                <td>${p.pid}</td>
                <td>${p.name}</td>
                <td>${p.cpu_percent.toFixed(1)}</td>
                <td>${p.memory_percent.toFixed(2)}</td>
                <td>${p.status}</td>
                <td>${(p.insights||[]).join(', ') || '—'}</td>
              </tr>
            `).join('')}
          </table>
        </div>
      `).join('');
    }
  </script>
</body>
</html>
"""
