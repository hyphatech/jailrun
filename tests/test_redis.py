from collections.abc import Generator

import pytest
import redis

from jailrun import ROOT_DIR
from jailrun.testing.redis import RedisJail


@pytest.fixture
def redis_jail() -> Generator[RedisJail]:
    with RedisJail(ROOT_DIR / "tests" / "redis.ucl", jail="hypha-redis-test") as r:
        yield r


def test_set_and_get(redis_jail: RedisJail) -> None:
    r = redis.Redis(host="127.0.0.1", port=redis_jail.port)
    r.set("name", "alice")
    assert r.get("name") == b"alice"


def test_empty_after_cleanup(redis_jail: RedisJail) -> None:
    r = redis.Redis(host="127.0.0.1", port=redis_jail.port)
    assert r.dbsize() == 0
