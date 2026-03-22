from collections import defaultdict, deque

from rich.text import Text

from .types import JailRow

SPARK_WIDTH = 20

# Braille dot positions (bottom=row0 to top=row3)
# Left column: row0=0x40, row1=0x04, row2=0x02, row3=0x01
# Right column: row0=0x80, row1=0x20, row2=0x10, row3=0x08
_BRAILLE_LEFT = (0x40, 0x04, 0x02, 0x01)
_BRAILLE_RIGHT = (0x80, 0x20, 0x10, 0x08)
_BRAILLE_BASE = 0x2800
_BRAILLE_ROWS = 4

_SPARK_GRADIENT = ("green", "green", "yellow", "red")


def _col_fill(row: int, bits: tuple[int, ...]) -> int:
    code = 0
    for r in range(row + 1):
        code |= bits[r]
    return code


def sparkline_text(
    values: list[float],
    *,
    floor: float = 0.0,
    ceil: float = 100.0,
    width: int = SPARK_WIDTH,
) -> Text:
    n_samples = width * 2
    tail = list(values[-n_samples:])
    padding = [None] * max(0, n_samples - len(tail))
    padded: list[float | None] = padding + tail

    effective_range = ceil - floor if ceil > floor else 1.0
    max_row = _BRAILLE_ROWS - 1

    result = Text("")
    for i in range(0, len(padded), 2):
        lv = padded[i]
        rv = padded[i + 1] if i + 1 < len(padded) else None

        code = 0
        peak = -1

        if lv is not None:
            ratio = max(0.0, min((lv - floor) / effective_range, 1.0))
            row = int(ratio * max_row)
            code |= _col_fill(row, _BRAILLE_LEFT)
            peak = max(peak, row)

        if rv is not None:
            ratio = max(0.0, min((rv - floor) / effective_range, 1.0))
            row = int(ratio * max_row)
            code |= _col_fill(row, _BRAILLE_RIGHT)
            peak = max(peak, row)

        if code == 0:
            result.append(" ")
        else:
            result.append(chr(_BRAILLE_BASE + code), style=_SPARK_GRADIENT[peak])

    return result


def _parse_cpu(raw: str | None) -> float | None:
    if not raw:
        return None

    try:
        return float(raw.replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def _parse_mem_mb(raw: str | None) -> float | None:
    if not raw:
        return None

    raw = raw.strip()

    try:
        upper = raw.upper()
        if upper.endswith("GB"):
            return float(raw[:-2].strip()) * 1024
        if upper.endswith("MB"):
            return float(raw[:-2].strip())
        if upper.endswith("KB"):
            return float(raw[:-2].strip()) / 1024
        return float(raw)
    except (ValueError, TypeError):
        return None


class SampleHistory:
    def __init__(self, maxlen: int = SPARK_WIDTH) -> None:
        self._cpu: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=maxlen))
        self._mem: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=maxlen))

    def record(self, jail_name: str, svc_name: str, *, cpu: float | None, mem_mb: float | None) -> None:
        key = f"{jail_name}:{svc_name}"
        if cpu is not None:
            self._cpu[key].append(cpu)
        if mem_mb is not None:
            self._mem[key].append(mem_mb)

    def cpu_spark(self, jail_name: str, svc_name: str) -> Text:
        vals = list(self._cpu.get(f"{jail_name}:{svc_name}", []))
        return sparkline_text(vals, floor=0.0, ceil=100.0)

    def mem_spark(self, jail_name: str, svc_name: str) -> Text:
        vals = list(self._mem.get(f"{jail_name}:{svc_name}", []))
        if not vals:
            return sparkline_text([], floor=0.0, ceil=1.0)

        mean = sum(vals) / len(vals)
        margin = max(mean * 0.3, 1.0)

        return sparkline_text(vals, floor=max(0.0, mean - margin), ceil=mean + margin)

    def ingest_jail(self, j: JailRow) -> None:
        monit = j.get("monit")
        if not monit:
            return

        for svc in monit["services"]:
            self.record(
                j["name"],
                svc["name"],
                cpu=_parse_cpu(svc["cpu"]),
                mem_mb=_parse_mem_mb(svc["mem"]),
            )

    def ingest(self, jail_rows: list[JailRow]) -> None:
        for j in jail_rows:
            self.ingest_jail(j)
