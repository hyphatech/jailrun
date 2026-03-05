import os
from pathlib import Path

import pytest

from jailrun import qemu
from jailrun.schemas import QemuFwd, QemuShare, State
from jailrun.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    root = tmp_path / "jrun"
    return Settings(
        ssh_dir=root / "ssh",
        log_dir=root / "logs",
        disk_dir=root / "disks",
        cloud_dir=root / "cloud",
        pid_file=root / "vm.pid",
        state_file=root / "state.json",
    )


def test_parse_size_bytes_and_units() -> None:
    assert qemu.parse_size("123") == 123
    assert qemu.parse_size("1K") == 1024
    assert qemu.parse_size("2M") == 2 * 1024**2
    assert qemu.parse_size("3G") == 3 * 1024**3
    assert qemu.parse_size("1.5G") == int(1.5 * 1024**3)


def test_build_netdev_arg_includes_default_ssh_and_rules() -> None:
    rules = [
        QemuFwd(proto="tcp", host=8080, guest=80),
        QemuFwd(proto="udp", host=5353, guest=5353),
    ]
    out = qemu.build_netdev_arg(hostfwd=rules, default_ssh_port=2222)

    assert "user" in out
    assert "id=net0" in out
    assert "hostfwd=tcp:127.0.0.1:2222-:22" in out

    assert "hostfwd=tcp:127.0.0.1:8080-:80" in out
    assert "hostfwd=udp:127.0.0.1:5353-:5353" in out


def test_build_share_args_two_shares(tmp_path: Path) -> None:
    s1 = QemuShare(host=str((tmp_path / "h1").resolve()), id="fs_a", mount_tag="tag_a")
    s2 = QemuShare(host=str((tmp_path / "h2").resolve()), id="fs_b", mount_tag="tag_b")

    features = qemu.detect_qemu_features()
    args = qemu.build_share_args([s1, s2], features=features)

    assert "-fsdev" in args
    assert "-device" in args

    assert f"local,id={s1.id},path={s1.host},security_model=none,readonly=off" in args
    assert f"virtio-9p-device,fsdev={s1.id},mount_tag={s1.mount_tag}" in args

    assert f"local,id={s2.id},path={s2.host},security_model=none,readonly=off" in args
    assert f"virtio-9p-device,fsdev={s2.id},mount_tag={s2.mount_tag}" in args


def test_build_qemu_cmd_minimal_state_no_shares_or_fwds(settings: Settings) -> None:
    state = State()

    cmd = qemu.build_qemu_cmd(state, mode=qemu.QemuMode.SERVER, settings=settings)
    features = qemu.detect_qemu_features()

    assert cmd[0] == f"qemu-system-{features.arch}"

    netdev_idx = cmd.index("-netdev") + 1
    assert f"hostfwd=tcp:127.0.0.1:{settings.ssh_port}-:22" in cmd[netdev_idx]

    assert "-display" in cmd
    assert "none" in cmd


def test_build_qemu_cmd_foreground_adds_serial_and_nographic(settings: Settings) -> None:
    state = State()

    cmd = qemu.build_qemu_cmd(state, mode=qemu.QemuMode.TTY, settings=settings)

    assert "-nographic" in cmd
    assert "-serial" in cmd
    assert "mon:stdio" in cmd


def test_vm_is_running_missing_pid_file(tmp_path: Path) -> None:
    pid_file = tmp_path / "missing.pid"
    running, pid = qemu.vm_is_running(pid_file)
    assert running is False
    assert pid is None


def test_vm_is_running_pid_not_qemu_unlinks(tmp_path: Path) -> None:
    pid_file = tmp_path / "vm.pid"
    pid_file.write_text(str(os.getpid()))

    running, pid = qemu.vm_is_running(pid_file)

    assert running is False
    assert pid is None
    assert not pid_file.exists()
