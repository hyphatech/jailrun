from datetime import UTC, datetime

import questionary
import typer
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from jailrun.ansible import run_playbook
from jailrun.network import SSHKwargs, get_ssh_kw, ssh_exec, wait_for_ssh
from jailrun.qemu import vm_is_running
from jailrun.schemas import State
from jailrun.settings import Settings
from jailrun.ui import Q_STYLE, con, err, nl, ok, warn


def snapshot_exists(ssh_kw: SSHKwargs, private_name: str, name: str) -> bool:
    raw = ssh_exec(
        cmd=(
            f"doas zfs list -t snapshot -H -o name "
            f"$(doas zfs list -H -o name /usr/local/bastille/jails/{private_name})@{name}"
        ),
        ssh_kw=ssh_kw,
    )
    return bool(raw and raw.strip())


def snapshot_create(
    state: State,
    settings: Settings,
    jail_name: str,
    name: str | None = None,
) -> None:
    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Run 'jrun start' first.")
        raise typer.Exit(1)

    if jail_name not in state.jails:
        err(f"Unknown jail: {jail_name}")
        raise typer.Exit(1)

    private_name = str(state.jails[jail_name].private_name)
    snap_name = name or datetime.now(tz=UTC).strftime("%Y-%m-%d_%H-%M-%S")

    ssh_kw = get_ssh_kw(settings=settings, state=state)
    wait_for_ssh(ssh_kw)

    run_playbook(
        "jail-snapshot.yml",
        extra_vars={
            "snapshot_jail": private_name,
            "snapshot_name": snap_name,
        },
        settings=settings,
        state=state,
    )
    ok(f"Snapshot '{snap_name}' created for '{jail_name}'.")


def snapshot_list(
    state: State,
    settings: Settings,
    jail_name: str,
) -> None:
    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Run 'jrun start' first.")
        raise typer.Exit(1)

    if jail_name not in state.jails:
        err(f"Unknown jail: {jail_name}")
        raise typer.Exit(1)

    private_name = str(state.jails[jail_name].private_name)

    ssh_kw = get_ssh_kw(settings=settings, state=state)
    wait_for_ssh(ssh_kw)

    raw = ssh_exec(
        cmd=(
            f"doas zfs list -t snapshot -H -o name,used,creation "
            f"$(doas zfs list -H -o name /usr/local/bastille/jails/{private_name})"
        ),
        ssh_kw=ssh_kw,
    )

    c = con()

    if not raw or not raw.strip():
        c.print("  [dim]no snapshots[/dim]\n")
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
    tbl.add_column("used", style="dim white", no_wrap=True)
    tbl.add_column("created", style="dim white", no_wrap=True)

    for line in raw.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue

        full_name = parts[0]
        snap_name = full_name.split("@")[-1] if "@" in full_name else full_name
        used = parts[1]
        created = parts[2]

        tbl.add_row(
            Text(snap_name, style="bold"),
            used,
            created,
        )

    c.print(Padding(tbl, pad=(0, 0, 0, 2)))
    nl()


def snapshot_rollback(
    state: State,
    settings: Settings,
    jail_name: str,
    name: str,
) -> None:
    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Run 'jrun start' first.")
        raise typer.Exit(1)

    if jail_name not in state.jails:
        err(f"Unknown jail: {jail_name}")
        raise typer.Exit(1)

    private_name = str(state.jails[jail_name].private_name)

    ssh_kw = get_ssh_kw(settings=settings, state=state)
    wait_for_ssh(ssh_kw)

    if not snapshot_exists(ssh_kw, private_name, name):
        err(f"Snapshot '{name}' not found for '{jail_name}'.")
        raise typer.Exit(1)

    answer = questionary.confirm(
        f"Rollback '{jail_name}' to '{name}'? This will stop the jail and destroy newer snapshots.",
        default=False,
        style=Q_STYLE,
    ).ask()

    nl()

    if not answer:
        warn("Aborted.")
        raise typer.Exit(0)

    run_playbook(
        "jail-snapshot-rollback.yml",
        extra_vars={
            "snapshot_jail": private_name,
            "snapshot_name": name,
        },
        settings=settings,
        state=state,
    )
    ok(f"Rolled back '{jail_name}' to '{name}'.")


def snapshot_delete(
    state: State,
    settings: Settings,
    jail_name: str,
    name: str,
) -> None:
    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Run 'jrun start' first.")
        raise typer.Exit(1)

    if jail_name not in state.jails:
        err(f"Unknown jail: {jail_name}")
        raise typer.Exit(1)

    private_name = str(state.jails[jail_name].private_name)

    ssh_kw = get_ssh_kw(settings=settings, state=state)
    wait_for_ssh(ssh_kw)

    if not snapshot_exists(ssh_kw, private_name, name):
        err(f"Snapshot '{name}' not found for '{jail_name}'.")
        raise typer.Exit(1)

    answer = questionary.confirm(
        f"Delete snapshot '{name}' for '{jail_name}'?",
        default=False,
        style=Q_STYLE,
    ).ask()

    nl()

    if not answer:
        warn("Aborted.")
        raise typer.Exit(0)

    run_playbook(
        "jail-snapshot-delete.yml",
        extra_vars={
            "snapshot_jail": private_name,
            "snapshot_name": name,
        },
        settings=settings,
        state=state,
    )
    ok(f"Deleted snapshot '{name}' from '{jail_name}'.")
