import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import typer

from jailrun import PACKAGE_DIR
from jailrun.schemas import Plan
from jailrun.serializers import dumps
from jailrun.settings import Settings
from jailrun.ssh import proxy_cmd


def resolve_playbook_path(playbook: str | Path) -> Path:
    p = Path(playbook)
    if p.is_absolute():
        return p.resolve()

    builtins_dir = (PACKAGE_DIR / "playbooks").resolve()

    candidate_user = (Path.cwd() / p).resolve()
    if candidate_user.exists():
        return candidate_user

    candidate_builtin = (builtins_dir / p).resolve()
    if candidate_builtin.exists():
        return candidate_builtin

    return candidate_user


def run_playbook(
    name: str,
    *,
    plan: Plan | None = None,
    settings: Settings,
    jail_name: str | None = None,
    jail_ip: str | None = None,
    extra_vars: dict[str, Any] | None = None,
) -> None:
    playbook = resolve_playbook_path(name)
    if not playbook.exists():
        typer.secho(f"Missing playbook: {playbook}", fg=typer.colors.RED)
        raise typer.Exit(1)

    private_key = settings.ssh_dir / settings.ssh_key
    env = os.environ.copy()
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"

    ev = {
        "ansible_host": "127.0.0.1",
        "ansible_port": settings.ssh_port,
        "ansible_user": settings.ssh_user,
        "ansible_python_interpreter": "/usr/local/bin/python3.13",
        "bsd_version": settings.bsd_version,
        "bsd_release_tag": settings.bsd_release_tag,
    }

    if jail_name and jail_ip:
        proxy = proxy_cmd(
            private_key=private_key,
            ssh_user=settings.ssh_user,
            ssh_port=settings.ssh_port,
        )
        ssh_args = [
            "-o StrictHostKeyChecking=no",
            "-o UserKnownHostsFile=/dev/null",
            f'-o ProxyCommand="{proxy}"',
        ]
        ev.update(
            {
                "ansible_host": jail_ip,
                "ansible_port": 22,
                "ansible_user": "root",
                "ansible_ssh_common_args": " ".join(ssh_args),
            }
        )

    if extra_vars:
        ev.update(extra_vars)

    cmd = [
        "ansible-playbook",
        "-i",
        "localhost,",
        "-c",
        "ssh",
        str(playbook),
        "--private-key",
        str(private_key),
    ]
    cmd += ["-e", dumps(ev)]

    if plan:
        with tempfile.NamedTemporaryFile(suffix=".json", prefix="jrun-plan-", mode="w") as f:
            f.write(plan.model_dump_json(indent=2))
            f.flush()
            cmd += ["-e", f"@{f.name}"]
            typer.echo(f"🧩 Running playbook {name}...")
            subprocess.run(cmd, check=True, env=env)
    else:
        typer.echo(f"🧩 Running playbook {name}...")
        subprocess.run(cmd, check=True, env=env)

    typer.secho(f"✅ Playbook {name} complete.", fg=typer.colors.GREEN)
