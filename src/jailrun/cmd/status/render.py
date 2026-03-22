from rich.padding import Padding
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from jailrun.ui import con, err

from .sparkline import SampleHistory
from .types import DEFAULT_SCOPES, JailRow, Scope, StatusInfo


def _jail_labels(j: JailRow) -> tuple[Text, Text]:
    name, st = j["name"], j["state"]
    if j.get("stale"):
        return (
            Text.assemble((name, "bold"), ("  stale", "yellow")),
            Text("missing", style="yellow"),
        )

    state_style = "green" if st.lower() == "up" else "red"

    if not j["managed"]:
        return (
            Text.assemble((name, "bold"), ("  unmanaged", "dim white")),
            Text(st.lower(), style=state_style),
        )

    return Text(name, style="bold"), Text(st.lower(), style=state_style)


def jail_header(j: JailRow) -> Text:
    name_t, state_t = _jail_labels(j)
    return Text.assemble(("  ", "")) + name_t + Text("  ") + state_t


def _multiline_cell(items: list[str], style: str = "dim white") -> Text:
    if not items:
        return Text("—", style="dim white")
    return Text("\n".join(items), style=style)


def _svc_summary_cell(j: JailRow) -> Text:
    monit = j.get("monit")
    if not monit or not monit["services"]:
        return Text("—", style="dim white")

    result = Text("")

    for i, svc in enumerate(monit["services"]):
        if i > 0:
            result.append("\n")
        svc_style = "green" if svc["status"] == "ok" else "red"
        result.append_text(
            Text.assemble(
                (svc["name"], "dim white"),
                (" ", ""),
                (svc["status"], svc_style),
            )
        )

    return result


def _add_tree_kv_rows(
    node: Tree,
    items: list[str],
    label: str,
    plural_label: str | None = None,
    style: str = "dim white",
) -> None:
    if items:
        for i, item in enumerate(items):
            prefix = f"{label:<8}" if i == 0 else " " * 8
            node.add(Text.assemble((prefix, "dim cyan"), (item, style)))
    else:
        fallback = plural_label or label + "s"
        node.add(Text.assemble((f"{fallback:<8}", "dim cyan"), ("—", "dim white")))


def _build_header(data: StatusInfo) -> Text:
    return Text.assemble(
        ("  ● ", "bold green"),
        ("VM", "bold white"),
        ("  running", "green"),
        (f"  on {data['ssh_host']}:{data['ssh_port']}", "dim white"),
        (f"  (pid {data['pid']})", "dim white"),
    )


def _build_vitals(data: StatusInfo) -> Table:
    vitals = Table.grid(padding=(0, 3, 0, 0))
    vitals.add_column(style="dim cyan", no_wrap=True, min_width=8)
    vitals.add_column()

    if data["uptime"]:
        vitals.add_row("uptime", data["uptime"].strip())
    if data["disk_free"] and data["disk_total"]:
        vitals.add_row(
            "disk",
            Text.assemble((data["disk_free"], "bold green"), (f" free of {data['disk_total']}", "dim white")),
        )
    if data["mem_total"] is not None and data["mem_usable"] is not None:
        vitals.add_row(
            "memory",
            Text.assemble(
                (f"{data['mem_usable']:.1f} GB", "bold green"),
                (f" usable / {data['mem_total']:.1f} GB total", "dim white"),
            ),
        )

    return vitals


def _add_vitals_to_tree(root: Tree, data: StatusInfo) -> None:
    if data["uptime"]:
        root.add(Text.assemble(("uptime  ", "dim cyan"), data["uptime"].strip()))
    if data["disk_free"] and data["disk_total"]:
        root.add(
            Text.assemble(
                ("disk    ", "dim cyan"),
                (data["disk_free"], "bold green"),
                (f" free of {data['disk_total']}", "dim white"),
            )
        )
    if data["mem_total"] is not None and data["mem_usable"] is not None:
        root.add(
            Text.assemble(
                ("memory  ", "dim cyan"),
                (f"{data['mem_usable']:.1f} GB", "bold green"),
                (f" usable / {data['mem_total']:.1f} GB total", "dim white"),
            )
        )


