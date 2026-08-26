"""Pluggable alert hooks fired by the worker when a new anomaly is found.

Designed to be swappable without touching detection code: each hook is a
small class implementing `notify(event: AlertEvent) -> None`. Which hooks
run is controlled by the `ALERT_HOOKS` environment variable, a comma
separated list (e.g. "log,webhook,email"). Hooks fail soft -- a broken
webhook endpoint or misconfigured SMTP server logs a warning and never
crashes the worker loop.

Env vars used:
    ALERT_HOOKS          comma list of hook names, default "log"
    ALERT_WEBHOOK_URL     URL to POST JSON anomaly events to (webhook hook)
    ALERT_SMTP_HOST       SMTP host (email hook)
    ALERT_SMTP_PORT       SMTP port, default 587
    ALERT_EMAIL_FROM      From address (email hook)
    ALERT_EMAIL_TO        To address (email hook)
    ALERT_SMTP_USER       optional SMTP auth username
    ALERT_SMTP_PASSWORD   optional SMTP auth password
"""
import json
import logging
import os
import smtplib
import urllib.request
from dataclasses import dataclass, asdict
from email.mime.text import MIMEText
from typing import List

@dataclass
class AlertEvent:
    sensor: str
    value: float
    z_score: float
    timestamp: str


class AlertHook:
    name = "base"

    def notify(self, event: AlertEvent) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class LogAlertHook(AlertHook):
    """Always-available fallback: just logs, same behavior as session 2."""

    name = "log"

    def __init__(self):
        self.log = logging.getLogger("alerts.log")

    def notify(self, event: AlertEvent) -> None:
        self.log.warning(
            "[ALERT] sensor=%s value=%.2f z=%.2f at %s",
            event.sensor, event.value, event.z_score, event.timestamp,
        )


class WebhookAlertHook(AlertHook):
    """POSTs a JSON payload to ALERT_WEBHOOK_URL. Uses stdlib urllib so no
    extra dependency is required. Fails soft on any network error.
    """

    name = "webhook"

    def __init__(self, url: str = None, timeout: float = 5.0):
        self.url = url or os.environ.get("ALERT_WEBHOOK_URL")
        self.timeout = timeout
        self.log = logging.getLogger("alerts.webhook")

    def notify(self, event: AlertEvent) -> None:
        if not self.url:
            self.log.debug("No ALERT_WEBHOOK_URL configured, skipping webhook alert.")
            return
        data = json.dumps(asdict(event)).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self.log.info("Webhook alert sent for sensor=%s (status=%s)", event.sensor, resp.status)
        except Exception as e:
            self.log.warning("Webhook alert failed for sensor=%s: %s", event.sensor, e)


class EmailAlertHook(AlertHook):
    """Sends a plain-text email over SMTP using env-configured settings.
    Fails soft if SMTP isn't configured or reachable.
    """

    name = "email"

    def __init__(self):
        self.host = os.environ.get("ALERT_SMTP_HOST")
        self.port = int(os.environ.get("ALERT_SMTP_PORT", "587"))
        self.from_addr = os.environ.get("ALERT_EMAIL_FROM")
        self.to_addr = os.environ.get("ALERT_EMAIL_TO")
        self.user = os.environ.get("ALERT_SMTP_USER")
        self.password = os.environ.get("ALERT_SMTP_PASSWORD")
        self.log = logging.getLogger("alerts.email")

    def notify(self, event: AlertEvent) -> None:
        if not (self.host and self.from_addr and self.to_addr):
            self.log.debug("Email alert hook not fully configured, skipping.")
            return

        subject = f"[Anomaly] {event.sensor} value={event.value:.2f} z={event.z_score:.2f}"
        body = (
            f"Sensor: {event.sensor}\n"
            f"Value: {event.value}\n"
            f"Z-score: {event.z_score}\n"
            f"Timestamp: {event.timestamp}\n"
        )
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = self.to_addr

        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                server.ehlo()
                try:
                    server.starttls()
                except smtplib.SMTPNotSupportedError:
                    pass
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.sendmail(self.from_addr, [self.to_addr], msg.as_string())
            self.log.info("Email alert sent for sensor=%s", event.sensor)
        except Exception as e:
            self.log.warning("Email alert failed for sensor=%s: %s", event.sensor, e)


_HOOK_REGISTRY = {
    "log": LogAlertHook,
    "webhook": WebhookAlertHook,
    "email": EmailAlertHook,
}


def build_hooks_from_env() -> List[AlertHook]:
    """Builds the list of active alert hooks based on ALERT_HOOKS env var.
    Defaults to just the log hook so behavior is unchanged if nothing is
    configured. Unknown names are ignored with a warning.
    """
    names = [n.strip().lower() for n in os.environ.get("ALERT_HOOKS", "log").split(",") if n.strip()]
    log = logging.getLogger("alerts")
    hooks = []
    for name in names:
        cls = _HOOK_REGISTRY.get(name)
        if cls is None:
            log.warning("Unknown alert hook '%s', ignoring.", name)
            continue
        hooks.append(cls())
    if not hooks:
        hooks.append(LogAlertHook())
    return hooks


def fire_all(hooks: List[AlertHook], event: AlertEvent) -> None:
    for hook in hooks:
        try:
            hook.notify(event)
        except Exception as e:  # extra safety net beyond each hook's own try/except
            logging.getLogger("alerts").warning("Hook %s raised unexpectedly: %s", hook.name, e)
