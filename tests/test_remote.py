from pathlib import Path

import httpx
import pytest
import respx
import typer

from jailrun.remote import (
    RemotePlaybook,
    build_manifest,
    cache_is_valid,
    cache_key,
    expand_hub_url,
    fetch_remote_playbook,
    parse_github_url,
    parse_manifest,
    raw_url,
    sha256_bytes,
)

RAW_BASE = "https://raw.githubusercontent.com"
SAMPLE_URL = "https://github.com/hyphatech/jailrun-hub/blob/main/playbooks/redis/rolling/playbook.yml"
MANIFEST_RAW = f"{RAW_BASE}/hyphatech/jailrun-hub/main/playbooks/redis/rolling/jrun.manifest"
PLAYBOOK_RAW = f"{RAW_BASE}/hyphatech/jailrun-hub/main/playbooks/redis/rolling/playbook.yml"
TEMPLATE_RAW = f"{RAW_BASE}/hyphatech/jailrun-hub/main/playbooks/redis/rolling/templates/index.html.j2"


def test_parse_main_branch() -> None:
    pb = parse_github_url(SAMPLE_URL)
    assert pb.owner == "hyphatech"
    assert pb.repo == "jailrun-hub"
    assert pb.ref == "main"
    assert pb.dir_path == "playbooks/redis/rolling"
    assert pb.entry == "playbook.yml"


def test_parse_tag_ref() -> None:
    url = "https://github.com/hyphatech/jailrun-hub/blob/v1.2.0/playbooks/redis/rolling/playbook.yml"
    assert parse_github_url(url).ref == "v1.2.0"


def test_parse_commit_sha() -> None:
    sha = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
    url = f"https://github.com/owner/repo/blob/{sha}/path/to/playbook.yml"
    pb = parse_github_url(url)
    assert pb.ref == sha
    assert pb.dir_path == "path/to"
    assert pb.entry == "playbook.yml"


def test_parse_file_at_repo_root() -> None:
    pb = parse_github_url("https://github.com/owner/repo/blob/main/playbook.yml")
    assert pb.dir_path == ""
    assert pb.entry == "playbook.yml"


def test_parse_invalid_url_exits() -> None:
    with pytest.raises(typer.Exit):
        parse_github_url("https://example.com/not-github")


def test_parse_tree_url_exits() -> None:
    with pytest.raises(typer.Exit):
        parse_github_url("https://github.com/owner/repo/tree/main/dir")


def test_raw_url_with_dir() -> None:
    pb = RemotePlaybook(
        owner="hyphatech",
        repo="jailrun-hub",
        ref="main",
        dir_path="playbooks/redis/rolling",
        entry="playbook.yml",
    )
    assert raw_url(pb, "playbook.yml") == PLAYBOOK_RAW


def test_raw_url_nested_relative() -> None:
    pb = RemotePlaybook(
        owner="o",
        repo="r",
        ref="v1",
        dir_path="base",
        entry="playbook.yml",
    )
    assert raw_url(pb, "templates/nginx.conf.j2") == (f"{RAW_BASE}/o/r/v1/base/templates/nginx.conf.j2")


def test_raw_url_empty_dir() -> None:
    pb = RemotePlaybook(
        owner="o",
        repo="r",
        ref="main",
        dir_path="",
        entry="playbook.yml",
    )
    assert raw_url(pb, "playbook.yml") == f"{RAW_BASE}/o/r/main/playbook.yml"


def test_cache_key_deterministic() -> None:
    pb = RemotePlaybook(owner="o", repo="r", ref="main", dir_path="p", entry="e")
    assert cache_key(pb) == cache_key(pb)


def test_cache_key_differs_by_ref() -> None:
    a = RemotePlaybook(owner="o", repo="r", ref="main", dir_path="p", entry="e")
    b = RemotePlaybook(owner="o", repo="r", ref="v1.0", dir_path="p", entry="e")
    assert cache_key(a) != cache_key(b)


def test_cache_key_sanitizes_slashes() -> None:
    pb = RemotePlaybook(owner="o", repo="r", ref="feat/bar", dir_path="p", entry="e")
    assert "/" not in cache_key(pb)


def test_manifest_standard() -> None:
    content = "aabbcc  playbook.yml\nddeeff  templates/index.html.j2\n"
    assert parse_manifest(content) == {
        "playbook.yml": "aabbcc",
        "templates/index.html.j2": "ddeeff",
    }


