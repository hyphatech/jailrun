from pathlib import Path
from types import TracebackType
from typing import Self

from influxdb import InfluxDBClient

from jailrun.settings import Settings
from jailrun.ssh import get_ssh_kw, jail_ssh_exec
from jailrun.testing.commons import Jail


class InfluxJail(Jail):
    def __init__(
        self,
        config: Path,
        jail: str = "hypha-influx-test",
        *,
        port: int = 9086,
        base: Path | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.port = port
        super().__init__(config, jail=jail, base=base, settings=settings)

    def is_ready(self) -> bool:
        result = jail_ssh_exec(
            "influx -execute 'SHOW DATABASES'",
            jail_ip=self._jail_ip,
            **get_ssh_kw(self._settings),
        )
        return result is not None

    def __enter__(self) -> Self:
        client = InfluxDBClient(host="127.0.0.1", port=self.port)
        client.query("DROP DATABASE test")
        client.create_database("test")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        client = InfluxDBClient(host="127.0.0.1", port=self.port)
        client.query("DROP DATABASE test")
        client.create_database("test")
