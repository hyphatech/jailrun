import contextlib
import json
import re
from pathlib import Path, PurePosixPath

from jailrun.cmd.status.monit import parse_monit_status
from jailrun.cmd.status.types import (
    DiskStats,
    JailRow,
    MemStats,
    MonitJailStatus,
    RawJail,
    StatusInfo,
)
from jailrun.network import SSHKwargs, get_ssh_kw, jail_ssh_exec, ssh_exec, wait_for_ssh
from jailrun.schemas import State
from jailrun.serializers import loads
from jailrun.settings import Settings

RE_IPV4 = re.compile(r"^\s+inet (\d+\.\d+\.\d+\.\d+)", re.MULTILINE)
RE_IPV6 = re.compile(r"^\s+inet6 ([0-9a-f:]+)", re.MULTILINE)
SKIP_V4 = {"127.0.0.1"}
SKIP_V6_PREFIX = ("::1", "fe80:")


def short_path(p: str) -> str:
    parts = Path(p).parts
    if len(parts) > 2:
        return "…/" + str(Path(*parts[-2:]))
    return p


def get_jail_ips(name: str, ssh_kw: SSHKwargs) -> tuple[list[str], list[str]]:
    ipv4 = ipv6 = []
    raw = ssh_exec(cmd=f"jexec {name} ifconfig", ssh_kw=ssh_kw)
    if raw:
        ipv4 = [m for m in RE_IPV4.findall(raw) if m not in SKIP_V4]
        ipv6 = [m for m in RE_IPV6.findall(raw) if not m.startswith(SKIP_V6_PREFIX)]

    return ipv4, ipv6


def get_raw_jails(ssh_kw: SSHKwargs, *, state: State) -> list[RawJail]:
    running: set[str] = set()
    raw = ssh_exec(cmd="jls -N --libxo json", ssh_kw=ssh_kw)
    with contextlib.suppress(json.JSONDecodeError, TypeError):
        for j in loads(raw).get("jail-information", {}).get("jail", []):
            running.add(j["name"])

    datasets = ssh_exec(
        cmd="zfs list -H -o name -d 1 zroot/jailrun/jails",
        ssh_kw=ssh_kw,
    )

    if not datasets:
        return []

    state_by_private = {str(j.private_name): j for j in state.jails.values()}
    names = [PurePosixPath(line).name for line in datasets.strip().splitlines()]
    results: list[RawJail] = []

    for name in names:
        if name == "jails":
            continue

        is_up = name in running

        if is_up:
            ipv4, ipv6 = get_jail_ips(name, ssh_kw)
        else:
            ipv4 = [state_by_private[name].ip or "-" if name in state_by_private else "-"]
            ipv6 = ["-"]

        results.append(RawJail(private_name=name, state="Up" if is_up else "Down", ipv4=ipv4, ipv6=ipv6))

    return results


def get_disk_stats(ssh_kw: SSHKwargs) -> DiskStats:
    disk_free: str | None = None
    disk_total: str | None = None
    disk = ssh_exec(cmd="df -h /", ssh_kw=ssh_kw)
    if disk:
        parts = disk.splitlines()[-1].split()
        if len(parts) >= 4:
            disk_free, disk_total = parts[3], parts[1]

    return DiskStats(disk_free=disk_free, disk_total=disk_total)


def get_mem_stats(ssh_kw: SSHKwargs) -> MemStats:
    mem_total: float | None = None
    mem_usable: float | None = None
    mem = ssh_exec(cmd="sysctl -n hw.physmem hw.usermem", ssh_kw=ssh_kw)
    if mem:
        lines = mem.splitlines()
        if len(lines) == 2:
            mem_total = int(lines[0]) / (1024**3)
            mem_usable = int(lines[1]) / (1024**3)

    return MemStats(mem_total=mem_total, mem_usable=mem_usable)


