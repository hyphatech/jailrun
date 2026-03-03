import subprocess

import typer

from jailrun.qemu import vm_is_running
from jailrun.settings import Settings
from jailrun.ssh import wait_for_ssh


def ssh(settings: Settings) -> None:
    key = settings.ssh_dir / settings.ssh_key

    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        typer.secho("Run 'jrun start' first.", fg=typer.colors.RED)
        raise typer.Exit(1)

    if not key.exists():
        typer.secho("VM SSH key missing. Run 'jrun init' first.", fg=typer.colors.RED)
        raise typer.Exit(1)

    wait_for_ssh(
        private_key=settings.ssh_dir / settings.ssh_key,
        ssh_user=settings.ssh_user,
        ssh_port=settings.ssh_port,
    )

    cmd = [
        "ssh",
        "-i",
        str(key),
        "-p",
        str(settings.ssh_port),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
        f"{settings.ssh_user}@localhost",
    ]
    subprocess.run(cmd, check=False)
