from pathlib import Path

import typer

from jailrun.ansible import run_playbook
from jailrun.cmd.stop import stop_vm
from jailrun.config import (
    derive_plan,
    derive_qemu_fwds,
    derive_qemu_shares,
    parse_config,
    resolve_base,
    save_state,
)
from jailrun.misc import lock
from jailrun.network import get_ssh_kw, resolve_ssh_port, wait_for_ssh
from jailrun.qemu import QemuMode, launch_vm, prepare_disk, vm_is_running
from jailrun.remote import fetch_remote_playbook
from jailrun.schemas import BaseState, LocalSetupStep, RemoteSetupStep, State
from jailrun.settings import Settings
from jailrun.ui import err, info, warn


def start(
    base_config: Path | None,
    state: State,
    settings: Settings,
    *,
    provision: bool = False,
    mode: QemuMode = QemuMode.SERVER,
) -> None:
    with lock(settings.state_file):
        _start_vm(
            base_config=base_config,
            state=state,
            settings=settings,
            provision=provision,
            mode=mode,
        )


def _start_vm(
    base_config: Path | None,
    state: State,
    settings: Settings,
    *,
    provision: bool = False,
    mode: QemuMode = QemuMode.SERVER,
) -> None:
    alive, pid = vm_is_running(settings.pid_file)
    if alive:
        warn(f"VM is already running (pid {pid}).")
        raise typer.Exit(0)

    vars_path = settings.disk_dir / "OVMF_VARS.fd"
    if vars_path.exists():
        vars_path.unlink()

    prepare_disk(settings)

    needs_base = not settings.state_file.exists()

    new_state = state.model_copy(deep=True)

    if base_config is None and new_state.base.is_empty():
        new_state.base = BaseState()

    if base_config and not base_config.exists():
        err(f"Base config not found: {base_config}")
        raise typer.Exit(1)

    if base_config:
        parsed = parse_config(base_config)
        if parsed.base:
            info(f"Loaded base config from {base_config.name}")
            config_base = base_config.parent.resolve()
            state.base = resolve_base(parsed.base, config_base)

    new_state.ssh_port = resolve_ssh_port(state=new_state, settings=settings)
    new_state.launched_fwds = derive_qemu_fwds(new_state)
    new_state.launched_shares = derive_qemu_shares(new_state)

    launch_vm(state=new_state, mode=QemuMode.SERVER, settings=settings)
    save_state(state=new_state, state_file=settings.state_file)

    ssh_kw = get_ssh_kw(settings, new_state)
    wait_for_ssh(ssh_kw)

    if needs_base or provision:
        run_playbook("base.yml", settings=settings, state=new_state)
        run_playbook("vm-dns-bootstrap.yml", settings=settings, state=new_state)
        if settings.mesh_network:
            run_playbook(
                "vm-yggdrasil.yml",
                extra_vars={
                    "relay_peer_uri": settings.relay_peer_uri,
                    "relay_peer_port": settings.relay_peer_port,
                    "relay_pubkey": settings.relay_pubkey,
                },
                settings=settings,
                state=new_state,
            )

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
                    state=new_state,
                )
            if isinstance(step, LocalSetupStep):
                run_playbook(
                    step.file,
                    extra_vars=step.vars or None,
                    settings=settings,
                    state=new_state,
                )

    if new_state.base.mounts or new_state.base.forwards:
        plan = derive_plan(state, new_state)
        run_playbook("vm-mounts.yml", plan=plan, settings=settings, state=new_state)

    save_state(state=new_state, state_file=settings.state_file)

    if mode in {QemuMode.TTY, QemuMode.GRAPHIC}:
        info(f"Restarting VM in {mode} mode…")
        stop_vm(settings)
        launch_vm(state=new_state, mode=mode, settings=settings)
