import typer
from rich.text import Text

from jailrun.cmd.status.collect import collect_info
from jailrun.cmd.status.live import render_jail_live
from jailrun.cmd.status.render import render_jail_table, render_jail_tree, render_overview_table, render_overview_tree
from jailrun.cmd.status.types import ALL_SCOPES, DEFAULT_SCOPES, Scope
from jailrun.network import get_ssh_kw
from jailrun.qemu import vm_is_running
from jailrun.schemas import State
from jailrun.settings import Settings
from jailrun.ui import con


def resolve_scopes(show: list[str] | None) -> frozenset[Scope]:
    if not show:
        return DEFAULT_SCOPES

    result: set[Scope] = set()

    for raw in show:
        item = raw.lower().strip()
        if not item:
            continue
        if item == "all":
            return frozenset(ALL_SCOPES)
        if item in ALL_SCOPES:
            result.add(item)  # type: ignore[arg-type]

    return frozenset(result)


def status(
    state: State,
    settings: Settings,
    *,
    jail_name: str | None = None,
    tree: bool = False,
    live: bool = False,
    scopes: frozenset[Scope] = DEFAULT_SCOPES,
) -> None:
    alive, pid = vm_is_running(settings.pid_file)

    if not alive or pid is None:
        c = con()
        c.print()
        c.print(
            Text.assemble(
                ("● ", "bold yellow"),
                ("VM", "bold white"),
                ("  not running", "yellow"),
            )
        )
        c.print()
        c.print(Text("  Run jrun start to boot it.", style="dim white"))
        c.print()
        raise typer.Exit(0)

    with con().status("[dim]Connecting to VM…[/dim]", spinner="dots"):
        data = collect_info(state=state, settings=settings, pid=pid)

    if jail_name:
        if live:
            ssh_kw = get_ssh_kw(settings, state)
            render_jail_live(data, jail_name, ssh_kw=ssh_kw, tree=tree)
        elif tree:
            render_jail_tree(data, jail_name)
        else:
            render_jail_table(data, jail_name)
    else:
        if tree:
            render_overview_tree(data, scopes=scopes)
        else:
            render_overview_table(data, scopes=scopes)
