import contextlib
import json
from pathlib import Path
from typing import NotRequired, TypedDict

import typer
from rich.padding import Padding
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from jailrun.network import get_ssh_kw, ssh_exec, wait_for_ssh
from jailrun.qemu import vm_is_running
from jailrun.schemas import State
from jailrun.serializers import loads
from jailrun.settings import Settings
from jailrun.ui import con


class RawJail(TypedDict):
    private_name: str
    state: str
    ip: str


class JailRow(TypedDict):
    name: str
    state: str
    ip: str
    managed: bool
    ports: str
    mounts: str
    stale: NotRequired[bool]


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


class DiskStats(TypedDict):
    disk_free: str | None
    disk_total: str | None


class MemStats(TypedDict):
    mem_total: float | None
    mem_usable: float | None


def short_path(p: str) -> str:
    parts = Path(p).parts
    if len(parts) > 2:
        return "…/" + str(Path(*parts[-2:]))
    return p


def get_bastille_jails(private_key: Path, ssh_user: str, ssh_host: str, ssh_port: int) -> list[RawJail]:
    raw_jails: list[dict[str, str]] = []
    clean_jails: list[RawJail] = []

    bastille_list = ssh_exec(
        cmd="bastille list -j",
        private_key=private_key,
        ssh_user=ssh_user,
        ssh_host=ssh_host,
        ssh_port=ssh_port,
    )
    if not bastille_list or bastille_list == "[]":
        return []

    with contextlib.suppress(json.JSONDecodeError, TypeError):
        raw_jails = loads(bastille_list)

    for j in sorted(raw_jails, key=lambda x: x.get("Name", "")):
        clean_jails.append(
            RawJail(
                private_name=j.get("Name", "?"),
                state=j.get("State", "?"),
                ip=j.get("IP Address", "-"),
            )
        )
    return clean_jails


def get_disk_stats(private_key: Path, ssh_user: str, ssh_host: str, ssh_port: int) -> DiskStats:
    disk_free: str | None = None
    disk_total: str | None = None
    disk = ssh_exec(cmd="df -h /", private_key=private_key, ssh_user=ssh_user, ssh_host=ssh_host, ssh_port=ssh_port)
    if disk:
        parts = disk.splitlines()[-1].split()
        if len(parts) >= 4:
            disk_free, disk_total = parts[3], parts[1]

    return DiskStats(disk_free=disk_free, disk_total=disk_total)


def get_mem_stats(private_key: Path, ssh_user: str, ssh_host: str, ssh_port: int) -> MemStats:
    mem_total: float | None = None
    mem_usable: float | None = None
    mem = ssh_exec(
        cmd="sysctl -n hw.physmem hw.usermem",
        private_key=private_key,
        ssh_host=ssh_host,
        ssh_user=ssh_user,
        ssh_port=ssh_port,
    )
    if mem:
        lines = mem.splitlines()
        if len(lines) == 2:
            mem_total = int(lines[0]) / (1024**3)
            mem_usable = int(lines[1]) / (1024**3)
    return MemStats(mem_total=mem_total, mem_usable=mem_usable)


def collect_info(settings: Settings, state: State) -> StatusInfo:
    alive, pid = vm_is_running(settings.pid_file)

    if not alive:
        c = con()
        c.print()
        c.print(
            Text.assemble(
                ("● ", "bold yellow"),
                ("VM", "bold white"),
                ("  not running", "yellow"),
            )
        )
        c.print()
        c.print(Text("  Run jrun start to boot it.", style="dim white"))
        c.print()
        raise typer.Exit(0)

    if pid is None:
        raise RuntimeError("VM reported running but PID is missing")

    ssh_kw = get_ssh_kw(settings, state)

    with con().status("[dim]Connecting to VM…[/dim]", spinner="dots"):
        wait_for_ssh(**ssh_kw, silent=True)
        uptime = ssh_exec(cmd="uptime", **ssh_kw)
        disk_stats = get_disk_stats(**ssh_kw)
        mem_stats = get_mem_stats(**ssh_kw)
        bastille_jails = get_bastille_jails(**ssh_kw)

    managed_names = set(state.jails.keys())
    public_by_private = {str(j.private_name): name for name, j in state.jails.items()}
    private_by_public = {name: str(j.private_name) for name, j in state.jails.items()}

    jail_rows: list[JailRow] = []

    for j in bastille_jails:
        private_name = j["private_name"]
        public_name = public_by_private.get(private_name, private_name)
        managed = private_name in public_by_private

        if managed:
            jail_state = state.jails[public_name]
            ports = ", ".join(f"{f.proto}/{f.host}→{f.jail}" for f in jail_state.forwards.values())
            mounts = ", ".join(f"{short_path(m.host)} → {m.jail}" for m in jail_state.mounts.values())
        else:
            ports = ""
            mounts = ""

        jail_rows.append(
            JailRow(
                name=public_name,
                state=j["state"],
                ip=j["ip"],
                managed=managed,
                ports=ports,
                mounts=mounts,
            )
        )

    bastille_private_names = {j["private_name"] for j in bastille_jails}
    for public_name in sorted(managed_names):
        private_name = private_by_public[public_name]
        if private_name in bastille_private_names:
            continue

        jail = state.jails[public_name]
        ports = ", ".join(f"{f.proto}/{f.host}→{f.jail}" for f in jail.forwards.values())
        mounts = ", ".join(f"{short_path(m.host)} → {m.jail}" for m in jail.mounts.values())
        jail_rows.append(
            JailRow(
                name=public_name,
                state="Missing",
                ip=jail.ip or "-",
                managed=True,
                stale=True,
                ports=ports,
                mounts=mounts,
            )
        )

    return StatusInfo(
        pid=int(pid),
        ssh_host=ssh_kw["ssh_host"],
        ssh_port=ssh_kw["ssh_port"],
        uptime=uptime,
        disk_free=disk_stats["disk_free"],
        disk_total=disk_stats["disk_total"],
        mem_total=mem_stats["mem_total"],
        mem_usable=mem_stats["mem_usable"],
        jail_rows=jail_rows,
    )


