import fcntl
import functools
import platform
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, TypeVar

import typer

from jailrun.ui import err


def current_arch() -> Literal["aarch64", "amd64"]:
    return "aarch64" if platform.machine() in {"aarch64", "arm64"} else "amd64"


@contextmanager
def lock(state_file: Path) -> Generator[None]:
    lock_path = state_file.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fp = open(lock_path, "w")  # noqa: SIM115
    try:
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        fp.close()
        err(
            f"Another jrun process is already running. If this is wrong, remove {lock_path}",
        )
        raise typer.Exit(1) from exc
    try:
        yield
    finally:
        fcntl.flock(fp, fcntl.LOCK_UN)
        fp.close()


F = TypeVar("F", bound=Callable[..., Any])


def exclusive(state_file: Path) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with lock(state_file):
                return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
