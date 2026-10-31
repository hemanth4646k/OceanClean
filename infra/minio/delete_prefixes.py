"""Delete every lake object under the given prefixes. Used by infra/reset_sim.sh."""

import os
import sys

from minio import Minio
from minio.deleteobjects import DeleteObject


def main() -> None:
    client = Minio(
        os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ROOT_USER"],
        secret_key=os.environ["MINIO_ROOT_PASSWORD"],
        secure=False,
    )
    bucket = os.environ["LAKE_BUCKET"]
    for prefix in sys.argv[1:]:
        objs = [DeleteObject(o.object_name) for o in client.list_objects(bucket, prefix, True)]
        errors = list(client.remove_objects(bucket, objs))
        if errors:
            raise SystemExit(f"{prefix}: {errors[:3]}")
        print(f"{prefix}: removed {len(objs)} objects")


if __name__ == "__main__":
    main()
