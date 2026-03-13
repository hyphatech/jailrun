from pathlib import Path

import typer

from jailrun.ansible import run_playbook
from jailrun.cmd.stop import stop_vm
from jailrun.config import (
    derive_plan,
    load_base_into_state,
    needs_qemu_restart,
    parse_config,
    resolve_jail,
    resolve_jail_dependencies,
    save_state,
    snapshot_qemu_wiring,
    sort_jails,
)
from jailrun.misc import lock
from jailrun.network import get_ssh_kw, resolve_jail_ips, resolve_ssh_port, wait_for_ssh
from jailrun.qemu import QemuMode, launch_vm, vm_is_running
from jailrun.remote import fetch_remote_playbook
from jailrun.schemas import JailPlan, LocalSetupStep, Plan, RemoteSetupStep, State
from jailrun.settings import Settings
from jailrun.ui import err, info, ok, warn


def up(
    config: Path,
    state: State,
    settings: Settings,
    *,
    base_config: Path | None,
    mode: QemuMode = QemuMode.SERVER,
    names: list[str] | None = None,
) -> None:
    with lock(settings.state_file):
        _up(
            config=config,
            state=state,
            settings=settings,
            base_config=base_config,
            mode=mode,
            names=names,
        )


def _up(
    config: Path,
    state: State,
    settings: Settings,
    *,
    base_config: Path | None,
    mode: QemuMode = QemuMode.SERVER,
    names: list[str] | None = None,
) -> None:
    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Run 'jrun start' first.")
        raise typer.Exit(1)

    cfg = parse_config(config)

    if not cfg.jail:
        warn("No jails defined in config.")
        raise typer.Exit(1)

    targets = set(names) if names else set(cfg.jail.keys())
    unknown = targets - set(cfg.jail.keys())

    if unknown:
        err(f"Not in config: {', '.join(sorted(unknown))}")
        raise typer.Exit(1)

    targets = resolve_jail_dependencies(targets, cfg.jail)
    ordered_jails = [n for n in sort_jails(cfg.jail) if n in targets]

    new_state = state.model_copy(deep=True)
    new_state = load_base_into_state(base_config, new_state)

    for name in ordered_jails:
        new_state.jails[name] = resolve_jail(
            jail_config=cfg.jail[name],
            config_base=config.parent.resolve(),
            default_release=f"{settings.bsd_version}-{settings.bsd_release_tag}",
        )

    if needs_qemu_restart(old_state=state, new_state=new_state):
        warn("QEMU wiring changed — restarting VM…")
        stop_vm(settings)

        resolve_ssh_port(state=new_state, settings=settings)
        launch_vm(state=new_state, mode=QemuMode.SERVER, settings=settings)
        snapshot_qemu_wiring(state=new_state)
        save_state(state=new_state, state_file=settings.state_file)

    ssh_kw = get_ssh_kw(settings, new_state)
    wait_for_ssh(**ssh_kw)

    try:
        resolve_jail_ips(old_state=state, new_state=new_state, **ssh_kw)
    finally:
        save_state(state=new_state, state_file=settings.state_file)

    plan = derive_plan(state, new_state)

    run_playbook("jail-teardown.yml", plan=plan, settings=settings, state=new_state)

    run_playbook("vm-mounts.yml", plan=plan, settings=settings, state=new_state)

    run_playbook("vm-dns-bootstrap.yml", plan=plan, settings=settings, state=new_state)

    provisioned_jails: list[JailPlan] = [
        JailPlan(name=n, release=j.release, ip=j.ip, base=j.base)
        for n, j in new_state.jails.items()
        if n not in targets
    ]
    provisioned_names = {j.name for j in provisioned_jails}

    for name in ordered_jails:
        jail_state = new_state.jails[name]
        jail_cfg = cfg.jail[name]

        jail_plan = JailPlan(
            name=name,
            release=jail_state.release,
            ip=jail_state.ip,
            base=jail_state.base,
        )
        provision_plan = Plan(
            jails=[jail_plan],
            jail_mounts=[m for m in plan.jail_mounts if m.jail == name],
            jail_rdrs=[r for r in plan.jail_rdrs if r.jail == name],
            execs=[e for e in plan.execs if e.jail == name],
        )

        run_playbook("jail-create.yml", plan=provision_plan, settings=settings, state=new_state)

        run_playbook("jail-mounts.yml", plan=provision_plan, settings=settings, state=new_state)

        run_playbook("jail-start.yml", plan=provision_plan, settings=settings, state=new_state)

        save_state(state=new_state, state_file=settings.state_file)

        provisioned_jails.append(jail_plan)
        provisioned_names.add(jail_plan.name)

        cumulative_plan = Plan(
            jails=list(provisioned_jails),
            jail_rdrs=[r for r in plan.jail_rdrs if r.jail in provisioned_names],
        )

        run_playbook("jail-dns.yml", plan=cumulative_plan, settings=settings, state=new_state)

        run_playbook("jail-forwards.yml", plan=cumulative_plan, settings=settings, state=new_state)

        for step in jail_cfg.setup.values():
            if step.type == "ansible":
                if isinstance(step, RemoteSetupStep):
                    playbook_path = fetch_remote_playbook(
                        step.url,
                        cache_dir=settings.playbook_cache_dir,
                    )
                    run_playbook(
                        str(playbook_path),
                        jail_name=name,
                        jail_ip=jail_cfg.ip or jail_state.ip,
                        extra_vars=step.vars or None,
                        settings=settings,
                        state=new_state,
                    )
                if isinstance(step, LocalSetupStep):
                    run_playbook(
                        step.file,
                        jail_name=name,
                        jail_ip=jail_cfg.ip or jail_state.ip,
                        extra_vars=step.vars or None,
                        settings=settings,
                        state=new_state,
                    )

        if settings.mesh_network:
            run_playbook("jail-yggdrasil.yml", plan=provision_plan, settings=settings, state=new_state)

        if provision_plan.execs:
            run_playbook("jail-monit.yml", plan=provision_plan, settings=settings, state=new_state)

    ok(f"Deploy complete ({', '.join(ordered_jails)}).")

    if mode in {QemuMode.TTY, QemuMode.GRAPHIC}:
        info(f"Restarting VM in {mode} mode…")
        stop_vm(settings)
        launch_vm(state=new_state, mode=mode, settings=settings)
