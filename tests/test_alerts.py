"""Tests for the pluggable alert hook system.

Uses monkeypatching / mocks so no real network or SMTP access is needed.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from analysis.alerts import (
    AlertEvent,
    EmailAlertHook,
    LogAlertHook,
    WebhookAlertHook,
    build_hooks_from_env,
    fire_all,
)


def make_event():
    return AlertEvent(sensor="temperature", value=99.9, z_score=4.2, timestamp="2024-01-01T00:00:00")


def test_log_hook_does_not_raise(caplog):
    hook = LogAlertHook()
    hook.notify(make_event())
    assert "ALERT" in caplog.text


def test_build_hooks_defaults_to_log(monkeypatch):
    monkeypatch.delenv("ALERT_HOOKS", raising=False)
    hooks = build_hooks_from_env()
    assert len(hooks) == 1
    assert hooks[0].name == "log"


def test_build_hooks_respects_env_list(monkeypatch):
    monkeypatch.setenv("ALERT_HOOKS", "log,webhook")
    hooks = build_hooks_from_env()
    names = {h.name for h in hooks}
    assert names == {"log", "webhook"}


def test_build_hooks_ignores_unknown_names(monkeypatch):
    monkeypatch.setenv("ALERT_HOOKS", "log,not_a_real_hook")
    hooks = build_hooks_from_env()
    assert len(hooks) == 1
    assert hooks[0].name == "log"


def test_webhook_hook_skips_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    hook = WebhookAlertHook()
    # Should simply return without raising when no URL is set.
    hook.notify(make_event())


def test_webhook_hook_posts_json_when_configured():
    hook = WebhookAlertHook(url="http://example.com/hook")
    fake_response = MagicMock()
    fake_response.status = 200
    fake_response.__enter__.return_value = fake_response

    with patch("urllib.request.urlopen", return_value=fake_response) as mock_urlopen:
        hook.notify(make_event())
        assert mock_urlopen.called
        request_obj = mock_urlopen.call_args[0][0]
        body = json.loads(request_obj.data.decode("utf-8"))
        assert body["sensor"] == "temperature"


def test_webhook_hook_fails_soft_on_network_error():
    hook = WebhookAlertHook(url="http://example.com/hook")
    with patch("urllib.request.urlopen", side_effect=OSError("boom")):
        # Should not raise -- failure is logged, not propagated.
        hook.notify(make_event())


def test_email_hook_skips_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ALERT_SMTP_HOST", raising=False)
    monkeypatch.delenv("ALERT_EMAIL_FROM", raising=False)
    monkeypatch.delenv("ALERT_EMAIL_TO", raising=False)
    hook = EmailAlertHook()
    hook.notify(make_event())


def test_email_hook_sends_when_configured(monkeypatch):
    monkeypatch.setenv("ALERT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("ALERT_EMAIL_FROM", "alerts@example.com")
    monkeypatch.setenv("ALERT_EMAIL_TO", "me@example.com")

    mock_server = MagicMock()
    mock_smtp_cls = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_server

    with patch("smtplib.SMTP", mock_smtp_cls):
        hook = EmailAlertHook()
        hook.notify(make_event())
        assert mock_server.sendmail.called


def test_fire_all_calls_every_hook():
    hook_a = MagicMock()
    hook_a.name = "a"
    hook_b = MagicMock()
    hook_b.name = "b"
    fire_all([hook_a, hook_b], make_event())
    hook_a.notify.assert_called_once()
    hook_b.notify.assert_called_once()


def test_fire_all_continues_if_one_hook_raises():
    broken_hook = MagicMock()
    broken_hook.name = "broken"
    broken_hook.notify.side_effect = RuntimeError("boom")
    ok_hook = MagicMock()
    ok_hook.name = "ok"

    fire_all([broken_hook, ok_hook], make_event())
    ok_hook.notify.assert_called_once()
