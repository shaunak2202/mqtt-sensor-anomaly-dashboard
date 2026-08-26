"""Background worker that continuously runs anomaly detection.

Instead of invoking `analysis.anomaly` by hand from the CLI every time you
want fresh flags, this polls every known sensor on a fixed interval, runs
the same detector over its most recent window of readings, marks any new
anomalies in the database, logs an alert line, and fires any configured
alert hooks (see `analysis/alerts.py`).

Per-sensor window/threshold can be overridden live via the dashboard's
settings panel (persisted in the `settings` table); those overrides take
priority over the CLI defaults below.

Usage:
    python -m analysis.worker
    python -m analysis.worker --interval 5 --window 30 --threshold 3.0
"""
import argparse
import logging
import time

from analysis.alerts import AlertEvent, build_hooks_from_env, fire_all
from analysis.anomaly import Reading, detect_anomalies
from ingest.db import fetch_recent, get_sensor_settings, list_sensors, mark_anomaly

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")


def check_sensor(
    sensor: str,
    default_window: int,
    default_threshold: float,
    use_ewma: bool,
    fetch_limit: int,
    hooks,
) -> int:
    """Run the detector over a sensor's most recent readings and mark any
    new anomalies, firing alert hooks for each. Returns the number of new
    anomalies found. Uses a per-sensor window/threshold override from the
    settings table if one has been saved via the dashboard.
    """
    window, threshold = get_sensor_settings(sensor, default_window, default_threshold)

    rows = fetch_recent(sensor, limit=fetch_limit)
    readings = [Reading(*row) for row in rows]

    if len(readings) <= window:
        return 0

    anomalies = detect_anomalies(readings, window=window, threshold=threshold, use_ewma=use_ewma)

    new_count = 0
    for a in anomalies:
        if a.reading.is_anomaly:
            continue  # already flagged in a previous pass
        mark_anomaly(a.reading.id)
        new_count += 1
        event = AlertEvent(
            sensor=a.reading.sensor,
            value=a.reading.value,
            z_score=a.z_score,
            timestamp=a.reading.timestamp,
        )
        fire_all(hooks, event)
    return new_count


def run_once(default_window: int, default_threshold: float, use_ewma: bool, fetch_limit: int, hooks) -> int:
    sensors = list_sensors()
    if not sensors:
        log.info("No sensors in the database yet -- is the subscriber running?")
        return 0

    total_new = 0
    for sensor in sensors:
        total_new += check_sensor(sensor, default_window, default_threshold, use_ewma, fetch_limit, hooks)
    return total_new


def main():
    parser = argparse.ArgumentParser(description="Continuously run anomaly detection over stored readings.")
    parser.add_argument("--interval", type=float, default=10.0, help="Seconds between polling passes")
    parser.add_argument("--window", type=int, default=30, help="Default trailing window size (overridable per sensor via dashboard)")
    parser.add_argument("--threshold", type=float, default=3.0, help="Default z-score threshold (overridable per sensor via dashboard)")
    parser.add_argument("--fetch-limit", type=int, default=200, help="How many recent rows per sensor to consider")
    parser.add_argument("--no-ewma", action="store_true", help="Use plain mean instead of EWMA")
    args = parser.parse_args()

    hooks = build_hooks_from_env()
    log.info(
        "Starting anomaly worker: interval=%ss window=%s threshold=%s ewma=%s hooks=%s",
        args.interval, args.window, args.threshold, not args.no_ewma,
        [h.name for h in hooks],
    )

    try:
        while True:
            new_count = run_once(args.window, args.threshold, not args.no_ewma, args.fetch_limit, hooks)
            if new_count:
                log.info("Pass complete: %d new anomaly(ies) flagged.", new_count)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log.info("Stopping worker.")


if __name__ == "__main__":
    main()
