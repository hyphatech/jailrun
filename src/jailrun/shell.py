import shlex
from collections.abc import Callable
from pathlib import Path
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

from jailrun import cmd, ucl
from jailrun.cmd.status.collect import get_bastille_jails
from jailrun.cmd.status.types import ALL_SCOPES, RawJail
from jailrun.network import get_ssh_kw
from jailrun.qemu import QemuMode, vm_is_running
from jailrun.schemas import State
from jailrun.settings import Settings
from jailrun.ui import COMMANDS, Q_STYLE, con, nl, warn

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
        nl()
    except click.exceptions.UsageError as exc:
        nl()
        con().print(f"  [bold red]error:[/bold red] {exc}")
        msg = str(exc)
        if "'--show'" in msg or "'-s'" in msg:
            opts = ", ".join([*ALL_SCOPES, "all"])
            con().print(f"  [dim]available: {opts}[/dim]")
        nl()


def _build_completer(click_app: click.Group) -> NestedCompleter:
    completions: dict[str, Any] = {}
    for name, sub in click_app.commands.items():
        if isinstance(sub, click.Group):
            sub_completions: dict[str, Any] = {}
            for sub_name, sub_cmd in sub.commands.items():
                opts = {
                    opt: None
                    for param in sub_cmd.params
                    if isinstance(param, click.Option)
                    for opt in param.opts
                    if opt.startswith("--")
                }
                sub_completions[sub_name] = opts or None
            completions[name] = sub_completions
        else:
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


def print_help() -> None:
    c = con()
    c.print()
    c.print(_command_table(include_shell_extras=True))
    c.print()


def _fetch_live_jails(state: State, settings: Settings) -> list[RawJail]:
    try:
        ssh_kw = get_ssh_kw(state=state, settings=settings)
        return get_bastille_jails(ssh_kw)
    except Exception:  # noqa: BLE001
        return []


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

    nl()

    if scope is None or scope == "__cancel__":
        raise typer.Abort()
    if scope == "__all__":
        return None

    choices = [Choice(n, value=n, checked=False) for n in names]

    selected = questionary.checkbox(
        "Select jails:",
        choices=choices,
        style=Q_STYLE,
    ).ask()

    nl()

    if selected is None or not selected:
        raise typer.Abort()

    return list(selected)


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

        for row in rendered:
            choices.append(Choice(row["name"], value=row["name"]))

        choices.append(Separator())

    if allow_host:
        choices += [Choice("Host VM", value="__host__"), Separator()]

    choices.append(Choice("Cancel", value="__cancel__"))

    nl()
    chosen = questionary.select(prompt, choices=choices, style=Q_STYLE).ask()
    nl()

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

    choices: list[Choice] = []

    for row in rendered:
        choices.append(Choice(row["name"], value=row["name"]))

    nl()
    selected = questionary.checkbox(
        prompt,
        choices=choices,
        style=Q_STYLE,
    ).ask()
    nl()

    if selected is None:
        raise typer.Abort()

    return list(selected)


def pick_config() -> Path:
    candidates = sorted(Path(".").glob("**/*.ucl"))

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

        nl()

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


def _is_vm_running(settings: Settings) -> bool:
    alive, _ = vm_is_running(settings.pid_file)
    return alive


def _offer_start_vm(state: State, settings: Settings) -> bool:
    nl()
    answer = questionary.confirm("VM is not running. Boot it now?", default=True, style=Q_STYLE).ask()
    nl()

    if not answer:
        return False

    cmd.start(base_config=None, state=state, settings=settings, mode=QemuMode.SERVER)

    return True


