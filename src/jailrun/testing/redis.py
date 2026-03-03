from pathlib import Path
from types import TracebackType
from typing import Self

import redis

from jailrun.cmd import up
from jailrun.settings import Settings
from jailrun.ssh import ssh_exec
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
        super().__init__(config, base=base, settings=settings)
        self.jail = jail
        self.port = port

    def is_ready(self) -> bool:
        result = ssh_exec(
            cmd=f"bastille cmd {self.jail} redis-cli ping",
            private_key=self._settings.ssh_dir / self._settings.ssh_key,
            ssh_user=self._settings.ssh_user,
            ssh_port=self._settings.ssh_port,
        )
        return result is not None and "PONG" in result

    def __enter__(self) -> Self:
        if not self.is_ready():
            up(config=self._config, base=self._base, settings=self._settings)

        redis.Redis(host="127.0.0.1", port=self.port).flushall()

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        redis.Redis(host="127.0.0.1", port=self.port).flushall()
