import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import httpx
import typer

GITHUB_BLOB_RE = re.compile(
    r"^https://github\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)"
    r"/blob/"
    r"(?P<ref>[^/]+)"
    r"/(?P<path>.+)$"
)


@dataclass(frozen=True)
class RemotePlaybook:
    owner: str
    repo: str
    ref: str
    dir_path: str
    entry: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_manifest(*files: tuple[str, bytes]) -> bytes:
    return "\n".join(f"{sha256_bytes(c)}  {p}" for p, c in files).encode()


def parse_github_url(url: str) -> RemotePlaybook:
    """Convert a GitHub blob URL into its constituent parts.

    Accepts:
        https://github.com/owner/repo/blob/main/path/to/playbook.yml
        https://github.com/owner/repo/blob/v1.2.0/path/to/playbook.yml
    """
    m = GITHUB_BLOB_RE.match(url)
    if not m:
        typer.secho(f"Not a valid GitHub blob URL: {url}", fg=typer.colors.RED)
        raise typer.Exit(1)

    parts = PurePosixPath(m.group("path"))
    return RemotePlaybook(
        owner=m.group("owner"),
        repo=m.group("repo"),
        ref=m.group("ref"),
        dir_path=str(parts.parent) if parts.parent != PurePosixPath(".") else "",
        entry=parts.name,
    )


def raw_url(pb: RemotePlaybook, relative_path: str) -> str:
    """Build a raw.githubusercontent.com URL for a file relative to the playbook directory."""
    base = f"https://raw.githubusercontent.com/{pb.owner}/{pb.repo}/{pb.ref}"
    if pb.dir_path:
        return f"{base}/{pb.dir_path}/{relative_path}"
    return f"{base}/{relative_path}"


def cache_key(pb: RemotePlaybook) -> str:
    slug = f"{pb.owner}/{pb.repo}/{pb.ref}/{pb.dir_path}"
    digest = hashlib.sha256(slug.encode()).hexdigest()[:12]
    safe_ref = re.sub(r"[^\w.-]", "_", pb.ref)

    return f"{pb.repo}_{safe_ref}_{digest}"


def fetch(url: str) -> bytes:
    try:
        r = httpx.get(url, follow_redirects=True, timeout=30)
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        typer.secho(f"HTTP {exc.response.status_code} fetching {url}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    except httpx.RequestError as exc:
        typer.secho(f"Failed to fetch {url}: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    return r.content


def parse_manifest(content: str) -> dict[str, str]:
    """Parse a jrun.manifest file into {relative_path: sha256_hex}.

    Manifest format (one entry per line):
        <sha256hex>  <relative-path>
    """
    entries: dict[str, str] = {}
    for lineno, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            typer.secho(f"Malformed manifest line {lineno}: {line}", fg=typer.colors.RED)
            raise typer.Exit(1)
        sha256_hex, rel_path = parts
        entries[rel_path] = sha256_hex
    return entries


def fetch_remote_playbook(url: str, *, cache_dir: Path) -> Path:
    pb = parse_github_url(url)
    dest = cache_dir / cache_key(pb)

    manifest_url = raw_url(pb, "jrun.manifest")
    typer.echo(f"📋 Fetching manifest from {pb.owner}/{pb.repo}@{pb.ref}")
    manifest_bytes = fetch(manifest_url)
    manifest_entries = parse_manifest(manifest_bytes.decode())

    if pb.entry not in manifest_entries:
        typer.secho(
            f"Entrypoint '{pb.entry}' not listed in jrun.manifest",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    if cache_is_valid(dest, manifest_entries):
        typer.echo(f"Using cached playbook at {dest}")
        return dest / pb.entry

    dest.mkdir(parents=True, exist_ok=True)

    for rel_path, expected_hash in manifest_entries.items():
        file_url = raw_url(pb, rel_path)
        typer.echo(f"...{rel_path}")
        data = fetch(file_url)

        actual_hash = sha256_bytes(data)
        if actual_hash != expected_hash:
            typer.secho(
                f"Checksum mismatch for {rel_path}:\n  expected: {expected_hash}\n  got:      {actual_hash}",
                fg=typer.colors.RED,
            )
            raise typer.Exit(1)

        out = dest / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)

    (dest / "jrun.manifest").write_bytes(manifest_bytes)

    typer.secho(
        f"Playbook fetched and verified ({len(manifest_entries)} files)",
        fg=typer.colors.GREEN,
    )
    return dest / pb.entry


def cache_is_valid(dest: Path, manifest_entries: dict[str, str]) -> bool:
    if not dest.is_dir():
        return False
    for rel_path, expected_hash in manifest_entries.items():
        cached_file = dest / rel_path
        if not cached_file.exists():
            return False
        actual_hash = sha256_bytes(cached_file.read_bytes())
        if actual_hash != expected_hash:
            return False

    return True
