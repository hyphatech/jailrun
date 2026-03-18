from pathlib import Path

import pytest
import typer

from jailrun import config, schemas


def test_private_jail_name_is_deterministic() -> None:
    a = schemas.private_jail_name("astronvim")
    b = schemas.private_jail_name("astronvim")
    c = schemas.private_jail_name("mysql")

    assert a == b
    assert a != c
    assert a.startswith("j")


def test_normalize_host_path_relative_resolves(tmp_path: Path) -> None:
    base = tmp_path / "base"
    (base / "data").mkdir(parents=True)

    out = config._normalize_host_path("data", base)

    assert Path(out).is_absolute()
    assert Path(out) == (base / "data").resolve()


def test_normalize_host_path_absolute_unchanged(tmp_path: Path) -> None:
    p = (tmp_path / "abs").resolve()
    p.mkdir()

    out = config._normalize_host_path(str(p), tmp_path)
    assert Path(out) == p.resolve()


def test_normalize_host_path_rejects_file(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()

    f = base / "logo.png"
    f.write_text("x")

    with pytest.raises(typer.Exit):
        config._normalize_host_path("logo.png", base)


def test_tag_mount_tag_and_target_path(tmp_path: Path) -> None:
    host = str((tmp_path / "x").resolve())
    t = config._tag(host)
    assert len(t) == 10
    mt = config._mount_tag(host)
    assert mt == f"jrun_{t}"
    vp = config._jail_target_path(host)
    assert vp == f"/mnt/jrun/{mt}"


def test_tag_deterministic() -> None:
    assert config._tag("/a/b/c") == config._tag("/a/b/c")
    assert config._tag("/a/b/c") != config._tag("/a/b/d")


def test_sort_jails_topological() -> None:
    jails = {
        "basej": schemas.JailConfig(name="basej", release="15.0"),
        "app": schemas.JailConfig(name="app", release="15.0", base=schemas.JailBaseConfig(name="basej")),
    }
    order = config.sort_jails(jails)
    assert order.index("basej") < order.index("app")


def test_sort_jails_cycle() -> None:
    jails = {
        "basej": schemas.JailConfig(name="basej", release="15.0", depends=["app"]),
        "app": schemas.JailConfig(name="app", release="15.0", depends=["basej"]),
    }

    with pytest.raises(typer.Exit):
        config.sort_jails(jails)


def test_sort_jails_respects_depends() -> None:
    jails = {
        "db": schemas.JailConfig(name="db", release="15.0"),
        "cache": schemas.JailConfig(name="cache", release="15.0"),
        "app": schemas.JailConfig(name="app", release="15.0", depends=["db", "cache"]),
    }
    order = config.sort_jails(jails)
    assert order.index("db") < order.index("app")
    assert order.index("cache") < order.index("app")


def test_sort_jails_base_and_depends_combined() -> None:
    jails = {
        "python": schemas.JailConfig(name="python", release="15.0"),
        "db": schemas.JailConfig(name="db", release="15.0"),
        "app": schemas.JailConfig(
            name="app",
            release="15.0",
            base=schemas.JailBaseConfig(name="python"),
            depends=["db"],
        ),
    }
    order = config.sort_jails(jails)
    assert order.index("python") < order.index("app")
    assert order.index("db") < order.index("app")


def test_sort_jails_independent_jails() -> None:
    jails = {
        "a": schemas.JailConfig(name="a", release="15.0"),
        "b": schemas.JailConfig(name="b", release="15.0"),
        "c": schemas.JailConfig(name="c", release="15.0"),
    }
    order = config.sort_jails(jails)
    assert set(order) == {"a", "b", "c"}


def test_sort_jails_deep_chain() -> None:
    jails = {
        "base": schemas.JailConfig(name="base", release="15.0"),
        "mid": schemas.JailConfig(name="mid", release="15.0", base=schemas.JailBaseConfig(name="base")),
        "top": schemas.JailConfig(name="top", release="15.0", base=schemas.JailBaseConfig(name="mid")),
    }
    order = config.sort_jails(jails)
    assert order.index("base") < order.index("mid") < order.index("top")


def test_resolve_jail_dependencies_single_no_deps() -> None:
    jails = {
        "app": schemas.JailConfig(name="app", release="15.0"),
    }
    result = config.resolve_jail_dependencies({"app"}, jails)
    assert result == {"app"}


def test_resolve_jail_dependencies_includes_base() -> None:
    jails = {
        "python": schemas.JailConfig(name="python", release="15.0"),
        "app": schemas.JailConfig(name="app", release="15.0", base=schemas.JailBaseConfig(name="python")),
    }
    result = config.resolve_jail_dependencies({"app"}, jails)
    assert result == {"python", "app"}


def test_resolve_jail_dependencies_includes_depends() -> None:
    jails = {
        "db": schemas.JailConfig(name="db", release="15.0"),
        "app": schemas.JailConfig(name="app", release="15.0", depends=["db"]),
    }
    result = config.resolve_jail_dependencies({"app"}, jails)
    assert result == {"db", "app"}


def test_resolve_jail_dependencies_transitive() -> None:
    jails = {
        "base": schemas.JailConfig(name="base", release="15.0"),
        "db": schemas.JailConfig(name="db", release="15.0", base=schemas.JailBaseConfig(name="base")),
        "app": schemas.JailConfig(name="app", release="15.0", depends=["db"]),
    }
    result = config.resolve_jail_dependencies({"app"}, jails)
    assert result == {"base", "db", "app"}


def test_resolve_jail_dependencies_ignores_unknown() -> None:
    jails = {
        "app": schemas.JailConfig(name="app", release="15.0", depends=["missing"]),
    }
    result = config.resolve_jail_dependencies({"app"}, jails)
    assert result == {"app"}


def test_resolve_jail_dependencies_no_duplicates() -> None:
    jails = {
        "shared": schemas.JailConfig(name="shared", release="15.0"),
        "a": schemas.JailConfig(name="a", release="15.0", depends=["shared"]),
        "b": schemas.JailConfig(name="b", release="15.0", depends=["shared"]),
    }
    result = config.resolve_jail_dependencies({"a", "b"}, jails)
    assert result == {"shared", "a", "b"}


def test_resolve_jail_dependencies_diamond() -> None:
    jails = {
        "base": schemas.JailConfig(name="base", release="15.0"),
        "left": schemas.JailConfig(name="left", release="15.0", depends=["base"]),
        "right": schemas.JailConfig(name="right", release="15.0", depends=["base"]),
        "top": schemas.JailConfig(name="top", release="15.0", depends=["left", "right"]),
    }
    result = config.resolve_jail_dependencies({"top"}, jails)
    assert result == {"base", "left", "right", "top"}


def _write_ucl(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.ucl"
    p.write_text(content)
    return p


def test_parse_config_rejects_unknown_base_ref(tmp_path: Path) -> None:
    p = _write_ucl(
        tmp_path,
        """
        jail "app" {
            release = "15.0";
            base { type = "jail"; name = "nonexistent"; }
        }
    """,
    )
    with pytest.raises(typer.Exit):
        config.parse_config(p)


def test_parse_config_rejects_unknown_depends(tmp_path: Path) -> None:
    p = _write_ucl(
        tmp_path,
        """
        jail "app" {
            release = "15.0";
            depends ["ghost"];
        }
    """,
    )
    with pytest.raises(typer.Exit):
        config.parse_config(p)


def test_parse_config_accepts_valid_refs(tmp_path: Path) -> None:
    p = _write_ucl(
        tmp_path,
        """
        jail "db" { release = "15.0"; }
        jail "python" { release = "15.0"; }
        jail "app" {
            release = "15.0";
            base { type = "jail"; name = "python"; }
            depends ["db"];
        }
    """,
    )
    cfg = config.parse_config(p)
    assert "app" in cfg.jail
    assert "db" in cfg.jail
    assert "python" in cfg.jail


def test_parse_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(typer.Exit):
        config.parse_config(tmp_path / "missing.ucl")


def test_resolve_jail_uses_explicit_release(tmp_path: Path) -> None:
    jc = schemas.JailConfig(name="j1", release="14.3-RELEASE")
    st = config.resolve_jail(jc, tmp_path, default_release="15.0-RELEASE")
    assert st.release == "14.3-RELEASE"


def test_resolve_jail_falls_back_to_default_release(tmp_path: Path) -> None:
    jc = schemas.JailConfig(name="j1")
    st = config.resolve_jail(jc, tmp_path, default_release="15.0-RELEASE")
    assert st.release == "15.0-RELEASE"


def test_resolve_base_normalizes_mounts(tmp_path: Path) -> None:
    config_base = tmp_path / "cfg"
    (config_base / "rel/path").mkdir(parents=True)

    bc = schemas.BaseConfig(
        mount={"m": schemas.BaseMountConfig(host="rel/path", target="/target/path")},
    )
    st = config.resolve_base(bc, config_base)

    assert "m" in st.mounts
    assert Path(st.mounts["m"].host) == (config_base / "rel/path").resolve()
    assert st.mounts["m"].target == "/target/path"


def test_resolve_base_preserves_setup_and_forwards(tmp_path: Path) -> None:
    bc = schemas.BaseConfig(
        setup={"s": schemas.LocalSetupStep(file="play.yml")},
        forward={"f": schemas.BaseForwardConfig(host=8080, target=80)},
    )
    st = config.resolve_base(bc, tmp_path)
    assert "s" in st.setup
    assert "f" in st.forwards


def test_resolve_jail_normalizes_mounts(tmp_path: Path) -> None:
    config_base = tmp_path / "cfg"
    (config_base / "rel/path").mkdir(parents=True)

    jc = schemas.JailConfig(
        name="j1",
        release="15.0",
        mount={"m": schemas.JailMountConfig(host="rel/path", jail="/inside")},
    )
    st = config.resolve_jail(jc, config_base, default_release="15.0-RELEASE")

    assert "m" in st.mounts
    assert Path(st.mounts["m"].host) == (config_base / "rel/path").resolve()
    assert st.mounts["m"].jail == "/inside"


def test_resolve_jail_preserves_execs(tmp_path: Path) -> None:
    jc = schemas.JailConfig(
        name="j1",
        release="15.0",
        exec={"srv": schemas.ExecConfig(cmd="python3 -m http.server", dir="/app")},
    )
    st = config.resolve_jail(jc, tmp_path, default_release="15.0-RELEASE")
    assert "srv" in st.execs
    assert st.execs["srv"].cmd == "python3 -m http.server"


def test_derive_qemu_fwds_detects_conflict_with_reserved(state: schemas.State) -> None:
    state.base.forwards = {"ssh": schemas.BaseForwardConfig(proto="tcp", host=2222, target=22)}
    with pytest.raises(typer.Exit):
        config.derive_qemu_fwds(state)


def test_derive_qemu_fwds_detects_conflict_between_base_and_jail(state: schemas.State) -> None:
    state.base.forwards = {"f": schemas.BaseForwardConfig(proto="tcp", host=8080, target=8080)}
    state.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            forwards={"web": schemas.JailForwardConfig(proto="tcp", host=8080, jail=80)},
        )
    }
    with pytest.raises(typer.Exit):
        config.derive_qemu_fwds(state)


