import contextlib
import json
from pathlib import Path
from typing import NotRequired, TypedDict

import typer
from rich import print as rprint
from rich.table import Table
from rich.tree import Tree

from jailrun.config import load_state
from jailrun.qemu import vm_is_running
from jailrun.serializers import loads
from jailrun.settings import Settings
from jailrun.ssh import ssh_exec, wait_for_ssh


class SSHKwargs(TypedDict):
    private_key: Path
    ssh_user: str
    ssh_port: int


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
    uptime: str | None
    disk_free: str | None
    disk_total: str | None
    mem_total: float | None
    mem_usable: float | None
    jail_rows: list[JailRow]


def short_path(p: str) -> str:
    parts = Path(p).parts
    if len(parts) > 2:
        return "…/" + str(Path(*parts[-2:]))
    return p


def collect_info(settings: Settings) -> StatusInfo:
    alive, pid = vm_is_running(settings.pid_file)

    if not alive:
        typer.secho("VM is not running. Run 'jrun start' first.", fg=typer.colors.YELLOW)
        raise typer.Exit(0)

    if pid is None:
        raise RuntimeError("VM reported running but PID is missing")

    state = load_state(settings.state_file)

    private_key: Path = Path(settings.ssh_dir) / str(settings.ssh_key)
    ssh_user: str = str(settings.ssh_user)
    ssh_port: int = int(settings.ssh_port)

    ssh_kw: SSHKwargs = {
        "private_key": private_key,
        "ssh_user": ssh_user,
        "ssh_port": ssh_port,
    }

    wait_for_ssh(**ssh_kw, silent=True)

    uptime = ssh_exec(cmd="uptime", **ssh_kw)

    disk_free: str | None = None
    disk_total: str | None = None
    disk = ssh_exec(cmd="df -h /", **ssh_kw)
    if disk:
        parts = disk.splitlines()[-1].split()
        if len(parts) >= 4:
            disk_free, disk_total = parts[3], parts[1]

    mem_total: float | None = None
    mem_usable: float | None = None
    mem = ssh_exec(cmd="sysctl -n hw.physmem hw.usermem", **ssh_kw)
    if mem:
        lines = mem.splitlines()
        if len(lines) == 2:
            mem_total = int(lines[0]) / (1024**3)
            mem_usable = int(lines[1]) / (1024**3)

    raw = ssh_exec(cmd="bastille list -j", **ssh_kw)
    bastille_jails: list[dict[str, str]] = []
    if raw and raw != "[]":
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            bastille_jails = loads(raw)

    managed_names = set(state.jails.keys())
    bastille_names = {j.get("Name") for j in bastille_jails}

    jail_rows: list[JailRow] = []
    for j in sorted(bastille_jails, key=lambda x: x.get("Name", "")):
        name = j.get("Name", "?")
        st = j.get("State", "?")
        ip = j.get("IP Address", "-")
        managed = name in managed_names

        if managed:
            jail_state = state.jails[name]
            ports = ", ".join(f"{f.proto}/{f.host}→{f.jail}" for f in jail_state.forwards.values())
            mounts = ", ".join(f"{short_path(m.host)} → {m.jail}" for m in jail_state.mounts.values())
        else:
            ports = ""
            mounts = ""

        jail_rows.append(
            JailRow(
                name=name,
                state=st,
                ip=ip,
                managed=managed,
                ports=ports,
                mounts=mounts,
            )
        )

    for name in sorted(managed_names - bastille_names):
        jail = state.jails[name]
        ports = ", ".join(f"{f.proto}/{f.host}→{f.jail}" for f in jail.forwards.values())
        mounts = ", ".join(f"{short_path(m.host)} → {m.jail}" for m in jail.mounts.values())
        jail_rows.append(
            JailRow(
                name=name,
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
        uptime=uptime,
        disk_free=disk_free,
        disk_total=disk_total,
        mem_total=mem_total,
        mem_usable=mem_usable,
        jail_rows=jail_rows,
    )


def render_table(data: StatusInfo) -> None:
    vm_table = Table(show_header=False, box=None, padding=(0, 2))
    vm_table.add_column(style="bold")
    vm_table.add_column()

    vm_table.add_row("VM", f"[green]running[/green] (pid {data['pid']})")
    if data["uptime"]:
        vm_table.add_row("Uptime", data["uptime"].strip())
    if data["disk_free"]:
        vm_table.add_row("Disk", f"{data['disk_free']} free of {data['disk_total']}")
    if data["mem_total"] is not None and data["mem_usable"] is not None:
        vm_table.add_row("Memory", f"{data['mem_total']:.1f}G total, {data['mem_usable']:.1f}G usable")

    rprint(vm_table)
    rprint()

    jail_table = Table(expand=False)
    jail_table.add_column("Name", style="bold")
    jail_table.add_column("State")
    jail_table.add_column("IP")
    jail_table.add_column("Ports")
    jail_table.add_column("Mounts")

    for j in data["jail_rows"]:
        name = j["name"]
        st = j["state"]
        ip = j["ip"]

        if j.get("stale"):
            name_label = f"{name} [yellow](stale state)[/yellow]"
            state_label = "[yellow]Missing[/yellow]"
        elif not j["managed"]:
            name_label = f"{name} [dim](unmanaged)[/dim]"
            state_style = "green" if st == "Up" else "red"
            state_label = f"[{state_style}]{st}[/{state_style}]"
        else:
            name_label = name
            state_style = "green" if st == "Up" else "red"
            state_label = f"[{state_style}]{st}[/{state_style}]"

        jail_table.add_row(
            name_label,
            state_label,
            ip,
            j["ports"] or "[dim]n/a[/dim]",
            j["mounts"] or "[dim]n/a[/dim]",
        )

    if jail_table.row_count == 0:
        typer.echo("No jails.")
    else:
        rprint(jail_table)


def render_tree(data: StatusInfo) -> None:
    root = Tree(f"[bold]VM[/bold]  [green]running[/green] (pid {data['pid']})")

    if data["uptime"]:
        root.add(f"[dim]Uptime[/dim]  {data['uptime'].strip()}")
    if data["disk_free"]:
        root.add(f"[dim]Disk[/dim]    {data['disk_free']} free of {data['disk_total']}")
    if data["mem_total"] is not None and data["mem_usable"] is not None:
        root.add(f"[dim]Memory[/dim]  {data['mem_total']:.1f}G total, {data['mem_usable']:.1f}G usable")

    jails_branch = root.add("[bold]Jails[/bold]")

    for j in data["jail_rows"]:
        name = j["name"]
        st = j["state"]
        ip = j["ip"]

        if j.get("stale"):
            label = f"[bold]{name}[/bold] [yellow](stale state)[/yellow]  [yellow]Missing[/yellow]  {ip}"
        elif not j["managed"]:
            state_style = "green" if st == "Up" else "red"
            label = f"[bold]{name}[/bold] [dim](unmanaged)[/dim]  [{state_style}]{st}[/{state_style}]  {ip}"
        else:
            state_style = "green" if st == "Up" else "red"
            label = f"[bold]{name}[/bold]  [{state_style}]{st}[/{state_style}]  {ip}"

        jail_node = jails_branch.add(label)
        jail_node.add(f"[dim]Ports[/dim]   {j['ports'] or '[dim]n/a[/dim]'}")
        jail_node.add(f"[dim]Mounts[/dim]  {j['mounts'] or '[dim]n/a[/dim]'}")

    if not data["jail_rows"]:
        jails_branch.add("[dim]No jails[/dim]")

    rprint(root)


def status(settings: Settings, tree: bool = False) -> None:
    data = collect_info(settings)
    if tree:
        render_tree(data)
    else:
        render_table(data)