def _preflight_start(args: list[str]) -> list[str] | None:
    if args:
        return args

    nl()

    want_base = questionary.confirm("Use a custom base.ucl config?", default=False, style=Q_STYLE).ask()
    if want_base is None:
        return None

    nl()

    if not want_base:
        return args

    raw = questionary.path("Path to base.ucl:", style=Q_STYLE).ask()
    if raw is None:
        return None

    nl()

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

    nl()
    con().print("[bold cyan]Jail wizard[/bold cyan]  [dim]starting interactive mode…[/dim]")
    nl()

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

    nl()

    try:
        extra = shlex.split(raw)
    except ValueError:
        con().print("  [bold red]error:[/bold red] invalid quoting")
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

    prompt_map = {"down": "Destroy which jails?"}
    names = pick_existing_jails(state=state, settings=settings, prompt=prompt_map[command])

    if not names:
        return None

    return list(names)


def _preflight_pair(
    args: list[str],
    state: State,
    settings: Settings,
) -> list[str] | None:
    if not _is_vm_running(settings) and not _offer_start_vm(state, settings):
        return None

    if args:
        return args

    nl()

    code = questionary.text("Pairing code (leave empty to create new):", style=Q_STYLE).ask()

    if code is None:
        return None

    return [code.strip()] if code.strip() else []


def _preflight_snapshot(
    args: list[str],
    state: State,
    settings: Settings,
) -> list[str] | None:
    if len(args) >= 2 and args[0] in ("create", "list", "rollback", "delete"):
        return args

    if not _is_vm_running(settings) and not _offer_start_vm(state, settings):
        return None

    action = args[0] if args and args[0] in ("create", "list", "rollback", "delete") else None
    remaining = args[1:] if action else args

    nl()

    if action is None:
        action = questionary.select(
            "Action:",
            choices=[
                Choice("List snapshots", value="list"),
                Choice("Create snapshot", value="create"),
                Choice("Rollback to snapshot", value="rollback"),
                Choice("Delete snapshot", value="delete"),
                Separator(),
                Choice("Cancel", value="__cancel__"),
            ],
            style=Q_STYLE,
        ).ask()

        if action in (None, "__cancel__"):
            return None

    jail_name = remaining[0] if remaining else None
    snap_name = remaining[1] if len(remaining) > 1 else None

    if jail_name is None:
        jail_name = pick_existing_jail(state, settings, prompt="Which jail:", allow_host=False)
        if jail_name is None:
            return None

    if action == "list":
        return [action, jail_name]

    if action == "create":
        if snap_name is None:
            raw = questionary.text("Snapshot name (empty for timestamp):", style=Q_STYLE).ask()
            nl()
            if raw is None:
                return None

            snap_name = raw.strip() or None

        result = [action, jail_name]
        if snap_name:
            result.append(snap_name)

        return result

    if snap_name is None:
        raw = questionary.text("Snapshot name:", style=Q_STYLE).ask()
        nl()
        if raw is None or not raw.strip():
            return None

        snap_name = raw.strip()

    return [action, jail_name, snap_name]


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
    if command == "down":
        return _preflight_jail_select(
            click_app=click_app,
            command=command,
            args=args,
            state=state,
            settings=settings,
        )
    if command == "pair":
        return _preflight_pair(args=args, state=state, settings=settings)
    if command == "snapshot":
        return _preflight_snapshot(args=args, state=state, settings=settings)

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
        print_help()
        return True

    if c not in click_app.commands:
        nl()
        con().print(
            f"  [bold red]unknown command:[/bold red] [cyan]{c}[/cyan]"
            "  —  type [bold]?[/bold] for help or Tab to browse"
        )
        nl()
        return True

    argv = _preflight(click_app=click_app, command=c, args=inline_args, state=state_loader(), settings=settings)

    if argv is None:
        warn("Aborted.")
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
            nl()
            con().print("[dim]  Bye![/dim]")
            nl()
            break
        except EOFError:
            nl()
            con().print("[dim]  Bye![/dim]")
            nl()
            break

        try:
            parts = shlex.split(raw)
        except ValueError:
            nl()
            con().print("  [bold red]error:[/bold red] invalid quoting")
            nl()
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
            nl()
            con().print(f"  [bold red]error:[/bold red] {exc}")
            nl()
            keep_going = True

        if not keep_going:
            nl()
            con().print("[dim]  Bye.[/dim]")
            nl()
            break
