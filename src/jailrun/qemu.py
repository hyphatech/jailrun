import os
import platform
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from jailrun.config import derive_qemu_fwds, derive_qemu_shares
from jailrun.http import download
from jailrun.network import ensure_vm_key
from jailrun.schemas import QemuFwd, QemuShare, State
from jailrun.serializers import loads
from jailrun.settings import Settings
from jailrun.templates import build_jinja_env
from jailrun.ui import info, ok


@dataclass(frozen=True)
class QemuFeatures:
    qemu_bin: str
    arch: str
    machine: str
    accel: str
    cpu: str | None
    bios: str
    bios_vars: str | None
    virtio_suffix: str
    display: str
    supports_9p: bool


class QemuMode(StrEnum):
    SERVER = "server"
    TTY = "tty"
    GRAPHIC = "graphic"


def _normalize_machine(machine: str) -> str:
    machine = machine.lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "aarch64"
    return machine


def _qemu_arch_for_host(machine: str) -> str:
    machine = _normalize_machine(machine)
    if machine in {"x86_64", "aarch64"}:
        return machine

    raise RuntimeError(f"Unsupported architecture: {machine}")


def _default_machine_for_arch(arch: str) -> str:
    if arch == "aarch64":
        return "virt"
    if arch == "x86_64":
        return "q35"

    raise RuntimeError(f"Unsupported architecture: {arch}")


def _virtio_suffix_for_arch(arch: str) -> str:
    if arch == "aarch64":
        return "device"
    if arch == "x86_64":
        return "pci"

    raise RuntimeError(f"Unsupported architecture: {arch}")


def _preferred_display_for_host(system: str) -> str:
    if system == "darwin":
        return "cocoa"
    return "gtk"


def _accel_chain_for_host(system: str) -> str:
    if system == "darwin":
        return "hvf:tcg"
    if system == "linux":
        return "kvm:tcg"
    return "tcg"


def _pick_cpu(accel: str) -> str | None:
    if ":" in accel:
        return None

    if accel in {"kvm", "hvf"}:
        return "host"

    if accel == "tcg":
        return "max"

    return None


def _require_qemu_bin(arch: str) -> str:
    binary = f"qemu-system-{arch}"
    path = shutil.which(binary)
    if path is None:
        raise RuntimeError(f"{binary} not found in PATH")
    return path


