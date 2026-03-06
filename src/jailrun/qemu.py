import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from jailrun.config import derive_qemu_fwds, derive_qemu_shares
from jailrun.http import download
from jailrun.schemas import QemuFwd, QemuShare, State
from jailrun.serializers import loads
from jailrun.settings import Settings
from jailrun.ssh import ensure_vm_key
from jailrun.templates import build_jinja_env
from jailrun.ui import info, ok


@dataclass(frozen=True)
class QemuFeatures:
    arch: str
    machine: str
    accel: str
    bios: str
    virtio_suffix: str
    display: str


class QemuMode(StrEnum):
    SERVER = "server"
    TTY = "tty"
    GRAPHIC = "graphic"


def detect_qemu_features() -> QemuFeatures:
    system = platform.system().lower()
    machine = platform.machine()

    if system == "darwin":
        if machine == "arm64":
            return QemuFeatures(
                arch="aarch64",
                machine="virt",
                accel="hvf",
                bios="edk2-aarch64-code.fd",
                virtio_suffix="device",
                display="cocoa",
            )
        return QemuFeatures(
            arch="x86_64",
            machine="q35",
            accel="hvf",
            bios="/usr/local/share/qemu/edk2-x86_64-code.fd",
            virtio_suffix="pci",
            display="cocoa",
        )

    if machine == "aarch64":
        return QemuFeatures(
            arch="aarch64",
            machine="virt",
            accel="kvm",
            bios="/usr/share/AAVMF/AAVMF_CODE.fd",
            virtio_suffix="device",
            display="gtk",
        )

    return QemuFeatures(
        arch="x86_64",
        machine="q35",
        accel="kvm",
        bios="/usr/share/OVMF/OVMF_CODE.fd",
        virtio_suffix="pci",
        display="gtk",
    )


def parse_size(value: str) -> int:
    units = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    v = value.strip().upper()
    if v[-1].isdigit():
        return int(v)
    return int(float(v[:-1]) * units[v[-1]])


def build_netdev_arg(hostfwd: list[QemuFwd], *, default_ssh_port: int) -> str:
    parts = ["user", "id=net0", f"hostfwd=tcp:127.0.0.1:{default_ssh_port}-:22"]
    for rule in hostfwd:
        parts.append(f"hostfwd={rule.proto}:127.0.0.1:{rule.host}-:{rule.guest}")
    return ",".join(parts)


def build_share_args(shares: list[QemuShare], *, features: QemuFeatures) -> list[str]:
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


def build_qemu_cmd(state: State, *, settings: Settings, mode: QemuMode) -> list[str]:
    image_xz = Path(str(settings.bsd_image_url)).name
    disk_path = settings.disk_dir / Path(image_xz).with_suffix("")
    cloud_iso = settings.cloud_dir / "cloud-init.iso"

    features = detect_qemu_features()

    hostfwd = derive_qemu_fwds(state=state, default_ssh_port=settings.ssh_port)
    shares = derive_qemu_shares(state)

    netdev = build_netdev_arg(hostfwd=hostfwd, default_ssh_port=settings.ssh_port)
    share_args = build_share_args(shares, features=features)

    cmd = [
        f"qemu-system-{features.arch}",
        "-m",
        settings.qemu_memory,
        "-M",
        f"{features.machine},accel={features.accel}",
        "-cpu",
        "host",
        "-bios",
        features.bios,
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

    if mode == QemuMode.SERVER:
        cmd.extend(["-display", "none"])
    if mode == QemuMode.TTY:
        cmd.extend(["-nographic", "-serial", "mon:stdio"])
    if mode == QemuMode.GRAPHIC:
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
    cmd = build_qemu_cmd(state=state, mode=mode, settings=settings)

    if mode in {QemuMode.TTY, QemuMode.GRAPHIC}:
        info(f"Starting VM in {mode} mode.")
        settings.pid_file.unlink(missing_ok=True)
        subprocess.run(cmd, check=False)
        return None

    log_file = settings.log_dir / "qemu.log"
    info("Starting VM in background…")

    with open(log_file, "ab") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True)

    settings.pid_file.write_text(str(proc.pid))
    ok(f"VM started (pid {proc.pid}).")

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

    if not disk_path.exists():
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
