import contextlib
import os
import signal
import time

import typer

from jailrun.qemu import vm_is_running
from jailrun.settings import Settings


def stop_vm(settings: Settings) -> None:
    alive, pid = vm_is_running(settings.pid_file)

    if not alive or not pid:
        typer.secho("VM is not running.", fg=typer.colors.YELLOW)
        return

    typer.secho(f"Stopping VM (pid {pid})...", fg=typer.colors.YELLOW)

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        typer.secho("VM already exited.", fg=typer.colors.YELLOW)
        settings.pid_file.unlink(missing_ok=True)
        return
    except PermissionError as exc:
        typer.secho("Permission denied.", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        for _ in range(30):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.5)
        else:
            typer.echo("⚡️ VM didn't stop gracefully, sending SIGKILL...")
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)

    settings.pid_file.unlink(missing_ok=True)
    typer.secho("VM stopped.", fg=typer.colors.GREEN)
