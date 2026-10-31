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
from oceanclean_common.telemetry import TELEMETRY_TOPIC, Telemetry, kafka_key

log = logging.getLogger("uvicorn.error")
# Below the simulator's 5 s HTTP timeout, so a stuck broker surfaces as 503, not a client timeout.
ACK_TIMEOUT_S = 3.0

producer: Producer | None = None


def ensure_topic(bootstrap: str, partitions: int) -> None:
    admin = AdminClient({"bootstrap.servers": bootstrap})
    if TELEMETRY_TOPIC in admin.list_topics(timeout=10).topics:
        return
    topic = NewTopic(TELEMETRY_TOPIC, num_partitions=partitions, replication_factor=1)
    admin.create_topics([topic])[TELEMETRY_TOPIC].result()
    log.info("created topic %s with %d partitions", TELEMETRY_TOPIC, partitions)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global producer
    bootstrap = os.environ["KAFKA_BOOTSTRAP"]
    ensure_topic(bootstrap, int(os.environ["TELEMETRY_PARTITIONS"]))
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


@app.post("/telemetry", status_code=202)
def ingest(payload: Telemetry | list[Telemetry]) -> dict[str, int]:
    assert producer is not None
    events = payload if isinstance(payload, list) else [payload]
    reports: list[KafkaError | None] = []

    def on_delivery(err: KafkaError | None, _msg: Message) -> None:
        reports.append(err)

    for t in events:
        try:
            producer.produce(
                TELEMETRY_TOPIC, key=kafka_key(t), value=t.to_json(), on_delivery=on_delivery
            )
        except BufferError as e:
            raise HTTPException(503, "broker backpressure, retry") from e
        producer.poll(0)
    # Wait for this request's own delivery reports. flush() would count every request's queue,
    # since sync routes share the producer across threadpool workers.
    deadline = time.monotonic() + ACK_TIMEOUT_S
    while len(reports) < len(events) and time.monotonic() < deadline:
        producer.poll(0.05)
    errors = [e for e in reports if e is not None]
    acked = len(reports) - len(errors)
    if acked != len(events):
        # Unacked events may still be delivered later; a client retry duplicates them, which
        # (vessel_id, seq) dedup absorbs. Losing them silently would not be absorbed.
        log.warning("kafka acked %d/%d events (errors: %s)", acked, len(events), errors[:3])
        raise HTTPException(503, f"kafka acknowledged {acked}/{len(events)} events, retry")
    return {"accepted": len(events)}