def test_derive_qemu_fwds_no_conflict(state: schemas.State) -> None:
    state.base.forwards = {"web": schemas.BaseForwardConfig(proto="tcp", host=8080, target=80)}
    state.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            forwards={"api": schemas.JailForwardConfig(proto="tcp", host=9090, jail=9090)},
        )
    }
    fwds = config.derive_qemu_fwds(state)
    ports = {(f.proto, f.host) for f in fwds}
    assert ("tcp", 8080) in ports
    assert ("tcp", 9090) in ports


def test_derive_qemu_fwds_sorted(state: schemas.State) -> None:
    state.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            forwards={
                "b": schemas.JailForwardConfig(proto="tcp", host=9000, jail=9000),
                "a": schemas.JailForwardConfig(proto="tcp", host=8000, jail=8000),
            },
        )
    }
    fwds = config.derive_qemu_fwds(state)
    hosts = [f.host for f in fwds]
    assert hosts == sorted(hosts)


def test_derive_qemu_fwds_same_port_different_proto(state: schemas.State) -> None:
    state.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            forwards={
                "tcp": schemas.JailForwardConfig(proto="tcp", host=8080, jail=8080),
                "udp": schemas.JailForwardConfig(proto="udp", host=8080, jail=8080),
            },
        )
    }
    fwds = config.derive_qemu_fwds(state)
    assert len(fwds) == 2


