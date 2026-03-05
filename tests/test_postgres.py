from collections.abc import Generator

import psycopg
import pytest

from jailrun import ROOT_DIR
from jailrun.testing.postgres import PostgresJail


@pytest.fixture
def postgres() -> Generator[PostgresJail]:
    with PostgresJail(ROOT_DIR / "tests" / "postgres.ucl", jail="hypha-postgres-test") as pg:
        yield pg


def test_insert_and_query(postgres: PostgresJail) -> None:
    with psycopg.connect(host="127.0.0.1", port=postgres.port, dbname=postgres.dbname, user=postgres.user) as conn:
        conn.execute("CREATE TABLE users (id serial, name text)")
        conn.execute("INSERT INTO users (name) VALUES ('alice')")
        row = conn.execute("SELECT name FROM users WHERE name = 'alice'").fetchone()
        assert row

        [value] = row
        assert value == "alice"


def test_empty_after_cleanup(postgres: PostgresJail) -> None:
    with psycopg.connect(host="127.0.0.1", port=postgres.port, dbname=postgres.dbname, user=postgres.user) as conn:
        tables = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
        assert tables == []
