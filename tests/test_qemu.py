import os
from pathlib import Path

import pytest

from jailrun import qemu
from jailrun.qemu import QemuFeatures
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


@pytest.fixture
def sample_features() -> QemuFeatures:
    return QemuFeatures(
        qemu_bin="qemu-system-x86_64",
        arch="x86_64",
        machine="q35",
        accel="tcg",
        cpu="max",
        bios="OVMF.fd",
        bios_vars=None,
        virtio_suffix="pci",
        display="gtk",
        supports_9p=True,
    )


@pytest.fixture
def sample_features_with_vars(tmp_path: Path) -> QemuFeatures:
    vars_file = tmp_path / "OVMF_VARS.fd"
    vars_file.write_bytes(b"")
    return QemuFeatures(
        qemu_bin="qemu-system-x86_64",
        arch="x86_64",
        machine="q35",
        accel="kvm:tcg",
        cpu=None,
        bios="/usr/share/edk2/ovmf/OVMF_CODE.fd",
        bios_vars=str(vars_file),
        virtio_suffix="pci",
        display="gtk",
        supports_9p=True,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("123", 123),
        ("1K", 1024),
        ("2M", 2 * 1024**2),
        ("3G", 3 * 1024**3),
        ("1.5G", int(1.5 * 1024**3)),
        ("2t", 2 * 1024**4),
    ],
)
def test_parse_size(value: str, expected: int) -> None:
    assert qemu.parse_size(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("AMD64", "x86_64"),
        ("x86_64", "x86_64"),
        ("arm64", "aarch64"),
        ("aarch64", "aarch64"),
        ("riscv64", "riscv64"),
    ],
)
def test_normalize_machine(value: str, expected: str) -> None:
    assert qemu._normalize_machine(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("amd64", "x86_64"),
        ("x86_64", "x86_64"),
        ("arm64", "aarch64"),
        ("aarch64", "aarch64"),
    ],
)
def test_qemu_arch_for_host_supported(value: str, expected: str) -> None:
    assert qemu._qemu_arch_for_host(value) == expected


def test_qemu_arch_for_host_rejects_unsupported_architecture() -> None:
    with pytest.raises(RuntimeError, match="Unsupported architecture: sparc64"):
        qemu._qemu_arch_for_host("sparc64")


@pytest.mark.parametrize(
    ("arch", "expected"),
    [
        ("x86_64", "q35"),
        ("aarch64", "virt"),
    ],
)
def test_default_machine_for_arch(arch: str, expected: str) -> None:
    assert qemu._default_machine_for_arch(arch) == expected


def test_default_machine_for_arch_rejects_unsupported_architecture() -> None:
    with pytest.raises(RuntimeError, match="Unsupported architecture: riscv64"):
        qemu._default_machine_for_arch("riscv64")


@pytest.mark.parametrize(
    ("arch", "expected"),
    [
        ("x86_64", "pci"),
        ("aarch64", "device"),
    ],
)
def test_virtio_suffix_for_arch(arch: str, expected: str) -> None:
    assert qemu._virtio_suffix_for_arch(arch) == expected


def test_virtio_suffix_for_arch_rejects_unsupported_architecture() -> None:
    with pytest.raises(RuntimeError, match="Unsupported architecture: riscv64"):
        qemu._virtio_suffix_for_arch("riscv64")


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("darwin", "cocoa"),
        ("linux", "gtk"),
        ("freebsd", "gtk"),
    ],
)
def test_preferred_display_for_host(system: str, expected: str) -> None:
    assert qemu._preferred_display_for_host(system) == expected


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("darwin", "hvf:tcg"),
        ("linux", "kvm:tcg"),
        ("freebsd", "tcg"),
    ],
)
def test_accel_chain_for_host(system: str, expected: str) -> None:
    assert qemu._accel_chain_for_host(system) == expected


@pytest.mark.parametrize(
    ("accel", "expected"),
    [
        ("kvm", "host"),
        ("hvf", "host"),
        ("tcg", "max"),
        ("kvm:tcg", None),
        ("hvf:tcg", None),
        ("unknown", None),
    ],
)
def test_pick_cpu(accel: str, expected: str | None) -> None:
    assert qemu._pick_cpu(accel) == expected


def test_ensure_linux_vars_copies_template_when_vars_absent(tmp_path: Path, settings: Settings) -> None:
    template = tmp_path / "OVMF_VARS_template.fd"
    template.write_bytes(b"varsdata")
    settings.disk_dir.mkdir(parents=True, exist_ok=True)

    result = qemu._ensure_linux_vars(settings, str(template))

    assert result.exists()
    assert result.read_bytes() == b"varsdata"


