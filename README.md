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

## Current status (session 3 -- complete)

Everything from the plan is now built and wired together:

- `simulator/publisher.py` -- simulates 3 sensors (temperature, humidity,
  soil moisture) publishing JSON readings to an MQTT broker on a timer,
  with occasional injected spikes/dropouts.
- `ingest/subscriber.py` -- subscribes to all sensor topics, parses
  incoming JSON payloads, and writes every reading into a local SQLite
  database (`data/sensors.db`).
- `ingest/db.py` -- schema + helper functions for reading/writing
  readings, plus a `settings` table used to persist per-sensor detector
  config (window/threshold) set from the UI.
- `analysis/anomaly.py` -- rolling z-score / EWMA-based anomaly detector,
  with a CLI mode for backfilling/tuning.
- `analysis/worker.py` -- background loop that polls each known sensor on
  an interval, runs the detector, marks new anomalies, logs an alert
  line, and now **fires configured alert hooks** (webhook/email) through
  `analysis/alerts.py`. It also picks up per-sensor window/threshold
  overrides from the `settings` table set via the dashboard, so tuning no
  longer requires restarting the worker with new CLI flags.
- `analysis/alerts.py` -- **new**. A small pluggable alerting layer:
  - `WebhookAlertHook` -- POSTs a JSON payload to a configured URL
    (`ALERT_WEBHOOK_URL` env var). Uses `urllib` so no extra dependency
    is needed, fails soft (logs and continues) if the endpoint is
    unreachable.
  - `EmailAlertHook` -- sends a plain-text email via SMTP using
    `ALERT_SMTP_HOST`/`ALERT_SMTP_PORT`/`ALERT_EMAIL_FROM`/`ALERT_EMAIL_TO`
    env vars. Also fails soft.
  - `LogAlertHook` -- always-on fallback that just logs (this is what
    session 2 did inline; it's now one of several hooks instead of the
    only option).
  - Hooks are selected via the `ALERT_HOOKS` env var (comma list, e.g.
    `log,webhook`); nothing is required to be configured for the app to
    keep working as before.
- `webapp/app.py` -- Flask API, now with two additions:
  - `GET /api/settings/<sensor>` / `POST /api/settings/<sensor>` -- read
    and update the per-sensor window/threshold used by the worker, so
    tuning is exposed in the UI instead of only via CLI/worker flags.
  - `GET /api/readings/<sensor>` now accepts `since` (ISO timestamp) in
    addition to `limit`, backing the dashboard's time-range picker.
- `webapp/templates/index.html` + `webapp/static/dashboard.js` -- dashboard
  now has, per sensor card: a time-range selector (last 15m/1h/6h/24h/all),
  and window/threshold number inputs with an "apply" button that calls the
  new settings endpoint -- so you can retune sensitivity live without
  touching code.
- `tests/test_anomaly.py` -- unchanged detector tests (still passing).
- `tests/test_alerts.py` -- **new**. Tests for the alert hook registry
  and the webhook/email hooks using mocked network calls (no real
  network access needed to run the suite).
- `docker-compose.yml` + `Dockerfile` -- **new**. Runs the Mosquitto
  broker, subscriber, simulator, worker, and webapp together with one
  command, sharing the SQLite file through a mounted volume.

This project is now considered feature-complete for its original scope:
ingest -> store -> detect -> alert -> visualize, with tunable detection
and one-command deployment.

### Possible future extensions (not planned for this repo's remaining sessions)
- Comparing the z-score/EWMA approach against an Isolation Forest or a
  small autoencoder trained on accumulated history.
- Multi-user auth on the dashboard if this ever left "personal tool"
  territory.

## Architecture

```
 publisher(s) --MQTT--> broker (mosquitto) --MQTT--> subscriber --> SQLite
                                                                      |
                                                     worker.py polls on an
                                                     interval (reading
                                                     per-sensor settings
                                                     from SQLite), runs
                                                     anomaly.py, marks
                                                     flags, and fires
                                                     alert hooks
                                                     (log/webhook/email)
                                                                      |
                                                        Flask app (webapp/)
                                                        serves JSON API +
                                                        Chart.js dashboard,
                                                        including a
                                                        settings endpoint
                                                        for live tuning
```

## Requirements

- Python 3.10+
- A running MQTT broker. Easiest local option: [Mosquitto](https://mosquitto.org/)
  ```
  # macOS
  brew install mosquitto
  mosquitto -p 1883
  ```
  Or run it in Docker (or just use `docker-compose up`, see below).

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running it (manual, four terminals)

**1. Start the subscriber (writes incoming readings to SQLite):**
```bash
python -m ingest.subscriber
```

**2. Start the simulated publisher:**
```bash
python -m simulator.publisher
```

**3. Start the background anomaly worker (continuously flags new readings, fires alerts):**
```bash
python -m analysis.worker
```
By default this uses the `log` alert hook, which just prints lines like:
```
[ALERT] sensor=soil_moisture value=14.20 z=-4.31 at 2024-05-01T12:03:41
```
To also fire a webhook and/or email on each new anomaly:
```bash
export ALERT_HOOKS=log,webhook
export ALERT_WEBHOOK_URL=https://example.com/hooks/anomaly
python -m analysis.worker
```
Per-sensor `--window`/`--threshold` set via CLI flags are used as
defaults; if a sensor has an override saved through the dashboard's
settings panel, that override wins.

**4. Start the dashboard:**
```bash
python -m webapp.app
```
Then open http://localhost:5000. Each sensor card now has a time-range
dropdown and a small window/threshold form you can apply live.

## Running it with Docker Compose (one command)

```bash
docker-compose up --build
```
This starts: an `eclipse-mosquitto` broker, the simulator, the
subscriber, the worker, and the webapp, all networked together, with
`data/` mounted as a volume so the SQLite file persists across restarts.
Open http://localhost:5000 once it's up.

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
│   └── db.py              # SQLite schema + helpers (+ settings table)
├── analysis/
│   ├── anomaly.py         # rolling z-score / EWMA anomaly detector (+ CLI)
│   ├── worker.py          # continuous background detector loop + alerts
│   └── alerts.py          # pluggable alert hooks (log/webhook/email)
├── webapp/
│   ├── app.py              # Flask app + JSON API + settings endpoint
│   ├── templates/
│   │   └── index.html
│   └── static/
│       └── dashboard.js    # Chart.js polling frontend + controls
├── tests/
│   ├── test_anomaly.py
│   └── test_alerts.py
├── data/                  # sensors.db created here at runtime
├── docker-compose.yml
├── Dockerfile
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
run unattended on live sensor data. The background worker just re-runs
this same function on a timer per sensor, now reading per-sensor
window/threshold overrides from a small `settings` table so the dashboard
can retune it live, rather than introducing a separate streaming/
incremental variant. This keeps the CLI, worker, and dashboard all backed
by identical logic.

Alerting is intentionally a thin, swappable layer (`analysis/alerts.py`)
rather than baked into the worker: adding a Slack hook or a paging
integration later is a matter of writing one more small class and adding
it to `ALERT_HOOKS`, not touching detection code.

---

Built by a personal automation project Shaunak set up: it uses Claude to design and write real, working code within his actual skill set, and pushes it here on a regular schedule as an ongoing practice/portfolio project.

---

Built by a personal automation project Shaunak set up: it uses Claude to design and write real, working code within his actual skill set, and pushes it here on a regular schedule as an ongoing practice/portfolio project.
