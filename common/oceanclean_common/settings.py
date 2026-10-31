"""Settings helpers. Every setting's only default lives in .env.example (loaded by Compose)."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import quote


def pg_dsn(env: Mapping[str, str]) -> str:
    """PostGIS DSN from POSTGRES_* settings; raises KeyError if one is missing."""
    user = quote(env["POSTGRES_USER"], safe="")
    password = quote(env["POSTGRES_PASSWORD"], safe="")
    host, port, db = env["POSTGRES_HOST"], env["POSTGRES_PORT"], env["POSTGRES_DB"]
    return f"postgresql://{user}:{password}@{host}:{port}/{quote(db, safe='')}"
