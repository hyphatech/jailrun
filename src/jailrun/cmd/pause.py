from jailrun.ansible import run_playbook
from jailrun.misc import lock
from jailrun.network import get_ssh_kw, wait_for_ssh
from jailrun.qemu import vm_is_running
from jailrun.schemas import JailPlan, Plan, State
from jailrun.settings import Settings
from jailrun.ui import err, ok, warn


def pause(state: State, settings: Settings, *, names: list[str] | None = None) -> None:
    with lock(settings.state_file):
        _pause(state=state, settings=settings, names=names)


def _pause(state: State, *, settings: Settings, names: list[str] | None = None) -> None:
    if not names:
        warn("No jails selected.")
        return

    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Run 'jrun start' first.")
        raise SystemExit(1)

    requested = list(dict.fromkeys(names))
    selected: list[JailPlan] = []
    skipped: list[str] = []

    for name in requested:
        jail = state.jails.get(name)
        if jail is None:
            skipped.append(name)
            continue

        selected.append(
            JailPlan(
                name=name,
                release=jail.release,
                ip=jail.ip,
                base=jail.base,
            )
        )

    for name in skipped:
        warn(f"Jail '{name}' not in state — skipping.")

    if not selected:
        warn("No matching jails found in state.")
        return

    ssh_kw = get_ssh_kw(settings, state)
    wait_for_ssh(**ssh_kw, silent=True)

    plan = Plan(jails=selected)
    run_playbook("jail-stop.yml", plan=plan, settings=settings, state=state)

    ok(f"Paused: {', '.join(j.name for j in selected)}.")