def _jail_labels(j: JailRow) -> tuple[Text, Text]:
    name, st = j["name"], j["state"]
    if j.get("stale"):
        return (
            Text.assemble((name, "bold"), ("  stale", "yellow")),
            Text("missing", style="yellow"),
        )
    state_style = "green" if st.lower() == "up" else "red"
    if not j["managed"]:
        return (
            Text.assemble((name, "bold"), ("  unmanaged", "dim white")),
            Text(st.lower(), style=state_style),
        )
    return Text(name, style="bold"), Text(st.lower(), style=state_style)


def render_table(data: StatusInfo) -> None:
    c = con()
    c.print()

    c.print(
        Text.assemble(
            ("  ● ", "bold green"),
            ("VM", "bold white"),
            ("  running", "green"),
            (f"  on {data['ssh_host']}:{data['ssh_port']}", "dim white"),
            (f"  (pid {data['pid']})", "dim white"),
        )
    )
    c.print()

    vitals = Table.grid(padding=(0, 3, 0, 0))
    vitals.add_column(style="dim cyan", no_wrap=True, min_width=8)
    vitals.add_column()

    if data["uptime"]:
        vitals.add_row("uptime", data["uptime"].strip())
    if data["disk_free"] and data["disk_total"]:
        vitals.add_row(
            "disk",
            Text.assemble((data["disk_free"], "bold green"), (f" free of {data['disk_total']}", "dim white")),
        )
    if data["mem_total"] is not None and data["mem_usable"] is not None:
        vitals.add_row(
            "memory",
            Text.assemble(
                (f"{data['mem_usable']:.1f} GB", "bold green"),
                (f" usable / {data['mem_total']:.1f} GB total", "dim white"),
            ),
        )
    c.print(Padding(vitals, pad=(0, 0, 0, 2)))
    c.print()

    if not data["jail_rows"]:
        c.print("  [dim]no jails[/dim]")
        c.print()
        return

    tbl = Table(
        show_header=True,
        header_style="dim",
        box=None,
        show_edge=False,
        padding=(0, 3, 0, 0),
        expand=False,
        pad_edge=False,
    )
    tbl.add_column("name", no_wrap=True)
    tbl.add_column("state", no_wrap=True)
    tbl.add_column("ip", style="dim white", no_wrap=True)
    tbl.add_column("ports", style="dim white")
    tbl.add_column("mounts", style="dim white")

    for j in data["jail_rows"]:
        name_t, state_t = _jail_labels(j)
        tbl.add_row(
            name_t,
            state_t,
            j["ip"],
            j["ports"] or Text("—", style="dim white"),
            j["mounts"] or Text("—", style="dim white"),
        )

    c.print(Padding(tbl, pad=(0, 0, 0, 2)))
    c.print()


def render_tree(data: StatusInfo) -> None:
    c = con()
    c.print()

    root = Tree(
        Text.assemble(
            ("● ", "bold green"),
            ("VM", "bold white"),
            ("  running", "green"),
            (f"  on {data['ssh_host']}:{data['ssh_port']}", "dim white"),
            (f"  (pid {data['pid']})", "dim white"),
        )
    )

    if data["uptime"]:
        root.add(Text.assemble(("uptime  ", "dim cyan"), data["uptime"].strip()))
    if data["disk_free"] and data["disk_total"]:
        root.add(
            Text.assemble(
                ("disk    ", "dim cyan"),
                (data["disk_free"], "bold green"),
                (f" free of {data['disk_total']}", "dim white"),
            )
        )
    if data["mem_total"] is not None and data["mem_usable"] is not None:
        root.add(
            Text.assemble(
                ("memory  ", "dim cyan"),
                (f"{data['mem_usable']:.1f} GB", "bold green"),
                (f" usable / {data['mem_total']:.1f} GB total", "dim white"),
            )
        )

    jails_node = root.add(Text("jails", style="bold"))

    if not data["jail_rows"]:
        jails_node.add(Text("no jails", style="dim white"))
    else:
        for j in data["jail_rows"]:
            name_t, state_t = _jail_labels(j)
            label = name_t + Text("  ") + state_t + Text(f"  {j['ip']}", style="dim white")
            node = jails_node.add(label)
            node.add(Text.assemble(("ports   ", "dim cyan"), j["ports"] or Text("—", style="dim white")))
            node.add(Text.assemble(("mounts  ", "dim cyan"), j["mounts"] or Text("—", style="dim white")))

    c.print(Padding(root, pad=(0, 0, 0, 2)))
    c.print()


def status(state: State, settings: Settings, *, tree: bool = False) -> None:
    data = collect_info(state=state, settings=settings)
    if tree:
        render_tree(data)
    else:
        render_table(data)
