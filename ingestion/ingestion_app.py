"""Ingestion endpoint: validates telemetry against the contract and publishes to Kafka."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from confluent_kafka import KafkaError, Message, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from fastapi import FastAPI, HTTPException
from oceanclean_common.debris import DEBRIS_TOPIC, PatchSurvey
from oceanclean_common.telemetry import TELEMETRY_TOPIC, Telemetry, kafka_key

log = logging.getLogger("uvicorn.error")
# Below the simulator's 5 s HTTP timeout, so a stuck broker surfaces as 503, not a client timeout.
ACK_TIMEOUT_S = 3.0

producer: Producer | None = None


def ensure_topic(admin: AdminClient, name: str, partitions: int) -> None:
    if name in admin.list_topics(timeout=10).topics:
        return
    topic = NewTopic(name, num_partitions=partitions, replication_factor=1)
    admin.create_topics([topic])[name].result()
    log.info("created topic %s with %d partitions", name, partitions)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global producer
    bootstrap = os.environ["KAFKA_BOOTSTRAP"]
    admin = AdminClient({"bootstrap.servers": bootstrap})
    ensure_topic(admin, TELEMETRY_TOPIC, int(os.environ["TELEMETRY_PARTITIONS"]))
    # One survey row per patch per sim-hour: a single partition is plenty.
    ensure_topic(admin, DEBRIS_TOPIC, 1)
    # acks=all + idempotence: producer retries never duplicate or reorder (SRS 4.1).
    # ingest() answers 202 only for events the broker acknowledged.
    producer = Producer(
        {
            "bootstrap.servers": bootstrap,
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


def publish(topic: str, records: list[tuple[str, str]]) -> int:
    """Produce (key, value) records; returns the count, or 503 unless the broker acked all."""
    assert producer is not None
    reports: list[KafkaError | None] = []

    def on_delivery(err: KafkaError | None, _msg: Message) -> None:
        reports.append(err)

    for key, value in records:
        try:
            producer.produce(topic, key=key, value=value, on_delivery=on_delivery)
        except BufferError as e:
            raise HTTPException(503, "broker backpressure, retry") from e
        producer.poll(0)
    # Wait for this request's own delivery reports. flush() would count every request's queue,
    # since sync routes share the producer across threadpool workers.
    deadline = time.monotonic() + ACK_TIMEOUT_S
    while len(reports) < len(records) and time.monotonic() < deadline:
        producer.poll(0.05)
    errors = [e for e in reports if e is not None]
    acked = len(reports) - len(errors)
    if acked != len(records):
        # Unacked events may still be delivered later; a client retry duplicates them, which
        # (vessel_id, seq) dedup absorbs. Losing them silently would not be absorbed.
        log.warning(
            "kafka acked %d/%d %s records (errors: %s)", acked, len(records), topic, errors[:3]
        )
        raise HTTPException(503, f"kafka acknowledged {acked}/{len(records)} records, retry")
    return len(records)


@app.post("/telemetry", status_code=202)
def ingest(payload: Telemetry | list[Telemetry]) -> dict[str, int]:
    events = payload if isinstance(payload, list) else [payload]
    return {"accepted": publish(TELEMETRY_TOPIC, [(kafka_key(t), t.to_json()) for t in events])}


@app.post("/debris-survey", status_code=202)
def debris_survey(payload: list[PatchSurvey]) -> dict[str, int]:
    """One debris survey: the current state of every patch (mass 0 = collected)."""
    return {"accepted": publish(DEBRIS_TOPIC, [(s.patch_id, s.to_json()) for s in payload])}
