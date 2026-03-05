from collections.abc import Generator

import psycopg
import pytest

from jailrun import ROOT_DIR
from jailrun.testing.postgres import PostgresJail


@pytest.fixture
def postgres_jail() -> Generator[PostgresJail]:
    with PostgresJail(ROOT_DIR / "tests" / "postgres.ucl", jail="hypha-postgres-test") as jail:
        yield jail


@pytest.fixture
def postgres_conn(postgres_jail: PostgresJail) -> Generator[psycopg.Connection]:
    with psycopg.connect(
        host="127.0.0.1", port=postgres_jail.port, dbname=postgres_jail.dbname, user=postgres_jail.user
    ) as conn:
        yield conn


def test_insert_and_query(postgres_conn: psycopg.Connection) -> None:
    with postgres_conn.cursor() as cur:
        cur.execute("CREATE TABLE users (id serial, name text)")
        cur.execute("INSERT INTO users (name) VALUES ('alice')")
        row = cur.execute("SELECT name FROM users WHERE name = 'alice'").fetchone()
        assert row

        [value] = row
        assert value == "alice"


def test_empty_after_cleanup(postgres_conn: psycopg.Connection) -> None:
    with postgres_conn.cursor() as cur:
        tables = cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
        assert tables == []