def test_derive_qemu_shares_dedup_by_host(state: schemas.State, tmp_path: Path) -> None:
    host = str((tmp_path / "same").resolve())
    state.base.mounts = {"m": schemas.BaseMountConfig(host=host, target="/target")}
    state.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            mounts={"m": schemas.JailMountConfig(host=host, jail="/inside")},
        )
    }
    shares = config.derive_qemu_shares(state)
    assert len(shares) == 1
    assert shares[0].host == host


def test_derive_qemu_shares_different_hosts(state: schemas.State, tmp_path: Path) -> None:
    h1 = str((tmp_path / "a").resolve())
    h2 = str((tmp_path / "b").resolve())
    state.base.mounts = {"m1": schemas.BaseMountConfig(host=h1, target="/t1")}
    state.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            mounts={"m2": schemas.JailMountConfig(host=h2, jail="/t2")},
        )
    }
    shares = config.derive_qemu_shares(state)
    assert len(shares) == 2


def test_needs_qemu_restart_no_change(state: schemas.State) -> None:
    state.base.forwards = {"f": schemas.BaseForwardConfig(proto="tcp", host=8080, target=80)}
    state.launched_fwds = config.derive_qemu_fwds(state)
    state.launched_shares = config.derive_qemu_shares(state)
    new_st = state.model_copy(deep=True)
    assert not config.needs_qemu_restart(state, new_st)


