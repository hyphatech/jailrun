from pathlib import Path
from types import TracebackType
from typing import Self

from influxdb import InfluxDBClient

from jailrun.network import get_ssh_kw, jail_ssh_exec
from jailrun.settings import Settings
from jailrun.testing.commons import Jail


class InfluxJail(Jail):
    def __init__(
        self,
        jail: str = "hypha-influx-test",
        *,
        jail_config: Path,
        base_config: Path | None = None,
        settings: Settings | None = None,
        port: int = 9086,
    ) -> None:
        self.port = port
        super().__init__(jail=jail, jail_config=jail_config, base_config=base_config, settings=settings)

    def is_ready(self) -> bool:
        result = jail_ssh_exec(
            "influx -execute 'SHOW DATABASES'",
            jail_ip=self._jail_ip,
            **get_ssh_kw(self._settings, self._state),
        )
        return result is not None

    def __enter__(self) -> Self:
        client = InfluxDBClient(host=self._settings.vm_host, port=self.port)
        client.drop_database("test")
        client.create_database("test")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        client = InfluxDBClient(host=self._settings.vm_host, port=self.port)
        client.drop_database("test")
        client.create_database("test")
