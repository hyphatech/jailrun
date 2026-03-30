from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import typer

from jailrun.ansible import run_playbook
from jailrun.cmd.stop import stop_vm
from jailrun.config import (
    derive_plan,
    derive_qemu_fwds,
    derive_qemu_shares,
    diff_jail,
    needs_qemu_restart,
    parse_config,
    resolve_jail,
    resolve_jail_dependencies,
    save_state,
)
from jailrun.misc import lock
from jailrun.network import get_ssh_kw, resolve_jail_ips, resolve_ssh_port, wait_for_ssh
from jailrun.qemu import QemuMode, launch_vm, vm_is_running
from jailrun.remote import fetch_remote_playbook
from jailrun.schemas import ALL_FLAGS, Capability, ChangeFlag, JailConfig, LocalSetupStep, RemoteSetupStep, State
from jailrun.settings import Settings
from jailrun.ui import err, info, ok, warn


@dataclass(frozen=True)
class PlaybookRule:
    playbook: str
    plan: Literal["single", "cumulative"]
    triggers: frozenset[ChangeFlag] = field(default_factory=frozenset)
    requires: frozenset[Capability] = field(default_factory=frozenset)


JAIL_RULES: tuple[PlaybookRule, ...] = (
    PlaybookRule(playbook="jail-create.yml", plan="single", triggers=frozenset({ChangeFlag.CREATE})),
    PlaybookRule(playbook="jail-mounts.yml", plan="single", triggers=frozenset({ChangeFlag.MOUNTS})),
    PlaybookRule(playbook="jail-start.yml", plan="single", triggers=frozenset({ChangeFlag.EXECS})),
    PlaybookRule(
        playbook="jail-dns.yml",
        plan="cumulative",
        triggers=frozenset({ChangeFlag.FORWARDS}),
    ),
    PlaybookRule(playbook="jail-forwards.yml", plan="cumulative", triggers=frozenset({ChangeFlag.FORWARDS})),
    PlaybookRule(
        playbook="jail-yggdrasil.yml",
        plan="single",
        triggers=frozenset({ChangeFlag.CREATE}),
        requires=frozenset({Capability.MESH}),
    ),
    PlaybookRule(
        playbook="jail-pf.yml",
        plan="single",
        triggers=frozenset({ChangeFlag.CREATE}),
        requires=frozenset({Capability.MESH}),
    ),
    PlaybookRule(
        playbook="jail-monit.yml",
        plan="single",
        triggers=frozenset({ChangeFlag.EXECS}),
        requires=frozenset({Capability.EXECS}),
    ),
)


def should_run(rule: PlaybookRule, *, flags: set[ChangeFlag], capabilities: set[Capability]) -> bool:
    if not (rule.triggers & flags):
        return False

    return rule.requires <= capabilities


def run_provisioning(
    jail_cfg: JailConfig,
    jail_name: str,
    jail_ip: str | None,
    settings: Settings,
    state: State,
) -> None:
    for step in jail_cfg.setup.values():
        if step.type != "ansible":
            continue

        if isinstance(step, RemoteSetupStep):
            playbook_path = fetch_remote_playbook(
                step.url,
                cache_dir=settings.playbook_cache_dir,
            )
            run_playbook(
                str(playbook_path),
                jail_name=jail_name,
                jail_ip=jail_ip,
                extra_vars=step.vars or None,
                settings=settings,
                state=state,
            )
        elif isinstance(step, LocalSetupStep):
            run_playbook(
                step.file,
                jail_name=jail_name,
                jail_ip=jail_ip,
                extra_vars=step.vars or None,
                settings=settings,
                state=state,
            )


def up(
    config: Path,
    state: State,
    settings: Settings,
    *,
    names: list[str] | None = None,
    provision: bool = False,
) -> None:
    with lock(settings.state_file):
        _up(
            config=config,
            state=state,
            settings=settings,
            names=names,
            provision=provision,
        )


def _up(
    config: Path,
    state: State,
    settings: Settings,
    *,
    names: list[str] | None = None,
    provision: bool = False,
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

    new_state = state.model_copy(deep=True)

    ordered_jails = resolve_jail_dependencies(targets, cfg.jail)

    for name in ordered_jails:
        new_state.jails[name] = resolve_jail(
            jail_config=cfg.jail[name],
            config_base=config.parent.resolve(),
            default_release=f"{settings.bsd_version}-{settings.bsd_release_tag}",
        )

    if needs_qemu_restart(old_state=state, new_state=new_state):
        warn("QEMU wiring changed — restarting VM…")
        stop_vm(settings)

        new_state.ssh_port = resolve_ssh_port(state=new_state, settings=settings)
        new_state.launched_fwds = derive_qemu_fwds(new_state)
        new_state.launched_shares = derive_qemu_shares(new_state)

        launch_vm(state=new_state, mode=QemuMode.SERVER, settings=settings)
        save_state(state=new_state, state_file=settings.state_file)

    ssh_kw = get_ssh_kw(settings, new_state)
    wait_for_ssh(ssh_kw)

    resolve_jail_ips(old_state=state, new_state=new_state, ssh_kw=ssh_kw)
    save_state(state=new_state, state_file=settings.state_file)

    plan = derive_plan(state, new_state)

    run_playbook("jail-stale.yml", plan=plan, settings=settings, state=new_state)
    run_playbook("vm-mounts.yml", plan=plan, settings=settings, state=new_state)

    peers_data = [p.model_dump() for p in new_state.peers]

    provisioned_names = {n for n in new_state.jails if n not in targets}

    deployed: list[str] = []

    for name in ordered_jails:
        jail_state = new_state.jails[name]
        jail_cfg = cfg.jail[name]

        changes = set(ALL_FLAGS) if provision else diff_jail(state.jails.get(name), jail_state)

        if not changes:
            info(f"Jail '{name}' unchanged — skipping.")
            provisioned_names.add(name)
            continue

        provisioned_names.add(name)

        single_plan = plan.for_jail(name)
        cumulative_plan = plan.for_jails(provisioned_names)

        plans = {"single": single_plan, "cumulative": cumulative_plan}

        capabilities: set[Capability] = set()
        if settings.mesh_network:
            capabilities.add(Capability.MESH)
        if single_plan.execs:
            capabilities.add(Capability.EXECS)

        for rule in JAIL_RULES:
            if not should_run(rule, flags=changes, capabilities=capabilities):
                continue

            extra_vars = {}
            if Capability.MESH in rule.requires:
                extra_vars.update({"peers": peers_data})

            run_playbook(
                rule.playbook,
                plan=plans[rule.plan],
                extra_vars=extra_vars,
                settings=settings,
                state=new_state,
            )

        if ChangeFlag.SETUP in changes:
            run_provisioning(
                jail_cfg=jail_cfg,
                jail_name=name,
                jail_ip=jail_cfg.ip or jail_state.ip,
                settings=settings,
                state=new_state,
            )

        save_state(state=new_state, state_file=settings.state_file)
        deployed.append(name)

    if deployed:
        ok(f"Deploy complete ({', '.join(deployed)}).")
    else:
        ok("Nothing to deploy — all jails up to date.")
