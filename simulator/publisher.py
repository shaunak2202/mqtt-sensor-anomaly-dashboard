"""Simulates a handful of IoT sensors publishing readings over MQTT.

Each sensor publishes a JSON payload of the form:
    {"sensor": "temperature", "value": 24.3, "timestamp": "2024-05-01T12:00:00"}

Occasionally injects spikes/dropouts so downstream anomaly detection has
something real to catch.
"""
import json
import os
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "localhost")
BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
PUBLISH_INTERVAL_SECONDS = 2
ANOMALY_PROBABILITY = 0.04  # ~4% of readings get an injected spike

# (topic, base value, noise stddev, spike multiplier range)
SENSORS = [
    ("temperature", 24.0, 0.6, (1.4, 1.9)),
    ("humidity", 55.0, 2.0, (1.3, 1.6)),
    ("soil_moisture", 40.0, 1.5, (0.3, 0.5)),  # anomaly here = a drop, not a spike
]


def generate_reading(base: float, noise_std: float, spike_range) -> float:
    value = random.gauss(base, noise_std)
    if random.random() < ANOMALY_PROBABILITY:
        multiplier = random.uniform(*spike_range)
        value *= multiplier
    return round(value, 2)


def main():
    client = mqtt.Client()
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()

    print(f"Publishing simulated readings every {PUBLISH_INTERVAL_SECONDS}s. Ctrl+C to stop.")
    try:
        while True:
            for sensor_name, base, noise_std, spike_range in SENSORS:
                value = generate_reading(base, noise_std, spike_range)
                payload = {
                    "sensor": sensor_name,
                    "value": value,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                topic = f"sensors/{sensor_name}"
                client.publish(topic, json.dumps(payload))
                print(f"published {topic} -> {payload}")
            time.sleep(PUBLISH_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopping publisher.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
