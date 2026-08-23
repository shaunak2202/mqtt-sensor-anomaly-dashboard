# MQTT Sensor Anomaly Dashboard

A small end-to-end pipeline for ingesting streaming sensor data over MQTT,
storing it, detecting anomalies in near real time, and (in progress)
visualizing it on a live dashboard.

## Why this project

During the hydroponics project I wired up MQTT sensors to a single control
loop. This project pulls that pattern out into a general-purpose,
reusable monitoring stack that could sit in front of any set of MQTT
publishing sensors -- not just plants. It's a good excuse to build a real
streaming ingestion + storage + detection pipeline end to end.

## Current status (session 1)

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

Not built yet (planned for next sessions):
- Flask web dashboard with Chart.js showing live sensor streams and
  highlighted anomalies.
- A background worker that runs the anomaly detector continuously as new
  readings arrive (instead of on-demand via CLI) and writes flags back to
  the DB.
- Basic alerting hook (e.g. log line / webhook stub) when an anomaly is
  detected.
- Unit tests for the anomaly detector's edge cases (flat signal, single
  spike, sustained drift).

## Architecture

```
 publisher(s) --MQTT--> broker (mosquitto) --MQTT--> subscriber --> SQLite
                                                                      |
                                                          anomaly.py reads
                                                          recent windows and
                                                          flags outliers
                                                                      |
                                                        (planned) Flask app
                                                        serves dashboard
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

Open three terminals (with the broker already running):

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

**3. Run anomaly detection over stored history:**
```bash
python -m analysis.anomaly --sensor temperature --window 30 --threshold 3.0
```

This prints out any readings whose z-score relative to the trailing
window exceeds the threshold, e.g.:
```
[ANOMALY] 2024-05-01T12:03:41 sensor=temperature value=41.8 z=4.12
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
│   └── anomaly.py         # rolling z-score / EWMA anomaly detector
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
run unattended on live sensor data. A natural extension (not done yet)
would be comparing this against an Isolation Forest or a small
autoencoder trained on the accumulated history.

---

Built by a personal automation project Shaunak set up: it uses Claude to design and write real, working code within his actual skill set, and pushes it here on a regular schedule as an ongoing practice/portfolio project.
