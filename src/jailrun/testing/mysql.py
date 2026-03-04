from pathlib import Path
from types import TracebackType
from typing import Self

from jailrun.settings import Settings
from jailrun.ssh import jail_ssh_exec
from jailrun.testing.commons import Jail


class MySQLJail(Jail):
    def __init__(
        self,
        config: Path,
        jail: str = "hypha-mysql",
        *,
        user: str = "test",
        password: str = "test",
        dbname: str = "testdb",
        port: int = 4306,
        base: Path | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.user = user
        self.password = password
        self.dbname = dbname
        self.port = port
        super().__init__(config, jail=jail, base=base, settings=settings)

    def is_ready(self) -> bool:
        result = jail_ssh_exec(
            "mysqladmin -u root ping",
            jail_ip=self._jail_ip,
            private_key=self._settings.ssh_dir / self._settings.ssh_key,
            ssh_user=self._settings.ssh_user,
            ssh_port=self._settings.ssh_port,
        )
        return result is not None

    def __enter__(self) -> Self:
        jail_ssh_exec(
            f"mysql -u root -e 'DROP DATABASE IF EXISTS `{self.dbname}`'",
            jail_ip=self._jail_ip,
            private_key=self._settings.ssh_dir / self._settings.ssh_key,
            ssh_user=self._settings.ssh_user,
            ssh_port=self._settings.ssh_port,
        )
        jail_ssh_exec(
            f"mysql -u root -e 'CREATE DATABASE `{self.dbname}`'",
            jail_ip=self._jail_ip,
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
        jail_ssh_exec(
            f"mysql -u root -e 'DROP DATABASE IF EXISTS `{self.dbname}`'",
            jail_ip=self._jail_ip,
            private_key=self._settings.ssh_dir / self._settings.ssh_key,
            ssh_user=self._settings.ssh_user,
            ssh_port=self._settings.ssh_port,
        )
