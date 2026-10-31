import re
from pathlib import Path

import pytest
from oceanclean_common.settings import pg_dsn

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
