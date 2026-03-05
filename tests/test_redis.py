from collections.abc import Generator

import pytest
import redis

from jailrun import ROOT_DIR
from jailrun.testing.redis import RedisJail


@pytest.fixture
def redis_jail() -> Generator[RedisJail]:
    with RedisJail(ROOT_DIR / "tests" / "redis.ucl", jail="hypha-redis-test") as jail:
        yield jail


@pytest.fixture
def redis_conn(redis_jail: RedisJail) -> redis.Redis:
    return redis.Redis(host="127.0.0.1", port=redis_jail.port)


def test_set_and_get(redis_conn: redis.Redis) -> None:
    redis_conn.set("name", "alice")
    assert redis_conn.get("name") == b"alice"


def test_empty_after_cleanup(redis_conn: redis.Redis) -> None:
    assert redis_conn.dbsize() == 0
