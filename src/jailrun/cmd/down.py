from pathlib import Path

import typer

from jailrun.ansible import run_playbook
from jailrun.config import (
    derive_plan,
    load_state,
    parse_config,
    save_state,
)
from jailrun.qemu import vm_is_running
from jailrun.settings import Settings
from jailrun.ssh import get_ssh_kw, wait_for_ssh
from jailrun.ui import err, ok, warn


def down(config: Path, *, settings: Settings, names: list[str] | None = None) -> None:
    cfg = parse_config(config)
    targets = set(names) if names else set(cfg.jail.keys())

    unknown = targets - set(cfg.jail.keys())
    if unknown:
        warn(f"Not in config: {', '.join(sorted(unknown))}")

    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Run 'jrun start' first.")
        raise typer.Exit(1)

    old_state = load_state(settings.state_file)
    new_state = old_state.model_copy(deep=True)

    removed: list[str] = []
    for name in sorted(targets):
        if name in new_state.jails:
            del new_state.jails[name]
            removed.append(name)
        else:
            warn(f"Jail '{name}' not in state — skipping.")

    if not removed:
        warn("No matching jails found in state.")
        return

    plan = derive_plan(old_state, new_state)

    ssh_kw = get_ssh_kw(settings)
    wait_for_ssh(**ssh_kw, silent=True)

    run_playbook("jail-teardown.yml", plan=plan, settings=settings)
    run_playbook("vm-mounts.yml", plan=plan, settings=settings)
    run_playbook("jail-forwards.yml", plan=plan, settings=settings)

    save_state(state=new_state, state_file=settings.state_file)

    ok(f"Removed: {', '.join(removed)}.")
