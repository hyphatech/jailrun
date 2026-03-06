from pathlib import Path

import typer

from jailrun.ansible import run_playbook
from jailrun.config import load_state, parse_config
from jailrun.qemu import vm_is_running
from jailrun.schemas import JailPlan, Plan
from jailrun.settings import Settings
from jailrun.ssh import get_ssh_kw, wait_for_ssh
from jailrun.ui import err, ok, warn


def pause(config: Path, *, settings: Settings, names: list[str] | None = None) -> None:
    cfg = parse_config(config)
    targets = set(names) if names else set(cfg.jail.keys())

    unknown = targets - set(cfg.jail.keys())
    if unknown:
        warn(f"Not in config: {', '.join(sorted(unknown))}")

    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Run 'jrun start' first.")
        raise typer.Exit(1)

    state = load_state(settings.state_file)

    to_stop: list[str] = []
    for name in sorted(targets):
        if name in state.jails:
            to_stop.append(name)
        else:
            warn(f"Jail '{name}' not in state — skipping.")

    if not to_stop:
        warn("No matching jails found in state.")
        return

    ssh_kw = get_ssh_kw(settings)
    wait_for_ssh(**ssh_kw, silent=True)

    stop_plan = Plan(
        jails=[
            JailPlan(
                name=name,
                release=state.jails[name].release,
                ip=state.jails[name].ip,
            )
            for name in to_stop
        ],
    )

    run_playbook("jail-stop.yml", plan=stop_plan, settings=settings)

    ok(f"Paused: {', '.join(to_stop)}.")
