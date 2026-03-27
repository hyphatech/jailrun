import time

from rich.live import Live
from rich.padding import Padding
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from jailrun.network import SSHKwargs, jail_ssh_exec
from jailrun.ui import con

from .monit import parse_monit_status
from .render import build_jail_info, build_jail_table, find_jail, jail_header
from .sparkline import SampleHistory
from .types import JailRow, MonitJailStatus, StatusInfo


def refresh_jail_monit(j: JailRow, *, ssh_kw: SSHKwargs) -> None:
    if j["state"].lower() != "up" or not j["ips"]:
        return

    jail_ip = j["ips"][0]
    try:
        raw = jail_ssh_exec(
            cmd="monit status 2>/dev/null",
            jail_ip=jail_ip,
            timeout=10,
            ssh_kw=ssh_kw,
        )
    except Exception:
        return

    if not raw:
        return

    parsed = parse_monit_status(raw)
    for _, monit_data in parsed.items():
        j["monit"] = MonitJailStatus(system_ok=None, services=[])

        if monit_data["system_ok"] is not None:
            j["monit"]["system_ok"] = monit_data["system_ok"]

        j["monit"]["services"].extend(monit_data["services"])


def _build_live_layout(
    j: JailRow,
    *,
    history: SampleHistory,
    interval: int,
    tree: bool = False,
) -> Table:
    layout = Table.grid(padding=0)
    layout.add_column()

    layout.add_row(jail_header(j))
    layout.add_row("")
    layout.add_row(Padding(build_jail_info(j), pad=(0, 0, 0, 2)))
    layout.add_row("")

    if tree:
        root = Tree(Text("services", style="bold"))
        monit = j.get("monit")
        if monit and monit["services"]:
            for svc in monit["services"]:
                svc_style = "green" if svc["status"] == "ok" else "red"
                label = Text.assemble(
                    (svc["name"], "bold white"),
                    ("  ", ""),
                    (svc["status"], svc_style),
                )
                node = root.add(label)
                if svc["cpu"]:
                    line = Text.assemble(("cpu     ", "dim cyan"), (svc["cpu"].ljust(10), "white"))
                    line.append_text(history.cpu_spark(j["name"], svc["name"]))
                    node.add(line)

                if svc["mem"]:
                    line = Text.assemble(("mem     ", "dim cyan"), (svc["mem"].ljust(10), "white"))
                    line.append_text(history.mem_spark(j["name"], svc["name"]))
                    node.add(line)

                if svc["uptime"]:
                    node.add(Text.assemble(("uptime  ", "dim cyan"), (svc["uptime"], "dim white")))

        layout.add_row(Padding(root, pad=(0, 0, 0, 2)))
    else:
        layout.add_row(Padding(build_jail_table(j, history=history), pad=(0, 0, 0, 2)))

    layout.add_row("")
    layout.add_row(Text(f"  refreshing every {interval}s · Ctrl-C to exit", style="dim white"))
    layout.add_row("")

    return layout


def render_jail_live(
    data: StatusInfo,
    jail_name: str,
    *,
    ssh_kw: SSHKwargs,
    tree: bool = False,
    interval: int = 5,
) -> None:
    j = find_jail(data, jail_name)

    history = SampleHistory()
    history.ingest_jail(j)

    c = con()

    try:
        with Live(
            _build_live_layout(j, history=history, interval=interval, tree=tree),
            console=c,
            refresh_per_second=1,
            screen=False,
        ) as live:
            while True:
                time.sleep(interval)
                refresh_jail_monit(j, ssh_kw=ssh_kw)
                history.ingest_jail(j)
                live.update(_build_live_layout(j, history=history, interval=interval, tree=tree))
    except KeyboardInterrupt:
        c.print(Text("  Stopped.", style="dim white"))
        c.print()
