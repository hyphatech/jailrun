from pathlib import Path
from types import TracebackType
from typing import Self

from tenacity import retry, retry_if_result, stop_after_attempt, wait_fixed

from jailrun.cmd import up
from jailrun.cmd.status.collect import get_raw_jails
from jailrun.config import load_state
from jailrun.network import get_ssh_kw, wait_for_ssh
from jailrun.qemu import vm_is_running
from jailrun.schemas import State
from jailrun.settings import Settings
from jailrun.settings import settings as default_settings


class Jail:
    def __init__(
        self,
        jail: str,
        *,
        jail_config: Path,
        settings: Settings | None = None,
    ) -> None:
        self._jail_config = jail_config.resolve()
        self._settings = settings or default_settings
        self._state: State
        self._jail_ip: str
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
        ssh_kw = get_ssh_kw(self._settings, state)
        wait_for_ssh(ssh_kw=ssh_kw, silent=True)

        jail_state = state.jails.get(jail)

        raw_jails = get_raw_jails(ssh_kw, state=state)
        jail_private_names = {j["private_name"]: j for j in raw_jails}

        private_name = str(jail_state.private_name) if jail_state else None
        raw_jail = jail_private_names.get(private_name) if private_name else None

        if (jail not in state.jails) or (raw_jail is None) or (raw_jail["state"].upper() != "UP"):
            up(
                config=self._jail_config,
                state=state,
                settings=self._settings,
                names=[jail],
            )
            state = load_state(self._settings.state_file)

        ip = state.jails[jail].ip
        if not ip:
            raise RuntimeError(f"Jail '{jail}' has no IP assigned.")

        self._state = state
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
