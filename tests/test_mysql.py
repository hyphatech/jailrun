from collections.abc import Generator

import pymysql
import pytest

from jailrun import ROOT_DIR
from jailrun.testing.mysql import MySQLJail


@pytest.fixture
def mysql_jail() -> Generator[MySQLJail]:
    with MySQLJail(ROOT_DIR / "tests" / "mysql.ucl", jail="hypha-mysql-test") as jail:
        yield jail


@pytest.fixture
def mysql_conn(mysql_jail: MySQLJail) -> Generator[pymysql.Connection]:
    with (
        pymysql.connect(
            host="127.0.0.1",
            port=mysql_jail.port,
            user=mysql_jail.user,
            password=mysql_jail.password,
            database=mysql_jail.dbname,
            autocommit=True,
        ) as conn,
    ):
        yield conn


def test_insert_and_query(mysql_conn: pymysql.Connection) -> None:
    with mysql_conn.cursor() as cur:
        cur.execute("CREATE TABLE users (id INT AUTO_INCREMENT PRIMARY KEY, name TEXT)")
        cur.execute("INSERT INTO users (name) VALUES ('alice')")
        cur.execute("SELECT name FROM users WHERE name = 'alice' LIMIT 1")
        row = cur.fetchone()
        assert row

        [value] = row
        assert value == "alice"


def test_empty_after_cleanup(mysql_conn: pymysql.Connection) -> None:
    with mysql_conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()")
        tables = cur.fetchall()
        assert tables == ()
