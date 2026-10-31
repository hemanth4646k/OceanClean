"""Fetch NOAA NCEI Marine Microplastics samples in the gyre (ArcGIS FeatureServer) into bronze.

The pages are merged into one raw JSON document (features as served) in the cache and bronze;
the ETL filters and normalises them. With the API down, the cached document is used.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from fetch_common import fetch_or_cache, http_get, put_object, record_source
from oceanclean_common.lake import minio_client
from oceanclean_common.regions import BRONZE_MICROPLASTICS, HISTORY_BOX, Box
from oceanclean_common.settings import pg_dsn

log = logging.getLogger("fetch_microplastics")

QUERY_URL = (
    "https://services2.arcgis.com/C8EMgrsFcRFL6LrL/arcgis/rest/services/"
    "Marine_Microplastics_WGS84/FeatureServer/0/query"
)
PAGE_SIZE = 2000  # the service's maxRecordCount

GetJson = Callable[[dict[str, str]], dict]


def envelope_params(box: Box) -> dict[str, str]:
    return {
        "where": "1=1",
        "geometry": f"{box.lon_min},{box.lat_min},{box.lon_max},{box.lat_max}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "f": "json",
    }


def page_params(offset: int, box: Box) -> dict[str, str]:
    return envelope_params(box) | {
        "outFields": "*",
        "orderByFields": "OBJECTID",
        "resultOffset": str(offset),
        "resultRecordCount": str(PAGE_SIZE),
    }


def checked(page: dict) -> dict:
    if "error" in page:
        raise ValueError(f"ArcGIS error: {page['error']}")
    return page


def fetch_features(get_json: GetJson, box: Box) -> list[dict]:
    """All features in the box, paged; fails if the pages don't add up to the server's count."""
    total = checked(get_json(envelope_params(box) | {"returnCountOnly": "true"}))["count"]
    features: list[dict] = []
    while True:
        page = checked(get_json(page_params(len(features), box)))
        features += page["features"]
        if not page.get("exceededTransferLimit") or not page["features"]:
            break
    if len(features) != total:
        raise ValueError(f"paging returned {len(features)} features, expected {total}")
    return features


def bronze_document(features: list[dict], fetched_at: str) -> bytes:
    doc = {
        "query_url": QUERY_URL,
        "envelope": envelope_params(HISTORY_BOX)["geometry"],
        "fetched_at": fetched_at,
        "features": features,
    }
    return json.dumps(doc).encode()


def get_json(params: dict[str, str]) -> dict:
    return json.loads(http_get(QUERY_URL, params))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    cache = Path(os.environ["CACHE_DIR"]) / "microplastics" / "ncei_gyre.json"

    def fetch() -> bytes:
        features = fetch_features(get_json, HISTORY_BOX)
        return bronze_document(features, datetime.now(timezone.utc).isoformat())

    got = fetch_or_cache(fetch, cache)
    n = len(json.loads(got.data)["features"])
    put_object(
        minio_client(os.environ),
        os.environ["LAKE_BUCKET"],
        BRONZE_MICROPLASTICS,
        got.data,
        "application/json",
    )
    detail = {"records": n, "envelope": envelope_params(HISTORY_BOX)["geometry"]}
    record_source(pg_dsn(os.environ), "microplastics", got.source, got.fetched_at, detail)
    log.info("bronze: %d microplastics samples (source=%s)", n, got.source)


if __name__ == "__main__":
    main()
