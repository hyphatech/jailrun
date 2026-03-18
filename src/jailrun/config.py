import hashlib
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

import typer
from pydantic import ValidationError

from jailrun import ucl
from jailrun.schemas import (
    BaseConfig,
    BaseMountConfig,
    BaseState,
    Config,
    ExecPlan,
    JailConfig,
    JailMountConfig,
    JailPlan,
    JailState,
    MountPlan,
    NullfsPlan,
    Plan,
    QemuFwd,
    QemuShare,
    RdrPlan,
    StaleJailPlan,
    StaleMountPlan,
    StaleNullfsPlan,
    State,
)
from jailrun.serializers import loads
from jailrun.ui import err


def _normalize_host_path(p: str, base: Path) -> str:
    pp = Path(p).expanduser()
    if not pp.is_absolute():
        pp = base / pp

    resolved = pp.resolve(strict=False)

    if not resolved.exists():
        err(f"Mount host path does not exist: {p} → {resolved}")
        raise typer.Exit(1)

    if resolved.is_file():
        err(f"Invalid mount path (must be a directory): {p} → {resolved}")
        raise typer.Exit(1)

    return str(pp.resolve())


def _tag(abs_host_path: str) -> str:
    return hashlib.sha256(abs_host_path.encode()).hexdigest()[:10]


def _mount_tag(abs_host_path: str) -> str:
    return f"jrun_{_tag(abs_host_path)}"


def _jail_target_path(abs_host_path: str) -> str:
    return f"/mnt/jrun/{_mount_tag(abs_host_path)}"


def _all_target_mounts(state: State) -> dict[str, MountPlan]:
    entries: dict[str, MountPlan] = {}
    for base_mnt in state.base.mounts.values():
        mt = _mount_tag(base_mnt.host)
        entries[mt] = MountPlan(mount_tag=mt, target=base_mnt.target)

    for jail in state.jails.values():
        for jmnt in jail.mounts.values():
            mt = _mount_tag(jmnt.host)
            entries[mt] = MountPlan(mount_tag=mt, target=_jail_target_path(jmnt.host))
    return entries


def _all_nullfs(state: State) -> dict[tuple[str, str], NullfsPlan]:
    entries: dict[tuple[str, str], NullfsPlan] = {}
    for name, jail in state.jails.items():
        for mnt in jail.mounts.values():
            vp = _jail_target_path(mnt.host)
            entries[(name, vp)] = NullfsPlan(jail=name, target_path=vp, jail_path=mnt.jail)
    return entries