def build_jail_info(j: JailRow) -> Table:
    info = Table.grid(padding=(0, 3, 0, 0))
    info.add_column(style="dim cyan", no_wrap=True, min_width=8)
    info.add_column()

    for label, items, fallback in (
        ("ip", j["ips"], "ip"),
        ("port", j["ports"], "ports"),
        ("mount", j["mounts"], "mounts"),
    ):
        if items:
            for i, item in enumerate(items):
                info.add_row(label if i == 0 else "", Text(item, style="dim white"))
        else:
            info.add_row(fallback, Text("—", style="dim white"))

    return info


def build_jail_table(j: JailRow, *, history: SampleHistory | None = None) -> Table:
    monit = j.get("monit")
    if not monit or not monit["services"]:
        tbl = Table.grid()
        tbl.add_row(Text("no monitored services", style="dim white"))
        return tbl

    has_sparks = history is not None

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
    tbl.add_column("status", no_wrap=True)
    tbl.add_column("cpu", no_wrap=True, justify="right")

    if has_sparks:
        tbl.add_column("", no_wrap=True)

    tbl.add_column("mem", no_wrap=True, justify="right")

    if has_sparks:
        tbl.add_column("", no_wrap=True)

    tbl.add_column("uptime", no_wrap=True, style="dim white")

    for svc in monit["services"]:
        svc_style = "green" if svc["status"] == "ok" else "red"
        cells: list[str | Text] = [
            Text(svc["name"], style="bold white"),
            Text(svc["status"], style=svc_style),
            Text(svc["cpu"] or "—", style="white" if svc["cpu"] else "dim white"),
        ]
        if history is not None:
            cells.append(history.cpu_spark(j["name"], svc["name"]))

        cells.append(Text(svc["mem"] or "—", style="white" if svc["mem"] else "dim white"))

        if history is not None:
            cells.append(history.mem_spark(j["name"], svc["name"]))

        cells.append(Text(svc["uptime"] or "—", style="dim white"))
        tbl.add_row(*cells)

    return tbl


def find_jail(data: StatusInfo, jail_name: str) -> JailRow:
    for j in data["jail_rows"]:
        if j["name"] == jail_name:
            return j

    err(f"Jail '{jail_name}' not found.")

    raise SystemExit(1)


def render_overview_table(data: StatusInfo, *, scopes: frozenset[Scope] = DEFAULT_SCOPES) -> None:
    c = con()
    c.print()
    c.print(_build_header(data))
    c.print()
    c.print(Padding(_build_vitals(data), pad=(0, 0, 0, 2)))
    c.print()

    if not data["jail_rows"]:
        c.print("  [dim]no jails[/dim]")
        c.print()
        return

    show_ip = "ip" in scopes
    show_services = "services" in scopes
    has_monit = any(j.get("monit") for j in data["jail_rows"])

    tbl = Table(
        show_header=True,
        header_style="dim",
        box=None,
        show_edge=False,
        padding=(0, 3, 0, 0),
        expand=False,
        pad_edge=False,
    )
    tbl.add_column("name", no_wrap=True, vertical="top")
    tbl.add_column("state", no_wrap=True, vertical="top")

    if show_services and has_monit:
        tbl.add_column("services", no_wrap=True, vertical="top")

    if show_ip:
        tbl.add_column("ip", style="dim white", no_wrap=True, vertical="top")

    tbl.add_column("ports", style="dim white", vertical="top")
    tbl.add_column("mounts", style="dim white", vertical="top")

    for j in data["jail_rows"]:
        name_t, state_t = _jail_labels(j)
        cells: list[str | Text] = [name_t, state_t]

        if show_services and has_monit:
            cells.append(_svc_summary_cell(j))

        if show_ip:
            cells.append(_multiline_cell(j["ips"]))

        cells.append(_multiline_cell(j["ports"]))
        cells.append(_multiline_cell(j["mounts"]))

        tbl.add_row(*cells)

    c.print(Padding(tbl, pad=(0, 0, 0, 2)))
    c.print()


