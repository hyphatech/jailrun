from collections.abc import Generator

import pymysql
import pytest

from jailrun import ROOT_DIR
from jailrun.testing.mariadb import MariaDBJail


@pytest.fixture
def mariadb() -> Generator[MariaDBJail]:
    with MariaDBJail(ROOT_DIR / "tests" / "mariadb.ucl", jail="hypha-mariadb-test") as db:
        yield db


def test_insert_and_query(mariadb: MariaDBJail) -> None:
    with (
        pymysql.connect(
            host="127.0.0.1",
            port=mariadb.port,
            user=mariadb.user,
            password=mariadb.password,
            database=mariadb.dbname,
            autocommit=True,
        ) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("CREATE TABLE users (id INT AUTO_INCREMENT PRIMARY KEY, name TEXT)")
        cur.execute("INSERT INTO users (name) VALUES ('alice')")
        cur.execute("SELECT name FROM users WHERE name = 'alice' LIMIT 1")
        row = cur.fetchone()
        assert row

        [value] = row
        assert value == "alice"


def test_empty_after_cleanup(mariadb: MariaDBJail) -> None:
    with (
        pymysql.connect(
            host="127.0.0.1",
            port=mariadb.port,
            user=mariadb.user,
            password=mariadb.password,
            database=mariadb.dbname,
            autocommit=True,
        ) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()")
        tables = cur.fetchall()
        assert tables == ()
