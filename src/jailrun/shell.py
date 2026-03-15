import shlex
from collections.abc import Callable
from typing import Any

import click
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
from jailrun.network import get_ssh_kw
from jailrun.qemu import QemuMode, vm_is_running
from jailrun.schemas import State
from jailrun.settings import Settings
from jailrun.ui import COMMANDS, Q_STYLE, con, pick_config, pick_jails_from_config, warn

_SHELL_COMMANDS = [
    ("help", "Show available commands", False),
    ("exit", "Quit", False),
]

_ALIASES: dict[str, str] = {"?": "help", "quit": "exit", "q": "exit"}

PT_STYLE = Style.from_dict({"prompt": "ansicyan bold", "rprompt": "ansibrightblack"})


def _parse(click_app: click.Group, command: str, args: list[str]) -> dict[str, Any]:
    sub_cmd = click_app.commands.get(command)
    if sub_cmd is None:
        return {}
    try:
        with sub_cmd.make_context(command, list(args), resilient_parsing=True) as ctx:
            return dict(ctx.params)
    except Exception:  # noqa: BLE001
        return {}


def _invoke(click_app: click.Group, argv: list[str]) -> None:
    try:
        with click_app.make_context("jrun", argv) as ctx:
            click_app.invoke(ctx)
    except SystemExit:
        pass
    except click.exceptions.Abort:
        _nl()
    except click.exceptions.UsageError as exc:
        con().print(f"\n  [bold red]error:[/bold red] {exc}\n")


def _build_completer(click_app: click.Group) -> NestedCompleter:
    completions: dict[str, Any] = {}
    for name, sub in click_app.commands.items():
        opts = {
            opt: None
            for param in sub.params
            if isinstance(param, click.Option)
            for opt in param.opts
            if opt.startswith("--")
        }
        completions[name] = opts or None

    completions["help"] = None
    completions["?"] = None
    completions["exit"] = None

    return NestedCompleter.from_nested_dict(completions)


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
    c.print(Text("  Tab · /  browse    ↑↓  history    ?  help    Ctrl-C  exit", style="dim cyan"))
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


def _fetch_live_jails(state: State, settings: Settings) -> list[RawJail]:
    try:
        ssh_kw = get_ssh_kw(state=state, settings=settings)
        return get_bastille_jails(**ssh_kw)
    except Exception:  # noqa: BLE001
        return []


def pick_existing_jail(
    state: State,
    settings: Settings,
    *,
    prompt: str,
    allow_host: bool = True,
) -> str | None:
    with con().status("[dim]Fetching jail list…[/dim]", spinner="dots"):
        jails = _fetch_live_jails(state=state, settings=settings)

    private_to_public = {str(j.private_name): name for name, j in state.jails.items()}

    _nl()

    choices: list[Choice] = []
    if jails:
        rendered: list[dict[str, str]] = []
        for raw_jail in jails:
            public_name = private_to_public.get(raw_jail["private_name"], raw_jail["private_name"])
            rendered.append(
                {
                    "name": public_name,
                    "state": raw_jail["state"],
                    "ip": raw_jail["ip"],
                }
            )

        max_name = max(len(j["name"]) for j in rendered)
        for row in rendered:
            state_col = "up" if row["state"].lower() == "up" else row["state"].lower()
            label = f"{row['name'].ljust(max_name)}   {state_col}   {row['ip']}"
            choices.append(Choice(label, value=row["name"]))

        choices.append(Separator())

    if allow_host:
        choices += [Choice("Host VM", value="__host__"), Separator()]

    choices.append(Choice("Cancel", value="__cancel__"))
    chosen = questionary.select(prompt, choices=choices, style=Q_STYLE).ask()

    _nl()

    if chosen in (None, "__cancel__"):
        raise typer.Abort()

    if chosen == "__host__":
        return None

    return str(chosen)


def pick_existing_jails(
    state: State,
    settings: Settings,
    *,
    prompt: str,
) -> list[str]:
    with con().status("[dim]Fetching jail list…[/dim]", spinner="dots"):
        jails = _fetch_live_jails(state=state, settings=settings)

    _nl()

    if not jails:
        raise typer.Abort()

    private_to_public = {str(j.private_name): name for name, j in state.jails.items()}

    rendered: list[dict[str, str]] = []
    for raw_jail in jails:
        public_name = private_to_public.get(raw_jail["private_name"], raw_jail["private_name"])
        rendered.append(
            {
                "name": public_name,
                "state": raw_jail["state"],
                "ip": raw_jail["ip"],
            }
        )

    max_name = max(len(j["name"]) for j in rendered)
    choices: list[Choice] = []

    for row in rendered:
        state_col = "up" if row["state"].lower() == "up" else row["state"].lower()
        label = f"{row['name'].ljust(max_name)}   {state_col}   {row['ip']}"
        choices.append(Choice(label, value=row["name"]))

    selected = questionary.checkbox(
        prompt,
        choices=choices,
        style=Q_STYLE,
    ).ask()

    _nl()

    if selected is None:
        raise typer.Abort()

    return list(selected)


def _is_vm_running(settings: Settings) -> bool:
    alive, _ = vm_is_running(settings.pid_file)
    return alive


def _offer_start_vm(state: State, settings: Settings) -> bool:
    _nl()
    answer = questionary.confirm("VM is not running. Boot it now?", default=True, style=Q_STYLE).ask()
    _nl()

    if not answer:
        return False

    cmd.start(base_config=None, state=state, settings=settings, mode=QemuMode.SERVER)

    return True


