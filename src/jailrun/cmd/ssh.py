import subprocess

import typer

from jailrun.config import load_state
from jailrun.qemu import vm_is_running
from jailrun.settings import Settings
from jailrun.ssh import get_ssh_kw, jail_ssh_cmd, ssh_cmd, wait_for_ssh
from jailrun.ui import err


def ssh(settings: Settings, jail_name: str | None = None, cmd: list[str] | None = None) -> None:
    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Run 'jrun start' first.")
        raise typer.Exit(1)

    ssh_kw = get_ssh_kw(settings)
    wait_for_ssh(**ssh_kw)

    if jail_name:
        state = load_state(settings.state_file)

        if jail_name not in state.jails:
            err(f"Jail '{jail_name}' not found in state.")
            raise typer.Exit(1)

        jail_ip = state.jails[jail_name].ip
        if not jail_ip:
            err(f"Jail '{jail_name}' has no IP assigned.")
            raise typer.Exit(1)

        command = jail_ssh_cmd(args=cmd or [], jail_ip=jail_ip, **ssh_kw)
    else:
        command = ssh_cmd(args=cmd or [], **ssh_kw)

    subprocess.run(command, check=False)
