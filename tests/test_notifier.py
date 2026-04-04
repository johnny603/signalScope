"""Tests for the notification hooks."""

from unittest.mock import patch, MagicMock
import pytest
from src.notifications.notifier import Notifier, AnomalyEvent, SlackNotifier, GenericWebhookNotifier


def make_event(**kwargs) -> AnomalyEvent:
    defaults = dict(pid=100, name="proc", event_type="high_cpu", detail="CPU at 90%")
    defaults.update(kwargs)
    return AnomalyEvent(**defaults)


class TestNotifier:
    def test_no_channels_does_nothing(self):
        n = Notifier()
        n.notify(make_event())  # No exception

    def test_dispatches_to_channel(self):
        n = Notifier()
        ch = MagicMock()
        n.add_channel(ch)
        event = make_event()
        n.notify(event)
        ch.send.assert_called_once_with(event)

    def test_cooldown_suppresses_duplicate(self):
        n = Notifier(cooldown_seconds=300)
        ch = MagicMock()
        n.add_channel(ch)
        event = make_event()
        n.notify(event)
        n.notify(event)  # second call should be suppressed
        assert ch.send.call_count == 1

    def test_different_event_type_not_suppressed(self):
        n = Notifier(cooldown_seconds=300)
        ch = MagicMock()
        n.add_channel(ch)
        n.notify(make_event(event_type="high_cpu"))
        n.notify(make_event(event_type="zombie"))  # different type, same pid
        assert ch.send.call_count == 2

    def test_sets_timestamp_and_host(self):
        n = Notifier()
        ch = MagicMock()
        n.add_channel(ch)
        event = make_event()
        assert event.timestamp == ""
        n.notify(event)
        assert event.timestamp != ""
        assert event.host != ""

    def test_cooldown_zero_always_notifies(self):
        n = Notifier(cooldown_seconds=0)
        ch = MagicMock()
        n.add_channel(ch)
        n.notify(make_event())
        n.notify(make_event())
        assert ch.send.call_count == 2


class TestSlackNotifier:
    def test_send_success(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            s = SlackNotifier("http://example.com/webhook")
            result = s.send(make_event(timestamp="2024-01-01", host="host1"))
        assert result is True

    def test_send_failure_returns_false(self):
        with patch('urllib.request.urlopen', side_effect=Exception("network error")), \
             patch('time.sleep'):
            s = SlackNotifier("http://example.com/webhook")
            result = s.send(make_event(timestamp="2024-01-01", host="host1"))
        assert result is False


class TestGenericWebhookNotifier:
    def test_send_success(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            g = GenericWebhookNotifier("http://example.com/hook")
            result = g.send(make_event(timestamp="2024-01-01", host="host1"))
        assert result is True

    def test_send_failure_returns_false(self):
        with patch('urllib.request.urlopen', side_effect=Exception("error")), \
             patch('time.sleep'):
            g = GenericWebhookNotifier("http://bad-url")
            result = g.send(make_event(timestamp="2024-01-01", host="host1"))
        assert result is False
