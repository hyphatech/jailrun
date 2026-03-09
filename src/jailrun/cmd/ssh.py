import shlex
import subprocess

import typer

from jailrun.qemu import vm_is_running
from jailrun.schemas import State
from jailrun.settings import Settings
from jailrun.ssh import get_ssh_kw, jail_ssh_cmd, ssh_cmd, wait_for_ssh
from jailrun.ui import err


def ssh(state: State, settings: Settings, jail_name: str | None = None) -> None:
    """Open an interactive SSH session to the VM or a jail."""
    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Run 'jrun start' first.")
        raise typer.Exit(1)

    ssh_kw = get_ssh_kw(settings, state)
    wait_for_ssh(**ssh_kw)

    if jail_name:
        if jail_name not in state.jails:
            err(f"Jail '{jail_name}' not found in state.")
            raise typer.Exit(1)

        jail_ip = state.jails[jail_name].ip
        if not jail_ip:
            err(f"Jail '{jail_name}' has no IP assigned.")
            raise typer.Exit(1)

        command = jail_ssh_cmd(args=[], jail_ip=jail_ip, tty=True, **ssh_kw)
    else:
        command = ssh_cmd(args=[], tty=True, **ssh_kw)

    subprocess.run(command, check=False)


def run_cmd(state: State, settings: Settings, jail_name: str, cmd: list[str]) -> None:
    """Execute a command inside a jail over SSH."""
    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Run 'jrun start' first.")
        raise typer.Exit(1)

    ssh_kw = get_ssh_kw(settings, state)
    wait_for_ssh(**ssh_kw)

    if jail_name not in state.jails:
        err(f"Jail '{jail_name}' not found in state.")
        raise typer.Exit(1)

    jail_ip = state.jails[jail_name].ip
    if not jail_ip:
        err(f"Jail '{jail_name}' has no IP assigned.")
        raise typer.Exit(1)

    remote_cmd = [shlex.join(cmd)]
    command = jail_ssh_cmd(args=remote_cmd, jail_ip=jail_ip, tty=True, **ssh_kw)

    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        err(f"Command exited with code {result.returncode}.")
        raise typer.Exit(result.returncode)
