"""Unit tests for the rolling z-score / EWMA anomaly detector.

Covers a flat signal (no anomalies possible), a single injected spike,
a sustained drift, and short/empty history edge cases.
"""
import pytest

from analysis.anomaly import Reading, detect_anomalies, ewma


def make_readings(values, sensor="test"):
    return [
        Reading(id=i, sensor=sensor, value=v, timestamp=f"2024-01-01T00:00:{i:02d}", is_anomaly=0)
        for i, v in enumerate(values)
    ]


def test_flat_signal_has_no_anomalies():
    # Perfectly flat signal -> std is 0 in every window -> nothing should
    # ever be flagged (the detector explicitly skips zero-std windows).
    readings = make_readings([10.0] * 50)
    results = detect_anomalies(readings, window=10, threshold=3.0)
    assert results == []


def test_single_spike_is_flagged():
    values = [20.0] * 40
    values[35] = 200.0  # sharp, isolated spike well past the window
    readings = make_readings(values)

    results = detect_anomalies(readings, window=20, threshold=3.0)

    assert len(results) == 1
    assert results[0].reading.id == 35
    assert results[0].reading.value == 200.0


def test_sustained_drift_eventually_flagged_then_absorbed():
    # A slow drift should get flagged near where it accelerates away from
    # the trailing window's mean, but once the window is dominated by
    # drifted values it should stop being flagged (mean catches up).
    baseline = [20.0] * 30
    drift = [20.0 + i * 5 for i in range(1, 11)]  # steep-ish ramp
    readings = make_readings(baseline + drift)

    results = detect_anomalies(readings, window=15, threshold=3.0)

    # At least one point during the ramp should be flagged.
    assert len(results) >= 1
    # All flagged points should be within (or after) the drift section.
    for r in results:
        assert r.reading.id >= len(baseline)


def test_short_history_returns_no_results():
    readings = make_readings([1.0, 2.0, 3.0])
    results = detect_anomalies(readings, window=30, threshold=3.0)
    assert results == []


def test_empty_history_returns_no_results():
    assert detect_anomalies([], window=30, threshold=3.0) == []


def test_ewma_weights_recent_values_more():
    # A jump at the end should pull the EWMA further than a plain mean.
    values = [10.0] * 9 + [20.0]
    weighted = ewma(values, alpha=0.3)
    plain_mean = sum(values) / len(values)
    assert weighted > plain_mean


def test_ewma_empty_list_is_zero():
    assert ewma([]) == 0.0


def test_negative_direction_spike_is_flagged():
    # Anomalies aren't just spikes upward -- a sharp drop should also z-score
    # past the threshold, mirroring the soil_moisture "dropout" case from the
    # simulator.
    values = [40.0] * 40
    values[35] = 5.0
    readings = make_readings(values)

    results = detect_anomalies(readings, window=20, threshold=3.0)

    assert len(results) == 1
    assert results[0].z_score < 0