def test_ensure_linux_vars_does_not_overwrite_existing_vars(tmp_path: Path, settings: Settings) -> None:
    template = tmp_path / "OVMF_VARS_template.fd"
    template.write_bytes(b"template")
    settings.disk_dir.mkdir(parents=True, exist_ok=True)
    existing = settings.disk_dir / "OVMF_VARS.fd"
    existing.write_bytes(b"already_written")

    result = qemu._ensure_linux_vars(settings, str(template))

    assert result.read_bytes() == b"already_written"


def test_ensure_linux_vars_returns_path_inside_disk_dir(tmp_path: Path, settings: Settings) -> None:
    template = tmp_path / "OVMF_VARS_template.fd"
    template.write_bytes(b"")
    settings.disk_dir.mkdir(parents=True, exist_ok=True)

    result = qemu._ensure_linux_vars(settings, str(template))

    assert result.parent == settings.disk_dir


def test_build_qemu_cmd_uses_bios_flag_when_bios_vars_is_none(
    settings: Settings,
    sample_features: QemuFeatures,
) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.SERVER,
        features=sample_features,
    )

    assert "-bios" in cmd
    assert cmd[cmd.index("-bios") + 1] == sample_features.bios


def test_build_qemu_cmd_omits_bios_flag_when_bios_vars_is_set(
    settings: Settings,
    sample_features_with_vars: QemuFeatures,
) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.SERVER,
        features=sample_features_with_vars,
    )

    assert "-bios" not in cmd


def test_build_qemu_cmd_uses_pflash_code_readonly_when_bios_vars_is_set(
    settings: Settings,
    sample_features_with_vars: QemuFeatures,
) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.SERVER,
        features=sample_features_with_vars,
    )

    expected = f"if=pflash,format=raw,unit=0,readonly=on,file={sample_features_with_vars.bios}"

    assert expected in cmd


def test_build_qemu_cmd_uses_pflash_vars_writable_when_bios_vars_is_set(
    settings: Settings,
    sample_features_with_vars: QemuFeatures,
) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.SERVER,
        features=sample_features_with_vars,
    )

    expected = f"if=pflash,format=raw,unit=1,file={sample_features_with_vars.bios_vars}"

    assert expected in cmd


def test_build_qemu_cmd_pflash_code_is_unit_0_before_vars_unit_1(
    settings: Settings,
    sample_features_with_vars: QemuFeatures,
) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.SERVER,
        features=sample_features_with_vars,
    )

    drives = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-drive"]
    code_idx = next(i for i, d in enumerate(drives) if "unit=0" in d)
    vars_idx = next(i for i, d in enumerate(drives) if "unit=1" in d)

    assert code_idx < vars_idx


def test_build_netdev_arg_always_includes_ssh_forward(settings: Settings) -> None:
    out = qemu.build_netdev_arg(
        hostfwd=[],
        ssh_host=settings.vm_host,
        ssh_port=settings.ssh_port,
    )

    assert out == f"user,id=net0,hostfwd=tcp:{settings.vm_host}:{settings.ssh_port}-:22"


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        (QemuFwd(proto="tcp", host=8080, guest=80), "hostfwd=tcp:127.0.0.1:8080-:80"),
        (QemuFwd(proto="udp", host=5353, guest=5353), "hostfwd=udp:127.0.0.1:5353-:5353"),
    ],
)
def test_build_netdev_arg_appends_forward_rule(
    settings: Settings,
    rule: QemuFwd,
    expected: str,
) -> None:
    out = qemu.build_netdev_arg(
        hostfwd=[rule],
        ssh_host=settings.vm_host,
        ssh_port=settings.ssh_port,
    )

    assert expected in out


def test_build_share_args_rejects_when_9p_is_not_supported(tmp_path: Path, sample_features: QemuFeatures) -> None:
    share = QemuShare(host=str(tmp_path), id="fs0", mount_tag="tag0")
    features = QemuFeatures(
        qemu_bin=sample_features.qemu_bin,
        arch=sample_features.arch,
        machine=sample_features.machine,
        accel=sample_features.accel,
        cpu=sample_features.cpu,
        bios=sample_features.bios,
        bios_vars=None,
        virtio_suffix=sample_features.virtio_suffix,
        display=sample_features.display,
        supports_9p=False,
    )

    with pytest.raises(RuntimeError, match="does not appear to support 9p"):
        qemu.build_share_args([share], features=features)


def test_build_share_args_adds_fsdev_entry(tmp_path: Path, sample_features: QemuFeatures) -> None:
    share = QemuShare(host=str(tmp_path.resolve()), id="fs0", mount_tag="tag0")

    args = qemu.build_share_args([share], features=sample_features)

    assert "-fsdev" in args
    assert f"local,id={share.id},path={share.host},security_model=none,readonly=off" in args


def test_build_share_args_adds_virtio_9p_device_entry(tmp_path: Path, sample_features: QemuFeatures) -> None:
    share = QemuShare(host=str(tmp_path.resolve()), id="fs0", mount_tag="tag0")

    args = qemu.build_share_args([share], features=sample_features)

    assert "-device" in args
    assert f"virtio-9p-pci,fsdev={share.id},mount_tag={share.mount_tag}" in args


