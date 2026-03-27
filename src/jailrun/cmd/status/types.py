from typing import Literal, NotRequired, TypedDict

Scope = Literal["ip", "services"]
ALL_SCOPES: tuple[Scope, ...] = ("ip", "services")
DEFAULT_SCOPES: frozenset[Scope] = frozenset()


class RawJail(TypedDict):
    private_name: str
    state: str
    ipv4: list[str]
    ipv6: list[str]


class DiskStats(TypedDict):
    disk_free: str | None
    disk_total: str | None


class MemStats(TypedDict):
    mem_total: float | None
    mem_usable: float | None


class MonitService(TypedDict):
    name: str
    status: str
    cpu: str | None
    mem: str | None
    uptime: str | None


class MonitJailStatus(TypedDict):
    system_ok: bool | None
    services: list[MonitService]


class JailRow(TypedDict):
    name: str
    state: str
    ips: list[str]
    managed: bool
    ports: list[str]
    mounts: list[str]
    stale: NotRequired[bool]
    monit: NotRequired[MonitJailStatus]


class StatusInfo(TypedDict):
    pid: int
    ssh_host: str
    ssh_port: int
    uptime: str | None
    disk_free: str | None
    disk_total: str | None
    mem_total: float | None
    mem_usable: float | None
    jail_rows: list[JailRow]
