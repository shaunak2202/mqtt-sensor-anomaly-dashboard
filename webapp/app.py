"""Flask app serving the live dashboard and a small JSON API over the
sensor readings stored in SQLite.

Run with:
    python -m webapp.app

Then open http://localhost:5000
"""
from flask import Flask, jsonify, render_template

from ingest.db import fetch_recent, init_db, list_sensors, sensor_stats

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/sensors")
def api_sensors():
    return jsonify(sorted(list_sensors()))


@app.route("/api/readings/<sensor>")
def api_readings(sensor):
    from flask import request

    limit = request.args.get("limit", default=200, type=int)
    limit = max(1, min(limit, 2000))

    rows = fetch_recent(sensor, limit=limit)
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


def main():
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    main()
