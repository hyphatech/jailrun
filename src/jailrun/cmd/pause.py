from jailrun.ansible import run_playbook
from jailrun.misc import lock
from jailrun.network import get_ssh_kw, wait_for_ssh
from jailrun.qemu import vm_is_running
from jailrun.schemas import ExecPlan, JailPlan, Plan, State
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
    selected: list[str] = []
    skipped: list[str] = []

    for name in requested:
        if name in state.jails:
            selected.append(name)
        else:
            skipped.append(name)

    for name in skipped:
        warn(f"Jail '{name}' not in state — skipping.")

    if not selected:
        warn("No matching jails found in state.")
        return

    selected_jails = [
        JailPlan(
            name=name,
            release=state.jails[name].release,
            ip=state.jails[name].ip,
            base=state.jails[name].base,
        )
        for name in selected
    ]

    selected_execs = [
        ExecPlan(name=en, jail=jn, cmd=e.cmd, dir=e.dir, env=e.env, healthcheck=e.healthcheck)
        for jn, j in state.jails.items()
        if jn in selected
        for en, e in j.execs.items()
    ]

    ssh_kw = get_ssh_kw(settings, state)
    wait_for_ssh(**ssh_kw, silent=True)

    plan = Plan(jails=selected_jails, execs=selected_execs)
    run_playbook("jail-stop.yml", plan=plan, settings=settings, state=state)

    ok(f"Paused: {', '.join(selected)}.")
