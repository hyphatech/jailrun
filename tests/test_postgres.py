from collections.abc import Generator

import psycopg
import pytest

from jailrun import ROOT_DIR
from jailrun.settings import Settings
from jailrun.testing.postgres import PostgresJail

pytestmark = pytest.mark.freebsd_vm


@pytest.fixture
def postgres_jail() -> Generator[PostgresJail]:
    with PostgresJail("hypha-postgres-test", jail_config=ROOT_DIR / "tests" / "postgres.ucl") as jail:
        yield jail


@pytest.fixture
def postgres_conn(settings: Settings, postgres_jail: PostgresJail) -> Generator[psycopg.Connection]:
    with psycopg.connect(
        host=settings.vm_host, port=postgres_jail.port, dbname=postgres_jail.dbname, user=postgres_jail.user
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
