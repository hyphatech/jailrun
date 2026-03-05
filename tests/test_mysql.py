from collections.abc import Generator

import pymysql
import pytest

from jailrun import ROOT_DIR
from jailrun.testing.mysql import MySQLJail


@pytest.fixture
def mysql() -> Generator[MySQLJail]:
    with MySQLJail(ROOT_DIR / "tests" / "mysql.ucl", jail="hypha-mysql-test") as my:
        yield my


def test_insert_and_query(mysql: MySQLJail) -> None:
    with (
        pymysql.connect(
            host="127.0.0.1",
            port=mysql.port,
            user=mysql.user,
            password=mysql.password,
            database=mysql.dbname,
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


def test_empty_after_cleanup(mysql: MySQLJail) -> None:
    with (
        pymysql.connect(
            host="127.0.0.1",
            port=mysql.port,
            user=mysql.user,
            password=mysql.password,
            database=mysql.dbname,
            autocommit=True,
        ) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()")
        tables = cur.fetchall()
        assert tables == ()
