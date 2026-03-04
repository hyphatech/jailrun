import subprocess
from pathlib import Path

import typer
from tenacity import retry, retry_if_result, stop_after_attempt, wait_fixed

from jailrun.schemas import State

SWEEP_START = "10.17.89.10"
SWEEP_END = "10.17.89.250"

SSH_OPTS = [
    "-o",
    "StrictHostKeyChecking=no",
    "-o",
    "UserKnownHostsFile=/dev/null",
    "-o",
    "LogLevel=ERROR",
]


def ensure_vm_key(private_key: Path, public_key: Path) -> str:
    if not public_key.exists():
        typer.echo("🔐 Generating VM SSH key...")
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(private_key), "-N", ""],
            check=True,
        )
    return public_key.read_text().strip()


def ssh_cmd(args: list[str], *, private_key: Path, ssh_user: str, ssh_port: int) -> list[str]:
    return [
        "ssh",
        "-i",
        str(private_key),
        "-p",
        str(ssh_port),
        *SSH_OPTS,
        f"{ssh_user}@localhost",
        *args,
    ]


def proxy_cmd(*, private_key: Path, ssh_user: str, ssh_port: int) -> str:
    """ProxyCommand string for jumping through the host VM to reach a jail."""
    return (
        f"ssh -i {private_key} -p {ssh_port} "
        f"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
        f"-o LogLevel=ERROR "
        f"-W %h:%p {ssh_user}@127.0.0.1"
    )


def jail_ssh_cmd(
    args: list[str],
    *,
    jail_ip: str,
    private_key: Path,
    ssh_user: str,
    ssh_port: int,
) -> list[str]:
    """SSH command list for connecting to a jail via the host VM."""
    return [
        "ssh",
        "-i",
        str(private_key),
        *SSH_OPTS,
        "-o",
        f"ProxyCommand={proxy_cmd(private_key=private_key, ssh_user=ssh_user, ssh_port=ssh_port)}",
        f"root@{jail_ip}",
        *args,
    ]


def ssh_exec(cmd: str, *, private_key: Path, ssh_user: str, ssh_port: int) -> str | None:
    result = subprocess.run(
        ssh_cmd(args=[f"doas {cmd}"], private_key=private_key, ssh_user=ssh_user, ssh_port=ssh_port),
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stdout.strip()
    return output if output else None


def wait_for_ssh(*, private_key: Path, ssh_user: str, ssh_port: int, silent: bool = False) -> None:
    if not silent:
        typer.echo("⏳ Waiting for SSH...")

    @retry(
        stop=stop_after_attempt(60),
        wait=wait_fixed(5),
        retry=retry_if_result(lambda rc: rc != 0),
        before_sleep=lambda state: (
            typer.echo(f"SSH not ready yet (attempt {state.attempt_number}/60), retrying in 5s...")
            if not silent
            else None
        ),
    )
    def _probe_ssh() -> int:
        return subprocess.run(
            ssh_cmd(args=["true"], private_key=private_key, ssh_user=ssh_user, ssh_port=ssh_port),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode

    try:
        _probe_ssh()
    except Exception as exc:
        if not silent:
            typer.secho(
                "🚫 SSH did not become available after 60 attempts.",
                fg=typer.colors.RED,
            )
        raise typer.Exit(1) from exc

    if not silent:
        typer.secho("✅ SSH is ready", fg=typer.colors.GREEN)


def resolve_jail_ips(old_state: State, new_state: State, *, private_key: Path, ssh_user: str, ssh_port: int) -> None:
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

    typer.echo("⏳ Probing free IP range...")

    raw = ssh_exec(
        cmd=f"fping -u -A -g -t 100 -r 1 {SWEEP_START} {SWEEP_END}",
        private_key=private_key,
        ssh_user=ssh_user,
        ssh_port=ssh_port,
    )

    if not raw:
        typer.secho(
            f"No free IPs found in {SWEEP_START}–{SWEEP_END}.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    free = [ip for ip in raw.splitlines() if ip.strip() and ip.strip() not in taken]

    if len(free) < len(needs_sweep):
        typer.secho(
            f"Need {len(needs_sweep)} IPs, only {len(free)} available.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    for name, ip in zip(needs_sweep, free, strict=False):
        ip = ip.strip()
        if not ip:
            continue

        new_state.jails[name].ip = ip
        taken.add(ip)
        typer.echo(f"👉 {name}: assigned {new_state.jails[name].ip}")
