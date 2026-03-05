from pathlib import Path

import typer

from jailrun.ansible import run_playbook
from jailrun.cmd.stop import stop_vm
from jailrun.config import (
    derive_plan,
    load_base_into_state,
    load_state,
    needs_qemu_restart,
    parse_config,
    resolve_jail,
    resolve_jail_dependencies,
    save_state,
    snapshot_qemu_wiring,
    sort_jails,
)
from jailrun.qemu import QemuMode, launch_vm, vm_is_running
from jailrun.remote import fetch_remote_playbook
from jailrun.schemas import JailPlan, LocalSetupStep, Plan, RemoteSetupStep
from jailrun.settings import Settings
from jailrun.ssh import resolve_jail_ips, wait_for_ssh


def up(
    config: Path,
    *,
    base: Path | None,
    mode: QemuMode = QemuMode.SERVER,
    settings: Settings,
    names: list[str] | None = None,
) -> None:
    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        typer.secho("VM is not running. Run 'jrun start' first.", fg=typer.colors.RED)
        raise typer.Exit(1)

    cfg = parse_config(config)

    if not cfg.jail:
        typer.secho("No jails defined in config.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)

    targets = set(names) if names else set(cfg.jail.keys())
    unknown = targets - set(cfg.jail.keys())

    if unknown:
        typer.secho(
            f"Not in config: {', '.join(sorted(unknown))}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    targets = resolve_jail_dependencies(targets, cfg.jail)
    jail_order = [n for n in sort_jails(cfg.jail) if n in targets]

    old_state = load_state(settings.state_file)
    new_state = old_state.model_copy(deep=True)

    if base:
        new_state = load_base_into_state(base, new_state)

    default_release = f"{settings.bsd_version}-{settings.bsd_release_tag}"
    for name in jail_order:
        new_state.jails[name] = resolve_jail(
            jail_config=cfg.jail[name],
            config_base=config.parent.resolve(),
            default_release=default_release,
        )

    if needs_qemu_restart(old_state=old_state, new_state=new_state, default_ssh_port=settings.ssh_port):
        typer.secho("👉 QEMU wiring changed: restarting VM...", fg=typer.colors.YELLOW)

        stop_vm(settings)

        launch_vm(state=new_state, mode=QemuMode.SERVER, settings=settings)
        snapshot_qemu_wiring(state=new_state, default_ssh_port=settings.ssh_port)
        save_state(state=new_state, state_file=settings.state_file)

    wait_for_ssh(
        private_key=settings.ssh_dir / settings.ssh_key,
        ssh_user=settings.ssh_user,
        ssh_port=settings.ssh_port,
    )

    try:
        resolve_jail_ips(
            old_state=old_state,
            new_state=new_state,
            private_key=settings.ssh_dir / settings.ssh_key,
            ssh_user=settings.ssh_user,
            ssh_port=settings.ssh_port,
        )
    finally:
        save_state(state=new_state, state_file=settings.state_file)

    plan = derive_plan(old_state, new_state)

    run_playbook("jail-teardown.yml", plan=plan, settings=settings)
    run_playbook("vm-mounts.yml", plan=plan, settings=settings)

    for name in jail_order:
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

        try:
            run_playbook("jail-create.yml", plan=provision_plan, settings=settings)

            if provision_plan.jail_mounts:
                run_playbook("jail-mounts.yml", plan=provision_plan, settings=settings)

            run_playbook("jail-start.yml", plan=provision_plan, settings=settings)

        finally:
            save_state(state=new_state, state_file=settings.state_file)

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
                    )
                if isinstance(step, LocalSetupStep):
                    run_playbook(
                        step.file,
                        jail_name=name,
                        jail_ip=jail_cfg.ip or jail_state.ip,
                        extra_vars=step.vars or None,
                        settings=settings,
                    )

        if provision_plan.jail_rdrs:
            run_playbook("jail-forwards.yml", plan=provision_plan, settings=settings)

        if provision_plan.execs:
            run_playbook("jail-monit.yml", plan=provision_plan, settings=settings)

    run_playbook("jail-hosts.yml", plan=plan, settings=settings)

    deployed = ", ".join(jail_order)
    typer.secho(f"✅ Deploy complete ({deployed}).", fg=typer.colors.GREEN)

    if mode in {QemuMode.TTY, QemuMode.GRAPHIC}:
        typer.secho(f"🖥️ Restarting VM in {mode} mode.", fg=typer.colors.YELLOW)
        stop_vm(settings)
        launch_vm(state=new_state, mode=mode, settings=settings)
