import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import typer
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from jailrun import PACKAGE_DIR
from jailrun.network import SSH_OPTS, get_ssh_kw, proxy_cmd
from jailrun.schemas import Plan, State
from jailrun.serializers import dumps
from jailrun.settings import Settings
from jailrun.ui import con, err, info, ok

_TASK_RE = re.compile(r"^TASK \[(.+)\]")


def _count_tasks(cmd: list[str], env: dict[str, str]) -> int:
    result = subprocess.run(cmd + ["--list-tasks"], capture_output=True, text=True, env=env)
    count = 0
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("play #", "pattern:")):
            count += 1

    return count


def _run_quiet(cmd: list[str], env: dict[str, str], total: int) -> None:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    if proc.stdout is None:
        raise RuntimeError("Failed to capture ansible-playbook output")

    failed_lines: list[str] = []
    progress = Progress(
        SpinnerColumn(),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[dim]{task.description}[/dim]"),
        console=con(),
        transient=True,
    )

    with progress:
        task_id = progress.add_task("Preparing…", total=total or None)
        for line in proc.stdout:
            line = line.rstrip()
            m = _TASK_RE.match(line)
            if m:
                progress.update(task_id, advance=1, description=m.group(1))
            elif "fatal:" in line or "FAILED!" in line:
                failed_lines.append(line)

    rc = proc.wait()
    for fail in failed_lines:
        err(fail)
    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd)


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
    settings: Settings,
    state: State,
    plan: Plan | None = None,
    jail_name: str | None = None,
    jail_ip: str | None = None,
    extra_vars: dict[str, Any] | None = None,
) -> None:
    playbook = resolve_playbook_path(name)
    if not playbook.exists():
        err(f"Missing playbook: {playbook}")
        raise typer.Exit(1)

    env = os.environ.copy()
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"

    ssh_kw = get_ssh_kw(settings, state)
    vars = {
        "ansible_host": ssh_kw["ssh_host"],
        "ansible_port": ssh_kw["ssh_port"],
        "ansible_user": ssh_kw["ssh_user"],
        "ansible_python_interpreter": settings.vm_python_interpreter,
        "ansible_ssh_common_args": " ".join(SSH_OPTS),
        "bsd_version": settings.bsd_version,
        "bsd_release_tag": settings.bsd_release_tag,
    }

    if jail_name and jail_ip:
        proxy = proxy_cmd(
            private_key=ssh_kw["private_key"],
            ssh_host=ssh_kw["ssh_host"],
            ssh_user=ssh_kw["ssh_user"],
            ssh_port=ssh_kw["ssh_port"],
        )
        vars.update(
            {
                "ansible_host": jail_ip,
                "ansible_port": 22,
                "ansible_user": "root",
                "ansible_ssh_common_args": f'{" ".join(SSH_OPTS)} -o ProxyCommand="{proxy}"',
            }
        )

    if extra_vars:
        vars.update(extra_vars)

    cmd = [
        "ansible-playbook",
        "-i",
        "localhost,",
        "-c",
        "ssh",
        "-v",
        str(playbook),
        "--private-key",
        str(ssh_kw["private_key"]),
        "-e",
        dumps(vars),
    ]

    if plan:
        with tempfile.NamedTemporaryFile(suffix=".json", prefix="jrun-plan-", mode="w", delete=False) as f:
            f.write(plan.model_dump_json(indent=2))
            cmd += ["-e", f"@{f.name}"]

    info(f"Running playbook {name}…")

    if settings.debug:
        subprocess.run(cmd, check=True, env=env)
    else:
        _run_quiet(cmd, env, _count_tasks(cmd, env))

    ok(f"Playbook {name} complete.")
