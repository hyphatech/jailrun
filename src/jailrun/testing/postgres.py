from pathlib import Path
from types import TracebackType
from typing import Self

from jailrun.network import get_ssh_kw, jail_ssh_exec
from jailrun.settings import Settings
from jailrun.testing.commons import Jail


class PostgresJail(Jail):
    def __init__(
        self,
        jail: str = "hypha-postgres-test",
        *,
        jail_config: Path,
        settings: Settings | None = None,
        user: str = "postgres",
        dbname: str = "testdb",
        port: int = 6432,
    ) -> None:
        self.user = user
        self.dbname = dbname
        self.port = port
        super().__init__(jail=jail, jail_config=jail_config, settings=settings)

    def is_ready(self) -> bool:
        result = jail_ssh_exec(
            f"su -m {self.user} -c 'psql -c \"SELECT 1\"'",
            jail_ip=self._jail_ip,
            ssh_kw=get_ssh_kw(self._settings, self._state),
        )
        return result is not None

    def __enter__(self) -> Self:
        jail_ssh_exec(
            f"su -m {self.user} -c 'psql -c \"DROP DATABASE IF EXISTS {self.dbname}\"'",
            jail_ip=self._jail_ip,
            ssh_kw=get_ssh_kw(self._settings, self._state),
        )
        jail_ssh_exec(
            f"su -m {self.user} -c 'psql -c \"CREATE DATABASE {self.dbname}\"'",
            jail_ip=self._jail_ip,
            ssh_kw=get_ssh_kw(self._settings, self._state),
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        jail_ssh_exec(
            f"su -m {self.user} -c 'psql -c \"DROP DATABASE IF EXISTS {self.dbname}\"'",
            jail_ip=self._jail_ip,
            ssh_kw=get_ssh_kw(self._settings, self._state),
        )
