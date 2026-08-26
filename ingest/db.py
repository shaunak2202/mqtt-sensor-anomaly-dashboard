"""SQLite schema and helper functions for storing sensor readings and
per-sensor detector settings."""
import sqlite3
import os
from contextlib import contextmanager
from typing import Tuple

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "sensors.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor TEXT NOT NULL,
    value REAL NOT NULL,
    timestamp TEXT NOT NULL,
    is_anomaly INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_readings_sensor_ts
    ON readings (sensor, timestamp);

CREATE TABLE IF NOT EXISTS settings (
    sensor TEXT PRIMARY KEY,
    window INTEGER,
    threshold REAL
);
"""


def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_reading(sensor: str, value: float, timestamp: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO readings (sensor, value, timestamp) VALUES (?, ?, ?)",
            (sensor, value, timestamp),
        )


def fetch_recent(sensor: str, limit: int = 200, since: str = None):
    """Return the most recent `limit` readings for a sensor, oldest first.
    If `since` (an ISO timestamp string) is given, only readings with a
    timestamp >= since are considered (still capped at `limit`, most
    recent first internally then reversed to chronological order).
    """
    with get_connection() as conn:
        if since:
            cur = conn.execute(
                """SELECT id, sensor, value, timestamp, is_anomaly
                   FROM readings WHERE sensor = ? AND timestamp >= ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (sensor, since, limit),
            )
        else:
            cur = conn.execute(
                """SELECT id, sensor, value, timestamp, is_anomaly
                   FROM readings WHERE sensor = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (sensor, limit),
            )
        rows = cur.fetchall()
    return list(reversed(rows))


def mark_anomaly(reading_id: int):
    with get_connection() as conn:
        conn.execute(
            "UPDATE readings SET is_anomaly = 1 WHERE id = ?", (reading_id,)
        )


def list_sensors():
    with get_connection() as conn:
        cur = conn.execute("SELECT DISTINCT sensor FROM readings")
        return [row[0] for row in cur.fetchall()]


def sensor_stats(sensor: str):
    """Return a small summary dict for a sensor: total readings, anomaly
    count, latest value/timestamp, and latest anomaly timestamp (if any).
    """
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT COUNT(*), SUM(is_anomaly) FROM readings WHERE sensor = ?", (sensor,)
        )
        total, anomaly_count = cur.fetchone()
        anomaly_count = anomaly_count or 0

        cur = conn.execute(
            """SELECT value, timestamp FROM readings WHERE sensor = ?
               ORDER BY timestamp DESC LIMIT 1""",
            (sensor,),
        )
        latest_row = cur.fetchone()

        cur = conn.execute(
            """SELECT timestamp FROM readings WHERE sensor = ? AND is_anomaly = 1
               ORDER BY timestamp DESC LIMIT 1""",
            (sensor,),
        )
        latest_anomaly_row = cur.fetchone()

    return {
        "sensor": sensor,
        "total_readings": total or 0,
        "anomaly_count": anomaly_count,
        "latest_value": latest_row[0] if latest_row else None,
        "latest_timestamp": latest_row[1] if latest_row else None,
        "latest_anomaly_timestamp": latest_anomaly_row[0] if latest_anomaly_row else None,
    }


def get_sensor_settings(sensor: str, default_window: int, default_threshold: float) -> Tuple[int, float]:
    """Return (window, threshold) for a sensor, falling back to the given
    defaults if no override has been saved.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT window, threshold FROM settings WHERE sensor = ?", (sensor,)
        )
        row = cur.fetchone()
    if row is None:
        return default_window, default_threshold
    window, threshold = row
    return (window if window is not None else default_window,
            threshold if threshold is not None else default_threshold)


def set_sensor_settings(sensor: str, window: int, threshold: float):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO settings (sensor, window, threshold) VALUES (?, ?, ?)
               ON CONFLICT(sensor) DO UPDATE SET window = ?, threshold = ?""",
            (sensor, window, threshold, window, threshold),
        )


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
