import socket
import subprocess
from pathlib import Path
from typing import Any, TypedDict

import typer
from tenacity import retry, retry_if_result, stop_after_attempt, wait_fixed

from jailrun.schemas import State
from jailrun.settings import Settings
from jailrun.ui import con, err, info, ok

SWEEP_START = "10.17.89.10"
SWEEP_END = "10.17.89.250"

SSH_OPTS = [
    "-o",
    "StrictHostKeyChecking=no",  # VM is ephemeral and gets a new host key every time
    "-o",
    "UserKnownHostsFile=/dev/null",  #  prevents polluting known_hosts
    "-o",
    "LogLevel=ERROR",  # suppresses the "Warning: Permanently added" noise
]


class SSHKwargs(TypedDict):
    private_key: Path
    ssh_host: str
    ssh_user: str
    ssh_port: int


def is_port_free(port: int, bind_addr: str) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((bind_addr, port))
            return True
        except OSError:
            return False


def find_free_port(preferred: int, bind_addr: str, search_range: int = 100) -> int:
    for port in range(preferred, preferred + search_range):
        if is_port_free(port, bind_addr):
            return port

    raise RuntimeError(
        f"No free port found in [{preferred}, {preferred + search_range}) on {bind_addr}. "
        "Stop other VMs or adjust ssh_port in your config."
    )


def get_ssh_kw(settings: Settings, state: State) -> SSHKwargs:
    private_key = Path(settings.ssh_dir) / str(settings.ssh_key)
    state_port = state.ssh_port if state is not None and state.ssh_port is not None else None
    return {
        "private_key": private_key,
        "ssh_host": settings.vm_host,
        "ssh_user": settings.ssh_user,
        "ssh_port": state_port or settings.ssh_port,
    }


def ensure_vm_key(private_key: Path, public_key: Path) -> str:
    if not public_key.exists():
        info("Generating VM SSH key…")
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(private_key), "-N", ""],
            check=True,
        )
    return public_key.read_text().strip()


def ssh_cmd(
    args: list[str], *, private_key: Path, ssh_host: str, ssh_user: str, ssh_port: int, tty: bool = False
) -> list[str]:
    return [
        "ssh",
        "-i",
        str(private_key),
        "-p",
        str(ssh_port),
        *(["-t"] if tty else []),
        *SSH_OPTS,
        f"{ssh_user}@{ssh_host}",
        *args,
    ]


def proxy_cmd(*, private_key: Path, ssh_user: str, ssh_host: str, ssh_port: int) -> str:
    return f"ssh -i {private_key} -p {ssh_port} {' '.join(SSH_OPTS)} -W %h:%p {ssh_user}@{ssh_host}"


def jail_ssh_cmd(
    args: list[str],
    *,
    jail_ip: str,
    private_key: Path,
    ssh_host: str,
    ssh_user: str,
    ssh_port: int,
    tty: bool = False,
) -> list[str]:
    return [
        "ssh",
        "-i",
        str(private_key),
        *(["-t"] if tty else []),
        *SSH_OPTS,
        "-o",
        f"ProxyCommand={proxy_cmd(private_key=private_key, ssh_host=ssh_host, ssh_user=ssh_user, ssh_port=ssh_port)}",
        f"root@{jail_ip}",
        *args,
    ]


def ssh_exec(
    cmd: str, *, private_key: Path, ssh_user: str, ssh_host: str, ssh_port: int, timeout: int = 30
) -> str | None:
    result = subprocess.run(
        ssh_cmd(args=[f"doas {cmd}"], private_key=private_key, ssh_host=ssh_host, ssh_user=ssh_user, ssh_port=ssh_port),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = result.stdout.strip()
    return output if output else None


def jail_ssh_exec(
    cmd: str, *, jail_ip: str, private_key: Path, ssh_user: str, ssh_host: str, ssh_port: int, timeout: int = 30
) -> str | None:
    result = subprocess.run(
        jail_ssh_cmd(
            args=[cmd],
            jail_ip=jail_ip,
            private_key=private_key,
            ssh_host=ssh_host,
            ssh_user=ssh_user,
            ssh_port=ssh_port,
        ),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = result.stdout.strip()
    return output if output else None


def wait_for_ssh(*, private_key: Path, ssh_user: str, ssh_host: str, ssh_port: int, silent: bool = False) -> None:
    status_ctx = con().status("[dim]Waiting for SSH…[/dim]", spinner="dots") if not silent else None

    def _before_sleep(s: Any) -> None:
        if status_ctx is not None:
            status_ctx.update(f"[dim]Waiting for SSH… (attempt {s.attempt_number}/60)[/dim]")

    @retry(
        stop=stop_after_attempt(60),
        wait=wait_fixed(5),
        retry=retry_if_result(lambda rc: rc != 0),
        before_sleep=_before_sleep,
    )
    def _probe() -> int:
        return subprocess.run(
            ssh_cmd(args=["true"], private_key=private_key, ssh_host=ssh_host, ssh_user=ssh_user, ssh_port=ssh_port),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode

    try:
        if status_ctx is not None:
            with status_ctx:
                _probe()
        else:
            _probe()
    except Exception as exc:
        err("SSH did not become available after 60 attempts.")
        raise typer.Exit(1) from exc

    if not silent:
        ok("SSH ready.")


def resolve_jail_ips(
    old_state: State, new_state: State, *, private_key: Path, ssh_user: str, ssh_host: str, ssh_port: int
) -> None:
    taken: set[str] = set()
    for jail in new_state.jails.values():
        if jail.ip:
            taken.add(jail.ip)

    needs_sweep: list[str] = []
    for name, jail in new_state.jails.items():
        if jail.ip:
            continue
        if name in old_state.jails and old_state.jails[name].ip:
            jail.ip = old_state.jails[name].ip
            if jail.ip:
                taken.add(jail.ip)
        else:
            needs_sweep.append(name)

    if not needs_sweep:
        return

    with con().status("[dim]Probing free IP range…[/dim]", spinner="dots"):
        raw = ssh_exec(
            cmd=f"fping -u -A -g -i 1 -t 100 -r 0 {SWEEP_START} {SWEEP_END}",
            private_key=private_key,
            ssh_host=ssh_host,
            ssh_user=ssh_user,
            ssh_port=ssh_port,
        )

    if not raw:
        err(f"No free IPs found in {SWEEP_START}–{SWEEP_END}.")
        raise typer.Exit(1)

    free = [ip for ip in raw.splitlines() if ip.strip() and ip.strip() not in taken]

    if len(free) < len(needs_sweep):
        err(f"Need {len(needs_sweep)} IPs, only {len(free)} available.")
        raise typer.Exit(1)

    for name, ip in zip(needs_sweep, free, strict=False):
        ip = ip.strip()
        if not ip:
            continue

        new_state.jails[name].ip = ip
        taken.add(ip)

        info(f"{name}: assigned {ip}")
