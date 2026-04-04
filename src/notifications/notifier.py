"""Notification hooks for SignalScope anomaly events."""

import json
import logging
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import socket

logger = logging.getLogger(__name__)


@dataclass
class AnomalyEvent:
    pid: int
    name: str
    event_type: str
    detail: str
    timestamp: str = ""  # ISO format; set by Notifier if empty
    host: str = ""  # set by Notifier if empty


class SlackNotifier:
    """Posts alerts to a Slack Incoming Webhook."""

    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    def send(self, event: AnomalyEvent) -> bool:
        """Returns True on success."""
        payload = json.dumps({
            "text": (
                f"*[SignalScope Alert]*\n"
                f"Process: *{event.name}* (PID {event.pid})\n"
                f"Event: `{event.event_type}`\n"
                f"Detail: {event.detail}\n"
                f"Host: `{event.host}`\n"
                f"Time: {event.timestamp}"
            )
        }).encode()
        return self._post(payload)

    def _post(self, payload: bytes) -> bool:
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    self._url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.status < 400
            except Exception as exc:
                logger.warning("SlackNotifier attempt %d failed: %s", attempt + 1, exc)
                if attempt == 0:
                    time.sleep(2)
        return False


class GenericWebhookNotifier:
    """Posts JSON anomaly payloads to a configurable URL."""

    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    def send(self, event: AnomalyEvent) -> bool:
        payload = json.dumps({
            "pid": event.pid,
            "name": event.name,
            "event_type": event.event_type,
            "detail": event.detail,
            "host": event.host,
            "timestamp": event.timestamp,
        }).encode()
        return self._post(payload)

    def _post(self, payload: bytes) -> bool:
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    self._url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.status < 400
            except Exception as exc:
                logger.warning("GenericWebhookNotifier attempt %d failed: %s", attempt + 1, exc)
                if attempt == 0:
                    time.sleep(2)
        return False


class Notifier:
    """Dispatches anomaly events to all configured notification channels."""

    def __init__(self, cooldown_seconds: int = 300) -> None:
        self._channels: List = []
        self._cooldown = cooldown_seconds
        self._last_notified: dict = {}  # (pid, event_type) -> timestamp
        self._hostname = socket.gethostname()

    def add_channel(self, channel) -> None:
        self._channels.append(channel)

    def notify(self, event: AnomalyEvent) -> None:
        if not self._channels:
            return
        # Set defaults
        if not event.timestamp:
            event.timestamp = datetime.utcnow().isoformat()
        if not event.host:
            event.host = self._hostname

        key = (event.pid, event.event_type)
        now = time.monotonic()
        last = self._last_notified.get(key, 0)
        if now - last < self._cooldown:
            logger.debug("Notifier: suppressing duplicate (%d, %s) within cooldown", event.pid, event.event_type)
            return

        self._last_notified[key] = now
        for ch in self._channels:
            try:
                ch.send(event)
            except Exception as exc:
                logger.error("Notification channel error: %s", exc)
