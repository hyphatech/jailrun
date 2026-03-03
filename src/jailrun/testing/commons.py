from pathlib import Path
from types import TracebackType
from typing import Self

from jailrun.cmd import up
from jailrun.settings import Settings
from jailrun.settings import settings as default_settings


class Jail:
    def __init__(self, config: Path, *, base: Path | None = None, settings: Settings | None = None) -> None:
        self._config = config.resolve()
        self._base = base.resolve() if base else None
        self._settings = settings or default_settings

    def is_ready(self) -> bool:
        return False

    def __enter__(self) -> Self:
        if not self.is_ready():
            up(config=self._config, base=self._base, settings=self._settings)

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass
