from pathlib import Path

from jailrun.cmd.pause import pause
from jailrun.cmd.up import up
from jailrun.settings import Settings


def restart(
    config: Path,
    *,
    base: Path | None,
    settings: Settings,
    names: list[str] | None = None,
) -> None:
    pause(config, settings=settings, names=names)
    up(config, base=base, settings=settings, names=names)
