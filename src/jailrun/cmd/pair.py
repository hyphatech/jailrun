from datetime import UTC, datetime
from json import JSONDecodeError
from typing import Any

import typer
from tenacity import retry, retry_if_result, stop_never, wait_fixed

from jailrun.ansible import run_playbook
from jailrun.config import save_state
from jailrun.misc import lock
from jailrun.network import SSHKwargs, get_ssh_kw, jail_ssh_exec, ssh_exec, wait_for_ssh
from jailrun.qemu import vm_is_running
from jailrun.schemas import PeerJail, PeerState, State
from jailrun.serializers import dumps, loads
from jailrun.settings import Settings
from jailrun.ui import con, err, info, ok, warn


def _relay_request(
    ssh_kw: SSHKwargs, *, method: str, url: str, body: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    cmd_parts = ["curl", "-s"]
    if method != "GET":
        cmd_parts += ["-X", method]
    if body is not None:
        cmd_parts += ["-H", '"Content-Type: application/json"', "-d", f"'{dumps(body)}'"]

    cmd_parts.append(f'"{url}"')

    raw = ssh_exec(cmd=" ".join(cmd_parts), **ssh_kw)
    if not raw:
        return None
    try:
        result: dict[str, Any] = loads(raw)
        return result
    except JSONDecodeError:
        return None


def _collect_jail_roster(ssh_kw: SSHKwargs, state: State) -> list[PeerJail]:
    roster: list[PeerJail] = []
    for name, jail in state.jails.items():
        if not jail.ip:
            continue

        raw = jail_ssh_exec(
            cmd="yggdrasilctl -json getSelf",
            jail_ip=jail.ip,
            **ssh_kw,
        )
        if not raw:
            continue

        try:
            data = loads(raw)
            addr = data.get("address", "")
            if addr:
                roster.append(PeerJail(name=name, ygg_address=addr))
        except (JSONDecodeError, KeyError):
            continue

    return roster


def pair_create(state: State, settings: Settings) -> None:
    with lock(settings.state_file):
        _pair_create(state=state, settings=settings)


def _pair_create(state: State, settings: Settings) -> None:
    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Start it first with: jrun start")
        raise typer.Exit(1)

    ssh_kw = get_ssh_kw(settings, state)

    with con().status("[dim]Connecting to VM…[/dim]", spinner="dots"):
        wait_for_ssh(**ssh_kw, silent=True)

    with con().status("[dim]Collecting jail addresses…[/dim]", spinner="dots"):
        roster = _collect_jail_roster(ssh_kw, state)

    if not roster:
        err("No mesh-enabled jails found. Deploy jails first with: jrun up")
        raise typer.Exit(1)

    base_url = f"http://[{settings.relay_addr}]:{settings.relay_port}"
    data = _relay_request(
        ssh_kw,
        method="POST",
        url=f"{base_url}/pair",
        body={"jails": [j.model_dump() for j in roster]},
    )
    if not data or "code" not in data:
        err("Failed to create pairing on relay.")
        raise typer.Exit(1)

    code = data["code"]

    c = con()
    c.print()
    c.print(f"[bold cyan]Code:[/bold cyan]  {code}")
    c.print(f"[dim]Tell your peer:[/dim]  jrun pair {code}")
    c.print()

    @retry(stop=stop_never, wait=wait_fixed(3), retry=retry_if_result(lambda r: r is None))
    def _poll() -> dict[str, Any] | None:
        resp = _relay_request(
            ssh_kw,
            method="GET",
            url=f"{base_url}/pair/{code}",
        )
        if not resp:
            return None
        if resp.get("joined"):
            return resp
        return None

    try:
        with c.status("[dim]Waiting for peer…[/dim]", spinner="dots"):
            result = _poll()
    except KeyboardInterrupt:
        c.print()
        warn("Cancelled.")
        raise typer.Exit(0) from None

    if result is None:
        err("Pairing failed.")
        raise typer.Exit(1)

    peer = PeerState(
        alias=code,
        direction="init",
        paired_at=datetime.now(UTC).isoformat(),
        jails=[PeerJail(**j) for j in result["jails"]],
    )
    state.peers.append(peer)
    save_state(state=state, state_file=settings.state_file)

    ok(f"Paired with {code} ({len(peer.jails)} jails)")
    _apply_peers(state=state, settings=settings)


def _apply_peers(state: State, settings: Settings) -> None:
    peers_data = [p.model_dump() for p in state.peers]

    info("Updating DNS records…")
    run_playbook(
        "jail-dns-peers.yml",
        extra_vars={"peers": peers_data},
        settings=settings,
        state=state,
    )

    info("Updating pf firewall rules…")
    run_playbook(
        "jail-pf-peers.yml",
        extra_vars={"peers": peers_data},
        settings=settings,
        state=state,
    )


def pair_join(code: str, state: State, settings: Settings) -> None:
    with lock(settings.state_file):
        _pair_join(code=code, state=state, settings=settings)


def _pair_join(code: str, state: State, settings: Settings) -> None:
    alive, _ = vm_is_running(settings.pid_file)
    if not alive:
        err("VM is not running. Start it first with: jrun start")
        raise typer.Exit(1)

    ssh_kw = get_ssh_kw(settings, state)

    with con().status("[dim]Connecting to VM…[/dim]", spinner="dots"):
        wait_for_ssh(**ssh_kw, silent=True)

    with con().status("[dim]Collecting jail addresses…[/dim]", spinner="dots"):
        roster = _collect_jail_roster(ssh_kw, state)

    if not roster:
        err("No mesh-enabled jails found. Deploy jails first with: jrun up")
        raise typer.Exit(1)

    base_url = f"http://[{settings.relay_addr}]:{settings.relay_port}"
    data = _relay_request(
        ssh_kw,
        method="POST",
        url=f"{base_url}/pair/{code}",
        body={"jails": [j.model_dump() for j in roster]},
    )
    if data is None:
        err("Invalid or expired code.")
        raise typer.Exit(1)

    peer = PeerState(
        alias=code,
        direction="joined",
        paired_at=datetime.now(UTC).isoformat(),
        jails=[PeerJail(**j) for j in data["jails"]],
    )
    state.peers.append(peer)
    save_state(state=state, state_file=settings.state_file)

    ok(f"Paired with {code} ({len(peer.jails)} jails)")
    _apply_peers(state=state, settings=settings)


def pair_list(state: State) -> None:
    from rich.padding import Padding
    from rich.table import Table
    from rich.text import Text

    c = con()
    c.print()

    if not state.peers:
        c.print("  [dim]no paired instances[/dim]")
        c.print()
        return

    tbl = Table(
        show_header=True,
        header_style="dim",
        box=None,
        show_edge=False,
        padding=(0, 3, 0, 0),
        expand=False,
        pad_edge=False,
    )
    tbl.add_column("name", no_wrap=True)
    tbl.add_column("peer", style="dim white", no_wrap=True)
    tbl.add_column("ip", style="dim white", no_wrap=True)
    tbl.add_column("paired", style="dim white", no_wrap=True)

    for p in state.peers:
        for j in p.jails:
            tbl.add_row(
                Text(j.name, style="bold"),
                p.alias,
                j.ygg_address,
                datetime.fromisoformat(p.paired_at).strftime("%b %d %Y, %H:%M UTC"),
            )

    c.print(Padding(tbl, pad=(0, 0, 0, 2)))
    c.print()


def pair_remove(alias: str, state: State, settings: Settings) -> None:
    with lock(settings.state_file):
        _pair_remove(alias=alias, state=state, settings=settings)


def _pair_remove(alias: str, state: State, settings: Settings) -> None:
    match = [p for p in state.peers if p.alias == alias]
    if not match:
        err(f"No peer found with name '{alias}'")
        raise typer.Exit(1)

    state.peers = [p for p in state.peers if p.alias != alias]
    save_state(state=state, state_file=settings.state_file)

    ok(f"Removed {alias}")
    _apply_peers(state=state, settings=settings)