def render_overview_tree(data: StatusInfo, *, scopes: frozenset[Scope] = DEFAULT_SCOPES) -> None:
    c = con()
    c.print()

    show_ip = "ip" in scopes
    show_services = "services" in scopes

    root = Tree(
        Text.assemble(
            ("● ", "bold green"),
            ("VM", "bold white"),
            ("  running", "green"),
            (f"  on {data['ssh_host']}:{data['ssh_port']}", "dim white"),
            (f"  (pid {data['pid']})", "dim white"),
        )
    )
    _add_vitals_to_tree(root, data)

    jails_node = root.add(Text("jails", style="bold"))
    if not data["jail_rows"]:
        jails_node.add(Text("no jails", style="dim white"))
    else:
        for j in data["jail_rows"]:
            name_t, state_t = _jail_labels(j)
            node = jails_node.add(name_t + Text("  ") + state_t)

            if show_ip:
                _add_tree_kv_rows(node, j["ips"], "ip", plural_label="ip")

            _add_tree_kv_rows(node, j["ports"], "port", plural_label="ports")
            _add_tree_kv_rows(node, j["mounts"], "mount", plural_label="mounts")

            monit = j.get("monit")
            if show_services and monit and monit["services"]:
                for i, svc in enumerate(monit["services"]):
                    svc_style = "green" if svc["status"] == "ok" else "red"
                    node.add(
                        Text.assemble(
                            ("service " if i == 0 else "        ", "dim cyan"),
                            (svc["name"], "dim white"),
                            ("  ", ""),
                            (svc["status"], svc_style),
                        )
                    )

    c.print(Padding(root, pad=(0, 0, 0, 2)))
    c.print()


def render_jail_table(data: StatusInfo, jail_name: str) -> None:
    c = con()
    j = find_jail(data, jail_name)
    c.print()
    c.print(jail_header(j))
    c.print()
    c.print(Padding(build_jail_info(j), pad=(0, 0, 0, 2)))
    c.print()
    c.print(Padding(build_jail_table(j), pad=(0, 0, 0, 2)))
    c.print()


def render_jail_tree(data: StatusInfo, jail_name: str, *, history: SampleHistory | None = None) -> None:
    c = con()
    j = find_jail(data, jail_name)
    c.print()

    name_t, state_t = _jail_labels(j)
    root = Tree(name_t + Text("  ") + state_t)

    _add_tree_kv_rows(root, j["ips"], "ip", plural_label="ip")
    _add_tree_kv_rows(root, j["ports"], "port", plural_label="ports")
    _add_tree_kv_rows(root, j["mounts"], "mount", plural_label="mounts")

    monit = j.get("monit")
    if monit and monit["services"]:
        svc_node = root.add(Text("services", style="bold"))
        for svc in monit["services"]:
            svc_style = "green" if svc["status"] == "ok" else "red"
            label = Text.assemble(
                (svc["name"], "bold white"),
                ("  ", ""),
                (svc["status"], svc_style),
            )
            node = svc_node.add(label)

            if svc["cpu"]:
                line = Text.assemble(("cpu     ", "dim cyan"), (svc["cpu"], "white"))
                if history:
                    line.append("  ")
                    line.append_text(history.cpu_spark(j["name"], svc["name"]))
                node.add(line)

            if svc["mem"]:
                line = Text.assemble(("mem     ", "dim cyan"), (svc["mem"], "white"))
                if history:
                    line.append("  ")
                    line.append_text(history.mem_spark(j["name"], svc["name"]))
                node.add(line)

            if svc["uptime"]:
                node.add(Text.assemble(("uptime  ", "dim cyan"), (svc["uptime"], "dim white")))

    c.print(Padding(root, pad=(0, 0, 0, 2)))
    c.print()