def _first_existing_path(candidates: list[str]) -> str | None:
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _qemu_help_text(qemu_bin: str, *args: str) -> str:
    try:
        proc = subprocess.run(
            [qemu_bin, *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""

    return "\n".join(part for part in [proc.stdout, proc.stderr] if part).strip()


_DISPLAY_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _supported_displays(qemu_bin: str) -> set[str]:
    text = _qemu_help_text(qemu_bin, "-display", "help")
    displays: set[str] = set()

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        name, *_ = re.split(r"[\s,]", line, maxsplit=1)
        if _DISPLAY_NAME_RE.fullmatch(name):
            displays.add(name)

    return displays


def _pick_display(system: str, qemu_bin: str) -> str:
    preferred = _preferred_display_for_host(system)
    displays = _supported_displays(qemu_bin)

    if not displays:
        return preferred
    if preferred in displays:
        return preferred

    for fallback in ("gtk", "cocoa", "sdl", "default"):
        if fallback in displays:
            return fallback

    return sorted(displays)[0]


def _probe_darwin_bios(arch: str, predefined: str | None) -> str:
    if predefined:
        return predefined

    if arch == "aarch64":
        abs_candidates = [
            "/opt/homebrew/share/qemu/edk2-aarch64-code.fd",
            "/usr/local/share/qemu/edk2-aarch64-code.fd",
        ]
        fallback = "edk2-aarch64-code.fd"
    elif arch == "x86_64":
        abs_candidates = [
            "/opt/homebrew/share/qemu/edk2-x86_64-code.fd",
            "/usr/local/share/qemu/edk2-x86_64-code.fd",
        ]
        fallback = "edk2-x86_64-code.fd"
    else:
        raise RuntimeError(f"Unsupported architecture: {arch}")

    bios = _first_existing_path(abs_candidates)
    if bios:
        return bios

    return fallback


LINUX_VARS_MAP = {
    "/usr/share/OVMF/OVMF_CODE.fd": "/usr/share/OVMF/OVMF_VARS.fd",
    "/usr/share/OVMF/OVMF_CODE_4M.fd": "/usr/share/OVMF/OVMF_VARS_4M.fd",
    "/usr/share/ovmf/OVMF.fd": "/usr/share/ovmf/OVMF_VARS.fd",
    "/usr/share/edk2/ovmf/OVMF_CODE.fd": "/usr/share/edk2/ovmf/OVMF_VARS.fd",
    "/usr/share/edk2/x64/OVMF_CODE.4m.fd": "/usr/share/edk2/x64/OVMF_VARS.4m.fd",
    "/usr/share/qemu/OVMF.fd": "/usr/share/qemu/OVMF_VARS.fd",
    "/usr/share/qemu/ovmf-x86_64-code.bin": "/usr/share/qemu/ovmf-x86_64-vars.bin",
    "/usr/share/qemu/ovmf-x86_64-ms-code.bin": "/usr/share/qemu/ovmf-x86_64-ms-vars.bin",
    "/usr/share/qemu/ovmf-x86_64-ms-4m-code.bin": "/usr/share/qemu/ovmf-x86_64-ms-4m-vars.bin",
    "/run/libvirt/nix-ovmf/OVMF_CODE.fd": "/run/libvirt/nix-ovmf/OVMF_VARS.fd",
    "/run/libvirt/nix-ovmf/OVMF_CODE_4M.fd": "/run/libvirt/nix-ovmf/OVMF_VARS_4M.fd",
    "/usr/share/AAVMF/AAVMF_CODE.fd": "/usr/share/AAVMF/AAVMF_VARS.fd",
    "/usr/share/AAVMF/AAVMF_CODE_4M.fd": "/usr/share/AAVMF/AAVMF_VARS_4M.fd",
    "/usr/share/edk2/aarch64/QEMU_EFI.fd": "/usr/share/edk2/aarch64/QEMU_VARS.fd",
    "/usr/share/edk2/aarch64/OVMF_CODE.fd": "/usr/share/edk2/aarch64/OVMF_VARS.fd",
    "/usr/share/qemu/aavmf-aarch64-code.bin": "/usr/share/qemu/aavmf-aarch64-vars.bin",
    "/run/libvirt/nix-ovmf/AAVMF_CODE.fd": "/run/libvirt/nix-ovmf/AAVMF_VARS.fd",
    "/run/libvirt/nix-ovmf/QEMU_EFI.fd": "/run/libvirt/nix-ovmf/QEMU_VARS.fd",
}


def _probe_linux_bios(arch: str, predefined: str | None) -> str:
    if predefined:
        return predefined

    if arch == "aarch64":
        candidates = [
            "/usr/share/AAVMF/AAVMF_CODE.fd",
            "/usr/share/AAVMF/AAVMF_CODE_4M.fd",
            "/usr/share/edk2/aarch64/QEMU_EFI.fd",
            "/usr/share/edk2/aarch64/OVMF_CODE.fd",
            "/usr/share/qemu/aavmf-aarch64-code.bin",
            "/run/libvirt/nix-ovmf/AAVMF_CODE.fd",
            "/run/libvirt/nix-ovmf/QEMU_EFI.fd",
        ]
    elif arch == "x86_64":
        candidates = [
            "/usr/share/OVMF/OVMF_CODE.fd",
            "/usr/share/OVMF/OVMF_CODE_4M.fd",
            "/usr/share/ovmf/OVMF.fd",
            "/usr/share/edk2/ovmf/OVMF_CODE.fd",
            "/usr/share/edk2/x64/OVMF_CODE.4m.fd",
            "/usr/share/qemu/OVMF.fd",
            "/usr/share/qemu/ovmf-x86_64-code.bin",
            "/usr/share/qemu/ovmf-x86_64-ms-code.bin",
            "/usr/share/qemu/ovmf-x86_64-ms-4m-code.bin",
            "/run/libvirt/nix-ovmf/OVMF_CODE.fd",
            "/run/libvirt/nix-ovmf/OVMF_CODE_4M.fd",
        ]
    else:
        raise RuntimeError(f"Unsupported architecture: {arch}")

    bios = _first_existing_path(candidates)
    if bios is None:
        checked = "\n  ".join(candidates)
        raise RuntimeError(
            f"Could not find QEMU firmware.\nChecked:\n  {checked}\nInstall OVMF/AAVMF firmware or set qemu_bios."
        )

    return bios


def _probe_linux_vars_template(bios_code: str) -> str | None:
    template = LINUX_VARS_MAP.get(bios_code)
    if template and Path(template).exists():
        return template
    return None


def _ensure_linux_vars(settings: Settings, vars_template: str) -> Path:
    vars_path = settings.disk_dir / "OVMF_VARS.fd"
    if not vars_path.exists():
        info(f"Creating per-VM EFI VARS from {vars_template}…")
        shutil.copy(vars_template, vars_path)
    return vars_path


def _probe_freebsd_bios(arch: str, predefined: str | None) -> str:
    if predefined:
        return predefined

    if arch == "x86_64":
        candidates = [
            "/usr/local/share/edk2-qemu/QEMU_UEFI-x86_64.fd",
            "/usr/local/share/edk2-qemu/QEMU_UEFI_CODE-x86_64.fd",
        ]
    elif arch == "aarch64":
        candidates = ["/usr/local/share/qemu/edk2-aarch64-code.fd"]
    else:
        raise RuntimeError(f"Unsupported architecture: {arch}")

    bios = _first_existing_path(candidates)
    if bios is None:
        checked = "\n  ".join(candidates)
        raise RuntimeError(f"Could not find QEMU firmware.\nChecked:\n  {checked}\nInstall qemu or set qemu_bios.")

    return bios


def _probe_bios(system: str, arch: str, predefined: str | None) -> str:
    if system == "darwin":
        return _probe_darwin_bios(arch, predefined=predefined)
    if system == "linux":
        return _probe_linux_bios(arch, predefined=predefined)
    if system == "freebsd":
        return _probe_freebsd_bios(arch, predefined=predefined)

    raise RuntimeError(f"Unsupported host OS: {system}")


def _supports_9p(qemu_bin: str, arch: str) -> bool:
    help_text = _qemu_help_text(qemu_bin, "-help")
    if "-fsdev" not in help_text:
        return False

    device_help = _qemu_help_text(qemu_bin, "-device", "help")
    needed = f"virtio-9p-{_virtio_suffix_for_arch(arch)}"

    return needed in device_help


def _default_smp() -> int:
    count = os.cpu_count() or 1
    if count <= 2:
        return 1
    return min(max(2, count // 2), 8)


def detect_qemu_features(settings: Settings) -> QemuFeatures:
    system = platform.system().lower()
    machine = _normalize_machine(platform.machine())

    if system not in {"darwin", "linux", "freebsd"}:
        raise RuntimeError("Your platform is not supported yet")

    arch = _qemu_arch_for_host(machine)
    qemu_bin = _require_qemu_bin(arch)
    accel = _accel_chain_for_host(system)
    cpu = _pick_cpu(accel)
    bios = _probe_bios(system, arch, predefined=settings.qemu_bios)
    machine_type = _default_machine_for_arch(arch)
    virtio_suffix = _virtio_suffix_for_arch(arch)
    display = _pick_display(system, qemu_bin)
    supports_9p = _supports_9p(qemu_bin, arch)

    bios_vars: str | None = None
    if system == "linux":
        vars_template = _probe_linux_vars_template(bios)
        if vars_template:
            bios_vars = str(_ensure_linux_vars(settings, vars_template))

    return QemuFeatures(
        qemu_bin=qemu_bin,
        arch=arch,
        machine=machine_type,
        accel=accel,
        cpu=cpu,
        bios=bios,
        bios_vars=bios_vars,
        virtio_suffix=virtio_suffix,
        display=display,
        supports_9p=supports_9p,
    )


def parse_size(value: str) -> int:
    units = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    v = value.strip().upper()
    if v[-1].isdigit():
        return int(v)

    return int(float(v[:-1]) * units[v[-1]])


def build_netdev_arg(hostfwd: list[QemuFwd], *, ssh_host: str, ssh_port: int) -> str:
    parts = ["user", "id=net0", f"hostfwd=tcp:{ssh_host}:{ssh_port}-:22"]
    for rule in hostfwd:
        parts.append(f"hostfwd={rule.proto}:{ssh_host}:{rule.host}-:{rule.guest}")

    return ",".join(parts)


def build_share_args(shares: list[QemuShare], *, features: QemuFeatures) -> list[str]:
    if not shares:
        return []

    if not features.supports_9p:
        raise RuntimeError(
            "This QEMU build/host does not appear to support 9p shared folders "
            f"(qemu={features.qemu_bin}, arch={features.arch})."
        )

    args: list[str] = []
    for share in shares:
        args += [
            "-fsdev",
            f"local,id={share.id},path={share.host},security_model=none,readonly=off",
            "-device",
            f"virtio-9p-{features.virtio_suffix},fsdev={share.id},mount_tag={share.mount_tag}",
        ]
    return args


def disk_size_bytes(path: Path) -> int:
    out = subprocess.run(
        ["qemu-img", "info", "--output=json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(loads(out.stdout)["virtual-size"])


def build_qemu_cmd(
    state: State,
    *,
    settings: Settings,
    mode: QemuMode,
    features: QemuFeatures | None = None,
) -> list[str]:
    if state.ssh_port is None:
        raise RuntimeError("state.ssh_port is not set")

    image_xz = Path(str(settings.bsd_image_url)).name
    disk_path = settings.disk_dir / Path(image_xz).with_suffix("")
    cloud_iso = settings.cloud_dir / "cloud-init.iso"

    if features is None:
        features = detect_qemu_features(settings)

    hostfwd = derive_qemu_fwds(state=state)
    shares = derive_qemu_shares(state)

    netdev = build_netdev_arg(hostfwd=hostfwd, ssh_host=settings.vm_host, ssh_port=state.ssh_port)
    share_args = build_share_args(shares, features=features)
    smp = settings.qemu_cpus or _default_smp()

    cmd = [
        features.qemu_bin,
        "-m",
        settings.qemu_memory,
        "-smp",
        str(smp),
        "-M",
        f"{features.machine},accel={features.accel}",
    ]

    if features.bios_vars:
        cmd += [
            "-drive",
            f"if=pflash,format=raw,unit=0,readonly=on,file={features.bios}",
            "-drive",
            f"if=pflash,format=raw,unit=1,file={features.bios_vars}",
        ]
    else:
        cmd += ["-bios", features.bios]

    cmd += [
        "-device",
        f"virtio-net-{features.virtio_suffix},netdev=net0",
        "-netdev",
        netdev,
        "-drive",
        f"if=virtio,file={disk_path},format=raw,cache=writethrough",
        "-drive",
        f"file={cloud_iso},media=cdrom",
        *share_args,
    ]

    if features.cpu is not None:
        cmd.extend(["-cpu", features.cpu])

    if mode == QemuMode.SERVER:
        cmd.extend(["-display", "none"])
    elif mode == QemuMode.TTY:
        cmd.extend(["-nographic", "-serial", "mon:stdio"])
    elif mode == QemuMode.GRAPHIC:
        cmd.extend(
            [
                "-display",
                features.display,
                "-device",
                "ramfb",
                "-device",
                "qemu-xhci",
                "-device",
                "usb-kbd",
                "-device",
                "usb-tablet",
            ]
        )

    return cmd


def launch_vm(state: State, *, mode: QemuMode, settings: Settings) -> int | None:
    if state.ssh_port is None:
        raise RuntimeError("state.ssh_port is not set")

    features = detect_qemu_features(settings)
    cmd = build_qemu_cmd(state=state, mode=mode, settings=settings, features=features)

    if mode in {QemuMode.TTY, QemuMode.GRAPHIC}:
        info(f"Starting VM in {mode} mode…")
        settings.pid_file.unlink(missing_ok=True)
        subprocess.run(cmd, check=False)
        return None

    log_file = settings.log_dir / "qemu.log"
    info("Starting VM in background…")

    with open(log_file, "ab") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True)

    settings.pid_file.write_text(str(proc.pid))

    try:
        proc.wait(timeout=3)
        settings.pid_file.unlink(missing_ok=True)
        raise RuntimeError(f"QEMU process {proc.pid} exited immediately — check {log_file}")
    except subprocess.TimeoutExpired:
        pass

    ok(f"VM started on {settings.vm_host}:{state.ssh_port} (pid {proc.pid}).")
    return proc.pid


def prepare_disk(settings: Settings) -> None:
    download(
        bsd_image_url=str(settings.bsd_image_url),
        bsd_image_checksum_url=str(settings.bsd_image_checksum_url),
        target_dir=settings.disk_dir,
    )

    image_xz = Path(str(settings.bsd_image_url)).name
    disk_path = settings.disk_dir / Path(image_xz).with_suffix("")
    xz_path = settings.disk_dir / image_xz

    if disk_path.exists():
        return

    info("Decompressing image…")
    subprocess.run(["xz", "-dk", str(xz_path)], check=True)

    target = parse_size(settings.qemu_disk_size)
    current = disk_size_bytes(disk_path)

    prepare_cloud_init(settings)
    build_cloud_iso(settings)

    if current < target:
        info(f"Resizing disk to {settings.qemu_disk_size}…")
        subprocess.run(
            ["qemu-img", "resize", "-f", "raw", str(disk_path), settings.qemu_disk_size],
            check=True,
        )


def vm_is_running(pid_file: Path) -> tuple[bool, int | None]:
    if not pid_file.exists():
        return False, None

    pid = int(pid_file.read_text().strip())

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return False, None
    except PermissionError:
        return True, pid

    try:
        out = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm="],
            capture_output=True,
            text=True,
        )
        if "qemu" not in out.stdout.lower():
            pid_file.unlink(missing_ok=True)
            return False, None
    except Exception:
        pass

    return True, pid


def prepare_cloud_init(settings: Settings) -> None:
    ssh_key = ensure_vm_key(
        private_key=settings.ssh_dir / settings.ssh_key,
        public_key=settings.ssh_dir / f"{settings.ssh_key}.pub",
    )
    env = build_jinja_env()

    user_data = env.get_template("cloud_user_data.j2").render(ssh_key=ssh_key)
    meta_data = env.get_template("cloud_meta_data.j2").render()

    (settings.cloud_dir / "user-data").write_text(f"#cloud-config\n{user_data}")
    (settings.cloud_dir / "meta-data").write_text(meta_data)


def build_cloud_iso(settings: Settings) -> None:
    iso = settings.cloud_dir / "cloud-init.iso"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        shutil.copy(settings.cloud_dir / "user-data", tmp_path)
        shutil.copy(settings.cloud_dir / "meta-data", tmp_path)
        subprocess.run(
            ["mkisofs", "-output", str(iso), "-volid", "cidata", "-joliet", "-rock", str(tmp_path)],
            check=True,
        )
