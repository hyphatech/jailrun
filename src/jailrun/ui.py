from pathlib import Path
from typing import NamedTuple

import questionary
import typer
from questionary import Choice, Separator
from rich.console import Console

from jailrun import ucl

CYAN = "#00aaaa"


class Command(NamedTuple):
    name: str
    desc: str
    danger: bool = False


COMMANDS: list[Command] = [
    Command("start", "Boot the VM"),
    Command("stop", "Gracefully shut down the VM", danger=True),
    Command("ssh", "Open a shell in the VM or a jail"),
    Command("up", "Create or update jails from config"),
    Command("down", "Stop and destroy jails", danger=True),
    Command("pause", "Stop jails without destroying them"),
    Command("purge", "Destroy the VM and ALL jails", danger=True),
    Command("status", "Show VM and jail status"),
]


def con() -> Console:
    return Console()


def ok(msg: str) -> None:
    con().print(f"\n[bold green]✓[/bold green] {msg}\n")


def warn(msg: str) -> None:
    con().print(f"[yellow]![/yellow] [dim]{msg}[/dim]\n")


def err(msg: str) -> None:
    con().print(f"[bold red]✗[/bold red] {msg}\n")


def info(msg: str) -> None:
    con().print(f"[dim]{msg}[/dim]")


Q_STYLE = questionary.Style(
    [
        ("qmark", f"fg:{CYAN} bold"),
        ("question", "bold"),
        ("answer", f"fg:{CYAN} bold"),
        ("pointer", f"fg:{CYAN} bold"),
        ("highlighted", f"fg:{CYAN}"),
        ("selected", f"fg:{CYAN}"),
        ("separator", "fg:#444444"),
        ("instruction", "fg:#555555 italic"),
        ("text", ""),
        ("disabled", "fg:#555555 italic"),
    ]
)


def pick_config() -> Path:
    candidates = sorted(Path(".").glob("**/*.ucl"))
    con().print()

    if candidates:
        choices: list[Choice] = [Choice(str(p), value=p) for p in candidates]
        choices += [
            Separator(),
            Choice("Enter path manually…", value="__manual__"),
            Choice("Cancel", value="__cancel__"),
        ]
        chosen = questionary.select(
            "Select jail config:",
            choices=choices,
            style=Q_STYLE,
        ).ask()

        if chosen is None or chosen == "__cancel__":
            raise typer.Abort()

        if chosen == "__manual__":
            raw = questionary.path("Path to config (.ucl):", style=Q_STYLE).ask()
            if not raw:
                raise typer.Abort()
            return Path(raw)
        return Path(chosen)

    raw = questionary.path("Path to jail config (.ucl):", style=Q_STYLE).ask()
    if not raw:
        raise typer.Abort()

    return Path(raw)


def _parse_jail_names_from_ucl(config: Path) -> list[str]:
    ucl_config = ucl.load_file(str(config))
    if "jail" not in ucl_config:
        return []

    return list(ucl_config["jail"].keys())


def pick_jails_from_config(config: Path) -> list[str] | None:
    names = _parse_jail_names_from_ucl(config)

    scope = questionary.select(
        "Target which jails?",
        choices=[
            c
            for c in [
                Choice("All jails", value="__all__"),
                Choice("Choose specific…", value="__pick__") if names else None,
                Separator(),
                Choice("Cancel", value="__cancel__"),
            ]
            if c is not None
        ],
        style=Q_STYLE,
    ).ask()

    if scope is None or scope == "__cancel__":
        raise typer.Abort()
    if scope == "__all__":
        return None

    con().print()

    choices = [Choice(n, value=n, checked=False) for n in names]

    selected = questionary.checkbox(
        "Select jails:",
        choices=choices,
        style=Q_STYLE,
    ).ask()

    if selected is None or not selected:
        raise typer.Abort()

    return list(selected)