def test_needs_qemu_restart_new_forward(state: schemas.State) -> None:
    state.launched_fwds = config.derive_qemu_fwds(state)
    state.launched_shares = config.derive_qemu_shares(state)
    new = state.model_copy(deep=True)
    new.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            forwards={"web": schemas.JailForwardConfig(proto="tcp", host=9090, jail=80)},
        )
    }
    assert config.needs_qemu_restart(state, new)


def test_needs_qemu_restart_new_mount(state: schemas.State) -> None:
    state.launched_fwds = config.derive_qemu_fwds(state)
    state.launched_shares = config.derive_qemu_shares(state)
    new = state.model_copy(deep=True)
    new.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            mounts={"m": schemas.JailMountConfig(host="/tmp/new", jail="/mnt/new")},
        )
    }
    assert config.needs_qemu_restart(state, new)


def test_needs_qemu_restart_removed_forward_no_restart(state: schemas.State) -> None:
    state.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            forwards={"web": schemas.JailForwardConfig(proto="tcp", host=9090, jail=80)},
        )
    }
    state.launched_fwds = config.derive_qemu_fwds(state)
    state.launched_shares = config.derive_qemu_shares(state)

    new = state.model_copy(deep=True)
    new.jails = {}

    assert not config.needs_qemu_restart(state, new)


def test_derive_plan_empty_to_empty() -> None:
    plan = config.derive_plan(schemas.State(), schemas.State())
    assert plan.jails == []
    assert plan.stale_jails == []
    assert plan.mounts == []
    assert plan.stale_mounts == []


def test_derive_plan_new_jail() -> None:
    old = schemas.State()
    new = schemas.State()
    new.jails = {"j1": schemas.JailState(name="j1", release="15.0", ip="10.0.0.1")}
    plan = config.derive_plan(old, new)
    assert len(plan.jails) == 1
    assert plan.jails[0].name == "j1"
    assert plan.stale_jails == []


def test_derive_plan_stale_jail() -> None:
    old = schemas.State()
    old.jails = {"j1": schemas.JailState(name="j1", release="15.0", ip="10.0.0.1")}
    new = schemas.State()
    plan = config.derive_plan(old, new)
    assert plan.jails == []


