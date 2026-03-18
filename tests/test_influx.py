from collections.abc import Generator
from typing import cast

import pytest
from influxdb import InfluxDBClient
from influxdb.resultset import ResultSet

from jailrun import ROOT_DIR
from jailrun.settings import Settings
from jailrun.testing.influx import InfluxJail

pytestmark = pytest.mark.freebsd_vm


@pytest.fixture
def influx_client(settings: Settings) -> Generator[InfluxDBClient]:
    with InfluxJail("hypha-influxdb-test", jail_config=ROOT_DIR / "tests" / "influxdb.ucl") as jail:
        client = InfluxDBClient(host=settings.vm_host, port=jail.port)
        client.switch_database("test")
        yield client


def test_write_and_query(influx_client: InfluxDBClient) -> None:
    influx_client.write_points(
        [
            {
                "measurement": "users",
                "tags": {"name": "alice"},
                "fields": {"value": 1},
            }
        ]
    )

    result = cast(ResultSet, influx_client.query('SELECT value FROM "users"'))
    [result] = list(result.get_points())

    assert result["value"] == 1


def test_empty_after_cleanup(influx_client: InfluxDBClient) -> None:
    result = cast(ResultSet, influx_client.query('SELECT * FROM "users"'))
    assert list(result.get_points()) == []
