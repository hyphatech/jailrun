from pathlib import Path
from types import TracebackType
from typing import Self

import redis

from jailrun.settings import Settings
from jailrun.ssh import jail_ssh_exec
from jailrun.testing.commons import Jail


class RedisJail(Jail):
    def __init__(
        self,
        config: Path,
        jail: str = "hypha-redis",
        *,
        port: int = 6379,
        base: Path | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.port = port
        super().__init__(config, jail=jail, base=base, settings=settings)

    def is_ready(self) -> bool:
        result = jail_ssh_exec(
            "redis-cli ping",
            jail_ip=self._jail_ip,
            private_key=self._settings.ssh_dir / self._settings.ssh_key,
            ssh_user=self._settings.ssh_user,
            ssh_port=self._settings.ssh_port,
        )
        return result is not None and "PONG" in result

    def __enter__(self) -> Self:
        redis.Redis(host="127.0.0.1", port=self.port).flushall()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        redis.Redis(host="127.0.0.1", port=self.port).flushall()
