import signal
from pathlib import Path

import questionary
import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from questionary import Choice, Separator
from rich.table import Table
from rich.text import Text

from jailrun import cmd
from jailrun.cmd.status import RawJail, get_bastille_jails
from jailrun.qemu import QemuMode, vm_is_running
from jailrun.settings import Settings
from jailrun.ssh import get_ssh_kw
from jailrun.ui import COMMANDS, Q_STYLE, con, pick_config, pick_jails_from_config, warn

_SHELL_COMMANDS = [
    ("help", "Show available commands", False),
    ("exit", "Quit", False),
]

_ALIASES: dict[str, str] = {"?": "help", "quit": "exit", "q": "exit"}


PT_STYLE = Style.from_dict(
    {
        "prompt": "ansicyan bold",
        "rprompt": "ansibrightblack",
    }
)


def _command_table(include_shell_extras: bool = False) -> Table:
    tbl = Table.grid(padding=(0, 4))
    tbl.add_column(no_wrap=True, min_width=10)
    tbl.add_column(style="dim white")

    for cmd_ in COMMANDS:
        style = "bold red" if cmd_.danger else "bold cyan"
        tbl.add_row(Text(f"  {cmd_.name}", style=style), cmd_.desc)

    if include_shell_extras:
        for name, desc, danger in _SHELL_COMMANDS:
            style = "bold red" if danger else "bold cyan"
            tbl.add_row(Text(f"  {name}", style=style), desc)

    return tbl


def _print_welcome(version: str) -> None:
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
    c.print(_command_table(include_shell_extras=False))
    c.print()
    c.print(
        Text(
            "  Tab · /  browse    ↑↓  history    ?  help    Ctrl-C  exit",
            style="dim cyan",
        )
    )
    c.print()


def _print_help() -> None:
    c = con()
    c.print()
    c.print(_command_table(include_shell_extras=True))
    c.print()


def _nl() -> None:
    con().print()


def _aborted() -> None:
    warn("Aborted.")


def _confirm_destructive(action: str) -> bool:
    _nl()
    answer = questionary.confirm(
        f"This will {action}. Continue?",
        default=False,
        style=Q_STYLE,
    ).ask()
    _nl()
    return bool(answer)


def _fetch_live_jails(settings: Settings) -> list[RawJail]:
    try:
        ssh_kw = get_ssh_kw(settings)
        return get_bastille_jails(**ssh_kw)
    except Exception:
        return []


def _pick_jail_interactively(settings: Settings) -> str | None:
    with con().status("[dim]Fetching jail list…[/dim]", spinner="dots"):
        jails = _fetch_live_jails(settings)

    _nl()

    choices: list[Choice] = []
    if jails:
        max_name = max(len(j["name"]) for j in jails)
        for j in jails:
            state_col = "up" if j["state"].lower() == "up" else j["state"].lower()
            label = f"{j['name'].ljust(max_name)}   {state_col}   {j['ip']}"
            choices.append(Choice(label, value=j["name"]))

        choices.append(Separator())

    choices += [
        Choice("Host VM", value="__host__"),
        Separator(),
        Choice("Cancel", value="__cancel__"),
    ]

    chosen = questionary.select(
        "SSH into:",
        choices=choices,
        style=Q_STYLE,
    ).ask()

    _nl()

    if chosen is None:
        raise typer.Abort()
    if chosen == "__cancel__":
        raise typer.Abort()
    if chosen == "__host__":
        return None

    return str(chosen)


def _is_vm_running(settings: Settings) -> bool:
    alive, _ = vm_is_running(settings.pid_file)
    return alive


def _offer_start_vm(settings: Settings) -> bool:
    _nl()
    answer = questionary.confirm(
        "VM is not running. Boot it now?",
        default=True,
        style=Q_STYLE,
    ).ask()
    _nl()

    if not answer:
        return False

    cmd.start_vm(base=None, settings=settings, mode=QemuMode.SERVER)

    return True


