"""Subscribes to sensor MQTT topics and persists incoming readings to SQLite."""
import json
import logging

import paho.mqtt.client as mqtt

from ingest.db import init_db, insert_reading

BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPIC_FILTER = "sensors/#"  # subscribes to sensors/temperature, sensors/humidity, etc.

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("subscriber")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("Connected to broker at %s:%s", BROKER_HOST, BROKER_PORT)
        client.subscribe(TOPIC_FILTER)
        log.info("Subscribed to %s", TOPIC_FILTER)
    else:
        log.error("Failed to connect to broker, return code %s", rc)


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        sensor = payload["sensor"]
        value = float(payload["value"])
        timestamp = payload["timestamp"]
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        log.warning("Dropping malformed message on %s: %s (%s)", msg.topic, msg.payload, e)
        return

    insert_reading(sensor, value, timestamp)
    log.info("Stored reading sensor=%s value=%.2f ts=%s", sensor, value, timestamp)


def main():
    init_db()
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    log.info("Connecting to broker...")
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
