"""Rolling z-score / EWMA anomaly detection over stored sensor readings.

Usage:
    python -m analysis.anomaly --sensor temperature --window 30 --threshold 3.0

The detector keeps a trailing window of the last N readings for a given
sensor, computes the mean/std over that window (optionally EWMA-weighted
so recent points matter more), and flags points whose z-score relative to
the window exceeds the threshold. It's intentionally simple and explainable
rather than a black-box model, which matters for something meant to run
unattended on live data.
"""
import argparse
import statistics
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Reading:
    id: int
    sensor: str
    value: float
    timestamp: str
    is_anomaly: int


@dataclass
class AnomalyResult:
    reading: Reading
    z_score: float
    window_mean: float
    window_std: float


def ewma(values: List[float], alpha: float = 0.3) -> float:
    """Exponentially weighted moving average -- recent values weighted more."""
    if not values:
        return 0.0
    avg = values[0]
    for v in values[1:]:
        avg = alpha * v + (1 - alpha) * avg
    return avg


def detect_anomalies(
    readings: List[Reading],
    window: int = 30,
    threshold: float = 3.0,
    use_ewma: bool = True,
) -> List[AnomalyResult]:
    """Slide a trailing window over `readings` (assumed chronological) and
    flag any point whose z-score against the preceding window exceeds
    `threshold`. The first `window` points are used purely to build up
    history and are not flagged.
    """
    results = []
    if not readings or window <= 0:
        return results

    for i in range(window, len(readings)):
        history = [r.value for r in readings[i - window : i]]
        current = readings[i]

        mean = ewma(history) if use_ewma else statistics.mean(history)
        std = statistics.pstdev(history)

        if std == 0:
            continue  # flat window, nothing to compare against

        z = (current.value - mean) / std
        if abs(z) >= threshold:
            results.append(
                AnomalyResult(reading=current, z_score=z, window_mean=mean, window_std=std)
            )
    return results


def _load_readings_from_db(sensor: str) -> List[Reading]:
    from ingest.db import get_connection

    with get_connection() as conn:
        cur = conn.execute(
            """SELECT id, sensor, value, timestamp, is_anomaly
               FROM readings WHERE sensor = ? ORDER BY timestamp ASC""",
            (sensor,),
        )
        rows = cur.fetchall()
    return [Reading(*row) for row in rows]


def main():
    parser = argparse.ArgumentParser(description="Detect anomalies in stored sensor readings.")
    parser.add_argument("--sensor", required=True, help="Sensor name, e.g. temperature")
    parser.add_argument("--window", type=int, default=30, help="Trailing window size")
    parser.add_argument("--threshold", type=float, default=3.0, help="Z-score threshold")
    parser.add_argument("--no-ewma", action="store_true", help="Use plain mean instead of EWMA")
    args = parser.parse_args()

    readings = _load_readings_from_db(args.sensor)
    if len(readings) <= args.window:
        print(f"Not enough data yet for sensor '{args.sensor}' "
              f"({len(readings)} readings, need > {args.window}). "
              "Let the publisher/subscriber run longer.")
        return

    anomalies = detect_anomalies(
        readings, window=args.window, threshold=args.threshold, use_ewma=not args.no_ewma
    )

    if not anomalies:
        print(f"No anomalies found in {len(readings)} readings for '{args.sensor}'.")
        return

    from ingest.db import mark_anomaly

    for a in anomalies:
        print(
            f"[ANOMALY] {a.reading.timestamp} sensor={a.reading.sensor} "
            f"value={a.reading.value:.2f} z={a.z_score:.2f} "
            f"(window mean={a.window_mean:.2f}, std={a.window_std:.2f})"
        )
        mark_anomaly(a.reading.id)


if __name__ == "__main__":
    main()
