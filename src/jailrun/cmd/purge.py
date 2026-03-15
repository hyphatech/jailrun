import shutil
from pathlib import Path

from jailrun.cmd.stop import stop_vm
from jailrun.misc import lock
from jailrun.settings import Settings
from jailrun.ui import info, ok


def purge(settings: Settings) -> None:
    with lock(settings.state_file):
        _purge(settings=settings)


def _purge(settings: Settings) -> None:
    stop_vm(settings)

    image_xz = Path(str(settings.bsd_image_url)).name

    paths = [
        settings.state_file,
        settings.disk_dir / Path(image_xz).with_suffix(""),
        settings.disk_dir / "OVMF_VARS.fd",
        settings.cloud_dir / "cloud-init.iso",
        settings.playbook_cache_dir,
    ]

    for p in paths:
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()

            info(f"Removed {p.name}")

    ok("Purge complete.")