def test_manifest_blank_lines() -> None:
    assert parse_manifest("\naabbcc  playbook.yml\n\n") == {"playbook.yml": "aabbcc"}


def test_manifest_extra_whitespace() -> None:
    assert parse_manifest("  aabbcc  playbook.yml  \n") == {"playbook.yml": "aabbcc"}


def test_manifest_malformed_exits() -> None:
    with pytest.raises(typer.Exit):
        parse_manifest("no-space-here\n")


def test_manifest_path_with_spaces() -> None:
    assert parse_manifest("aabbcc  path with spaces/file.yml\n") == {
        "path with spaces/file.yml": "aabbcc",
    }


def test_cache_valid(tmp_path: Path) -> None:
    data = b"content"
    (tmp_path / "playbook.yml").write_bytes(data)
    assert cache_is_valid(tmp_path, {"playbook.yml": sha256_bytes(data)}) is True


def test_cache_missing_file(tmp_path: Path) -> None:
    assert cache_is_valid(tmp_path, {"missing.yml": "abc"}) is False


def test_cache_hash_mismatch(tmp_path: Path) -> None:
    (tmp_path / "playbook.yml").write_bytes(b"content")
    assert cache_is_valid(tmp_path, {"playbook.yml": "wrong"}) is False


def test_cache_nonexistent_dir(tmp_path: Path) -> None:
    assert cache_is_valid(tmp_path / "nope", {"f": "h"}) is False


def test_cache_nested_file(tmp_path: Path) -> None:
    data = b"template"
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "index.j2").write_bytes(data)
    assert cache_is_valid(tmp_path, {"templates/index.j2": sha256_bytes(data)}) is True


@respx.mock
def test_fetch_single_file(tmp_path: Path) -> None:
    playbook = b"---\n- hosts: all\n"
    manifest = build_manifest(("playbook.yml", playbook))

    respx.get(MANIFEST_RAW).mock(return_value=httpx.Response(200, content=manifest))
    respx.get(PLAYBOOK_RAW).mock(return_value=httpx.Response(200, content=playbook))

    result = fetch_remote_playbook(SAMPLE_URL, cache_dir=tmp_path)

    assert result.name == "playbook.yml"
    assert result.read_bytes() == playbook


@respx.mock
def test_fetch_multiple_files(tmp_path: Path) -> None:
    playbook = b"---\n- hosts: all\n"
    template = b"<html>{{ title }}</html>"
    manifest = build_manifest(
        ("playbook.yml", playbook),
        ("templates/index.html.j2", template),
    )

    respx.get(MANIFEST_RAW).mock(return_value=httpx.Response(200, content=manifest))
    respx.get(PLAYBOOK_RAW).mock(return_value=httpx.Response(200, content=playbook))
    respx.get(TEMPLATE_RAW).mock(return_value=httpx.Response(200, content=template))

    result = fetch_remote_playbook(SAMPLE_URL, cache_dir=tmp_path)

    assert result.read_bytes() == playbook
    assert (result.parent / "templates" / "index.html.j2").read_bytes() == template


@respx.mock
def test_fetch_checksum_mismatch_exits(tmp_path: Path) -> None:
    playbook = b"---\n- hosts: all\n"
    manifest = build_manifest(("playbook.yml", playbook))

    respx.get(MANIFEST_RAW).mock(return_value=httpx.Response(200, content=manifest))
    respx.get(PLAYBOOK_RAW).mock(return_value=httpx.Response(200, content=b"CORRUPTED"))

    with pytest.raises(typer.Exit):
        fetch_remote_playbook(SAMPLE_URL, cache_dir=tmp_path)


@respx.mock
def test_fetch_entrypoint_not_in_manifest_exits(tmp_path: Path) -> None:
    manifest = b"abc123  other_file.yml\n"
    respx.get(MANIFEST_RAW).mock(return_value=httpx.Response(200, content=manifest))

    with pytest.raises(typer.Exit):
        fetch_remote_playbook(SAMPLE_URL, cache_dir=tmp_path)