def _dispatch(token: str, inline_args: list[str], settings: Settings) -> bool:
    c = token.strip().lower()
    c = _ALIASES.get(c, c)

    if c in ("exit", "quit", "q"):
        return False

    if c == "help":
        _print_help()
        return True

    if c == "status":
        tree = "--tree" in inline_args or "-t" in inline_args
        cmd.status(settings, tree=tree)
        return True

    if c == "start":
        base: Path | None = None
        if not inline_args:
            _nl()
            if questionary.confirm(
                "Use a custom base.ucl config?",
                default=False,
                style=Q_STYLE,
            ).ask():
                _nl()
                raw = questionary.path("Path to base.ucl:", style=Q_STYLE).ask()
                base = Path(raw) if raw else None
            _nl()

        cmd.start_vm(base=base, settings=settings, mode=QemuMode.SERVER)

        return True

    if c == "stop":
        if not _confirm_destructive("stop the VM"):
            _aborted()
            return True

        cmd.stop_vm(settings)

        return True

    if c == "ssh":
        if inline_args:
            cmd.ssh(settings, jail_name=inline_args[0])
        else:
            if not _is_vm_running(settings):
                _offer_start_vm(settings)
                return True

            jail_name = _pick_jail_interactively(settings)
            cmd.ssh(settings, jail_name=jail_name)

        return True

    if c == "up":
        config = Path(inline_args[0]) if inline_args else pick_config()
        if config is None:
            _aborted()
            return True

        names = pick_jails_from_config(config)
        _nl()
        cmd.up(config=config, base=None, mode=QemuMode.SERVER, names=names, settings=settings)

        return True

    if c == "down":
        config = Path(inline_args[0]) if inline_args else pick_config()
        if config is None:
            _aborted()
            return True

        names = pick_jails_from_config(config)
        _nl()
        target = f"jails in {config.name}" if not names else ", ".join(names)

        if not _confirm_destructive(f"destroy {target}"):
            _aborted()
            return True

        cmd.down(config=config, names=names, settings=settings)

        return True

    if c == "pause":
        config = Path(inline_args[0]) if inline_args else pick_config()
        if config is None:
            _aborted()
            return True

        names = pick_jails_from_config(config)
        _nl()
        cmd.pause(config=config, names=names, settings=settings)

        return True

    if c == "purge":
        if not _confirm_destructive("destroy the VM and ALL jails"):
            _aborted()
            return True

        cmd.purge(settings=settings)

        return True

    con().print(
        f"\n  [bold red]unknown command:[/bold red] [cyan]{c}[/cyan]"
        "  —  type [bold]?[/bold] for help or Tab to browse\n"
    )
    return True


def run(settings: Settings, version: str = "dev") -> None:
    """Start the interactive shell."""
    _print_welcome(version)

    completer = NestedCompleter.from_nested_dict(
        {
            "status": {"--tree": None},
            "start": None,
            "stop": None,
            "ssh": None,
            "up": None,
            "down": None,
            "pause": None,
            "purge": None,
            "help": None,
            "exit": None,
        }
    )

    kb = KeyBindings()

    @kb.add("/")
    def _slash(event) -> None:  # type: ignore[no-untyped-def]
        buf = event.current_buffer
        if buf.text == "":
            buf.start_completion(select_first=False)
        else:
            buf.insert_text("/")

    def _on_resize(sig: int, frame: object) -> None:  # noqa: ARG001
        _print_welcome(version)

    signal.signal(signal.SIGWINCH, _on_resize)

    session: PromptSession[str] = PromptSession(
        history=InMemoryHistory(),
        completer=completer,
        key_bindings=kb,
        style=PT_STYLE,
        complete_while_typing=False,
        mouse_support=False,
    )

    while True:
        try:
            raw = session.prompt(HTML("<ansicyan><b>jrun</b></ansicyan> <ansibrightblack>›</ansibrightblack> "))
        except KeyboardInterrupt:
            con().print()
            con().print("[dim]  Bye![/dim]\n")
            break
        except EOFError:
            con().print("[dim]\n  Bye![/dim]\n")
            break

        parts = raw.strip().split()
        if not parts:
            continue

        if parts[0] == "?":
            parts[0] = "help"

        try:
            keep_going = _dispatch(parts[0], parts[1:], settings)
        except (typer.Exit, typer.Abort):
            keep_going = True
        except Exception as exc:  # noqa: BLE001
            con().print(f"\n  [bold red]error:[/bold red] {exc}\n")
            keep_going = True

        if not keep_going:
            con().print("[dim]  Bye.[/dim]\n")
            break
