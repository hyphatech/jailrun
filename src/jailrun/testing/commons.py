from pathlib import Path
from types import TracebackType
from typing import Self

from tenacity import retry, retry_if_result, stop_after_attempt, wait_fixed

from jailrun.cmd import up
from jailrun.cmd.status import get_bastille_jails
from jailrun.config import load_state
from jailrun.qemu import vm_is_running
from jailrun.settings import Settings
from jailrun.settings import settings as default_settings
from jailrun.ssh import get_ssh_kw, wait_for_ssh


class Jail:
    def __init__(
        self,
        config: Path,
        jail: str,
        *,
        base: Path | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._config = config.resolve()
        self._base = base.resolve() if base else None
        self._settings = settings or default_settings
        self._get_jail_ip(jail)
        self._wait_ready()

    @retry(
        stop=stop_after_attempt(30),
        wait=wait_fixed(2),
        retry=retry_if_result(lambda ready: not ready),
    )
    def _wait_ready(self) -> bool:
        return self.is_ready()

    def _get_jail_ip(self, jail: str) -> None:
        alive, _ = vm_is_running(self._settings.pid_file)

        if not alive:
            raise RuntimeError("VM is not running. Run 'jrun start' first.")

        state = load_state(self._settings.state_file)

        ssh_kw = get_ssh_kw(self._settings)
        wait_for_ssh(**ssh_kw, silent=True)

        bastille_jails = get_bastille_jails(**ssh_kw)

        grouped_bastille_jails = {j["name"]: j for j in bastille_jails}
        bastille_jail = grouped_bastille_jails.get(jail)

        if (jail not in state.jails) or (bastille_jail is None) or (bastille_jail["state"].upper() != "UP"):
            up(config=self._config, base=self._base, settings=self._settings, names=[jail])
            state = load_state(self._settings.state_file)

        ip = state.jails[jail].ip
        if not ip:
            raise RuntimeError(f"Jail '{jail}' has no IP assigned.")

        self._jail_ip = ip

    def is_ready(self) -> bool:
        return False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass
