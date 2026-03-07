import contextlib
import os
import signal
import time

import typer

from jailrun.misc import lock
from jailrun.qemu import vm_is_running
from jailrun.settings import Settings
from jailrun.ui import err, info, ok, warn


def stop(settings: Settings) -> None:
    with lock(settings.state_file):
        stop_vm(settings)


def stop_vm(settings: Settings) -> None:
    alive, pid = vm_is_running(settings.pid_file)

    if not alive or not pid:
        warn("VM is not running.")
        return

    info(f"Stopping VM (pid {pid})…")

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        warn("VM already exited.")
        settings.pid_file.unlink(missing_ok=True)
        return
    except PermissionError as exc:
        err("Permission denied.")
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
            warn("VM didn't stop gracefully — sending SIGKILL…")
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)

    settings.pid_file.unlink(missing_ok=True)
    ok("VM stopped.")
