import re
from datetime import timezone
from pathlib import Path

import pytest
from oceanclean_common.settings import lake_url, parse_utc, pg_dsn, s3a_conf, sim_start

ROOT = Path(__file__).resolve().parents[1]
CODE_DIRS = ("common", "simulator", "ingestion", "streaming", "batch", "routing", "api", "infra")
PG_ENV = {
    "POSTGRES_USER": "ocean",
    "POSTGRES_PASSWORD": "p@ss:w/rd",
    "POSTGRES_DB": "oceanclean",
    "POSTGRES_HOST": "postgis",
    "POSTGRES_PORT": "5432",
}


def env_example_keys() -> set[str]:
    lines = (ROOT / ".env.example").read_text().splitlines()
    return {ln.split("=", 1)[0] for ln in lines if ln.strip() and not ln.startswith("#")}


def code_files() -> list[Path]:
    return [p for d in CODE_DIRS if (ROOT / d).exists() for p in (ROOT / d).rglob("*.py")]


def test_pg_dsn_built_from_env_and_escaped() -> None:
    assert pg_dsn(PG_ENV) == "postgresql://ocean:p%40ss%3Aw%2Frd@postgis:5432/oceanclean"


def test_pg_dsn_missing_setting_fails_loudly() -> None:
    env = {k: v for k, v in PG_ENV.items() if k != "POSTGRES_HOST"}
    with pytest.raises(KeyError):
        pg_dsn(env)


def test_s3a_conf_points_spark_at_minio_from_env() -> None:
    env = {"MINIO_ENDPOINT": "minio:9000", "MINIO_ROOT_USER": "u", "MINIO_ROOT_PASSWORD": "p"}
    conf = s3a_conf(env)
    assert conf["spark.hadoop.fs.s3a.endpoint"] == "http://minio:9000"
    assert conf["spark.hadoop.fs.s3a.access.key"] == "u"
    assert conf["spark.hadoop.fs.s3a.secret.key"] == "p"
    assert conf["spark.hadoop.fs.s3a.path.style.access"] == "true"
    assert lake_url({"LAKE_BUCKET": "lake"}, "silver/currents") == "s3a://lake/silver/currents"


def test_every_setting_read_by_code_has_its_default_in_env_example() -> None:
    read = {
        name
        for p in code_files()
        for name in re.findall(r"\b(?:environ|env)\[\s*\"(\w+)\"\s*\]", p.read_text())
    }
    assert read, "scanner found no settings; regex out of date?"
    assert read <= env_example_keys(), f"missing from .env.example: {read - env_example_keys()}"


def test_code_has_no_second_default_for_a_setting() -> None:
    offenders = [
        f"{p.relative_to(ROOT)}: {m}"
        for p in code_files()
        for m in re.findall(r"(?:environ\.get|getenv)\([^)]*", p.read_text())
    ]
    assert not offenders, "read settings with os.environ[...]; defaults live in .env.example"


def test_sim_start_is_parsed_as_aware_utc() -> None:
    ts = sim_start({"SIM_START": "2026-09-01T00:00:00Z"})
    assert ts.utcoffset() == timezone.utc.utcoffset(None) and ts.hour == 0
    with pytest.raises(ValueError):
        sim_start({"SIM_START": "2026-09-01T00:00:00"})


def test_parse_utc_accepts_z_and_offsets_and_rejects_naive_times() -> None:
    assert parse_utc("2026-09-01T06:00:00Z").hour == 6
    assert parse_utc("2026-09-01T08:00:00+02:00").astimezone(timezone.utc).hour == 6
    with pytest.raises(ValueError):
        parse_utc("2026-09-01T06:00:00")
