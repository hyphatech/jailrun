import subprocess

import typer

from jailrun.config import load_state
from jailrun.qemu import vm_is_running
from jailrun.settings import Settings
from jailrun.ssh import jail_ssh_cmd, ssh_cmd, wait_for_ssh


def ssh(settings: Settings, jail_name: str | None = None) -> None:
    key = settings.ssh_dir / settings.ssh_key

    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        typer.secho("Run 'jrun start' first.", fg=typer.colors.RED)
        raise typer.Exit(1)

    if not key.exists():
        typer.secho("VM SSH key missing. Run 'jrun init' first.", fg=typer.colors.RED)
        raise typer.Exit(1)

    wait_for_ssh(
        private_key=key,
        ssh_user=settings.ssh_user,
        ssh_port=settings.ssh_port,
    )

    if jail_name:
        state = load_state(settings.state_file)

        if jail_name not in state.jails:
            typer.secho(f"Jail '{jail_name}' not found in state.", fg=typer.colors.RED)
            raise typer.Exit(1)

        jail_ip = state.jails[jail_name].ip
        if not jail_ip:
            typer.secho(f"Jail '{jail_name}' has no IP assigned.", fg=typer.colors.RED)
            raise typer.Exit(1)

        cmd = jail_ssh_cmd(
            args=[],
            jail_ip=jail_ip,
            private_key=key,
            ssh_user=settings.ssh_user,
            ssh_port=settings.ssh_port,
        )
    else:
        cmd = ssh_cmd(
            args=[],
            private_key=key,
            ssh_user=settings.ssh_user,
            ssh_port=settings.ssh_port,
        )

    subprocess.run(cmd, check=False)