def _fetch_monit_for_jails(
    jails: list[RawJail],
    public_by_private: dict[str, str],
    ssh_kw: SSHKwargs,
) -> dict[str, MonitJailStatus]:
    monit_by_jail: dict[str, MonitJailStatus] = {}
    running_jails = [j for j in jails if j["state"].lower() == "up"]

    for jail in running_jails:
        jail_ip = " ".join(jail["ipv4"])
        if not jail_ip:
            continue

        raw = jail_ssh_exec(cmd="monit status 2>/dev/null", jail_ip=jail_ip, ssh_kw=ssh_kw, timeout=10)
        if not raw:
            continue

        parsed = parse_monit_status(raw)
        private_name = jail["private_name"]
        public_name = public_by_private.get(private_name, private_name)

        for monit_jail_name, monit_data in parsed.items():
            if monit_jail_name in (private_name, public_name):
                monit_by_jail[public_name] = monit_data
            else:
                entry = monit_by_jail.setdefault(
                    public_name,
                    MonitJailStatus(system_ok=None, services=[]),
                )
                if monit_data["system_ok"] is not None:
                    entry["system_ok"] = monit_data["system_ok"]

                entry["services"].extend(monit_data["services"])

    return monit_by_jail


def collect_info(settings: Settings, state: State, pid: int) -> StatusInfo:
    ssh_kw = get_ssh_kw(settings, state)

    wait_for_ssh(ssh_kw=ssh_kw, silent=True)
    uptime = ssh_exec(cmd="uptime", ssh_kw=ssh_kw)
    disk_stats = get_disk_stats(ssh_kw)
    mem_stats = get_mem_stats(ssh_kw)
    raw_jails = get_raw_jails(ssh_kw, state=state)

    managed_names = set(state.jails.keys())
    public_by_private = {str(j.private_name): name for name, j in state.jails.items()}
    private_by_public = {name: str(j.private_name) for name, j in state.jails.items()}

    monit_by_jail = _fetch_monit_for_jails(raw_jails, public_by_private, ssh_kw)

    jail_rows: list[JailRow] = []
    for j in raw_jails:
        private_name = j["private_name"]
        public_name = public_by_private.get(private_name, private_name)
        managed = private_name in public_by_private

        if managed:
            jail_state = state.jails[public_name]
            ports = [f"{f.proto}/{f.host} → {f.jail}" for f in jail_state.forwards.values()]
            mounts = [f"{short_path(m.host)} → {m.jail}" for m in jail_state.mounts.values()]
        else:
            ports = []
            mounts = []

        ipv4 = [ip for ip in j["ipv4"] if ip != "-"]
        ipv6 = [ip for ip in j["ipv6"] if ip != "-"]

        row = JailRow(
            name=public_name,
            state=j["state"],
            ips=[*ipv4, *ipv6],
            managed=managed,
            ports=ports,
            mounts=mounts,
        )
        if public_name in monit_by_jail:
            row["monit"] = monit_by_jail[public_name]

        jail_rows.append(row)

    jail_private_names = {j["private_name"] for j in raw_jails}
    for public_name in sorted(managed_names):
        private_name = private_by_public[public_name]
        if private_name in jail_private_names:
            continue

        jail = state.jails[public_name]
        ports = [f"{f.proto}/{f.host} → {f.jail}" for f in jail.forwards.values()]
        mounts = [f"{short_path(m.host)} → {m.jail}" for m in jail.mounts.values()]

        jail_rows.append(
            JailRow(
                name=public_name,
                state="Missing",
                ips=[jail.ip] if jail.ip else [],
                managed=True,
                stale=True,
                ports=ports,
                mounts=mounts,
            )
        )

    return StatusInfo(
        pid=pid,
        ssh_host=ssh_kw["ssh_host"],
        ssh_port=ssh_kw["ssh_port"],
        uptime=uptime,
        disk_free=disk_stats["disk_free"],
        disk_total=disk_stats["disk_total"],
        mem_total=mem_stats["mem_total"],
        mem_usable=mem_stats["mem_usable"],
        jail_rows=jail_rows,
    )
