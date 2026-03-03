from typing import Literal

import pytest

from jailrun.settings import BASE_URL, Settings


@pytest.mark.parametrize(
    "arch, expected_image",
    [
        (
            "amd64",
            f"{BASE_URL}/15.0-RELEASE/amd64/Latest/FreeBSD-15.0-RELEASE-amd64-BASIC-CLOUDINIT-zfs.raw.xz",
        ),
        (
            "aarch64",
            f"{BASE_URL}/15.0-RELEASE/aarch64/Latest/FreeBSD-15.0-RELEASE-arm64-aarch64-BASIC-CLOUDINIT-zfs.raw.xz",
        ),
    ],
)
def test_bsd_image_url_default_release_tag(arch: Literal["amd64", "aarch64"], expected_image: str) -> None:
    s = Settings(bsd_arch=arch, bsd_version="15.0", bsd_release_tag="RELEASE")
    assert str(s.bsd_image_url) == expected_image


@pytest.mark.parametrize(
    "arch, expected_checksum",
    [
        (
            "amd64",
            f"{BASE_URL}/15.0-RELEASE/amd64/Latest/CHECKSUM.SHA512",
        ),
        (
            "aarch64",
            f"{BASE_URL}/15.0-RELEASE/aarch64/Latest/CHECKSUM.SHA512",
        ),
    ],
)
def test_bsd_image_checksum_url_default_release_tag(arch: Literal["amd64", "aarch64"], expected_checksum: str) -> None:
    s = Settings(bsd_arch=arch, bsd_version="15.0", bsd_release_tag="RELEASE")
    assert str(s.bsd_image_checksum_url) == expected_checksum


@pytest.mark.parametrize(
    "arch, tag, expected_image, expected_checksum",
    [
        (
            "amd64",
            "RC1",
            f"{BASE_URL}/15.0-RC1/amd64/Latest/FreeBSD-15.0-RC1-amd64-BASIC-CLOUDINIT-zfs.raw.xz",
            f"{BASE_URL}/15.0-RC1/amd64/Latest/CHECKSUM.SHA512",
        ),
        (
            "aarch64",
            "RC1",
            f"{BASE_URL}/15.0-RC1/aarch64/Latest/FreeBSD-15.0-RC1-arm64-aarch64-BASIC-CLOUDINIT-zfs.raw.xz",
            f"{BASE_URL}/15.0-RC1/aarch64/Latest/CHECKSUM.SHA512",
        ),
    ],
)
def test_urls_with_rc_tag(
    arch: Literal["amd64", "aarch64"], tag: str, expected_image: str, expected_checksum: str
) -> None:
    s = Settings(bsd_arch=arch, bsd_version="15.0", bsd_release_tag=tag)
    assert str(s.bsd_image_url) == expected_image
    assert str(s.bsd_image_checksum_url) == expected_checksum
