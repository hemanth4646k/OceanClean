"""Ingestion endpoint: validates telemetry against the contract and publishes to Kafka."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic
from fastapi import FastAPI, HTTPException
from oceanclean_common.telemetry import TELEMETRY_TOPIC, Telemetry, kafka_key

log = logging.getLogger("ingestion")
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
PARTITIONS = int(os.environ.get("TELEMETRY_PARTITIONS", "6"))

producer: Producer | None = None


def ensure_topics() -> None:
    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    existing = admin.list_topics(timeout=10).topics
    new = [
        NewTopic(t, num_partitions=PARTITIONS, replication_factor=1)
        for t in (TELEMETRY_TOPIC,)
        if t not in existing
    ]
    for topic, fut in admin.create_topics(new).items() if new else []:
        fut.result()
        log.info("created topic %s with %d partitions", topic, PARTITIONS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global producer
    ensure_topics()
    # acks=all + idempotence: burst ingestion without loss or duplicates (SRS 4.1).
    producer = Producer(
        {
            "bootstrap.servers": BOOTSTRAP,
            "acks": "all",
            "enable.idempotence": True,
            "linger.ms": 20,
            "compression.type": "lz4",
            "queue.buffering.max.messages": 500000,
        }
    )
    yield
    producer.flush(10)


app = FastAPI(title="OceanClean ingestion", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/telemetry", status_code=202)
def ingest(payload: Telemetry | list[Telemetry]) -> dict[str, int]:
    assert producer is not None
    events = payload if isinstance(payload, list) else [payload]
    for t in events:
        try:
            producer.produce(TELEMETRY_TOPIC, key=kafka_key(t), value=t.to_json())
        except BufferError as e:
            producer.flush(5)
            raise HTTPException(503, "broker backpressure, retry") from e
        producer.poll(0)
    producer.flush(10)
    return {"accepted": len(events)}
