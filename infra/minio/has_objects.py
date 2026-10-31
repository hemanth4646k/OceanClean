"""Exit 0 if every given lake object exists, else 1. Used by start.sh to detect a fresh lake."""

import os
import sys

from minio import Minio
from minio.error import S3Error


def main() -> None:
    client = Minio(
        os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ROOT_USER"],
        secret_key=os.environ["MINIO_ROOT_PASSWORD"],
        secure=False,
    )
    bucket = os.environ["LAKE_BUCKET"]
    for name in sys.argv[1:]:
        try:
            client.stat_object(bucket, name)
        except S3Error as e:
            if e.code != "NoSuchKey":
                raise
            print(f"missing: {name}")
            sys.exit(1)


if __name__ == "__main__":
    main()
