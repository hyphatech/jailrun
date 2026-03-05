from collections.abc import Generator

import pymysql
import pytest

from jailrun import ROOT_DIR
from jailrun.testing.mariadb import MariaDBJail


@pytest.fixture
def mariadb_jail() -> Generator[MariaDBJail]:
    with MariaDBJail(ROOT_DIR / "tests" / "mariadb.ucl", jail="hypha-mariadb-test") as jail:
        yield jail


@pytest.fixture
def mariadb_conn(mariadb_jail: MariaDBJail) -> Generator[pymysql.Connection]:
    with (
        pymysql.connect(
            host="127.0.0.1",
            port=mariadb_jail.port,
            user=mariadb_jail.user,
            password=mariadb_jail.password,
            database=mariadb_jail.dbname,
            autocommit=True,
        ) as conn,
    ):
        yield conn


def test_insert_and_query(mariadb_conn: pymysql.Connection) -> None:
    with mariadb_conn.cursor() as cur:
        cur.execute("CREATE TABLE users (id INT AUTO_INCREMENT PRIMARY KEY, name TEXT)")
        cur.execute("INSERT INTO users (name) VALUES ('alice')")
        cur.execute("SELECT name FROM users WHERE name = 'alice' LIMIT 1")
        row = cur.fetchone()
        assert row

        [value] = row
        assert value == "alice"


def test_empty_after_cleanup(mariadb_conn: pymysql.Connection) -> None:
    with mariadb_conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()")
        tables = cur.fetchall()
        assert tables == ()
