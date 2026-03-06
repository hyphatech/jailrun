from pathlib import Path

from jailrun.cmd.stop import stop_vm
from jailrun.settings import Settings
from jailrun.ui import info, ok


def purge(settings: Settings) -> None:
    stop_vm(settings)

    image_xz = Path(str(settings.bsd_image_url)).name

    paths = [
        settings.state_file,
        settings.disk_dir / Path(image_xz).with_suffix(""),
        settings.cloud_dir / "cloud-init.iso",
    ]

    for p in paths:
        if p.exists():
            p.unlink()
            info(f"Removed {p.name}")

    ok("Purge complete.")
