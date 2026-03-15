from json import JSONDecodeError
from typing import Any

import typer
from tenacity import retry, retry_if_result, stop_never, wait_fixed

from jailrun.ansible import run_playbook
from jailrun.config import save_state
from jailrun.misc import lock
from jailrun.network import SSHKwargs, get_ssh_kw, ssh_exec, wait_for_ssh
from jailrun.qemu import vm_is_running
from jailrun.schemas import PeerInfo, State
from jailrun.serializers import dumps, loads
from jailrun.settings import Settings
from jailrun.ui import con, err, info, ok, warn


def relay_request(
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

    raw = ssh_exec(cmd="yggdrasilctl -json getSelf", **ssh_kw)
    if not raw:
        err("Cannot reach yggdrasil on VM. Is mesh_network enabled?")
        raise typer.Exit(1)

    pubkey = loads(raw)["key"]

    base_url = f"http://[{settings.relay_addr}]:{settings.relay_port}"
    data = relay_request(ssh_kw, method="POST", url=f"{base_url}/mesh", body={"pubkey": pubkey})
    if not data or "code" not in data:
        err("Failed to create mesh on relay.")
        raise typer.Exit(1)

    code = data["code"]

    c = con()
    c.print()
    c.print(f"[bold cyan]Code:[/bold cyan]  {code}")
    c.print(f"[dim]Tell your peer:[/dim]  jrun pair {code}")
    c.print()

    existing_keys = {p.pubkey for p in state.peers}

    @retry(stop=stop_never, wait=wait_fixed(3), retry=retry_if_result(lambda found: not found))
    def _poll() -> bool:
        poll = relay_request(ssh_kw, method="GET", url=f"{base_url}/mesh/{code}?pubkey={pubkey}")
        if not poll or "peers" not in poll:
            return False
        found = False
        for p in poll["peers"]:
            if p["pubkey"] not in existing_keys:
                existing_keys.add(p["pubkey"])
                state.peers.append(PeerInfo(pubkey=p["pubkey"]))
                ok(f"Paired with {p['pubkey'][:16]}…")
                found = True
        return found

    try:
        with c.status("[dim]Waiting for peers…[/dim]", spinner="dots"):
            _poll()
    except KeyboardInterrupt:
        c.print()

    if state.peers:
        save_state(state=state, state_file=settings.state_file)

        info("Applying yggdrasil configuration…")
        run_playbook(
            "vm-yggdrasil.yml",
            extra_vars={
                "relay_peer_uri": settings.relay_peer_uri,
                "relay_pubkey": settings.relay_pubkey,
                "peer_pubkeys": [p.pubkey for p in state.peers],
            },
            settings=settings,
            state=state,
        )
        ok("Done. Peer jails are now reachable.")


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

    raw = ssh_exec(cmd="yggdrasilctl -json getSelf", **ssh_kw)
    if not raw:
        err("Cannot reach yggdrasil on VM. Is mesh_network enabled?")
        raise typer.Exit(1)

    pubkey = loads(raw)["key"]

    base_url = f"http://[{settings.relay_addr}]:{settings.relay_port}"
    data = relay_request(ssh_kw, method="POST", url=f"{base_url}/mesh/{code}", body={"pubkey": pubkey})
    if data is None:
        err("Invalid or expired code.")
        raise typer.Exit(1)

    peers = data.get("peers", [])
    if not peers:
        warn("No peers found in mesh yet.")
        raise typer.Exit(0)

    existing_keys = {p.pubkey for p in state.peers}
    for p in peers:
        if p["pubkey"] not in existing_keys:
            state.peers.append(PeerInfo(pubkey=p["pubkey"]))
            ok(f"Paired with {p['pubkey'][:16]}…")

    save_state(state=state, state_file=settings.state_file)

    info("Applying yggdrasil configuration…")
    run_playbook(
        "vm-yggdrasil.yml",
        extra_vars={
            "relay_peer_uri": settings.relay_peer_uri,
            "relay_pubkey": settings.relay_pubkey,
            "peer_pubkeys": [p.pubkey for p in state.peers],
        },
        settings=settings,
        state=state,
    )
    ok("Done. Peer jails are now reachable.")
