"""Create the lake bucket (idempotent). Runs once as a Compose init job."""

import os
import time

from minio import Minio

client = Minio(
    os.environ["MINIO_ENDPOINT"],
    access_key=os.environ["MINIO_ROOT_USER"],
    secret_key=os.environ["MINIO_ROOT_PASSWORD"],
    secure=False,
)
bucket = os.environ["LAKE_BUCKET"]
for _ in range(30):
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        print(f"bucket {bucket} ready")
        break
    except Exception as e:  # MinIO not up yet
        print(f"waiting for minio ({e.__class__.__name__})")
        time.sleep(2)
else:
    raise SystemExit("minio never became ready")