def test_derive_plan_stale_mounts() -> None:
    old = schemas.State()
    old.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            mounts={"m": schemas.JailMountConfig(host="/tmp/old", jail="/mnt/old")},
        )
    }
    new = schemas.State()
    plan = config.derive_plan(old, new)
    assert len(plan.stale_mounts) > 0
    assert len(plan.stale_jail_mounts) > 0


def test_derive_plan_new_mounts() -> None:
    old = schemas.State()
    new = schemas.State()
    new.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            mounts={"m": schemas.JailMountConfig(host="/tmp/new", jail="/mnt/new")},
        )
    }
    plan = config.derive_plan(old, new)
    assert len(plan.mounts) > 0
    assert len(plan.jail_mounts) > 0
    assert plan.stale_mounts == []


def test_derive_plan_execs() -> None:
    old = schemas.State()
    new = schemas.State()
    new.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            execs={"srv": schemas.ExecConfig(cmd="python3 -m http.server", dir="/app")},
        )
    }
    plan = config.derive_plan(old, new)
    assert len(plan.execs) == 1
    assert plan.execs[0].jail == "j1"
    assert plan.execs[0].name == "srv"


def test_derive_plan_rdrs() -> None:
    old = schemas.State()
    new = schemas.State()
    new.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            forwards={"web": schemas.JailForwardConfig(proto="tcp", host=8080, jail=80)},
        )
    }
    plan = config.derive_plan(old, new)
    assert len(plan.jail_rdrs) == 1
    assert plan.jail_rdrs[0].jail == "j1"
    assert plan.jail_rdrs[0].target_port == 8080
    assert plan.jail_rdrs[0].jail_port == 80


def test_derive_plan_base_mounts() -> None:
    old = schemas.State()
    new = schemas.State()
    new.base.mounts = {"m": schemas.BaseMountConfig(host="/tmp/base", target="/mnt/base")}
    plan = config.derive_plan(old, new)
    assert len(plan.mounts) == 1


def test_save_and_load_state_roundtrip(tmp_path: Path) -> None:
    f = tmp_path / "state.json"
    s = schemas.State()
    s.jails = {"j": schemas.JailState(name="j", release="15.0")}
    config.save_state(s, f)
    out = config.load_state(f)
    assert "j" in out.jails
    assert out.jails["j"].release == "15.0"


def test_load_state_missing_file(tmp_path: Path) -> None:
    out = config.load_state(tmp_path / "missing.json")
    assert out.jails == {}
    assert out.version == 1


def test_load_state_corrupt_file(tmp_path: Path) -> None:
    f = tmp_path / "state.json"
    f.write_text("not json at all {{{")
    out = config.load_state(f)
    assert out.jails == {}


def test_save_state_atomic(tmp_path: Path) -> None:
    f = tmp_path / "state.json"
    s = schemas.State()
    s.jails = {"j": schemas.JailState(name="j", release="15.0")}
    config.save_state(s, f)
    assert not f.with_suffix(".tmp").exists()
    assert f.exists()


def test_save_state_full_roundtrip(state: schemas.State, tmp_path: Path) -> None:
    f = tmp_path / "state.json"
    state.base.forwards = {"f": schemas.BaseForwardConfig(proto="tcp", host=8080, target=80)}
    state.base.mounts = {"m": schemas.BaseMountConfig(host="/tmp/x", target="/mnt/x")}
    state.jails = {
        "j1": schemas.JailState(
            name="j1",
            release="15.0",
            ip="10.0.0.1",
            forwards={"web": schemas.JailForwardConfig(proto="tcp", host=9090, jail=80)},
            mounts={"m": schemas.JailMountConfig(host="/tmp/y", jail="/mnt/y")},
            execs={"srv": schemas.ExecConfig(cmd="echo hi", dir="/")},
        )
    }
    state.launched_fwds = config.derive_qemu_fwds(state)
    state.launched_shares = config.derive_qemu_shares(state)
    config.save_state(state, f)

    out = config.load_state(f)
    assert out.jails["j1"].ip == "10.0.0.1"
    assert out.jails["j1"].execs["srv"].cmd == "echo hi"
    assert len(out.launched_fwds) > 0
    assert len(out.launched_shares) > 0
