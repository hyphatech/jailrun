import subprocess

import typer

from jailrun.config import load_state
from jailrun.qemu import build_qemu_cmd, prepare_disk, vm_is_running
from jailrun.settings import Settings


def console(settings: Settings) -> None:
    alive, _ = vm_is_running(settings.pid_file)
    if alive:
        typer.secho(
            "VM already running, stop it first to attach console.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)

    prepare_disk(settings)

    state = load_state(settings.state_file)
    cmd = build_qemu_cmd(state=state, settings=settings, foreground=True)

    typer.echo("🖥️ Starting VM console")
    subprocess.run(cmd, check=False)
