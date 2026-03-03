from pathlib import Path

import typer

from jailrun.cmd.stop import stop_vm
from jailrun.settings import Settings


def purge(settings: Settings) -> None:
    typer.confirm("This will delete all running jails. Continue?", abort=True)
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
            typer.echo(f"Removed {p.name}")

    typer.secho("✅ Purge complete.", fg=typer.colors.GREEN)
