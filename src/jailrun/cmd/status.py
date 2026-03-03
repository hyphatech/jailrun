import contextlib
import json
from pathlib import Path

import typer
from rich import print as rprint
from rich.table import Table

from jailrun.config import load_state
from jailrun.qemu import vm_is_running
from jailrun.serializers import loads
from jailrun.settings import Settings
from jailrun.ssh import ssh_exec, wait_for_ssh


def status(settings: Settings) -> None:
    alive, pid = vm_is_running(settings.pid_file)

    if not alive:
        typer.secho("VM is not running. Run 'jrun start' first.", fg=typer.colors.YELLOW)
        raise typer.Exit(0)

    state = load_state(settings.state_file)

    wait_for_ssh(
        private_key=settings.ssh_dir / settings.ssh_key,
        ssh_user=settings.ssh_user,
        ssh_port=settings.ssh_port,
        silent=True,
    )

    vm_table = Table(show_header=False, box=None, padding=(0, 2))
    vm_table.add_column(style="bold")
    vm_table.add_column()

    vm_table.add_row("VM", f"[green]running[/green] (pid {pid})")

    uptime = ssh_exec(
        cmd="uptime",
        private_key=settings.ssh_dir / settings.ssh_key,
        ssh_user=settings.ssh_user,
        ssh_port=settings.ssh_port,
    )
    if uptime:
        vm_table.add_row("Uptime", uptime.strip())

    disk = ssh_exec(
        cmd="df -h /",
        private_key=settings.ssh_dir / settings.ssh_key,
        ssh_user=settings.ssh_user,
        ssh_port=settings.ssh_port,
    )
    if disk:
        parts = disk.splitlines()[-1].split()
        if len(parts) >= 4:
            vm_table.add_row("Disk", f"{parts[3]} free of {parts[1]}")

    mem = ssh_exec(
        cmd="sysctl -n hw.physmem hw.usermem",
        private_key=settings.ssh_dir / settings.ssh_key,
        ssh_user=settings.ssh_user,
        ssh_port=settings.ssh_port,
    )
    if mem:
        lines = mem.splitlines()
        if len(lines) == 2:
            total = int(lines[0]) / (1024**3)
            usable = int(lines[1]) / (1024**3)
            vm_table.add_row("Memory", f"{total:.1f}G total, {usable:.1f}G usable")

    rprint(vm_table)
    rprint()

    raw = ssh_exec(
        cmd="bastille list -j",
        private_key=settings.ssh_dir / settings.ssh_key,
        ssh_user=settings.ssh_user,
        ssh_port=settings.ssh_port,
    )
    bastille_jails: list[dict[str, str]] = []
    if raw and raw != "[]":
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            bastille_jails = loads(raw)

    managed_names = set(state.jails.keys())
    bastille_names = {j.get("Name") for j in bastille_jails}

    jail_table = Table(expand=False)
    jail_table.add_column("Name", style="bold")
    jail_table.add_column("State")
    jail_table.add_column("IP")
    jail_table.add_column("Ports")
    jail_table.add_column("Mounts")

    def _short_path(p: str) -> str:
        parts = Path(p).parts
        if len(parts) > 2:
            return "…/" + str(Path(*parts[-2:]))
        return p

    for j in sorted(bastille_jails, key=lambda x: x.get("Name", "")):
        name = j.get("Name", "?")
        st = j.get("State", "?")
        ip = j.get("IP Address", "-")
        managed = name in managed_names

        state_style = "green" if st == "Up" else "red"

        ports = ""
        mounts = ""
        if managed:
            jail_state = state.jails[name]
            ports = "\n".join(f"{f.proto}/{f.host}→{f.jail}" for f in jail_state.forwards.values())
            mounts = "\n".join(f"{_short_path(m.host)} → {m.jail}" for m in jail_state.mounts.values())
        else:
            name = f"{name} [dim](unmanaged)[/dim]"

        jail_table.add_row(
            name,
            f"[{state_style}]{st}[/{state_style}]",
            ip,
            ports,
            mounts,
        )

    for name in sorted(managed_names - bastille_names):
        jail = state.jails[name]
        ports = "\n".join(f"{f.proto}/{f.host}→{f.jail}" for f in jail.forwards.values())
        mounts = "\n".join(f"{m.host} → {m.jail}" for m in jail.mounts.values())
        jail_table.add_row(
            f"{name} [yellow](stale state)[/yellow]",
            "[yellow]Missing[/yellow]",
            jail.ip or "-",
            ports,
            mounts,
        )

    if jail_table.row_count == 0:
        typer.echo("No jails.")
    else:
        rprint(jail_table)
