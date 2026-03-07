import pytest

from jailrun.schemas import State
from jailrun.settings import Settings


@pytest.fixture(name="settings", scope="session")
def settings_fixture() -> Settings:
    return Settings()


@pytest.fixture(name="state")
def state_fixture() -> State:
    return State(ssh_port=2222)
