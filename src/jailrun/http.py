import hashlib
import re
from pathlib import Path

import httpx
import typer
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

CHUNK_SIZE = 1024 * 1024


def sha512_file(path: Path) -> str:
    h = hashlib.sha512()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_checksum(bsd_image_url: str, bsd_image_checksum_url: str) -> str:
    r = httpx.get(bsd_image_checksum_url, follow_redirects=True, timeout=30)
    r.raise_for_status()

    image_xz = Path(bsd_image_url).name

    pattern = re.compile(rf"^SHA512 \({re.escape(image_xz)}\) = ([0-9a-fA-F]+)$")
    for line in r.text.splitlines():
        m = pattern.match(line.strip())
        if m:
            return m.group(1)

    raise RuntimeError("Checksum not found")


def download(bsd_image_url: str, bsd_image_checksum_url: str, *, target_dir: Path) -> None:
    image_xz_name = Path(bsd_image_url).name
    out_path = target_dir / image_xz_name
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")

    if out_path.exists():
        typer.secho("Image already downloaded.", fg=typer.colors.GREEN)
        return

    typer.echo("Fetching checksum...")
    expected = fetch_checksum(bsd_image_url, bsd_image_checksum_url)

    downloaded = tmp_path.stat().st_size if tmp_path.exists() else 0
    headers = {"Range": f"bytes={downloaded}-"} if downloaded else {}

    with httpx.stream("GET", bsd_image_url, headers=headers, follow_redirects=True, timeout=None) as r:
        r.raise_for_status()

        if downloaded and r.status_code == 200:
            tmp_path.unlink(missing_ok=True)
            downloaded = 0

        total = int(r.headers.get("Content-Length", 0)) + downloaded
        mode = "ab" if downloaded else "wb"

        with Progress(
            TextColumn("Downloading base system: [bold]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task(image_xz_name, total=total, completed=downloaded)

            with tmp_path.open(mode) as f:
                for chunk in r.iter_bytes(CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))

    if sha512_file(tmp_path) != expected:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError("Checksum mismatch")

    tmp_path.replace(out_path)
    typer.secho(f"Downloaded {out_path.name}", fg=typer.colors.GREEN)
