"""Tests for multi-host agent and collector modes."""

import json
from unittest.mock import patch, MagicMock
import pytest
from src.web.collector_app import create_collector_app
from fastapi.testclient import TestClient


@pytest.fixture
def collector_client():
    app = create_collector_app(args=None)
    return TestClient(app)


class TestCollectorApp:
    def test_health(self, collector_client):
        resp = collector_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_ingest_and_list(self, collector_client):
        payload = {
            "agent_id": "test-agent-1",
            "host": "myhost",
            "captured_at": "2024-01-01T00:00:00",
            "processes": [{"pid": 1, "name": "init", "cpu_percent": 0.1, "memory_percent": 0.5, "status": "sleeping", "insights": []}],
        }
        resp = collector_client.post("/ingest", json=payload)
        assert resp.status_code == 200

        agents = collector_client.get("/agents").json()
        assert any(a["agent_id"] == "test-agent-1" for a in agents)

    def test_ingest_wrong_secret(self):
        from unittest.mock import MagicMock
        mock_args = MagicMock()
        mock_args.agent_secret = "mysecret"
        _app = create_collector_app(mock_args)
        client = TestClient(_app)
        resp = client.post("/ingest", json={"agent_id": "x"}, headers={"X-Agent-Secret": "wrong"})
        assert resp.status_code == 403

    def test_agent_processes_not_found(self, collector_client):
        resp = collector_client.get("/agents/nonexistent/processes")
        assert resp.status_code == 404

    def test_collector_index(self, collector_client):
        resp = collector_client.get("/")
        assert resp.status_code == 200
        assert b"SignalScope" in resp.content


class TestAgentId:
    def test_get_or_create_agent_id(self, tmp_path):
        import uuid
        from src.main import _get_or_create_agent_id
        with patch('pathlib.Path.home', return_value=tmp_path):
            agent_id1 = _get_or_create_agent_id()
            agent_id2 = _get_or_create_agent_id()
        assert agent_id1 == agent_id2
        assert len(agent_id1) == 36  # UUID format
        uuid.UUID(agent_id1)  # Raises ValueError if not a valid UUID
