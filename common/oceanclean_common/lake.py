"""MinIO client for the lake, from MINIO_* settings (Python services; Spark uses s3a_conf)."""

from __future__ import annotations

from collections.abc import Mapping

from minio import Minio


def minio_client(env: Mapping[str, str]) -> Minio:
    return Minio(
        env["MINIO_ENDPOINT"],
        access_key=env["MINIO_ROOT_USER"],
        secret_key=env["MINIO_ROOT_PASSWORD"],
        secure=False,
    )