def test_build_qemu_cmd_requires_state_ssh_port(settings: Settings, sample_features: QemuFeatures) -> None:
    with pytest.raises(RuntimeError, match="state.ssh_port is not set"):
        qemu.build_qemu_cmd(
            State(),
            settings=settings,
            mode=qemu.QemuMode.SERVER,
            features=sample_features,
        )


def test_build_qemu_cmd_uses_featured_qemu_binary(settings: Settings, sample_features: QemuFeatures) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.SERVER,
        features=sample_features,
    )

    assert cmd[0] == sample_features.qemu_bin


def test_build_qemu_cmd_sets_machine_and_accel(settings: Settings, sample_features: QemuFeatures) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.SERVER,
        features=sample_features,
    )

    assert cmd[cmd.index("-M") + 1] == "q35,accel=tcg"


def test_build_qemu_cmd_sets_cpu_when_feature_provides_one(settings: Settings, sample_features: QemuFeatures) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.SERVER,
        features=sample_features,
    )

    assert cmd[cmd.index("-cpu") + 1] == "max"


def test_build_qemu_cmd_omits_cpu_when_feature_cpu_is_none(settings: Settings, sample_features: QemuFeatures) -> None:
    state = State(ssh_port=2222)
    features = QemuFeatures(
        qemu_bin=sample_features.qemu_bin,
        arch=sample_features.arch,
        machine=sample_features.machine,
        accel="kvm:tcg",
        cpu=None,
        bios=sample_features.bios,
        bios_vars=None,
        virtio_suffix=sample_features.virtio_suffix,
        display=sample_features.display,
        supports_9p=sample_features.supports_9p,
    )

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.SERVER,
        features=features,
    )

    assert "-cpu" not in cmd


def test_build_qemu_cmd_server_mode_uses_display_none(settings: Settings, sample_features: QemuFeatures) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.SERVER,
        features=sample_features,
    )

    assert cmd[cmd.index("-display") + 1] == "none"


def test_build_qemu_cmd_tty_mode_adds_nographic(settings: Settings, sample_features: QemuFeatures) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.TTY,
        features=sample_features,
    )

    assert "-nographic" in cmd


def test_build_qemu_cmd_tty_mode_uses_mon_stdio_serial(settings: Settings, sample_features: QemuFeatures) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.TTY,
        features=sample_features,
    )

    assert cmd[cmd.index("-serial") + 1] == "mon:stdio"


def test_build_qemu_cmd_graphic_mode_uses_feature_display(settings: Settings, sample_features: QemuFeatures) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.GRAPHIC,
        features=sample_features,
    )

    assert cmd[cmd.index("-display") + 1] == sample_features.display


@pytest.mark.parametrize(
    "device",
    ["ramfb", "qemu-xhci", "usb-kbd", "usb-tablet"],
)
def test_build_qemu_cmd_graphic_mode_adds_required_devices(
    settings: Settings,
    sample_features: QemuFeatures,
    device: str,
) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.GRAPHIC,
        features=sample_features,
    )

    assert device in cmd


def test_build_qemu_cmd_uses_state_ssh_port_for_builtin_forward(
    settings: Settings,
    sample_features: QemuFeatures,
) -> None:
    state = State(ssh_port=2299)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.SERVER,
        features=sample_features,
    )

    netdev = cmd[cmd.index("-netdev") + 1]

    assert f"hostfwd=tcp:{settings.vm_host}:2299-:22" in netdev


def test_build_qemu_cmd_uses_settings_memory(settings: Settings, sample_features: QemuFeatures) -> None:
    state = State(ssh_port=2222)

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.SERVER,
        features=sample_features,
    )

    assert cmd[cmd.index("-m") + 1] == settings.qemu_memory


def test_build_qemu_cmd_uses_explicit_cpu_count_from_settings(
    settings: Settings,
    sample_features: QemuFeatures,
) -> None:
    state = State(ssh_port=2222)
    settings.qemu_cpus = 6

    cmd = qemu.build_qemu_cmd(
        state,
        settings=settings,
        mode=qemu.QemuMode.SERVER,
        features=sample_features,
    )

    assert cmd[cmd.index("-smp") + 1] == "6"


def test_vm_is_running_returns_false_when_pid_file_is_missing(tmp_path: Path) -> None:
    running, pid = qemu.vm_is_running(tmp_path / "missing.pid")

    assert running is False
    assert pid is None


def test_vm_is_running_rejects_non_qemu_process_and_unlinks_pid_file(tmp_path: Path) -> None:
    pid_file = tmp_path / "vm.pid"
    pid_file.write_text(str(os.getpid()))

    running, pid = qemu.vm_is_running(pid_file)

    assert running is False
    assert pid is None
    assert not pid_file.exists()
