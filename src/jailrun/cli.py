from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Annotated

import click
import questionary
import typer
import typer.main as typer_main
from rich.table import Table
from rich.text import Text
from typer.core import TyperGroup

from jailrun import cmd, shell
from jailrun.config import load_state
from jailrun.qemu import QemuMode
from jailrun.settings import settings
from jailrun.ui import COMMANDS, Q_STYLE, con, warn


def _get_version() -> str:
    try:
        return pkg_version("jailrun")
    except Exception:
        return "dev"


def _print_help(version: str) -> None:
    c = con()
    c.print()

    logo = Text()
    logo.append("█ ", style="bold cyan")
    logo.append("jrun", style="bold white")
    logo.append(f"  {version}", style="dim white")

    c.print(logo)
    c.print()
    c.print(Text("  Effortless orchestration for FreeBSD jails", style="dim white"))
    c.print()

    tbl = Table.grid(padding=(0, 4))
    tbl.add_column(no_wrap=True, min_width=10)
    tbl.add_column(style="dim white")

    for cmd_ in COMMANDS:
        style = "bold red" if cmd_.danger else "bold cyan"
        tbl.add_row(Text(f"  {cmd_.name}", style=style), cmd_.desc)

    c.print(tbl)

    c.print()
    c.print(Text("  Run jrun with no arguments to enter the interactive shell.", style="dim cyan"))
    c.print()

    otbl = Table.grid(padding=(0, 4))
    otbl.add_column(style="bold cyan", no_wrap=True)
    otbl.add_column(style="dim cyan", no_wrap=True)
    otbl.add_column(style="dim white")
    otbl.add_row("  --version", "-v", "Print version and exit")
    otbl.add_row("  --help", "-h", "Show this message")

    c.print(otbl)
    c.print()


class BannerTyperGroup(TyperGroup):
    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        if ctx.parent is None:
            _print_help(_get_version())
        else:
            super().format_help(ctx, formatter)


app = typer.Typer(
    cls=BannerTyperGroup,
    no_args_is_help=False,
    rich_markup_mode="rich",
)


def _confirm_destructive(action: str, target: str, *, yes: bool) -> None:
    if yes:
        return

    answer = questionary.confirm(
        f"This will {action} {target}. Continue?",
        default=False,
        style=Q_STYLE,
    ).ask()

    if not answer:
        warn("Aborted.")
        raise typer.Exit(0)


@app.command()
def start(
    base: Path | None = typer.Option(None, "--base", "-b", help="Path to base.ucl"),
    mode: QemuMode = typer.Option(QemuMode.SERVER, "--mode", "-m", help="VM mode"),
    provision: bool = typer.Option(False, "--provision", help="Run base provision"),
) -> None:
    """Boot the VM, applying base config if provided."""
    state = load_state(settings.state_file)
    cmd.start(base_config=base, state=state, settings=settings, provision=provision, mode=mode)


@app.command()
def stop(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Gracefully shut down the VM."""
    _confirm_destructive("stop", "the VM", yes=yes)
    cmd.stop(settings)


@app.command()
def ssh(
    jail_name: str | None = typer.Argument(None, help="Jail name (default: host VM)"),
) -> None:
    """Open an interactive SSH session to the VM or a jail."""
    state = load_state(settings.state_file)
    cmd.ssh(state=state, settings=settings, jail_name=jail_name)


@app.command(name="cmd", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run_cmd(
    ctx: typer.Context,
    jail_name: str = typer.Argument(..., help="Jail name"),
    executable: str = typer.Argument(..., help="Command to execute"),
) -> None:
    """Execute a command inside a jail."""
    state = load_state(settings.state_file)
    cmd.run_cmd(state=state, settings=settings, jail_name=jail_name, cmd=[executable, *ctx.args])


@app.command()
def up(
    config: Path | None = typer.Argument(None, help="Path to jail config (.ucl)"),
    names: list[str] | None = typer.Argument(None, help="Jail names (default: all)"),
) -> None:
    """Create or update jails from a config file."""
    if config is None:
        warn("Config file required. Run 'jrun' for interactive mode.")
        raise typer.Exit(1)

    state = load_state(settings.state_file)
    cmd.up(config=config, state=state, settings=settings, names=names)


@app.command()
def down(
    names: list[str] | None = typer.Argument(
        None,
        help="Jail names to destroy",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation.",
    ),
) -> None:
    """Stop and destroy jails."""
    if not names:
        warn("Jail names required. Run 'jrun' for interactive mode.")
        raise typer.Exit(1)

    _confirm_destructive("destroy", ", ".join(names), yes=yes)

    state = load_state(settings.state_file)
    cmd.down(state=state, settings=settings, names=names)


@app.command()
def pause(
    names: list[str] | None = typer.Argument(
        None,
        help="Jail names to pause",
    ),
) -> None:
    """Stop running jails without destroying them."""
    if not names:
        warn("Jail names required. Run 'jrun' for interactive mode.")
        raise typer.Exit(1)

    state = load_state(settings.state_file)
    cmd.pause(state=state, settings=settings, names=names)


@app.command()
def purge(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Stop and destroy the VM with [bold red]all[/bold red] jails."""
    _confirm_destructive("destroy", "the VM and ALL jails", yes=yes)
    cmd.purge(settings=settings)


@app.command()
def status(
    tree: bool = typer.Option(False, "--tree", "-t", help="Show as tree instead of table."),
) -> None:
    """Show VM and jail status."""
    state = load_state(settings.state_file)
    cmd.status(state=state, settings=settings, tree=tree)


@app.command()
def pair(
    code: str | None = typer.Argument(None, help="Pairing code (omit to create new)"),
    list_peers: bool = typer.Option(False, "--list", "-l", help="Show paired instances"),
    drop: str | None = typer.Option(None, "--drop", help="Remove a paired instance by name"),
) -> None:
    """Pair with another jailrun instance over the mesh network."""
    state = load_state(settings.state_file)

    if list_peers:
        cmd.pair_list(state=state)
        return

    if drop is not None:
        cmd.pair_remove(alias=drop, state=state, settings=settings)
        return

    if code is None:
        cmd.pair_create(state=state, settings=settings)
    else:
        cmd.pair_join(code=code, state=state, settings=settings)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"jrun {_get_version()}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Print version.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Run without arguments for the interactive shell."""
    if ctx.invoked_subcommand is None:
        shell.run(
            settings=settings,
            version=_get_version(),
            state_loader=lambda: load_state(settings.state_file),
            click_app=typer_main.get_command(app),  # type: ignore[arg-type]
        )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