def _preflight_start(args: list[str]) -> list[str] | None:
    if args:
        return args

    _nl()

    want_base = questionary.confirm("Use a custom base.ucl config?", default=False, style=Q_STYLE).ask()
    if want_base is None:
        return None

    _nl()

    if not want_base:
        return args

    raw = questionary.path("Path to base.ucl:", style=Q_STYLE).ask()
    if raw is None:
        return None

    _nl()

    return ["--base", raw] if raw else args


def _preflight_up(
    click_app: click.Group,
    args: list[str],
    state: State,
    settings: Settings,
) -> list[str] | None:
    p = _parse(click_app, "up", args)

    if p.get("config") is not None:
        if not _is_vm_running(settings) and not _offer_start_vm(state, settings):
            return None
        return args

    if not _is_vm_running(settings) and not _offer_start_vm(state, settings):
        return None

    _nl()

    con().print("[bold cyan]Jail wizard[/bold cyan]  [dim]starting interactive mode…[/dim]")

    config = pick_config()
    names = pick_jails_from_config(config)

    result = [str(config)]
    if names:
        result.extend(names)

    return result


def _preflight_ssh(
    click_app: click.Group,
    args: list[str],
    state: State,
    settings: Settings,
) -> list[str] | None:
    p = _parse(click_app, "ssh", args)
    if p.get("jail_name") is not None:
        return args

    if not _is_vm_running(settings) and not _offer_start_vm(state, settings):
        return None

    jail_name = pick_existing_jail(state, settings, prompt="SSH into:")

    return args if jail_name is None else [jail_name, *args]


def _preflight_cmd(
    click_app: click.Group,
    args: list[str],
    state: State,
    settings: Settings,
) -> list[str] | None:
    p = _parse(click_app, "cmd", args)

    if p.get("jail_name") is not None and p.get("executable") is not None:
        return args

    if not _is_vm_running(settings) and not _offer_start_vm(state, settings):
        return None

    jail_name = p.get("jail_name")
    if jail_name is None:
        jail_name = pick_existing_jail(state, settings, prompt="Run command in:", allow_host=False)
        if jail_name is None:
            return None

    raw = questionary.text("Executable (with args):", style=Q_STYLE).ask()
    if not raw:
        return None

    _nl()

    try:
        extra = shlex.split(raw)
    except ValueError:
        con().print("\n  [bold red]error:[/bold red] invalid quoting\n")
        return None

    return [jail_name, *extra]


def _preflight_jail_select(
    click_app: click.Group,
    command: str,
    args: list[str],
    state: State,
    settings: Settings,
) -> list[str] | None:
    p = _parse(click_app, command, args)
    if p.get("names"):
        return args

    if not _is_vm_running(settings) and not _offer_start_vm(state, settings):
        return None

    if not state.jails:
        warn("No jails in state.")
        return None

    prompt_map = {"down": "Destroy which jails?", "pause": "Pause which jails?"}
    names = pick_existing_jails(state=state, settings=settings, prompt=prompt_map[command])

    if not names:
        return None

    return list(names)


def _preflight(
    click_app: click.Group,
    command: str,
    args: list[str],
    state: State,
    settings: Settings,
) -> list[str] | None:
    if command == "start":
        return _preflight_start(args)
    if command == "up":
        return _preflight_up(click_app=click_app, args=args, state=state, settings=settings)
    if command == "ssh":
        return _preflight_ssh(click_app=click_app, args=args, state=state, settings=settings)
    if command == "cmd":
        return _preflight_cmd(click_app=click_app, args=args, state=state, settings=settings)
    if command in ("down", "pause"):
        return _preflight_jail_select(
            click_app=click_app,
            command=command,
            args=args,
            state=state,
            settings=settings,
        )

    return args


def _dispatch(
    *,
    settings: Settings,
    state_loader: Callable[[], State],
    click_app: click.Group,
    token: str,
    inline_args: list[str],
) -> bool:
    c = _ALIASES.get(token.strip().lower(), token.strip().lower())

    if c == "exit":
        return False

    if c == "help":
        _print_help()
        return True

    if c not in click_app.commands:
        con().print(
            f"\n  [bold red]unknown command:[/bold red] [cyan]{c}[/cyan]"
            "  —  type [bold]?[/bold] for help or Tab to browse\n"
        )
        return True

    argv = _preflight(click_app=click_app, command=c, args=inline_args, state=state_loader(), settings=settings)

    if argv is None:
        _aborted()
        return True

    _invoke(click_app, [c, *argv])

    return True


def run(
    *,
    settings: Settings,
    state_loader: Callable[[], State],
    click_app: click.Group,
    version: str,
) -> None:
    _print_welcome(version)

    completer = _build_completer(click_app)

    kb = KeyBindings()

    @kb.add("/")
    def _slash(event) -> None:  # type: ignore[no-untyped-def]
        buf = event.current_buffer
        if buf.text == "":
            buf.start_completion(select_first=False)
        else:
            buf.insert_text("/")

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

        try:
            parts = shlex.split(raw)
        except ValueError:
            con().print("\n  [bold red]error:[/bold red] invalid quoting\n")
            continue

        if not parts:
            continue
        if parts[0] == "?":
            parts[0] = "help"

        try:
            keep_going = _dispatch(
                settings=settings,
                state_loader=state_loader,
                click_app=click_app,
                token=parts[0],
                inline_args=parts[1:],
            )
        except (typer.Exit, typer.Abort):
            keep_going = True
        except Exception as exc:  # noqa: BLE001
            con().print(f"\n  [bold red]error:[/bold red] {exc}\n")
            keep_going = True

        if not keep_going:
            con().print("[dim]  Bye.[/dim]\n")
            break
