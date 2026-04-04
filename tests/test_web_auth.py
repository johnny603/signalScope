"""Tests for web dashboard authentication."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from src.web import app as web_module


@pytest.fixture(autouse=True)
def reset_config():
    """Isolate config changes between tests."""
    original = dict(web_module._config)
    yield
    web_module._config.clear()
    web_module._config.update(original)


@pytest.fixture
def auth_client():
    web_module._config.update({
        "web_user": "admin",
        "web_password": "secret",
        "no_auth": False,
        "interval": 2.0,
        "cpu_threshold": 50.0,
        "mem_threshold": 10.0,
    })
    return TestClient(web_module.app, raise_server_exceptions=False)


@pytest.fixture
def noauth_client():
    web_module._config.update({
        "no_auth": True,
        "interval": 2.0,
        "cpu_threshold": 50.0,
        "mem_threshold": 10.0,
    })
    return TestClient(web_module.app, raise_server_exceptions=False)


class TestWebAuth:
    def test_unauthenticated_returns_401(self, auth_client):
        resp = auth_client.get("/health")
        assert resp.status_code == 401

    def test_wrong_password_returns_401(self, auth_client):
        resp = auth_client.get("/health", auth=("admin", "wrong"))
        assert resp.status_code == 401

    def test_correct_credentials_returns_200(self, auth_client):
        resp = auth_client.get("/health", auth=("admin", "secret"))
        assert resp.status_code == 200

    def test_no_auth_flag_bypasses_auth(self, noauth_client):
        resp = noauth_client.get("/health")
        assert resp.status_code == 200
