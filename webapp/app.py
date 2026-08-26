"""Flask app serving the live dashboard and a small JSON API over the
sensor readings stored in SQLite.

Run with:
    python -m webapp.app

Then open http://localhost:5000
"""
from flask import Flask, jsonify, render_template, request

from ingest.db import (
    fetch_recent,
    get_sensor_settings,
    init_db,
    list_sensors,
    sensor_stats,
    set_sensor_settings,
)

DEFAULT_WINDOW = 30
DEFAULT_THRESHOLD = 3.0

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/sensors")
def api_sensors():
    return jsonify(sorted(list_sensors()))


@app.route("/api/readings/<sensor>")
def api_readings(sensor):
    limit = request.args.get("limit", default=200, type=int)
    limit = max(1, min(limit, 2000))
    since = request.args.get("since", default=None, type=str)

    rows = fetch_recent(sensor, limit=limit, since=since)
    readings = [
        {
            "id": row[0],
            "sensor": row[1],
            "value": row[2],
            "timestamp": row[3],
            "is_anomaly": bool(row[4]),
        }
        for row in rows
    ]
    return jsonify(readings)


@app.route("/api/stats/<sensor>")
def api_stats(sensor):
    return jsonify(sensor_stats(sensor))


@app.route("/api/settings/<sensor>", methods=["GET"])
def api_get_settings(sensor):
    window, threshold = get_sensor_settings(sensor, DEFAULT_WINDOW, DEFAULT_THRESHOLD)
    return jsonify({"sensor": sensor, "window": window, "threshold": threshold})


@app.route("/api/settings/<sensor>", methods=["POST"])
def api_set_settings(sensor):
    data = request.get_json(silent=True) or {}
    try:
        window = int(data["window"])
        threshold = float(data["threshold"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Expected JSON body with integer 'window' and numeric 'threshold'."}), 400

    if window <= 0:
        return jsonify({"error": "window must be a positive integer."}), 400
    if threshold <= 0:
        return jsonify({"error": "threshold must be positive."}), 400

    set_sensor_settings(sensor, window, threshold)
    return jsonify({"sensor": sensor, "window": window, "threshold": threshold})


def main():
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    main()
