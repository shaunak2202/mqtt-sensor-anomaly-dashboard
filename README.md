# MQTT Sensor Anomaly Dashboard

A small end-to-end pipeline for ingesting streaming sensor data over MQTT,
storing it, detecting anomalies in near real time, and visualizing it on a
live dashboard.

## Why this project

During the hydroponics project I wired up MQTT sensors to a single control
loop. This project pulls that pattern out into a general-purpose,
reusable monitoring stack that could sit in front of any set of MQTT
publishing sensors -- not just plants. It's a good excuse to build a real
streaming ingestion + storage + detection + visualization pipeline end to end.

## Current status (session 2)

Working so far:
- `simulator/publisher.py` -- simulates 3 sensors (temperature, humidity,
  soil moisture) publishing JSON readings to an MQTT broker on a timer,
  with occasional injected spikes/dropouts so there's something for the
  detector to actually catch.
- `ingest/subscriber.py` -- subscribes to all sensor topics, parses
  incoming JSON payloads, and writes every reading into a local SQLite
  database (`data/sensors.db`).
- `ingest/db.py` -- schema + helper functions for reading/writing
  readings.
- `analysis/anomaly.py` -- rolling z-score / EWMA-based anomaly detector
  that runs over a sensor's recent history and flags points that deviate
  from the recent mean by more than a configurable threshold. Includes a
  standalone CLI mode (`python -m analysis.anomaly --sensor temperature`)
  to test detection against data already in the DB.
- `analysis/worker.py` -- **new**. A background loop that polls each known
  sensor on an interval, runs the same detector over its most recent
  window, marks new anomalies in the DB, and logs an alert line when it
  finds one. This replaces having to run the CLI by hand every time you
  want fresh flags.
- `webapp/app.py` -- **new**. A small Flask app exposing:
  - `GET /` -- the dashboard page
  - `GET /api/sensors` -- list of known sensor names
  - `GET /api/readings/<sensor>?limit=200` -- recent readings + anomaly
    flags as JSON, used by the frontend to draw charts
  - `GET /api/stats/<sensor>` -- quick summary (count, anomaly count,
    latest value, latest anomaly timestamp)
- `webapp/templates/index.html` + `webapp/static/dashboard.js` -- **new**.
  A live dashboard: one Chart.js line chart per sensor, polling the API
  every few seconds, with anomalous points rendered as red highlighted
  markers on top of the normal line, plus small stat cards per sensor.
- Unit tests for the anomaly detector (`tests/test_anomaly.py`) covering
  a flat signal, a single spike, a sustained drift, and an empty/short
  history -- **new**.

Not built yet (planned for next session):
- Basic alerting hook beyond the log line (e.g. a webhook stub / email
  stub) when an anomaly is detected.
- Some polish on the dashboard (time range picker, sensor-level threshold
  controls exposed in the UI instead of only via CLI/worker config).
- Packaging the whole thing (broker + subscriber + worker + webapp) behind
  a single `docker-compose up`.

## Architecture

```
 publisher(s) --MQTT--> broker (mosquitto) --MQTT--> subscriber --> SQLite
                                                                      |
                                                     worker.py polls on an
                                                     interval, runs anomaly.py
                                                     over recent windows,
                                                     marks flags in SQLite
                                                                      |
                                                        Flask app (webapp/)
                                                        serves JSON API +
                                                        Chart.js dashboard
```

## Requirements

- Python 3.10+
- A running MQTT broker. Easiest local option: [Mosquitto](https://mosquitto.org/)
  ```
  # macOS
  brew install mosquitto
  mosquitto -p 1883
  ```
  Or run it in Docker:
  ```
  docker run -it -p 1883:1883 eclipse-mosquitto
  ```

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running it

Open four terminals (with the broker already running):

**1. Start the subscriber (writes incoming readings to SQLite):**
```bash
python -m ingest.subscriber
```

**2. Start the simulated publisher:**
```bash
python -m simulator.publisher
```

You should see readings being logged and rows accumulating in
`data/sensors.db`.

**3. Start the background anomaly worker (continuously flags new readings):**
```bash
python -m analysis.worker
```
This polls every 10s by default, running the same z-score/EWMA detector
from `analysis/anomaly.py` over each sensor's trailing window and writing
flags back with `mark_anomaly`. It also prints an alert line to stdout
whenever it finds something new, e.g.:
```
[ALERT] sensor=soil_moisture value=14.20 z=-4.31 at 2024-05-01T12:03:41
```

**4. Start the dashboard:**
```bash
python -m webapp.app
```
Then open http://localhost:5000 -- you'll see one live chart per sensor,
updating every few seconds, with anomalies drawn as red points.

**One-off CLI detection (still works, useful for backfilling/tuning):**
```bash
python -m analysis.anomaly --sensor temperature --window 30 --threshold 3.0
```

## Running the tests

```bash
pip install pytest
pytest
```

## Project layout

```
mqtt-sensor-anomaly-dashboard/
├── simulator/
│   └── publisher.py       # fake sensors publishing to MQTT
├── ingest/
│   ├── subscriber.py      # MQTT -> SQLite ingestion
│   └── db.py              # SQLite schema + helpers
├── analysis/
│   ├── anomaly.py         # rolling z-score / EWMA anomaly detector (+ CLI)
│   └── worker.py          # continuous background detector loop
├── webapp/
│   ├── app.py              # Flask app + JSON API
│   ├── templates/
│   │   └── index.html
│   └── static/
│       └── dashboard.js    # Chart.js polling frontend
├── tests/
│   └── test_anomaly.py
├── data/                  # sensors.db created here at runtime
├── requirements.txt
└── README.md
```

## Notes on the detection approach

The detector keeps a trailing window of the last N readings per sensor,
computes a mean and standard deviation over that window (optionally
EWMA-weighted so recent points count more), and flags any new reading
whose z-score exceeds a configurable threshold (default 3.0). It's a
deliberately simple, explainable method -- no ML model -- chosen because
it's easy to reason about and tune, which matters for something meant to
run unattended on live sensor data. The background worker in
`analysis/worker.py` just re-runs this same function on a timer per
sensor rather than introducing a separate streaming/incremental variant,
which keeps the CLI, worker, and dashboard all backed by identical logic.
A natural extension (not done yet) would be comparing this against an
Isolation Forest or a small autoencoder trained on the accumulated
history.

---

Built by a personal automation project Shaunak set up: it uses Claude to design and write real, working code within his actual skill set, and pushes it here on a regular schedule as an ongoing practice/portfolio project.

---

Built by a personal automation project Shaunak set up: it uses Claude to design and write real, working code within his actual skill set, and pushes it here on a regular schedule as an ongoing practice/portfolio project.
