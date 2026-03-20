import os
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from jailrun import ROOT_DIR
from jailrun.misc import current_arch

STATE_DIR = Path.home() / ".jrun"

BASE_URL = "https://download.freebsd.org/releases/VM-IMAGES"


class Settings(BaseSettings):
    ssh_dir: Path = STATE_DIR / "ssh"
    log_dir: Path = STATE_DIR / "logs"
    disk_dir: Path = STATE_DIR / "disks"
    cloud_dir: Path = STATE_DIR / "cloud-init"
    playbook_cache_dir: Path = STATE_DIR / "playbooks"
    pid_file: Path = STATE_DIR / "vm.pid"

    vm_host: str = "127.0.0.1"
    vm_python_interpreter: str = "python3.13"

    ssh_port: int = 2222
    ssh_user: str = "admin"
    ssh_key: str = "id_ed25519"

    state_file: Path = STATE_DIR / "state.json"

    bsd_version: str = "15.0"
    bsd_release_tag: str = "RELEASE"
    bsd_arch: Literal["aarch64", "amd64"] = Field(default_factory=current_arch)

    mesh_network: bool = True
    relay_peer_uri: str = "relay.jail.run"
    relay_peer_port: int = 37100
    relay_pubkey: str = "3468e255ce164f8c2003b4dd965bd577f0e4e628df439b0cc38b167ab31996ee"

    debug: bool = False

    qemu_memory: str = "4096M"
    qemu_disk_size: str = "20G"
    qemu_cpus: int | None = None
    qemu_bios: str | None = None

    @computed_field
    def bsd_image_url(self) -> HttpUrl:
        image_suffix = "BASIC-CLOUDINIT-zfs.raw.xz"
        match self.bsd_arch:
            case "amd64":
                image_name = f"FreeBSD-{self.bsd_version}-{self.bsd_release_tag}-{self.bsd_arch}-{image_suffix}"
            case "aarch64":
                image_name = f"FreeBSD-{self.bsd_version}-{self.bsd_release_tag}-arm64-{self.bsd_arch}-{image_suffix}"

        return HttpUrl(f"{BASE_URL}/{self.bsd_version}-{self.bsd_release_tag}/{self.bsd_arch}/Latest/{image_name}")

    @computed_field
    def bsd_image_checksum_url(self) -> HttpUrl:
        return HttpUrl(f"{BASE_URL}/{self.bsd_version}-{self.bsd_release_tag}/{self.bsd_arch}/Latest/CHECKSUM.SHA512")

    model_config = SettingsConfigDict(
        env_file=os.getenv("JRUN_ENV_FILE", ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        env_prefix="JRUN_",
        env_nested_delimiter="__",
    )


settings = Settings()


for d in (settings.ssh_dir, settings.log_dir, settings.disk_dir, settings.cloud_dir, settings.playbook_cache_dir):
    d.mkdir(parents=True, exist_ok=True)
