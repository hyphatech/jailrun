from typing import NamedTuple

import questionary
from rich.console import Console

CYAN = "#00aaaa"


class Command(NamedTuple):
    name: str
    desc: str
    danger: bool = False


COMMANDS: list[Command] = [
    Command("start", "Boot the VM"),
    Command("stop", "Gracefully shut down the VM", danger=True),
    Command("ssh", "Open a shell in the VM or a jail"),
    Command("cmd", "Execute a command inside a jail"),
    Command("up", "Create or update jails from config"),
    Command("down", "Stop and destroy jails", danger=True),
    Command("pause", "Stop jails without destroying them"),
    Command("snapshot", "Manage jail snapshots"),
    Command("purge", "Destroy the VM and ALL jails", danger=True),
    Command("status", "Show VM and jail status"),
    Command("pair", "Connect to another Jailrun"),
]


def con() -> Console:
    return Console()


def ok(msg: str) -> None:
    con().print(f"[bold green]✓[/bold green] {msg}\n")


def warn(msg: str) -> None:
    con().print(f"[yellow]![/yellow] [dim]{msg}[/dim]\n")


def err(msg: str) -> None:
    con().print(f"[bold red]✗[/bold red] {msg}\n")


def info(msg: str) -> None:
    con().print(f"[dim]> {msg}[/dim]")


def nl() -> None:
    con().print()


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
