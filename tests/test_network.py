import socket
from pathlib import Path

import pytest

from jailrun import network
from jailrun.schemas import State
from jailrun.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    root = tmp_path / "jrun"
    ssh_dir = root / "ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        ssh_dir=ssh_dir,
        log_dir=root / "logs",
        disk_dir=root / "disks",
        cloud_dir=root / "cloud",
        pid_file=root / "vm.pid",
        state_file=root / "state.json",
    )


def test_resolve_ssh_port_switches_when_existing_port_is_busy(settings: Settings) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((settings.vm_host, 2500))
        sock.listen(1)

        state = State(ssh_port=2500)
        resolved = network.resolve_ssh_port(state, settings=settings)

        assert resolved != 2500
        assert state.ssh_port == resolved
        assert network.is_port_free(resolved, settings.vm_host) is True


def test_is_port_free_returns_false_for_bound_port(settings: Settings) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((settings.vm_host, 0))
        sock.listen(1)
        busy_port = sock.getsockname()[1]

        assert network.is_port_free(busy_port, settings.vm_host) is False


def test_is_port_free_returns_true_after_port_is_released(settings: Settings) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((settings.vm_host, 0))
        port = sock.getsockname()[1]

    assert network.is_port_free(port, settings.vm_host) is True


def test_find_free_port_skips_busy_port(settings: Settings) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((settings.vm_host, 0))
        sock.listen(1)
        busy_port = sock.getsockname()[1]

        free_port = network.find_free_port(busy_port, settings.vm_host, search_range=5)

        assert free_port > busy_port


def test_find_free_port_raises_when_range_is_exhausted(settings: Settings) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((settings.vm_host, 0))
        sock.listen(1)
        busy_port = sock.getsockname()[1]

        with pytest.raises(RuntimeError, match="No free port found"):
            network.find_free_port(busy_port, settings.vm_host, search_range=1)


def test_get_ssh_kw_prefers_state_port(settings: Settings) -> None:
    state = State(ssh_port=2601)

    kw = network.get_ssh_kw(settings, state)

    assert kw["ssh_port"] == 2601
    assert kw["ssh_host"] == settings.vm_host
    assert kw["ssh_user"] == settings.ssh_user
    assert kw["private_key"] == Path(settings.ssh_dir) / settings.ssh_key


def test_ensure_vm_key_generates_real_keypair(tmp_path: Path) -> None:
    private_key = tmp_path / "id_ed25519"
    public_key = tmp_path / "id_ed25519.pub"

    pub = network.ensure_vm_key(private_key, public_key)

    assert private_key.exists()
    assert public_key.exists()

    assert pub == public_key.read_text().strip()
    assert pub.startswith("ssh-ed25519 ")