def sort_jails(jails: dict[str, JailConfig]) -> list[str]:
    graph: dict[str, set[str]] = {}
    for name, cfg in jails.items():
        deps: set[str] = set()
        if cfg.base and cfg.base.name in jails:
            deps.add(cfg.base.name)
        for dep in cfg.depends:
            if dep in jails:
                deps.add(dep)
        graph[name] = deps

    try:
        return list(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        err(f"Dependency cycle detected: {exc}")
        raise typer.Exit(1) from exc


def parse_config(config: Path) -> Config:
    if not config.exists():
        err(f"Config not found: {config}")
        raise typer.Exit(1)

    raw = ucl.load_file(str(config))

    raw["jail"] = {name: {"name": name, **cfg} for name, cfg in raw.get("jail", {}).items()}

    try:
        cfg = Config.model_validate(raw)
    except ValidationError as exc:
        err(f"Invalid config: {exc}")
        raise typer.Exit(1) from exc

    jail_names = set(cfg.jail.keys())

    for name, jail_cfg in cfg.jail.items():
        if jail_cfg.base and jail_cfg.base.name not in jail_names:
            err(f"Jail '{name}' clones from unknown jail '{jail_cfg.base.name}'")
            raise typer.Exit(1)

        unknown_deps = [d for d in jail_cfg.depends if d not in jail_names]
        if unknown_deps:
            err(f"Jail '{name}' depends on unknown jails: {', '.join(unknown_deps)}")
            raise typer.Exit(1)

    return cfg


def resolve_base(base_config: BaseConfig, config_base: Path) -> BaseState:
    return BaseState(
        setup=base_config.setup,
        forwards=base_config.forward,
        mounts={
            name: BaseMountConfig(
                host=_normalize_host_path(mnt.host, config_base),
                target=mnt.target,
            )
            for name, mnt in base_config.mount.items()
        },
    )


def resolve_jail(jail_config: JailConfig, config_base: Path, *, default_release: str) -> JailState:
    return JailState(
        name=jail_config.name,
        base=jail_config.base,
        release=jail_config.release or default_release,
        ip=jail_config.ip,
        forwards=jail_config.forward,
        mounts={
            name: JailMountConfig(
                host=_normalize_host_path(mnt.host, config_base),
                jail=mnt.jail,
            )
            for name, mnt in jail_config.mount.items()
        },
        execs=jail_config.exec,
        setup=jail_config.setup,
    )


def resolve_jail_dependencies(names: set[str], jails: dict[str, JailConfig]) -> set[str]:
    result = set()
    queue = list(names)
    while queue:
        name = queue.pop()
        if name in result or name not in jails:
            continue

        result.add(name)
        cfg = jails[name]
        if cfg.base and cfg.base.name in jails:
            queue.append(cfg.base.name)

        for dep in cfg.depends:
            if dep in jails:
                queue.append(dep)

    return result


def resolve_jail_dependents(names: set[str], jails: dict[str, JailConfig]) -> set[str]:
    result = set()
    queue = list(names)

    while queue:
        name = queue.pop()
        if name in result:
            continue

        result.add(name)

        for other_name, cfg in jails.items():
            if other_name in result:
                continue

            is_base_dependent = cfg.base is not None and cfg.base.name == name
            is_dep_dependent = name in cfg.depends

            if is_base_dependent or is_dep_dependent:
                queue.append(other_name)

    return result


def derive_qemu_fwds(state: State) -> list[QemuFwd]:
    if state.ssh_port is None:
        raise RuntimeError("state.ssh_port is not set")

    fwds: list[QemuFwd] = []
    seen: dict[tuple[str, int], str] = {
        ("tcp", state.ssh_port): "SSH (reserved)",
    }

    for name, base_fwd in state.base.forwards.items():
        key = (base_fwd.proto, base_fwd.host)
        if key in seen:
            err(f"Port conflict: {base_fwd.proto}/{base_fwd.host} claimed by '{seen[key]}' and 'base.forward.{name}'")
            raise typer.Exit(1)

        seen[key] = f"base.forward.{name}"
        fwds.append(QemuFwd(proto=base_fwd.proto, host=base_fwd.host, guest=base_fwd.target))

    for jname, jail in state.jails.items():
        for fname, jfwd in jail.forwards.items():
            key = (jfwd.proto, jfwd.host)
            if key in seen:
                err(f"Port conflict: {jfwd.proto}/{jfwd.host} claimed by '{seen[key]}' and '{jname}.forward.{fname}'")
                raise typer.Exit(1)

            seen[key] = f"{jname}.forward.{fname}"
            fwds.append(QemuFwd(proto=jfwd.proto, host=jfwd.host, guest=jfwd.host))

    return sorted(fwds, key=lambda f: (f.proto, f.host, f.guest))


def derive_qemu_shares(state: State) -> list[QemuShare]:
    by_host: dict[str, QemuShare] = {}
    for mnt in state.base.mounts.values():
        t = _tag(mnt.host)
        by_host[mnt.host] = QemuShare(
            host=mnt.host,
            id=f"fs_{t}",
            mount_tag=_mount_tag(mnt.host),
        )
    for jail in state.jails.values():
        for jmnt in jail.mounts.values():
            t = _tag(jmnt.host)
            by_host[jmnt.host] = QemuShare(
                host=jmnt.host,
                id=f"fs_{t}",
                mount_tag=_mount_tag(jmnt.host),
            )
    return sorted(by_host.values(), key=lambda s: s.host)


def needs_qemu_restart(old_state: State, new_state: State) -> bool:
    if new_state.ssh_port is None:
        raise RuntimeError("state.ssh_port is not set")

    launched_fwds = {(f.proto, f.host, f.guest) for f in old_state.launched_fwds}
    desired_fwds = {(f.proto, f.host, f.guest) for f in derive_qemu_fwds(state=new_state)}

    launched_hosts = {s.host for s in old_state.launched_shares}
    desired_hosts = {s.host for s in derive_qemu_shares(new_state)}

    return not (desired_fwds <= launched_fwds and desired_hosts <= launched_hosts)


def derive_plan(old_state: State, new_state: State) -> Plan:
    jails = [JailPlan(name=n, release=j.release, ip=j.ip, base=j.base) for n, j in new_state.jails.items()]

    new_target_mounts = _all_target_mounts(new_state)
    mounts = sorted(new_target_mounts.values(), key=lambda m: m.mount_tag)

    execs = [
        ExecPlan(name=en, jail=jn, cmd=e.cmd, dir=e.dir, env=e.env, healthcheck=e.healthcheck)
        for jn, j in new_state.jails.items()
        for en, e in j.execs.items()
    ]

    jail_rdrs = [
        RdrPlan(jail=jn, proto=f.proto, target_port=f.host, jail_port=f.jail)
        for jn, j in new_state.jails.items()
        for f in j.forwards.values()
    ]

    new_nullfs = _all_nullfs(new_state)
    jail_mounts = sorted(new_nullfs.values(), key=lambda m: (m.jail, m.target_path))

    stale_jails = [StaleJailPlan(name=name) for name in sorted(set(old_state.jails) - set(new_state.jails))]

    old_target_mounts = _all_target_mounts(old_state)
    stale_mounts = [
        StaleMountPlan(mount_tag=tag, target=m.target)
        for tag, m in old_target_mounts.items()
        if tag not in new_target_mounts
    ]

    old_nullfs = _all_nullfs(old_state)
    stale_jail_mounts = [
        StaleNullfsPlan(jail=jail, target_path=vp) for (jail, vp) in sorted(set(old_nullfs) - set(new_nullfs))
    ]

    return Plan(
        jails=jails,
        mounts=mounts,
        execs=execs,
        jail_rdrs=jail_rdrs,
        jail_mounts=jail_mounts,
        stale_jails=stale_jails,
        stale_mounts=stale_mounts,
        stale_jail_mounts=stale_jail_mounts,
    )


def load_state(state_file: Path) -> State:
    if not state_file.exists():
        return State()
    try:
        data = loads(state_file.read_text())
        return State.model_validate(data)
    except Exception:
        return State()


def save_state(state: State, state_file: Path) -> None:
    tmp = state_file.with_suffix(".tmp")
    tmp.write_text(state.model_dump_json(indent=2))
    tmp.replace(state_file)
