from pathlib import Path

import typer

from jailrun.ansible import run_playbook
from jailrun.cmd.stop import stop_vm
from jailrun.config import (
    derive_plan,
    load_base_into_state,
    load_state,
    save_state,
    snapshot_qemu_wiring,
)
from jailrun.qemu import QemuMode, launch_vm, prepare_disk, vm_is_running
from jailrun.remote import fetch_remote_playbook
from jailrun.schemas import LocalSetupStep, RemoteSetupStep
from jailrun.settings import Settings
from jailrun.ssh import get_ssh_kw, wait_for_ssh


def start_vm(
    base: Path | None,
    *,
    mode: QemuMode = QemuMode.SERVER,
    settings: Settings,
) -> None:
    alive, pid = vm_is_running(settings.pid_file)
    if alive:
        typer.secho(f"VM is already running (pid {pid})", fg=typer.colors.YELLOW)
        raise typer.Exit(0)

    prepare_disk(settings)

    needs_base = not settings.state_file.exists()
    old_state = load_state(settings.state_file)
    new_state = old_state.model_copy(deep=True)

    if base:
        new_state = load_base_into_state(base, new_state)

    launch_vm(state=new_state, mode=QemuMode.SERVER, settings=settings)
    snapshot_qemu_wiring(state=new_state, default_ssh_port=settings.ssh_port)
    save_state(state=new_state, state_file=settings.state_file)

    ssh_kw = get_ssh_kw(settings)
    wait_for_ssh(**ssh_kw)

    if needs_base:
        run_playbook("base.yml", settings=settings)

    for step in new_state.base.setup.values():
        if step.type == "ansible":
            if isinstance(step, RemoteSetupStep):
                playbook_path = fetch_remote_playbook(
                    step.url,
                    cache_dir=settings.playbook_cache_dir,
                )
                run_playbook(
                    str(playbook_path),
                    extra_vars=step.vars or None,
                    settings=settings,
                )
            if isinstance(step, LocalSetupStep):
                run_playbook(
                    step.file,
                    extra_vars=step.vars or None,
                    settings=settings,
                )

    if new_state.base.mounts or new_state.base.forwards:
        plan = derive_plan(old_state, new_state)
        run_playbook("vm-mounts.yml", plan=plan, settings=settings)

    save_state(state=new_state, state_file=settings.state_file)

    if mode in {QemuMode.TTY, QemuMode.GRAPHIC}:
        typer.secho(f"🖥️ Restarting VM in {mode} mode.", fg=typer.colors.YELLOW)
        stop_vm(settings)
        launch_vm(state=new_state, mode=mode, settings=settings)
