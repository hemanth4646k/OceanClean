"""Fetch-and-cache helpers shared by the batch fetchers (ADR-0002).

Every fetch tries the API, writes the raw response to the local cache and to bronze on MinIO,
and falls back to the cache when the API fails. data_sources records which one was used.
"""

from __future__ import annotations

import io
import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
import psycopg
from minio import Minio

log = logging.getLogger("fetch")

Source = Literal["api", "cache"]
# What a failed or bad fetch raises: network errors, HTTP status errors, invalid payloads.
FETCH_ERRORS = (httpx.HTTPError, OSError, ValueError)
TIMEOUT = httpx.Timeout(30.0, read=180.0)
ATTEMPTS = 3


@dataclass(frozen=True)
class Fetched:
    data: bytes
    source: Source
    fetched_at: datetime


def http_get(url: str, params: Mapping[str, str] | None = None) -> bytes:
    """GET with redirects (ERDDAP answers 302) and a few retries; raises on the last failure."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            resp = httpx.get(url, params=params, follow_redirects=True, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPError as e:
            if attempt == ATTEMPTS:
                raise
            log.warning("GET failed (%s), retry %d/%d", e.__class__.__name__, attempt, ATTEMPTS)
            time.sleep(2 * attempt)
    raise AssertionError("unreachable")


def write_atomic(path: Path, data: bytes) -> None:
    """Write via a .part file and rename, so a crash never leaves a truncated cache entry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_bytes(data)
    part.replace(path)


def cached(path: Path) -> Fetched:
    """A cache entry; its mtime is when it was fetched from the API."""
    mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return Fetched(path.read_bytes(), "cache", mtime)


def fetch_or_cache(fetch: Callable[[], bytes], cache: Path) -> Fetched:
    """Fetch and refresh the cache; on failure use the cache, or re-raise if there is none."""
    try:
        data = fetch()
    except FETCH_ERRORS as e:
        if not cache.exists():
            raise
        log.warning("fetch failed (%s: %s); source=cache %s", e.__class__.__name__, e, cache)
        return cached(cache)
    write_atomic(cache, data)
    return Fetched(data, "api", datetime.now(timezone.utc))


def put_object(client: Minio, bucket: str, key: str, data: bytes, content_type: str) -> None:
    client.put_object(bucket, key, io.BytesIO(data), len(data), content_type=content_type)


def record_source(
    dsn: str, dataset: str, source: Source, fetched_at: datetime, detail: Mapping[str, object]
) -> None:
    """Upsert the dataset's provenance into PostGIS data_sources (shown in the UI)."""
    with psycopg.connect(dsn) as conn:
        conn.execute(
            """
            INSERT INTO data_sources (dataset, source, fetched_at, detail, recorded_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (dataset) DO UPDATE SET source = EXCLUDED.source,
              fetched_at = EXCLUDED.fetched_at, detail = EXCLUDED.detail, recorded_at = now()
            """,
            (dataset, source, fetched_at, json.dumps(detail)),
        )
    log.info("data_sources: %s source=%s fetched_at=%s", dataset, source, fetched_at.isoformat())
