from jailrun.ansible import run_playbook
from jailrun.config import derive_plan, save_state
from jailrun.misc import lock
from jailrun.network import get_ssh_kw, wait_for_ssh
from jailrun.qemu import vm_is_running
from jailrun.schemas import JailPlan, Plan, State
from jailrun.settings import Settings
from jailrun.ui import err, ok, warn


def down(state: State, settings: Settings, *, names: list[str] | None = None) -> None:
    with lock(settings.state_file):
        _down(state=state, settings=settings, names=names)


def _down(state: State, *, settings: Settings, names: list[str] | None = None) -> None:
    if not names:
        warn("No jails selected.")
        return

    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Run 'jrun start' first.")
        raise SystemExit(1)

    new_state = state.model_copy(deep=True)

    requested = list(dict.fromkeys(names))
    removed: list[str] = []
    skipped: list[str] = []

    for name in requested:
        if name in new_state.jails:
            del new_state.jails[name]
            removed.append(name)
        else:
            skipped.append(name)

    for name in skipped:
        warn(f"Jail '{name}' not in state — skipping.")

    if not removed:
        warn("No matching jails found in state.")
        return

    plan = derive_plan(state, new_state)

    ssh_kw = get_ssh_kw(settings, state)
    wait_for_ssh(**ssh_kw, silent=True)

    run_playbook("jail-teardown.yml", plan=plan, settings=settings, state=new_state)
    run_playbook("vm-mounts.yml", plan=plan, settings=settings, state=new_state)
    run_playbook("jail-forwards.yml", plan=plan, settings=settings, state=new_state)

    if plan.execs:
        run_playbook("jail-monit.yml", plan=plan, settings=settings, state=new_state)

    dns_jails = [JailPlan(name=n, release=j.release, ip=j.ip, base=j.base) for n, j in new_state.jails.items() if j.ip]

    run_playbook(
        "jail-dns.yml",
        plan=Plan(jails=dns_jails),
        settings=settings,
        state=new_state,
    )

    save_state(state=new_state, state_file=settings.state_file)

    ok(f"Removed: {', '.join(removed)}.")
