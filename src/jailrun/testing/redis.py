from pathlib import Path
from types import TracebackType
from typing import Self

import redis

from jailrun.network import get_ssh_kw, jail_ssh_exec
from jailrun.settings import Settings
from jailrun.testing.commons import Jail


class RedisJail(Jail):
    def __init__(
        self,
        jail: str = "hypha-redis-test",
        *,
        jail_config: Path,
        base_config: Path | None = None,
        settings: Settings | None = None,
        port: int = 7379,
    ) -> None:
        self.port = port
        super().__init__(jail=jail, jail_config=jail_config, base_config=base_config, settings=settings)

    def is_ready(self) -> bool:
        result = jail_ssh_exec(
            "redis-cli ping",
            jail_ip=self._jail_ip,
            **get_ssh_kw(self._settings, self._state),
        )
        return result is not None and "PONG" in result

    def __enter__(self) -> Self:
        redis.Redis(host=self._settings.vm_host, port=self.port).flushall()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        redis.Redis(host=self._settings.vm_host, port=self.port).flushall()
