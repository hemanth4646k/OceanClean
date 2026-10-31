"""Column types of the tables in infra/postgres/init.sql, for contract tests."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

INIT_SQL = Path(__file__).resolve().parents[1] / "infra" / "postgres" / "init.sql"
SPARK_TYPE = {str: "STRING", datetime: "TIMESTAMP", int: "BIGINT", float: "DOUBLE", bool: "BOOLEAN"}
PG_TYPE = {
    str: "TEXT",
    datetime: "TIMESTAMPTZ",
    int: "BIGINT",
    float: "DOUBLE PRECISION",
    bool: "BOOLEAN",
}


def table_columns(table: str) -> dict[str, str]:
    """Column name -> SQL type of one table, constraints stripped."""
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", INIT_SQL.read_text(), re.S)
    assert m, f"{table} table not found in init.sql"
    cols = {}
    for line in m.group(1).strip().splitlines():
        name, rest = line.strip().rstrip(",").split(None, 1)
        cols[name] = re.split(r"\s+(?:NOT NULL|NULL|PRIMARY KEY|DEFAULT)\b", rest)[0]
    return cols
