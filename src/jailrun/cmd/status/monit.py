import re
from dataclasses import dataclass, field
from typing import Literal

from .types import MonitJailStatus, MonitService

BlockType = Literal["system", "process", "program"]

HEADER_RE = re.compile(r"^(System|Process|Program)\s+'(.+)'\s*$")

COMPOUND_KEYS = (
    "cpu total",
    "memory usage",
    "monitoring status",
    "monitoring mode",
)


@dataclass
class MonitBlock:
    type: BlockType
    name: str
    fields: dict[str, str] = field(default_factory=dict)


def _parse_field_line(line: str) -> tuple[str, str] | None:
    lower = line.lower()
    for ck in COMPOUND_KEYS:
        if lower.startswith(ck):
            val = line[len(ck) :].strip()
            return (ck, val) if val else None

    parts = line.split(None, 1)

    return (parts[0].lower(), parts[1]) if len(parts) == 2 else None


def _tokenize(raw: str) -> list[MonitBlock]:
    blocks: list[MonitBlock] = []
    current: MonitBlock | None = None

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        m = HEADER_RE.match(stripped)
        if m:
            current = MonitBlock(
                type=m.group(1).lower(),  # type: ignore[arg-type]
                name=m.group(2),
            )
            blocks.append(current)
            continue

        if current is not None and "  " in stripped:
            pair = _parse_field_line(stripped)
            if pair:
                current.fields[pair[0]] = pair[1]

    return blocks


def _resolve_jail_and_exec(
    process_name: str,
    known_jails: set[str],
) -> tuple[str, str]:
    best_jail: str | None = None
    best_exec: str | None = None

    for jail in known_jails:
        prefix = jail + "-"
        if process_name.startswith(prefix) and (best_jail is None or len(jail) > len(best_jail)):
            best_jail = jail
            best_exec = process_name[len(prefix) :]

    if best_jail is not None and best_exec is not None:
        return best_jail, best_exec

    if "-" in process_name:
        return process_name.rsplit("-", 1)  # type: ignore[return-value]

    return process_name, process_name


def _extract_mem(raw: str | None) -> str | None:
    if not raw:
        return None
    if "[" in raw:
        return raw.split("[")[-1].rstrip("]").strip() or None

    return raw.strip() or None


def _interpret(blocks: list[MonitBlock]) -> dict[str, MonitJailStatus]:
    results: dict[str, MonitJailStatus] = {}

    for block in blocks:
        if block.type == "system" and block.name.endswith("-system"):
            jail_name = block.name.rsplit("-system", 1)[0]
            status_val = block.fields.get("status", "unknown").strip()
            results.setdefault(jail_name, MonitJailStatus(system_ok=None, services=[]))
            results[jail_name]["system_ok"] = status_val.upper() == "OK"

    known_jails = set(results.keys())

    for block in blocks:
        if block.type != "process":
            continue

        jail_name, exec_name = _resolve_jail_and_exec(block.name, known_jails)
        entry = results.setdefault(jail_name, MonitJailStatus(system_ok=None, services=[]))
        known_jails.add(jail_name)

        status_val = block.fields.get("status", "unknown").strip().lower()
        cpu_raw = block.fields.get("cpu total") or block.fields.get("cpu")

        entry["services"].append(
            MonitService(
                name=exec_name,
                status=status_val,
                cpu=cpu_raw.strip() if cpu_raw else None,
                mem=_extract_mem(block.fields.get("memory")),
                uptime=block.fields.get("uptime", "").strip() or None,
            )
        )

    return results


def parse_monit_status(raw: str) -> dict[str, MonitJailStatus]:
    return _interpret(_tokenize(raw))
