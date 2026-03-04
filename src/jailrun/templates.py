from functools import cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from jailrun import PACKAGE_DIR


@cache
def build_jinja_env(templates_dir: Path | None = None) -> Environment:
    jinja_env = Environment(
        loader=FileSystemLoader(templates_dir or PACKAGE_DIR / "files"),
        autoescape=True,
    )
    return jinja_env