@respx.mock(assert_all_called=False)
def test_fetch_cache_hit_skips_download(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    playbook = b"---\n- hosts: all\n"
    manifest = build_manifest(("playbook.yml", playbook))

    manifest_route = respx_mock.get(MANIFEST_RAW).mock(
        return_value=httpx.Response(200, content=manifest),
    )
    playbook_route = respx_mock.get(PLAYBOOK_RAW).mock(
        return_value=httpx.Response(200, content=playbook),
    )

    first = fetch_remote_playbook(SAMPLE_URL, cache_dir=tmp_path)
    assert manifest_route.call_count == 1
    assert playbook_route.call_count == 1

    second = fetch_remote_playbook(SAMPLE_URL, cache_dir=tmp_path)
    assert first == second
    assert manifest_route.call_count == 2
    assert playbook_route.call_count == 1  # not fetched again


@respx.mock
def test_fetch_http_500_exits(tmp_path: Path) -> None:
    respx.get(MANIFEST_RAW).mock(return_value=httpx.Response(500))

    with pytest.raises(typer.Exit):
        fetch_remote_playbook(SAMPLE_URL, cache_dir=tmp_path)


@respx.mock
def test_fetch_connection_error_exits(tmp_path: Path) -> None:
    respx.get(MANIFEST_RAW).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(typer.Exit):
        fetch_remote_playbook(SAMPLE_URL, cache_dir=tmp_path)


def test_hub_expand_default_ref() -> None:
    result = expand_hub_url("hub://postgres/16")
    assert result == "https://github.com/hyphatech/jailrun-hub/blob/main/playbooks/postgres/16/playbook.yml"


def test_hub_expand_tag_ref() -> None:
    result = expand_hub_url("hub://nginx/rolling@v1.0.0")
    assert result == "https://github.com/hyphatech/jailrun-hub/blob/v1.0.0/playbooks/nginx/rolling/playbook.yml"


def test_hub_expand_semver_ref() -> None:
    result = expand_hub_url("hub://redis/rolling@v2.3.1")
    assert result == "https://github.com/hyphatech/jailrun-hub/blob/v2.3.1/playbooks/redis/rolling/playbook.yml"


def test_hub_expand_strips_trailing_slash() -> None:
    result = expand_hub_url("hub://postgres/16/")
    assert result == expand_hub_url("hub://postgres/16")


def test_hub_passthrough_https() -> None:
    url = "https://github.com/someone/repo/blob/main/playbooks/custom/playbook.yml"
    assert expand_hub_url(url) == url


def test_hub_passthrough_http() -> None:
    url = "http://internal.example.com/playbook.yml"
    assert expand_hub_url(url) == url


HUB_POSTGRES_URL = "hub://redis/rolling"
HUB_POSTGRES_EXPANDED = "https://github.com/hyphatech/jailrun-hub/blob/main/playbooks/redis/rolling/playbook.yml"
HUB_MANIFEST_RAW = f"{RAW_BASE}/hyphatech/jailrun-hub/main/playbooks/redis/rolling/jrun.manifest"
HUB_PLAYBOOK_RAW = f"{RAW_BASE}/hyphatech/jailrun-hub/main/playbooks/redis/rolling/playbook.yml"


@respx.mock
def test_fetch_hub_url(tmp_path: Path) -> None:
    playbook = b"---\n- hosts: all\n"
    manifest = build_manifest(("playbook.yml", playbook))

    respx.get(HUB_MANIFEST_RAW).mock(return_value=httpx.Response(200, content=manifest))
    respx.get(HUB_PLAYBOOK_RAW).mock(return_value=httpx.Response(200, content=playbook))

    result = fetch_remote_playbook(HUB_POSTGRES_URL, cache_dir=tmp_path)

    assert result.name == "playbook.yml"
    assert result.read_bytes() == playbook


HUB_TAG_URL = "hub://redis/rolling@v1.0.0"
HUB_TAG_MANIFEST_RAW = f"{RAW_BASE}/hyphatech/jailrun-hub/v1.0.0/playbooks/redis/rolling/jrun.manifest"
HUB_TAG_PLAYBOOK_RAW = f"{RAW_BASE}/hyphatech/jailrun-hub/v1.0.0/playbooks/redis/rolling/playbook.yml"


@respx.mock
def test_fetch_hub_url_with_tag(tmp_path: Path) -> None:
    playbook = b"---\n- hosts: all\n"
    manifest = build_manifest(("playbook.yml", playbook))

    respx.get(HUB_TAG_MANIFEST_RAW).mock(return_value=httpx.Response(200, content=manifest))
    respx.get(HUB_TAG_PLAYBOOK_RAW).mock(return_value=httpx.Response(200, content=playbook))

    result = fetch_remote_playbook(HUB_TAG_URL, cache_dir=tmp_path)

    assert result.name == "playbook.yml"
    assert result.read_bytes() == playbook
