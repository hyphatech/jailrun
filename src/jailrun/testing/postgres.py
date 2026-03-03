from pathlib import Path
from types import TracebackType
from typing import Self

from jailrun.cmd import up
from jailrun.settings import Settings
from jailrun.ssh import ssh_exec
from jailrun.testing.commons import Jail


class PostgresJail(Jail):
    def __init__(
        self,
        config: Path,
        jail: str = "hypha-postgres",
        *,
        user: str = "postgres",
        dbname: str = "testdb",
        port: int = 6432,
        base: Path | None = None,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(config, base=base, settings=settings)
        self.jail = jail
        self.user = user
        self.dbname = dbname
        self.port = port

    def is_ready(self) -> bool:
        result = ssh_exec(
            cmd=f"bastille cmd {self.jail} su -m {self.user} -c 'psql -c \"SELECT 1\"'",
            private_key=self._settings.ssh_dir / self._settings.ssh_key,
            ssh_user=self._settings.ssh_user,
            ssh_port=self._settings.ssh_port,
        )
        return result is not None

    def __enter__(self) -> Self:
        if not self.is_ready():
            up(config=self._config, base=self._base, settings=self._settings)
        else:
            ssh_exec(
                cmd=f"bastille cmd {self.jail} su -m {self.user} -c 'psql -c \"CREATE DATABASE {self.dbname}\"'",
                private_key=self._settings.ssh_dir / self._settings.ssh_key,
                ssh_user=self._settings.ssh_user,
                ssh_port=self._settings.ssh_port,
            )

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        ssh_exec(
            cmd=f"bastille cmd {self.jail} su -m {self.user} -c 'psql -c \"DROP DATABASE IF EXISTS {self.dbname}\"'",
            private_key=self._settings.ssh_dir / self._settings.ssh_key,
            ssh_user=self._settings.ssh_user,
            ssh_port=self._settings.ssh_port,
        )
