from pathlib import Path
from types import TracebackType
from typing import Self

from jailrun.settings import Settings
from jailrun.ssh import get_ssh_kw, jail_ssh_exec
from jailrun.testing.commons import Jail


class MySQLJail(Jail):
    def __init__(
        self,
        jail: str = "hypha-mysql-test",
        *,
        jail_config: Path,
        base_config: Path | None = None,
        settings: Settings | None = None,
        user: str = "test",
        password: str = "test",
        dbname: str = "testdb",
        port: int = 4306,
    ) -> None:
        self.user = user
        self.password = password
        self.dbname = dbname
        self.port = port
        super().__init__(jail=jail, jail_config=jail_config, base_config=base_config, settings=settings)

    def is_ready(self) -> bool:
        result = jail_ssh_exec(
            "mysqladmin -u root ping",
            jail_ip=self._jail_ip,
            **get_ssh_kw(self._settings, self._state),
        )
        return result is not None

    def __enter__(self) -> Self:
        jail_ssh_exec(
            f"mysql -u root -e 'DROP DATABASE IF EXISTS `{self.dbname}`'",
            jail_ip=self._jail_ip,
            **get_ssh_kw(self._settings, self._state),
        )
        jail_ssh_exec(
            f"mysql -u root -e 'CREATE DATABASE `{self.dbname}`'",
            jail_ip=self._jail_ip,
            **get_ssh_kw(self._settings, self._state),
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        jail_ssh_exec(
            f"mysql -u root -e 'DROP DATABASE IF EXISTS `{self.dbname}`'",
            jail_ip=self._jail_ip,
            **get_ssh_kw(self._settings, self._state),
        )
