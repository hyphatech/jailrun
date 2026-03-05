from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Annotated

import click
import typer
from typer.core import TyperGroup

from jailrun import cmd
from jailrun.misc import exclusive
from jailrun.qemu import QemuMode
from jailrun.settings import settings

ASCII_BANNER = r"""
     ██╗██████╗ ██╗   ██╗███╗   ██╗
     ██║██╔══██╗██║   ██║████╗  ██║
     ██║██████╔╝██║   ██║██╔██╗ ██║
██   ██║██╔══██╗██║   ██║██║╚██╗██║
╚█████╔╝██║  ██║╚██████╔╝██║ ╚████║
 ╚════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝
"""


class BannerTyperGroup(TyperGroup):
    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        if ctx.parent is None:
            click.echo(ASCII_BANNER)
        return super().format_help(ctx, formatter)


app = typer.Typer(
    cls=BannerTyperGroup,
    no_args_is_help=True,
)


@app.command()
@exclusive(settings.state_file)
def start(
    base: Path | None = typer.Option(None, "--base", "-b", help="Path to base.ucl"),
    mode: QemuMode = typer.Option(QemuMode.SERVER, "--mode", "-m", help="VM mode"),
) -> None:
    """Boot the VM, applying base config if provided."""
    cmd.start_vm(base=base, settings=settings, mode=mode)


@app.command()
@exclusive(settings.state_file)
def stop() -> None:
    """Gracefully shut down the VM."""
    cmd.stop_vm(settings)


@app.command()
def ssh(
    jail_name: str | None = typer.Argument(None, help="Jail name to SSH into (default: host VM)"),
) -> None:
    """Open an interactive SSH session to the VM or a jail."""
    cmd.ssh(settings, jail_name=jail_name)


@app.command()
@exclusive(settings.state_file)
def up(
    config: Path = typer.Argument(..., help="Path to jail config (.ucl)"),
    names: list[str] | None = typer.Argument(None, help="Jail names (default: all in config)"),
    base: Path | None = typer.Option(None, "--base", "-b", help="Path to base.ucl"),
    mode: QemuMode = typer.Option(QemuMode.SERVER, "--mode", "-m", help="VM mode"),
) -> None:
    """Create or update jails from a config file."""
    cmd.up(config=config, base=base, mode=mode, names=names, settings=settings)


@app.command()
@exclusive(settings.state_file)
def down(
    config: Path = typer.Argument(..., help="Path to jail config (.ucl)"),
    names: list[str] | None = typer.Argument(None, help="Jail names (default: all in config)"),
) -> None:
    """Stop and destroy jails."""
    cmd.down(config=config, names=names, settings=settings)


@app.command()
@exclusive(settings.state_file)
def pause(
    config: Path = typer.Argument(..., help="Path to jail config (.ucl)"),
    names: list[str] | None = typer.Argument(None, help="Jail names (default: all in config)"),
) -> None:
    """Stop jails without destroying them."""
    cmd.pause(config=config, names=names, settings=settings)


@app.command()
@exclusive(settings.state_file)
def purge() -> None:
    """Stop and destroy the VM with all jails."""
    cmd.purge(settings=settings)


@app.command()
def status(
    tree: bool = typer.Option(False, "--tree", "-t", help="Show status as a tree instead of a table."),
) -> None:
    """Show VM and jail status."""
    cmd.status(settings, tree=tree)


def _get_version() -> str:
    try:
        return pkg_version("jailrun")
    except Exception:
        return "dev"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"jrun {_get_version()}")
        raise typer.Exit()


@app.callback()
def version(
    version: Annotated[
        bool, typer.Option("--version", "-v", help="Current version.", callback=_version_callback, is_eager=True)
    ] = False,
) -> None:
    pass


def main() -> None:
    app()


if __name__ == "__main__":
    main()
