"""Settings helpers. Every setting's only default lives in .env.example (loaded by Compose)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from urllib.parse import quote


def pg_dsn(env: Mapping[str, str]) -> str:
    """PostGIS DSN from POSTGRES_* settings; raises KeyError if one is missing."""
    user = quote(env["POSTGRES_USER"], safe="")
    password = quote(env["POSTGRES_PASSWORD"], safe="")
    host, port, db = env["POSTGRES_HOST"], env["POSTGRES_PORT"], env["POSTGRES_DB"]
    return f"postgresql://{user}:{password}@{host}:{port}/{quote(db, safe='')}"


def parse_utc(s: str) -> datetime:
    """ISO-8601 with a UTC offset or trailing Z as an aware datetime; naive input is an error."""
    ts = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if ts.utcoffset() is None:
        raise ValueError(f"timestamp must carry a UTC offset or Z: {s}")
    return ts


def to_utc(ts: datetime) -> datetime:
    """Spark collect() returns naive datetimes in the Python process's local zone; make it UTC."""
    return ts.astimezone(timezone.utc)


def sim_start(env: Mapping[str, str]) -> datetime:
    """SIM_START (ISO-8601 UTC, trailing Z allowed) as an aware datetime."""
    return parse_utc(env["SIM_START"])


def s3a_conf(env: Mapping[str, str]) -> dict[str, str]:
    """Spark config for the MinIO lake over s3a, from MINIO_* settings."""
    prefix = "spark.hadoop.fs.s3a."
    return {
        f"{prefix}endpoint": f"http://{env['MINIO_ENDPOINT']}",
        f"{prefix}access.key": env["MINIO_ROOT_USER"],
        f"{prefix}secret.key": env["MINIO_ROOT_PASSWORD"],
        f"{prefix}path.style.access": "true",
        f"{prefix}connection.ssl.enabled": "false",
        f"{prefix}impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
        f"{prefix}aws.credentials.provider": (
            "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider"
        ),
    }


def lake_url(env: Mapping[str, str], key: str) -> str:
    """s3a:// URL of a lake object or prefix."""
    return f"s3a://{env['LAKE_BUCKET']}/{key}"
